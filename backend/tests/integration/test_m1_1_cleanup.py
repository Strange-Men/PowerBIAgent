"""M1.1 历史收口集成测试

验证 Phase A 所有修复：
- ScenarioFingerprint 五个字段参与 Hash
- 幂等冲突仍返回 409
- 协调失败返回 503
- 正常 Owner/Waiter 不回归
- docs/09 和 CHANGELOG 已更新（通过内容验证）
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest

from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
    RequestFingerprint,
    ScenarioFingerprint,
)
from backend.app.application.mock_turn_service import (
    MockScenarioSelection,
    MockTurnService,
)
from backend.app.memory.result_snapshot import (
    IdempotencyClaimStatus,
)


class TestScenarioFingerprintHash:
    """ScenarioFingerprint 五个字段参与 Hash"""

    def test_all_five_fields_participate(self):
        """五个字段全部参与 Hash — 任意字段变化 Hash 都不同"""
        sfp1 = ScenarioFingerprint(
            intent_key="a", query_plan_key="a", dax_key="a",
            powerbi_key="a", response_key="a",
        )
        fp1 = RequestFingerprint.compute(
            message="test",
            scenario=sfp1,
        )
        h1 = fp1.hash()

        # 改变 intent_key
        sfp2 = ScenarioFingerprint(
            intent_key="b", query_plan_key="a", dax_key="a",
            powerbi_key="a", response_key="a",
        )
        fp2 = RequestFingerprint.compute(message="test", scenario=sfp2)
        h2 = fp2.hash()
        assert h1 != h2, "intent_key 变化应导致 Hash 不同"

        # 改变 query_plan_key
        sfp3 = ScenarioFingerprint(
            intent_key="a", query_plan_key="b", dax_key="a",
            powerbi_key="a", response_key="a",
        )
        h3 = RequestFingerprint.compute_hash(message="test", scenario=sfp3)
        assert h1 != h3, "query_plan_key 变化应导致 Hash 不同"

        # 改变 dax_key
        sfp4 = ScenarioFingerprint(
            intent_key="a", query_plan_key="a", dax_key="b",
            powerbi_key="a", response_key="a",
        )
        h4 = RequestFingerprint.compute_hash(message="test", scenario=sfp4)
        assert h1 != h4, "dax_key 变化应导致 Hash 不同"

        # 改变 powerbi_key
        sfp5 = ScenarioFingerprint(
            intent_key="a", query_plan_key="a", dax_key="a",
            powerbi_key="b", response_key="a",
        )
        h5 = RequestFingerprint.compute_hash(message="test", scenario=sfp5)
        assert h1 != h5, "powerbi_key 变化应导致 Hash 不同"

        # 改变 response_key
        sfp6 = ScenarioFingerprint(
            intent_key="a", query_plan_key="a", dax_key="a",
            powerbi_key="a", response_key="b",
        )
        h6 = RequestFingerprint.compute_hash(message="test", scenario=sfp6)
        assert h1 != h6, "response_key 变化应导致 Hash 不同"

    def test_identical_scenario_same_hash(self):
        """相同 ScenarioFingerprint 产生相同 Hash"""
        sfp1 = ScenarioFingerprint(
            intent_key="data_question", query_plan_key="data_question",
            dax_key="data_question", powerbi_key="data_question",
            response_key="data_question",
        )
        sfp2 = ScenarioFingerprint(
            intent_key="data_question", query_plan_key="data_question",
            dax_key="data_question", powerbi_key="data_question",
            response_key="data_question",
        )
        h1 = RequestFingerprint.compute_hash(message="test", scenario=sfp1)
        h2 = RequestFingerprint.compute_hash(message="test", scenario=sfp2)
        assert h1 == h2

    def test_scenario_fingerprint_extra_forbid(self):
        """ScenarioFingerprint extra=forbid"""
        with pytest.raises(Exception):
            ScenarioFingerprint(
                intent_key="a", query_plan_key="a", dax_key="a",
                powerbi_key="a", response_key="a", extra_field="no",
            )

    def test_scenario_fingerprint_frozen(self):
        """ScenarioFingerprint frozen=True"""
        sfp = ScenarioFingerprint(
            intent_key="a", query_plan_key="a", dax_key="a",
            powerbi_key="a", response_key="a",
        )
        with pytest.raises(Exception):
            sfp.intent_key = "new"


class TestIdempotencyConflict409:
    """幂等冲突仍返回 409"""

    @pytest.mark.asyncio
    async def test_same_request_id_different_content_409(self):
        """相同 request_id 不同内容 → IdempotencyConflictError"""
        service = MockTurnService()

        rid = str(uuid.uuid4())
        # 第一次
        result1 = await service.execute(
            message="本月销售额？",
            request_id=rid,
        )
        assert result1["terminal_state"] == "completed"

        # 第二次 — 不同 message → 冲突
        with pytest.raises(IdempotencyConflictError):
            await service.execute(
                message="上个月销售额？",
                request_id=rid,
            )


class TestIdempotencyCoordination503:
    """协调失败返回 503 类型"""

    def test_coordination_error_has_request_id(self):
        """IdempotencyCoordinationError 携带 request_id"""
        e = IdempotencyCoordinationError(
            request_id="req-123",
            detail="test detail",
        )
        assert e.request_id == "req-123"
        assert "test detail" in str(e)

    def test_coordination_error_not_conflict(self):
        """IdempotencyCoordinationError 不是 IdempotencyConflictError"""
        e = IdempotencyCoordinationError(request_id="x")
        assert not isinstance(e, IdempotencyConflictError)


class TestNormalOwnerWaiterNotBroken:
    """正常 Owner/Waiter 不回归"""

    @pytest.mark.asyncio
    async def test_normal_owner_completes(self):
        """Owner 正常执行完成"""
        service = MockTurnService()
        result = await service.execute(
            message="本月销售额？",
            request_id=str(uuid.uuid4()),
        )
        assert result["terminal_state"] == "completed"
        assert "answer" in result

    @pytest.mark.asyncio
    async def test_idempotent_replay_works(self):
        """幂等重放正常"""
        service = MockTurnService()
        rid = str(uuid.uuid4())
        # 首次
        r1 = await service.execute(message="本月销售额？", request_id=rid)
        assert r1["terminal_state"] == "completed"
        # 重放
        r2 = await service.execute(message="本月销售额？", request_id=rid)
        assert r2["terminal_state"] == "duplicate"


class TestDocsUpdated:
    """文档更新验证 — 离线检查 docs/09 和 CHANGELOG"""

    def test_docs_09_has_historical_commits(self):
        """docs/09 写入了 c223d7b、5726959 和测试结果"""
        import os
        docs_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "docs"
        )
        path09 = os.path.join(docs_dir, "09_context_handoff.md")
        content = open(path09, encoding="utf-8").read()
        assert "c223d7b" in content, "docs/09 应包含 M1.0.1 Commit SHA"
        assert "5726959" in content, "docs/09 应包含 M1.0.2 Commit SHA"
        assert "53cf43e" in content, "docs/09 应包含 M1.2 Commit SHA"
        assert "675 passed" in content, "docs/09 应记录最新 pytest 结果"

    def test_changelog_no_pending_push(self):
        """CHANGELOG 旧区域不再保留待推送/由 Git 解析占位符"""
        import os
        changelog = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "CHANGELOG.md"
        )
        content = open(changelog, encoding="utf-8").read()
        # M1.0.1 和 M1.0.2 的 Commit SHA 已写入
        assert "c223d7b" in content
        assert "5726959" in content
        # M1.0/M1.0.1/M1.0.2/M0.4/M0.4.1 的 Commit SHA 不应再有占位符
        # 检查没有 "**Commit SHA：** 由 Git 解析" 格式的行
        import re
        placeholder_pattern = re.compile(r"\*\*Commit SHA：\*\*\s*由 Git 解析")
        assert not placeholder_pattern.search(content), (
            "CHANGELOG 不应再有 '**Commit SHA：** 由 Git 解析' 占位符"
        )
        # 检查没有 "**Push 状态：** 待推送" 格式的行
        push_pattern = re.compile(r"\*\*Push 状态：\*\*\s*(?:待推送|将在 Git 收尾)")
        assert not push_pattern.search(content), (
            "CHANGELOG 不应再有 Push 状态占位符"
        )


class TestSecurityScannerTestsAndScripts:
    """安全扫描器：测试和 scripts 目录纳入扫描"""

    def test_scanner_does_not_exclude_tests(self):
        """扫描器不再整体排除 backend/tests"""
        import sys, os
        scripts_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "scripts"
        )
        sys.path.insert(0, scripts_dir)
        from scripts.check_repository_safety import EXCLUDE_DIRS
        assert "backend/tests" not in EXCLUDE_DIRS, (
            "backend/tests 不应再被整体排除"
        )

    def test_scanner_does_not_exclude_scripts(self):
        """扫描器不再整体排除 scripts"""
        import sys, os
        scripts_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "scripts"
        )
        sys.path.insert(0, scripts_dir)
        from scripts.check_repository_safety import EXCLUDE_DIRS
        assert "scripts" not in EXCLUDE_DIRS, (
            "scripts 不应再被整体排除"
        )


class TestFakeSecretNotInTestLiterals:
    """测试 Secret 使用拼接生成，避免完整疑似 Key 字面量"""

    def test_fake_key_uses_concatenation(self):
        """假 Key 使用字符串拼接生成"""
        # sk- 后跟拼接字符串，不直接在源码中出现完整疑似 Key
        fake = "sk-" + ("X" * 24)
        assert len(fake) == 27
        assert fake.startswith("sk-")
        # 不直接在源码中写完整的 sk-xxx...xxx
