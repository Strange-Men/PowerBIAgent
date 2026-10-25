"""Candidate retrieval narrows large catalogs without becoming authority."""

from __future__ import annotations

from backend.app.query_plan.candidate_retrieval import (
    SemanticCandidateRetriever,
    compact_evidence,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)


def large_catalog() -> SemanticCatalog:
    objects = [
        CatalogObject(
            object_id=f"field:Sales:Field{index:03d}",
            canonical_name=f"Field{index:03d}",
            object_type=SemanticObjectType.FIELD,
            table_name="Sales",
            data_type="string",
            description="synthetic dimension",
        )
        for index in range(200)
    ]
    objects.append(CatalogObject(
        object_id="field:Geography:City",
        canonical_name="City",
        object_type=SemanticObjectType.FIELD,
        table_name="Geography",
        data_type="string",
        description="城市名称",
    ))
    objects.extend(
        CatalogObject(
            object_id=f"measure:Sales:Metric{index:03d}",
            canonical_name=f"Metric{index:03d}",
            object_type=SemanticObjectType.MEASURE,
            table_name="Sales",
            data_type="decimal",
            description="synthetic metric",
        )
        for index in range(30)
    )
    objects.append(CatalogObject(
        object_id="measure:Sales:Total Profit",
        canonical_name="Total Profit",
        object_type=SemanticObjectType.MEASURE,
        table_name="Sales",
        data_type="decimal",
        description="利润",
    ))
    return SemanticCatalog(
        semantic_model_key="large",
        schema_fingerprint="a" * 64,
        objects=tuple(objects),
    )


def test_large_dimension_role_is_bounded_and_keeps_lexical_match():
    retriever = SemanticCandidateRetriever(large_catalog())
    result = retriever.retrieve(role="dimension", phrase="city")

    assert result.method == "lexical_ranked"
    assert 1 <= len(result.candidates) <= 12
    assert "field:Geography:City" in {item.object_id for item in result.candidates}
    assert all(item.object_id.startswith("field:") for item in result.candidates)


def test_large_measure_role_is_bounded_and_cross_language_terms_help():
    retriever = SemanticCandidateRetriever(large_catalog())
    result = retriever.retrieve(
        role="measure",
        phrase="销售额",
        search_terms=("total sales", "profit", "revenue"),
    )

    assert 1 <= len(result.candidates) <= 12
    assert "measure:Sales:Total Profit" in {
        item.object_id for item in result.candidates
    }


def test_compact_evidence_contains_only_metadata_not_members_or_rows():
    retriever = SemanticCandidateRetriever(large_catalog())
    result = retriever.retrieve(role="dimension", phrase="city")
    evidence = compact_evidence(large_catalog(), result.candidates)

    assert evidence
    serialized = str(evidence)
    assert "member" not in serialized.casefold()
    assert "row" not in serialized.casefold()
    assert all("candidate_id" in item for item in evidence)
