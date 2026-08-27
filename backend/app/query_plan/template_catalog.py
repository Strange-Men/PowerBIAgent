"""Application-scoped deterministic report-template grounding."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from backend.app.query_plan.semantic_catalog import normalize_semantic_text
from backend.app.report.registry import DEFAULT_REPORT_TEMPLATE_REGISTRY


class TemplateGroundingStatus(str, Enum):
    NOT_MENTIONED = "NOT_MENTIONED"
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    CONFIG_CONFLICT = "CONFIG_CONFLICT"


class TemplateDefinition(BaseModel):
    key: str
    aliases: tuple[str, ...] = ()
    allowed: bool = True

    model_config = ConfigDict(frozen=True)


class TemplateGroundingResult(BaseModel):
    status: TemplateGroundingStatus
    canonical_key: str | None = None
    candidate_keys: tuple[str, ...] = ()
    method: str
    weak_signal_disagrees: bool = False

    model_config = ConfigDict(frozen=True)


class TemplateCatalog:
    """Resolve only registry-owned keys and approved business terms."""

    def __init__(
        self,
        definitions: tuple[TemplateDefinition, ...],
        *,
        default_key: str | None = None,
    ):
        self._definitions = definitions
        self._by_key = {item.key: item for item in definitions}
        if len(self._by_key) != len(definitions):
            raise ValueError("template_catalog_duplicate_key")
        if default_key is not None:
            raise ValueError("template_catalog_default_forbidden")

        alias_targets: dict[str, set[str]] = {}
        for item in definitions:
            for alias in item.aliases:
                normalized = normalize_semantic_text(alias)
                if not normalized:
                    raise ValueError("template_catalog_empty_alias")
                alias_targets.setdefault(normalized, set()).add(item.key)
        self._alias_targets = alias_targets

    @property
    def allowed_keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self._definitions if item.allowed)

    @classmethod
    def from_report_registry(cls) -> "TemplateCatalog":
        return cls(tuple(
            TemplateDefinition(
                key=item.template_key,
                aliases=item.aliases,
                allowed=item.availability.value == "available",
            )
            for item in DEFAULT_REPORT_TEMPLATE_REGISTRY.descriptors
        ))

    def get_definition(self, key: str) -> TemplateDefinition | None:
        """Return registry metadata without granting availability."""

        return self._by_key.get(key)

    def ground(
        self,
        user_input: str,
        *,
        weak_requested_template: str | None = None,
        explicit_template_key: str | None = None,
        required: bool = False,
    ) -> TemplateGroundingResult:
        if explicit_template_key is not None:
            explicit = self._by_key.get(explicit_template_key)
            if explicit is None or not explicit.allowed:
                return TemplateGroundingResult(
                    status=TemplateGroundingStatus.UNRESOLVED,
                    method="explicit_key_not_allowed",
                )
            return TemplateGroundingResult(
                status=TemplateGroundingStatus.RESOLVED,
                canonical_key=explicit.key,
                candidate_keys=(explicit.key,),
                method="explicit_canonical_key",
                weak_signal_disagrees=(
                    weak_requested_template not in (None, explicit.key)
                ),
            )

        # Report generation always requires an explicit application-owned key.
        # Natural-language mentions and weak LLM drafts are never template
        # selection authority, even while the catalog exposes only one option.
        if required:
            return TemplateGroundingResult(
                status=TemplateGroundingStatus.UNRESOLVED,
                method="required_template_missing",
                weak_signal_disagrees=weak_requested_template is not None,
            )

        normalized_input = normalize_semantic_text(user_input)
        disabled_mentioned = any(
            not item.allowed
            and (
                normalize_semantic_text(item.key) in normalized_input
                or any(
                    normalize_semantic_text(alias) in normalized_input
                    for alias in item.aliases
                )
            )
            for item in self._definitions
        )
        if disabled_mentioned:
            return TemplateGroundingResult(
                status=TemplateGroundingStatus.UNRESOLVED,
                method="disabled_template_mentioned",
            )
        canonical_matches = {
            item.key
            for item in self._definitions
            if item.allowed and normalize_semantic_text(item.key) in normalized_input
        }
        if canonical_matches:
            return self._result_from_matches(
                canonical_matches, "canonical_exact", weak_requested_template
            )

        alias_matches: set[str] = set()
        conflicted = False
        for alias, targets in self._alias_targets.items():
            if alias and alias in normalized_input:
                allowed_targets = {
                    key for key in targets if self._by_key[key].allowed
                }
                alias_matches.update(allowed_targets)
                conflicted = conflicted or len(allowed_targets) > 1
        if conflicted:
            return TemplateGroundingResult(
                status=TemplateGroundingStatus.CONFIG_CONFLICT,
                candidate_keys=tuple(sorted(alias_matches)),
                method="alias_config_conflict",
            )
        if alias_matches:
            return self._result_from_matches(
                alias_matches, "approved_alias_exact", weak_requested_template
            )

        return TemplateGroundingResult(
            status=(
                TemplateGroundingStatus.UNRESOLVED
                if required else TemplateGroundingStatus.NOT_MENTIONED
            ),
            method=("required_template_missing" if required else "no_template_mention"),
            weak_signal_disagrees=weak_requested_template is not None,
        )

    @staticmethod
    def _result_from_matches(
        matches: set[str], method: str, weak_requested_template: str | None
    ) -> TemplateGroundingResult:
        ordered = tuple(sorted(matches))
        if len(ordered) != 1:
            return TemplateGroundingResult(
                status=TemplateGroundingStatus.AMBIGUOUS,
                candidate_keys=ordered,
                method=f"{method}_ambiguous",
            )
        key = ordered[0]
        return TemplateGroundingResult(
            status=TemplateGroundingStatus.RESOLVED,
            canonical_key=key,
            candidate_keys=(key,),
            method=method,
            weak_signal_disagrees=weak_requested_template not in (None, key),
        )


DEFAULT_TEMPLATE_CATALOG = TemplateCatalog.from_report_registry()
