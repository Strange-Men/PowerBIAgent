"""Deterministic adaptive report, renderer, resource, and anti-bypass tests."""

from __future__ import annotations

import hashlib
import inspect
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import backend.app.report.assembly as assembly_module
import backend.app.report.fixed as renderer_module
from backend.app.api.routes import router
from backend.app.application.deepseek_turn_service import DeepSeekTurnService
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.facts import FactType, VerifiedFactSet, VerifiedFactSetBuilder
from backend.app.harness.models import HarnessConfig
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.memory.models import MemoryStatus, RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.report.assembly import (
    SalesReportAssemblyError,
    SalesReportDataAssembler,
    SalesReportSpecBuilder,
)
from backend.app.report.contracts import ReportDataPlanBuilder
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.intent import ReportIntentDraft
from backend.app.report.resources import (
    InMemoryReportRepository,
    LocalReportRepository,
    ReportArtifact,
    ReportDeleteResult,
    ReportNotFoundError,
    ReportRenameResult,
    ReportRepository,
    ReportStorageError,
)
from backend.app.schemas.data_contracts import (
    ChartSpec,
    ColumnSchema,
    DAXRequest,
    MeasureSchema,
    PowerBIError,
    QueryPlan,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
    TableSchema,
)

SIMPLE_KEYS = (
    "total_sales",
    "total_quantity",
    "sales_by_category",
    "top_products",
)


def _schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="local_desktop_model",
        key="local_desktop_model",
        tables=[TableSchema(
            name="Sales",
            columns=[
                ColumnSchema(name="OrderID", data_type="Int64"),
                ColumnSchema(name="OrderDate", data_type="Int64"),
                ColumnSchema(name="Category", data_type="String"),
                ColumnSchema(name="Product", data_type="String"),
                ColumnSchema(name="Quantity", data_type="Int64"),
                ColumnSchema(name="UnitPrice", data_type="Double"),
                ColumnSchema(name="SalesAmount", data_type="Double"),
            ],
            measures=[
                MeasureSchema(
                    name="Total Sales",
                    expression="SUM(Sales[SalesAmount])",
                    data_type="Double",
                ),
                MeasureSchema(
                    name="Total Quantity",
                    expression="SUM(Sales[Quantity])",
                    data_type="Int64",
                ),
            ],
        )],
    )


def _plan():
    return ReportDataPlanBuilder().build(
        "sales_report", _schema(), requirement_keys=SIMPLE_KEYS
    )


def _results(
    *,
    source_mode: str = "real",
    category: str = "办公用品",
) -> dict[str, QueryResult]:
    common = {
        "semantic_model_key": "local_desktop_model",
        "source_mode": source_mode,
    }
    return {
        "total_sales": QueryResult(
            result_id="qr_total_sales",
            columns=["[Total Sales]"],
            rows=[[1200.5]],
            row_count=1,
            **common,
        ),
        "total_quantity": QueryResult(
            result_id="qr_total_quantity",
            columns=["[Total Quantity]"],
            rows=[[9]],
            row_count=1,
            **common,
        ),
        "sales_by_category": QueryResult(
            result_id="qr_sales_by_category",
            columns=["Sales[Category]", "[Total Sales]"],
            rows=[[category, 700.25], ["家具", 500.25]],
            row_count=2,
            **common,
        ),
        "top_products": QueryResult(
            result_id="qr_top_products",
            columns=["Sales[Product]", "[Total Sales]"],
            rows=[["产品 A", 800.0], ["产品 B", 400.5]],
            row_count=2,
            **common,
        ),
    }


def _facts(results: dict[str, QueryResult]) -> dict[str, VerifiedFactSet]:
    plan = _plan()
    return {
        query.requirement_key: VerifiedFactSetBuilder().build(
            query.query_plan,
            results[query.requirement_key],
        )
        for query in plan.queries
    }


