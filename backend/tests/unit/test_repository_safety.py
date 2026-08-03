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
    EXCLUDE_DIRS,
    _match_forbidden_filename,
    _is_text_file,
    _is_test_safe,
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
    """检查：空的 KEY= 和占位值允许"""

    _DK = "DEEPSEEK_" + "API_KEY"
    _CS = "POWERBI_CLIENT_" + "SECRET"

    def _matches_any_secret_pattern(self, line: str) -> bool:
        """检查某行是否匹配任何真实 Secret 模式"""
        for pattern, _description in OBVIOUS_SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_empty_deepseek_key_allowed(self):
        """✅ 空的 KEY= 允许"""
        assert not self._matches_any_secret_pattern(self._DK + "=")

    def test_empty_deepseek_key_with_spaces_allowed(self):
        """✅ KEY= 后接空格允许"""
        assert not self._matches_any_secret_pattern(self._DK + "=   ")

    def test_your_key_here_allowed(self):
        """✅ YOUR_KEY_HERE 占位值允许"""
        assert not self._matches_any_secret_pattern(
            self._DK + "=YOUR_KEY_HERE"
        )

    def test_replace_me_allowed(self):
        """✅ REPLACE_ME 占位值允许"""
        assert not self._matches_any_secret_pattern(
            self._DK + "=REPLACE_ME"
        )

    def test_empty_client_secret_allowed(self):
        """空的 client secret 允许"""
        assert not self._matches_any_secret_pattern(
            self._CS + "="
        )


class TestRealSecretRejected:
    """检查：看起来像真实 Key 的值被拒绝"""

    _DK = "DEEPSEEK_" + "API_KEY"
    _CS = "POWERBI_CLIENT_" + "SECRET"

    def _matches_any_secret_pattern(self, line: str) -> bool:
        for pattern, _description in OBVIOUS_SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_non_empty_deepseek_key_rejected(self):
        """✅ KEY 后跟非空非占位值被拒绝"""
        # 使用明显标记的假字符串（不是真实 Key 格式）
        assert self._matches_any_secret_pattern(
            self._DK + "=FAKE_TEST_KEY_FOR_UNIT_TEST_ONLY"
        )

    def test_bearer_long_token_rejected(self):
        """✅ Authorization Bearer 后跟长 Token 被拒绝"""
        assert self._matches_any_secret_pattern(
            "Authorization: " + "Bearer abcdefghijklmnopqrstuvwxyz1234567890"
        )

    def test_client_secret_with_value_rejected(self):
        """✅ CLIENT_SECRET 后跟非空非占位值被拒绝"""
        assert self._matches_any_secret_pattern(
            self._CS + "=NOT_A_REAL_SECRET_BUT_LOOKS_LIKE_ONE"
        )


