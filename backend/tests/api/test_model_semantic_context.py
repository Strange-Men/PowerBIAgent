"""Context/override integration at the actual Chat boundary, with owned cleanup."""

import json
import calendar
import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import LLMMode, PersistenceBackend, PowerBIMode, Settings
from backend.app.intent.models import TimeIntentDraft, TimeIntentKind, TurnRelation
from backend.app.intent.semantic_interpreter import (
    RankingIntent,
    SemanticCoverageDecision,
    SemanticEvidenceSpan,
    SemanticFilterMention,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.llm.base import LLMProvider, LLMResponse, LLMTask
from backend.app.llm.profiles import LLMModelProfile, LLMProviderProtocol
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry, managed_test_run, probe_owned_sqlite_residuals
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.presentation.localization import DisplayTranslationResponse
from backend.app.query_plan.grounding import CandidateSelection, SemanticEquivalenceVeto
from backend.app.schemas.data_contracts import ColumnMembersResult, QueryPlan, QueryResult, QueryShape, TableSchema, ColumnSchema
from backend.tests.fixtures.semantic_context_domains import domains


class LanguageDraft(LLMProvider):
    provider_name = "test_language"
    is_mock = False

    def __init__(self, domain, message, shape):
        self.domain, self.message, self.shape = domain, message, shape

    async def generate(self, request, output_type):
        if request.task == LLMTask.UNDERSTANDING:
            output = self.semantic_frame()
        elif request.task == LLMTask.UNDERSTANDING_COVERAGE:
            output = SemanticCoverageDecision(decision="ACCEPT")
        elif request.task == LLMTask.DISPLAY_TRANSLATION:
            # Presentation may request translation after canonical grounding;
            # an empty bounded response preserves canonical labels unchanged.
            output = DisplayTranslationResponse()
        elif request.task == LLMTask.SEMANTIC_SELECTION:
            output = self.semantic_selection(request)
        elif request.task == LLMTask.SEMANTIC_EQUIVALENCE_VETO:
            payload = json.loads(request.messages[-1]["content"])
            output = SemanticEquivalenceVeto(
                decision=(
                    "REJECT"
                    if payload["requested_literal"] in {"深圳", "火星区"}
                    else "ACCEPT"
                ),
                mismatch=(
                    "PROPER_ENTITY"
                    if payload["requested_literal"] in {"深圳", "火星区"}
                    else "NONE"
                ),
            )
        else:
            raise AssertionError(f"metadata binding must need no {request.task}")
        return LLMResponse(content="{}", structured=output, model="offline-language")

    def semantic_frame(self) -> SemanticFrame:
        message = self.message
        measure = next(
            (
                item
                for item in (self.domain.measure_text, self.domain.measure)
                if item in message
            ),
            "不存在的指标" if "不存在的指标" in message else self.domain.measure,
        )
        dimension_name = (
            self.domain.month
            if self.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}
            else self.domain.dimension
        )
        dimension = next(
            (
                item
                for item in (
                    self.domain.dimension_text,
                    self.domain.dimension,
                    dimension_name,
                )
                if item in message
            ),
            "每个月"
            if "每个月" in message
            else "每月"
            if "每月" in message
            else "Monthly"
            if "Monthly" in message
            else dimension_name,
        )
        measures = () if self.shape is QueryShape.ENTITY_LIST else (measure,)
        dimension_shapes = {
            QueryShape.ENTITY_LIST,
            QueryShape.GROUPED,
            QueryShape.RANKING,
            QueryShape.MEMBER_SET,
            QueryShape.TREND,
            QueryShape.BOUNDED_TREND,
        }
        dimensions = (dimension,) if self.shape in dimension_shapes else ()
        evidence = [SemanticEvidenceSpan(slot="query_shape", text=message)]
        evidence.extend(
            SemanticEvidenceSpan(slot="measure", text=item) for item in measures
        )
        evidence.extend(
            SemanticEvidenceSpan(slot="dimension", text=item)
            for item in dimensions
        )
        filters = ()
        quoted = re.search(r'\[([^\]]+)\]\s*等于\s*"([^"]+)"', message)
        if quoted:
            field = quoted.group(1)
            member = quoted.group(2)
            filters = (SemanticFilterMention(
                field_mention=field,
                member_mention=member,
                evidence_span=member,
            ),)
            evidence.append(SemanticEvidenceSpan(slot="filter", text=member))
        ranking = None
        if self.shape is QueryShape.RANKING:
            ranking = RankingIntent(
                direction="desc",
                top_n=1,
                evidence_span=message,
            )
            evidence.append(SemanticEvidenceSpan(slot="ranking", text=message))
        time_mentions: tuple[str, ...] = ()
        time_intent = None
        if self.shape is QueryShape.BOUNDED_TREND:
            chinese = re.search(
                r"(\d{4})年(\d{1,2})月(?:至|到)(?:(\d{4})年)?(\d{1,2})月",
                message,
            )
            english = re.search(
                r"(\d{4})-(\d{2})\s+to\s+(\d{4})-(\d{2})",
                message,
                re.IGNORECASE,
            )
            if chinese:
                start_year = int(chinese.group(1))
                start_month = int(chinese.group(2))
                end_year = int(chinese.group(3) or chinese.group(1))
                end_month = int(chinese.group(4))
                time_text = chinese.group(0)
            elif english:
                start_year = int(english.group(1))
                start_month = int(english.group(2))
                end_year = int(english.group(3))
                end_month = int(english.group(4))
                time_text = english.group(0)
            else:
                raise AssertionError("bounded trend fixture requires an explicit range")
            time_mentions = (time_text,)
            time_intent = TimeIntentDraft(
                kind=TimeIntentKind.BOUNDED_RANGE,
                expression=time_text,
                start_date=f"{start_year:04d}-{start_month:02d}-01",
                end_date=(
                    f"{end_year:04d}-{end_month:02d}-"
                    f"{calendar.monthrange(end_year, end_month)[1]:02d}"
                ),
            )
            evidence.append(SemanticEvidenceSpan(slot="time", text=time_text))
        return SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            relation=TurnRelation.FRESH_QUESTION,
            query_shape=self.shape,
            measure_mentions=measures,
            dimension_mentions=dimensions,
            filter_mentions=filters,
            time_mentions=time_mentions,
            time_intent=time_intent,
            ranking_intent=ranking,
            evidence_spans=tuple(evidence),
        )

    def semantic_selection(self, request):
        content = request.messages[-1]["content"]
        if content.startswith("{"):
            payload = json.loads(content)
            requested = payload["requested_value"]
            candidate = next(
                (
                    item["candidate_id"]
                    for item in payload["candidates"]
                    if item["value"] == requested
                ),
                None,
            )
            return CandidateSelection(
                outcome="RESOLVED" if candidate else "UNRESOLVED",
                candidate_id=candidate,
                matched_phrase=requested if candidate else None,
            )
        role = content.splitlines()[0]
        current_phrase = content.split("\n当前输入：", 1)[0].split("当前短语：", 1)[-1]
        if current_phrase == "不存在的指标":
            return CandidateSelection(outcome="UNRESOLVED")
        target = (
            self.domain.measure
            if role == "角色：measure"
            else self.domain.month
            if self.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}
            else self.domain.dimension
        )
        pattern = re.compile(
            r'"object_id"\s*:\s*"([^"]+)"[^{}]*?'
            r'"canonical_name"\s*:\s*"' + re.escape(target) + r'"'
        )
        match = pattern.search(content)
        if match is None:
            return CandidateSelection(outcome="UNRESOLVED")
        return CandidateSelection(
            outcome="RESOLVED",
            candidate_id=match.group(1),
            matched_phrase=current_phrase,
        )


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
        elif self.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
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


async def owned_request(app, database, tmp_path, domain, message, request_options=None):
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
                response = await client.post("/api/v1/chat", json={"message": message, "semantic_model_key": domain.schema.key, "conversation_id": conversation, "request_id": str(uuid.uuid4()), **(request_options or {})})
                assert response.status_code == 200, response.text
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
async def test_runtime_trend_with_missing_date_metadata_still_clarifies_without_intent_llm(
    monkeypatch, tmp_path
):
    domain = domains()[0]
    domain.schema.tables[2].columns[1].expression = None
    message = f"每月{domain.measure}趋势"
    app, adapter, database = create_runtime_app(monkeypatch, tmp_path, domain, message, QueryShape.TREND, True)
    body = await owned_request(app, database, tmp_path, domain, message)
    assert body["terminal_state"] == "clarification_required", (
        body.get("error_type"), body.get("execution_audit"), body.get("trace")
    )
    assert body["memory_commit"] is False
    assert adapter.dax_calls == 0
    assert body["execution_audit"]["semantic_interpretation_authority"] == (
        "semantic_frame"
    )


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
