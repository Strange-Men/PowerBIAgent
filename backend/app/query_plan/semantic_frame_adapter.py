"""Compatibility projection from a language SemanticFrame into Grounding input.

This module does not bind canonical identities and is not an LLM planner.  It
exists only while the established runtime Grounding API accepts ``QueryPlan`` as
its language-draft carrier.
"""

from __future__ import annotations

from backend.app.intent.models import FilterOperator
from backend.app.intent.semantic_interpreter import SemanticFrame
from backend.app.schemas.data_contracts import QueryPlan, StructuredFilter


def build_grounding_draft(
    frame: SemanticFrame,
    *,
    user_input: str,
    semantic_model_key: str,
) -> QueryPlan:
    filters: list[StructuredFilter] = []
    represented_members: set[str] = set()
    for mention in frame.filter_mentions:
        represented_members.add(mention.member_mention)
        filters.append(StructuredFilter(
            field=mention.field_mention or mention.member_mention,
            operator=FilterOperator(mention.operator.value),
            value=mention.member_mention,
        ))
    for member in frame.member_mentions:
        if member not in represented_members:
            filters.append(StructuredFilter(
                field=member,
                operator=FilterOperator.EQ,
                value=member,
            ))
    shape_evidence = next(
        (item.text for item in frame.evidence_spans if item.slot == "query_shape"),
        None,
    )
    return QueryPlan(
        normalized_question=user_input.strip(),
        semantic_model_key=semantic_model_key,
        query_shape=frame.query_shape,
        query_shape_evidence=shape_evidence,
        measure_evidence_spans=list(frame.measure_mentions),
        dimension_evidence_spans=list(frame.dimension_mentions),
        measures=list(frame.measure_mentions),
        dimensions=list(frame.dimension_mentions),
        filters=filters,
        time_range=(frame.time_mentions[0] if frame.time_mentions else None),
        sort=(frame.ranking_intent.direction if frame.ranking_intent else None),
        top_n=(frame.ranking_intent.top_n if frame.ranking_intent else None),
        comparison_mode=frame.comparison_intent,
        requested_template=None,
    )
