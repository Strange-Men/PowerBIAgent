"""M1.6.5 GOV-165-003: 错题本校验器单元测试

验证 check_ai_error_ledger.py 的各项检查能力。
"""

import os
import sys
import pytest
import tempfile
import yaml
from pathlib import Path

# 导入校验器
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from scripts.check_ai_error_ledger import (
    REQUIRED_FIELDS,
    VALID_STATUSES,
    check_entry,
    check_id_unique,
    check_schema_version,
)


class TestRequiredFields:
    """必填字段检查"""

    def test_all_required_fields_present_passes(self):
        """所有必填字段存在时通过"""
        entry = {
            "id": "TEST-001",
            "title": "Test",
            "category": "TX",
            "first_detected_version": "M1.0",
            "symptom": "test symptom",
            "local_evidence": "test evidence",
            "authoritative_sources": [{"title": "Test", "reason": "Test reason"}],
            "root_cause": "test cause",
            "failed_attempts": [],
            "repair_attempt_count": 1,
            "final_fix": "test fix",
            "regression_tests": ["backend/tests/unit/test_m165_error_ledger.py"],
            "prohibited_patterns": [],
            "prevention_rules": [],
            "related_adr": None,
            "related_commits": [],
            "status": "resolved",
            "events": [{"date": "2026-08-05", "action": "discovered"}],
        }
        errors = check_entry(entry, 0)
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    @pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
    def test_missing_required_field_detected(self, missing_field):
        """缺少必填字段被检测"""
        entry = {
            "id": "TEST-002",
            "title": "Test",
            "category": "TX",
            "first_detected_version": "M1.0",
            "symptom": "test",
            "local_evidence": "test",
            "authoritative_sources": [{"title": "T", "reason": "R"}],
            "root_cause": "test",
            "failed_attempts": [],
            "repair_attempt_count": 1,
            "final_fix": "test",
            "regression_tests": [],
            "prohibited_patterns": [],
            "prevention_rules": [],
            "related_adr": None,
            "related_commits": [],
            "status": "open",
            "events": [{"date": "2026-08-05", "action": "discovered"}],
        }
        del entry[missing_field]
        errors = check_entry(entry, 0)
        assert any(missing_field in e for e in errors), (
            f"应检测到缺少字段 {missing_field}"
        )


class TestStatusValidation:
    """状态合法性检查"""

    def test_valid_statuses_pass(self):
        """合法状态通过"""
        for status in VALID_STATUSES:
            entry = self._make_entry("TEST-S", status=status)
            errors = check_entry(entry, 0)
            status_errors = [e for e in errors if "状态" in e or "status" in e.lower()]
            assert len(status_errors) == 0, f"合法状态 {status} 不应报错: {status_errors}"

    def test_invalid_status_detected(self):
        """非法状态被检测"""
        entry = self._make_entry("TEST-INVALID", status="bogus_status")
        errors = check_entry(entry, 0)
        assert any("bogus_status" in e for e in errors)

    def _make_entry(self, eid, status="open"):
        return {
            "id": eid, "title": "T", "category": "TX",
            "first_detected_version": "M1.0",
            "symptom": "s", "local_evidence": "e",
            "authoritative_sources": [{"title": "T", "reason": "R"}],
            "root_cause": "c", "failed_attempts": [],
            "repair_attempt_count": 1, "final_fix": "f",
            "regression_tests": ["backend/tests/unit/test_m165_error_ledger.py"],
            "prohibited_patterns": [], "prevention_rules": [],
            "related_adr": None, "related_commits": [],
            "status": status,
            "events": [{"date": "2026-08-05", "action": "discovered"}],
        }


class TestRepairAttemptCount:
    """修复次数限制检查"""

    def test_count_not_exceed_2_passes(self):
        """修复次数 <= 2 通过"""
        for count in [0, 1, 2]:
            entry = self._make_entry()
            entry["repair_attempt_count"] = count
            errors = check_entry(entry, 0)
            count_errors = [e for e in errors if "repair_attempt_count" in e]
            assert len(count_errors) == 0

    def test_count_exceed_2_fails(self):
        """修复次数 > 2 被拒绝"""
        entry = self._make_entry()
        entry["repair_attempt_count"] = 3
        errors = check_entry(entry, 0)
        assert any("repair_attempt_count" in e and "3" in e for e in errors)

    def _make_entry(self):
        return {
            "id": "TEST-RC", "title": "T", "category": "TX",
            "first_detected_version": "M1.0",
            "symptom": "s", "local_evidence": "e",
            "authoritative_sources": [{"title": "T", "reason": "R"}],
            "root_cause": "c", "failed_attempts": [],
            "repair_attempt_count": 1, "final_fix": "f",
            "regression_tests": [],
            "prohibited_patterns": [], "prevention_rules": [],
            "related_adr": None, "related_commits": [],
            "status": "open",
            "events": [{"date": "2026-08-05", "action": "discovered"}],
        }


