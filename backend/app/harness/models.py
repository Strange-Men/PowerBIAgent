"""Harness 配置和运行模型

M1.6.2: Enum 类型统一从 config/settings.py 导入，不再重复定义。
HarnessConfig.from_settings() 是 Settings → HarnessConfig 唯一映射入口。
"""

from typing import Optional

from pydantic import BaseModel, Field

from backend.app.config.settings import AppEnv, HarnessMode, LLMMode, PowerBIMode, Settings


class HarnessConfig(BaseModel):
    """Harness 运行配置 — M0.3 定义模型，M1.6.2 统一从 Settings 构建"""

    # ── 四个运行模式（Enum 来源统一为 config/settings.py） ──
    app_env: AppEnv = AppEnv.TEST
    llm_mode: LLMMode = LLMMode.MOCK
    powerbi_mode: PowerBIMode = PowerBIMode.MOCK
    harness_mode: HarnessMode = HarnessMode.STRICT

    # ── 超时与限制 ──
    request_timeout_seconds: int = Field(default=120, ge=10)
    powerbi_query_timeout_seconds: int = Field(default=30, ge=5, le=300)

    max_tool_calls: int = Field(default=4, ge=1)
    max_dax_repairs: int = Field(default=1, ge=0)
    max_llm_format_retries: int = Field(default=1, ge=0)
    max_powerbi_retries: int = Field(default=1, ge=0)
    max_query_rows: int = Field(default=1000, ge=1)
    max_user_input_length: int = Field(default=2000, ge=1)

    @property
    def is_mock(self) -> bool:
        return self.llm_mode == LLMMode.MOCK and self.powerbi_mode == PowerBIMode.MOCK

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION

    @classmethod
    def from_settings(cls, settings: Settings) -> "HarnessConfig":
        """从 Pydantic Settings 完整构建 HarnessConfig

        这是 Settings → HarnessConfig 的唯一映射入口。
        所有字段一一映射，不做默认值回退。
        """
        return cls(
            # ── 四个运行模式 ──
            app_env=settings.app_env,
            llm_mode=settings.llm_mode,
            powerbi_mode=settings.powerbi_mode,
            harness_mode=settings.harness_mode,
            # ── 超时 ──
            request_timeout_seconds=settings.request_timeout_seconds,
            powerbi_query_timeout_seconds=settings.powerbi_query_timeout_seconds,
            # ── 限制 ──
            max_tool_calls=settings.max_tool_calls,
            max_dax_repairs=settings.max_dax_repairs,
            max_llm_format_retries=settings.max_llm_format_retries,
            max_powerbi_retries=settings.max_powerbi_retries,
            max_query_rows=settings.max_query_rows,
            max_user_input_length=settings.max_user_input_length,
        )
