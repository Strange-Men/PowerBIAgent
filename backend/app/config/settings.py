"""Pydantic Settings — M3.2 项目配置

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
    OPENAI_COMPATIBLE = "openai_compatible"


class PowerBIMode(str, Enum):
    MOCK = "mock"
    LOCAL_MCP = "local_mcp"
    REMOTE_MCP = "remote_mcp"


class HarnessMode(str, Enum):
    STRICT = "strict"
    TEST = "test"


class PersistenceBackend(str, Enum):
    MEMORY = "memory"
    SQLITE = "sqlite"


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
    version: str = Field(default="M5.8.4", frozen=True)

    # ── 服务器 ──────────────────────────────
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = Field(default="info")

    # ── 运行模式 ──────────────────────────────
    llm_mode: LLMMode = Field(default=LLMMode.MOCK)
    llm_default_profile: str = Field(default="deepseek", min_length=1)
    powerbi_mode: PowerBIMode = Field(default=PowerBIMode.MOCK)
    harness_mode: HarnessMode = Field(default=HarnessMode.STRICT)

    # ── API Key（仅 Real 模式需要） ───────────
    deepseek_api_key: Optional[SecretStr] = Field(default=None)
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_model: str = Field(default="deepseek-chat")

    # Kimi-K2.6 via a user-configured OpenAI-compatible gateway.  The endpoint
    # intentionally has no production default because host ownership belongs
    # to the user's environment.
    kimi_api_key: Optional[SecretStr] = Field(default=None)
    kimi_base_url: str = Field(default="")
    kimi_model: str = Field(default="azure/Kimi-K2.6")

    # ── 成本计算（可选） ──────────────────────
    deepseek_input_cost_per_million_tokens: Optional[float] = Field(
        default=None, ge=0,
        description="DeepSeek 输入价格（美元/百万 Token）。未配置时 estimated_cost_usd=null",
    )
    deepseek_output_cost_per_million_tokens: Optional[float] = Field(
        default=None, ge=0,
        description="DeepSeek 输出价格（美元/百万 Token）。未配置时 estimated_cost_usd=null",
    )

    # ── Power BI（仅 Real 模式需要） ────────────
    powerbi_tenant_id: Optional[str] = Field(default=None)
    powerbi_client_id: Optional[str] = Field(default=None)
    powerbi_client_secret: Optional[SecretStr] = Field(default=None)
    powerbi_mcp_endpoint: Optional[str] = Field(default=None)
    powerbi_local_mcp_executable: str = Field(default="npx")
    powerbi_local_mcp_package: str = Field(
        default="@microsoft/powerbi-modeling-mcp@0.5.0-beta.12"
    )
    powerbi_local_semantic_model_key: str = Field(default="local_desktop_model")
    powerbi_semantic_override_path: Optional[str] = Field(default=None)
    powerbi_local_mcp_readonly: bool = Field(default=True)

    # ── 资源限制 ──────────────────────────────
    request_timeout_seconds: int = Field(default=120, ge=10)
    powerbi_query_timeout_seconds: int = Field(default=30, ge=5, le=300)
    max_tool_calls: int = Field(default=8, ge=1)
    max_dax_repairs: int = Field(default=1, ge=0)
    max_llm_format_retries: int = Field(default=1, ge=0)
    max_powerbi_retries: int = Field(default=1, ge=0)
    max_query_rows: int = Field(default=1000, ge=1)
    max_user_input_length: int = Field(default=2000, ge=1)

    # ── 只读属性 ──────────────────────────────

    # ── Persistence ────────────────────────────
    persistence_backend: PersistenceBackend = Field(
        default=PersistenceBackend.MEMORY,
        description="持久化后端：memory（默认）或 sqlite",
    )
    persistence_database_path: str = Field(
        default="local_state/persistence/powerbiagent.db",
        description="SQLite 数据库相对路径（persistence_backend=sqlite 时使用）",
    )
    report_artifacts_path: str = Field(
        default="local_state/reports",
        description="受管 HTML report 根目录；测试必须覆盖到临时目录",
    )
    kimi_input_cost_per_million_tokens: Optional[float] = Field(
        default=None, ge=0,
        description="Kimi 输入价格（美元/百万 Token）。未配置时 estimated_cost_usd=null",
    )
    kimi_output_cost_per_million_tokens: Optional[float] = Field(
        default=None, ge=0,
        description="Kimi 输出价格（美元/百万 Token）。未配置时 estimated_cost_usd=null",
    )
    presentation_localization_registry_path: str = Field(
        default="local_state/runtime/display_localizations.json",
        description="model/object/schema-scoped 展示本地化 registry",
    )

    @property
    def is_persistence_sqlite(self) -> bool:
        return self.persistence_backend == PersistenceBackend.SQLITE

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
        return bool(
            key
            and key.strip()
            and self.deepseek_base_url.strip()
            and self.deepseek_model.strip()
        )

    @property
    def is_kimi_configured(self) -> bool:
        if self.kimi_api_key is None:
            return False
        key = self.kimi_api_key.get_secret_value()
        return bool(
            key
            and key.strip()
            and self.kimi_base_url.strip()
            and self.kimi_model.strip()
        )

    def is_llm_profile_configured(self, profile_key: str) -> bool:
        if profile_key == "mock":
            return self.llm_mode == LLMMode.MOCK
        if profile_key == "deepseek":
            return self.is_deepseek_configured
        if profile_key == "kimi-k2.6":
            return self.is_kimi_configured
        return False

    @property
    def is_powerbi_local_mcp_configured(self) -> bool:
        """Local MCP 的非 Secret 启动配置是否完整且为只读。"""
        return (
            bool(self.powerbi_local_mcp_executable.strip())
            and bool(self.powerbi_local_mcp_package.strip())
            and bool(self.powerbi_local_semantic_model_key.strip())
            and self.powerbi_local_mcp_readonly
        )

    @property
    def is_real_ready(self) -> bool:
        """Real 模式的配置是否具备创建 Service 的条件。

        M1.5: DeepSeek + Mock Power BI 全链路已封板。
        DeepSeek 配置 Key 且 PowerBI 为 Mock 时 ready=true。
        M2.6: DeepSeek 配置 Key 且 Local MCP 启动配置完整时 ready=true。
        这是 configuration ready，不代表 Desktop 此刻 live connected；此属性
        不启动 MCP、不连接 Desktop、不读取 Schema。
        """
        if self.llm_mode in {LLMMode.DEEPSEEK, LLMMode.OPENAI_COMPATIBLE}:
            if not self.is_llm_profile_configured(self.llm_default_profile):
                return False
            if self.powerbi_mode == PowerBIMode.MOCK:
                return True
            if self.powerbi_mode == PowerBIMode.LOCAL_MCP:
                return self.is_powerbi_local_mcp_configured
            return False
        return self.powerbi_mode == PowerBIMode.MOCK

    @property
    def local_real_configuration_reasons(self) -> list[str]:
        """Return safe, value-free diagnostics for the supported Real stack."""
        reasons: list[str] = []
        if self.llm_mode not in {LLMMode.DEEPSEEK, LLMMode.OPENAI_COMPATIBLE}:
            reasons.append("llm_mode_requires_openai_compatible")
            reasons.append("llm_mode_requires_deepseek")  # legacy diagnostic alias
        if not self.is_llm_profile_configured(self.llm_default_profile):
            reasons.append("llm_default_profile_not_configured")
        if self.powerbi_mode != PowerBIMode.LOCAL_MCP:
            reasons.append("powerbi_mode_requires_local_mcp")
        if not self.is_powerbi_local_mcp_configured:
            reasons.append("powerbi_local_mcp_configuration_incomplete")
        if self.persistence_backend != PersistenceBackend.SQLITE:
            reasons.append("persistence_backend_requires_sqlite")
        if self.max_tool_calls != 8:
            reasons.append("max_tool_calls_requires_8")
        return reasons

    @property
    def is_local_real_configuration_complete(self) -> bool:
        """Whether the documented DeepSeek + Local MCP + SQLite stack is complete."""
        return not self.local_real_configuration_reasons

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
            "llm_default_profile": self.llm_default_profile,
            "powerbi_mode": self.powerbi_mode.value,
            "harness_mode": self.harness_mode.value,
            "version": self.version,
            "is_mock": self.is_mock,
            "is_real_ready": self.is_real_ready,
            "configuration_ready": self.is_real_ready,
            "deepseek_configured": self.is_deepseek_configured,
            "kimi_configured": self.is_kimi_configured,
            "powerbi_local_mcp_configured": self.is_powerbi_local_mcp_configured,
            "powerbi_local_mcp_readonly": self.powerbi_local_mcp_readonly,
            "persistence_backend": self.persistence_backend.value,
            "max_tool_calls": self.max_tool_calls,
            "local_real_configuration_complete": (
                self.is_local_real_configuration_complete
            ),
            "local_real_configuration_reasons": (
                self.local_real_configuration_reasons
            ),
        }


@lru_cache()
def get_settings() -> Settings:
    """获取全局 Settings 单例（缓存）"""
    return Settings()
