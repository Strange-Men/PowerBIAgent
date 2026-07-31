#!/usr/bin/env python3
"""仓库安全检查 —— M1.0.2

检查 Git 已跟踪文件和暂存文件是否包含：
- 禁止跟踪的文件名
- 前端 Secret
- 明显真实 Secret

脚本绝不读取 .env 或被 .gitignore 忽略的文件。
输出只包含文件路径、行号和规则名称，不输出匹配到的 Secret 原文。

退出码：
  0 — 安全
  非 0 — 发现风险
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# 禁止被 Git 跟踪的文件名（支持通配符）
FORBIDDEN_FILENAMES: list[str] = [
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "*.key",
    "*.pem",
    "credentials.json",
    "token.json",
    "secrets.yaml",
    "*.har",
]

# 允许被跟踪的文件名（覆盖 FORBIDDEN_FILENAMES）
ALLOWED_FILENAMES: list[str] = [
    ".env.example",
]

# 前端目录
FRONTEND_DIRS: list[str] = ["frontend"]

# 排除目录（不检查这些目录中的文件）
EXCLUDE_DIRS: list[str] = [
    "backend/tests",
    "scripts",
]

# 前端禁止的 Secret 模式 (pattern, description)
FORBIDDEN_FRONTEND_PATTERNS: list[tuple[str, str]] = [
    (r"DEEPSEEK_API_KEY\s*=\s*\S", "DEEPSEEK_API_KEY 赋值"),
    (r"DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY 引用"),
    (r"VITE_[A-Z_]*API[_-]?KEY", "VITE_*API_KEY"),
    (r"REACT_APP_[A-Z_]*API[_-]?KEY", "REACT_APP_*API_KEY"),
    (r"NEXT_PUBLIC_[A-Z_]*API[_-]?KEY", "NEXT_PUBLIC_*API_KEY"),
    (r"PUBLIC_[A-Z_]*API[_-]?KEY", "PUBLIC_*API_KEY"),
    (r"NUXT_PUBLIC_[A-Z_]*API[_-]?KEY", "NUXT_PUBLIC_*API_KEY"),
    (r"Authorization:\s*Bearer\s+\S", "Authorization Bearer Token"),
    (r"api\.deepseek\.com", "DeepSeek API 直接调用"),
]

# 明显真实 Secret 模式（适用于所有已跟踪/已暂存文件）
# 注意：不输出捕获到的具体值
OBVIOUS_SECRET_PATTERNS: list[tuple[str, str]] = [
    # DEEPSEEK_API_KEY 后跟非空非占位值
    (r"DEEPSEEK_API_KEY\s*=\s*(?!\s*$)(?!\s*YOUR_KEY_HERE\b)(?!\s*REPLACE_ME\b)(?!\s*EXAMPLE_ONLY\b)(?!\s*your_)", "DEEPSEEK_API_KEY 有疑似真实值"),
    # Authorization Bearer 后跟长 Token（>20 字符）
    (r"Authorization:\s*Bearer\s+[A-Za-z0-9_\-\.]{20,}", "Authorization Bearer 长 Token"),
    # sk- 后跟明显长随机字符串
    (r"sk-[A-Za-z0-9_\-]{20,}", "疑似 OpenAI/DeepSeek 格式 Key"),
    # Microsoft / Azure Client Secret
    (r"CLIENT_SECRET\s*=\s*(?!\s*$)(?!\s*YOUR_KEY_HERE\b)(?!\s*REPLACE_ME\b)(?!\s*EXAMPLE_ONLY\b)(?!\s*your_)", "CLIENT_SECRET 有疑似真实值"),
    # 通用 secret/key/token 后跟长随机字符串
    (r"(?:secret|api_key|apikey|token|password)\s*[=:]\s*[A-Za-z0-9_\-\.\+/]{20,}", "通用凭据有疑似真实值"),
]

# 占位值（允许）
PLACEHOLDER_VALUES = {
    "YOUR_KEY_HERE",
    "REPLACE_ME",
    "EXAMPLE_ONLY",
    "your_deepseek_api_key_here",
    "your_tenant_id_here",
    "your_client_id_here",
    "your_client_secret_here",
}

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _is_text_file(filepath: Path) -> bool:
    """判断文件是否为文本文件（非二进制）。"""
    try:
        content = filepath.read_text(encoding="utf-8")
        # 检测 null 字节（二进制文件标志）
        if "\x00" in content:
            return False
        return True
    except (UnicodeDecodeError, OSError):
        return False


def _get_tracked_files() -> list[str]:
    """获取 Git 已跟踪的文件列表（相对路径）。"""
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(f"ERROR: git ls-files failed: {result.stderr}")
        sys.exit(1)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_staged_files() -> list[str]:
    """获取 Git 暂存区文件列表（相对路径）。"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(f"ERROR: git diff --cached failed: {result.stderr}")
        sys.exit(1)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_ignored_files() -> set[str]:
    """获取被 Git 忽略的文件列表。"""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _is_in_frontend_dir(filepath: str) -> bool:
    """检查文件是否在前端目录中。"""
    for d in FRONTEND_DIRS:
        if filepath.startswith(d + "/") or filepath.startswith(d + "\\"):
            return True
    return False


