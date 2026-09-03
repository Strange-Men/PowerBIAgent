"""Cross-language and template state at the formal HTTP/SQLite boundary."""

import pytest

import backend.tests.api.test_model_semantic_context as runtime_tests
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMResponse, LLMTask
from backend.app.schemas.data_contracts import QueryShape, QueryPlan, ColumnMembersResult, StructuredFilter, FilterOperator
from backend.app.query_plan.grounding import CandidateSelection
from backend.tests.fixtures.semantic_context_domains import domains


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["timeout", "response_validation"])
async def test_missing_language_draft_never_executes_partial_intent_as_unfiltered_query(monkeypatch, tmp_path, category):
    from backend.app.llm.base import LLMProviderError, LLMErrorCategory

    class MissingDraft(runtime_tests.LanguageDraft):
        async def generate(self, request, output_type):
            if request.task == LLMTask.INTENT_RECOGNITION:
                return LLMResponse(content="{}", model="offline-language", structured=IntentSpec(
                    intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=self.message,
                    detected_measures=[self.domain.measure_text]))
            if request.task == LLMTask.QUERY_PLAN:
                raise LLMProviderError("must not leak", error_category=LLMErrorCategory(category))
            return await super().generate(request, output_type)

    monkeypatch.setattr(runtime_tests, "LanguageDraft", MissingDraft)
    domain = domains()[0]
    message = f"未知地点的{domain.measure_text}是多少"
    app, adapter, database = runtime_tests.create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.SCALAR)
    body = await runtime_tests.owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "validation_failed"
    assert adapter.dax_calls == 0
    assert not body.get("memory_commit")


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda item: item.schema.key)
async def test_unknown_modifier_without_domain_suffix_is_zero_dax(monkeypatch, tmp_path, domain):
    message = f"地球{domain.measure_text}是多少"
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, QueryShape.SCALAR, reject_dax=True
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )
    assert body["terminal_state"] == "clarification_required"
    assert body["memory_commit"] is False
    assert adapter.dax_calls == 0
    audit = body["execution_audit"]
    assert audit["semantic_obligation_coverage"] is False
    assert any(
        item["phrase"] == "地球" and item["status"] == "NEEDS_CLARIFICATION"
        for item in audit["semantic_obligations"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("template", [None, "sales_report", "stale-template"])
@pytest.mark.parametrize("draft_intent", [IntentType.REPORT_GENERATION, IntentType.CLARIFICATION])
async def test_template_selection_and_weak_report_intent_do_not_hijack_data(monkeypatch, tmp_path, template, draft_intent):
    class StaleIntent(runtime_tests.LanguageDraft):
        async def generate(self, request, output_type):
            if request.task == LLMTask.INTENT_RECOGNITION:
                output = IntentSpec(intent=draft_intent, confidence=.8, normalized_question=self.message,
                    needs_clarification=draft_intent == IntentType.CLARIFICATION,
                    clarification_question="请确认" if draft_intent == IntentType.CLARIFICATION else None)
                return LLMResponse(content="{}", structured=output, model="offline-language")
            return await super().generate(request, output_type)
    monkeypatch.setattr(runtime_tests, "LanguageDraft", StaleIntent)
    domain = domains()[0]
    message = f"{domain.measure_text}是多少"
    app, adapter, database = runtime_tests.create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.SCALAR)
    body = await runtime_tests.owned_request(app, database, tmp_path, domain, message,
        {"report_template_key": template})
    assert body["terminal_state"] == "completed"
    assert body["response_type"] == "answer"
    assert body["execution_audit"]["canonical_query_plan"]["requested_template"] is None
    assert adapter.dax_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda x: x.schema.key)
