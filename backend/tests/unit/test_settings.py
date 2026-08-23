"""Settings 测试 — 动态版本一致性 + 通用 Settings 验证"""

import os
import re
import subprocess
from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.app.config.settings import (
    AppEnv,
    HarnessMode,
    LLMMode,
    PowerBIMode,
    Settings,
    get_settings,
)
from backend.app.config.startup_diagnostics import (
    inspect_dotenv_format,
    safe_startup_summary,
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

    def test_version_is_non_empty(self):
        settings = Settings()
        assert settings.version
        assert len(settings.version) >= 3

    def test_host_default_localhost(self):
        settings = Settings()
        assert settings.host == "127.0.0.1"

    def test_port_default_8000(self):
        settings = Settings()
        assert settings.port == 8000

    def test_local_mcp_uses_pinned_readonly_defaults(self):
        default_settings = Settings(_env_file=None)
        assert default_settings.powerbi_local_mcp_executable == "npx"
        assert default_settings.powerbi_local_mcp_package == (
            "@microsoft/powerbi-modeling-mcp@0.5.0-beta.12"
        )
        assert (
            default_settings.powerbi_local_semantic_model_key
            == "local_desktop_model"
        )
        assert default_settings.powerbi_local_mcp_readonly is True


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

    def test_env_override_powerbi_local_mcp_executable(self, monkeypatch):
        monkeypatch.setenv("POWERBI_LOCAL_MCP_EXECUTABLE", "local-mcp-placeholder")
        settings = Settings()
        assert settings.powerbi_local_mcp_executable == "local-mcp-placeholder"


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
        fake_key = "sk-" + ("T" * 15) + "-" + ("k" * 10)
        settings = Settings(deepseek_api_key=fake_key)
        safe = settings.safe_repr()
        assert "deepseek_api_key" not in safe
        assert "api_key" not in str(safe)

    def test_str_repr_no_secret(self):
        fake_key = "sk-" + ("T" * 15) + "-" + ("k" * 10)
        settings = Settings(deepseek_api_key=fake_key)
        r = repr(settings)
        # SecretStr repr 不应暴露实际值
        assert fake_key not in r

    def test_dict_no_secret_leak(self):
        """model_dump 包含 SecretStr 但值是 SecretStr 对象，不是明文"""
        fake_key = "sk-" + ("T" * 15) + "-" + ("k" * 10)
        settings = Settings(deepseek_api_key=fake_key)
        dumped = settings.model_dump()
        # SecretStr 导出时应为占位符或对象（不应是明文字符串）
        val = dumped.get("deepseek_api_key")
        if val is not None:
            assert str(val) != fake_key

    def test_default_no_api_key(self):
        settings = Settings(
            deepseek_api_key=None,
            llm_mode="mock",
            powerbi_mode="mock",
        )
        # 显式传 None 应视为无 Key（覆盖 .env 中的值）
        assert (
            settings.deepseek_api_key is None
            or settings.deepseek_api_key.get_secret_value() == ""
        )

    def test_powerbi_values_and_secret_stay_out_of_safe_repr(self):
        fake_tenant = "tenant-value-must-not-appear"
        fake_client = "client-value-must-not-appear"
        fake_secret = "secret-value-must-not-appear"
        settings = Settings(
            powerbi_tenant_id=fake_tenant,
            powerbi_client_id=fake_client,
            powerbi_client_secret=SecretStr(fake_secret),
        )
        safe_text = str(settings.safe_repr())
        assert fake_tenant not in safe_text
        assert fake_client not in safe_text
        assert fake_secret not in safe_text


class TestSettingsRealMode:
    """Real 模式检查"""

    def test_mock_mode_is_real_ready(self):
        settings = Settings(llm_mode=LLMMode.MOCK, powerbi_mode=PowerBIMode.MOCK)
        assert settings.is_real_ready is True

    def test_deepseek_mode_not_real_ready_without_key(self):
        """M1.5: DeepSeek 模式无 Key → not ready（需显式覆盖 .env）"""
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=None,
        )
        assert settings.is_real_ready is False

    def test_deepseek_mode_real_ready_with_key(self):
        """M1.5: DeepSeek+Mock 有 Key → ready"""
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=SecretStr("test-key-not-real"),
        )
        assert settings.is_real_ready is True

    def test_remote_mcp_mode_not_real_ready(self):
        """M0.4: Remote MCP 模式尚未实现，不应返回 ready"""
        settings = Settings(llm_mode=LLMMode.MOCK, powerbi_mode=PowerBIMode.REMOTE_MCP)
        assert settings.is_real_ready is False

    def test_mock_llm_plus_local_mcp_is_not_product_chat_mode(self):
        settings = Settings(llm_mode=LLMMode.MOCK, powerbi_mode=PowerBIMode.LOCAL_MCP)
        assert settings.is_real_ready is False
        assert settings.is_powerbi_local_mcp_configured is True

    def test_deepseek_plus_local_mcp_is_configuration_ready(self):
        settings = Settings(
            _env_file=None,
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            deepseek_api_key=SecretStr("test-key-not-real"),
        )
        assert settings.is_real_ready is True

    def test_deepseek_plus_local_requires_readonly_local_configuration(self):
        settings = Settings(
            _env_file=None,
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            deepseek_api_key=SecretStr("test-key-not-real"),
            powerbi_local_mcp_readonly=False,
        )
        assert settings.is_real_ready is False

    def test_full_real_not_ready(self):
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.REMOTE_MCP,
        )
        assert settings.is_real_ready is False

    def test_local_mcp_configuration_requires_readonly_and_non_empty_command(self):
        configured = Settings(_env_file=None)
        writable = configured.model_copy(update={"powerbi_local_mcp_readonly": False})
        missing_command = configured.model_copy(
            update={"powerbi_local_mcp_executable": ""}
        )
        missing_model_key = configured.model_copy(
            update={"powerbi_local_semantic_model_key": ""}
        )
        assert configured.is_powerbi_local_mcp_configured is True
        assert writable.is_powerbi_local_mcp_configured is False
        assert missing_command.is_powerbi_local_mcp_configured is False
        assert missing_model_key.is_powerbi_local_mcp_configured is False

    def test_local_real_diagnostics_require_sqlite_readonly_and_tool_budget(self):
        configured = Settings(
            _env_file=None,
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            persistence_backend="sqlite",
            deepseek_api_key=SecretStr("test-key-not-real"),
            max_tool_calls=8,
        )
        assert configured.is_local_real_configuration_complete is True
        assert configured.local_real_configuration_reasons == []

        incomplete = configured.model_copy(
            update={"persistence_backend": "memory", "max_tool_calls": 3}
        )
        assert incomplete.is_local_real_configuration_complete is False
        assert "persistence_backend_requires_sqlite" in (
            incomplete.local_real_configuration_reasons
        )
        assert "max_tool_calls_requires_8" in (
            incomplete.local_real_configuration_reasons
        )


