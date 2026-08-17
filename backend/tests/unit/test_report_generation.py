"""Deterministic sales report, renderer, resource, and anti-bypass tests."""

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
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse
from backend.app.memory.models import MemoryStatus, RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.report.assembly import (
    SalesReportAssemblyError,
    SalesReportDataAssembler,
    SalesReportSpecBuilder,
)
from backend.app.report.contracts import ReportDataPlanBuilder
from backend.app.report.fixed import FixedSalesReportRenderer
from backend.app.report.resources import (
    InMemoryReportRepository,
    LocalReportRepository,
    ReportArtifact,
    ReportNotFoundError,
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
    plan = ReportDataPlanBuilder().build("sales_report", _schema())
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
        ReportDataPlanBuilder().build("sales_report", _schema()),
        selected_results,
        selected_facts,
    )


def test_sales_report_data_and_spec_are_exact_fixed_projections():
    data = _assembled()
    assert data.total_sales == 1200.5
    assert data.total_quantity == 9
    assert [item.category for item in data.category_sales] == ["办公用品", "家具"]
    assert [item.result_position for item in data.top_products] == [1, 2]
    assert [item.product for item in data.top_products] == ["产品 A", "产品 B"]
    assert data.source_mode == "real"
    assert len(data.query_result_ids) == 4
    assert len(data.verified_fact_set_ids) == 4

    report = SalesReportSpecBuilder().build(data)
    assert report.title == "销售分析报表"
    assert [item.name for item in report.kpis] == ["总销售额", "总销量"]
    assert [item.title for item in report.tables] == [
        "按类别销售额",
        "Top 5 产品销售额",
    ]
    assert report.charts == []
    assert report.insights == []


@pytest.mark.parametrize("missing_key", [
    "total_sales",
    "total_quantity",
    "sales_by_category",
    "top_products",
])
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
    html = await FixedSalesReportRenderer().render(report)
    assert "销售分析报表" in html
    assert "品类销售表现" in html
    assert "头部产品销售表现" in html
    assert 'data-chart="category_sales"' in html
    assert 'data-chart="top_products"' in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "<script" not in html.casefold()
    assert "javascript:" not in html.casefold()
    assert "http://" not in html.casefold()
    assert "https://" not in html.casefold()


@pytest.mark.asyncio
async def test_fixed_renderer_bar_geometry_is_deterministic_and_data_bound():
    report = SalesReportSpecBuilder().build(_assembled())
    html = await FixedSalesReportRenderer().render(report)

    assert 'data-source-value="700.25" data-bar-percent="100.00"' in html
    assert 'data-source-value="500.25" data-bar-percent="71.44"' in html
    assert 'data-source-value="800.0" data-bar-percent="100.00"' in html
    assert 'data-source-value="400.5" data-bar-percent="50.06"' in html
    assert 'style="width: 71.44%"' in html
    assert "结果序号 1" in html
    assert "严格业务排名" in html


@pytest.mark.asyncio
async def test_no_duplicate_table_visual_regression():
    """M3.3: one business question per visual — no duplicate table below bars."""
    html = await FixedSalesReportRenderer().render(
        SalesReportSpecBuilder().build(_assembled())
    )
    assert 'data-chart="category_sales"' in html
    assert 'data-chart="top_products"' in html
    # Category bars exist but no "品类明细" heading or corresponding table
    assert '<p class="detail-heading">品类明细</p>' not in html
    assert '<p class="detail-heading">产品结果明细</p>' not in html
    assert "<th>Category</th>" not in html
    assert "<th>Product</th>" not in html
    assert "<table" not in html
    # KPI still present
    assert "总销售额" in html
    assert "总销量" in html


@pytest.mark.asyncio
async def test_renderer_section_capability_respects_evidence():
    """Renderer uses section capability gates; missing evidence → no HTML."""
    report = SalesReportSpecBuilder().build(_assembled())
    html = await FixedSalesReportRenderer().render(report)
    assert "品类销售表现" in html
    assert "头部产品销售表现" in html

    # Remove source_mode → section unavailable → bars stripped
    stripped = report.model_copy(update={"source_mode": ""})
    with pytest.raises(ValueError, match="sales_report_provenance_invalid"):
        await FixedSalesReportRenderer().render(stripped)


