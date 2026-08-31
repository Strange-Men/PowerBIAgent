"""Explicit exact-model language supplements, never schema or result data."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.query_plan.model_semantic_context import ModelSemanticContext
from backend.app.query_plan.semantic_catalog import (
    CatalogObject, GlossaryCatalogError, SemanticObjectSource, SemanticObjectType,
    TemporalGroupingBinding, normalize_semantic_text,
)


class ObjectLanguageOverride(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    aliases: list[str] = Field(default_factory=list)
    member_aliases: dict[str, str] = Field(default_factory=dict)
    member_suffixes: list[str] = Field(default_factory=list)
    temporal_role: Literal["default"] | None = None
    temporal_grouping: TemporalGroupingBinding | None = None
    preferred_phrasing: str | None = None


class ModelBusinessOverride(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    version: Literal[2]
    semantic_model_key: str
    runtime_identity: str
    schema_fingerprint: str
    objects: dict[str, ObjectLanguageOverride]


class ModelOverrideBinding(BaseModel):
    """Only an explicit identity/fingerprint binding can activate a profile."""

    model_config = ConfigDict(extra="forbid", strict=True)
    semantic_model_key: str = Field(min_length=1)
    runtime_identity: str = Field(min_length=1)
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_keys: list[str] = Field(default_factory=list)
    objects: dict[str, ObjectLanguageOverride] = Field(default_factory=dict)


class ModelOverrideRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[2]
    profiles: dict[str, dict[str, ObjectLanguageOverride]] = Field(default_factory=dict)
    overrides: list[ModelOverrideBinding]


def resolve_model_override(context: ModelSemanticContext, raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        registry = ModelOverrideRegistry.model_validate(raw)
    except ValueError as exc:
        raise GlossaryCatalogError("override_registry_invalid") from exc
    selected = [entry for entry in registry.overrides if entry.semantic_model_key == context.semantic_model_key]
    if not selected:
        return None
    if len(selected) != 1:
        raise GlossaryCatalogError("override_model_identity_conflict")
    binding = selected[0]
    if binding.runtime_identity != context.runtime_identity:
        raise GlossaryCatalogError("override_model_identity_mismatch")
    if binding.schema_fingerprint != context.schema_fingerprint:
        raise GlossaryCatalogError("override_schema_fingerprint_mismatch")
    objects: dict[str, ObjectLanguageOverride] = {}
    for key in binding.profile_keys:
        profile = registry.profiles.get(key)
        if profile is None:
            raise GlossaryCatalogError("override_profile_unknown")
        for object_id, language in profile.items():
            if object_id in objects:
                raise GlossaryCatalogError("override_object_conflict")
            objects[object_id] = language
    for object_id, language in binding.objects.items():
        if object_id in objects:
            raise GlossaryCatalogError("override_object_conflict")
        objects[object_id] = language
    return ModelBusinessOverride(
        version=2, semantic_model_key=binding.semantic_model_key,
        runtime_identity=binding.runtime_identity,
        schema_fingerprint=binding.schema_fingerprint, objects=objects,
    ).model_dump(exclude_none=True)


def apply_model_override(context: ModelSemanticContext, objects: dict[str, CatalogObject], raw: dict[str, Any]) -> dict[str, CatalogObject]:
    try:
        binding = ModelBusinessOverride.model_validate(raw)
    except ValueError as exc:
        raise GlossaryCatalogError("override_contract_invalid") from exc
    if (binding.semantic_model_key, binding.runtime_identity) != (context.semantic_model_key, context.runtime_identity):
        raise GlossaryCatalogError("override_model_identity_mismatch")
    if binding.schema_fingerprint != context.schema_fingerprint:
        raise GlossaryCatalogError("override_schema_fingerprint_mismatch")
    result = dict(objects)
    for object_id, language in binding.objects.items():
        item = objects.get(object_id)
        if item is None:
            raise GlossaryCatalogError("override_unknown_object")
        strings = [*language.aliases, *language.member_aliases.keys(), *language.member_aliases.values(), *language.member_suffixes]
        if any(not value.strip() for value in strings):
            raise GlossaryCatalogError("override_empty_language")
        if item.object_type != SemanticObjectType.FIELD and (language.member_aliases or language.member_suffixes or language.temporal_role or language.temporal_grouping):
            raise GlossaryCatalogError("override_field_metadata_invalid")
        if language.temporal_role and not any(token in item.data_type.casefold() for token in ("date", "time")):
            raise GlossaryCatalogError("override_temporal_role_invalid")
        if language.temporal_grouping:
            temporal = language.temporal_grouping
            target = objects.get(f"field:{temporal.date_table_name}:{temporal.date_field}")
            if target is None or not any(token in target.data_type.casefold() for token in ("date", "time")):
                raise GlossaryCatalogError("override_temporal_target_invalid")
        member_aliases: dict[str, str] = {}
        for alias, value in language.member_aliases.items():
            normalized = normalize_semantic_text(alias)
            if normalized in member_aliases and member_aliases[normalized] != value:
                raise GlossaryCatalogError("override_member_alias_conflict")
            member_aliases[normalized] = value
        result[object_id] = item.model_copy(update={
            "aliases": tuple(dict.fromkeys(alias.strip() for alias in language.aliases)),
            "member_aliases": member_aliases, "member_suffixes": tuple(language.member_suffixes),
            "temporal_role": language.temporal_role,
            "temporal_grouping": language.temporal_grouping or item.temporal_grouping,
            "source": SemanticObjectSource.RUNTIME_GLOSSARY,
        })
    if sum(item.temporal_role == "default" for item in result.values()) > 1:
        raise GlossaryCatalogError("override_default_temporal_role_conflict")
    return result
