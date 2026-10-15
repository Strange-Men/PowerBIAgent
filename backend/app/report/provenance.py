"""Server-owned provider compatibility for report snapshot provenance only."""
from backend.app.powerbi.fabric_iq import FabricIQPowerBIAdapter
from backend.app.schemas.report_context import ReportDataSourceKind


def report_source_kind(adapter, semantic_model_key: str) -> ReportDataSourceKind:
    if isinstance(adapter, FabricIQPowerBIAdapter):
        # Revalidate the exact principal/session-bound model, not a provider
        # name, model-key prefix, real flag, or client-supplied source field.
        adapter.bound_resource_identity(semantic_model_key)
        return ReportDataSourceKind.FABRIC_IQ
    # Preserve the existing formal report path's Desktop provenance.
    return ReportDataSourceKind.LOCAL_MCP
