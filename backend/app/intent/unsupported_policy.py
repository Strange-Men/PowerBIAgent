"""Deterministic capability and safety preflight.

Only closed operation categories are classified here. Open language and
business meaning belong exclusively to ``LLMSemanticInterpreter``.
"""

from __future__ import annotations

import re
from enum import Enum

class CapabilityClass(str, Enum):
    """Closed registry for bounded language classification."""

    READ_ANALYSIS = "READ_ANALYSIS"
    FUTURE_PREDICTION = "FUTURE_PREDICTION"
    MODEL_WRITE = "MODEL_WRITE"
    DATA_DELETE = "DATA_DELETE"
    ARBITRARY_CODE = "ARBITRARY_CODE"
    UNKNOWN = "UNKNOWN"


_FUTURE_CUE = re.compile(
    r"(?:明年|下一年|下个月|未来|后续\s*\d*\s*(?:天|周|月|年))",
    re.IGNORECASE,
)
_PROJECTION_CUE = re.compile(
    r"(?:预测|预估|估算|外推|forecast|假设.*(?:增长|下降|增加|减少))",
    re.IGNORECASE,
)
_MODEL_WRITE = re.compile(
    r"(?:写入|修改|更新|新增|创建).*(?:数据|表|模型|字段|度量值|Measure|PBIX|Power\s*BI)",
    re.IGNORECASE,
)
_DATA_DELETE = re.compile(r"(?:删除|清空|销毁).*(?:数据|表|模型)", re.IGNORECASE)
_ARBITRARY_CODE = re.compile(
    r"(?:(?:执行|运行|编写).*(?:SQL|Shell|PowerShell|Python|JavaScript|代码)|"
    r"(?:SQL|Shell|PowerShell|Python|JavaScript|任意代码|代码).*(?:执行|运行))",
    re.IGNORECASE,
)


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
    )
)


def deterministic_unsupported_reason(user_input: str) -> str | None:
    """Fail closed before Memory inheritance, Grounding, tools, or DAX."""

    normalized = user_input.strip()
    if not normalized:
        return None
    capability = classify_capability(normalized)
    if capability == CapabilityClass.FUTURE_PREDICTION:
        return "当前只支持基于已存在数据的只读分析，不支持预测或未来外推。"
    if capability in {
        CapabilityClass.MODEL_WRITE,
        CapabilityClass.DATA_DELETE,
        CapabilityClass.ARBITRARY_CODE,
    }:
        return "当前为只读分析模式，不支持修改、删除、写入模型或执行任意代码。"
    if any(pattern.search(normalized) for pattern in _DETERMINISTICALLY_OUT_OF_SCOPE):
        return "当前为只读分析模式，不支持修改、删除、写入模型或执行任意代码。"
    return None

def classify_capability(user_input: str) -> CapabilityClass:
    """Classify into a registry enum without granting execution authority.

    This layer interprets only the requested operation category.  The final
    supported/unsupported decision remains deterministic policy below.
    """

    normalized = user_input.strip()
    if not normalized:
        return CapabilityClass.UNKNOWN
    if _DATA_DELETE.search(normalized):
        return CapabilityClass.DATA_DELETE
    if _MODEL_WRITE.search(normalized):
        return CapabilityClass.MODEL_WRITE
    if _ARBITRARY_CODE.search(normalized):
        return CapabilityClass.ARBITRARY_CODE
    if _FUTURE_CUE.search(normalized) and _PROJECTION_CUE.search(normalized):
        return CapabilityClass.FUTURE_PREDICTION
    return CapabilityClass.UNKNOWN