def _assembled(
    *,
    results: dict[str, QueryResult] | None = None,
    facts: dict[str, VerifiedFactSet] | None = None,
):
    selected_results = results or _results()
    selected_facts = facts or _facts(selected_results)
    return SalesReportDataAssembler(
        clock=lambda: datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc)
    ).build(
        _plan(),
        selected_results,
        selected_facts,
    )


def test_sales_report_data_and_spec_are_exact_fixed_projections():
    data = _assembled()
    assert [(item.measure, item.value) for item in data.kpis] == [
        ("Total Sales", 1200.5),
        ("Total Quantity", 9),
    ]
    assert len(data.sections) == 2
    category = next(item for item in data.sections if item.kind == "grouped")
    assert [item.label for item in category.values] == ["办公用品", "家具"]
    top = next(item for item in data.sections if item.kind == "top_n")
    assert [item.result_position for item in top.values] == [1, 2]
    assert [item.label for item in top.values] == ["产品 A", "产品 B"]
    assert data.source_mode == "real"
    assert len(data.query_result_ids) == 4
    assert len(data.verified_fact_set_ids) == 4

    report = SalesReportSpecBuilder().build(data)
    assert report.title == "销售分析报表"
    assert [(item.name, item.field) for item in report.kpis] == [
        ("总销售额", "Total Sales"),
        ("总销量", "Total Quantity"),
    ]
    roles = {item.business_role for item in report.charts}
    assert roles == {"category_contribution", "top_products"}
    assert report.tables == []
    assert report.insights == []


@pytest.mark.parametrize("missing_key", SIMPLE_KEYS)
def test_missing_required_query_fails_closed(missing_key):
    results = _results()
    facts = _facts(results)
    results.pop(missing_key)
    with pytest.raises(SalesReportAssemblyError) as error:
        _assembled(results=results, facts=facts)
    assert error.value.code == "sales_report_query_result_set_incomplete"


def test_missing_or_wrong_fact_set_binding_fails_closed():
    results = _results()
    facts = _facts(results)
    facts.pop("total_quantity")
    with pytest.raises(SalesReportAssemblyError) as missing:
        _assembled(results=results, facts=facts)
    assert missing.value.code == "sales_report_fact_set_incomplete"

    facts = _facts(results)
    facts["total_quantity"] = facts["total_sales"]
    with pytest.raises(SalesReportAssemblyError) as wrong:
        _assembled(results=results, facts=facts)
    assert wrong.value.code == "sales_report_fact_result_binding_mismatch"


def test_mixed_mock_real_sources_fail_closed():
    results = _results()
    results["top_products"] = results["top_products"].model_copy(
        update={"source_mode": "mock"}
    )
    facts = _facts(results)
    with pytest.raises(SalesReportAssemblyError) as error:
        _assembled(results=results, facts=facts)
    assert error.value.code == "sales_report_source_mode_mixed_or_invalid"


def test_empty_required_query_fails_closed():
    results = _results()
    results["sales_by_category"] = results["sales_by_category"].model_copy(
        update={"rows": [], "row_count": 0}
    )
    facts = _facts(results)
    with pytest.raises(SalesReportAssemblyError) as error:
        _assembled(results=results, facts=facts)
    assert error.value.code == "sales_report_required_query_empty"


def test_fabricated_kpi_and_category_fact_are_rejected():
    results = _results()
    facts = _facts(results)
    scalar = facts["total_sales"].facts[0].model_copy(update={"value": 999999})
    facts["total_sales"] = facts["total_sales"].model_copy(
        update={"facts": [scalar, *facts["total_sales"].facts[1:]]}
    )
    with pytest.raises(SalesReportAssemblyError) as kpi_error:
        _assembled(results=results, facts=facts)
    assert kpi_error.value.code == "sales_report_fact_set_tampered"

    facts = _facts(results)
    grouped_index = next(
        index
        for index, item in enumerate(facts["sales_by_category"].facts)
        if item.fact_type == FactType.GROUPED_METRIC
    )
    tampered = list(facts["sales_by_category"].facts)
    tampered[grouped_index] = tampered[grouped_index].model_copy(
        update={"dimensions": {"Category": "伪造类别"}}
    )
    facts["sales_by_category"] = facts["sales_by_category"].model_copy(
        update={"facts": tampered}
    )
    with pytest.raises(SalesReportAssemblyError) as row_error:
        _assembled(results=results, facts=facts)
    assert row_error.value.code == "sales_report_fact_set_tampered"


