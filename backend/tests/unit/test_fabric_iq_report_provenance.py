"""Provider provenance compatibility; no query/fact semantics are replaced."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.api.cloud_routes import CloudChatRequest
from backend.app.facts import VerifiedFactSetBuilder
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.app.report.presentation import ProfessionalReportPresenter
from backend.app.report.reading_context import ReportDataSnapshotBuilder
from backend.app.schemas.data_contracts import CanonicalQueryPlan, DAXRequest
from backend.app.schemas.report_context import ReportDataSourceKind
from backend.tests.unit.test_complex_report_contract import NOW, _reading_context
from backend.tests.unit.test_executive_report_renderer import _report
from backend.tests.unit.test_fabric_iq_adapter import harness  # noqa: F401


def source_kind(adapter, key):
    from backend.app.report.provenance import report_source_kind
    return report_source_kind(adapter, key)


@pytest.mark.asyncio
async def test_bound_native_iq_snapshot_preserves_result_and_fact_identity(harness):
    _, _, _, adapter = harness
    ref = await adapter.resolve_bootstrap('fixture')
    key = ref.server_model_key
    result = await adapter.execute_dax(DAXRequest(semantic_model_key=key,
        dax='EVALUATE ROW("Count",[Count])'))
    plan = CanonicalQueryPlan(normalized_question='synthetic count',
        semantic_model_key=key, measures=['Count'])
    facts = VerifiedFactSetBuilder().build(plan, result)
    before = facts.model_dump_json()
    snapshot = ReportDataSnapshotBuilder().build(semantic_model_identity=key,
        schema_fingerprint=compute_schema_fingerprint(adapter._schemas[key]),
        query_results={'count': result}, verified_fact_sets={'count': facts},
        source_kind=source_kind(adapter, key), queried_at=NOW, snapshot_at=NOW)
    assert snapshot.source_kind.value == 'fabric_iq'
    assert snapshot.source_mode == facts.source_mode == result.source_mode == 'real'
    assert snapshot.semantic_model_identity == facts.semantic_model_key == key
    assert snapshot.query_result_ids == (result.result_id,)
    assert snapshot.verified_fact_set_ids == (facts.fact_set_id,)
    assert facts.model_dump_json() == before
    context = _reading_context(snapshot=snapshot)
    assert context.data_source.kind == snapshot.source_kind
    assert context.data_source.display_name == 'Fabric IQ · 实时查询'


@pytest.mark.asyncio
async def test_iq_identity_requires_current_bound_model(harness):
    _, _, _, adapter = harness
    with pytest.raises(PowerBIAdapterError):
        source_kind(adapter, 'fabric_iq:unbound')
    ref = await adapter.resolve_bootstrap('fixture')
    await adapter.aclose()
    with pytest.raises(PowerBIAdapterError):
        source_kind(adapter, ref.server_model_key)


@pytest.mark.parametrize('claimed_name', ['fabric_iq', 'local_mcp', 'remote_mcp'])
def test_real_flag_provider_string_or_opaque_key_cannot_claim_iq(claimed_name):
    fake = SimpleNamespace(provider_name=claimed_name, is_mock=False,
        source_kind='fabric_iq')
    assert source_kind(fake, 'fabric_iq:claimed') is ReportDataSourceKind.LOCAL_MCP


@pytest.mark.parametrize(('kind', 'label'), [
    ('fabric_iq', 'Fabric IQ'), ('local_mcp', 'Power BI Desktop'),
    ('remote_mcp', '远程 Power BI'), ('test_fixture', '测试数据'),
])
@pytest.mark.asyncio
async def test_professional_source_mapping_and_canonical_identity(kind, label):
    report = _report()
    before = report.model_dump(mode='json')
    snapshot = report.data_snapshot.model_copy(update={
        'source_kind': ReportDataSourceKind(kind), 'source_display_name': None,
        'semantic_model_display_name': 'Synthetic Sales'})
    context = report.reading_context.model_copy(update={
        'data_source': report.reading_context.data_source.model_copy(update={
            'kind': snapshot.source_kind, 'display_name': label})})
    report = report.model_copy(update={'data_snapshot': snapshot, 'reading_context': context})
    projection = ProfessionalReportPresenter().project(report)
    html = await ExecutiveSalesReportRenderer().render(report)
    assert label + ' · 实时查询' in projection.source_display_name
    assert label in html and kind in html
    assert projection.model_display_name == 'Synthetic Sales'
    assert projection.canonical_source_mode == report.source_mode == snapshot.source_mode
    assert snapshot.verified_fact_set_ids == tuple(before['verified_fact_set_ids'])
    assert snapshot.semantic_model_identity == report.semantic_model_key
    assert report.model_dump(mode='json')['kpis'] == before['kpis']
    if kind == 'fabric_iq':
        assert 'local_mcp' not in html and 'Power BI Desktop' not in html


def test_fabric_opaque_identity_is_not_a_model_display_name():
    report = _report()
    snapshot = report.data_snapshot.model_copy(update={
        'source_kind': ReportDataSourceKind('fabric_iq'),
        'semantic_model_display_name': 'fabric_iq:other-opaque',
        'semantic_model_identity': 'fabric_iq:opaque'})
    projection = ProfessionalReportPresenter().project(report.model_copy(update={'data_snapshot':snapshot}))
    assert 'fabric_iq:' not in projection.main_text


@pytest.mark.parametrize('kind', ['fabric_iq', 'local_mcp', 'test_fixture'])
def test_client_cannot_supply_report_source_kind(kind):
    with pytest.raises(ValidationError):
        CloudChatRequest(expected_generation=0, message='synthetic', request_id='probe',
            source_kind=kind)
