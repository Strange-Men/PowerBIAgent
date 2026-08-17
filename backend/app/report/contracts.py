"""M3.4 capability-driven report template and deterministic data-plan contracts.

This module owns no execution capability.  A TemplateContract is now a fixed
*allowed capability catalog*: fixed design rules + allowed analysis goals, not
fixed output content (ADR-011 supersedes ADR-010's one-fingerprint / four-query
binding).  The runtime schema decides which registered capabilities resolve;
the deterministic planner picks the requested subset; every resolved sub-query
still reuses the sealed M2 execution chain.

Per-requirement availability is computed here from the runtime schema only.
LLM drafts, expected values, result objects and free query descriptions
never enter this module.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.app.query_plan.template_catalog import DEFAULT_TEMPLATE_CATALOG
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    SemanticModelSchema,
)


class ReportSchemaObjectType(str, Enum):
    FIELD = "field"
    MEASURE = "measure"


class ReportQueryShape(str, Enum):
    SCALAR = "scalar"
    GROUPED = "grouped"
    ORDERED_TOP_N = "ordered_top_n"


class ReportAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    UNKNOWN_TEMPLATE = "unknown_template"
    TEMPLATE_NOT_AVAILABLE = "template_not_available"
    CONTRACT_CONFIGURATION_ERROR = "contract_configuration_error"
    SEMANTIC_MODEL_MISMATCH = "semantic_model_mismatch"


class ReportContractError(ValueError):
    def __init__(self, code: str, errors: tuple[str, ...] = ()):
        super().__init__(code)
        self.code = code
        self.errors = errors


class TemplateSchemaBinding(BaseModel):
    """Template binding is model-scoped; capability availability is decided
    per requirement against the runtime schema (ADR-011)."""

    semantic_model_key: str = Field(..., min_length=1)

    model_config = ConfigDict(frozen=True)


class ReportSchemaRequirement(BaseModel):
    object_type: ReportSchemaObjectType
    table_name: str = Field(..., min_length=1)
    canonical_name: str = Field(..., min_length=1)
    accepted_data_types: tuple[str, ...] = Field(..., min_length=1)

    model_config = ConfigDict(frozen=True)


class ReportQueryRequirement(BaseModel):
    key: str = Field(..., min_length=1)
    shape: ReportQueryShape
    measures: tuple[str, ...] = Field(..., min_length=1, max_length=1)
    dimensions: tuple[str, ...] = ()
    # M3.4: deterministic ownership hint for star-schema duplicated columns
    # (e.g. Sales[Region] vs Region[Region]).  Single-dimension queries only.
    dimension_table: str | None = None
    # M3.4: display-only ordering of verified grouped rows (time points).
    # Ordering never creates business values; it only fixes presentation order.
    dimension_order: Literal["asc", "desc"] | None = None
    sort: str | None = None
    top_n: int | None = Field(default=None, ge=1)
    # Objects the runtime schema must provide for this requirement to resolve.
    required_objects: tuple[ReportSchemaRequirement, ...] = ()

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_shape(self) -> "ReportQueryRequirement":
        if self.shape == ReportQueryShape.SCALAR:
            if self.dimensions or self.sort is not None or self.top_n is not None:
                raise ValueError("report_scalar_requirement_invalid")
        elif self.shape == ReportQueryShape.GROUPED:
            if not self.dimensions or self.sort is not None or self.top_n is not None:
                raise ValueError("report_grouped_requirement_invalid")
        elif self.shape == ReportQueryShape.ORDERED_TOP_N:
            if not self.dimensions or self.sort not in {"asc", "desc"}:
                raise ValueError("report_topn_requirement_invalid")
            if self.top_n is None:
                raise ValueError("report_topn_requirement_invalid")
        if self.dimension_table is not None and len(self.dimensions) != 1:
            raise ValueError("report_dimension_table_requires_single_dimension")
        if self.dimension_order is not None and (
            self.shape != ReportQueryShape.GROUPED or not self.dimensions
        ):
            raise ValueError("report_dimension_order_requires_grouped_dimension")
        return self


class ReportMetadataContract(BaseModel):
    include_data_source: bool = True
    include_filters: bool = True
    include_time_range: bool = True
    include_generated_at: bool = True

    model_config = ConfigDict(frozen=True)


class TemplateContract(BaseModel):
    template_key: str = Field(..., min_length=1)
    contract_version: str = Field(..., min_length=1)
    binding: TemplateSchemaBinding
    query_requirements: tuple[ReportQueryRequirement, ...]
    metadata: ReportMetadataContract = ReportMetadataContract()

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_contract(self) -> "TemplateContract":
        query_keys = [item.key for item in self.query_requirements]
        if len(query_keys) != len(set(query_keys)):
            raise ValueError("report_contract_duplicate_query_key")
        # A contract may reference one object from several requirements; only
        # exact duplicates inside one requirement are invalid.
        for requirement in self.query_requirements:
            refs = {
                (item.object_type, item.table_name, item.canonical_name)
                for item in requirement.required_objects
            }
            if len(refs) != len(requirement.required_objects):
                raise ValueError("report_contract_duplicate_schema_requirement")
            measure_objects = {
                item.canonical_name
                for item in requirement.required_objects
                if item.object_type == ReportSchemaObjectType.MEASURE
            }
            if any(name not in measure_objects for name in requirement.measures):
                raise ValueError("report_contract_query_measure_not_required")
            field_objects = {
                item.canonical_name
                for item in requirement.required_objects
                if item.object_type == ReportSchemaObjectType.FIELD
            }
            if any(name not in field_objects for name in requirement.dimensions):
                raise ValueError("report_contract_query_dimension_not_required")
        return self


class RequirementAvailability(BaseModel):
    """Per-requirement capability resolution against one runtime schema."""

    requirement_key: str
    available: bool
    missing: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


class ReportContractValidation(BaseModel):
    status: ReportAvailabilityStatus
    template_key: str
    runtime_schema_fingerprint: str | None = None
    errors: tuple[str, ...] = ()
    contract: TemplateContract | None = None
    requirement_availability: tuple[RequirementAvailability, ...] = ()

    model_config = ConfigDict(frozen=True)

    @property
    def available(self) -> bool:
        return self.status == ReportAvailabilityStatus.AVAILABLE


class ReportDataQuery(BaseModel):
    requirement_key: str
    shape: ReportQueryShape
    query_plan: CanonicalQueryPlan

    model_config = ConfigDict(frozen=True)


class ReportDataPlan(BaseModel):
    template_key: str
    contract_version: str
    semantic_model_key: str
    schema_fingerprint: str
    queries: tuple[ReportDataQuery, ...]
    metadata: ReportMetadataContract

    model_config = ConfigDict(frozen=True)


# ── M3.4 sales_report capability catalog ───────────────────────────────────
# Fixed design rules + allowed analysis goals.  The runtime schema decides
# which of these resolve; the deterministic planner selects the requested
# subset.  No LLM draft, fingerprint gate or free query description here.

_NUMERIC_SALES = ("Double", "Int64")
_STRING = ("String",)
_DATETIME = ("DateTime", "Date")


def _measure(table: str, name: str, data_types: tuple[str, ...]) -> ReportSchemaRequirement:
    return ReportSchemaRequirement(
        object_type=ReportSchemaObjectType.MEASURE,
        table_name=table,
        canonical_name=name,
        accepted_data_types=data_types,
    )


def _field(table: str, name: str, data_types: tuple[str, ...]) -> ReportSchemaRequirement:
    return ReportSchemaRequirement(
        object_type=ReportSchemaObjectType.FIELD,
        table_name=table,
        canonical_name=name,
        accepted_data_types=data_types,
    )


SALES_REPORT_CONTRACT = TemplateContract(
    template_key="sales_report",
    contract_version="2.0",
    binding=TemplateSchemaBinding(semantic_model_key="local_desktop_model"),
    query_requirements=(
        ReportQueryRequirement(
            key="total_sales",
            shape=ReportQueryShape.SCALAR,
            measures=("Total Sales",),
            required_objects=(
                _measure("Sales", "Total Sales", _NUMERIC_SALES),
            ),
        ),
        ReportQueryRequirement(
            key="total_quantity",
            shape=ReportQueryShape.SCALAR,
            measures=("Total Quantity",),
            required_objects=(
                _measure("Sales", "Total Quantity", _NUMERIC_SALES),
            ),
        ),
        ReportQueryRequirement(
            key="total_orders",
            shape=ReportQueryShape.SCALAR,
            measures=("Total Orders",),
            required_objects=(
                _measure("Sales", "Total Orders", _NUMERIC_SALES),
            ),
        ),
        ReportQueryRequirement(
            key="average_order_value",
            shape=ReportQueryShape.SCALAR,
            measures=("Average Order Value",),
            required_objects=(
                _measure("Sales", "Average Order Value", _NUMERIC_SALES),
            ),
        ),
        ReportQueryRequirement(
            key="monthly_sales",
            shape=ReportQueryShape.GROUPED,
            measures=("Total Sales",),
            dimensions=("YearMonth",),
            dimension_table="Date",
            dimension_order="asc",
            required_objects=(
                _measure("Sales", "Total Sales", _NUMERIC_SALES),
                _field("Date", "YearMonth", _DATETIME),
            ),
        ),
        ReportQueryRequirement(
            key="sales_by_category",
            shape=ReportQueryShape.GROUPED,
            measures=("Total Sales",),
            dimensions=("Category",),
            dimension_table="Sales",
            required_objects=(
                _measure("Sales", "Total Sales", _NUMERIC_SALES),
                _field("Sales", "Category", _STRING),
            ),
        ),
        ReportQueryRequirement(
            key="sales_by_region",
            shape=ReportQueryShape.GROUPED,
            measures=("Total Sales",),
            dimensions=("Region",),
            dimension_table="Sales",
            required_objects=(
                _measure("Sales", "Total Sales", _NUMERIC_SALES),
                _field("Sales", "Region", _STRING),
            ),
        ),
        ReportQueryRequirement(
            key="top_products",
            shape=ReportQueryShape.ORDERED_TOP_N,
            measures=("Total Sales",),
            dimensions=("Product",),
            dimension_table="Sales",
            sort="desc",
            top_n=5,
            required_objects=(
                _measure("Sales", "Total Sales", _NUMERIC_SALES),
                _field("Sales", "Product", _STRING),
            ),
        ),
        ReportQueryRequirement(
            key="top_customers",
            shape=ReportQueryShape.ORDERED_TOP_N,
            measures=("Total Sales",),
            dimensions=("Customer",),
            dimension_table="Sales",
            sort="desc",
            top_n=5,
            required_objects=(
                _measure("Sales", "Total Sales", _NUMERIC_SALES),
                _field("Sales", "Customer", _STRING),
            ),
        ),
    ),
)


REPORT_TEMPLATE_CONTRACTS: Mapping[str, TemplateContract] = MappingProxyType({
    SALES_REPORT_CONTRACT.template_key: SALES_REPORT_CONTRACT,
})


class ReportContractValidator:
    """Resolve registry-owned templates and per-requirement capabilities."""

    def __init__(
        self,
        contracts: Mapping[str, TemplateContract] = REPORT_TEMPLATE_CONTRACTS,
    ) -> None:
        self._contracts = MappingProxyType(dict(contracts))

    def validate(
        self,
        template_key: str,
        schema: SemanticModelSchema,
    ) -> ReportContractValidation:
        definition = DEFAULT_TEMPLATE_CATALOG.get_definition(template_key)
        if definition is None:
            return ReportContractValidation(
                status=ReportAvailabilityStatus.UNKNOWN_TEMPLATE,
                template_key=template_key,
                errors=("report_template_unknown",),
            )
        if not definition.allowed:
            return ReportContractValidation(
                status=ReportAvailabilityStatus.TEMPLATE_NOT_AVAILABLE,
                template_key=template_key,
                errors=("report_template_not_available",),
            )
        contract = self._contracts.get(template_key)
        if contract is None:
            return ReportContractValidation(
                status=ReportAvailabilityStatus.CONTRACT_CONFIGURATION_ERROR,
                template_key=template_key,
                errors=("report_template_contract_missing",),
            )
        runtime_fingerprint = compute_schema_fingerprint(schema)
        if schema.key != contract.binding.semantic_model_key:
            return ReportContractValidation(
                status=ReportAvailabilityStatus.SEMANTIC_MODEL_MISMATCH,
                template_key=template_key,
                runtime_schema_fingerprint=runtime_fingerprint,
                errors=("report_contract_semantic_model_mismatch",),
                contract=contract,
            )
        availability = tuple(
            RequirementAvailability(
                requirement_key=requirement.key,
                available=self._requirement_available(requirement, schema),
                missing=self._requirement_missing(requirement, schema),
            )
            for requirement in contract.query_requirements
        )
        return ReportContractValidation(
            status=ReportAvailabilityStatus.AVAILABLE,
            template_key=template_key,
            runtime_schema_fingerprint=runtime_fingerprint,
            contract=contract,
            requirement_availability=availability,
        )

    def requirement_available(
        self,
        contract: TemplateContract,
        requirement_key: str,
        schema: SemanticModelSchema,
    ) -> bool:
        requirement = next(
            (item for item in contract.query_requirements if item.key == requirement_key),
            None,
        )
        if requirement is None:
            return False
        return self._requirement_available(requirement, schema)

    @staticmethod
    def _visible_tables(schema: SemanticModelSchema) -> dict[str, object]:
        return {
            table.name: table
            for table in schema.tables
            if not table.is_hidden and not table.is_system_managed
        }

    @classmethod
    def _requirement_missing(
        cls, requirement: ReportQueryRequirement, schema: SemanticModelSchema
    ) -> tuple[str, ...]:
        visible_tables = cls._visible_tables(schema)
        missing: list[str] = []
        for item in requirement.required_objects:
            table = visible_tables.get(item.table_name)
            if table is None:
                missing.append(
                    f"report_contract_table_missing:{item.table_name}"
                )
                continue
            objects = (
                table.columns
                if item.object_type == ReportSchemaObjectType.FIELD
                else table.measures
            )
            matches = [
                candidate
                for candidate in objects
                if candidate.name == item.canonical_name and not candidate.is_hidden
            ]
            if len(matches) != 1:
                missing.append(
                    "report_contract_object_missing_or_ambiguous:"
                    f"{item.object_type.value}:"
                    f"{item.table_name}.{item.canonical_name}"
                )
                continue
            accepted = {
                value.casefold() for value in item.accepted_data_types
            }
            if matches[0].data_type.casefold() not in accepted:
                missing.append(
                    "report_contract_data_type_mismatch:"
                    f"{item.object_type.value}:"
                    f"{item.table_name}.{item.canonical_name}"
                )
        return tuple(missing)

    @classmethod
    def _requirement_available(
        cls, requirement: ReportQueryRequirement, schema: SemanticModelSchema
    ) -> bool:
        return not cls._requirement_missing(requirement, schema)


class ReportDataPlanBuilder:
    """Create the requested deterministic sub-queries from TemplateContract,
    never from LLM output."""

    def __init__(
        self,
        validator: ReportContractValidator | None = None,
    ) -> None:
        self._validator = validator or ReportContractValidator()

    def build(
        self,
        template_key: str,
        schema: SemanticModelSchema,
        *,
        requirement_keys: tuple[str, ...] | None = None,
    ) -> ReportDataPlan:
        validation = self._validator.validate(template_key, schema)
        if not validation.available or validation.contract is None:
            raise ReportContractError(validation.status.value, validation.errors)
        contract = validation.contract

        selected = contract.query_requirements
        if requirement_keys is not None:
            unknown = set(requirement_keys) - {
                item.key for item in contract.query_requirements
            }
            if unknown:
                raise ReportContractError(
                    "report_requirement_key_unknown", tuple(sorted(unknown))
                )
            by_key = {item.key: item for item in contract.query_requirements}
            selected = tuple(by_key[key] for key in requirement_keys)

        failed: list[RequirementAvailability] = []
        for item in selected:
            resolved = self._resolved_availability(
                validation, contract, schema, item.key
            )
            if not resolved.available:
                failed.append(resolved)
        if failed:
            raise ReportContractError(
                "report_requirement_unavailable",
                tuple(f"{item.requirement_key}:{item.missing}" for item in failed),
            )
        queries = tuple(
            ReportDataQuery(
                requirement_key=requirement.key,
                shape=requirement.shape,
                query_plan=CanonicalQueryPlan(
                    normalized_question=(
                        f"template:{contract.template_key}/"
                        f"requirement:{requirement.key}"
                    ),
                    semantic_model_key=schema.key,
                    measures=list(requirement.measures),
                    dimensions=list(requirement.dimensions),
                    sort=requirement.sort,
                    top_n=requirement.top_n,
                    requested_template=contract.template_key,
                    is_mock=False,
                    dimension_tables=(
                        {requirement.dimensions[0]: requirement.dimension_table}
                        if requirement.dimension_table is not None
                        else None
                    ),
                    dimension_order=requirement.dimension_order,
                ),
            )
            for requirement in selected
        )
        return ReportDataPlan(
            template_key=contract.template_key,
            contract_version=contract.contract_version,
            semantic_model_key=schema.key,
            schema_fingerprint=validation.runtime_schema_fingerprint or "",
            queries=queries,
            metadata=contract.metadata,
        )

    @staticmethod
    def _resolved_availability(
        validation: ReportContractValidation,
        contract: TemplateContract,
        schema: SemanticModelSchema,
        requirement_key: str,
    ) -> RequirementAvailability:
        known = {
            item.requirement_key: item
            for item in validation.requirement_availability
        }
        if requirement_key in known:
            return known[requirement_key]
        requirement = next(
            (
                item
                for item in contract.query_requirements
                if item.key == requirement_key
            ),
            None,
        )
        if requirement is None:
            return RequirementAvailability(
                requirement_key=requirement_key, available=False,
                missing=("report_requirement_unknown",),
            )
        return RequirementAvailability(
            requirement_key=requirement_key,
            available=ReportContractValidator._requirement_available(
                requirement, schema
            ),
            missing=ReportContractValidator._requirement_missing(
                requirement, schema
            ),
        )