def test_forged_or_reordered_top_product_is_rejected():
    results = _results()
    facts = _facts(results)
    ranking_index = next(
        index
        for index, item in enumerate(facts["top_products"].facts)
        if item.fact_type == FactType.RANKING
    )
    tampered = list(facts["top_products"].facts)
    tampered[ranking_index] = tampered[ranking_index].model_copy(
        update={"values": list(reversed(tampered[ranking_index].values))}
    )
    facts["top_products"] = facts["top_products"].model_copy(
        update={"facts": tampered}
    )
    with pytest.raises(SalesReportAssemblyError) as error:
        _assembled(results=results, facts=facts)
    assert error.value.code == "sales_report_fact_set_tampered"


@pytest.mark.asyncio
async def test_fixed_renderer_escapes_injection_and_has_no_active_content():
    results = _results(category='<script>alert("x")</script>')
    report = SalesReportSpecBuilder().build(
        _assembled(results=results, facts=_facts(results))
    )
    html = await SalesReportRenderer().render(report)
    assert "销售分析报表" in html
    assert "品类销售贡献" in html
    assert "Top 5 产品销售额" in html
    assert 'data-chart="category_contribution"' in html
    assert 'data-chart="top_products"' in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "<script" not in html.casefold()
    assert "javascript:" not in html.casefold()
    assert "http://" not in html.casefold()
    assert "https://" not in html.casefold()


@pytest.mark.asyncio
async def test_fixed_renderer_geometry_is_deterministic_and_data_bound():
    report = SalesReportSpecBuilder().build(_assembled())
    html = await SalesReportRenderer().render(report)

    # Category (2 slices) renders as donut: percents derived from verified rows.
    assert 'data-slice-percent="58.33"' in html
    assert 'data-source-value="700.25"' in html
    assert 'data-slice-percent="41.67"' in html
    assert 'data-source-value="500.25"' in html
    # Top products render as horizontal bars with verified geometry.
    assert 'data-source-value="800.0" data-bar-percent="100.00"' in html
    assert 'data-source-value="400.5" data-bar-percent="50.06"' in html
    assert 'style="width: 50.06%"' in html
    assert "结果序号 1" in html
    assert "结果序号 2" in html


@pytest.mark.asyncio
async def test_no_duplicate_table_visual_regression():
    """One business question per visual — no duplicate table below charts."""
    html = await SalesReportRenderer().render(
        SalesReportSpecBuilder().build(_assembled())
    )
    assert 'data-chart="category_contribution"' in html
    assert 'data-chart="top_products"' in html
    assert "<table" not in html
    # KPI still present
    assert "总销售额" in html
    assert "总销量" in html


@pytest.mark.asyncio
async def test_renderer_rejects_incomplete_provenance():
    report = SalesReportSpecBuilder().build(_assembled())
    stripped = report.model_copy(update={"source_mode": ""})
    with pytest.raises(ValueError, match="sales_report_provenance_invalid"):
        await SalesReportRenderer().render(stripped)

    short_ids = report.model_copy(update={"query_result_ids": []})
    with pytest.raises(ValueError, match="sales_report_provenance_invalid"):
        await SalesReportRenderer().render(short_ids)


