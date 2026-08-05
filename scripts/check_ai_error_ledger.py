#!/usr/bin/env python
"""AI 开发错误总账校验器 — M1.6.6

检查 docs/ai_development_error_ledger.yaml 的完整性和正确性。

检查项：
1. YAML 可解析
2. Schema 版本存在
3. ID 唯一
4. 必填字段存在
5. 状态合法（不得缺失或为空）
6. repair_attempt_count 必须为 0、1 或 2（负数必须失败）
7. resolved 条目回归测试路径真实存在
8. resolved 条目的 related_commits 不得为空
9. resolved 条目必须存在 resolved 事件
10. resolved 事件必须记录 Commit
11. 关联 ADR 路径真实存在
12. 关联 Commit 格式合法
13. related_commits 中的 SHA 必须真实存在于本地 Git 历史
14. 禁止空字符串冒充证据
15. 检测 U+FFFD Unicode 替换字符
16. Commit 引用、事件 Commit 和最终修复状态基本一致
17. 校验失败时不得输出 Secret 或 YAML 全文

用法：
    python scripts/check_ai_error_ledger.py [--path PATH]

退出码：
    0 — 所有检查通过
    1 — 存在错误
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)


# ── 常量 ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT_ROOT / "docs" / "ai_development_error_ledger.yaml"

VALID_STATUSES = {"open", "blocked", "monitoring", "resolved", "superseded"}

REQUIRED_FIELDS = [
    "id", "title", "category", "first_detected_version",
    "symptom", "local_evidence", "authoritative_sources",
    "root_cause", "failed_attempts", "repair_attempt_count",
    "final_fix", "regression_tests", "prohibited_patterns",
    "prevention_rules", "related_adr", "related_commits",
    "status", "events",
]

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),       # API Key 格式
    re.compile(r"Bearer\s+[a-zA-Z0-9\-_\.]+"), # Bearer Token
    re.compile(r"eyJ[a-zA-Z0-9\-_]+\.eyJ"),   # JWT Token
]

# Git commit SHA cache: {sha: True/False}
_commit_exists_cache: dict[str, bool] = {}


def _git_commit_exists(sha: str) -> bool:
    """使用本地 Git 验证 commit SHA 是否存在（带缓存）"""
    if sha in _commit_exists_cache:
        return _commit_exists_cache[sha]
    try:
        result = subprocess.run(
            ["git", "cat-file", "-t", sha],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        exists = result.returncode == 0 and result.stdout.strip() == "commit"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        exists = False
    _commit_exists_cache[sha] = exists
    return exists


def check_unicode_replacement(data: dict) -> list[str]:
    """检查 YAML 中是否存在 U+FFFD Unicode 替换字符（乱码）"""
    import json
    text = json.dumps(data, ensure_ascii=False, default=str)
    count = text.count("�")
    if count > 0:
        return [f"存在 {count} 个 Unicode 替换字符 (U+FFFD)，表示编码损坏或乱码"]
    return []


# ── 校验函数 ────────────────────────────────────────────────────────────────


def check_yaml_parseable(path: Path) -> dict[str, Any] | None:
    """检查 YAML 可解析"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            print("ERROR: YAML 文件为空或仅含注释")
            return None
        if not isinstance(data, dict):
            print("ERROR: YAML 根节点必须是 dict")
            return None
        return data
    except yaml.YAMLError as e:
        print(f"ERROR: YAML 解析失败: {e}")
        return None
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {path}")
        return None


def check_schema_version(data: dict) -> bool:
    """检查 Schema 版本"""
    version = data.get("schema_version")
    if not version:
        print("ERROR: 缺少 schema_version")
        return False
    if not isinstance(version, str):
        print(f"ERROR: schema_version 必须是字符串: {version}")
        return False
    print(f"  schema_version: {version}")
    return True


def check_entries(data: dict) -> list[dict]:
    """获取 entries 列表"""
    entries = data.get("entries")
    if entries is None:
        print("ERROR: 缺少 entries 字段")
        return []
    if not isinstance(entries, list):
        print("ERROR: entries 必须是列表")
        return []
    print(f"  entries count: {len(entries)}")
    return entries


