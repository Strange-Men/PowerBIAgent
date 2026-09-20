"""Cross-domain mutation stress for canonical completeness."""

import pytest

from backend.app.query_plan.completeness import (
    CanonicalShapeCompletenessError,
    CanonicalShapeCompletenessGate,
)
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryShape


DOMAINS = (
    ("retail", "Net Sales", "Product"),
    ("education", "Average Score", "School"),
    ("inventory", "Stock Balance", "Warehouse"),
    ("logistics", "Shipment Count", "Carrier"),
    ("unknown-holdout", "Metric X", "Entity X"),
)


@pytest.mark.parametrize(("domain", "measure", "dimension"), DOMAINS)
@pytest.mark.parametrize(("sort", "top_n"), [("asc", 1), ("desc", 3), ("desc", 100)])
def test_cross_domain_ranking_contract_is_domain_agnostic(
    domain: str,
    measure: str,
    dimension: str,
    sort: str,
    top_n: int,
) -> None:
    plan = CanonicalQueryPlan(
        normalized_question=domain,
        semantic_model_key=domain,
        query_shape=QueryShape.RANKING,
        measures=[measure],
        dimensions=[dimension],
        sort=sort,
        top_n=top_n,
    )
    assert CanonicalShapeCompletenessGate().validate(plan).complete


@pytest.mark.parametrize(("domain", "measure", "dimension"), DOMAINS)
@pytest.mark.parametrize("missing", ["measure", "dimension", "sort", "top_n"])
def test_cross_domain_ranking_slot_mutations_fail_closed(
    domain: str,
    measure: str,
    dimension: str,
    missing: str,
) -> None:
    values = {
        "normalized_question": domain,
        "semantic_model_key": domain,
        "query_shape": QueryShape.RANKING,
        "measures": [measure],
        "dimensions": [dimension],
        "sort": "desc",
        "top_n": 3,
    }
    values[{"measure": "measures", "dimension": "dimensions"}.get(missing, missing)] = (
        [] if missing in {"measure", "dimension"} else None
    )
    plan = CanonicalQueryPlan(**values)
    with pytest.raises(CanonicalShapeCompletenessError):
        CanonicalShapeCompletenessGate().validate(plan)
