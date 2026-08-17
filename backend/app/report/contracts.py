"""M3 fixed report-template and deterministic data-plan contracts.

This module owns no execution capability. It validates one runtime schema and
emits CanonicalQueryPlan objects for the already sealed M2 execution chain.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.app.query_plan.template_catalog import DEFAULT_TEMPLATE_CATALOG
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    SemanticModelSchema,
)


M3_SALES_SCHEMA_FINGERPRINT = (
    "d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac"
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
    SCHEMA_INCOMPATIBLE = "schema_incompatible"
    SCHEMA_FINGERPRINT_MISMATCH = "schema_fingerprint_mismatch"


class ReportContractError(ValueError):
    def __init__(self, code: str, errors: tuple[str, ...] = ()):
        super().__init__(code)
        self.code = code
        self.errors = errors


class TemplateSchemaBinding(BaseModel):
    semantic_model_key: str = Field(..., min_length=1)
    schema_fingerprint: str = Field(..., min_length=64, max_length=64)

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
    sort: str | None = None
    top_n: int | None = Field(default=None, ge=1)

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
    schema_requirements: tuple[ReportSchemaRequirement, ...]
    query_requirements: tuple[ReportQueryRequirement, ...]
    metadata: ReportMetadataContract = ReportMetadataContract()

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_contract(self) -> "TemplateContract":
        query_keys = [item.key for item in self.query_requirements]
        if len(query_keys) != len(set(query_keys)):
            raise ValueError("report_contract_duplicate_query_key")
        schema_refs = {
            (item.object_type, item.canonical_name)
            for item in self.schema_requirements
        }
        if len(schema_refs) != len(self.schema_requirements):
            raise ValueError("report_contract_duplicate_schema_requirement")
        for query in self.query_requirements:
            if any(
                (ReportSchemaObjectType.MEASURE, name) not in schema_refs
                for name in query.measures
            ):
                raise ValueError("report_contract_query_measure_not_required")
            if any(
                (ReportSchemaObjectType.FIELD, name) not in schema_refs
                for name in query.dimensions
            ):
                raise ValueError("report_contract_query_dimension_not_required")
        return self


class ReportContractValidation(BaseModel):
    status: ReportAvailabilityStatus
    template_key: str
    runtime_schema_fingerprint: str | None = None
    errors: tuple[str, ...] = ()
    contract: TemplateContract | None = None

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


SALES_REPORT_CONTRACT = TemplateContract(
    template_key="sales_report",
    contract_version="1.0",
    binding=TemplateSchemaBinding(
        semantic_model_key="local_desktop_model",
        schema_fingerprint=M3_SALES_SCHEMA_FINGERPRINT,
    ),
    schema_requirements=(
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="OrderID",
            accepted_data_types=("Int64",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="OrderDate",
            accepted_data_types=("Int64",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="Category",
            accepted_data_types=("String",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="Product",
            accepted_data_types=("String",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="Quantity",
            accepted_data_types=("Int64",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="UnitPrice",
            accepted_data_types=("Double",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.FIELD,
            table_name="Sales",
            canonical_name="SalesAmount",
            accepted_data_types=("Double",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.MEASURE,
            table_name="Sales",
            canonical_name="Total Sales",
            accepted_data_types=("Double",),
        ),
        ReportSchemaRequirement(
            object_type=ReportSchemaObjectType.MEASURE,
            table_name="Sales",
            canonical_name="Total Quantity",
            accepted_data_types=("Int64",),
        ),
    ),
    query_requirements=(
        ReportQueryRequirement(
            key="total_sales",
            shape=ReportQueryShape.SCALAR,
            measures=("Total Sales",),
        ),
        ReportQueryRequirement(
            key="total_quantity",
            shape=ReportQueryShape.SCALAR,
            measures=("Total Quantity",),
        ),
        ReportQueryRequirement(
            key="sales_by_category",
            shape=ReportQueryShape.GROUPED,
            measures=("Total Sales",),
            dimensions=("Category",),
        ),
        ReportQueryRequirement(
            key="top_products",
            shape=ReportQueryShape.ORDERED_TOP_N,
            measures=("Total Sales",),
            dimensions=("Product",),
            sort="desc",
            top_n=5,
        ),
    ),
)


REPORT_TEMPLATE_CONTRACTS: Mapping[str, TemplateContract] = MappingProxyType({
    SALES_REPORT_CONTRACT.template_key: SALES_REPORT_CONTRACT,
})


class ReportContractValidator:
    """Bind registry-owned templates to one exact runtime schema."""

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

        schema_errors = self._validate_schema_requirements(contract, schema)
        if schema_errors:
            return ReportContractValidation(
                status=ReportAvailabilityStatus.SCHEMA_INCOMPATIBLE,
                template_key=template_key,
                runtime_schema_fingerprint=runtime_fingerprint,
                errors=tuple(schema_errors),
                contract=contract,
            )
        if runtime_fingerprint != contract.binding.schema_fingerprint:
            return ReportContractValidation(
                status=ReportAvailabilityStatus.SCHEMA_FINGERPRINT_MISMATCH,
                template_key=template_key,
                runtime_schema_fingerprint=runtime_fingerprint,
                errors=("report_contract_schema_fingerprint_mismatch",),
                contract=contract,
            )
        return ReportContractValidation(
            status=ReportAvailabilityStatus.AVAILABLE,
            template_key=template_key,
            runtime_schema_fingerprint=runtime_fingerprint,
            contract=contract,
        )

    @staticmethod
    def _validate_schema_requirements(
        contract: TemplateContract,
        schema: SemanticModelSchema,
    ) -> list[str]:
        visible_tables = {
            table.name: table
            for table in schema.tables
            if not table.is_hidden and not table.is_system_managed
        }
        errors: list[str] = []
        for requirement in contract.schema_requirements:
            table = visible_tables.get(requirement.table_name)
            if table is None:
                errors.append(
                    f"report_contract_table_missing:{requirement.table_name}"
                )
                continue
            objects = (
                table.columns
                if requirement.object_type == ReportSchemaObjectType.FIELD
                else table.measures
            )
            matches = [
                item
                for item in objects
                if item.name == requirement.canonical_name and not item.is_hidden
            ]
            if len(matches) != 1:
                errors.append(
                    "report_contract_object_missing_or_ambiguous:"
                    f"{requirement.object_type.value}:"
                    f"{requirement.table_name}.{requirement.canonical_name}"
                )
                continue
            accepted = {value.casefold() for value in requirement.accepted_data_types}
            if matches[0].data_type.casefold() not in accepted:
                errors.append(
                    "report_contract_data_type_mismatch:"
                    f"{requirement.object_type.value}:"
                    f"{requirement.table_name}.{requirement.canonical_name}"
                )
        return errors


class ReportDataPlanBuilder:
    """Create fixed sub-queries from TemplateContract, never from LLM output."""

    def __init__(
        self,
        validator: ReportContractValidator | None = None,
    ) -> None:
        self._validator = validator or ReportContractValidator()

    def build(
        self,
        template_key: str,
        schema: SemanticModelSchema,
    ) -> ReportDataPlan:
        validation = self._validator.validate(template_key, schema)
        if not validation.available or validation.contract is None:
            raise ReportContractError(validation.status.value, validation.errors)
        contract = validation.contract
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
                ),
            )
            for requirement in contract.query_requirements
        )
        return ReportDataPlan(
            template_key=contract.template_key,
            contract_version=contract.contract_version,
            semantic_model_key=schema.key,
            schema_fingerprint=validation.runtime_schema_fingerprint or "",
            queries=queries,
            metadata=contract.metadata,
        )