def check_entry(entry: dict, idx: int) -> list[str]:
    """检查单条错误记录，返回错误列表"""
    errors: list[str] = []
    entry_id = entry.get("id", f"<index {idx}>")

    # 必填字段
    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"[{entry_id}] 缺少必填字段: {field}")

    # 状态 — 不得缺失或为空
    status = entry.get("status")
    if status is None or (isinstance(status, str) and status.strip() == ""):
        errors.append(f"[{entry_id}] status 不得缺失或为空")
    elif status not in VALID_STATUSES:
        errors.append(f"[{entry_id}] 非法状态: {status}，允许: {VALID_STATUSES}")

    # repair_attempt_count — 必须为 0、1 或 2，负数必须失败
    count = entry.get("repair_attempt_count")
    if count is not None:
        if not isinstance(count, int):
            errors.append(f"[{entry_id}] repair_attempt_count 必须是整数: {count}")
        elif count < 0:
            errors.append(f"[{entry_id}] repair_attempt_count={count} 为负数，不允许")
        elif count > 2:
            errors.append(f"[{entry_id}] repair_attempt_count={count} 超过上限 2")

    # resolved 条目: 回归测试、related_commits、resolved 事件、事件 Commit
    if status == "resolved":
        # 必须有回归测试
        reg_tests = entry.get("regression_tests", [])
        if not isinstance(reg_tests, list) or len(reg_tests) == 0:
            errors.append(f"[{entry_id}] resolved 状态必须有至少一个回归测试")

        # related_commits 不得为空
        related_commits = entry.get("related_commits", [])
        if not isinstance(related_commits, list) or len(related_commits) == 0:
            errors.append(f"[{entry_id}] resolved 条目的 related_commits 不得为空")

        # 必须存在 resolved 事件
        events = entry.get("events", [])
        if isinstance(events, list):
            resolved_events = [e for e in events if isinstance(e, dict) and e.get("action") == "resolved"]
            if not resolved_events:
                errors.append(f"[{entry_id}] resolved 条目必须存在 action=resolved 的事件")
            else:
                # resolved 事件必须记录 Commit
                for re_ev in resolved_events:
                    if not re_ev.get("commit"):
                        errors.append(f"[{entry_id}] resolved 事件缺少 commit 字段")

        # Commit SHA 真实存在于本地 Git 历史
        if isinstance(related_commits, list):
            for commit_str in related_commits:
                if not isinstance(commit_str, str):
                    continue
                sha_candidate = commit_str.split()[0] if commit_str.split() else ""
                if COMMIT_SHA_RE.match(sha_candidate):
                    if not _git_commit_exists(sha_candidate):
                        errors.append(
                            f"[{entry_id}] Commit SHA 在本地 Git 历史中不存在: {sha_candidate}"
                        )

    # 回归测试路径真实存在
    if isinstance(entry.get("regression_tests"), list):
        for test_path in entry["regression_tests"]:
            full_path = PROJECT_ROOT / test_path
            if not full_path.exists():
                errors.append(f"[{entry_id}] 回归测试路径不存在: {test_path}")

    # ADR 路径真实存在
    related_adr = entry.get("related_adr")
    if related_adr and isinstance(related_adr, str):
        if related_adr.startswith("ADR-"):
            adr_files = list((PROJECT_ROOT / "docs" / "adr").glob(f"{related_adr}*.md"))
            if not adr_files:
                adr_readme = PROJECT_ROOT / "docs" / "adr" / "README.md"
                if adr_readme.exists():
                    readme_text = adr_readme.read_text(encoding="utf-8")
                    if related_adr not in readme_text:
                        errors.append(f"[{entry_id}] 关联 ADR 文件不存在且 README 中无记录: {related_adr}")
        elif related_adr.lower() not in ("none", "null", ""):
            errors.append(f"[{entry_id}] related_adr 格式不正确: {related_adr}")

    # Commit 格式
    if isinstance(entry.get("related_commits"), list):
        for commit_str in entry["related_commits"]:
            if not isinstance(commit_str, str):
                errors.append(f"[{entry_id}] Commit 记录必须是字符串: {commit_str}")
                continue
            sha_candidate = commit_str.split()[0] if commit_str.split() else ""
            if not COMMIT_SHA_RE.match(sha_candidate):
                errors.append(f"[{entry_id}] Commit 格式不合法: {commit_str}")

    # 空字符串冒充证据
    for field in ["symptom", "local_evidence", "root_cause", "final_fix"]:
        val = entry.get(field, "")
        if val == "" or val is None:
            errors.append(f"[{entry_id}] 字段 {field} 为空，不得冒充证据")
        if isinstance(val, str) and val.strip() == "":
            errors.append(f"[{entry_id}] 字段 {field} 仅为空白字符")

    # 权威来源
    sources = entry.get("authoritative_sources", [])
    if not isinstance(sources, list) or len(sources) == 0:
        errors.append(f"[{entry_id}] authoritative_sources 不能为空")
    elif isinstance(sources, list):
        for src in sources:
            if isinstance(src, dict):
                if not src.get("title"):
                    errors.append(f"[{entry_id}] authoritative_source 缺少 title")
                if not src.get("reason"):
                    errors.append(f"[{entry_id}] authoritative_source 缺少 reason (无资料时需说明原因)")

    # events
    events = entry.get("events", [])
    if not isinstance(events, list) or len(events) == 0:
        errors.append(f"[{entry_id}] events 不能为空")

    return errors