@pytest.mark.asyncio
async def test_renderer_rejects_unregistered_or_duplicate_sections():
    report = SalesReportSpecBuilder().build(_assembled())
    forged = report.model_copy(update={
        "charts": [chart.model_copy(update={"business_role": "forged_role"})
                   for chart in report.charts],
    })
    with pytest.raises(ValueError, match="sales_report_chart_role_unregistered"):
        await SalesReportRenderer().render(forged)

    duplicated = report.model_copy(update={
        "charts": [
            report.charts[0],
            report.charts[0].model_copy(),
        ],
    })
    with pytest.raises(ValueError, match="sales_report_chart_duplicate_role"):
        await SalesReportRenderer().render(duplicated)

    kpi_as_chart = report.model_copy(update={
        "charts": [
            report.charts[0].model_copy(update={"business_role": "sales_kpi"}),
        ],
    })
    with pytest.raises(ValueError, match="sales_report_chart_role_unregistered"):
        await SalesReportRenderer().render(kpi_as_chart)


@pytest.mark.asyncio
async def test_fixed_renderer_rejects_forged_chart_input():
    report = SalesReportSpecBuilder().build(_assembled()).model_copy(update={
        "charts": [ChartSpec(
            type="bar",
            title="伪造图表",
            x_field="Category",
            y_field="Forged Sales",
            visual_type="line",
            business_role="time_trend",
            series=[],
        )],
    })
    with pytest.raises(ValueError, match="sales_report_chart_series_empty"):
        await SalesReportRenderer().render(report)

    forged_role = SalesReportSpecBuilder().build(_assembled()).model_copy(update={
        "charts": [ChartSpec(
            type="bar",
            title="伪造图表",
            x_field="Category",
            y_field="Total Sales",
            visual_type="line",
            business_role="sales_kpi",
            series=[{"label": "x", "value": 1, "position": 1}],
        )],
    })
    with pytest.raises(ValueError, match="sales_report_chart_role_unregistered"):
        await SalesReportRenderer().render(forged_role)

    forged_value = SalesReportSpecBuilder().build(_assembled()).model_copy(update={
        "charts": [ChartSpec(
            type="bar",
            title="伪造图表",
            x_field="Category",
            y_field="Total Sales",
            visual_type="column",
            business_role="region_comparison",
            series=[{"label": "华东", "value": "not-a-number", "position": 1}],
        )],
    })
    with pytest.raises(ValueError, match="sales_report_number_invalid"):
        await SalesReportRenderer().render(forged_value)


@pytest.mark.asyncio
async def test_fixed_renderer_rejects_non_sales_report():
    with pytest.raises(ValueError, match="sales_report_renderer_template_rejected"):
        await SalesReportRenderer().render(
            ReportSpec(title="旧模板", template_key="sales_weekly")
        )


def test_assembler_and_renderer_have_zero_llm_or_powerbi_authority():
    assembly_source = inspect.getsource(assembly_module)
    renderer_source = inspect.getsource(renderer_module)
    for source in (assembly_source, renderer_source):
        assert "LLMProvider" not in source
        assert "PowerBIAdapter" not in source
        assert "ToolGateway" not in source
    assert "QueryResult(" not in assembly_source
    assert "expected_total" not in assembly_source
    production_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path("backend/app/report")).glob("*.py")
    )
    for forbidden_oracle in ("500" + "821", "35" + "8", "694" + "3997"):
        assert forbidden_oracle not in production_source


@pytest.mark.asyncio
async def test_local_repository_hash_atomic_content_and_resource_api(tmp_path):
    repository = LocalReportRepository(tmp_path / "local_state" / "reports")
    report = SalesReportSpecBuilder().build(_assembled())
    html = await SalesReportRenderer().render(report)
    artifact = await repository.store(report, html)
    stored_artifact, stored_html = await repository.read_html(artifact.report_id)
    content = stored_html.encode("utf-8")
    assert stored_artifact == artifact
    assert hashlib.sha256(content).hexdigest() == artifact.content_hash
    assert (repository.root / f"{artifact.report_id}.html").read_bytes() == content
    assert not list(repository.root.glob("*.tmp"))

    app = FastAPI()
    app.state.report_repository = repository
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        view = await client.get(artifact.view_reference)
        download = await client.get(artifact.download_reference)
        unknown = await client.get("/api/reports/rpt_00000000000000000000000000000000")
        traversal = await client.get("/api/reports/not..valid")
    assert view.status_code == 200
    assert view.headers["content-type"].startswith("text/html")
    assert view.content == content
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-disposition"] == (
        f'attachment; filename="{artifact.report_id}.html"'
    )
    assert unknown.status_code == 404
    assert traversal.status_code == 404
    with pytest.raises(ReportNotFoundError):
        await repository.read_html("../outside")


