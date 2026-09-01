"""Runtime-only language boundary; fixture selectors are not Real LLM evidence."""

import json
import pytest

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.intent.question_router import QuestionRouter
from backend.app.memory.models import StructuredWorkMemory, MemoryStatus
from backend.app.llm.base import LLMProvider, LLMResponse, LLMTask
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector, CandidateSelection, GroundingStatus,
    ObjectGrounder, SemanticGroundingService,
    MemberGrounder,
)
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder, SemanticObjectType
from backend.app.schemas.data_contracts import (
    ColumnSchema as C, MeasureSchema as M, TableSchema as T,
    SemanticModelSchema as S, QueryPlan, QueryShape, ColumnMembersResult,
    StructuredFilter, FilterOperator,
)


def schema():
    return S(name="Commerce", key="runtime-en", runtime_identity="runtime-en", session_generation=3, tables=[
        T(name="Orders", description="Completed purchase transactions", columns=[
            C(name="Product", data_type="String", description="Name of the purchased item"),
            C(name="Region", data_type="String", description="Geographical sales territory"),
            C(name="Date", data_type="DateTime"),
            C(name="Month", data_type="DateTime", expression="DATE(YEAR([Date]),MONTH([Date]),1)"),
        ], measures=[M(name="Total Sales", description="Total monetary amount of sales", format_string="$#,0.00"),
                     M(name="Total Quantity", description="Number of units sold"),
                     M(name="Order Count", description="Distinct number of orders")]),
    ])


def test_relationship_endpoint_evidence_is_object_scoped_and_does_not_prune_candidates():
    from backend.app.schemas.data_contracts import RelationshipSchema

    model = schema()
    model.tables.append(T(name="Territory", columns=[C(name="Region", data_type="String")]))
    model.relationships = [RelationshipSchema(from_table="Orders", from_column="Region",
        to_table="Territory", to_column="Region", from_cardinality="Many", to_cardinality="One")]
    catalog = SemanticCatalogBuilder().build(model)
    candidates = catalog.selection_candidates(SemanticObjectType.FIELD, "filter_field")
    evidence = {entry["object_id"]: entry for entry in catalog.selection_evidence(candidates)["candidates"]}
    assert evidence["field:Orders:Region"]["relationship_roles"] == [{
        "is_active": True, "cardinality": "Many", "related_object_id": "field:Territory:Region",
        "related_cardinality": "One"}]
    assert evidence["field:Territory:Region"]["relationship_roles"] == [{
        "is_active": True, "cardinality": "One", "related_object_id": "field:Orders:Region",
        "related_cardinality": "Many"}]
    assert evidence["field:Orders:Product"]["relationship_roles"] == []
    # Relationship endpoints are evidence, not interchangeable identities.
    assert {obj.object_id for obj in candidates} == {obj.object_id for obj in catalog.by_type(SemanticObjectType.FIELD)}
    assert ObjectGrounder(catalog).resolve_phrase("Orders[Region]", SemanticObjectType.FIELD,
        "filter_field").canonical_object.object_id == "field:Orders:Region"


@pytest.mark.parametrize("active,from_cardinality,to_cardinality", [
    (False, "Many", "One"), (True, "Many", "Many"), (True, None, None),
])
def test_relationship_endpoint_evidence_never_upgrades_missing_or_inactive_proof(active, from_cardinality, to_cardinality):
    from backend.app.schemas.data_contracts import RelationshipSchema

    model = schema()
    model.tables.append(T(name="Territory", columns=[C(name="Region", data_type="String")]))
    model.relationships = [RelationshipSchema(from_table="Orders", from_column="Region",
        to_table="Territory", to_column="Region", is_active=active,
        from_cardinality=from_cardinality, to_cardinality=to_cardinality)]
    catalog = SemanticCatalogBuilder().build(model)
    entry = catalog.selection_evidence((catalog.get("field:Territory:Region"),))["candidates"][0]
    assert entry["relationship_roles"] == [{"is_active": active, "cardinality": to_cardinality,
        "related_object_id": "field:Orders:Region", "related_cardinality": from_cardinality}]


