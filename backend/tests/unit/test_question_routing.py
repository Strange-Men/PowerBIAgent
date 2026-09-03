"""M5.8.2 question routing and query-shape regression contract."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.application.mock_turn_service import MockTurnService
from backend.app.harness.models import HarnessConfig
from backend.app.intent.question_router import (
    CalculatorError,
    QuestionRoute,
    QuestionRouter,
    QueryShape,
    SafeCalculator,
)
from backend.app.memory.models import PendingClarificationContext, RuntimeDataMode


@pytest.mark.parametrize(
    ("question", "route", "shape"),
    [
        ("平均订单金额是多少", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.SCALAR),
        ("总订单数是多少", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.SCALAR),
        ("我们销售了哪些产品？", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.ENTITY_LIST),
        ("哪些产品卖的最好？", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.RANKING),
        ("销量最高的是哪款产品？", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.RANKING),
        ("手机和笔记本的销量分别是多少？", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.MEMBER_SET),
        ("手机和电脑加起来销量是多少", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.FILTERED_AGGREGATION),
        ("每个产品销量", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.GROUPED),
        ("过去12个月销售额趋势", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.TREND),
        ("2025年8月到2026年1月销售额月趋势", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.BOUNDED_TREND),
        ("从2025年8月至2026年1月按月看销售额", QuestionRoute.BUSINESS_DATA_QUERY, QueryShape.BOUNDED_TREND),
        ("生成报表", QuestionRoute.REPORT_REQUEST, None),
        ("数据分析支持的范围在哪", QuestionRoute.PRODUCT_HELP, None),
        ("你支持回答哪些问题？", QuestionRoute.PRODUCT_HELP, None),
        ("你是什么模型", QuestionRoute.SYSTEM_INFO, None),
        ("我是谁", QuestionRoute.UNSUPPORTED_GENERAL, None),
        ("给我讲个笑话", QuestionRoute.UNSUPPORTED_GENERAL, None),
        ("今天天气怎么样", QuestionRoute.UNSUPPORTED_GENERAL, None),
        ("1+1等于几", QuestionRoute.DETERMINISTIC_CALC, None),
        ("50乘50是几", QuestionRoute.DETERMINISTIC_CALC, None),
    ],
)
def test_router_classifies_capability_before_semantic_grounding(
    question: str,
    route: QuestionRoute,
    shape: QueryShape | None,
):
    decision = QuestionRouter().route(question)

    assert decision.route == route
    assert decision.query_shape == shape


@pytest.mark.parametrize(
    ("question", "shape"),
    [
        ("平均分是多少", QueryShape.SCALAR),
        ("有哪些课程", QueryShape.ENTITY_LIST),
        ("各课程平均分", QueryShape.GROUPED),
        ("平均分最高的是哪个学生", QueryShape.RANKING),
        ("各仓库当前库存", QueryShape.GROUPED),
        ("库存最低的是哪个仓库", QueryShape.RANKING),
        ("哪个枢纽最准时", QueryShape.RANKING),
        ("哪个承运商延误最严重", QueryShape.RANKING),
        ("有哪些节点", QueryShape.ENTITY_LIST),
        ("东校区和西校区的学生数量分别是多少", QueryShape.MEMBER_SET),
        ("过去12个月出勤率趋势", QueryShape.TREND),
        ("甲仓和乙仓的当前库存分别是多少", QueryShape.MEMBER_SET),
        ("过去6个月当前库存趋势", QueryShape.TREND),
    ],
)
def test_query_shape_grammar_is_cross_domain(question: str, shape: QueryShape):
    decision = QuestionRouter().route(question)

    assert decision.route == QuestionRoute.BUSINESS_DATA_QUERY
    assert decision.query_shape == shape


@pytest.mark.parametrize("question", ["换成销量", "只看华南", "那继续呢"])
def test_slot_only_followups_inherit_committed_query_shape(question: str):
    decision = QuestionRouter().route(question)

    assert decision.route == QuestionRoute.BUSINESS_DATA_QUERY
    assert decision.query_shape is None


def test_explicit_grouping_in_followup_overrides_inherited_shape():
    decision = QuestionRouter().route("那各地区呢")

    assert decision.query_shape == QueryShape.GROUPED


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1+1等于几", Decimal("2")),
        ("50乘50是几", Decimal("2500")),
        ("(2 + 3.5) × 4", Decimal("22.0")),
        ("10 ÷ 4", Decimal("2.5")),
        ("-2 + 5", Decimal("3")),
    ],
)
def test_safe_calculator_supports_only_bounded_arithmetic(expression: str, expected: Decimal):
    assert SafeCalculator().calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "1 / 0",
        "2 ** 8",
        "__import__('os').system('whoami')",
        "x + 1",
        "1" + "+1" * 100,
        "(" * 12 + "1" + ")" * 12,
        "999999999999999999999999 * 999999999999999999999999",
    ],
)
def test_safe_calculator_rejects_unsafe_or_unbounded_input(expression: str):
    with pytest.raises(CalculatorError):
        SafeCalculator().calculate(expression)


def test_code_owned_product_help_and_public_system_info_are_bounded():
    router = QuestionRouter()
    help_decision = router.route("你支持回答哪些问题？")
    system_decision = router.route("你是什么模型", public_model_name="Kimi K2.6")

    assert "指标查询" in (help_decision.direct_answer or "")
    assert "不预测" in (help_decision.direct_answer or "")
    assert system_decision.direct_answer == "当前使用的模型是 Kimi K2.6。"
    assert "http" not in system_decision.direct_answer
    assert "key" not in system_decision.direct_answer.casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "expected_type", "answer_fragment"),
    [
        ("你支持回答哪些问题？", "answer", "指标查询"),
        ("数据分析支持的范围在哪", "answer", "只读"),
        ("你是什么模型", "answer", "Mock"),
        ("1+1等于几", "answer", "2"),
        ("50乘50是几", "answer", "2500"),
        ("我是谁", "unsupported", "无法判断"),
    ],
)
async def test_shared_pipeline_short_circuits_non_business_without_semantic_mutation(
    question: str,
    expected_type: str,
    answer_fragment: str,
):
    service = MockTurnService(config=HarnessConfig(is_mock=True))

    result = await service.execute(question)

    text = result.get("answer") or result.get("unsupported_reason") or ""
    assert result["response_type"] == expected_type
    assert answer_fragment in text
    assert result["memory_commit"] is False
    assert result["tool_sequence"] == []
    assert result["execution_audit"]["schema_read"] is False
    assert result["execution_audit"]["dax_executed"] is False
    assert await service.pipeline.get_latest_committed_memory(
        result["conversation_id"],
        RuntimeDataMode.MOCK,
    ) is None


@pytest.mark.asyncio
async def test_non_business_turn_preserves_existing_pending_semantic_context():
    service = MockTurnService(config=HarnessConfig(is_mock=True))
    pending = PendingClarificationContext(
        conversation_id="pending-preserved",
        semantic_model_key="mock_sales_model",
        schema_fingerprint="a" * 64,
        intent="data_question",
        missing_slots=["measure"],
        last_request_id="previous-request",
    )
    await service.pipeline.save_pending_clarification(
        pending, RuntimeDataMode.MOCK
    )

    result = await service.execute(
        "你支持回答哪些问题？",
        conversation_id="pending-preserved",
    )

    retained = await service.pipeline.get_pending_clarification(
        "pending-preserved", RuntimeDataMode.MOCK
    )
    assert result["memory_commit"] is False
    assert retained is not None
    assert retained.chain_id == pending.chain_id
