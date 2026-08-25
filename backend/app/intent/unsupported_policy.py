"""Three-layer readonly capability policy.

Regex is a high-confidence safety floor.  A bounded LLM classification is only
a language signal; ordinary code owns the terminal policy decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from backend.app.intent.models import CapabilityClass, IntentSpec
from backend.app.memory.models import PendingClarificationContext, StructuredWorkMemory


_FUTURE_EVIDENCE = r"(?:明年|来年|后年|下(?:一)?季度|下(?:一)?个月|未来|next\s+year|next\s+quarter|future)"
_PREDICTION_VERB = r"(?:预测|预估|估算|估计|推测|外推|forecast|project)"
_BUSINESS_TARGET = r"(?:销售额|销售|销量|订单|利润|收入|成本|金额|数据|指标|营收|能卖多少)"

_FUTURE_PREDICTION = re.compile(
    rf"(?:"
    rf"{_PREDICTION_VERB}.*(?:{_FUTURE_EVIDENCE}|{_BUSINESS_TARGET})|"
    rf"{_FUTURE_EVIDENCE}.*(?:{_PREDICTION_VERB}|大概.*(?:能|会)?|假设|增长\s*\d|{_BUSINESS_TARGET}.*会)|"
    rf"假设.*{_FUTURE_EVIDENCE}"
    rf")",
    re.IGNORECASE,
)

_MODEL_WRITE = re.compile(
    r"(?:写入|修改|改一下|更新|新增|编辑).*(?:模型|字段|度量值|Measure|PBIX|Power\s*BI)|"
    r"(?:模型|字段|度量值|Measure|PBIX|Power\s*BI).*(?:写入|修改|改一下|更新|新增|编辑)",
    re.IGNORECASE,
)
_DATA_DELETE = re.compile(
    r"(?:删除|删掉|清掉|清空|销毁).*(?:数据|模型|表|字段|度量值|Measure|PBIX|Power\s*BI|销售|订单)|"
    r"(?:数据|模型|表|字段|度量值|Measure|PBIX|Power\s*BI|销售|订单).*(?:删除|删掉|清掉|清空|销毁)",
    re.IGNORECASE,
)
_ARBITRARY_CODE = re.compile(
    r"(?:执行|运行|编写|生成).*(?:SQL|Shell|PowerShell|Python|JavaScript|任意代码|代码)|"
    r"(?:SQL|Shell|PowerShell|Python|JavaScript|任意代码|代码).*(?:执行|运行|编写)",
    re.IGNORECASE,
)

_DETERMINISTICALLY_OUT_OF_SCOPE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
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
    if _FUTURE_PREDICTION.search(normalized):
        return "当前只支持基于已存在数据的只读分析，不支持预测或未来外推。"
    if _DATA_DELETE.search(normalized):
        return "当前为只读分析模式，不支持删除或清空数据。"
    if _MODEL_WRITE.search(normalized):
        return "当前为只读分析模式，不支持修改、更新或写入 Power BI 模型。"
    if _ARBITRARY_CODE.search(normalized):
        return "当前为只读分析模式，不支持执行任意代码。"
    if any(pattern.search(normalized) for pattern in _DETERMINISTICALLY_OUT_OF_SCOPE):
        return "当前为只读分析模式，不支持修改、删除、写入模型或执行任意代码。"
    return None


class CapabilityPolicyStatus(str, Enum):
    SUPPORTED = "supported"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CapabilityPolicyDecision:
    status: CapabilityPolicyStatus
    reason: str | None = None


_CAPABILITY_UNSUPPORTED_REASONS = {
    CapabilityClass.FUTURE_PREDICTION: (
        "当前只支持基于已存在数据的只读分析，不支持预测或未来外推。"
    ),
    CapabilityClass.MODEL_WRITE: (
        "当前为只读分析模式，不支持修改、更新或写入 Power BI 模型。"
    ),
    CapabilityClass.DATA_DELETE: "当前为只读分析模式，不支持删除或清空数据。",
    CapabilityClass.ARBITRARY_CODE: "当前为只读分析模式，不支持执行任意代码。",
    CapabilityClass.RESOURCE_MANAGEMENT_REQUEST: (
        "会话与报表资源管理只能由用户在界面中明确操作，不能通过自然语言执行。"
    ),
}


def resolve_capability_policy(user_input: str, intent: IntentSpec) -> CapabilityPolicyDecision:
    """Resolve a bounded language signal without granting it authority."""

    fast_path = deterministic_unsupported_reason(user_input)
    if fast_path is not None:
        return CapabilityPolicyDecision(CapabilityPolicyStatus.UNSUPPORTED, fast_path)

    signal = intent.capability_classification
    if signal is None:
        return CapabilityPolicyDecision(CapabilityPolicyStatus.SUPPORTED)

    if signal.capability == CapabilityClass.READ_ANALYSIS:
        return CapabilityPolicyDecision(CapabilityPolicyStatus.SUPPORTED)

    evidence = signal.evidence_span
    evidence_is_current = bool(
        evidence and evidence.casefold() in user_input.casefold()
    )
    if not evidence_is_current or signal.confidence < 0.75:
        return CapabilityPolicyDecision(
            CapabilityPolicyStatus.CLARIFICATION,
            "请确认你是要查询已有数据，还是要预测未来、修改模型或管理资源？",
        )

    if signal.capability == CapabilityClass.UNKNOWN:
        return CapabilityPolicyDecision(
            CapabilityPolicyStatus.CLARIFICATION,
            "请说明你希望查询的已有数据指标或分析范围。",
        )

    reason = _CAPABILITY_UNSUPPORTED_REASONS.get(signal.capability)
    if reason is not None:
        return CapabilityPolicyDecision(CapabilityPolicyStatus.UNSUPPORTED, reason)
    return CapabilityPolicyDecision(CapabilityPolicyStatus.CLARIFICATION, "请进一步说明你的分析需求。")

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
    if deterministic_unsupported_reason(normalized) is not None:
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
