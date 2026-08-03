"""Pydantic Settings — M0.4 项目配置骨架

环境变量可覆盖所有配置项。
Mock 模式启动不需要任何 API Key。
"""

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class Settings(BaseSettings):
    """PowerBIAgent 应用配置

    环境变量前缀：无（直接读取环境变量）
    .env 文件可选加载
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # ── 应用基础 ──────────────────────────────
    app_name: str = Field(default="PowerBIAgent", frozen=True)
    app_env: AppEnv = Field(default=AppEnv.DEVELOPMENT)
    debug: bool = Field(default=True)
    version: str = Field(default="M1.1", frozen=True)

    # ── 服务器 ──────────────────────────────
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = Field(default="info")

    # ── 运行模式 ──────────────────────────────
    llm_mode: LLMMode = Field(default=LLMMode.MOCK)
    powerbi_mode: PowerBIMode = Field(default=PowerBIMode.MOCK)
    harness_mode: HarnessMode = Field(default=HarnessMode.STRICT)

    # ── API Key（仅 Real 模式需要） ───────────
    deepseek_api_key: Optional[SecretStr] = Field(default=None)
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_model: str = Field(default="deepseek-chat")

    # ── Power BI（仅 Real 模式需要） ────────────
    powerbi_tenant_id: Optional[str] = Field(default=None)
    powerbi_client_id: Optional[str] = Field(default=None)
    powerbi_client_secret: Optional[SecretStr] = Field(default=None)
    powerbi_mcp_endpoint: Optional[str] = Field(default=None)

    # ── 资源限制 ──────────────────────────────
    request_timeout_seconds: int = Field(default=120, ge=10)
    powerbi_query_timeout_seconds: int = Field(default=30, ge=5, le=300)
    max_tool_calls: int = Field(default=3, ge=1)
    max_dax_repairs: int = Field(default=1, ge=0)
    max_llm_format_retries: int = Field(default=1, ge=0)
    max_powerbi_retries: int = Field(default=1, ge=0)
    max_query_rows: int = Field(default=1000, ge=1)
    max_user_input_length: int = Field(default=2000, ge=1)

    # ── 只读属性 ──────────────────────────────

    @property
    def is_mock(self) -> bool:
        return self.llm_mode == LLMMode.MOCK and self.powerbi_mode == PowerBIMode.MOCK

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION

    @property
    def is_deepseek_configured(self) -> bool:
        """DeepSeek API Key 是否已配置

        只判断是否存在非空 Secret，不进行网络访问。
        不返回 Key 长度、前缀或后缀。
        """
        if self.deepseek_api_key is None:
            return False
        key = self.deepseek_api_key.get_secret_value()
        return bool(key and key.strip())

    @property
    def is_real_ready(self) -> bool:
        """Real 模式是否具备运行条件

        M1.1：DeepSeek Provider 已实现，但真实意图链路尚未完成。
        即使配置了 API Key，整个 Agent Pipeline 仍不可用。
        """
        if self.llm_mode == LLMMode.DEEPSEEK:
            return False  # M1.2+ 真实意图识别未完成
        if self.powerbi_mode == PowerBIMode.REMOTE_MCP:
            return False  # M2 前不可用
        return True

    def safe_repr(self) -> dict:
        """返回不包含 Secret 的易读配置摘要"""
        return {
            "app_name": self.app_name,
            "app_env": self.app_env.value,
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "llm_mode": self.llm_mode.value,
            "powerbi_mode": self.powerbi_mode.value,
            "harness_mode": self.harness_mode.value,
            "version": self.version,
            "is_mock": self.is_mock,
            "is_real_ready": self.is_real_ready,
            "deepseek_configured": self.is_deepseek_configured,
        }


@lru_cache()
def get_settings() -> Settings:
    """获取全局 Settings 单例（缓存）"""
    return Settings()