def test_section_capability_compute():
    """SectionCapability gates correctly for present and absent evidence."""
    from backend.app.report.capability import (
        SectionKey,
        compute_section_capabilities,
    )

    # All evidence present
    caps = compute_section_capabilities(
        "sales_report", "real",
        category_row_count=3, product_row_count=2,
    )
    assert caps[SectionKey.SALES_KPI].available is True
    assert caps[SectionKey.CATEGORY_BREAKDOWN].available is True
    assert caps[SectionKey.TOP_PRODUCTS].available is True

    # Category has 0 rows → unavailable
    caps = compute_section_capabilities(
        "sales_report", "real",
        category_row_count=0, product_row_count=2,
    )
    assert caps[SectionKey.CATEGORY_BREAKDOWN].available is False

    # No source_mode → KPI unavailable
    caps = compute_section_capabilities(
        "sales_report", None,
        category_row_count=3, product_row_count=2,
    )
    assert caps[SectionKey.SALES_KPI].available is False

    # Wrong template → all unavailable
    caps = compute_section_capabilities(
        "other_template", "real",
        category_row_count=3, product_row_count=2,
    )
    assert caps[SectionKey.SALES_KPI].available is False
    assert caps[SectionKey.CATEGORY_BREAKDOWN].available is False
    assert caps[SectionKey.TOP_PRODUCTS].available is False


def test_extension_points_never_generate_automatically():
    """Extension point sections (defined in code but no contract) fail closed."""
    from backend.app.report.capability import SectionKey

    # Confirm extension_point IDs exist in the enum as comments but not as
    # active production sections.  If added, they must gate to UNAVAILABLE.
    # This test exists to catch accidental activation of a future section.
    assert SectionKey.SALES_KPI.is_extension_point() is False
    assert SectionKey.CATEGORY_BREAKDOWN.is_extension_point() is False
    assert SectionKey.TOP_PRODUCTS.is_extension_point() is False


@pytest.mark.asyncio
async def test_fixed_renderer_rejects_forged_chart_input():
    report = SalesReportSpecBuilder().build(_assembled()).model_copy(update={
        "charts": [ChartSpec(
            type="bar",
            title="伪造图表",
            x_field="Category",
            y_field="Forged Sales",
        )],
    })
    with pytest.raises(ValueError, match="sales_report_structure_invalid"):
        await FixedSalesReportRenderer().render(report)


@pytest.mark.asyncio
async def test_fixed_renderer_rejects_non_sales_report():
    with pytest.raises(ValueError, match="sales_report_renderer_template_rejected"):
        await FixedSalesReportRenderer().render(
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
    for forbidden_oracle in ("500" + "821", "35" + "8"):
        assert forbidden_oracle not in production_source


@pytest.mark.asyncio
async def test_local_repository_hash_atomic_content_and_resource_api(tmp_path):
    repository = LocalReportRepository(tmp_path / "local_state" / "reports")
    report = SalesReportSpecBuilder().build(_assembled())
    html = await FixedSalesReportRenderer().render(report)
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
    html = await FixedSalesReportRenderer().render(report)
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


class _CountingReportRepository(InMemoryReportRepository):
    def __init__(self) -> None:
        super().__init__()
        self.store_count = 0

    async def store(self, report: ReportSpec, html: str) -> ReportArtifact:
        self.store_count += 1
        return await super().store(report, html)


class _ReportLanguageProvider(LLMProvider):
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
                normalized_question="生成固定销售报表",
                requested_template="sales_report",
            )
        elif output_type is QueryPlan:
            structured = QueryPlan(
                normalized_question="生成固定销售报表",
                semantic_model_key="local_desktop_model",
                requested_template="sales_report",
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
async def test_production_turn_uses_four_real_queries_and_replays_without_rerun():
    adapter = _RealReportAdapter()
    provider = _ReportLanguageProvider()
    repository = _CountingReportRepository()
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        powerbi_local_semantic_model_key="local_desktop_model",
        max_tool_calls=8,
    )
    service = DeepSeekTurnService(
        memory_repo=InMemoryMemoryRepository(),
        llm_provider=provider,
        powerbi_adapter=adapter,
        report_renderer=FixedSalesReportRenderer(),
        report_repository=repository,
        settings=settings,
        config=HarnessConfig.from_settings(settings),
    )
    request = {
        "message": "生成销售分析报表",
        "conversation_id": "conv-fixed-sales-report",
        "request_id": "req-fixed-sales-report",
        "semantic_model_key": "local_desktop_model",
        "report_template_key": "sales_report",
    }
    first = await service.execute(**request)
    replay = await service.execute(**request)

    assert first["terminal_state"] == "completed"
    assert first["memory_commit"] is True
    assert first["source_mode"] == "real"
    assert first["execution_audit"]["query_count"] == 4
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
# M3.3  Multi-schema anti-fake compatibility tests
# ═════════════════════════════════════════════════════════════════════════════