class Selector(LLMProvider):
    provider_name = "fixture-selector"
    is_mock = False

    def __init__(self, selections):
        self.selections = list(selections)
        self.requests = []

    async def generate(self, request, output_type):
        assert request.task == LLMTask.SEMANTIC_SELECTION
        assert output_type is CandidateSelection
        self.requests.append(request)
        value = self.selections.pop(0)
        choice = CandidateSelection(outcome=value if value in {"AMBIGUOUS", "UNRESOLVED"} else "RESOLVED",
                                    candidate_id=None if value in {"AMBIGUOUS", "UNRESOLVED"} else value)
        return LLMResponse(content="{}", structured=choice, model="fixture-selector")


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["timeout", "response_validation"])
async def test_selector_failure_category_is_safe_and_not_semantic_abstention(category):
    from backend.app.llm.base import LLMProviderError, LLMErrorCategory

    class Failure(Selector):
        async def generate(self, request, output_type):
            raise LLMProviderError("secret response must never escape", error_category=LLMErrorCategory(category))

    catalog = SemanticCatalogBuilder().build(schema())
    selector = BoundedLLMObjectSelector(Failure([]))
    object_result = await ObjectGrounder(catalog, selector).select_bounded(
        "未知", "未知是多少", SemanticObjectType.MEASURE, "measure")
    member_result = await selector.select_member("未知", catalog.get("field:Orders:Region"),
        ColumnMembersResult(semantic_model_key=schema().key, table_name="Orders", field_name="Region",
            values=["Alpha", "Beta"], source_mode="real"))
    for result in (object_result, member_result):
        assert result.status == GroundingStatus.UNRESOLVED
        assert result.method.endswith("unavailable_" + category)
        assert "secret" not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase,target", [("销售额", "Total Sales"), ("营业收入", "Total Sales"), ("销量", "Total Quantity"), ("订单总数", "Order Count")])
async def test_cross_script_objects_reach_existing_bounded_selector(phrase, target):
    catalog = SemanticCatalogBuilder().build(schema())
    provider = Selector([f"measure:Orders:{target}"])
    result = await ObjectGrounder(catalog, BoundedLLMObjectSelector(provider)).select_bounded(
        phrase, phrase + "是多少", SemanticObjectType.MEASURE, "measure")
    assert result.status == GroundingStatus.RESOLVED
    assert result.canonical_object.object_id == f"measure:Orders:{target}"
    assert len(provider.requests) == 1
    prompt = provider.requests[0].messages[-1]["content"]
    assert "Completed purchase transactions" in prompt
    assert "Total monetary amount of sales" in prompt
    assert "$#,0.00" in prompt
    assert not any(obj.aliases for obj in catalog.objects)


@pytest.mark.asyncio
@pytest.mark.parametrize("shape,message,dimensions", [
    (QueryShape.ENTITY_LIST, "我们销售了哪些产品", ["Product"]),
    (QueryShape.GROUPED, "各地区销售额", ["Region"]),
    (QueryShape.RANKING, "销售额最高的是哪个产品", ["Product"]),
])
async def test_translated_weak_dimension_is_not_omission(shape, message, dimensions):
    catalog = SemanticCatalogBuilder().build(schema())
    provider = Selector((["measure:Orders:Total Sales"] if shape != QueryShape.ENTITY_LIST else []) + [f"field:Orders:{dimensions[0]}"])
    async def members(field, limit):
        return ColumnMembersResult(semantic_model_key=schema().key, table_name=field.table_name, field_name=field.canonical_name, values=[], source_mode="real")
    result = await SemanticGroundingService(catalog, selector=BoundedLLMObjectSelector(provider)).ground(
        message, IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message),
        QueryPlan(normalized_question=message, semantic_model_key=schema().key,
                  measures=[] if shape == QueryShape.ENTITY_LIST else ["Total Sales"], dimensions=dimensions),
        None, members, query_shape=shape)
    assert result.status == GroundingStatus.RESOLVED
    assert result.delta.dimensions == dimensions
    assert result.delta.dimension_tables[dimensions[0]] == "Orders"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["UNRESOLVED", "AMBIGUOUS", "measure:Other:Invented", "field:Orders:Product"])
