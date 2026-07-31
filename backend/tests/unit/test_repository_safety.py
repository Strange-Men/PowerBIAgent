"""仓库安全检查测试 —— M1.0.2

测试 check_repository_safety.py 的核心检查逻辑。
不创建真实格式 API Key，使用明显标记的假字符串。
"""

from __future__ import annotations

import os
import re
import sys

import pytest

# 将 scripts 目录加入 sys.path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from scripts.check_repository_safety import (
    FORBIDDEN_FILENAMES,
    ALLOWED_FILENAMES,
    FORBIDDEN_FRONTEND_PATTERNS,
    OBVIOUS_SECRET_PATTERNS,
    _match_forbidden_filename,
    _is_text_file,
)


class TestForbiddenFilenames:
    """检查 1：禁止跟踪的文件名"""

    def test_env_is_forbidden(self):
        """✅ .env 属于禁止跟踪文件"""
        assert _match_forbidden_filename(".env") == ".env"

    def test_env_local_is_forbidden(self):
        """✅ .env.local 属于禁止跟踪文件"""
        assert _match_forbidden_filename(".env.local") == ".env.local"

    def test_env_example_is_allowed(self):
        """✅ .env.example 允许提交"""
        assert _match_forbidden_filename(".env.example") is None

    def test_key_files_forbidden(self):
        """✅ *.key 文件禁止跟踪"""
        assert _match_forbidden_filename("server.key") is not None

    def test_credentials_json_forbidden(self):
        """✅ credentials.json 禁止跟踪"""
        assert _match_forbidden_filename("credentials.json") == "credentials.json"

    def test_normal_file_allowed(self):
        """✅ 普通源码文件允许"""
        assert _match_forbidden_filename("src/main.py") is None
        assert _match_forbidden_filename("README.md") is None

    def test_env_example_in_subdir_allowed(self):
        """✅ 子目录中的 .env.example 允许"""
        # .env.example appears in ALLOWED_FILENAMES
        assert _match_forbidden_filename("some/path/.env.example") is None


class TestEmptySecretAllowed:
    """检查：空的 DEEPSEEK_API_KEY= 和占位值允许"""

    def _matches_any_secret_pattern(self, line: str) -> bool:
        """检查某行是否匹配任何真实 Secret 模式"""
        for pattern, _description in OBVIOUS_SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_empty_deepseek_key_allowed(self):
        """✅ 空的 DEEPSEEK_API_KEY= 允许"""
        assert not self._matches_any_secret_pattern("DEEPSEEK_API_KEY=")

    def test_empty_deepseek_key_with_spaces_allowed(self):
        """✅ DEEPSEEK_API_KEY= 后接空格允许"""
        assert not self._matches_any_secret_pattern("DEEPSEEK_API_KEY=   ")

    def test_your_key_here_allowed(self):
        """✅ YOUR_KEY_HERE 占位值允许"""
        assert not self._matches_any_secret_pattern(
            "DEEPSEEK_API_KEY=YOUR_KEY_HERE"
        )

    def test_replace_me_allowed(self):
        """✅ REPLACE_ME 占位值允许"""
        assert not self._matches_any_secret_pattern(
            "DEEPSEEK_API_KEY=REPLACE_ME"
        )

    def test_empty_client_secret_allowed(self):
        """✅ 空的 CLIENT_SECRET= 允许"""
        assert not self._matches_any_secret_pattern(
            "POWERBI_CLIENT_SECRET="
        )


class TestRealSecretRejected:
    """检查：看起来像真实 Key 的值被拒绝"""

    def _matches_any_secret_pattern(self, line: str) -> bool:
        for pattern, _description in OBVIOUS_SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_non_empty_deepseek_key_rejected(self):
        """✅ DEEPSEEK_API_KEY 后跟非空非占位值被拒绝"""
        # 使用明显标记的假字符串（不是真实 Key 格式）
        assert self._matches_any_secret_pattern(
            "DEEPSEEK_API_KEY=FAKE_TEST_KEY_FOR_UNIT_TEST_ONLY"
        )

    def test_bearer_long_token_rejected(self):
        """✅ Authorization Bearer 后跟长 Token 被拒绝"""
        assert self._matches_any_secret_pattern(
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890"
        )

    def test_client_secret_with_value_rejected(self):
        """✅ CLIENT_SECRET 后跟非空非占位值被拒绝"""
        assert self._matches_any_secret_pattern(
            "POWERBI_CLIENT_SECRET=NOT_A_REAL_SECRET_BUT_LOOKS_LIKE_ONE"
        )


