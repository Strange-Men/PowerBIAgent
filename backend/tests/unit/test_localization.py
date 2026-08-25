"""M5.5 model/object/schema-scoped display localization boundaries."""

from pathlib import Path

import pytest

from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.localization.models import LocalizationRecord, LocalizationSource
from backend.app.localization.registry import LocalizationRegistry
from backend.app.localization.service import DisplayTranslationBatch, LocalizationService
from backend.app.query_plan.semantic_catalog import (
    SemanticCatalogBuilder,
    compute_schema_fingerprint,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnSchema,
    MeasureSchema,
    SemanticModelSchema,
    TableSchema,
)


class TranslationProvider(LLMProvider):
    def __init__(self, labels: dict[str, str], confidence: float = 0.95):
        self.labels = labels
        self.confidence = confidence
        self.calls: list[LLMRequest] = []

    @property
    def provider_name(self) -> str:
        return "translation-test"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(self, request, output_type):
        self.calls.append(request)
        assert request.task == LLMTask.DISPLAY_TRANSLATION
        translations = [
            {
                "object_identity": object_id,
                "display_name": label,
                "confidence": self.confidence,
            }
            for object_id, label in self.labels.items()
        ]
        structured = DisplayTranslationBatch(translations=translations)
        return LLMResponse(content="{}", structured=structured, model="test")


def _schema(*, metadata_display: str | None = None) -> SemanticModelSchema:
    return SemanticModelSchema(
        name="Education",
        key="education-model",
        tables=[
            TableSchema(
                name="Students",
                columns=[
                    ColumnSchema(
                        name="StudentCount",
                        data_type="int64",
                        display_name=metadata_display,
                    )
                ],
                measures=[
                    MeasureSchema(name="AttendanceRate", data_type="decimal")
                ],
            )
        ],
    )


def _catalog(schema: SemanticModelSchema, glossary: dict | None = None):
    data = glossary or {
        "version": 1,
        "semantic_model_key": schema.key,
        "schema_fingerprint": compute_schema_fingerprint(schema),
        "measures": {},
        "fields": {},
    }
    return SemanticCatalogBuilder().build_from_data(schema, data)


def _plan(*, measures=None, dimensions=None) -> CanonicalQueryPlan:
    return CanonicalQueryPlan(
        normalized_question="query",
        semantic_model_key="education-model",
        measures=measures or [],
        dimensions=dimensions or [],
        dimension_tables={"StudentCount": "Students"},
    )


@pytest.mark.asyncio
async def test_model_metadata_has_highest_display_priority(tmp_path: Path):
    schema = _schema(metadata_display="学生人数")
    catalog = _catalog(schema)
    provider = TranslationProvider({"field:Students:StudentCount": "错误翻译"})
    labels = await LocalizationService(
        LocalizationRegistry(tmp_path / "registry.json")
    ).resolve_for_plan(
        schema=schema,
        catalog=catalog,
        plan=_plan(dimensions=["StudentCount"]),
        translator=provider,
    )
    assert labels["Students[StudentCount]"].display_name == "学生人数"
    assert labels["Students[StudentCount]"].source == LocalizationSource.MODEL_METADATA
    assert provider.calls == []


@pytest.mark.asyncio
async def test_glossary_display_precedes_registry_and_translation(tmp_path: Path):
    schema = _schema()
    glossary = {
        "version": 1,
        "semantic_model_key": schema.key,
        "schema_fingerprint": compute_schema_fingerprint(schema),
        "measures": {
            "AttendanceRate": {
                "table_name": "Students",
                "object_type": "measure",
                "display_name": "出勤率",
                "aliases": ["到课率"],
            }
        },
        "fields": {},
    }
    catalog = _catalog(schema, glossary)
    labels = await LocalizationService(
        LocalizationRegistry(tmp_path / "registry.json")
    ).resolve_for_plan(
        schema=schema,
        catalog=catalog,
        plan=_plan(measures=["AttendanceRate"]),
        translator=None,
    )
    assert labels["[AttendanceRate]"].display_name == "出勤率"
    assert labels["[AttendanceRate]"].canonical_name == "AttendanceRate"
    assert labels["[AttendanceRate]"].source == LocalizationSource.GLOSSARY


@pytest.mark.asyncio
async def test_registry_hit_is_exact_and_schema_change_invalidates(tmp_path: Path):
    schema = _schema()
    catalog = _catalog(schema)
    registry = LocalizationRegistry(tmp_path / "registry.json")
    registry.put(LocalizationRecord(
        semantic_model_key=schema.key,
        object_identity="measure:Students:AttendanceRate",
        object_type="measure",
        canonical_name="AttendanceRate",
        display_name="持久化出勤率",
        source=LocalizationSource.LLM_TRANSLATION,
        schema_identity=catalog.schema_fingerprint,
    ))
    service = LocalizationService(registry)
    hit = await service.resolve_for_plan(
        schema=schema,
        catalog=catalog,
        plan=_plan(measures=["AttendanceRate"]),
        translator=None,
    )
    assert hit["[AttendanceRate]"].display_name == "持久化出勤率"
    assert hit["[AttendanceRate]"].source == LocalizationSource.REGISTRY

    drifted = schema.model_copy(update={"name": "Education v2"})
    drifted.tables[0].measures[0].expression = "1"
    drifted_catalog = _catalog(drifted)
    miss = await service.resolve_for_plan(
        schema=drifted,
        catalog=drifted_catalog,
        plan=_plan(measures=["AttendanceRate"]),
        translator=None,
    )
    assert miss["[AttendanceRate]"].display_name == "Attendance Rate"
    assert miss["[AttendanceRate]"].source == LocalizationSource.HUMANIZED_FALLBACK


@pytest.mark.asyncio
async def test_unknown_education_fields_use_bounded_translation_and_persist(tmp_path: Path):
    schema = _schema()
    catalog = _catalog(schema)
    provider = TranslationProvider({
        "measure:Students:AttendanceRate": "出勤率",
        "field:Students:StudentCount": "学生人数",
        "field:Students:Ghost": "不存在字段",
    })
    registry = LocalizationRegistry(tmp_path / "registry.json")
    labels = await LocalizationService(registry).resolve_for_plan(
        schema=schema,
        catalog=catalog,
        plan=_plan(
            measures=["AttendanceRate"], dimensions=["StudentCount"]
        ),
        translator=provider,
    )
    assert labels["[AttendanceRate]"].display_name == "出勤率"
    assert labels["Students[StudentCount]"].display_name == "学生人数"
    assert all(item.canonical_name in {"AttendanceRate", "StudentCount"} for item in labels.values())
    assert "Ghost" not in labels
    assert provider.calls[0].metadata == {"candidate_count": 2}

    second_provider = TranslationProvider({})
    cached = await LocalizationService(registry).resolve_for_plan(
        schema=schema,
        catalog=catalog,
        plan=_plan(measures=["AttendanceRate"]),
        translator=second_provider,
    )
    assert cached["[AttendanceRate]"].source == LocalizationSource.REGISTRY
    assert second_provider.calls == []


@pytest.mark.asyncio
async def test_nonexistent_object_is_never_sent_to_translation(tmp_path: Path):
    schema = _schema()
    provider = TranslationProvider({"field:Students:Ghost": "不存在字段"})
    labels = await LocalizationService(
        LocalizationRegistry(tmp_path / "registry.json")
    ).resolve_for_plan(
        schema=schema,
        catalog=_catalog(schema),
        plan=_plan(dimensions=["Ghost"]),
        translator=provider,
    )
    assert labels == {}
    assert provider.calls == []