@pytest.mark.asyncio
async def test_repository_rejects_external_static_resource_markup():
    repository = InMemoryReportRepository()
    report = SalesReportSpecBuilder().build(_assembled())
    html = await SalesReportRenderer().render(report)
    unsafe = html.replace(
        "</head>",
        '<link rel="stylesheet" href="//cdn.example/report.css"></head>',
    )
    with pytest.raises(ReportStorageError, match="report_html_unsafe_or_incomplete"):
        await repository.store(report, unsafe)


class _FailingReportRepository(ReportRepository):
    async def store(self, report: ReportSpec, html: str) -> ReportArtifact:
        raise ReportStorageError("forced_store_failure")

    async def get(self, report_id: str) -> ReportArtifact:
        raise ReportNotFoundError("report_not_found")

    async def read_html(self, report_id: str) -> tuple[ReportArtifact, str]:
        raise ReportNotFoundError("report_not_found")

    async def delete(self, report_id: str) -> ReportDeleteResult:
        raise ReportStorageError("forced_delete_failure")

    async def rename(
        self, report_id: str, display_title: str
    ) -> ReportRenameResult:
        raise ReportStorageError("forced_rename_failure")


class _CountingReportRepository(InMemoryReportRepository):
    def __init__(self) -> None:
        super().__init__()
        self.store_count = 0

    async def store(
        self,
        report: ReportSpec,
        html: str,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> ReportArtifact:
        self.store_count += 1
        return await super().store(
            report, html,
            conversation_id=conversation_id,
            request_id=request_id,
        )


class _ReportLanguageProvider(LLMProvider):
    """Fake real provider: intent → query plan → bounded report-intent draft."""

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    @property
    def provider_name(self) -> str:
        return "test_language_provider"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(self, request: LLMRequest, output_type: type) -> LLMResponse:
        self.calls.append(request)
        if output_type is IntentSpec:
            structured = IntentSpec(
                intent=IntentType.REPORT_GENERATION,
                confidence=1.0,
                normalized_question="生成销售分析报表",
                requested_template="sales_report",
            )
        elif output_type is QueryPlan:
            structured = QueryPlan(
                normalized_question="生成销售分析报表",
                semantic_model_key="local_desktop_model",
                requested_template="sales_report",
            )
        elif output_type is ReportIntentDraft:
            structured = ReportIntentDraft(
                report_section_ids=[
                    "sales_kpi",
                    "quantity_kpi",
                    "time_trend",  # unknown for the simple schema → dropped
                ]
            )
        else:
            raise AssertionError(f"unexpected LLM output type: {output_type}")
        return LLMResponse(content="{}", structured=structured, model="test")


class _RealReportAdapter(PowerBIAdapter):
    def __init__(self) -> None:
        self.execute_count = 0

    @property
    def provider_name(self) -> str:
        return "test_real_powerbi"

    @property
    def is_mock(self) -> bool:
        return False

    async def health_check(self) -> bool:
        return True

    async def get_semantic_model_schema(self, semantic_model_key: str):
        assert semantic_model_key == "local_desktop_model"
        return _schema()

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.execute_count += 1
        if "Total Quantity" in request.dax:
            columns, rows = ["[Total Quantity]"], [[9]]
        elif "[Category]" in request.dax:
            columns, rows = (
                ["Sales[Category]", "[Total Sales]"],
                [["办公用品", 700.25], ["家具", 500.25]],
            )
        elif "[Product]" in request.dax:
            columns, rows = (
                ["Sales[Product]", "[Total Sales]"],
                [["产品 A", 800.0], ["产品 B", 400.5]],
            )
        else:
            columns, rows = ["[Total Sales]"], [[1200.5]]
        return QueryResult(
            result_id=f"qr_service_{self.execute_count}",
            semantic_model_key="local_desktop_model",
            columns=columns,
            rows=rows,
            row_count=len(rows),
            source_mode="real",
            request_id=request.request_id,
        )

    async def normalize_result(self, raw: object) -> QueryResult:
        if not isinstance(raw, QueryResult):
            raise TypeError("QueryResult required")
        return raw

    async def normalize_error(self, raw: object) -> PowerBIError:
        return PowerBIError(type="test", message=str(raw), retryable=False)


@pytest.mark.asyncio
async def test_store_failure_never_commits_memory():
    memory = InMemoryMemoryRepository()
    service = MockTurnService(
        memory_repo=memory,
        report_repository=_FailingReportRepository(),
    )
    result = await service.execute(
        message="生成销售周报",
        conversation_id="conv-store-fail",
        request_id="req-store-fail",
        report_template_key="sales_weekly",
    )
    assert result["terminal_state"] == "response_failed"
    assert result["memory_commit"] is False
    saved = await service.pipeline.get_memory_by_request_id(
        "req-store-fail", RuntimeDataMode.MOCK
    )
    assert saved is not None
    assert saved.state_status == MemoryStatus.FAILED


@pytest.mark.asyncio
async def test_idempotent_report_replay_reuses_one_artifact():
    repository = _CountingReportRepository()
    service = MockTurnService(report_repository=repository)
    request = {
        "message": "生成销售周报",
        "conversation_id": "conv-report-replay",
        "request_id": "req-report-replay",
        "report_template_key": "sales_weekly",
    }
    first = await service.execute(**request)
    replay = await service.execute(**request)
    assert first["report"]["report_id"] == replay["report"]["report_id"]
    assert replay["idempotent_replay"] is True
    assert replay["tool_sequence"] == []
    assert repository.store_count == 1


@pytest.mark.asyncio
async def test_production_turn_uses_capability_resolved_queries_and_replays():
    adapter = _RealReportAdapter()
    provider = _ReportLanguageProvider()
    repository = _CountingReportRepository()
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        powerbi_local_semantic_model_key="local_desktop_model",
        max_tool_calls=16,
    )
    service = DeepSeekTurnService(
        memory_repo=InMemoryMemoryRepository(),
        llm_provider=provider,
        powerbi_adapter=adapter,
        report_renderer=SalesReportRenderer(),
        report_repository=repository,
        settings=settings,
        config=HarnessConfig.from_settings(settings),
    )
    request = {
        "message": "生成销售分析报表",
        "conversation_id": "conv-sales-report",
        "request_id": "req-sales-report",
        "semantic_model_key": "local_desktop_model",
        "report_template_key": "sales_report",
    }
    first = await service.execute(**request)
    replay = await service.execute(**request)

    assert first["terminal_state"] == "completed"
    assert first["memory_commit"] is True
    assert first["source_mode"] == "real"
    assert first["execution_audit"]["query_count"] == 4
    # Full request is the fixed default; the Simple schema resolves only the
    # four M3-baseline capabilities (no trend/region/customer/orders/aov).
    assert first["execution_audit"]["requested_sections"] == [
        "sales_kpi",
        "quantity_kpi",
        "orders_kpi",
        "aov_kpi",
        "time_trend",
        "category_contribution",
        "region_comparison",
        "top_products",
        "top_customers",
    ]
    assert first["execution_audit"]["unavailable_sections"] == [
        "orders_kpi",
        "aov_kpi",
        "time_trend",
        "region_comparison",
        "top_customers",
    ]
    assert first["execution_audit"]["resolved_sections"] == [
        "sales_kpi",
        "quantity_kpi",
        "category_contribution",
        "top_products",
    ]
    assert first["execution_audit"]["llm_report_intent_call_count"] == 1
    assert first["execution_audit"]["llm_dax_call_count"] == 0
    assert first["execution_audit"]["llm_report_data_call_count"] == 0
    assert first["execution_audit"]["llm_report_factual_call_count"] == 0
    assert first["execution_audit"]["renderer_llm_call_count"] == 0
    assert first["execution_audit"]["fallback_count"] == 0
    assert first["execution_audit"]["fake_query_result_count"] == 0
    assert first["tool_sequence"].count("execute_dax") == 4
    assert first["tool_sequence"].count("render_report") == 1
    assert adapter.execute_count == 4
    assert repository.store_count == 1
    assert [call.task.value for call in provider.calls] == [
        "intent_recognition",
        "query_plan",
        "report_intent",
    ]
    assert replay["idempotent_replay"] is True
    assert replay["report"]["report_id"] == first["report"]["report_id"]
    assert replay["tool_sequence"] == []
    assert adapter.execute_count == 4
    assert repository.store_count == 1


