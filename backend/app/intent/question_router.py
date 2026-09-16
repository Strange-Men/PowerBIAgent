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
from backend.app.schemas.data_contracts import QueryShape


class QuestionRoute(str, Enum):
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
    """Classify capability and generic query shape before semantic grounding."""

    _RANKING_NUMBER = r"(?:\d+|[零〇一二两三四五六七八九十百]+)"

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
        r"(?:看|查|查询|分析|统计|比较|多少|哪些|谁|趋势|排名|报表)",
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
    _RANKING = re.compile(
        r"(?:最高|最低|最大|最小|最多|最少|最好|最差|最准|最严重|最快|最慢|最早|最晚|卖得最好|卖的最好)|"
        r"(?:哪个|哪家|哪位|哪款|哪种|哪座|谁)[^\n。！？!?]{0,40}最(?:准|严重|快|慢|早|晚)|"
        rf"(?:前|后|top)\s*{_RANKING_NUMBER}|"
        r"前\s*几(?:个)?|第\s*(?:一|1)\s*个|"
        r"\b(?:highest|lowest|most|least|best|worst)\b",
        re.IGNORECASE,
    )
    _SOCIAL = re.compile(
        r"^(?:你好|您好|嗨|哈喽|早上好|上午好|下午好|晚上好|"
        r"谢谢|多谢|感谢|不客气|你怎么样|最近怎么样|你是谁|再见|拜拜|"
        r"随便聊聊|陪我聊(?:天|两句)|"
        r"(?:给我|帮我)?讲(?:一个|个)?(?:简短的?)?笑话|"
        r"(?:帮我)?写(?:一首|一句)?(?:四句|简短|轻松|短)?(?:的)?(?:小?诗|问候)|"
        r"(?:帮我)?解释(?:一下)?(?:一个)?普通概念|"
        r"hello|hi|hey|thanks|thank\s+you|goodbye|bye)[！!？?。.,，\s]*$",
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
    _CONCEPT = re.compile(
        r"^(?:什么是|解释(?:一下)?|介绍(?:一下)?)\s*"
        r"(?:同比|平均值|中位数|top\s*n)[？?。.!\s]*$|"
        r"^(?:同比|平均值|中位数|top\s*n)\s*(?:是什么|是什么意思|怎么理解)[？?。.!\s]*$|"
        r"^(?:解释(?:一下)?)?平均值和中位数(?:的)?区别[？?。.!\s]*$",
        re.IGNORECASE,
    )
    _TREND = re.compile(r"趋势|走势|变化|按月看|按年看|逐月|逐年|\b(?:trend|monthly|yearly)\b", re.IGNORECASE)
    _ABSOLUTE_MONTH = re.compile(r"(?:\d{4}年\d{1,2}月|\d{4}[-/]\d{1,2})")
    _ENTITY_LIST = re.compile(
        r"(?:有|包含|包括|销售了|提供)(?:哪些|什么)|"
        r"(?:哪些|什么).{0,8}(?:有|可选)|"
        r"(?:列出|展示|显示).{0,3}(?:所有|全部)?|(?<![A-Za-z0-9_])list\s+(?:all|the)\b", re.IGNORECASE,
    )
    _GROUPED = re.compile(
        r"(?:各|每个|每位|每种|每款|每家|各个)|"
        # Runtime canonical/qualified identifiers can be longer than ten
        # characters. This bounded span only classifies shape; Grounding must
        # still prove every requested object against the current model.
        r"(?:按|分(?!析))[^\n。！？!?]{1,200}(?:看|统计|汇总|比较)|"
        r"分别.{0,8}(?:的)?(?:情况|数据)?$|\b(?:by|per)\s+[^\n。！？!?]{1,200}", re.IGNORECASE,
    )
    _MEMBER_SET_WORDING = re.compile(
        r"分别(?:是|为|有|多少|统计|查询|看)|各自(?:的|是|为|有|多少)?|\brespectively\b",
        re.IGNORECASE,
    )
    _MEMBER_COORDINATOR = re.compile(r"和|与|及|、|\band\b", re.IGNORECASE)
    _FILTERED_AGGREGATION = re.compile(r"加起来|合起来|合计|总共|一起|\bcombined\b", re.IGNORECASE)
    _INHERIT_SHAPE = re.compile(
        r"^\s*(?:那|那么|其中|只看|再看|继续|然后|改成|改为|换成|换为|"
        r"调整为|改看|换看|改|换)"
    )
    _BOUNDED_TIME_ONLY = re.compile(
        r"^\s*(?:(?:最近|过去|近)\s*\d+\s*个?月|"
        r"(?:last|past)\s+\d+\s+months?|"
        r"(?:从\s*)?\d{1,2}\s*月(?:份)?\s*(?:至|到|[-—–~～])\s*"
        r"\d{1,2}\s*月(?:份)?)\s*[？?。.!]*\s*$",
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
        if self._has_report_generation_evidence(text):
            return QuestionRoutingDecision(QuestionRoute.REPORT_REQUEST)
        if (
            self._HELP.search(text)
            and not self._FOLLOW_ON_DATA_REQUEST.search(text)
        ):
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
        if self._SOCIAL.fullmatch(text):
            return QuestionRoutingDecision(
                QuestionRoute.SOCIAL_CONVERSATION,
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
        if self._CONCEPT.fullmatch(text):
            return QuestionRoutingDecision(
                QuestionRoute.CONCEPT_EXPLANATION,
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
        return QuestionRoutingDecision(
            QuestionRoute.BUSINESS_DATA_QUERY,
            query_shape=self._query_shape(text),
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

    def _query_shape(self, text: str) -> QueryShape | None:
        if self._BOUNDED_TIME_ONLY.fullmatch(text):
            return None
        if self._TREND.search(text):
            if has_explicit_month_range(text):
                return QueryShape.BOUNDED_TREND
            return QueryShape.TREND
        if self._RANKING.search(text):
            return QueryShape.RANKING
        if self._FILTERED_AGGREGATION.search(text) and re.search(
            r"加起来|合起来|一起|和|与|及|、|\b(?:combined|and)\b", text, re.IGNORECASE,
        ):
            return QueryShape.FILTERED_AGGREGATION
        if self._has_member_set_evidence(text):
            return QueryShape.MEMBER_SET
        if self._ENTITY_LIST.search(text):
            return QueryShape.ENTITY_LIST
        if self._GROUPED.search(text) or self._MEMBER_SET_WORDING.search(text):
            return QueryShape.GROUPED
        if self._INHERIT_SHAPE.search(text):
            return None
        return QueryShape.SCALAR

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

    @classmethod
    def _has_member_set_evidence(cls, text: str) -> bool:
        """Require coordinated literals; 'respectively' alone is not a set."""
        return bool(
            cls._MEMBER_SET_WORDING.search(text)
            and cls._MEMBER_COORDINATOR.search(text)
        )

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        if value == value.to_integral():
            return str(value.quantize(Decimal("1")))
        return format(value.normalize(), "f")
