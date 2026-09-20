"""Code-owned capability routing and bounded query-shape classification.

The router decides only which product capability should receive a question.
It deliberately does not resolve semantic-model objects or business facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, DivisionByZero, InvalidOperation
from enum import Enum
from typing import Callable
from zoneinfo import ZoneInfo

from backend.app.intent.temporal_expression import has_explicit_month_range
from backend.app.intent.unsupported_policy import CapabilityClass, classify_capability
from backend.app.schemas.data_contracts import QueryShape


class QuestionRoute(str, Enum):
    LLM_SEMANTIC_INTERPRETATION = "llm_semantic_interpretation"
    SOCIAL_CONVERSATION = "social_conversation"
    SYSTEM_DATETIME = "system_datetime"
    CONCEPT_EXPLANATION = "concept_explanation"
    BUSINESS_DATA_QUERY = "business_data_query"
    REPORT_REQUEST = "report_request"
    PRODUCT_HELP = "product_help"
    SYSTEM_INFO = "system_info"
    DETERMINISTIC_CALC = "deterministic_calc"
    UNSUPPORTED_GENERAL = "unsupported_general"


class CalculatorError(ValueError):
    """The expression is not inside the bounded calculator contract."""


@dataclass(frozen=True)
class QuestionRoutingDecision:
    route: QuestionRoute
    query_shape: QueryShape | None = None
    direct_answer: str | None = None


PRODUCT_HELP_ANSWER = (
    "我支持只读的 Power BI 数据分析，包括指标查询、分类或分组比较、TopN 排名、"
    "时间趋势、成员筛选、多轮 KEEP/REPLACE，以及使用已选择的固定模板生成报表。"
    "你可以直接描述指标、维度、筛选条件和时间范围。当前不预测、不写回、不删除 "
    "Power BI 数据，也不执行任意用户 DAX。"
)


class SafeCalculator:
    """A tiny recursive-descent Decimal calculator with explicit limits."""

    MAX_INPUT_LENGTH = 64
    MAX_NESTING = 8
    MAX_ABS_VALUE = Decimal("1e18")
    _TOKEN = re.compile(r"\d+(?:\.\d+)?|[()+\-*/]")

    def calculate(self, text: str) -> Decimal:
        expression = self._extract_expression(text)
        if not expression or len(expression) > self.MAX_INPUT_LENGTH:
            raise CalculatorError("calculator_input_out_of_bounds")
        tokens = self._TOKEN.findall(expression)
        if "".join(tokens) != expression:
            raise CalculatorError("calculator_invalid_token")
        self._tokens = tokens
        self._position = 0
        try:
            value = self._parse_expression(0)
        except (DivisionByZero, InvalidOperation, OverflowError) as exc:
            raise CalculatorError("calculator_invalid_operation") from exc
        if self._position != len(tokens):
            raise CalculatorError("calculator_invalid_expression")
        return self._bounded(value)

    @staticmethod
    def _extract_expression(text: str) -> str:
        normalized = (
            text.strip()
            .replace("×", "*")
            .replace("乘以", "*")
            .replace("乘", "*")
            .replace("÷", "/")
            .replace("除以", "/")
            .replace("除", "/")
            .replace("＋", "+")
            .replace("－", "-")
            .replace("（", "(")
            .replace("）", ")")
        )
        normalized = re.sub(r"(?:等于多少|等于几|是多少|是几)[？?]?\s*$", "", normalized)
        return re.sub(r"\s+", "", normalized)

    def _parse_expression(self, depth: int) -> Decimal:
        value = self._parse_term(depth)
        while self._peek() in {"+", "-"}:
            operator = self._take()
            right = self._parse_term(depth)
            value = self._bounded(value + right if operator == "+" else value - right)
        return value

    def _parse_term(self, depth: int) -> Decimal:
        value = self._parse_factor(depth)
        while self._peek() in {"*", "/"}:
            operator = self._take()
            right = self._parse_factor(depth)
            if operator == "/" and right == 0:
                raise CalculatorError("calculator_division_by_zero")
            value = self._bounded(value * right if operator == "*" else value / right)
        return value

    def _parse_factor(self, depth: int) -> Decimal:
        token = self._peek()
        if token in {"+", "-"}:
            operator = self._take()
            value = self._parse_factor(depth)
            return value if operator == "+" else self._bounded(-value)
        if token == "(":
            if depth >= self.MAX_NESTING:
                raise CalculatorError("calculator_nesting_out_of_bounds")
            self._take()
            value = self._parse_expression(depth + 1)
            if self._take() != ")":
                raise CalculatorError("calculator_unbalanced_parentheses")
            return value
        if token is None or token == ")":
            raise CalculatorError("calculator_operand_required")
        self._take()
        try:
            return self._bounded(Decimal(token))
        except InvalidOperation as exc:
            raise CalculatorError("calculator_invalid_number") from exc

    def _peek(self) -> str | None:
        if self._position >= len(self._tokens):
            return None
        return self._tokens[self._position]

    def _take(self) -> str | None:
        token = self._peek()
        if token is not None:
            self._position += 1
        return token

    def _bounded(self, value: Decimal) -> Decimal:
        if not value.is_finite() or abs(value) > self.MAX_ABS_VALUE:
            raise CalculatorError("calculator_numeric_magnitude_out_of_bounds")
        return value


class QuestionRouter:
    """Deterministic capability/safety preflight; never interprets business language."""

    _REPORT_VERB = re.compile(
        r"(?:生成|创建|制作|导出|出一份|给我一份)|"
        r"\b(?:generate|create|make|export|give\s+me)\b",
        re.IGNORECASE,
    )
    _REPORT_NOUN = re.compile(
        r"(?:报表|报告|周报|月报|季报|年报)|\breport\b",
        re.IGNORECASE,
    )
    _HELP = re.compile(
        r"(?:支持|能够|能做|可以做|可做).{0,10}(?:哪些|什么|范围|分析|问题)|"
        r"(?:哪些|什么).{0,8}(?:问题|分析).{0,5}(?:支持|能回答|可以问)|"
        r"(?:数据分析).{0,8}(?:范围|支持)|我可以怎么问"
    )
    _SYSTEM = re.compile(r"(?:你|当前|现在).{0,5}(?:是|使用|用的).{0,4}(?:什么|哪个|哪种)?.{0,3}模型")
    _FOLLOW_ON_DATA_REQUEST = re.compile(
        r"(?:顺便|再|然后|同时|另外|并且?|还|[，,；;。]\s*).{0,80}"
        r"(?:看|查|查询|分析|统计|比较|多少|哪些|谁|趋势|排名)",
        re.IGNORECASE,
    )
    _UNSUPPORTED_EXTERNAL = re.compile(
        r"^(?:(?:今天|现在|当前|实时).{0,8}(?:天气|气温|股票|股价|新闻)"
        r".{0,8}(?:怎么样|如何|多少|是什么)?|"
        r"(?:天气|气温|股票|股价|新闻).{0,8}(?:怎么样|如何|多少|是什么))[？?。.!\s]*$",
        re.IGNORECASE,
    )
    _UNSUPPORTED_IDENTITY = re.compile(
        r"^(?:我是谁|你知道我是谁吗)[？?。.!\s]*$",
        re.IGNORECASE,
    )
    _CURRENT_DATE = re.compile(
        r"^(?:今天(?:是)?(?:几号|几日|什么日期|星期几)|当前日期(?:是什(?:么|麼))?|"
        r"what(?:'s|\s+is)\s+(?:today(?:'s)?\s+date|the\s+date\s+today))[？?。.!\s]*$",
        re.IGNORECASE,
    )
    _CURRENT_TIME = re.compile(
        r"^(?:现在(?:是)?几点(?:钟)?|当前时间(?:是什(?:么|麼))?|"
        r"what\s+time\s+is\s+it)[？?。.!\s]*$",
        re.IGNORECASE,
    )

    _WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

    def __init__(
        self,
        *,
        application_timezone: str = "Asia/Shanghai",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._timezone_name = application_timezone
        self._timezone = ZoneInfo(application_timezone)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def route(
        self,
        question: str,
        *,
        public_model_name: str | None = None,
    ) -> QuestionRoutingDecision:
        text = question.strip()
        capability = classify_capability(text)
        if capability in {
            CapabilityClass.FUTURE_PREDICTION,
            CapabilityClass.MODEL_WRITE,
            CapabilityClass.DATA_DELETE,
            CapabilityClass.ARBITRARY_CODE,
        }:
            return QuestionRoutingDecision(
                QuestionRoute.UNSUPPORTED_GENERAL,
                direct_answer=(
                    "当前为只读分析模式，不支持预测、修改、删除、写入模型"
                    "或执行任意代码。"
                ),
            )
        if self._has_report_generation_evidence(text):
            return QuestionRoutingDecision(QuestionRoute.REPORT_REQUEST)
        if self._HELP.search(text) and not self._FOLLOW_ON_DATA_REQUEST.search(text):
            return QuestionRoutingDecision(
                QuestionRoute.PRODUCT_HELP,
                direct_answer=PRODUCT_HELP_ANSWER,
            )
        if (
            self._SYSTEM.search(text)
            and not self._FOLLOW_ON_DATA_REQUEST.search(text)
        ):
            display_name = (public_model_name or "当前已选择的公开模型").strip()
            return QuestionRoutingDecision(
                QuestionRoute.SYSTEM_INFO,
                direct_answer=f"当前使用的模型是 {display_name}。",
            )
        if self._CURRENT_DATE.fullmatch(text):
            return QuestionRoutingDecision(
                QuestionRoute.SYSTEM_DATETIME,
                direct_answer=self._current_date_answer(),
            )
        if self._CURRENT_TIME.fullmatch(text):
            return QuestionRoutingDecision(
                QuestionRoute.SYSTEM_DATETIME,
                direct_answer=self._current_time_answer(),
            )
        if self._is_calculator(text):
            try:
                value = SafeCalculator().calculate(text)
                answer = f"计算结果是 {self._format_decimal(value)}。"
            except CalculatorError:
                answer = "该算式超出安全基础计算范围，请检查除零、长度、括号或数值大小。"
            return QuestionRoutingDecision(
                QuestionRoute.DETERMINISTIC_CALC,
                direct_answer=answer,
            )
        if (
            self._UNSUPPORTED_EXTERNAL.fullmatch(text)
            and not self._FOLLOW_ON_DATA_REQUEST.search(text)
        ):
            return QuestionRoutingDecision(
                QuestionRoute.UNSUPPORTED_GENERAL,
                direct_answer="当前没有可验证的实时外部信息来源，无法回答该问题。",
            )
        if self._UNSUPPORTED_IDENTITY.fullmatch(text):
            return QuestionRoutingDecision(
                QuestionRoute.UNSUPPORTED_GENERAL,
                direct_answer="我无法判断你的现实身份。",
            )
        # All remaining open language is interpreted once by SemanticFrame.
        return QuestionRoutingDecision(
            QuestionRoute.LLM_SEMANTIC_INTERPRETATION,
        )

    @classmethod
    def _has_report_generation_evidence(cls, text: str) -> bool:
        """Require a generation action and report noun in one bounded clause."""
        for clause in re.split(r"[\n。！？!?；;]", text):
            normalized = clause.strip()
            if not normalized or len(normalized) > 160:
                continue
            if cls._REPORT_VERB.search(normalized) and cls._REPORT_NOUN.search(
                normalized
            ):
                return True
        return False

    @staticmethod
    def _is_calculator(text: str) -> bool:
        normalized = SafeCalculator._extract_expression(text)
        if not normalized or not re.search(r"[+\-*/×÷乘除]", text):
            return False
        return re.fullmatch(r"[\d.()+\-*/\s]+", normalized) is not None

    def _application_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(self._timezone)

    def _current_date_answer(self) -> str:
        current = self._application_now()
        return (
            f"今天是{current.year}年{current.month}月{current.day}日，"
            f"{self._WEEKDAYS[current.weekday()]}（{self._timezone_name}）。"
        )

    def _current_time_answer(self) -> str:
        current = self._application_now()
        return (
            f"现在是{current.year}年{current.month}月{current.day}日 "
            f"{current:%H:%M}（{self._timezone_name}）。"
        )

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        if value == value.to_integral():
            return str(value.quantize(Decimal("1")))
        return format(value.normalize(), "f")