class TestStartupDiagnostics:
    def test_dotenv_format_reports_only_invalid_line_numbers(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "# comment\nLLM_MODE=deepseek\n\nnot-an-assignment\n",
            encoding="utf-8",
        )
        result = inspect_dotenv_format(env_path)
        assert result.exists is True
        assert result.valid is False
        assert result.invalid_line_numbers == (4,)
        assert "deepseek" not in repr(result)

    def test_safe_summary_never_contains_secret_value(self):
        secret = "secret-value-must-not-appear"
        settings = Settings(_env_file=None, deepseek_api_key=SecretStr(secret))
        summary = safe_startup_summary(settings)
        assert summary["deepseek_configured"] is True
        assert secret not in str(summary)


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


class TestVersionConsistency:
    """动态版本一致性 — CI 通用门禁（替代固定版本号的文档一致性检查）"""

    def test_settings_version_is_major_minor_patch(self):
        """版本号格式：M主版本.次版本[.修订版本]"""
        s = Settings()
        assert re.match(r"^M\d+\.\d+(\.\d+)?$", s.version), (
            f"Settings.version={s.version} 格式不符合 Mx.y 或 Mx.y.z"
        )

    def test_readme_contains_current_version(self):
        """README 当前状态标注必须包含 Settings.version"""
        s = Settings()
        readme = (Path(__file__).parent.parent.parent.parent / "README.md").read_text(encoding="utf-8")
        assert s.version in readme, f"README.md 未包含版本号 {s.version}"

    def test_docs_08_header_contains_current_version(self):
        """docs/08 状态行必须包含 Settings.version"""
        s = Settings()
        roadmap = (Path(__file__).parent.parent.parent.parent / "docs/08_development_roadmap.md").read_text(encoding="utf-8")
        status_line = roadmap.split("状态：")[1].split("\n")[0] if "状态：" in roadmap else ""
        assert s.version in status_line, (
            f"docs/08 状态行未包含版本号 {s.version}，当前: {status_line}"
        )

    def test_docs_09_current_phase_contains_current_version(self):
        """docs/09 当前阶段必须包含 Settings.version"""
        s = Settings()
        handoff = (Path(__file__).parent.parent.parent.parent / "docs/09_context_handoff.md").read_text(encoding="utf-8")
        phase_section = handoff.split("当前阶段")[1][:120] if "当前阶段" in handoff else ""
        assert s.version in phase_section, (
            f"docs/09 当前阶段未包含版本号 {s.version}"
        )

    def test_no_two_versions_both_in_progress(self):
        """docs/08 中不得同时存在两个版本标记为"进行中" """
        roadmap = (Path(__file__).parent.parent.parent.parent / "docs/08_development_roadmap.md").read_text(encoding="utf-8")
        in_progress = set()
        for m in re.finditer(r"(M\d+\.\d+(?:\.\d+)?).*进行中", roadmap):
            in_progress.add(m.group(1))
        assert len(in_progress) <= 1, f"多个版本同时进行中: {in_progress}"

    def test_dotenv_not_tracked_by_git(self):
        """.env 不得被 Git 跟踪"""
        r = subprocess.run(["git", "ls-files", ".env"], capture_output=True, text=True)
        assert r.stdout.strip() == "", ".env 被 Git 跟踪！"
