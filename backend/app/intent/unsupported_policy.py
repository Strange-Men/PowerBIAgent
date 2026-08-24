"""Deterministic routing policy for an LLM ``UNSUPPORTED`` classification."""

from __future__ import annotations

import re

from backend.app.intent.models import IntentSpec
from backend.app.memory.models import PendingClarificationContext, StructuredWorkMemory


_DETERMINISTICALLY_OUT_OF_SCOPE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:删除|清空|销毁|写入|修改|更新|新增).*(?:数据|模型|表|字段|度量值|Measure|PBIX|Power\s*BI)",
        r"(?:预测|预估|外推|forecast).*(?:销售|销量|订单|利润|收入|成本|金额|数据|指标)",
        r"(?:执行|运行|编写).*(?:SQL|Shell|PowerShell|Python|JavaScript|代码)",
        r"(?:SQL|Shell|PowerShell|Python|JavaScript|任意代码|代码).*(?:执行|运行)",
        r"(?:密钥|API\s*Key|Token|密码|Client\s*Secret)",
        r"(?:绕过|规避).*(?:权限|白名单|安全|验证)",
        r"(?:修改|泄露|显示).*(?:系统\s*Prompt|系统提示词)",
        r"(?:写诗|写一首诗|讲笑话|翻译|天气|新闻|订餐|发邮件)",
    )
)


def deterministic_unsupported_reason(user_input: str) -> str | None:
    """Fail closed before Memory inheritance, Grounding, tools, or DAX."""

    normalized = user_input.strip()
    if not normalized:
        return None
    if re.search(
        r"(?:预测|预估|外推|forecast).*(?:销售|销量|订单|利润|收入|成本|金额|数据|指标)",
        normalized,
        re.IGNORECASE,
    ):
        return "当前只支持基于已存在数据的只读分析，不支持预测或未来外推。"
    if any(pattern.search(normalized) for pattern in _DETERMINISTICALLY_OUT_OF_SCOPE):
        return "当前为只读分析模式，不支持修改、删除、写入模型或执行任意代码。"
    return None

_DATA_SHAPED = re.compile(
    r"(?:"
    r"数据|报表|报告|指标|度量|字段|维度|筛选|过滤|"
    r"销售|销量|数量|订单|利润|收入|成本|金额|件数|周转率|"
    r"本月|本年|今年|去年|日期|时间|最近\s*\d+|"
    r"排名|排行|前\s*\d+|top\s*\d+|最高|最低|最大|最小|"
    r"同比|环比|比较|对比|大于|小于|超过|等于|包含|"
    r"多少|总计|合计|平均"
    r")",
    re.IGNORECASE,
)


def should_defer_unsupported_to_grounding(
    user_input: str,
    intent: IntentSpec,
    *,
    committed: StructuredWorkMemory | None = None,
    pending: PendingClarificationContext | None = None,
    report_template_key: str | None = None,
) -> bool:
    """Return true only when an unsupported result still looks data-shaped.

    Destructive, privileged, arbitrary-code, and clearly non-data requests keep
    the cheap early stop.  Data/report-shaped requests continue through the
    existing authoritative Grounding and capability checks, which may resolve
    them or request clarification without committing Memory.
    """

    normalized = user_input.strip()
    if any(pattern.search(normalized) for pattern in _DETERMINISTICALLY_OUT_OF_SCOPE):
        return False
    # Existing Memory/Pending state is deliberately irrelevant: it can never
    # turn the current unsupported request into a data query.
    if report_template_key is not None:
        return True
    if (
        intent.detected_measures
        or intent.detected_dimensions
        or intent.detected_filters
        or intent.detected_time_range is not None
        or intent.requested_template is not None
    ):
        return True
    return bool(_DATA_SHAPED.search(normalized))