def _is_allowed_filename(filename: str) -> bool:
    """检查文件名是否在允许列表中。"""
    for allowed in ALLOWED_FILENAMES:
        if filename == allowed or filename.endswith("/" + allowed):
            return True
    return False


def _match_forbidden_filename(filepath: str) -> str | None:
    """检查文件路径是否匹配禁止跟踪的模式。返回匹配的规则名或 None。"""
    for pattern in FORBIDDEN_FILENAMES:
        # 精确匹配
        if "/" not in pattern and "\\" not in pattern and "*" not in pattern:
            if filepath == pattern or filepath.endswith("/" + pattern):
                if not _is_allowed_filename(filepath):
                    return pattern
        # 通配符匹配（仅支持 *.ext 格式）
        elif pattern.startswith("*."):
            ext = pattern[1:]  # 例如 .key
            if filepath.endswith(ext) and not _is_allowed_filename(filepath):
                return pattern
    return None


# ---------------------------------------------------------------------------
# 检查函数
# ---------------------------------------------------------------------------

def _collect_files_to_check() -> list[str]:
    """收集需要检查的文件列表（已跟踪 + 已暂存，去重）。"""
    tracked = set(_get_tracked_files())
    staged = set(_get_staged_files())
    all_files = tracked | staged
    # 排除被 .gitignore 忽略的文件
    ignored = _get_ignored_files()
    all_files = all_files - ignored
    return sorted(all_files)


def _is_excluded(filepath: str) -> bool:
    """检查文件路径是否在排除目录中。"""
    for d in EXCLUDE_DIRS:
        if filepath.startswith(d + "/") or filepath.startswith(d + "\\"):
            return True
        if filepath == d:
            return True
    return False


def check_forbidden_filenames(files: list[str]) -> list[dict]:
    """检查 1：禁止跟踪的文件名。"""
    findings = []
    for filepath in files:
        if _is_excluded(filepath):
            continue
        match = _match_forbidden_filename(filepath)
        if match:
            findings.append({
                "file": filepath,
                "line": 0,
                "rule": f"禁止跟踪文件: {match}",
            })
    return findings


def check_frontend_secrets(files: list[str]) -> list[dict]:
    """检查 2：前端禁止 Secret。"""
    findings = []
    frontend_files = [f for f in files if _is_in_frontend_dir(f) and not _is_excluded(f)]
    for filepath in frontend_files:
        full_path = REPO_ROOT / filepath
        if not full_path.is_file() or not _is_text_file(full_path):
            continue
        try:
            lines = full_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            for pattern, description in FORBIDDEN_FRONTEND_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "file": filepath,
                        "line": i,
                        "rule": f"前端禁止 Secret: {description}",
                    })
                    break  # 每行只报第一条规则
    return findings


def check_obvious_secrets(files: list[str]) -> list[dict]:
    """检查 3：明显真实 Secret（排除测试和脚本目录）。"""
    findings = []
    for filepath in files:
        if _is_excluded(filepath):
            continue
        full_path = REPO_ROOT / filepath
        if not full_path.is_file() or not _is_text_file(full_path):
            continue
        try:
            lines = full_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            for pattern, description in OBVIOUS_SECRET_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "file": filepath,
                        "line": i,
                        "rule": f"疑似真实 Secret: {description}",
                    })
                    break  # 每行只报第一条规则
    return findings


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    files = _collect_files_to_check()

    all_findings: list[dict] = []
    all_findings.extend(check_forbidden_filenames(files))
    all_findings.extend(check_frontend_secrets(files))
    all_findings.extend(check_obvious_secrets(files))

    if all_findings:
        print(f"[FAIL] 发现 {len(all_findings)} 项安全问题：")
        for finding in all_findings:
            print(f"  {finding['file']}:{finding['line']} — {finding['rule']}")
        return 1
    else:
        print(f"[PASS] 仓库安全检查通过（{len(files)} 个文件已检查）")
        return 0


if __name__ == "__main__":
    sys.exit(main())
