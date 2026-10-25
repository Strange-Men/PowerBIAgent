"""Provider-neutral candidate retrieval over one runtime SemanticCatalog.

The retriever narrows language phrases to a small bounded set of existing
catalog objects.  It is not an authority: it cannot bind a final object, create
an identity, choose a member, write a plan, or produce facts.  Every returned
candidate is an existing ``CatalogObject`` from the current catalog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
    normalize_semantic_text,
)

Role = Literal[
    "measure", "dimension", "ranking_dimension", "filter_field",
    "date_field", "temporal_grouping",
]

_LIMITS: dict[str, int] = {
    "measure": 12,
    "dimension": 12,
    "ranking_dimension": 12,
    "filter_field": 12,
    "date_field": 8,
    "temporal_grouping": 8,
}
_TOKEN = re.compile(r"[a-z0-9]+|[㐀-䶿一-鿿]", re.IGNORECASE)


@dataclass(frozen=True)
class RetrievedCandidates:
    role: Role
    phrase: str
    candidates: tuple[CatalogObject, ...]
    method: str
    scores: tuple[float, ...] = ()


class SemanticCandidateRetriever:
    """Provider-neutral, read-only candidate narrowing for one catalog."""

    def __init__(self, catalog: SemanticCatalog):
        self.catalog = catalog

    def retrieve(
        self, *, role: Role, phrase: str, search_terms: tuple[str, ...] = ()
    ) -> RetrievedCandidates:
        return retrieve(
            self.catalog, role=role, phrase=phrase, search_terms=search_terms
        )


def _object_terms(obj: CatalogObject) -> tuple[str, ...]:
    return tuple(term for term in (
        obj.canonical_name,
        obj.display_name,
        obj.description,
        obj.table_name,
        obj.format_string,
        *obj.aliases,
    ) if term)


def _tokens(text: str) -> set[str]:
    normalized = normalize_semantic_text(text)
    return set(_TOKEN.findall(normalized))


def _bigrams(text: str) -> set[str]:
    normalized = normalize_semantic_text(text)
    compact = re.sub(r"\s+", "", normalized)
    return {compact[index:index + 2] for index in range(max(0, len(compact) - 1))}


def _term_score(phrase: str, term: str) -> float:
    left = normalize_semantic_text(phrase)
    right = normalize_semantic_text(term)
    if not left or not right:
        return 0.0
    if left == right:
        return 120.0
    if left in right or right in left:
        shorter, longer = sorted((len(left), len(right)))
        return 55.0 + 35.0 * (shorter / longer)
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens)
        if overlap:
            return 45.0 * (overlap / max(len(left_tokens), len(right_tokens)))
    left_bigrams, right_bigrams = _bigrams(left), _bigrams(right)
    if left_bigrams and right_bigrams:
        overlap = len(left_bigrams & right_bigrams)
        if overlap:
            return 30.0 * (overlap / max(len(left_bigrams), len(right_bigrams)))
    return 0.0


def _score(obj: CatalogObject, phrases: tuple[str, ...]) -> float:
    terms = _object_terms(obj)
    if obj.object_type is SemanticObjectType.MEASURE:
        # A measure definition is metadata evidence, never executable output.
        terms = (*terms, obj.canonical_name)
    best = 0.0
    for phrase in phrases:
        if not phrase.strip():
            continue
        for term in terms:
            best = max(best, _term_score(phrase, term))
        # A description is longer than a label; a partial match there is weaker
        # than an exact label match but still useful retrieval evidence.
        if obj.description and normalize_semantic_text(phrase) in normalize_semantic_text(
            obj.description
        ):
            best = max(best, 25.0)
    return best


def retrieve(
    catalog: SemanticCatalog,
    *,
    role: Role,
    phrase: str,
    search_terms: tuple[str, ...] = (),
) -> RetrievedCandidates:
    """Return bounded existing candidates for one language phrase."""

    if role == "measure":
        objects = catalog.by_type(SemanticObjectType.MEASURE)
    elif role in {"dimension", "ranking_dimension", "filter_field"}:
        objects = catalog.selection_candidates(SemanticObjectType.FIELD, role)
    elif role == "date_field":
        objects = tuple(
            obj for obj in catalog.by_type(SemanticObjectType.FIELD)
            if ("date" in obj.data_type.casefold() or "time" in obj.data_type.casefold())
            and obj.temporal_grouping is None
        )
    elif role == "temporal_grouping":
        objects = tuple(
            obj for obj in catalog.by_type(SemanticObjectType.FIELD)
            if obj.temporal_grouping is not None
            or "date" in obj.data_type.casefold()
            or "time" in obj.data_type.casefold()
        )
    else:  # pragma: no cover - Literal exhaustiveness
        objects = ()
    limit = _LIMITS[role]
    if not objects:
        return RetrievedCandidates(role, phrase, (), "no_catalog_candidates")
    ordered = tuple(sorted(objects, key=lambda item: item.object_id))
    if len(ordered) <= limit:
        return RetrievedCandidates(role, phrase, ordered, "complete_bounded_role")
    phrases = tuple(dict.fromkeys(
        term.strip() for term in (phrase, *search_terms) if term and term.strip()
    ))
    scored = sorted(
        ((_score(obj, phrases), obj) for obj in ordered),
        key=lambda item: (-item[0], item[1].object_id),
    )
    selected = tuple(obj for score, obj in scored if score > 0)[:limit]
    if not selected:
        # No lexical evidence.  Return a deterministic bounded slice rather
        # than failing on catalog size; the resolver may still recognise a
        # translated concept, and otherwise the turn clarifies.
        selected = tuple(obj for _, obj in scored[:limit])
        return RetrievedCandidates(
            role, phrase, selected, "deterministic_catalog_slice",
            tuple(score for score, _ in scored[:limit]),
        )
    scores = tuple(score for score, obj in scored if score > 0)[:limit]
    return RetrievedCandidates(role, phrase, selected, "lexical_ranked", scores)


def lexical_support(phrase: str, obj: CatalogObject) -> bool:
    """Whether the object's own metadata lexically supports this phrase."""

    return _score(obj, (phrase,)) > 0


