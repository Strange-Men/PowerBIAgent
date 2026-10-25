"""One bounded semantic resolution over existing candidate IDs."""

from __future__ import annotations

import json

import pytest

from backend.app.llm.base import LLMProvider, LLMResponse
from backend.app.query_plan.candidate_retrieval import (
    SemanticCandidateRetriever,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)
from backend.app.query_plan.semantic_resolution import (
    BoundedSemanticResolver,
    ResolutionDecision,
    ResolutionResponse,
    ResolutionSlot,
)


def catalog() -> SemanticCatalog:
    objects = [
        CatalogObject(
            object_id="measure:Sales:Total Sales",
            canonical_name="Total Sales",
            object_type=SemanticObjectType.MEASURE,
            table_name="Sales",
            data_type="decimal",
            description="销售额",
        ),
        CatalogObject(
            object_id="measure:Sales:Total Quantity",
            canonical_name="Total Quantity",
            object_type=SemanticObjectType.MEASURE,
            table_name="Sales",
            data_type="int64",
            description="销量",
        ),
        CatalogObject(
            object_id="field:Geography:City",
            canonical_name="City",
            object_type=SemanticObjectType.FIELD,
            table_name="Geography",
            data_type="string",
            description="城市",
        ),
        CatalogObject(
            object_id="field:Product:Product",
            canonical_name="Product",
            object_type=SemanticObjectType.FIELD,
            table_name="Product",
            data_type="string",
            description="产品",
        ),
    ]
    return SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="a" * 64,
        objects=tuple(objects),
    )


class _ResolverProvider(LLMProvider):
    provider_name = "resolver"
    is_mock = False

    def __init__(self, candidate_by_role):
        self.candidate_by_role = candidate_by_role
        self.calls = 0
        self.payloads = []

    async def generate(self, request, output_type):
        self.calls += 1
        payload = json.loads(request.messages[-1]["content"])
        self.payloads.append(payload)
        decisions = []
        for slot in payload["slots"]:
            candidate = self.candidate_by_role.get(slot["role"])
            ids = {item["candidate_id"] for item in slot["candidates"]}
            decisions.append(ResolutionDecision(
                slot_id=slot["slot_id"],
                outcome="RESOLVED" if candidate in ids else "UNRESOLVED",
                candidate_id=candidate if candidate in ids else None,
            ))
        return LLMResponse(
            content="{}",
            structured=ResolutionResponse(decisions=tuple(decisions)),
            model="resolver",
        )


def slots():
    retriever = SemanticCandidateRetriever(catalog())
    return (
        ResolutionSlot(
            slot_id="m0",
            role="measure",
            phrase="sales",
            candidates=retriever.retrieve(
                role="measure", phrase="sales", search_terms=("revenue",)
            ).candidates,
        ),
        ResolutionSlot(
            slot_id="d0",
            role="dimension",
            phrase="cities",
            candidates=retriever.retrieve(
                role="dimension", phrase="cities"
            ).candidates,
        ),
    )


@pytest.mark.asyncio
async def test_one_call_resolves_all_slots_from_existing_candidates():
    provider = _ResolverProvider({
        "measure": "measure:Sales:Total Sales",
        "dimension": "field:Geography:City",
    })
    result = await BoundedSemanticResolver(provider).resolve(
        catalog(), "sales by city", slots()
    )

    assert provider.calls == 1
    assert result.method == "bounded_semantic_resolution"
    assert result.decisions["m0"].candidate_id == "measure:Sales:Total Sales"
    assert result.decisions["d0"].candidate_id == "field:Geography:City"
    assert len(provider.payloads[0]["slots"]) == 2


@pytest.mark.asyncio
async def test_proposal_cannot_escape_the_slot_candidate_set():
    strict_catalog = catalog()
    strict_slots = (
        ResolutionSlot(
            slot_id="m0",
            role="measure",
            phrase="sales",
            candidates=(strict_catalog.get("measure:Sales:Total Sales"),),
        ),
        ResolutionSlot(
            slot_id="d0",
            role="dimension",
            phrase="cities",
            candidates=(strict_catalog.get("field:Geography:City"),),
        ),
    )
    provider = _ResolverProvider({
        "measure": "measure:Sales:Total Quantity",
        "dimension": "field:Product:Product",
    })
    result = await BoundedSemanticResolver(provider).resolve(
        strict_catalog, "sales by city", strict_slots
    )

    # Both returned IDs exist in the catalog but are not in the corresponding
    # slot candidate sets; deterministic verification rejects them.
    assert result.decisions["m0"].outcome == "UNRESOLVED"
    assert result.decisions["d0"].outcome == "UNRESOLVED"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_missing_or_duplicate_decisions_fail_closed():
    class Missing(LLMProvider):
        provider_name = "missing"
        is_mock = False

        async def generate(self, request, output_type):
            return LLMResponse(
                content="{}",
                structured=ResolutionResponse(decisions=()),
                model="missing",
            )

    result = await BoundedSemanticResolver(Missing()).resolve(
        catalog(), "sales by city", slots()
    )
    assert all(
        decision.outcome == "UNRESOLVED"
        for decision in result.decisions.values()
    )