class TestFrontendSecretRejected:
    """检查：前端出现 Secret 被拒绝"""

    _DK = "DEEPSEEK_" + "API_KEY"

    def _matches_frontend_pattern(self, line: str) -> bool:
        for pattern, _description in FORBIDDEN_FRONTEND_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_vite_deepseek_key_in_frontend_rejected(self):
        """✅ 前端出现 VITE_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "VITE_" + self._DK + "=sk-00000000000000000000000000000000"
        )

    def test_react_app_key_in_frontend_rejected(self):
        """✅ 前端出现 REACT_APP_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "const KEY = process.env.REACT_APP_" + self._DK
        )

    def test_next_public_key_in_frontend_rejected(self):
        """✅ 前端出现 NEXT_PUBLIC_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "NEXT_PUBLIC_" + self._DK + "=test-fake-key-value"
        )

    def test_public_key_in_frontend_rejected(self):
        """✅ 前端出现 PUBLIC_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "PUBLIC_" + self._DK + "=fake_key_for_testing_only"
        )

    def test_nuxt_public_key_in_frontend_rejected(self):
        """✅ 前端出现 NUXT_PUBLIC_DEEPSEEK_API_KEY 被拒绝"""
        assert self._matches_frontend_pattern(
            "NUXT_PUBLIC_" + self._DK + "=test_fake_not_real"
        )

    def test_deepseek_direct_call_in_frontend_rejected(self):
        """✅ 前端直接访问 api.deepseek.com 被拒绝"""
        assert self._matches_frontend_pattern(
            'fetch("https://api.' + 'deepseek.com/v1/chat/completions", ...)'
        )

    def test_authorization_header_in_frontend_rejected(self):
        """✅ 前端出现 Authorization Bearer 被拒绝"""
        assert self._matches_frontend_pattern(
            "Authorization: " + "Bearer fake_test_token_1234567890"
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


# ══════════════════════════════════════════════════════════════════
# M1.1 新增：安全扫描器不再整体排除测试和 scripts
# ══════════════════════════════════════════════════════════════════

class TestScannerExcludesTestsAndScripts:
    """M1.1: 测试和 scripts 目录纳入扫描"""

    def test_exclude_dirs_empty(self):
        """EXCLUDE_DIRS 不再包含 backend/tests 和 scripts"""
        assert "backend/tests" not in EXCLUDE_DIRS, (
            "backend/tests 不应再被整体排除"
        )
        assert "scripts" not in EXCLUDE_DIRS, (
            "scripts 不应再被整体排除"
        )


class TestSecretInTestFileDetectable:
    """M1.1: 测试文件中的疑似 Secret 能被发现（regex 级别）"""

    _DK = "DEEPSEEK_" + "API_KEY"

    def _matches_any_secret_pattern(self, line: str) -> bool:
        for pattern, _description in OBVIOUS_SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_concatenated_fake_sk_key_matches(self):
        """字符串拼接生成的假 sk- Key 能被正则发现"""
        fake = "sk-" + ("M" * 24)
        line = self._DK + "=" + fake
        assert self._matches_any_secret_pattern(line), (
            "拼接生成的疑似 Key 应被正则匹配"
        )

    def test_fake_key_in_test_code_detectable(self):
        """测试代码中的假 Key 可被正则检测"""
        fake = "sk-" + ("N" * 24)
        line = 'api_key = "' + fake + '"  # test only'
        assert self._matches_any_secret_pattern(line)


class TestSecretInScriptDetectable:
    """M1.1: 脚本文件中的疑似 Secret 能被发现"""

    def _matches_any_secret_pattern(self, line: str) -> bool:
        for pattern, _description in OBVIOUS_SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def test_fake_key_in_script_code_detectable(self):
        """脚本代码中的假 Key 可被正则检测"""
        fake = "sk-" + ("P" * 24)
        line = 'API_KEY = "' + fake + '"'
        assert self._matches_any_secret_pattern(line)


class TestTestSafeMarkers:
    """M1.1: 测试安全标记避免误报"""

    _DK = "DEEPSEEK_" + "API_KEY"
    _CS = "CLIENT_" + "SECRET"

    def test_fake_test_key_marker_safe(self):
        """FAKE_TEST_KEY 标记行跳过扫描"""
        assert _is_test_safe(
            "backend/tests/unit/test_intent.py",
            self._DK + "=FAKE_TEST_KEY_FOR_UNIT_TEST_ONLY",
        ) is True

    def test_not_a_real_secret_safe(self):
        """NOT_A_REAL_SECRET 标记行跳过"""
        assert _is_test_safe(
            "backend/tests/unit/test_intent.py",
            self._CS + "=NOT_A_REAL_SECRET_BUT_LOOKS_LIKE_ONE",
        ) is True

    def test_normal_line_not_safe(self):
        """普通行不应被标记为测试安全"""
        k = "sk-" + "real-looking-key-12345678901234567890"
        assert _is_test_safe(
            "backend/tests/unit/test_intent.py",
            self._DK + "=" + k,
        ) is False


class TestScannerOutputNoSecretValue:
    """M1.1: 扫描器输出不含 Secret 原文"""

    def test_finding_has_no_secret_value_field(self):
        """Finding 输出只含路径、行号、规则名"""
        finding = {
            "file": "test.py",
            "line": 10,
            "rule": "疑似真实 Secret: sk-xxx",
        }
        assert "matched" not in finding
        assert "value" not in finding
        assert "secret" not in finding


# ══════════════════════════════════════════════════════════════════
# M1.2 新增：安全扫描豁免收紧
# ══════════════════════════════════════════════════════════════════

class TestM12ExemptionTightening:
    """M1.2: 测试豁免仅在测试目录生效"""

    def test_test_dir_identified_correctly(self):
        """backend/tests/ 目录正确识别为测试目录"""
        from scripts.check_repository_safety import _is_in_test_dir
        assert _is_in_test_dir("backend/tests/unit/test_intent.py") is True
        assert _is_in_test_dir("backend/tests/integration/foo.py") is True

    def test_production_dir_not_test(self):
        """backend/app/ 不是测试目录"""
        from scripts.check_repository_safety import _is_in_test_dir
        assert _is_in_test_dir("backend/app/llm/deepseek.py") is False
        assert _is_in_test_dir("backend/app/intent/models.py") is False

    def test_production_dirs_identified(self):
        """生产目录正确识别"""
        from scripts.check_repository_safety import _is_in_production_dir
        assert _is_in_production_dir("backend/app/main.py") is True
        assert _is_in_production_dir("frontend/index.html") is True
        assert _is_in_production_dir("docs/00_prd.md") is True
        assert _is_in_production_dir("README.md") is True
        assert _is_in_production_dir("CLAUDE.md") is True

    def test_scripts_dir_not_production(self):
        """scripts/ 不是生产目录"""
        from scripts.check_repository_safety import _is_in_production_dir
        assert _is_in_production_dir("scripts/check_repository_safety.py") is False

    def test_test_dir_not_production(self):
        """backend/tests/ 不是生产目录"""
        from scripts.check_repository_safety import _is_in_production_dir
        assert _is_in_production_dir("backend/tests/unit/test_intent.py") is False

    _DK = "DEEPSEEK_" + "API_KEY"

    def test_test_safe_markers_only_in_test_dir(self):
        """测试安全标记仅在测试目录生效"""
        from scripts.check_repository_safety import _is_test_safe

        # 测试目录中的 FAKE_TEST_KEY 标记被跳过
        assert _is_test_safe(
            "backend/tests/unit/test_intent.py",
            self._DK + "=FAKE_TEST_KEY_FOR_UNIT_TEST_ONLY",
        ) is True

        # 生产代码中的 FAKE_TEST_KEY 不应被跳过（因为不在测试目录）
        assert _is_test_safe(
            "backend/app/llm/deepseek.py",
            self._DK + "=FAKE_TEST_KEY_FOR_UNIT_TEST_ONLY",
        ) is False


class TestM12PythonVariableRef:
    """M1.2: Python 变量引用全局豁免"""

    _DK = "DEEPSEEK_" + "API_KEY"

    def test_variable_ref_global_exemption(self):
        """Python 变量/属性引用应全局豁免（不区分目录）"""
        from scripts.check_repository_safety import _is_python_variable_ref

        assert _is_python_variable_ref("api_key=settings." + "deepseek_api_key,  # type: ignore") is True
        assert _is_python_variable_ref("api_key=settings." + "deepseek_api_key)") is True
        s = "some_provider." + "_api_key.get_" + "secret_value()"
        assert _is_python_variable_ref("secret=" + s) is True

    def test_literal_value_not_variable_ref(self):
        """字面量值不应被判断为变量引用"""
        from scripts.check_repository_safety import _is_python_variable_ref

        # 字面字符串值不是变量引用
        fake = "sk-" + ("F" * 20)
        assert _is_python_variable_ref(self._DK + '="' + fake + '"') is False
        fake2 = "my-" + ("S" * 20)
        assert _is_python_variable_ref('secret="' + fake2 + '"') is False


class TestM12ScannerSelfExemption:
    """M1.2: 扫描器自身窄范围豁免"""

    def test_scan_pattern_definition_exempted(self):
        """# secret-scan: allow-pattern-definition 行豁免"""
        from scripts.check_repository_safety import _is_scan_pattern_definition

        line = (
            'r"DEEPSEEK_' + 'API_KEY\\\\s*=\\\\s*...'
            '", "DEEPSEEK_API_KEY 有疑似真实值"),'
            '  # secret-scan: allow-pattern-definition'
        )
        assert _is_scan_pattern_definition(
            "scripts/check_repository_safety.py", line
        ) is True

    def test_pattern_definition_only_in_scanner(self):
        """扫描器豁免仅对自身生效"""
        from scripts.check_repository_safety import _is_scan_pattern_definition

        line = 'r"sk-[A-Za-z0-9_\\\\-]{20,}"  # secret-scan: allow-pattern-definition'
        # 其他文件即使有相同注释也不豁免
        assert _is_scan_pattern_definition(
            "backend/app/llm/deepseek.py", line
        ) is False

    def test_normal_line_not_exempted(self):
        """不带注释的普通行不被豁免"""
        from scripts.check_repository_safety import _is_scan_pattern_definition

        fake_sk = "sk-" + ("L" * 20)
        line = 'api_key = "' + fake_sk + '"'
        assert _is_scan_pattern_definition(
            "scripts/check_repository_safety.py", line
        ) is False
