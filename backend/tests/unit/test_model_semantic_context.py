"""Runtime-only semantic adaptation, independent of registered business models."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.query_plan.grounding import (
    GroundingStatus, ObjectGrounder, SemanticGroundingService,
)
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.semantic_catalog import (
    GlossaryCatalogError, SemanticCatalogBuilder, SemanticObjectType,
)
from backend.app.schemas.data_contracts import (
    ColumnSchema, MeasureSchema, QueryPlan, QueryShape, RelationshipSchema,
    SemanticModelSchema, TableSchema,
)


def runtime_schema(key="unregistered-73"):
    return SemanticModelSchema(
        name="Runtime", key=key, runtime_identity=key, session_generation=7,
        metadata_source="local_mcp",
        tables=[
            TableSchema(name="Events", columns=[
                ColumnSchema(name="Segment", data_type="String", display_name="分组"),
                ColumnSchema(name="Recorded", data_type="DateTime"),
            ], measures=[MeasureSchema(name="Load", display_name="载荷", description="有效负载", data_type="Double")]),
            TableSchema(name="Calendar", columns=[
                ColumnSchema(name="Day", data_type="DateTime", is_key=True),
                ColumnSchema(name="Period", data_type="DateTime", format_string="yyyy-MM", expression="DATE(YEAR([Day]),MONTH([Day]),1)"),
            ]),
        ],
        relationships=[RelationshipSchema(from_table="Events", from_column="Recorded", to_table="Calendar", to_column="Day", from_cardinality="Many", to_cardinality="One")],
    )


def context(schema=None):
    return ModelSemanticContextBuilder().build(schema or runtime_schema())


def catalog(schema=None):
    return SemanticCatalogBuilder().build_from_context(context(schema))


def override(ctx):
    return {"version": 2, "semantic_model_key": ctx.semantic_model_key,
            "runtime_identity": ctx.runtime_identity,
            "schema_fingerprint": ctx.schema_fingerprint,
            "objects": {"measure:Events:Load": {"aliases": ["利用量"]}}}


def test_qualified_runtime_field_is_a_grouping_language_cue():
    runtime_catalog = catalog()
    field = runtime_catalog.get("field:Events:Segment")
    grounding = SemanticGroundingService(runtime_catalog)
    assert grounding._field_has_dimension_cue("按Events[Segment]统计Load", field)
    assert grounding._field_has_dimension_cue("按'Events'[Segment]统计Load", field)


def test_context_is_deeply_immutable_sorted_and_detached():
    schema = runtime_schema()
    original = context(schema)
    reordered = schema.model_copy(deep=True)
    reordered.tables.reverse()
    for table in reordered.tables:
        table.columns.reverse()
    assert context(reordered) == original
    schema.tables[0].measures[0].description = "changed"
    assert original.measures[0].description == "有效负载"
    with pytest.raises(ValidationError):
        original.measures[0].canonical_name = "invented"
    assert original.runtime_identity == schema.key
    assert original.session_generation == 7
    assert original.ai_instructions is None
    assert original.synonyms == ()


@pytest.mark.parametrize("phrase,method", [("Load", "canonical_exact"), ("载荷", "display_exact"), ("有效负载", "description_exact")])
def test_runtime_metadata_binding_without_glossary(phrase, method):
    result = ObjectGrounder(catalog()).resolve_phrase(phrase, SemanticObjectType.MEASURE, "measure")
    assert result.status == GroundingStatus.RESOLVED
    assert result.method == method
    assert result.canonical_object.object_id == "measure:Events:Load"


def test_unknown_model_build_does_not_require_glossary():
    result = SemanticCatalogBuilder().build(runtime_schema())
    assert result.semantic_model_key == "unregistered-73"
    assert result.get("measure:Events:Load").aliases == ()


def test_current_mentions_respect_metadata_priority_and_qualified_ownership():
    schema = runtime_schema()
    schema.tables[0].measures.append(MeasureSchema(name="Other", display_name="Load", description="载荷"))
    grounder = ObjectGrounder(catalog(schema))
    assert grounder.find_mentions("Load是多少", SemanticObjectType.MEASURE, "measure").canonical_object.canonical_name == "Load"
    assert grounder.find_mentions("载荷是多少", SemanticObjectType.MEASURE, "measure").canonical_object.canonical_name == "Load"
    schema.tables.append(TableSchema(name="OtherTable", columns=[ColumnSchema(name="Segment", data_type="String")]))
    result = ObjectGrounder(catalog(schema)).find_mentions("有哪些Events[Segment]", SemanticObjectType.FIELD, "dimension")
    assert result.canonical_object.table_name == "Events"


def test_profile_requires_explicit_exact_binding_and_stale_is_rejected():
    from backend.app.query_plan.model_override import resolve_model_override

    ctx = context()
    registry = {"version": 2, "profiles": {"business": override(ctx)["objects"]}, "overrides": []}
    assert resolve_model_override(ctx, registry) is None
    registry["overrides"] = [{"semantic_model_key": ctx.semantic_model_key, "runtime_identity": ctx.runtime_identity,
                              "schema_fingerprint": ctx.schema_fingerprint, "profile_keys": ["business"]}]
    configured = SemanticCatalogBuilder().build_from_context(ctx, resolve_model_override(ctx, registry))
    assert configured.get("measure:Events:Load").aliases == ("利用量",)
    assert resolve_model_override(context(runtime_schema("another")), registry) is None
    registry["overrides"][0]["schema_fingerprint"] = "0" * 64
    with pytest.raises(GlossaryCatalogError, match="override_schema_fingerprint_mismatch"):
        resolve_model_override(ctx, registry)


def test_missing_metadata_never_defaults_single_measure_or_date():
    schema = SemanticModelSchema(name="Minimal", key="minimal", tables=[TableSchema(name="T", columns=[ColumnSchema(name="D", data_type="DateTime")], measures=[MeasureSchema(name="M")])])
    result = ObjectGrounder(catalog(schema)).resolve_phrase("unknown", SemanticObjectType.MEASURE, "measure")
    assert result.status == GroundingStatus.UNRESOLVED
    assert SemanticGroundingService(catalog(schema))._resolve_date_field("今年").status != GroundingStatus.RESOLVED


def test_duplicate_names_preserve_ownership_and_ambiguity():
    schema = runtime_schema()
    schema.tables.append(TableSchema(name="Other", columns=[ColumnSchema(name="Segment", data_type="String")]))
    grounder = ObjectGrounder(catalog(schema))
    assert grounder.resolve_phrase("Segment", SemanticObjectType.FIELD, "dimension").status == GroundingStatus.AMBIGUOUS
    exact = grounder.resolve_phrase("Events[Segment]", SemanticObjectType.FIELD, "dimension")
    assert exact.status == GroundingStatus.RESOLVED
    assert exact.canonical_object.table_name == "Events"


def test_hidden_system_objects_never_become_candidates():
    schema = runtime_schema()
    schema.tables[0].columns[0].is_system_managed = True
    schema.tables[0].measures[0].is_hidden = True
    schema.tables[1].is_hidden = True
    built = context(schema)
    assert not built.measures
    assert [c.canonical_name for c in built.columns] == ["Recorded"]
    assert not built.relationships


@pytest.mark.parametrize("mutation", ["rename", "remove", "duplicate", "relationship", "description", "temporal"])
def test_metadata_mutation_invalidates_context_and_override(mutation):
    original = runtime_schema()
    before = context(original)
    changed = original.model_copy(deep=True)
    if mutation == "rename":
        changed.tables[0].measures[0].name = "Changed"
    elif mutation == "remove":
        changed.tables[0].columns.pop(0)
    elif mutation == "duplicate":
        changed.tables.append(TableSchema(name="Other", measures=[MeasureSchema(name="Load")]))
    elif mutation == "relationship":
        changed.relationships[0].is_active = False
    elif mutation == "description":
        changed.tables[0].measures[0].description = "new meaning"
    else:
        changed.tables[1].columns[0].name = "DifferentDay"
    after = context(changed)
    assert before.schema_fingerprint != after.schema_fingerprint
    with pytest.raises(GlossaryCatalogError, match="override_schema_fingerprint_mismatch"):
        SemanticCatalogBuilder().build_from_context(after, override(before))


def test_month_projection_preserves_spaces_inside_runtime_identifiers():
    schema = SemanticModelSchema(name="Neutral", key="space-sensitive", tables=[TableSchema(name="T", columns=[
        ColumnSchema(name="A B", data_type="DateTime"),
        ColumnSchema(name="AB", data_type="DateTime"),
        ColumnSchema(name="Month", data_type="DateTime", expression=" DATE ( YEAR ( [A B] ), MONTH ( [A B] ), 1 ) "),
    ])])
    bindings = [item for item in context(schema).temporal_candidates if item.kind == "month_projection"]
    assert len(bindings) == 1
    assert bindings[0].date_object_id == "field:T:A B"


def test_relationship_filter_metadata_changes_invalidate_context():
    original = runtime_schema()
    changed = original.model_copy(deep=True)
    changed.relationships[0] = RelationshipSchema.model_validate({
        **changed.relationships[0].model_dump(), "cross_filtering_behavior": "BothDirections",
    })
    assert context(changed).schema_fingerprint != context(original).schema_fingerprint
    assert context(changed).relationships[0].cross_filtering_behavior == "BothDirections"


@pytest.mark.parametrize("qualified_measure", [False, True])
@pytest.mark.parametrize("explicit_second_field", [False, True])
def test_complete_runtime_object_span_owns_embedded_names(qualified_measure, explicit_second_field):
    schema = SemanticModelSchema(name="Neutral", key="overlap", tables=[TableSchema(name="T", columns=[
        ColumnSchema(name="Marker", data_type="String"), ColumnSchema(name="Units", data_type="Int64"),
    ], measures=[MeasureSchema(name="Total Units")])])
    name = "T[Total Units]" if qualified_measure else "Total Units"
    message = f'T[Marker]等于"alpha"时，{name}是多少'
    if explicit_second_field:
        message += "，T[Units]等于2"
    result = ObjectGrounder(catalog(schema)).find_mentions(message, SemanticObjectType.FIELD, "filter_field")
    if explicit_second_field:
        assert result.status == GroundingStatus.AMBIGUOUS
        assert set(result.candidate_ids) == {"field:T:Marker", "field:T:Units"}
    else:
        assert result.status == GroundingStatus.RESOLVED
        assert result.canonical_object.object_id == "field:T:Marker"


def test_thin_override_uses_existing_object_and_exact_identity():
    ctx = context()
    result = SemanticCatalogBuilder().build_from_context(ctx, override(ctx))
    assert ObjectGrounder(result).resolve_phrase("利用量", SemanticObjectType.MEASURE, "measure").status == GroundingStatus.RESOLVED
    with pytest.raises(GlossaryCatalogError, match="override_model_identity_mismatch"):
        SemanticCatalogBuilder().build_from_context(context(runtime_schema("PBIX-B")), override(ctx))
    bad = override(ctx)
    bad["objects"] = {"measure:Events:Invented": {"aliases": ["利用量"]}}
    with pytest.raises(GlossaryCatalogError, match="override_unknown_object"):
        SemanticCatalogBuilder().build_from_context(ctx, bad)


@pytest.mark.parametrize("property_name", ["table_name", "data_type", "expression", "relationships", "value"])
def test_override_rejects_schema_or_facts(property_name):
    ctx = context()
    bad = override(ctx)
    bad["objects"]["measure:Events:Load"][property_name] = "invalid"
    with pytest.raises(GlossaryCatalogError):
        SemanticCatalogBuilder().build_from_context(ctx, bad)


def test_relationship_is_evidence_and_ambiguity_is_not_resolved_by_order():
    schema = runtime_schema()
    built = catalog(schema)
    assert len(built.context.relationships) == 1
    assert SemanticGroundingService(built)._resolve_date_field("今年").canonical_object.canonical_name == "Day"
    schema.tables.append(TableSchema(name="OtherCalendar", columns=[ColumnSchema(name="Day", data_type="DateTime", is_key=True)]))
    schema.relationships.append(RelationshipSchema(from_table="Events", from_column="Recorded", to_table="OtherCalendar", to_column="Day", from_cardinality="Many", to_cardinality="One"))
    assert SemanticGroundingService(catalog(schema))._resolve_date_field("今年").status == GroundingStatus.AMBIGUOUS


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["Sales", "Education", "Inventory", "unregistered-holdout"])
@pytest.mark.parametrize("shape,question", [
    (QueryShape.ENTITY_LIST, "有哪些分组"),
    (QueryShape.SCALAR, "载荷是多少"),
    (QueryShape.GROUPED, "按分组统计载荷"),
    (QueryShape.RANKING, "载荷最高的是哪个分组"),
    (QueryShape.TREND, "每月载荷趋势"),
])
async def test_zero_config_domains_share_builder_and_grounding(domain, shape, question):
    schema = runtime_schema(domain)

    async def no_members(*_):
        raise AssertionError("this shape needs no member lookup")

    outcome = await SemanticGroundingService(catalog(schema), today=lambda: date(2026, 8, 30)).ground(
        question, IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=question),
        QueryPlan(normalized_question=question, semantic_model_key=domain, query_shape=shape),
        None, no_members, query_shape=shape,
    )
    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta.measures == ([] if shape == QueryShape.ENTITY_LIST else ["Load"]) or (shape == QueryShape.ENTITY_LIST and outcome.delta.measures is None)
    if shape == QueryShape.RANKING:
        assert outcome.delta.top_n == 1


from backend.tests.fixtures.semantic_context_domains import domains


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda domain: domain.schema.key)
@pytest.mark.parametrize("shape", [QueryShape.ENTITY_LIST, QueryShape.SCALAR, QueryShape.GROUPED, QueryShape.RANKING, QueryShape.TREND])
async def test_structurally_different_zero_config_models(domain, shape):
    questions = {
        QueryShape.ENTITY_LIST: f"有哪些{domain.dimension_text}",
        QueryShape.SCALAR: f"{domain.measure_text}是多少",
        QueryShape.GROUPED: f"按{domain.dimension_text}统计{domain.measure_text}",
        QueryShape.RANKING: f"{domain.measure_text}最高的是哪个{domain.dimension_text}",
        QueryShape.TREND: f"每月{domain.measure_text}趋势",
    }
    question = questions[shape]
    runtime_catalog = SemanticCatalogBuilder().build(domain.schema)
    assert all(not obj.aliases for obj in runtime_catalog.objects)

    async def no_members(*_):
        raise AssertionError("unexpected member lookup")

    outcome = await SemanticGroundingService(runtime_catalog).ground(
        question, IntentSpec(intent=IntentType.DATA_QUESTION, confidence=1, normalized_question=question),
        QueryPlan(normalized_question=question, semantic_model_key=domain.schema.key, query_shape=shape), None, no_members,
        query_shape=shape,
    )
    assert outcome.status == GroundingStatus.RESOLVED
    if shape != QueryShape.ENTITY_LIST:
        assert outcome.delta.measures == [domain.measure]
    if shape in {QueryShape.GROUPED, QueryShape.RANKING, QueryShape.ENTITY_LIST}:
        assert outcome.delta.dimensions == [domain.dimension]
        assert outcome.delta.dimension_tables[domain.dimension] == domain.dimension_table
    if shape == QueryShape.TREND:
        assert outcome.delta.dimensions == [domain.month]
        assert outcome.delta.dimension_tables[domain.month] == domain.month_table