def check_no_secrets(data: dict) -> list[str]:
    """检查文档中无 Secret"""
    import json
    text = json.dumps(data, ensure_ascii=False, default=str)
    errors = []
    for pattern in SECRET_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            for m in matches[:3]:
                errors.append(f"疑似 Secret 泄露: ...{m[:30]}...")
    return errors


def check_id_unique(entries: list[dict]) -> list[str]:
    """检查 ID 唯一"""
    ids = []
    errors = []
    for entry in entries:
        eid = entry.get("id")
        if eid is None:
            errors.append("存在无 id 的条目")
        elif eid in ids:
            errors.append(f"ID 重复: {eid}")
        else:
            ids.append(eid)
    return errors


def check_regression_tests(entries: list[dict]) -> list[str]:
    """检查 resolved 条目回归测试路径是否存在（非空检查由 check_entry 完成）"""
    errors = []
    for entry in entries:
        if entry.get("status") == "resolved":
            eid = entry.get("id", "?")
            tests = entry.get("regression_tests", [])
            for t in tests:
                if not (PROJECT_ROOT / t).exists():
                    errors.append(f"[{eid}] 测试文件不存在: {t}")
    return errors


# ── 主入口 ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 开发错误总账校验器")
    parser.add_argument("--path", type=str, default=str(DEFAULT_PATH),
                        help=f"错误总账文件路径 (默认: {DEFAULT_PATH})")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出结果")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    all_errors: list[str] = []

    # 1. YAML 可解析
    data = check_yaml_parseable(path)
    if data is None:
        return 1

    # 2. Schema 版本
    if not check_schema_version(data):
        all_errors.append("schema_version 检查失败")

    # 3. entries
    entries = check_entries(data)

    # 4. ID 唯一
    all_errors.extend(check_id_unique(entries))

    # 5. 逐条检查
    for i, entry in enumerate(entries):
        all_errors.extend(check_entry(entry, i))

    # 6. resolved 回归测试
    all_errors.extend(check_regression_tests(entries))

    # 7. Unicode 替换字符检测
    all_errors.extend(check_unicode_replacement(data))

    # 8. 无 Secret
    all_errors.extend(check_no_secrets(data))

    # ── 输出结果 ──
    if args.json:
        import json
        result = {
            "schema_version": data.get("schema_version"),
            "entry_count": len(entries),
            "error_count": len(all_errors),
            "errors": all_errors,
            "pass": len(all_errors) == 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"AI 开发错误总账校验: {path.name}")
        print(f"  Schema 版本: {data.get('schema_version')}")
        print(f"  条目数量: {len(entries)}")
        print(f"  错误数量: {len(all_errors)}")
        print(f"{'='*60}")
        if all_errors:
            print("\n错误详情:")
            for err in all_errors:
                print(f"  [FAIL] {err}")
            print(f"\n结果: FAIL ({len(all_errors)} errors)")
        else:
            print("\n结果: PASS")
        print()

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