@pytest.mark.parametrize("shape", list(QueryShape))
@pytest.mark.parametrize("direction", ["zh_to_en", "en_to_zh"])
async def test_zero_override_cross_language_shapes_at_chat_boundary(monkeypatch, tmp_path, domain, shape, direction):
    # Remove every Chinese object label from the runtime. The same old domain
    # topology is preserved; only the fixture language provider knows the input
    # translations. This is a control-plane test, not evidence of LLM quality.
    for table in domain.schema.tables:
        for obj in (*table.columns, *table.measures):
            obj.display_name = None
            obj.description = None
    if direction == "en_to_zh":
        # Translate only runtime object names, leaving relationships and month
        # topology intact. The English input has no overlap with the bindings.
        old_measure, old_dimension = domain.measure, domain.dimension
        for table in domain.schema.tables:
            for measure in table.measures:
                if measure.name == old_measure:
                    measure.name = domain.measure_text
            for column in table.columns:
                if table.name == domain.dimension_table and column.name == old_dimension:
                    column.name = domain.dimension_text
        domain.measure, domain.dimension = domain.measure_text, domain.dimension_text
        domain.measure_text, domain.dimension_text = old_measure, old_dimension
    messages = {
        QueryShape.SCALAR: f"{domain.measure_text}是多少",
        QueryShape.ENTITY_LIST: f"有哪些{domain.dimension_text}",
        QueryShape.GROUPED: f"各{domain.dimension_text}的{domain.measure_text}",
        QueryShape.RANKING: f"{domain.measure_text}最高的是哪个{domain.dimension_text}",
        QueryShape.MEMBER_SET: f"甲站和乙站的{domain.measure_text}分别是多少",
        QueryShape.FILTERED_AGGREGATION: f"甲站和乙站的{domain.measure_text}加起来多少",
        QueryShape.TREND: f"每月{domain.measure_text}趋势",
        QueryShape.BOUNDED_TREND: f"2025年1月到2025年3月每月{domain.measure_text}趋势",
    }
    if direction == "en_to_zh":
        messages = {
            QueryShape.SCALAR: f"What is {domain.measure_text}?",
            QueryShape.ENTITY_LIST: f"List all {domain.dimension_text}",
            QueryShape.GROUPED: f"{domain.measure_text} by {domain.dimension_text}",
            QueryShape.RANKING: f"Which {domain.dimension_text} has the highest {domain.measure_text}?",
            QueryShape.MEMBER_SET: f"{domain.measure_text} for Alpha and Beta respectively",
            QueryShape.FILTERED_AGGREGATION: f"{domain.measure_text} for Alpha and Beta combined",
            QueryShape.TREND: f"Monthly {domain.measure_text} trend",
            QueryShape.BOUNDED_TREND: f"Monthly {domain.measure_text} trend from 2025-01 to 2025-03",
        }
    message = messages[shape]
    measure_table = next(t.name for t in domain.schema.tables if any(m.name == domain.measure for m in t.measures))

    class CrossLanguageDraft(runtime_tests.LanguageDraft):
        async def generate(self, request, output_type):
            if request.task == LLMTask.INTENT_RECOGNITION:
                output = IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message,
                    detected_measures=[] if shape == QueryShape.ENTITY_LIST else [domain.measure_text],
                    detected_dimensions=[domain.dimension_text] if shape in {QueryShape.ENTITY_LIST, QueryShape.GROUPED, QueryShape.RANKING} else [])
            elif request.task == LLMTask.QUERY_PLAN:
                # Weak canonical suggestions are intentionally NOT the source
                # of binding: the selector still must see runtime candidates.
                output = QueryPlan(normalized_question=message, semantic_model_key=domain.schema.key,
                    measures=[] if shape == QueryShape.ENTITY_LIST else [domain.measure],
                    dimensions=[domain.dimension] if shape in {QueryShape.ENTITY_LIST, QueryShape.GROUPED, QueryShape.RANKING} else [])
            elif request.task == LLMTask.SEMANTIC_SELECTION:
                role = request.messages[-1]["content"].splitlines()[0]
                identity = f"measure:{measure_table}:{domain.measure}" if role == "角色：measure" else f"field:{domain.dimension_table}:{domain.dimension}"
                assert identity in request.messages[-1]["content"]
                output = CandidateSelection(outcome="RESOLVED", candidate_id=identity)
            else:
                return await super().generate(request, output_type)
            return LLMResponse(content="{}", structured=output, model="offline-cross-language")

    class MembersAdapter(runtime_tests.RuntimeAdapter):
        async def get_column_members(self, request):
            assert request.field_name == domain.dimension
            return ColumnMembersResult(semantic_model_key=request.semantic_model_key, table_name=request.table_name,
                field_name=request.field_name, values=["甲站", "乙站"] if direction == "zh_to_en" else ["Alpha", "Beta"], source_mode="real")

    monkeypatch.setattr(runtime_tests, "LanguageDraft", CrossLanguageDraft)
    monkeypatch.setattr(runtime_tests, "RuntimeAdapter", MembersAdapter)
    adapter_shape = QueryShape.TREND if shape == QueryShape.BOUNDED_TREND else QueryShape.SCALAR if shape == QueryShape.FILTERED_AGGREGATION else shape
    app, adapter, database = runtime_tests.create_runtime_app(monkeypatch, tmp_path, domain, message, adapter_shape)
    body = await runtime_tests.owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "completed", body.get("execution_audit")
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == shape.value
    assert plan["measures"] == ([] if shape == QueryShape.ENTITY_LIST else [domain.measure])
    assert body["memory_commit"] and adapter.dax_calls == 1
    if shape in {QueryShape.ENTITY_LIST, QueryShape.GROUPED, QueryShape.RANKING, QueryShape.MEMBER_SET}:
        assert plan["dimensions"] == [domain.dimension]
        assert plan["dimension_tables"][domain.dimension] == domain.dimension_table
    if shape in {QueryShape.MEMBER_SET, QueryShape.FILTERED_AGGREGATION}:
        assert plan["filters"] == [{"field": domain.dimension, "operator": "in", "value": ["甲站", "乙站"] if direction == "zh_to_en" else ["Alpha", "Beta"]}]
    if shape == QueryShape.BOUNDED_TREND:
        assert plan["time_range"]["start_date"] == "2025-01-01"
        assert plan["time_range"]["end_date"] == "2025-03-31"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown_metric", "ambiguous_metric", "ambiguous_dimension", "foreign_id", "mixed_unknown_member"])
