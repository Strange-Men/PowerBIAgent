"""Harness 配置和运行模型"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LLMMode(str, Enum):
    MOCK = "mock"
    DEEPSEEK = "deepseek"


class PowerBIMode(str, Enum):
    MOCK = "mock"
    REMOTE_MCP = "remote_mcp"


class HarnessMode(str, Enum):
    STRICT = "strict"
    TEST = "test"


class HarnessConfig(BaseModel):
    """Harness 运行配置 — M0.3 定义模型，M0.4 通过 Pydantic Settings 接入"""

    app_env: AppEnv = AppEnv.TEST
    llm_mode: LLMMode = LLMMode.MOCK
    powerbi_mode: PowerBIMode = PowerBIMode.MOCK
    harness_mode: HarnessMode = HarnessMode.STRICT

    request_timeout_seconds: int = Field(default=120, ge=10)
    powerbi_query_timeout_seconds: int = Field(default=30, ge=5, le=300)

    max_tool_calls: int = Field(default=3, ge=1)
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


# 默认 Mock 执行模式配置
DEFAULT_MOCK_CONFIG = HarnessConfig(
    app_env=AppEnv.TEST,
    llm_mode=LLMMode.MOCK,
    powerbi_mode=PowerBIMode.MOCK,
    harness_mode=HarnessMode.STRICT,
)