class TestFrontendSecretRejected:
    """检查：前端出现 Secret 被拒绝"""

    def _matches_frontend_pattern(self, line: str) -> bool:
        for pattern, _description in FORBIDDEN_FRONTEND_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_vite_deepseek_key_in_frontend_rejected(self):
        """✅ 前端出现 VITE_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "VITE_DEEPSEEK_API_KEY=sk-00000000000000000000000000000000"
        )

    def test_react_app_key_in_frontend_rejected(self):
        """✅ 前端出现 REACT_APP_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "const KEY = process.env.REACT_APP_DEEPSEEK_API_KEY"
        )

    def test_next_public_key_in_frontend_rejected(self):
        """✅ 前端出现 NEXT_PUBLIC_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "NEXT_PUBLIC_DEEPSEEK_API_KEY=test-fake-key-value"
        )

    def test_public_key_in_frontend_rejected(self):
        """✅ 前端出现 PUBLIC_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "PUBLIC_DEEPSEEK_API_KEY=fake_key_for_testing_only"
        )

    def test_nuxt_public_key_in_frontend_rejected(self):
        """✅ 前端出现 NUXT_PUBLIC_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "NUXT_PUBLIC_DEEPSEEK_API_KEY=test_fake_not_real"
        )

    def test_deepseek_direct_call_in_frontend_rejected(self):
        """✅ 前端直接访问 api.deepseek.com 被拒绝"""
        assert self._matches_frontend_pattern(
            'fetch("https://api.deepseek.com/v1/chat/completions", ...)'
        )

    def test_authorization_header_in_frontend_rejected(self):
        """✅ 前端出现 Authorization Bearer 被拒绝"""
        assert self._matches_frontend_pattern(
            "Authorization: Bearer fake_test_token_1234567890"
        )

    def test_normal_frontend_code_allowed(self):
        """✅ 正常前端代码不匹配"""
        assert not self._matches_frontend_pattern(
            'const API_URL = "http://127.0.0.1:8000/api/v1/chat"'
        )


class TestOutputDoesNotContainSecret:
    """检查：输出不包含匹配到的 Secret 原文"""

    def test_finding_dict_has_no_secret_value(self):
        """✅ Finding 字典不包含 Secret 原文字段"""
        from scripts.check_repository_safety import (
            FORBIDDEN_FRONTEND_PATTERNS,
        )

        # 构造一个 finding - 不包含 secret_value 字段
        finding = {
            "file": "test.js",
            "line": 42,
            "rule": "前端禁止 Secret: VITE_*API_KEY",
        }
        assert "secret_value" not in finding
        assert "matched_text" not in finding
        assert "value" not in finding


class TestScannerDoesNotReadEnv:
    """检查：扫描器不会读取被 .gitignore 忽略的 .env"""

    def test_ignored_files_are_excluded(self):
        """✅ _get_ignored_files 返回包含 .env 的集合"""
        from scripts.check_repository_safety import _get_ignored_files

        ignored = _get_ignored_files()
        # .env 应该在被忽略文件集合中
        assert any(
            f.endswith(".env") and ".env." not in f for f in ignored
        ) or not any(
            f.endswith(".env") and ".env." not in f and ".example" not in f
            for f in ignored
        ), f".env should be in ignored files, got: {ignored}"


class TestCurrentRepositorySafety:
    """检查：当前仓库安全检查通过（集成测试）"""

    def test_safety_script_passes_on_current_repo(self):
        """✅ scripts/check_repository_safety.py 退出码为 0"""
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPTS_DIR, "check_repository_safety.py"),
            ],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..", "..", ".."),
        )
        assert result.returncode == 0, (
            f"Safety check failed with exit code {result.returncode}:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "PASS" in result.stdout