async def test_cross_language_abstention_and_foreign_or_wrong_type_id_fail_closed(outcome):
    provider = Selector([outcome])
    result = await ObjectGrounder(SemanticCatalogBuilder().build(schema()), BoundedLLMObjectSelector(provider)).select_bounded(
        "幸福指数", "幸福指数是多少", SemanticObjectType.MEASURE, "measure")
    assert result.status in {GroundingStatus.UNRESOLVED, GroundingStatus.AMBIGUOUS}
    assert result.canonical_object is None
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_english_question_chinese_model():
    runtime = S(name="中文", key="runtime-zh", tables=[T(name="交易", measures=[M(name="销售收入", description="已完成交易的金额合计")])])
    provider = Selector(["measure:交易:销售收入"])
    result = await ObjectGrounder(SemanticCatalogBuilder().build(runtime), BoundedLLMObjectSelector(provider)).select_bounded(
        "sales revenue", "What is the sales revenue?", SemanticObjectType.MEASURE, "measure")
    assert result.status == GroundingStatus.RESOLVED
    assert result.canonical_object.canonical_name == "销售收入"


@pytest.mark.asyncio
async def test_english_bounded_trend_uses_deterministic_calendar_endpoints():
    runtime = schema()
    catalog = SemanticCatalogBuilder().build(runtime)
    async def members(field, limit):
        raise AssertionError("calculated runtime month proof needs no member lookup")
    message = "Monthly Total Sales trend from 2025-01 to 2025-03"
    outcome = await SemanticGroundingService(catalog).ground(message,
        IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message),
        QueryPlan(normalized_question=message, semantic_model_key=runtime.key), None, members,
        query_shape=QueryShape.BOUNDED_TREND)
    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta.dimensions == ["Month"]
    assert str(outcome.delta.time_range.start_date) == "2025-01-01"
    assert str(outcome.delta.time_range.end_date) == "2025-03-31"


@pytest.mark.asyncio
@pytest.mark.parametrize("replace", [False, True])
async def test_cross_language_keep_and_replace_respect_canonical_table_identity(replace):
    runtime = schema()
    runtime.tables.append(T(name="Other", columns=[C(name="Product", data_type="String")]))
    catalog = SemanticCatalogBuilder().build(runtime)
    message = "改成按地区看" if replace else "那销量呢"
    provider = Selector(["field:Orders:Region"] if replace else ["measure:Orders:Total Quantity"])
    memory = StructuredWorkMemory(state_status=MemoryStatus.COMMITTED, semantic_model_key=runtime.key,
        measures=["Total Sales"], dimensions=["Product"],
        last_query_plan={"query_shape": "grouped", "dimension_tables": {"Product": "Orders"}})
    async def members(field, limit):
        return ColumnMembersResult(semantic_model_key=runtime.key, table_name=field.table_name,
            field_name=field.canonical_name, values=[], source_mode="real")
    intent = IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message,
        detected_dimensions=["地区"] if replace else [], detected_measures=[] if replace else ["销量"])
    draft = QueryPlan(normalized_question=message, semantic_model_key=runtime.key,
        measures=["Total Sales"] if replace else ["Total Quantity"], dimensions=["Region"] if replace else ["Product"])
    outcome = await SemanticGroundingService(catalog, selector=BoundedLLMObjectSelector(provider)).ground(
        message, intent, draft, memory, members, query_shape=QueryShape.GROUPED)
    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta.dimensions == (["Region"] if replace else ["Product"])
    assert outcome.delta.dimension_tables[outcome.delta.dimensions[0]] == "Orders"
    assert outcome.delta.measures == (None if replace else ["Total Quantity"])


