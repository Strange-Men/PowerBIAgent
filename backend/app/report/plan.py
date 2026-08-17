"""Deterministic ReportPlan: requested sections → resolved sections → queries.

The planner is the final authority between the weak signals (NL matcher +
bounded LLM draft) and the sealed M2 execution chain.  It consumes only:

  - registry-owned requested section IDs (already filtered by capability),
  - the runtime schema,
  - the fixed TemplateContract capability catalog.

It never reads LLM query drafts, QueryResults, expected values or free query
descriptions, and it never invents sections for schema extra fields.  A
requested-but-unavailable section is dropped (fail closed); a request with
zero resolvable sections is an error — never an empty/mock report.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.app.report.capability import (
    ANALYSIS_SECTION_ORDER,
    KPI_SECTION_ORDER,
    SectionInfo,
    SectionKey,
    apply_fact_evidence,
    compute_section_capabilities,
    resolve_requested_sections,
)
from backend.app.report.contracts import (
    REPORT_TEMPLATE_CONTRACTS,
    ReportContractError,
    ReportContractValidator,
    ReportDataPlan,
    ReportDataPlanBuilder,
    TemplateContract,
)
from backend.app.report.intent import ReportIntentSignal
from backend.app.schemas.data_contracts import SemanticModelSchema


class ReportPlanError(ValueError):
    def __init__(self, code: str, errors: tuple[str, ...] = ()):
        super().__init__(code)
        self.code = code
        self.errors = errors


class ReportPlan(BaseModel):
    """Canonical adaptive report plan produced by ordinary code."""

    template_key: str
    contract_version: str
    requested_ids: tuple[str, ...]
    resolved_sections: tuple[SectionKey, ...]
    unavailable_sections: tuple[SectionKey, ...]
    requirement_keys: tuple[str, ...]
    data_plan: ReportDataPlan
    schema_fingerprint: str
    signal: ReportIntentSignal
    section_capabilities: dict[SectionKey, SectionInfo]

    model_config = ConfigDict(frozen=True)


class ReportPlanner:
    """Resolve requested analysis goals against the runtime schema."""

    def __init__(
        self,
        validator: ReportContractValidator | None = None,
        data_plan_builder: ReportDataPlanBuilder | None = None,
    ) -> None:
        self._validator = validator or ReportContractValidator()
        self._builder = data_plan_builder or ReportDataPlanBuilder(
            validator=self._validator
        )

    def plan(
        self,
        template_key: str,
        schema: SemanticModelSchema,
        requested_ids: tuple[str, ...],
        signal: ReportIntentSignal,
    ) -> ReportPlan:
        validation = self._validator.validate(template_key, schema)
        if not validation.available or validation.contract is None:
            raise ReportPlanError(validation.status.value, validation.errors)
        contract: TemplateContract = validation.contract

        capabilities = compute_section_capabilities(
            template_key, contract, schema
        )
        resolved, unavailable = resolve_requested_sections(
            requested_ids, capabilities
        )
        if not resolved:
            raise ReportPlanError(
                "sales_report_no_resolved_sections",
                tuple(item.value for item in unavailable),
            )

        # Requirement order follows the fixed visual hierarchy: KPI row,
        # analysis sections in layout order.  One requirement runs at most
        # once regardless of how many sections need it.
        requirement_keys: list[str] = []
        for section in (*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER):
            if section not in resolved:
                continue
            from backend.app.report.capability import SECTION_REQUIREMENTS
            for key in SECTION_REQUIREMENTS[section]:
                if key not in requirement_keys:
                    requirement_keys.append(key)
        requirement_tuple = tuple(requirement_keys)

        try:
            data_plan = self._builder.build(
                template_key,
                schema,
                requirement_keys=requirement_tuple,
            )
        except ReportContractError as exc:
            raise ReportPlanError(exc.code, exc.errors) from exc

        return ReportPlan(
            template_key=contract.template_key,
            contract_version=contract.contract_version,
            requested_ids=requested_ids,
            resolved_sections=resolved,
            unavailable_sections=unavailable,
            requirement_keys=requirement_tuple,
            data_plan=data_plan,
            schema_fingerprint=validation.runtime_schema_fingerprint or "",
            signal=signal,
            section_capabilities=capabilities,
        )

    def apply_fact_evidence(
        self,
        report_plan: ReportPlan,
        schema: SemanticModelSchema,
        fact_row_counts: dict[str, int],
    ) -> tuple[tuple[SectionKey, ...], tuple[SectionKey, ...]]:
        """Re-gate sections after verified fact evidence exists.

        A section whose requirement returned zero verified rows is dropped
        here — never rendered empty.  Returns (still-resolved, dropped).
        """
        validation = self._validator.validate(
            report_plan.template_key, schema
        )
        resolved_after = apply_fact_evidence(
            report_plan.section_capabilities,
            template_key=report_plan.template_key,
            contract=validation.contract,
            schema=schema,
            fact_row_counts=fact_row_counts,
        )
        still, dropped = resolve_requested_sections(
            tuple(item.value for item in report_plan.resolved_sections),
            resolved_after,
        )
        return still, dropped
