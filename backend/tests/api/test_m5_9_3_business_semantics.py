"""M5.9.3 HTTP-boundary semantic correctness regressions."""

from __future__ import annotations

import pytest

import backend.tests.api.test_model_semantic_context as runtime_tests
from backend.app.intent.models import FilterSpec, IntentSpec
from backend.app.llm.base import LLMTask
from backend.app.schemas.data_contracts import QueryPlan, QueryShape, StructuredFilter
from backend.tests.fixtures.semantic_context_domains import domains


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda item: item.schema.key)
async def test_grouped_respectively_wording_cannot_create_a_filter(
    monkeypatch, tmp_path, domain
) -> None:
    message = f"{domain.dimension_text}{domain.measure_text}分别是多少"
    generate = runtime_tests.LanguageDraft.generate

    async def weak_filter_draft(self, request, output_type):
        response = await generate(self, request, output_type)
        if request.task == LLMTask.INTENT_RECOGNITION:
            assert isinstance(response.structured, IntentSpec)
            response.structured.detected_measures = [domain.measure_text]
            response.structured.detected_dimensions = [domain.dimension_text]
            response.structured.detected_filters = [FilterSpec(
                field=domain.dimension,
                value=domain.dimension_text,
            )]
        elif request.task == LLMTask.QUERY_PLAN:
            assert isinstance(response.structured, QueryPlan)
            response.structured.measures = [domain.measure]
            response.structured.dimensions = [domain.dimension]
            response.structured.filters = [StructuredFilter(
                field=domain.dimension,
                value=domain.dimension_text,
            )]
        return response

    monkeypatch.setattr(
        runtime_tests.LanguageDraft, "generate", weak_filter_draft
    )
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, QueryShape.GROUPED
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "completed", body
    assert body["memory_commit"] is True
    assert adapter.dax_calls == 1
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "grouped"
    assert plan["dimensions"] == [domain.dimension]
    assert plan["filters"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda item: item.schema.key)
async def test_explicit_month_range_reaches_dax_with_complete_endpoints(
    monkeypatch, tmp_path, domain
) -> None:
    message = f"2025年1月至6月每个月的{domain.measure_text}趋势是什么？"
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch,
        tmp_path,
        domain,
        message,
        QueryShape.BOUNDED_TREND,
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "completed", body.get("error_type")
    assert body["memory_commit"] is True
    assert adapter.dax_calls == 1
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "bounded_trend"
    assert plan["dimension_order"] == "asc"
    assert plan["time_range"] == {
        "date_field": next(
            item
            for item, owner in plan["dimension_tables"].items()
            if owner == domain.month_table and item != domain.month
        ),
        "start_date": "2025-01-01",
        "end_date": "2025-06-30",
        "mode": "explicit_range",
        "grain": "month",
    }
