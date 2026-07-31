"""Mock LLM Provider — 可运行的假 LLM

支持根据 scenario_key 返回预设结构化结果。
Fixture 从 harness/fixtures/ 唯一来源加载。
Mock 结果不可标记为真实业务结果。
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMScenarioNotFoundError,
    LLMTimeoutError,
    LLMValidationError,
)

# 唯一 Fixture 路径
DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "harness" / "fixtures"
FIXTURE_FILE = "mock_llm_responses.json"


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider

    完全离线可运行，不依赖任何网络或 API Key。
    根据 LLMRequest.scenario_key 返回对应的预设结构化结果。

    Fixture 从 harness/fixtures/ 唯一来源加载，不存在时明确失败。
    未知 scenario_key 严格抛出 LLMScenarioNotFoundError。
    """

    PROVIDER_NAME = "mock"

    def __init__(
        self,
        scenario_delay: float = 0.0,
        fixtures_dir: Optional[Path] = None,
    ):
        self._responses: dict[str, dict[str, dict[str, Any]]] = {}
        self._scenario_delay = scenario_delay
        self._fixtures_dir = fixtures_dir or DEFAULT_FIXTURES_DIR
        self._fixtures_loaded = False
        self._active_scenario: str = "data_question"  # M0.3.2: 由 MockAgentRuntime.set_scenario 设置
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """加载 mock 响应预设 — fixture 不存在或 JSON 错误时明确失败"""
        fixture_path = self._fixtures_dir / FIXTURE_FILE

        if not fixture_path.exists():
            raise LLMProviderError(
                f"Mock fixture file not found: {fixture_path}. "
                f"Expected at harness/fixtures/{FIXTURE_FILE}",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        try:
            with open(fixture_path, "r", encoding="utf-8") as f:
                self._responses = json.load(f)
        except json.JSONDecodeError as e:
            raise LLMProviderError(
                f"Mock fixture JSON decode error in {fixture_path}: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )
        except IOError as e:
            raise LLMProviderError(
                f"Mock fixture file read error: {fixture_path}: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        self._fixtures_loaded = True

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return True

    @property
    def fixtures_loaded(self) -> bool:
        """是否成功从文件加载了 fixture"""
        return self._fixtures_loaded

    def available_scenario_keys(self, task: str = "intent") -> list[str]:
        """列出指定 task 下的可用 scenario_key"""
        task_fixtures = self._responses.get(task, {})
        return list(task_fixtures.keys())

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
            LLMScenarioNotFoundError: 未知 scenario_key
        """
        # 模拟延迟 — 使用 asyncio.sleep，非 time.sleep
        if self._scenario_delay > 0:
            await asyncio.sleep(self._scenario_delay)

        key = request.scenario_key or "data_question"

        # 超时模拟
        if key == "timeout":
            raise LLMTimeoutError("Mock timeout", provider=self.PROVIDER_NAME, retryable=True)

        # 非法结构模拟
        if key == "invalid_structure":
            raise LLMValidationError(
                f"Mock validation failed: output does not match {output_type.__name__}",
                provider=self.PROVIDER_NAME,
                retryable=True,
            )

        # 正常场景：从 fixture 获取预设数据
        raw = self._get_response_data(key, request.task.value if hasattr(request.task, 'value') else str(request.task))
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

    # task 值到 fixture group 的映射
    _TASK_TO_GROUP: dict[str, str] = {
        "intent_recognition": "intent",
        "query_plan": "query_plan",
        "dax": "dax",
        "answer": "answer",
        "report": "report",
        "intent": "intent",  # 兼容直接传入 group 名
    }

    @staticmethod
    def _task_to_fixture_group(task: str) -> str:
        """将 LLMTask 值映射到 fixture JSON 中的 group key"""
        return MockLLMProvider._TASK_TO_GROUP.get(task, task)

    def _get_response_data(self, key: str, task: str = "intent") -> dict[str, Any]:
        """获取指定场景的响应数据

        查找顺序：
        1. task 映射后的 group 下的 key（如 intent/data_question）
        2. 严格失败（不再静默回退）
        """
        group = self._task_to_fixture_group(task)
        task_fixtures = self._responses.get(group, {})
        if key in task_fixtures:
            return task_fixtures[key]

        # 收集所有可用 key
        all_keys: list[str] = []
        for tk, tv in self._responses.items():
            if isinstance(tv, dict):
                for sk in tv:
                    all_keys.append(f"{tk}/{sk}")

        raise LLMScenarioNotFoundError(
            scenario_key=key,
            available_keys=all_keys,
            provider=self.PROVIDER_NAME,
        )

    def __repr__(self) -> str:
        return f"MockLLMProvider(delay={self._scenario_delay}, fixtures_loaded={self._fixtures_loaded})"
