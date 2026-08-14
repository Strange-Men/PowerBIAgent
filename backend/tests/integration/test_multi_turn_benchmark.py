"""Offline API-first verification of the formal Real multi-turn benchmark."""

from pathlib import Path

import pytest

from backend.app.harness.cases.multi_turn_runner import (
    ConversationEvaluation,
    MultiTurnBenchmarkRunner,
    TurnEvaluation,
)
from backend.app.harness.cases.benchmark_models import KnownAnswerCaseSpec
from backend.app.harness.cases.production_e2e_runner import (
    _strict_rank_claim_absent,
    _topn_boundary_tie_observed,
    exact_known_answer_schedule,
)
from backend.app.query_plan import prompt as query_plan_prompt
from backend.app.schemas.data_contracts import QueryResult


@pytest.fixture(scope="module")
def benchmark_summary():
    import asyncio

    return asyncio.run(MultiTurnBenchmarkRunner().run_offline())


def _conversation(summary, conversation_id: str) -> ConversationEvaluation:
    return next(
        item for item in summary.conversations if item.conversation_id == conversation_id
    )


def test_six_conversations_and_sixteen_turns_pass_offline(benchmark_summary):
    assert benchmark_summary.passed
    assert benchmark_summary.conversations_defined == 6
    assert benchmark_summary.conversations_passed == 6
    assert benchmark_summary.turns_defined == 16
    assert benchmark_summary.turns_passed == 16
    assert benchmark_summary.deepseek_real_calls == 0
    assert benchmark_summary.local_mcp_real_calls == 0


@pytest.mark.parametrize(
    ("conversation_id", "required_turn", "required_checks"),
    [
        ("conversation_a_filter_refinement", "a3", {"query_plan_filters", "inheritance"}),
        ("conversation_b_dimension_switch_topn", "b3", {"query_plan_dimensions", "query_plan_sort_top_n"}),
        ("conversation_c_filter_replacement", "c2", {"query_plan_filters", "inheritance"}),
        ("conversation_d_metric_switch", "d2", {"query_plan_measure", "inheritance"}),
        ("conversation_e_clarification", "e1", {"no_powerbi_execute", "no_memory_record"}),
        ("conversation_f_failure_memory_integrity", "f2", {"failed_memory_record", "last_committed_unchanged"}),
    ],
)
def test_each_interaction_pattern_is_verified(
    benchmark_summary, conversation_id, required_turn, required_checks
):
    conversation = _conversation(benchmark_summary, conversation_id)
    turn = next(item for item in conversation.turns if item.turn_id == required_turn)
    assert conversation.passed
    assert required_checks.issubset(turn.checks)
    assert all(turn.checks[name] for name in required_checks)


def test_follow_up_after_failed_turn_inherits_last_successful_state(benchmark_summary):
    conversation = _conversation(
        benchmark_summary, "conversation_f_failure_memory_integrity"
    )
    final_turn = next(item for item in conversation.turns if item.turn_id == "f3")
    assert final_turn.passed
    assert final_turn.checks["inheritance"]
    assert final_turn.checks["memory_committed"]


def test_clarification_contract_requires_both_partial_turns_before_execution(
    benchmark_summary,
):
    conversation = _conversation(
        benchmark_summary, "conversation_e_clarification"
    )
    by_id = {turn.turn_id: turn for turn in conversation.turns}
    assert conversation.passed
    assert by_id["e1"].checks["no_powerbi_execute"]
    assert by_id["e1"].checks["no_memory_record"]
    assert by_id["e2"].checks["no_powerbi_execute"]
    assert by_id["e2"].checks["no_memory_record"]
    assert by_id["e3"].checks["query_plan_measure"]
    assert by_id["e3"].checks["query_plan_dimensions"]
    assert by_id["e3"].checks["query_plan_sort_top_n"]
    assert by_id["e3"].checks["memory_committed"]


def test_conversation_scoring_requires_every_turn_to_pass():
    passing = TurnEvaluation(turn_id="t1", passed=True)
    failing = TurnEvaluation(turn_id="t2", passed=False, mismatches=["oracle"])
    all_pass = MultiTurnBenchmarkRunner.score_conversation("all-pass", [passing])
    one_fail = MultiTurnBenchmarkRunner.score_conversation(
        "one-fail", [passing, failing]
    )
    assert all_pass.passed
    assert not one_fail.passed


def test_correct_clarification_cannot_hide_later_failure():
    clarification = TurnEvaluation(
        turn_id="clarification", passed=True, checks={"no_powerbi_execute": True}
    )
    later_failure = TurnEvaluation(
        turn_id="answer", passed=False, mismatches=["query_plan_dimensions"]
    )
    scored = MultiTurnBenchmarkRunner.score_conversation(
        "clarification-then-fail", [clarification, later_failure]
    )
    assert not scored.passed


def test_real_acceptance_tie_observer_is_value_blind_and_rank_safe():
    case = KnownAnswerCaseSpec(
        id="tie",
        message="top two",
        expected_measure="Total Sales",
        expected_dimensions=["Product"],
        expected_sort="desc",
        expected_top_n=2,
        oracle_key="top2",
    )
    tied = QueryResult(
        semantic_model_key="local_desktop_model",
        request_id="tie",
        source_mode="real",
        columns=["Product", "[Total Sales]"],
        rows=[["A", 100], ["B", 90], ["C", 90]],
        row_count=3,
    )

    assert _topn_boundary_tie_observed(tied, case)
    assert not _topn_boundary_tie_observed(
        tied.model_copy(update={"rows": tied.rows[:2], "row_count": 2}), case
    )
    assert _strict_rank_claim_absent("TopN结果顺序：结果第1项；结果第2项")
    assert not _strict_rank_claim_absent("A 第1位，B 第2位")


@pytest.mark.asyncio
async def test_oracle_failure_fails_turn_and_conversation(tmp_path: Path):
    wrong_baseline = tmp_path / "wrong.yaml"
    wrong_baseline.write_text(
        """baselines:
  - oracle_key: sales_by_category
    mode: grouped
    expected_columns: [Category, \"[Total Sales]\"]
    key_columns: [Category]
    metric_columns: [\"[Total Sales]\"]
    expected_rows:
      - {Category: Electronics, \"[Total Sales]\": 999999}
""",
        encoding="utf-8",
    )
    summary = await MultiTurnBenchmarkRunner(
        example_baseline_path=wrong_baseline
    ).run_offline()
    first = _conversation(summary, "conversation_a_filter_refinement").turns[0]
    assert not first.checks["oracle"]
    assert not first.passed
    assert not summary.passed


def test_eight_known_answer_cases_include_two_prompt_holdouts():
    cases = MultiTurnBenchmarkRunner().load_known_answer_cases()
    holdouts = [item for item in cases if item.holdout]
    assert len(cases) == 8
    assert len(holdouts) == 2
    for holdout in holdouts:
        assert holdout.message not in query_plan_prompt.SYSTEM_PROMPT


def test_real_known_answer_schedule_never_deduplicates_by_oracle_key():
    cases = [
        KnownAnswerCaseSpec(
            id="exact_prompt_a",
            message="第一个完整提示",
            expected_measure="Total Sales",
            oracle_key="shared_key",
        ),
        KnownAnswerCaseSpec(
            id="exact_prompt_b",
            message="第二个完整提示",
            expected_measure="Total Sales",
            oracle_key="shared_key",
        ),
    ]

    scheduled = exact_known_answer_schedule(cases)

    assert [item.id for item in scheduled] == ["exact_prompt_a", "exact_prompt_b"]
    assert [item.message for item in scheduled] == ["第一个完整提示", "第二个完整提示"]
