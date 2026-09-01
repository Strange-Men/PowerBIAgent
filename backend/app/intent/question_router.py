"""Code-owned capability routing and bounded query-shape classification.

The router decides only which product capability should receive a question.
It deliberately does not resolve semantic-model objects or business facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from enum import Enum

from backend.app.schemas.data_contracts import QueryShape


class QuestionRoute(str, Enum):
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
    """Classify capability and generic query shape before semantic grounding."""

    _REPORT = re.compile(
        r"(?:生成|创建|制作|导出).{0,8}(?:报表|报告|周报|月报|季报|年报)|"
        r"(?:报表|报告|周报|月报|季报|年报).{0,8}(?:生成|创建|制作)|"
        r"\b(?:generate|create|make|export)\b.{0,60}\breport\b", re.IGNORECASE,
    )
    _HELP = re.compile(
        r"(?:支持|能够|能做|可以做|可做).{0,10}(?:哪些|什么|范围|分析|问题)|"
        r"(?:哪些|什么).{0,8}(?:问题|分析).{0,5}(?:支持|能回答|可以问)|"
        r"(?:数据分析).{0,8}(?:范围|支持)|我可以怎么问"
    )
    _SYSTEM = re.compile(r"(?:你|当前|现在).{0,5}(?:是|使用|用的).{0,4}(?:什么|哪个|哪种)?.{0,3}模型")
    _GENERAL = re.compile(
        r"^(?:我是谁|你知道我是谁吗|今天天气(?:怎么样|如何)?|"
        r"(?:给我)?讲个笑话|(?:帮我)?写(?:一首)?诗|陪我聊天)[？?。.]?$"
    )
    _RANKING = re.compile(
        r"(?:最高|最低|最大|最小|最多|最少|最好|最差|卖得最好|卖的最好)|"
        r"(?:前|后|top)\s*\d+|\b(?:highest|lowest|most|least|best|worst)\b",
        re.IGNORECASE,
    )
    _TREND = re.compile(r"趋势|走势|变化|按月看|按年看|逐月|逐年|\b(?:trend|monthly|yearly)\b", re.IGNORECASE)
    _ABSOLUTE_MONTH = re.compile(r"(?:\d{4}年\d{1,2}月|\d{4}[-/]\d{1,2})")
    _ENTITY_LIST = re.compile(
        r"(?:有|包含|包括|销售了|提供)(?:哪些|什么)|"
        r"(?:哪些|什么).{0,8}(?:有|可选)|"
        r"(?:列出|展示|显示).{0,3}(?:所有|全部)?|\blist\s+(?:all|the)\b", re.IGNORECASE,
    )
    _GROUPED = re.compile(
        r"(?:^|那|那么)(?:各|每个|每位|每种|每款|每家|各个)|"
        # Runtime canonical/qualified identifiers can be longer than ten
        # characters. This bounded span only classifies shape; Grounding must
        # still prove every requested object against the current model.
        r"(?:按|分)[^\n。！？!?]{1,200}(?:看|统计|汇总|比较)|"
        r"分别.{0,8}(?:的)?(?:情况|数据)?$|\b(?:by|per)\s+[^\n。！？!?]{1,200}", re.IGNORECASE,
    )
    _MEMBER_SET = re.compile(r"分别(?:是|为|有|多少)|各自(?:是|为|有|多少)|\brespectively\b", re.IGNORECASE)
    _FILTERED_AGGREGATION = re.compile(r"加起来|合起来|合计|总共|\bcombined\b", re.IGNORECASE)
    _INHERIT_SHAPE = re.compile(
        r"^\s*(?:那|那么|只看|再看|继续|然后|改成|改为|换成|换为|"
        r"调整为|改看|换看|改|换)"
    )

    def route(
        self,
        question: str,
        *,
        public_model_name: str | None = None,
    ) -> QuestionRoutingDecision:
        text = question.strip()
        if self._REPORT.search(text):
            return QuestionRoutingDecision(QuestionRoute.REPORT_REQUEST)
        if self._HELP.search(text):
            return QuestionRoutingDecision(
                QuestionRoute.PRODUCT_HELP,
                direct_answer=PRODUCT_HELP_ANSWER,
            )
        if self._SYSTEM.search(text):
            display_name = (public_model_name or "当前已选择的公开模型").strip()
            return QuestionRoutingDecision(
                QuestionRoute.SYSTEM_INFO,
                direct_answer=f"当前使用的模型是 {display_name}。",
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
        if self._GENERAL.fullmatch(text):
            return QuestionRoutingDecision(
                QuestionRoute.UNSUPPORTED_GENERAL,
                direct_answer=(
                    "我无法判断你的现实身份。"
                    if "我是谁" in text
                    else "该问题不属于当前只读 Power BI 数据分析能力范围。"
                ),
            )
        return QuestionRoutingDecision(
            QuestionRoute.BUSINESS_DATA_QUERY,
            query_shape=self._query_shape(text),
        )

    @staticmethod
    def _is_calculator(text: str) -> bool:
        normalized = SafeCalculator._extract_expression(text)
        if not normalized or not re.search(r"[+\-*/×÷乘除]", text):
            return False
        return re.fullmatch(r"[\d.()+\-*/\s]+", normalized) is not None

    def _query_shape(self, text: str) -> QueryShape | None:
        if self._TREND.search(text):
            if len(self._ABSOLUTE_MONTH.findall(text)) >= 2:
                return QueryShape.BOUNDED_TREND
            return QueryShape.TREND
        if self._RANKING.search(text):
            return QueryShape.RANKING
        if self._FILTERED_AGGREGATION.search(text) and re.search(
            r"加起来|合起来|和|与|及|、|\b(?:combined|and)\b", text, re.IGNORECASE,
        ):
            return QueryShape.FILTERED_AGGREGATION
        if self._MEMBER_SET.search(text):
            return QueryShape.MEMBER_SET
        if self._ENTITY_LIST.search(text):
            return QueryShape.ENTITY_LIST
        if self._GROUPED.search(text):
            return QueryShape.GROUPED
        if self._INHERIT_SHAPE.search(text):
            return None
        return QueryShape.SCALAR

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        if value == value.to_integral():
            return str(value.quantize(Decimal("1")))
        return format(value.normalize(), "f")
