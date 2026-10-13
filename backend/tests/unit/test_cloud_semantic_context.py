"""User-approved six-field compatibility; unknown never becomes false."""
import pytest

from backend.app.auth.models import AuthFailure
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder, RuntimeObject, RuntimeTable
from backend.tests.unit.test_fabric_iq_adapter import harness, WORKSPACE, MODEL  # noqa: F401


@pytest.mark.asyncio
async def test_native_cloud_schema_preserves_unknown_flags_and_provenance(harness):
    _, _, _, adapter = harness
    ref = await adapter.bind_catalog_model(WORKSPACE, MODEL)
    schema = await adapter.get_semantic_model_schema(ref.server_model_key)
    context = ModelSemanticContextBuilder().build(schema)
    assert context.metadata_source == "fabric_iq"
    assert context.tables and context.columns and context.measures
    assert all(table.is_hidden is None and table.is_system_managed is None for table in context.tables)
    assert all(item.is_hidden is None and item.is_system_managed is None and item.is_key is None for item in context.columns)
    assert all(item.is_hidden is None and item.is_system_managed is None for item in context.measures)
    assert all(item.evidence == ("fabric_iq",) for item in (*context.columns, *context.measures))
    assert context.relationships == ()
    assert all(item.expression is None for item in context.measures)


@pytest.mark.asyncio
@pytest.mark.parametrize("flag",["is_hidden","is_system_managed"])
async def test_explicit_hidden_system_objects_still_excluded(harness,flag):
    _, _, _, adapter = harness
    ref = await adapter.bind_catalog_model(WORKSPACE, MODEL)
    schema = await adapter.get_semantic_model_schema(ref.server_model_key)
    table = schema.tables[0]
    hidden_table = schema.model_copy(update={"tables":[table.model_copy(update={flag:True})]})
    context = ModelSemanticContextBuilder().build(hidden_table)
    assert context.tables == context.columns == context.measures == ()


@pytest.mark.asyncio
async def test_context_compatibility_does_not_bypass_native_permission_failure(harness):
    auth, session, transport, adapter = harness
    ref = await adapter.bind_catalog_model(WORKSPACE, MODEL)
    transport.schema = {"Error":{"HttpStatusCode":403}}
    with pytest.raises(PowerBIAdapterError, match="^RESOURCE_NOT_ACCESSIBLE$"):
        await adapter.get_semantic_model_schema(ref.server_model_key)
    assert adapter.binding_count == 0
    with pytest.raises(AuthFailure): auth.require_session(session.session_id)


def test_legacy_runtime_defaults_remain_false():
    assert RuntimeTable(name="Synthetic").is_hidden is False
    item = RuntimeObject(object_id="field:Synthetic:Id",canonical_name="Id",object_type="field",
                         table_name="Synthetic",data_type="Int64")
    assert item.is_hidden is False and item.is_system_managed is False and item.is_key is False
