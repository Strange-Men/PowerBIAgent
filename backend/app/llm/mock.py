"""Mock LLM Provider — 可运行的假 LLM

支持根据 scenario_key 返回预设结构化结果：
- data_question: 正常数据问答意图
- report_generation: 报表生成意图
- clarification: 需要澄清
- unsupported: 拒绝/不支持
- invalid_structure: 非法结构模拟
- timeout: 超时模拟
- missing_fields: 缺字段模拟

Mock 结果不可标记为真实业务结果。
"""

import json
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMValidationError,
)

FIXTURES_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "mock_llm_responses.json"


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider

    完全离线可运行，不依赖任何网络或 API Key。
    根据 LLMRequest.scenario_key 返回对应的预设结构化结果。
    """

    PROVIDER_NAME = "mock"

    def __init__(self, scenario_delay: float = 0.0):
        self._responses: dict[str, dict[str, Any]] = {}
        self._scenario_delay = scenario_delay
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """加载 mock 响应预设"""
        try:
            if FIXTURES_PATH.exists():
                with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
                    self._responses = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

        # 内联默认响应（确保即使文件不存在也能运行）
        self._defaults = {
            "data_question": {
                "intent": "data_question",
                "confidence": 0.95,
                "normalized_question": "本月销售额是多少？",
                "needs_clarification": False,
                "detected_measures": ["销售额"],
                "detected_time_range": "本月",
            },
            "report_generation": {
                "intent": "report_generation",
                "confidence": 0.90,
                "normalized_question": "生成销售周报",
                "needs_clarification": False,
                "detected_measures": ["销售额"],
                "requested_template": "销售周报模板",
            },
            "clarification": {
                "intent": "clarification",
                "confidence": 0.60,
                "normalized_question": "帮我看看数据",
                "needs_clarification": True,
                "clarification_question": "请问您想查看哪个指标？比如销售额、利润或订单数？",
            },
            "unsupported": {
                "intent": "unsupported",
                "confidence": 0.98,
                "normalized_question": "删除所有数据",
                "needs_clarification": False,
                "unsupported_reason": "该操作不在允许范围内",
            },
            "invalid_structure": {
                "intent": "invalid_type_xyz",
                "confidence": 999.0,
                "normalized_question": "",
            },
            "missing_fields": {
                "intent": "data_question",
                "confidence": 0.85,
            },
        }

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return True

    async def generate(self, request: LLMRequest, output_type: type[BaseModel]) -> LLMResponse:
        """根据 scenario_key 返回预设结构化结果

        Args:
            request: LLM 请求（scenario_key 决定返回哪种预设结果）
            output_type: 期望的 Pydantic 输出类型

        Returns:
            LLMResponse

        Raises:
            LLMTimeoutError: 当 scenario_key 为 "timeout"
            LLMValidationError: 当场景需要非法结构时
        """
        # 模拟延迟
        if self._scenario_delay > 0:
            time.sleep(self._scenario_delay)

        key = request.scenario_key or "data_question"

        # 超时模拟
        if key == "timeout":
            raise LLMTimeoutError("Mock timeout", provider=self.PROVIDER_NAME, retryable=True)

        # 非法结构模拟
        if key == "invalid_structure":
            raw = self._get_response_data(key)
            # 返回不符合 output_type 的数据，触发校验失败
            content = json.dumps(raw, ensure_ascii=False)
            raise LLMValidationError(
                f"Mock validation failed: output does not match {output_type.__name__}",
                provider=self.PROVIDER_NAME,
                retryable=True,
            )

        # 正常场景：获取预设数据并构建响应
        raw = self._get_response_data(key)
        content = json.dumps(raw, ensure_ascii=False)

        # 尝试反序列化为 output_type
        try:
            structured = output_type.model_validate(raw)
        except Exception as e:
            raise LLMValidationError(
                f"Failed to parse mock response as {output_type.__name__}: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        return LLMResponse(
            content=content,
            structured=structured,
            model="mock-model",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason="stop",
        )

    def _get_response_data(self, key: str) -> dict[str, Any]:
        """获取指定场景的响应数据（优先 Fixture，fallback 默认）"""
        if key in self._responses:
            return self._responses[key]
        if key in self._defaults:
            return self._defaults[key]
        # 未知场景：返回 data_question 默认
        return self._defaults["data_question"]
