"""Deterministic language cues shared by Understanding and Grounding.

These helpers only detect language structure (a ranking operator, a concrete
time expression, a reset phrase, or business-looking residual text).  They never
choose a canonical object, member, date field, metric family, or fact.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.app.intent.temporal_expression import (
    has_explicit_month_range,
    has_vague_recent_month_range,
)

_CHINESE_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
    "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_RANKING_NUMBER = r"(?:\d+|[零〇一二两三四五六七八九十百]+)"
_RANKING = re.compile(
    rf"(?:\btop\s*(?P<top>{_RANKING_NUMBER})\b|"
    rf"\bthe\s+top\s+(?P<top_words>{_RANKING_NUMBER})\b|"
    rf"哪\s*(?P<which>{_RANKING_NUMBER})\s*个?|"
    rf"前\s*(?P<front>{_RANKING_NUMBER})\s*个?|"
    r"第\s*(?P<ordinal>一|1)\s*个|"
    rf"(?:最高|最多|最大|最低|最少|最小|最好|最差|最挣钱|最赚钱|最盈利)"
    rf"(?:的)?\s*(?P<extreme>{_RANKING_NUMBER})\s*个?)",
    re.IGNORECASE,
)
_RANKING_WORD = re.compile(
    r"(?:\btop\b|\bhighest\b|\blowest\b|\bmost\b|\bleast\b|\bbest\b|"
    r"\bworst\b|\blargest\b|\bsmallest\b|\bbiggest\b|\bleading\b|"
    r"最高|最低|最多|最少|最大|最小|最好|最差|最挣钱|最赚钱|最盈利|领先|排)",
    re.IGNORECASE,
)
_RANKING_ASC = re.compile(
    r"(?:最低|最少|最小|最差|最低的|bottom|lowest|least|smallest|worst)",
    re.IGNORECASE,
)
_RANKING_DESC = re.compile(
    r"(?:最高|最多|最大|最好|最高的|最挣钱|最赚钱|最盈利|领先|排|"
    r"top|highest|most|largest|biggest|best|leading)",
    re.IGNORECASE,
)
_COUNT_WORD = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_COUNT_WORD_PATTERN = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)
_CN_COUNT_PATTERN = re.compile(
    r"([一二两三四五六七八九十]+)\s*(?:个|项|款|名)"
)
_RESET = re.compile(
    r"(?:新问题|重新开始|重新分析|换个问题|换一个话题|换个话题|另一个问题|"
    r"独立问题|单独问|忽略之前|忽略前面|不管之前|不使用之前|"
    r"从头开始|忘记之前|清空上下文|"
    r"\bnew\s+question\b|\breset\b|\bstart\s+over\b|\bforget\s+(?:the\s+)?"
    r"(?:previous|prior|last)\b|\banother\s+question\b)",
    re.IGNORECASE,
)

# Concrete temporal values or relative windows only.  Bare "year/month/quarter"
# words remain dimension language and must not force a time filter.
_TIME_VALUE = re.compile(
    r"(?<!\d)(?:19|20)\d{2}\s*年|"
    r"(?<!\d)(?:19|20)\d{2}\s*[-/]\s*(?:0?[1-9]|1[0-2])(?!\d)|"
    r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)|"
    r"(?:今年|去年|明年|前年)\s*(?:的)?\s*"
    r"(?:0?[1-9]|1[0-2]|[一二三四五六七八九十]+)\s*月|"
    r"(?:今年|去年|明年|前年)(?!\s*(?:的)?\s*[0-9一二三四五六七八九十]+月)|"
    r"(?:本月|这个月|当月|上个月|上月|下个月|下月)|"
    r"(?:最近|过去|近)\s*(?:\d+|[一二三四五六七八九十]+)\s*个?\s*月|"
    r"(?:最近|过去)\s*半年|"
    r"(?:上半年|下半年|前\s*6\s*个月|后\s*6\s*个月)|"
    r"(?:(?:19|20)\d{2}\s*年?|今年|去年)?\s*第?\s*[一二三四1-4]\s*季度|"
    r"\b(?:19|20)\d{2}\b|"
    r"\bQ[1-4]\b|\bH[12]\b|"
    r"\b(?:first|second)\s+half\b|"
    r"\b(?:last|past|next|this)\s+(?:\d+\s+)?(?:month|quarter|year|week)s?\b|"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\b(?:\s+(?:19|20)\d{2})?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RankingCue:
    direction: str
    top_n: int | None
    text: str


def parse_cn_integer(value: str) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value]
    if "十" in value:
        left, _, right = value.partition("十")
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        units = _CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + units
    if "百" in value:
        left, _, right = value.partition("百")
        hundreds = _CHINESE_DIGITS.get(left, 1) if left else 1
        remainder = parse_cn_integer(right) if right else 0
        return hundreds * 100 + (remainder or 0)
    return None


def extract_ranking_cue(text: str) -> RankingCue | None:
    """Return the user-written ranking operator, or None.

    The direction is only a language cue; the canonical plan still proves the
    measure, dimension, sort and top-N through the normal completeness gate.
    """

    normalized = unicodedata.normalize("NFKC", text)
    match = _RANKING.search(normalized)
    if match is None:
        word = _RANKING_WORD.search(normalized)
        if word is None:
            return None
        return RankingCue(
            direction=(
                "asc" if _RANKING_ASC.search(word.group(0)) else "desc"
            ),
            top_n=_count_from_message(normalized),
            text=word.group(0),
        )
    raw = (
        match.group("top")
        or match.group("top_words")
        or match.group("which")
        or match.group("front")
        or match.group("extreme")
        or match.group("ordinal")
    )
    top_n = parse_cn_integer(raw) if raw else None
    if top_n is None:
        top_n = _count_from_message(normalized)
    direction = "asc" if _RANKING_ASC.search(match.group(0)) else "desc"
    return RankingCue(direction=direction, top_n=top_n, text=match.group(0))


def _count_from_message(text: str) -> int | None:
    word = _COUNT_WORD_PATTERN.search(text)
    if word is not None:
        return _COUNT_WORD[word.group(1).casefold()]
    chinese = _CN_COUNT_PATTERN.search(text)
    if chinese is not None:
        return parse_cn_integer(chinese.group(1))
    return None


def has_time_language(text: str) -> bool:
    """Detect a concrete date value, range, or relative time window."""

    normalized = unicodedata.normalize("NFKC", text)
    return bool(
        _TIME_VALUE.search(normalized)
        or has_explicit_month_range(normalized)
        or has_vague_recent_month_range(normalized)
    )


def has_reset_cue(text: str) -> bool:
    return bool(_RESET.search(unicodedata.normalize("NFKC", text)))


_TREND_CUE = re.compile(
    r"(?:\btrend\b|\bseries\b|\bover\s+time\b|\bmonthly\b|\bmonth\s+by\s+month\b|"
    r"走势|趋势|按月|每月|逐月)",
    re.IGNORECASE,
)


def has_trend_cue(text: str) -> bool:
    return bool(_TREND_CUE.search(unicodedata.normalize("NFKC", text)))


# Language-level framing vocabulary.  It contains grammar, request verbs and
# analytics framing only; business nouns are deliberately excluded so an
# omitted member/measure/grouping remains visible to the coverage gate.
_FRAMING = (
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "of", "in", "on", "at",
    "for", "to", "from", "by", "with", "and", "or", "but", "if", "then",
    "than", "that", "this", "these", "those", "it", "its", "as", "per",
    "each", "all", "any", "some", "both", "between", "into", "over",
    "under", "above", "below", "more", "most", "less", "least", "much",
    "many", "few", "very", "just", "only", "also", "now", "current",
    "currently", "please", "show", "display", "list", "give", "tell",
    "get", "find", "calculate", "compute", "analyze", "analyse", "analysis",
    "report", "dashboard", "data", "here", "what", "which", "who", "whom",
    "whose", "when", "where", "why", "how", "total", "overall",
    "generated", "generate", "made", "make", "earn", "earned",
    "produce", "produced", "contribute", "contributed", "sold", "sell",
    "sells", "bought", "buy", "purchase", "purchased", "spend", "spent",
    "during", "within", "last", "next", "previous", "first", "second",
    "third", "half", "trend", "compare", "comparison", "top", "highest",
    "lowest", "best", "worst", "biggest", "smallest", "largest",
    "dimension", "dimensions", "metric", "metrics", "measure",
    "measures", "want", "need", "like", "would",
    "could", "can", "will", "should", "about", "across", "among", "using",
    "use", "used", "based", "according", "respectively", "side", "together",
    "combined", "combine", "break", "down", "briefly", "short", "simple",
    "instead", "rather", "again", "same", "new", "different", "other",
    "please", "kindly", "return", "output", "answer", "question",
    "i", "me", "my", "we", "us", "our", "you", "your", "yours",
    "he", "him", "his", "she", "her", "they", "them", "their",
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "dozen", "hundred", "thousand", "million", "billion",
    "zero",
    "的", "了", "吗", "呢", "吧", "啊", "是", "在", "有", "和", "与",
    "及", "或", "等", "各", "每", "个", "哪些", "哪个", "什么", "多少",
    "几", "怎么", "如何", "为什么", "请", "帮", "我", "我们", "你", "您",
    "生成", "创建", "制作", "导出", "出一份", "给我一份", "一份",
    "一下", "看看", "查看", "查询", "显示", "列出", "给出", "告诉", "统计",
    "分析", "比较", "对比", "计算", "求", "总共", "一共", "合计", "总计",
    "整体", "全部", "所有", "当前", "目前", "现在", "这里", "这个", "那个",
    "这些", "那些", "报表", "报告", "数据", "仪表板", "页面", "图表", "图",
    "表现", "performance", "performing", "doing",
    "monthly", "yearly", "daily", "weekly", "quarterly", "over time",
    "spread", "leading", "三项", "两项", "四项", "五项", "一项", "几项",
    "大概", "大约", "约", "差不多", "左右", "包含", "含有", "包括",
    "匹配", "等于", "大于", "小于", "不低于", "不高于", "同比", "环比",
    "相比", "谢谢", "感谢", "麻烦", "劳驾", "你好", "您好",
    "完整", "完整地", "详细", "全面", "专业", "经营",
    "这张", "这份", "那份", "上述", "上面", "以下", "那么", "这么",
    "不是", "也不是", "而是", "换成", "改为",
    "情况", "结果", "数值", "数字", "产生", "创造", "带来", "贡献", "获得",
    "赚取", "实现", "卖", "购买", "花费", "销售了", "销售过", "卖出",
    "卖了", "售出", "哪款", "哪几款", "款",
    "最高", "最低", "最多", "最少",
    "最大", "最小", "前", "后", "排名", "排序", "上升", "下降", "增长",
    "减少", "趋势", "按月", "按年", "每月", "每年", "今年", "去年", "明年",
    "本月", "上月", "上个月", "下个月", "最近", "过去", "未来", "上半年",
    "下半年", "季度", "月", "年", "日", "天", "周", "第一", "第二",
    "第三", "半", "从", "到", "至", "开始", "结束", "之间", "内", "中",
    "里", "上", "下", "以及", "还有", "顺便", "再", "然后", "同时", "另外",
    "并且", "还", "改", "改成", "换成", "替换", "按", "按照",
    "清除", "取消", "不限", "只看",
    "只要", "仅", "就", "也", "都", "很", "更", "分别", "各自", "一起",
    "合在一起", "加起来", "平均", "总", "共", "计", "简洁", "简短",
)
_FRAMING_TERMS = tuple(
    sorted(
        {term.casefold() for term in _FRAMING if term.strip()},
        key=len,
        reverse=True,
    )
)
_RESIDUAL_CJK = re.compile(r"[㐀-䶿一-鿿]{2,}")
_RESIDUAL_WORD = re.compile(r"[a-z][a-z0-9_]{1,}", re.IGNORECASE)
_NEGATED = re.compile(
    r"(?:不是|而不是|并非|并不是|不叫|别用|不要)\s*"
    r"[^，,。；;是]{1,40}"
)
_NEGATED_EN = re.compile(
    r"\b(?:not|instead\s+of|rather\s+than)\s+"
    r"[A-Za-z0-9_'\-\s]{1,40}?(?=\bby\b|\bfor\b|\bin\b|[,.;]|$)",
    re.IGNORECASE,
)


def uncovered_content(text: str, covered: tuple[str, ...]) -> str | None:
    """Return the first business-looking residual not covered by the frame.

    Coverage is lexical only: the exact slot values are removed from the
    current message, then a small language-level framing vocabulary.  What
    remains must be a name, category, metric or other business term that the
    LLM failed to preserve.  The caller sends it through the existing bounded
    repair; this function never binds or guesses.
    """

    normalized = unicodedata.normalize("NFKC", text).casefold()
    if not normalized.strip():
        return None
    remaining = _RESET.sub(" ", normalized)
    remaining = _NEGATED.sub(" ", remaining)
    remaining = _NEGATED_EN.sub(" ", remaining)
    for term in sorted(
        {value.casefold() for value in covered if value and value.strip()},
        key=len,
        reverse=True,
    ):
        remaining = remaining.replace(term, " ")
    for term in _FRAMING_TERMS:
        if term.isascii():
            remaining = re.sub(
                r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])",
                " ",
                remaining,
            )
        else:
            remaining = remaining.replace(term, " ")
    for match in _RESIDUAL_CJK.finditer(remaining):
        candidate = match.group(0).strip()
        if candidate and candidate not in _FRAMING_TERMS:
            return candidate
    for match in _RESIDUAL_WORD.finditer(remaining):
        candidate = match.group(0).strip()
        if len(candidate) >= 2 and candidate not in _FRAMING_TERMS:
            return candidate
    return None