class TestResolvedRequiresRegressionTests:
    """resolved 条目必须有回归测试"""

    def test_resolved_without_tests_fails(self):
        """resolved 无回归测试被拒绝"""
        entry = self._make_entry()
        entry["status"] = "resolved"
        entry["regression_tests"] = []
        errors = check_entry(entry, 0)
        assert any("回归测试" in e for e in errors)

    def test_resolved_with_tests_passes(self):
        """resolved 有回归测试通过"""
        entry = self._make_entry()
        entry["status"] = "resolved"
        entry["regression_tests"] = ["backend/tests/unit/test_m165_error_ledger.py"]
        errors = check_entry(entry, 0)
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def _make_entry(self):
        return {
            "id": "TEST-RT", "title": "T", "category": "TX",
            "first_detected_version": "M1.0",
            "symptom": "s", "local_evidence": "e",
            "authoritative_sources": [{"title": "T", "reason": "R"}],
            "root_cause": "c", "failed_attempts": [],
            "repair_attempt_count": 1, "final_fix": "f",
            "regression_tests": [],
            "prohibited_patterns": [], "prevention_rules": [],
            "related_adr": None, "related_commits": [],
            "status": "open",
            "events": [{"date": "2026-08-05", "action": "discovered"}],
        }


class TestEmptyEvidenceRejected:
    """空证据拒绝"""

    @pytest.mark.parametrize("field", ["symptom", "local_evidence", "root_cause", "final_fix"])
    def test_empty_field_detected(self, field):
        """空字符串证据被检测"""
        entry = {
            "id": "TEST-EE", "title": "T", "category": "TX",
            "first_detected_version": "M1.0",
            "symptom": "s", "local_evidence": "e",
            "authoritative_sources": [{"title": "T", "reason": "R"}],
            "root_cause": "c", "failed_attempts": [],
            "repair_attempt_count": 1, "final_fix": "f",
            "regression_tests": [],
            "prohibited_patterns": [], "prevention_rules": [],
            "related_adr": None, "related_commits": [],
            "status": "open",
            "events": [{"date": "2026-08-05", "action": "discovered"}],
        }
        entry[field] = ""
        errors = check_entry(entry, 0)
        assert any(field in e for e in errors), f"应检测到 {field} 为空"


class TestIDUniqueness:
    """ID 唯一性检查"""

    def test_duplicate_id_detected(self):
        """重复 ID 被检测"""
        entries = [
            {"id": "DUP-001"},
            {"id": "DUP-001"},
        ]
        errors = check_id_unique(entries)
        assert len(errors) == 1
        assert "重复" in errors[0] or "DUP" in errors[0]

    def test_unique_ids_pass(self):
        """唯一 ID 通过"""
        entries = [
            {"id": "UNIQ-001"},
            {"id": "UNIQ-002"},
            {"id": "UNIQ-003"},
        ]
        errors = check_id_unique(entries)
        assert len(errors) == 0


class TestRealLedgerYAML:
    """真实错题本 YAML 文件完整性"""

    def test_yaml_loads(self):
        """真实 YAML 可解析"""
        path = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "ai_development_error_ledger.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "schema_version" in data
        assert "entries" in data

    def test_entries_count(self):
        """真实条目数量 >= 8"""
        path = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "ai_development_error_ledger.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["entries"]) >= 8, f"预期至少 8 条历史错误，实际 {len(data['entries'])}"


class TestValidatorScriptIntegration:
    """校验器脚本集成测试"""

    def test_validator_on_real_ledger_passes(self):
        """校验器对真实错题本返回 PASS"""
        import subprocess
        script = str(Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "check_ai_error_ledger.py")
        result = subprocess.run(
            [sys.executable, script, "--json"],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, f"Validator failed:\n{result.stdout}\n{result.stderr}"