@pytest.mark.asyncio
@pytest.mark.parametrize("two_explicit_owners", [False, True])
async def test_committed_owner_never_resolves_two_current_explicit_qualified_filter_fields(two_explicit_owners):
    runtime = schema()
    runtime.tables.append(T(name="Other", columns=[C(name="Region", data_type="String")]))
    message = ("Orders[Region]和Other[Region]" if two_explicit_owners else "Region") + "筛选甲站的Total Sales"
    memory = StructuredWorkMemory(state_status=MemoryStatus.COMMITTED, semantic_model_key=runtime.key,
        measures=["Total Sales"], filters=[{"field": "Region", "operator": "eq", "value": "乙站"}],
        last_query_plan={"query_shape": "scalar", "dimension_tables": {"Region": "Orders"}})
    lookups = []
    async def members(field, limit):
        lookups.append(field.object_id)
        return ColumnMembersResult(semantic_model_key=runtime.key, table_name=field.table_name,
            field_name=field.canonical_name, values=["甲站", "乙站"], source_mode="real")
    result = await SemanticGroundingService(SemanticCatalogBuilder().build(runtime)).ground(message,
        IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message),
        QueryPlan(normalized_question=message, semantic_model_key=runtime.key,
            filters=[StructuredFilter(field="Region", operator=FilterOperator.EQ, value="甲站")]),
        memory, members, query_shape=QueryShape.SCALAR)
    if two_explicit_owners:
        assert result.status == GroundingStatus.AMBIGUOUS
        assert result.delta is None
        assert lookups == []
    else:
        assert result.status == GroundingStatus.RESOLVED
        assert result.delta.dimension_tables["Region"] == "Orders"
        assert lookups == ["field:Orders:Region"]


@pytest.mark.asyncio
async def test_large_catalog_cannot_truncate_into_a_false_unique_choice():
    runtime = S(name="Large", key="large", tables=[T(name="Items", measures=[M(name=f"Metric{i}") for i in range(129)])])
    provider = Selector([])
    result = await ObjectGrounder(SemanticCatalogBuilder().build(runtime), BoundedLLMObjectSelector(provider)).select_bounded(
        "请求指标", "请求指标是多少", SemanticObjectType.MEASURE, "measure")
    assert result.status == GroundingStatus.UNRESOLVED
    assert result.method == "bounded_llm_candidate_budget_exceeded"
    assert len(result.candidate_ids) == 129 and not provider.requests


@pytest.mark.asyncio
async def test_wrong_language_hypothesis_never_filters_candidates_or_binds_identity():
    catalog = SemanticCatalogBuilder().build(schema())
    provider = Selector(["measure:Orders:Total Quantity"])
    result = await ObjectGrounder(catalog, BoundedLLMObjectSelector(provider)).select_bounded(
        "销量", "总销量是多少", SemanticObjectType.MEASURE, "measure",
        language_hints=("Total Sales", "Invented", "Product"))
    assert result.canonical_object.canonical_name == "Total Quantity"
    assert len(result.candidate_ids) == 3
    evidence = json.loads(provider.requests[0].messages[-1]["content"].split("候选：\n")[1])
    assert evidence["untrusted_language_hypotheses"] == ["Total Sales"]
    assert {x["canonical_name"] for x in evidence["candidates"]} == {"Total Sales", "Total Quantity", "Order Count"}


@pytest.mark.asyncio
async def test_member_candidate_identity_is_stable_under_runtime_enumeration_order():
    catalog = SemanticCatalogBuilder().build(schema())
    provider = Selector(["UNRESOLVED", "UNRESOLVED"])
    selector = BoundedLLMObjectSelector(provider)
    field = catalog.get("field:Orders:Region")
    for values in (["North", "South"], ["South", "North"]):
        await selector.select_member("不存在", field, ColumnMembersResult(semantic_model_key=schema().key,
            table_name="Orders", field_name="Region", values=values, source_mode="real"))
    assert provider.requests[0].messages == provider.requests[1].messages


