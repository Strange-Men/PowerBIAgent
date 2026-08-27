"""Static checks owned by the permanent Semantic Compatibility Gate."""

from scripts.check_semantic_compatibility import collect_static_violations


def test_no_benchmark_answer_or_provider_authority_leakage():
    assert collect_static_violations() == []
