"""Settings 测试 — M0.4"""

import os

import pytest

from backend.app.config.settings import (
    AppEnv,
    HarnessMode,
    LLMMode,
    PowerBIMode,
    Settings,
    get_settings,
)


class TestSettingsDefaults:
    """默认 Mock 配置"""

    def test_defaults_are_mock(self):
        settings = Settings()
        assert settings.llm_mode == LLMMode.MOCK
        assert settings.powerbi_mode == PowerBIMode.MOCK
        assert settings.is_mock is True

    def test_default_env_is_development(self):
        settings = Settings()
        assert settings.app_env == AppEnv.DEVELOPMENT

    def test_app_name_is_powerbiagent(self):
        settings = Settings()
        assert settings.app_name == "PowerBIAgent"

    def test_version_is_m1_0(self):
        settings = Settings()
        assert settings.version == "M1.0"

    def test_host_default_localhost(self):
        settings = Settings()
        assert settings.host == "127.0.0.1"

    def test_port_default_8000(self):
        settings = Settings()
        assert settings.port == 8000


class TestSettingsEnvOverride:
    """环境变量覆盖"""

    def test_env_override_llm_mode(self, monkeypatch):
        monkeypatch.setenv("LLM_MODE", "deepseek")
        settings = Settings()
        assert settings.llm_mode == LLMMode.DEEPSEEK

    def test_env_override_app_env(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        settings = Settings()
        assert settings.app_env == AppEnv.PRODUCTION

    def test_env_override_port(self, monkeypatch):
        monkeypatch.setenv("PORT", "9090")
        settings = Settings()
        assert settings.port == 9090

    def test_env_override_host(self, monkeypatch):
        monkeypatch.setenv("HOST", "0.0.0.0")
        settings = Settings()
        assert settings.host == "0.0.0.0"

    def test_env_override_debug(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "false")
        settings = Settings()
        assert settings.debug is False

    def test_env_override_log_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "warning")
        settings = Settings()
        assert settings.log_level == "warning"


class TestSettingsValidation:
    """Settings 校验"""

    def test_invalid_llm_mode_rejected(self, monkeypatch):
        monkeypatch.setenv("LLM_MODE", "openai")
        with pytest.raises(ValueError):
            Settings()

    def test_invalid_app_env_rejected(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "staging")
        with pytest.raises(ValueError):
            Settings()

    def test_invalid_harness_mode_rejected(self, monkeypatch):
        monkeypatch.setenv("HARNESS_MODE", "lax")
        with pytest.raises(ValueError):
            Settings()

    def test_port_below_1_rejected(self, monkeypatch):
        monkeypatch.setenv("PORT", "0")
        with pytest.raises(ValueError):
            Settings()

    def test_max_tool_calls_below_1_rejected(self, monkeypatch):
        monkeypatch.setenv("MAX_TOOL_CALLS", "0")
        with pytest.raises(ValueError):
            Settings()


class TestSettingsNoSecretLeak:
    """不泄露 Secret"""

    def test_safe_repr_no_secret(self):
        settings = Settings(deepseek_api_key="sk-test-key-12345")
        safe = settings.safe_repr()
        assert "deepseek_api_key" not in safe
        assert "api_key" not in str(safe)

    def test_str_repr_no_secret(self):
        settings = Settings(deepseek_api_key="sk-test-key-12345")
        r = repr(settings)
        # SecretStr repr 不应暴露实际值
        assert "sk-test-key-12345" not in r

    def test_dict_no_secret_leak(self):
        """model_dump 包含 SecretStr 但值是 SecretStr 对象，不是明文"""
        settings = Settings(deepseek_api_key="sk-test-key-12345")
        dumped = settings.model_dump()
        # SecretStr 导出时应为占位符或对象（不应是明文字符串）
        val = dumped.get("deepseek_api_key")
        if val is not None:
            assert str(val) != "sk-test-key-12345"

    def test_default_no_api_key(self):
        settings = Settings()
        # 未设置或为空均视为无 Key
        assert (
            settings.deepseek_api_key is None
            or settings.deepseek_api_key.get_secret_value() == ""
        )


class TestSettingsRealMode:
    """Real 模式检查"""

    def test_mock_mode_is_real_ready(self):
        settings = Settings(llm_mode=LLMMode.MOCK, powerbi_mode=PowerBIMode.MOCK)
        assert settings.is_real_ready is True

    def test_deepseek_mode_not_real_ready(self):
        """M0.4: DeepSeek 模式尚未实现，不应返回 ready"""
        settings = Settings(llm_mode=LLMMode.DEEPSEEK, powerbi_mode=PowerBIMode.MOCK)
        assert settings.is_real_ready is False

    def test_remote_mcp_mode_not_real_ready(self):
        """M0.4: Remote MCP 模式尚未实现，不应返回 ready"""
        settings = Settings(llm_mode=LLMMode.MOCK, powerbi_mode=PowerBIMode.REMOTE_MCP)
        assert settings.is_real_ready is False

    def test_full_real_not_ready(self):
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.REMOTE_MCP,
        )
        assert settings.is_real_ready is False


class TestSettingsIsolation:
    """Settings 测试隔离"""

    def test_monkeypatch_does_not_pollute(self):
        """环境变量修改不污染其他测试"""
        settings1 = Settings()
        original_mode = settings1.llm_mode

        settings2 = Settings(llm_mode=LLMMode.DEEPSEEK)
        assert settings2.llm_mode == LLMMode.DEEPSEEK

        # 第一个 settings 不变
        assert settings1.llm_mode == original_mode


class TestGetSettingsCache:
    """get_settings 缓存"""

    def test_get_settings_returns_same_instance(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
