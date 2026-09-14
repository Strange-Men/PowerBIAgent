"""Public report API with lazy imports.

The registry is an input to ``query_plan.template_catalog`` and report
contracts consume that catalog.  Eagerly importing every report module from
the package initializer therefore made isolated submodule imports depend on
test collection order.  PEP 562 lazy attributes preserve the public exports
without executing unrelated report modules during package initialization.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "KpiValue": "backend.app.report.assembly",
    "SalesReportAssemblyError": "backend.app.report.assembly",
    "SalesReportData": "backend.app.report.assembly",
    "SalesReportDataAssembler": "backend.app.report.assembly",
    "SalesReportSpecBuilder": "backend.app.report.assembly",
    "SectionProjection": "backend.app.report.assembly",
    "TrendPoint": "backend.app.report.assembly",
    "REPORT_TEMPLATE_CONTRACTS": "backend.app.report.contracts",
    "RequirementAvailability": "backend.app.report.contracts",
    "SALES_REPORT_CONTRACT": "backend.app.report.contracts",
    "ReportAvailabilityStatus": "backend.app.report.contracts",
    "ReportContractError": "backend.app.report.contracts",
    "ReportContractValidation": "backend.app.report.contracts",
    "ReportContractValidator": "backend.app.report.contracts",
    "ReportDataPlan": "backend.app.report.contracts",
    "ReportDataPlanBuilder": "backend.app.report.contracts",
    "ReportDataQuery": "backend.app.report.contracts",
    "ReportMetadataContract": "backend.app.report.contracts",
    "ReportQueryRequirement": "backend.app.report.contracts",
    "ReportQueryShape": "backend.app.report.contracts",
    "ReportSchemaObjectType": "backend.app.report.contracts",
    "ReportSchemaRequirement": "backend.app.report.contracts",
    "TemplateContract": "backend.app.report.contracts",
    "TemplateSchemaBinding": "backend.app.report.contracts",
    "SalesReportRenderer": "backend.app.report.fixed",
    "ExecutiveSalesReportRenderer": "backend.app.report.executive",
    "DEFAULT_REPORT_TEMPLATE_REGISTRY": "backend.app.report.registry",
    "ReportRendererDispatcher": "backend.app.report.registry",
    "ReportRendererRegistry": "backend.app.report.registry",
    "ReportTemplateAvailability": "backend.app.report.registry",
    "ReportTemplateDescriptor": "backend.app.report.registry",
    "ReportTemplateRegistry": "backend.app.report.registry",
    "ReportTemplateUnavailableError": "backend.app.report.registry",
    "InMemoryReportRepository": "backend.app.report.resources",
    "LocalReportRepository": "backend.app.report.resources",
    "ReportArtifact": "backend.app.report.resources",
    "ReportNotFoundError": "backend.app.report.resources",
    "ReportRepository": "backend.app.report.resources",
    "ReportResourceError": "backend.app.report.resources",
    "ReportStorageError": "backend.app.report.resources",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
