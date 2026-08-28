"""LLM Call Observer — 请求级 LLM 调用观察与统计

每个请求创建独立 LLMCallCollector + ObservedLLMProvider。
不修改共享 Provider 实例方法，不污染并发请求。
不记录 Prompt、响应正文、Header 或 Secret。

用法：
    collector = LLMCallCollector(input_cost_per_m=0.14, output_cost_per_m=0.28)
    observed = ObservedLLMProvider(inner_provider, collector)
    # 将 observed 传给 DeepSeekIntentService 等
    # 请求结束后调用 collector.summary()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMValidationError,
)
from backend.app.llm.profiles import LLMModelProfile


# ---------------------------------------------------------------------------
# Observation — 单次 LLM 调用记录
# ---------------------------------------------------------------------------

@dataclass
class LLMCallObservation:
    """单次 LLM 调用观察记录"""

    task: str                          # LLMTask 值（如 "intent_recognition"）
    attempt_index: int                 # 0-based，当前 task 内第几次调用
    provider_name: str                 # "deepseek" / "mock"
    model: str                         # 模型名
    started_at: float                  # time.monotonic() 起始
    duration_ms: float                 # 调用耗时（ms）
    status: str                        # "success" / "validation_error" / "provider_error"
    error_type: Optional[str] = None   # 异常类名
    error_code: Optional[str] = None   # 错误代码
    error_category: Optional[str] = None
    profile_key: str = ""
    provider_protocol: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    usage_available: bool = False      # 是否成功获取 usage

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "attempt_index": self.attempt_index,
            "provider_name": self.provider_name,
            "model": self.model,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "error_category": self.error_category,
            "profile_key": self.profile_key,
            "provider_protocol": self.provider_protocol,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "usage_available": self.usage_available,
        }


# ---------------------------------------------------------------------------
# UsageSummary — 聚合统计
# ---------------------------------------------------------------------------

@dataclass
class LLMUsageSummary:
    """请求级 LLM 使用摘要"""

    call_count: int = 0
    repair_count: int = 0              # 跨所有 task 的总修复次数
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    estimated_cost_usd: Optional[float] = None  # None = 未配置价格
    pricing_configured: bool = False
    per_task: dict[str, int] = field(default_factory=dict)  # task → attempt_count
    calls: list[dict] = field(default_factory=list)          # 安全序列化

    def to_dict(self) -> dict:
        result: dict = {
            "call_count": self.call_count,
            "repair_count": self.repair_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "pricing_configured": self.pricing_configured,
            "per_task": dict(self.per_task),
            "calls": list(self.calls),
        }
        if self.estimated_cost_usd is not None:
            result["estimated_cost_usd"] = self.estimated_cost_usd
        else:
            result["estimated_cost_usd"] = None
        return result


# ---------------------------------------------------------------------------
# CallCollector — 请求级收集器
# ---------------------------------------------------------------------------

class LLMCallCollector:
    """请求独立的 LLM 调用收集器

    每个 HTTP 请求创建一个 Collector 实例。
    通过 ObservedLLMProvider 记录每次 generate() 调用。
    """

    def __init__(
        self,
        input_cost_per_million: Optional[float] = None,
        output_cost_per_million: Optional[float] = None,
    ):
        self._observations: list[LLMCallObservation] = []
        self._input_cost_per_m = input_cost_per_million
        self._output_cost_per_m = output_cost_per_million

    def add_attempt(self, observation: LLMCallObservation) -> None:
        """记录一次 LLM 调用"""
        self._observations.append(observation)

    @property
    def observations(self) -> list[LLMCallObservation]:
        return list(self._observations)

    def summary(self) -> LLMUsageSummary:
        """计算聚合摘要

        repair_count = Σ(max(attempts_per_task - 1, 0))
        """
        calls = [o.to_dict() for o in self._observations]

        # 按 task 分组统计
        task_attempts: dict[str, int] = {}
        for obs in self._observations:
            task_attempts[obs.task] = task_attempts.get(obs.task, 0) + 1

        # repair = 总尝试次数 - 唯一 task 数（每个 task 至少一次成功/必需的调用）
        repair_count = max(0, len(self._observations) - len(task_attempts))

        prompt_tokens = sum(o.prompt_tokens for o in self._observations)
        completion_tokens = sum(o.completion_tokens for o in self._observations)
        total_tokens = sum(o.total_tokens for o in self._observations)

        # 耗时 = 所有调用的耗时之和（非重叠串行调用）
        duration_ms = sum(o.duration_ms for o in self._observations)

        # 成本计算
        pricing_configured = (
            self._input_cost_per_m is not None
            and self._output_cost_per_m is not None
        )
        estimated_cost_usd: Optional[float] = None
        if pricing_configured:
            estimated_cost_usd = (
                (prompt_tokens / 1_000_000.0) * self._input_cost_per_m  # type: ignore[operator]
                + (completion_tokens / 1_000_000.0) * self._output_cost_per_m  # type: ignore[operator]
            )
            estimated_cost_usd = round(estimated_cost_usd, 8)

        return LLMUsageSummary(
            call_count=len(self._observations),
            repair_count=repair_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            estimated_cost_usd=estimated_cost_usd,
            pricing_configured=pricing_configured,
            per_task=dict(task_attempts),
            calls=calls,
        )


# ---------------------------------------------------------------------------
# ObservedLLMProvider — 包装 LLMProvider，拦截 generate()
# ---------------------------------------------------------------------------

class ObservedLLMProvider(LLMProvider):
    """包装 LLMProvider，拦截每次 generate() 调用进行统计

    - 不修改共享 Provider 实例方法
    - 每次 generate() 调用前增加 task 级 attempt_count
    - 成功时记录 LLMResponse.usage
    - 异常时读取异常的安全 usage（LLMValidationError.usage 等）
    - 原样重新抛出异常
    - 不改变业务重试规则
    - 每个请求独立 Collector + ObservedLLMProvider
    """

    def __init__(
        self,
        inner: LLMProvider,
        collector: LLMCallCollector,
        profile: LLMModelProfile | None = None,
    ):
        if inner is None:
            raise ValueError("inner provider 不能为 None")
        self._inner = inner
        self._collector = collector
        self._profile = profile
        self._task_attempts: dict[str, int] = {}  # task → 已调用次数

    # ── 属性 ──

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def is_mock(self) -> bool:
        return self._inner.is_mock

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    # ── generate ──

    async def generate(
        self,
        request: LLMRequest,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        """拦截 generate()，记录调用统计后透传"""
        task_key = request.task.value
        attempt_index = self._task_attempts.get(task_key, 0)
        self._task_attempts[task_key] = attempt_index + 1

        started_at = time.monotonic()
        try:
            response = await self._inner.generate(request, output_type)
            duration_ms = (time.monotonic() - started_at) * 1000.0

            usage = response.usage or {}
            self._collector.add_attempt(LLMCallObservation(
                task=task_key,
                attempt_index=attempt_index,
                provider_name=self.provider_name,
                model=response.model or (self._profile.model if self._profile else ""),
                profile_key=(self._profile.profile_key if self._profile else self.provider_name),
                provider_protocol=(
                    self._profile.provider_protocol.value if self._profile else ""
                ),
                started_at=started_at,
                duration_ms=duration_ms,
                status="success",
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                usage_available=bool(usage),
            ))
            return response

        except LLMValidationError as e:
            duration_ms = (time.monotonic() - started_at) * 1000.0
            error_usage = e.usage or {}
            self._collector.add_attempt(LLMCallObservation(
                task=task_key,
                attempt_index=attempt_index,
                provider_name=self.provider_name,
                model=e.model or (self._profile.model if self._profile else ""),
                started_at=started_at,
                duration_ms=duration_ms,
                status="validation_error",
                error_type=type(e).__name__,
                error_code=e.error_code,
                error_category=e.error_category.value,
                profile_key=(self._profile.profile_key if self._profile else self.provider_name),
                provider_protocol=(
                    self._profile.provider_protocol.value if self._profile else ""
                ),
                prompt_tokens=error_usage.get("prompt_tokens", 0),
                completion_tokens=error_usage.get("completion_tokens", 0),
                total_tokens=error_usage.get("total_tokens", 0),
                usage_available=bool(error_usage),
            ))
            raise

        except LLMProviderError as e:
            duration_ms = (time.monotonic() - started_at) * 1000.0
            self._collector.add_attempt(LLMCallObservation(
                task=task_key,
                attempt_index=attempt_index,
                provider_name=self.provider_name,
                model=e.model or (self._profile.model if self._profile else ""),
                started_at=started_at,
                duration_ms=duration_ms,
                status="provider_error",
                error_type=type(e).__name__,
                error_code=e.error_code,
                error_category=e.error_category.value,
                profile_key=(self._profile.profile_key if self._profile else self.provider_name),
                provider_protocol=(
                    self._profile.provider_protocol.value if self._profile else ""
                ),
                usage_available=False,
            ))
            raise

    def __repr__(self) -> str:
        return f"ObservedLLMProvider(inner={self._inner!r})"