def compact_evidence(
    catalog: SemanticCatalog,
    candidates: tuple[CatalogObject, ...],
) -> list[dict[str, object]]:
    """A small candidate view for one bounded semantic resolution call.

    Descriptions and definitions are evidence, not instructions.  Member values
    and business rows never enter this view.
    """

    context = catalog.context
    tables = {table.name: table for table in context.tables} if context else {}
    measures = {item.object_id: item for item in context.measures} if context else {}
    records: list[dict[str, object]] = []
    for obj in candidates:
        table = tables.get(obj.table_name)
        record: dict[str, object] = {
            "candidate_id": obj.object_id,
            "canonical_name": obj.canonical_name[:160],
            "object_type": obj.object_type.value,
            "table_name": obj.table_name[:160],
            "data_type": obj.data_type[:80],
        }
        if obj.display_name:
            record["display_name"] = obj.display_name[:160]
        if obj.description:
            record["description"] = obj.description[:240]
        if obj.format_string:
            record["format_string"] = obj.format_string[:120]
        if obj.aliases:
            record["aliases"] = [alias[:120] for alias in obj.aliases[:6]]
        if table is not None and (table.display_name or table.description):
            record["table_context"] = {
                key: value[:200]
                for key, value in (
                    ("display_name", table.display_name),
                    ("description", table.description),
                )
                if value
            }
        definition = measures.get(obj.object_id)
        if definition is not None and definition.expression:
            record["runtime_definition"] = definition.expression[:400]
        if context is not None:
            record["relationship_roles"] = [
                {
                    "is_active": rel.is_active,
                    "cardinality": cardinality,
                    "related_object_id": related_id,
                    "related_cardinality": related_cardinality,
                }
                for rel in context.relationships
                for endpoint, cardinality, related_id, related_cardinality in (
                    (rel.from_object_id, rel.from_cardinality, rel.to_object_id, rel.to_cardinality),
                    (rel.to_object_id, rel.to_cardinality, rel.from_object_id, rel.from_cardinality),
                )
                if endpoint == obj.object_id
            ]
            record["hierarchies"] = [
                {
                    "name": hierarchy.name,
                    "levels": list(hierarchy.levels),
                }
                for hierarchy in context.hierarchies
                if obj.object_id in hierarchy.level_object_ids
            ]
        records.append(record)
    return records