async def test_zero_override_abstention_never_reaches_dax_or_memory(monkeypatch, tmp_path, failure):
    domain = domains()[0]
    for table in domain.schema.tables:
        for obj in (*table.columns, *table.measures):
            obj.display_name = obj.description = None
    message = "甲站和未知站的净营收分别是多少" if failure == "mixed_unknown_member" else "各经营分区的幸福指数是多少"
    measure_id = "measure:Transactions:NetRevenue"
    field_id = "field:Areas:AreaName"
    class AbstainingDraft(runtime_tests.LanguageDraft):
        async def generate(self, request, output_type):
            if request.task == LLMTask.INTENT_RECOGNITION:
                output = IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message,
                    detected_measures=["净营收" if failure == "mixed_unknown_member" else "幸福指数"],
                    detected_dimensions=["经营分区"] if failure != "mixed_unknown_member" else [])
            elif request.task == LLMTask.QUERY_PLAN:
                output = QueryPlan(normalized_question=message, semantic_model_key=domain.schema.key,
                    measures=[domain.measure], dimensions=[domain.dimension] if failure != "mixed_unknown_member" else [],
                    filters=[StructuredFilter(field=domain.dimension, operator=FilterOperator.IN_SET, value=["甲站", "未知站"])] if failure == "mixed_unknown_member" else [])
            elif request.task == LLMTask.SEMANTIC_SELECTION:
                content = request.messages[-1]["content"]
                if content.startswith("{"):
                    output = CandidateSelection(outcome="UNRESOLVED")
                elif "角色：measure" in content:
                    output = CandidateSelection(outcome="AMBIGUOUS" if failure == "ambiguous_metric" else "UNRESOLVED") if failure in {"unknown_metric", "ambiguous_metric"} else CandidateSelection(outcome="RESOLVED", candidate_id="measure:Other:Ghost" if failure == "foreign_id" else measure_id)
                else:
                    output = CandidateSelection(outcome="AMBIGUOUS") if failure == "ambiguous_dimension" else CandidateSelection(outcome="RESOLVED", candidate_id=field_id)
            else:
                return await super().generate(request, output_type)
            return LLMResponse(content="{}", structured=output, model="offline-abstention")
    class Members(runtime_tests.RuntimeAdapter):
        async def get_column_members(self, request):
            return ColumnMembersResult(semantic_model_key=request.semantic_model_key, table_name=request.table_name,
                field_name=request.field_name, values=["甲站", "乙站"], source_mode="real")
    monkeypatch.setattr(runtime_tests, "LanguageDraft", AbstainingDraft)
    monkeypatch.setattr(runtime_tests, "RuntimeAdapter", Members)
    app, adapter, database = runtime_tests.create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.GROUPED, reject_dax=True)
    body = await runtime_tests.owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "clarification_required"
    assert not body.get("memory_commit") and adapter.dax_calls == 0
    assert not body["execution_audit"].get("dax_executed")