@pytest.mark.asyncio
async def test_one_member_resolution_does_not_absorb_other_question_slots():
    catalog = SemanticCatalogBuilder().build(schema())
    provider = Selector(["UNRESOLVED", "UNRESOLVED"])
    selector = BoundedLLMObjectSelector(provider)
    field = catalog.get("field:Orders:Region")
    members = ColumnMembersResult(semantic_model_key=schema().key, table_name="Orders", field_name="Region",
        values=["North", "South"], source_mode="real")
    for question in ("华南销售额", "华南和华北销售额分别是多少"):
        await selector.select_member("华南", field, members, user_input=question)
    # Other filters are separate required slots in Grounding, not reasons to
    # change this exact same literal/field/runtime-candidate interpretation.
    assert provider.requests[0].messages == provider.requests[1].messages


@pytest.mark.asyncio
async def test_member_set_never_drops_an_explicit_unknown_literal():
    catalog = SemanticCatalogBuilder().build(schema())
    message = "Region 甲站和未知站的 Total Sales 分别是多少"
    async def members(field, limit):
        return ColumnMembersResult(semantic_model_key=schema().key, table_name=field.table_name,
            field_name=field.canonical_name, values=["甲站", "乙站"], source_mode="real")
    outcome = await SemanticGroundingService(catalog).ground(message,
        IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message),
        QueryPlan(normalized_question=message, semantic_model_key=schema().key,
            filters=[StructuredFilter(field="Region", operator=FilterOperator.IN_SET, value=["甲站", "未知站"])]),
        None, members, query_shape=QueryShape.MEMBER_SET)
    assert outcome.status == GroundingStatus.UNRESOLVED
    assert outcome.delta is None


@pytest.mark.asyncio
@pytest.mark.parametrize("message,values", [
    ("Region 甲站和未知站的 Total Sales 分别是多少", ["甲站", "乙站"]),
    ("Total Sales for Region North and Atlantis respectively", ["North", "South"]),
    ("Total Sales for Region North, Atlantis and South respectively", ["North", "South"]),
])
@pytest.mark.parametrize("partial_draft", [False, True])
async def test_member_discovery_cannot_accept_known_subset_when_weak_filters_are_missing(message, values, partial_draft):
    catalog = SemanticCatalogBuilder().build(schema())
    async def members(field, limit):
        return ColumnMembersResult(semantic_model_key=schema().key, table_name=field.table_name,
            field_name=field.canonical_name, values=values, source_mode="real")
    outcome = await SemanticGroundingService(catalog).ground(message,
        IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message),
        QueryPlan(normalized_question=message, semantic_model_key=schema().key,
            filters=[StructuredFilter(field="Region", operator=FilterOperator.EQ, value=values[0])] if partial_draft else []),
        None, members, query_shape=QueryShape.MEMBER_SET)
    assert outcome.status == GroundingStatus.UNRESOLVED
    assert outcome.delta is None


@pytest.mark.parametrize("text,terms", [
    ("甲站和乙站的数值", ["甲站", "乙站"]),
    ("North and South respectively", ["North", "South"]),
    ("Research and Development and Support respectively", ["Research and Development", "Support"]),
])
def test_complete_member_conjunctions_and_literal_names_are_preserved(text, terms):
    assert not SemanticGroundingService._has_incomplete_member_conjunction(text, terms)


@pytest.mark.asyncio
async def test_same_current_member_literal_from_two_weak_drafts_is_validated_once():
    runtime = schema()
    message = "甲站和乙站的Total Sales分别是多少"
    provider = Selector(["field:Orders:Region"] * 4)
    lookups = []
    async def members(field, limit):
        lookups.append(field.object_id)
        return ColumnMembersResult(semantic_model_key=runtime.key, table_name=field.table_name,
            field_name=field.canonical_name, values=["甲站", "乙站"], source_mode="real")
    result = await SemanticGroundingService(SemanticCatalogBuilder().build(runtime),
        selector=BoundedLLMObjectSelector(provider)).ground(message,
        IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=message,
            detected_filters=[{"field": "地区", "operator": "eq", "value": value} for value in ["甲站", "乙站"]]),
        QueryPlan(normalized_question=message, semantic_model_key=runtime.key,
            filters=[StructuredFilter(field="Region", operator=FilterOperator.IN_SET, value=["甲站", "乙站"])]),
        None, members, query_shape=QueryShape.MEMBER_SET)
    assert result.status == GroundingStatus.RESOLVED
    assert len(lookups) == 2
    assert len(provider.requests) == 2
    assert result.delta.filters[0].value == ["甲站", "乙站"]


