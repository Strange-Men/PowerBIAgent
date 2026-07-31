"""GoldenCaseRunner — 加载 YAML 用例，运行 MockTurnService，比较预期结果"""

import copy
import json
import time
from pathlib import Path
from typing import Any, Optional

import yaml


class GoldenCaseResult:
    """单条 Golden Case 运行结果"""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.passed = False
        self.failed = False
        self.mismatches: list[str] = []
        self.errors: list[str] = []
        self.duration_ms: float = 0.0

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.failed or self.mismatches:
            return "failed"
        return "passed"


class GoldenCaseSummary:
    """Golden Cases 运行摘要"""

    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.results: list[GoldenCaseResult] = []

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.total > 0


class GoldenCaseRunner:
    """Golden Case 运行器

    职责：
    - 加载 YAML 用例定义
    - 校验 Case 结构
    - 注入 initial_memory
    - 运行 MockTurnService
    - 收集 Trace
    - 比较 expected
    - 输出摘要
    """

    def __init__(self, cases_dir: Path, mock_turn_service: Any):
        self.cases_dir = Path(cases_dir)
        self.mock_turn_service = mock_turn_service

    def load_cases(self) -> list[dict[str, Any]]:
        """加载并校验所有 Golden Cases"""
        cases_file = self.cases_dir / "golden_cases.yaml"
        if not cases_file.exists():
            raise FileNotFoundError(f"Golden cases file not found: {cases_file}")

        with open(cases_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        cases = data.get("cases", [])
        for case in cases:
            self._validate_case_structure(case)

        return cases

    def _validate_case_structure(self, case: dict[str, Any]) -> None:
        """校验 Case 结构完整性"""
        required = ["id", "category", "status", "description", "input", "expected"]
        for field in required:
            if field not in case:
                raise ValueError(f"Golden case '{case.get('id', 'unknown')}' missing field: {field}")

    def run_all(self) -> GoldenCaseSummary:
        """运行全部 Golden Cases"""
        cases = self.load_cases()
        summary = GoldenCaseSummary()
        summary.total = len(cases)

        for case in cases:
            result = self.run_one(case)
            summary.results.append(result)

            if result.status == "passed":
                summary.passed += 1
            elif result.status == "error":
                summary.errors += 1
            else:
                summary.failed += 1

        return summary

    def run_one(self, case: dict[str, Any]) -> GoldenCaseResult:
        """运行单条 Golden Case"""
        case_id = case["id"]
        result = GoldenCaseResult(case_id)

        # 跳过非 mock_ready 用例
        if case["status"] != "mock_ready":
            result.errors.append(f"Case status is '{case['status']}', not mock_ready")
            return result

        try:
            start = time.monotonic()

            # 调用 MockTurnService
            turn_result = self._run_turn(case)

            result.duration_ms = (time.monotonic() - start) * 1000

            # 比较预期
            expected = case.get("expected", {})
            mismatches = self._compare(expected, turn_result)
            result.mismatches = mismatches

            if not mismatches:
                result.passed = True
            else:
                result.failed = True

        except Exception as e:
            result.errors.append(f"{type(e).__name__}: {e}")
            result.duration_ms = (time.monotonic() - start) * 1000

        return result

    def _run_turn(self, case: dict[str, Any]) -> dict[str, Any]:
        """执行 Turn（同步包装）"""
        import asyncio

        input_data = case["input"]
        runtime = case.get("runtime", {})
        mock_scenario = case.get("mock_scenario", {})
        initial_memory = case.get("initial_memory", None)

        try:
            loop = asyncio.get_running_loop()
            # 在运行中的事件循环中，使用 create_task
            import concurrent.futures
            raise RuntimeError("Cannot run in existing event loop - use sync runner")
        except RuntimeError:
            # 没有运行中的事件循环，创建新的
            return asyncio.run(
                self.mock_turn_service.execute(
                    message=input_data.get("message", ""),
                    conversation_id=input_data.get("conversation_id", "test-conv"),
                    request_id=input_data.get("request_id", "test-req"),
                    semantic_model_key=input_data.get("semantic_model_key", "mock_sales_model"),
                    report_template_key=input_data.get("report_template_key"),
                    initial_memory=initial_memory,
                    intent_key=mock_scenario.get("intent_key"),
                )
            )

    def _compare(
        self, expected: dict[str, Any], actual: dict[str, Any]
    ) -> list[str]:
        """比较预期与实际结果 — 不逐字比较自然语言答案"""
        mismatches: list[str] = []

        for key, exp_val in expected.items():
            if key == "tool_sequence":
                actual_seq = actual.get("tool_sequence", [])
                if actual_seq != exp_val:
                    mismatches.append(f"tool_sequence: expected {exp_val}, got {actual_seq}")
            elif key == "terminal_state":
                actual_state = actual.get("terminal_state", "")
                if actual_state != exp_val:
                    mismatches.append(f"terminal_state: expected {exp_val}, got {actual_state}")
            elif key == "state_changes":
                actual_changes = actual.get("state_changes", {})
                for sk, sv in (exp_val or {}).items():
                    av = actual_changes.get(sk)
                    if av != sv:
                        mismatches.append(f"state_changes.{sk}: expected {sv}, got {av}")
            elif key == "memory_commit":
                # 比较是否提交（bool）
                actual_commit = actual.get("memory_commit")
                if actual_commit != exp_val:
                    mismatches.append(f"memory_commit: expected {exp_val}, got {actual_commit}")
            elif key == "final_memory_version":
                actual_ver = actual.get("final_memory_version")
                if actual_ver is not None and actual_ver != exp_val:
                    mismatches.append(f"final_memory_version: expected {exp_val}, got {actual_ver}")
            elif key == "response_type":
                actual_rt = actual.get("response_type", "")
                if actual_rt != exp_val:
                    mismatches.append(f"response_type: expected {exp_val}, got {actual_rt}")
            elif key == "error_type":
                actual_et = actual.get("error_type")
                if actual_et != exp_val:
                    mismatches.append(f"error_type: expected {exp_val}, got {actual_et}")
            elif key == "intent":
                actual_intent = actual.get("intent", "")
                if actual_intent != exp_val:
                    mismatches.append(f"intent: expected {exp_val}, got {actual_intent}")
            elif key == "inherited_context":
                actual_ic = actual.get("inherited_context")
                if exp_val is not None and actual_ic != exp_val:
                    mismatches.append(f"inherited_context: expected present, got {actual_ic}")
            elif key == "allowed_tools":
                actual_tools = actual.get("allowed_tools", [])
                if set(actual_tools) != set(exp_val or []):
                    mismatches.append(f"allowed_tools mismatch")
            elif key == "forbidden_tools":
                actual_tools = actual.get("tool_sequence", [])
                for ft in (exp_val or []):
                    if ft in actual_tools:
                        mismatches.append(f"forbidden_tool '{ft}' was called")

        return mismatches
