"""RequestFingerprint — 请求指纹与冲突检测

M1.0.1 新增：
- RequestFingerprint: 为每个带 request_id 的请求生成稳定指纹
- IdempotencyConflictError: 相同 request_id 不同指纹时抛出
- 使用 Canonical JSON + SHA-256 生成指纹 Hash

设计原则：
- 指纹使用稳定的 Canonical JSON 序列化，保证确定性
- message 仅执行首尾空白清理，不做大小写转换或语义合并
- client_conversation_id 保存客户端原始输入，未传时保持 None
- 不将原始 message 或完整请求内容写入日志和 Trace
- 快照中仅长期保存指纹 Hash
"""

import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, Field


class IdempotencyConflictError(Exception):
    """request_id 冲突异常

    相同 runtime_mode + request_id 但不同的请求指纹。
    不重放旧结果、不执行新请求、不覆盖原快照。
    """

    def __init__(self, request_id: str, detail: str = ""):
        self.request_id = request_id
        self.detail = detail or (
            "request_id has already been used by a different request"
        )
        super().__init__(self.detail)


class OwnerFailedError(Exception):
    """Owner 执行失败异常 — 内部使用，唤醒 Waiter 后由 Waiter 重试"""
    pass


class RequestFingerprint(BaseModel):
    """请求指纹 — 用于判断重复 request_id 是否真的是同一业务请求

    所有影响执行结果的输入参数都参与指纹计算。
    """

    message: str = Field(description="首尾空白清理后的用户消息")
    client_conversation_id: Optional[str] = Field(
        default=None,
        description="客户端原始 conversation_id，未传时保持 None",
    )
    semantic_model_key: str = Field(description="语义模型标识")
    effective_report_template_key: Optional[str] = Field(
        default=None,
        description="已解析完成的生效报表模板 Key",
    )
    scenario: Optional[Any] = Field(
        default=None,
        description="Harness 显式传入的 Scenario（MockScenarioSelection）",
    )
    intent_key: Optional[str] = Field(
        default=None,
        description="旧式 intent_key（向后兼容）",
    )
    powerbi_key: Optional[str] = Field(
        default=None,
        description="旧式 powerbi_key（向后兼容）",
    )

    model_config = {"frozen": True}

    def to_canonical_dict(self) -> dict:
        """转换为 Canonical JSON 友好的字典

        Pydantic 字段按名称排序，确保确定性。
        """
        result: dict[str, Any] = {
            "client_conversation_id": self.client_conversation_id,
            "effective_report_template_key": self.effective_report_template_key,
            "intent_key": self.intent_key,
            "message": self.message,
            "powerbi_key": self.powerbi_key,
            "scenario": (
                self.scenario.model_dump()
                if self.scenario is not None and hasattr(self.scenario, "model_dump")
                else self.scenario
            ),
            "semantic_model_key": self.semantic_model_key,
        }
        return result

    def hash(self) -> str:
        """计算指纹的 SHA-256 Hash（实例方法）

        使用稳定的 Canonical JSON（按键排序），确保相同输入产生相同 Hash。
        """
        canonical = json.dumps(
            self.to_canonical_dict(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def compute(
        cls,
        message: str,
        client_conversation_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        effective_report_template_key: Optional[str] = None,
        scenario: Optional[Any] = None,
        intent_key: Optional[str] = None,
        powerbi_key: Optional[str] = None,
    ) -> "RequestFingerprint":
        """创建请求指纹并返回实例

        message 执行首尾空白清理，不做其他转换。
        client_conversation_id 使用客户端原始输入。
        """
        return cls(
            message=message.strip(),
            client_conversation_id=client_conversation_id,
            semantic_model_key=semantic_model_key,
            effective_report_template_key=effective_report_template_key,
            scenario=scenario,
            intent_key=intent_key,
            powerbi_key=powerbi_key,
        )

    @classmethod
    def compute_hash(
        cls,
        message: str,
        client_conversation_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        effective_report_template_key: Optional[str] = None,
        scenario: Optional[Any] = None,
        intent_key: Optional[str] = None,
        powerbi_key: Optional[str] = None,
    ) -> str:
        """便捷方法：直接计算并返回指纹 Hash"""
        return cls.compute(
            message=message,
            client_conversation_id=client_conversation_id,
            semantic_model_key=semantic_model_key,
            effective_report_template_key=effective_report_template_key,
            scenario=scenario,
            intent_key=intent_key,
            powerbi_key=powerbi_key,
        ).hash()

    def __repr__(self) -> str:
        """安全 repr — 不暴露原始 message 和完整请求内容"""
        return (
            f"RequestFingerprint(hash={self.hash()[:12]}..., "
            f"semantic_model_key={self.semantic_model_key})"
        )