@pytest.mark.asyncio
@pytest.mark.parametrize("values,truncated,expected", [
    (["2025-01-01T00:00:00", "2025-02-01T00:00:00"], False, GroundingStatus.RESOLVED),
    (["2025-01-01T00:00:00", "2025-02-02T00:00:00"], False, GroundingStatus.UNRESOLVED),
    (["2025-01-01T00:00:00"], True, GroundingStatus.UNRESOLVED),
    ([], False, GroundingStatus.UNRESOLVED),
])
async def test_imported_month_field_requires_language_and_complete_runtime_grain_proof(values, truncated, expected):
    runtime = schema()
    runtime.tables[0].columns[-1].expression = None
    provider = Selector(["field:Orders:Month"])
    async def lookup(field, limit):
        return ColumnMembersResult(semantic_model_key=runtime.key, table_name=field.table_name,
            field_name=field.canonical_name, values=values, truncated=truncated, source_mode="real")
    result = await SemanticGroundingService(SemanticCatalogBuilder().build(runtime), selector=BoundedLLMObjectSelector(provider)).ground(
        "每月Total Sales趋势", IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question="每月Total Sales趋势"),
        QueryPlan(normalized_question="每月Total Sales趋势", semantic_model_key=runtime.key), None, lookup, query_shape=QueryShape.TREND)
    assert result.status == expected
    if expected == GroundingStatus.RESOLVED:
        assert result.delta.dimensions == ["Month"]
        assert result.delta.dimension_order == "asc"


@pytest.mark.parametrize("question,shape", [
    ("What is the total revenue?", QueryShape.SCALAR),
    ("销售收入合计是多少", QueryShape.SCALAR),
    ("总共销售了多少件", QueryShape.SCALAR),
    ("List all products", QueryShape.ENTITY_LIST),
    ("Revenue by region", QueryShape.GROUPED),
    ("Which product has the highest revenue?", QueryShape.RANKING),
    ("Monthly revenue trend", QueryShape.TREND),
    ("Monthly revenue trend from 2025-01 to 2025-03", QueryShape.BOUNDED_TREND),
    ("Units for South and North respectively", QueryShape.MEMBER_SET),
    ("Units for South and North combined", QueryShape.FILTERED_AGGREGATION),
])
def test_english_shape_language_has_no_business_object_authority(question, shape):
    assert QuestionRouter().route(question).query_shape == shape


@pytest.mark.asyncio
@pytest.mark.parametrize("requested,choice,expected", [("华南", "华南区", GroundingStatus.RESOLVED),
    ("火星区", None, GroundingStatus.UNRESOLVED), ("南区", "AMBIGUOUS", GroundingStatus.AMBIGUOUS)])
async def test_runtime_member_language_choice_never_creates_a_member(requested, choice, expected):
    class RuntimeMemberSelector(Selector):
        async def generate(self, request, output_type):
            candidates = json.loads(request.messages[-1]["content"])["candidates"]
            selected = next((x["candidate_id"] for x in candidates if x["value"] == choice), None)
            self.selections = [selected or ("AMBIGUOUS" if choice == "AMBIGUOUS" else "UNRESOLVED")]
            return await super().generate(request, output_type)
    catalog = SemanticCatalogBuilder().build(schema())
    field = catalog.get("field:Orders:Region")
    members = ColumnMembersResult(semantic_model_key=schema().key, table_name="Orders", field_name="Region",
        values=["华南区", "华北区"], source_mode="real")
    result = await BoundedLLMObjectSelector(RuntimeMemberSelector([])).select_member(requested, field, members)
    assert result.status == expected
    if result.status == GroundingStatus.RESOLVED:
        assert result.canonical_value in members.values
        assert MemberGrounder.resolve(field, result.canonical_value, members).status == GroundingStatus.RESOLVED