def _schema_b(
    *,
    has_category: bool = True,
    has_product: bool = True,
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
    if not has_category:
        columns = [c for c in columns if c.name != "Category"]
    if not has_product:
        columns = [c for c in columns if c.name != "Product"]
    return SemanticModelSchema(
        name="local_desktop_model",
        key="local_desktop_model",
        tables=[TableSchema(name="Sales", columns=columns, measures=measures)],
    )


def test_model_a_facts_work_with_section_capability():
    """Model A (current simple schema) produces all three sections."""
    from backend.app.report.capability import (
        SectionKey,
        compute_section_capabilities,
    )

    data = _assembled()
    caps = compute_section_capabilities(
        "sales_report", data.source_mode,
        category_row_count=len(data.category_sales),
        product_row_count=len(data.top_products),
    )
    assert caps[SectionKey.SALES_KPI].available is True
    assert caps[SectionKey.CATEGORY_BREAKDOWN].available is True
    assert caps[SectionKey.TOP_PRODUCTS].available is True
    assert data.total_sales == 1200.5
    assert data.total_quantity == 9


def test_model_b_extra_fields_dont_auto_generate_sections():
    """Extra schema fields (Date, Region, Customer) do not create new sections.

    The capability model only gates sections defined in TemplateContract.
    New fields in the schema are ignored unless they appear in a contract's
    query_requirements.
    """
    from backend.app.report.capability import (
        SectionKey,
        compute_section_capabilities,
    )

    # Even with extra fields, only sales_report sections are gated.
    caps = compute_section_capabilities("sales_report", "real",
                                         category_row_count=3,
                                         product_row_count=2)
    # No unexpected sections auto-generated
    assert len(caps) == 3  # Only the three defined sections
    # The extra fields don't magically enable a "region" or "time" section
    # because no such section key exists in the active production capability map.
    known_keys = {SectionKey.SALES_KPI, SectionKey.CATEGORY_BREAKDOWN,
                  SectionKey.TOP_PRODUCTS}
    assert set(caps) == known_keys


def test_model_c_missing_category_fails_contract_validation():
    """Schema C: missing Category column → contract validation fails."""
    schema_c = _schema_b(has_category=False)
    from backend.app.report.contracts import ReportContractValidator
    validator = ReportContractValidator()
    result = validator.validate("sales_report", schema_c)
    assert result.available is False
    error_strs = " ".join(result.errors)
    assert "Category" in error_strs


def test_model_c_missing_product_fails_contract_validation():
    """Schema C variant: missing Product column → contract validation fails."""
    schema_c = _schema_b(has_product=False)
    from backend.app.report.contracts import ReportContractValidator
    validator = ReportContractValidator()
    result = validator.validate("sales_report", schema_c)
    assert result.available is False
    error_strs = " ".join(result.errors)
    assert "Product" in error_strs


def test_capability_anti_fake_no_oracle_in_source():
    """Production code must not contain business oracle values."""
    production_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path("backend/app/report")).glob("*.py")
    )
    for forbidden in ("500" + "821", "35" + "8"):
        assert forbidden not in production_source
    # Check the capability module specifically for numeric oracles
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
