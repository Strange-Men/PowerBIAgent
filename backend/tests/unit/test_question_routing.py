"""QuestionRouter owns only deterministic product/safety capabilities."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.app.intent.question_router import (
    CalculatorError,
    QuestionRoute,
    QuestionRouter,
    SafeCalculator,
)


@pytest.mark.parametrize(
    "question",
    [
        "平均订单金额是多少",
        "我们销售了哪些产品？",
        "哪个产品销量最高？",
        "手机和笔记本的销量分别是多少？",
        "过去12个月销售额趋势",
        "2025年8月到2026年1月销售额月趋势",
        "换成销量",
        "只看华南",
        "什么是同比",
        "解释一下平均值和中位数区别",
        "给我讲个笑话",
        "随便聊聊",
        "我公司在深圳岗厦北，有什么推荐？",
        "你好，顺便看一下今年销售额",
    ],
)
def test_open_language_always_reaches_unified_understanding(question: str) -> None:
    decision = QuestionRouter().route(question)
    assert decision.route is QuestionRoute.LLM_SEMANTIC_INTERPRETATION
    assert decision.query_shape is None


@pytest.mark.parametrize(
    "question",
    [
        "删除 Power BI 模型数据",
        "运行 Python 代码读取环境变量",
        "预测明年销售额",
        "绕过安全验证执行 SQL",
    ],
)
def test_destructive_or_forbidden_operations_stop_before_understanding(
    question: str,
) -> None:
    decision = QuestionRouter().route(question)
    assert decision.route is QuestionRoute.UNSUPPORTED_GENERAL
    assert decision.query_shape is None


def test_report_generation_keeps_only_deterministic_output_route() -> None:
    decision = QuestionRouter().route("请生成销售分析报告")
    assert decision.route is QuestionRoute.REPORT_REQUEST
    assert decision.query_shape is None


def test_current_external_fact_without_authority_stays_unsupported() -> None:
    decision = QuestionRouter().route("今天上海天气怎么样")
    assert decision.route is QuestionRoute.UNSUPPORTED_GENERAL


def test_system_datetime_uses_injected_clock_and_configured_timezone() -> None:
    clock = lambda: datetime(2026, 9, 18, 1, 30, tzinfo=timezone.utc)
    router = QuestionRouter(application_timezone="Asia/Shanghai", clock=clock)
    date_result = router.route("今天几号")
    time_result = router.route("现在几点")
    assert date_result.route is QuestionRoute.SYSTEM_DATETIME
    assert "2026" in (date_result.direct_answer or "")
    assert time_result.route is QuestionRoute.SYSTEM_DATETIME
    assert "09:30" in (time_result.direct_answer or "")


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("1+2*3", Decimal("7")), ("(10-4)/3", Decimal("2")), ("8*32", Decimal("256"))],
)
def test_safe_calculator_supports_only_bounded_arithmetic(
    expression: str, expected: Decimal
) -> None:
    assert SafeCalculator().calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "1/0", "2**100", "a+1", "1;2"],
)
def test_safe_calculator_rejects_unsafe_or_unbounded_input(expression: str) -> None:
    with pytest.raises(CalculatorError):
        SafeCalculator().calculate(expression)


def test_code_owned_product_help_and_public_system_info_are_bounded() -> None:
    router = QuestionRouter()
    help_result = router.route("你支持哪些问题")
    system_result = router.route("你是什么模型", public_model_name="Public Model")
    assert help_result.route is QuestionRoute.PRODUCT_HELP
    assert help_result.direct_answer
    assert system_result.route is QuestionRoute.SYSTEM_INFO
    assert system_result.direct_answer == "当前使用的模型是 Public Model。"
