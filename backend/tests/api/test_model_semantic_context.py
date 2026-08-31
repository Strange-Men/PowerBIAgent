"""Context/override integration at the actual Chat boundary, with owned cleanup."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import LLMMode, PersistenceBackend, PowerBIMode, Settings
from backend.app.intent.models import IntentSpec, IntentType, TurnRelation
from backend.app.llm.base import LLMProvider, LLMResponse, LLMTask
from backend.app.llm.profiles import LLMModelProfile, LLMProviderProtocol
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry, managed_test_run, probe_owned_sqlite_residuals
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.presentation.localization import DisplayTranslationResponse
from backend.app.schemas.data_contracts import ColumnMembersResult, QueryPlan, QueryResult, QueryShape, TableSchema, ColumnSchema
from backend.tests.fixtures.semantic_context_domains import domains


class LanguageDraft(LLMProvider):
    provider_name = "test_language"
    is_mock = False

    def __init__(self, domain, message, shape):
        self.domain, self.message, self.shape = domain, message, shape

    async def generate(self, request, output_type):
        if request.task == LLMTask.INTENT_RECOGNITION:
            output = IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=self.message, turn_relation=TurnRelation.FRESH_QUESTION)
        elif request.task == LLMTask.QUERY_PLAN:
            output = QueryPlan(normalized_question=self.message, semantic_model_key=self.domain.schema.key, query_shape=self.shape)
        elif request.task == LLMTask.DISPLAY_TRANSLATION:
            # Presentation may request translation after canonical grounding;
            # an empty bounded response preserves canonical labels unchanged.
            output = DisplayTranslationResponse()
        else:
            raise AssertionError(f"metadata binding must need no {request.task}")
        return LLMResponse(content="{}", structured=output, model="offline-language")


class RuntimeAdapter(PowerBIAdapter):
    provider_name = "test_runtime"
    is_mock = False

    def __init__(self, domain, shape, reject_dax=False):
        self.domain, self.shape, self.reject_dax = domain, shape, reject_dax
        self.dax_calls = 0
        self.last_dax = ""

    async def health_check(self):
        return True

    async def get_semantic_model_schema(self, key):
        assert key == self.domain.schema.key
        return self.domain.schema.model_copy(deep=True)

    async def get_column_members(self, request):
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key, table_name=request.table_name, field_name=request.field_name, values=[], source_mode="real")

    async def execute_dax(self, request):
        self.dax_calls += 1
        self.last_dax = request.dax
        assert not self.reject_dax, "unresolved/ambiguous requirement reached DAX"
        domain = self.domain
        if self.shape == QueryShape.SCALAR:
            columns, rows = [domain.measure], [[12.5]]
        elif self.shape == QueryShape.ENTITY_LIST:
            columns, rows = [domain.dimension], [["A"], ["B"]]
        elif self.shape == QueryShape.TREND:
            columns, rows = [domain.month, domain.measure], [["2025-01-01T00:00:00", 12.5], ["2025-02-01T00:00:00", 14.0]]
        else:
            columns, rows = [domain.dimension, domain.measure], [["A", 12.5]]
        return QueryResult(semantic_model_key=request.semantic_model_key, columns=columns, rows=rows, row_count=len(rows), source_mode="real", request_id=request.request_id)

    async def normalize_result(self, raw):
        raise AssertionError("unused")

    async def normalize_error(self, raw):
        raise AssertionError("unused")


def create_runtime_app(monkeypatch, tmp_path, domain, message, shape, reject_dax=False):
    import backend.app.llm.factory as factory
    import backend.app.main as main

    registry = LLMProviderRegistry()
    registry.register(LLMModelProfile(profile_key="deepseek", display_name="Offline language", provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS, model="offline-language", timeout_seconds=10), LanguageDraft(domain, message, shape))
    adapter = RuntimeAdapter(domain, shape, reject_dax)
    monkeypatch.setattr(factory, "build_llm_registry", lambda settings: registry)
    monkeypatch.setattr(main, "LocalMCPPowerBIAdapter", lambda **kwargs: adapter)
    database = tmp_path / "runtime.db"
    app = main.create_app(Settings(_env_file=None, llm_mode=LLMMode.DEEPSEEK, powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real", persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(database), presentation_localization_registry_path=str(tmp_path / "display.json")))
    return app, adapter, database


async def owned_request(app, database, tmp_path, domain, message):
    from backend.app.persistence.database import create_engine
    from backend.app.persistence.models import Base

    engine = create_engine(Settings(_env_file=None, persistence_database_path=str(database)))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    registry = ArtifactOwnershipRegistry(tmp_path / "ownership.json")
    run_id = "context-api-" + uuid.uuid4().hex
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async def delete_conversation(identity):
                response = await client.delete(f"/api/v1/conversations/{identity}", params={"runtime_mode": "real"})
                assert response.status_code in (200, 404)

            async def delete_report(identity):
                raise AssertionError("no reports in context tests")

            async def probe(run):
                return probe_owned_sqlite_residuals(database, run)

            async with managed_test_run(registry, test_run_id=run_id, test_namespace=run_id, runtime_mode="real", source_mode="real", delete_conversation=delete_conversation, delete_report=delete_report, residual_probe=probe) as owner:
                conversation = str(uuid.uuid4())
                owner.add_conversation(conversation)
                owner.add_sqlite_path(database)
                response = await client.post("/api/v1/chat", json={"message": message, "semantic_model_key": domain.schema.key, "conversation_id": conversation, "request_id": str(uuid.uuid4())})
                assert response.status_code == 200
                return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda domain: domain.schema.key)
@pytest.mark.parametrize("shape", [QueryShape.ENTITY_LIST, QueryShape.SCALAR, QueryShape.GROUPED, QueryShape.RANKING, QueryShape.TREND])
async def test_runtime_only_chat_shapes(monkeypatch, tmp_path, domain, shape):
    message = {
        QueryShape.ENTITY_LIST: f"有哪些{domain.dimension_text}",
        QueryShape.SCALAR: f"{domain.measure_text}是多少",
        QueryShape.GROUPED: f"按{domain.dimension_text}统计{domain.measure_text}",
        QueryShape.RANKING: f"{domain.measure_text}最高的是哪个{domain.dimension_text}",
        QueryShape.TREND: f"每月{domain.measure_text}趋势",
    }[shape]
    app, adapter, database = create_runtime_app(monkeypatch, tmp_path, domain, message, shape)
    body = await owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "completed", body.get("error_type")
    assert body["memory_commit"] is True
    assert adapter.dax_calls == 1
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == shape.value
    if shape != QueryShape.ENTITY_LIST:
        assert plan["measures"] == [domain.measure]
    if shape in {QueryShape.GROUPED, QueryShape.RANKING, QueryShape.ENTITY_LIST}:
        assert plan["dimension_tables"][domain.dimension] == domain.dimension_table
    if shape == QueryShape.TREND:
        assert plan["dimension_tables"][domain.month] == domain.month_table


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda domain: domain.schema.key)
@pytest.mark.parametrize("quoted", [False, True])
async def test_qualified_runtime_grouping_keeps_shape_and_owner(monkeypatch, tmp_path, domain, quoted):
    table = f"'{domain.dimension_table}'" if quoted else domain.dimension_table
    message = f"按{table}[{domain.dimension}]统计{domain.measure}"
    app, adapter, database = create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.GROUPED)
    body = await owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "completed"
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "grouped"
    assert plan["dimensions"] == [domain.dimension]
    assert plan["dimension_tables"][domain.dimension] == domain.dimension_table
    assert adapter.dax_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("weak_filter", [False, True])
async def test_measure_name_substring_does_not_create_extra_filter_field(monkeypatch, tmp_path, weak_filter):
    from backend.app.schemas.data_contracts import StructuredFilter, FilterOperator

    domain = domains()[2]
    domain.schema.tables[0].measures[0].name = domain.measure = "Total Units"
    domain.schema.tables[0].columns.append(ColumnSchema(name="Units", data_type="Int64"))
    message = f'{domain.dimension_table}[{domain.dimension}]等于"alpha"时，{domain.measure}是多少'
    original_generate = LanguageDraft.generate

    async def generate(self, request, output_type):
        response = await original_generate(self, request, output_type)
        if weak_filter and request.task == LLMTask.QUERY_PLAN:
            response.structured.filters = [StructuredFilter(field=domain.dimension, operator=FilterOperator.EQ, value="alpha")]
        return response

    async def runtime_members(self, request):
        assert (request.table_name, request.field_name) == (domain.dimension_table, domain.dimension)
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key, table_name=request.table_name,
            field_name=request.field_name, values=["alpha", "beta"], source_mode="real")

    monkeypatch.setattr(LanguageDraft, "generate", generate)
    monkeypatch.setattr(RuntimeAdapter, "get_column_members", runtime_members)
    app, adapter, database = create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.SCALAR)
    body = await owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "completed"
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["filters"] == [{"field":domain.dimension, "operator":"eq", "value":"alpha"}]
    assert plan["measures"] == [domain.measure]
    assert plan["dimension_tables"][domain.dimension] == domain.dimension_table
    assert adapter.dax_calls == 1


@pytest.mark.asyncio
async def test_runtime_trend_with_invalid_weak_intent_still_clarifies(monkeypatch, tmp_path):
    from backend.app.llm.base import LLMValidationError

    domain = domains()[0]
    domain.schema.tables[2].columns[1].expression = None
    message = f"每月{domain.measure}趋势"
    generate = LanguageDraft.generate

    async def invalid_intent(self, request, output_type):
        if request.task == LLMTask.INTENT_RECOGNITION:
            raise LLMValidationError("invalid weak time draft", error_code="output_schema_invalid")
        return await generate(self, request, output_type)

    monkeypatch.setattr(LanguageDraft, "generate", invalid_intent)
    app, adapter, database = create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.TREND, True)
    body = await owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "clarification_required"
    assert body["memory_commit"] is False
    assert adapter.dax_calls == 0
    assert body["execution_audit"]["intent_fallback"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown_measure", "duplicate_dimension", "missing_month_evidence", "disconnected_relationship"])
async def test_context_unresolved_is_zero_dax_and_no_memory(monkeypatch, tmp_path, failure):
    domain = domains()[0]
    shape = QueryShape.GROUPED
    message = f"按{domain.dimension_text}统计{domain.measure_text}"
    if failure == "unknown_measure":
        message = f"按{domain.dimension_text}统计不存在的指标"
    elif failure == "duplicate_dimension":
        domain.schema.tables.append(TableSchema(name="AnotherArea", columns=[ColumnSchema(name="Another", data_type="String", description=domain.dimension_text)]))
    elif failure == "missing_month_evidence":
        shape = QueryShape.TREND
        message = f"每月{domain.measure_text}趋势"
        domain.schema.tables[2].columns[1].expression = None
    else:
        domain = domains()[-1]
        domain.schema.relationships.clear()
        message = f"按{domain.dimension_text}统计{domain.measure_text}"
    app, adapter, database = create_runtime_app(monkeypatch, tmp_path, domain, message, shape, True)
    body = await owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == ("validation_failed" if failure == "disconnected_relationship" else "clarification_required")
    assert body["memory_commit"] is False
    assert adapter.dax_calls == 0