def test_local_reports_and_pbix_are_not_git_tracked():
    tracked = subprocess.run(
        ["git", "ls-files", "--", "local_state", "*.pbix"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tracked == ""


# ═════════════════════════════════════════════════════════════════════════════
# M3.4  Multi-schema adaptive capability tests
# ═════════════════════════════════════════════════════════════════════════════


def _schema_b(
    *,
    has_category: bool = True,
    has_product: bool = True,
    has_region: bool = True,
    has_customer: bool = True,
    has_orders: bool = True,
    has_aov: bool = True,
    has_date: bool = True,
) -> SemanticModelSchema:
    """Model B: richer schema with Date / Region / Customer columns."""
    columns = [
        ColumnSchema(name="OrderID", data_type="Int64"),
        ColumnSchema(name="OrderDate", data_type="DateTime"),
        ColumnSchema(name="Category", data_type="String"),
        ColumnSchema(name="Product", data_type="String"),
        ColumnSchema(name="Region", data_type="String"),
        ColumnSchema(name="Customer", data_type="String"),
        ColumnSchema(name="Quantity", data_type="Int64"),
        ColumnSchema(name="UnitPrice", data_type="Double"),
        ColumnSchema(name="SalesAmount", data_type="Double"),
    ]
    measures = [
        MeasureSchema(
            name="Total Sales",
            expression="SUM(Sales[SalesAmount])",
            data_type="Double",
        ),
        MeasureSchema(
            name="Total Quantity",
            expression="SUM(Sales[Quantity])",
            data_type="Int64",
        ),
    ]
    if has_orders:
        measures.append(MeasureSchema(
            name="Total Orders", expression="COUNTROWS(Sales)", data_type="Int64",
        ))
    if has_aov:
        measures.append(MeasureSchema(
            name="Average Order Value",
            expression="DIVIDE([Total Sales],[Total Orders])",
            data_type="Double",
        ))
    if not has_category:
        columns = [c for c in columns if c.name != "Category"]
    if not has_product:
        columns = [c for c in columns if c.name != "Product"]
    if not has_region:
        columns = [c for c in columns if c.name != "Region"]
    if not has_customer:
        columns = [c for c in columns if c.name != "Customer"]
    tables = [TableSchema(name="Sales", columns=columns, measures=measures)]
    if has_date:
        tables.append(TableSchema(
            name="Date",
            columns=[ColumnSchema(name="YearMonth", data_type="DateTime")],
        ))
    return SemanticModelSchema(
        name="local_desktop_model",
        key="local_desktop_model",
        tables=tables,
    )


def _rich_results() -> dict[str, QueryResult]:
    """Verified-style results for the full capability set."""
    common = {
        "semantic_model_key": "local_desktop_model",
        "source_mode": "real",
    }
    from datetime import date

    return {
        "total_sales": QueryResult(
            result_id="qr_ts", columns=["[Total Sales]"], rows=[[1200.5]],
            row_count=1, **common,
        ),
        "total_quantity": QueryResult(
            result_id="qr_tq", columns=["[Total Quantity]"], rows=[[9]],
            row_count=1, **common,
        ),
        "total_orders": QueryResult(
            result_id="qr_to", columns=["[Total Orders]"], rows=[[8]],
            row_count=1, **common,
        ),
        "average_order_value": QueryResult(
            result_id="qr_aov", columns=["[Average Order Value]"], rows=[[150.06]],
            row_count=1, **common,
        ),
        "monthly_sales": QueryResult(
            result_id="qr_ms",
            columns=["Date[YearMonth]", "[Total Sales]"],
            rows=[
                [date(2024, 1, 1), 100.0],
                [date(2024, 3, 1), 300.0],
                [date(2024, 2, 1), 200.0],
            ],
            row_count=3,
            **common,
        ),
        "sales_by_category": QueryResult(
            result_id="qr_sc",
            columns=["Sales[Category]", "[Total Sales]"],
            rows=[["办公用品", 700.25], ["家具", 500.25]],
            row_count=2,
            **common,
        ),
        "sales_by_region": QueryResult(
            result_id="qr_sr",
            columns=["Sales[Region]", "[Total Sales]"],
            rows=[["华东", 800.0], ["华南", 400.5]],
            row_count=2,
            **common,
        ),
        "top_products": QueryResult(
            result_id="qr_tp",
            columns=["Sales[Product]", "[Total Sales]"],
            rows=[["产品 A", 800.0], ["产品 B", 400.5]],
            row_count=2,
            **common,
        ),
        "top_customers": QueryResult(
            result_id="qr_tc",
            columns=["Sales[Customer]", "[Total Sales]"],
            rows=[["客户甲", 600.0], ["客户乙", 300.25]],
            row_count=2,
            **common,
        ),
    }


def test_full_rich_assembly_produces_kpis_trend_donut_column_and_topn():
    from backend.app.report.contracts import ReportDataPlanBuilder as Builder

    rich_keys = tuple(_rich_results())
    plan = Builder().build("sales_report", _schema_b(), requirement_keys=rich_keys)
    facts = {
        q.requirement_key: VerifiedFactSetBuilder().build(q.query_plan, _rich_results()[q.requirement_key])
        for q in plan.queries
    }
    data = SalesReportDataAssembler(
        clock=lambda: datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc)
    ).build(plan, _rich_results(), facts)
    assert len(data.kpis) == 4
    assert len(data.sections) == 5
    kinds = {item.kind for item in data.sections}
    assert kinds == {"trend", "grouped", "top_n"}
    trend = next(item for item in data.sections if item.kind == "trend")
    # Display ordering by verified time point (2024-01, 02, 03)
    assert [item.period for item in trend.values] == ["2024-01", "2024-02", "2024-03"]
    assert [item.value for item in trend.values] == [100.0, 200.0, 300.0]

    spec = SalesReportSpecBuilder().build(data)
    visuals = {item.business_role: item.visual_type for item in spec.charts}
    assert visuals == {
        "time_trend": "line",
        "category_contribution": "donut",
        "region_comparison": "column",
        "top_products": "hbar",
        "top_customers": "hbar",
    }


def test_capability_anti_fake_no_oracle_in_source():
    """Production code must not contain business oracle values."""
    production_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path("backend/app/report")).glob("*.py")
    )
    for forbidden in ("500" + "821", "35" + "8", "694" + "3997"):
        assert forbidden not in production_source
    cap_source = (Path("backend/app/report/capability.py")).read_text(encoding="utf-8")
    for forbidden in ("500" + "821", "35" + "8", "expected_total"):
        assert forbidden not in cap_source


def test_capability_no_llm_no_powerbi():
    """Capability module has zero LLM or Power BI authority."""
    source = (Path("backend/app/report/capability.py")).read_text(encoding="utf-8")
    assert "LLMProvider" not in source
    assert "PowerBIAdapter" not in source
    assert "ToolGateway" not in source
    assert "QueryResult(" not in source
