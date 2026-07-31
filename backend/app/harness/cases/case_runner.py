"""GoldenCaseRunner — 加载 YAML 用例，运行 MockTurnService，比较预期结果

M0.3.1 修复：
- async-first (run_one_async / run_all_async)
- 安全处理已存在事件循环
- 传入全部五类 Scenario Key
- Pydantic 强校验 Case 结构
- Runtime 配置真实生效
- pending_real_baseline 计为 skipped
- 未知 expected 字段不忽略
- actual 为 None 时不假通过
- Runner 读取 Repository 验证 Memory
"""

import asyncio
import copy
import json
import time
from pathlib import Path
from typing import Any, ClassVar, Optional

import yaml
from pydantic import BaseModel, Field

from backend.app.application.mock_turn_service import MockScenarioSelection, MockTurnService


class GoldenCaseSpec(BaseModel):
    """Golden Case 结构化规格"""
    id: str
    category: str
    status: str
    description: str = ""
    runtime: dict[str, str] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    mock_scenario: dict[str, str] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    setup_turns: list[dict[str, Any]] = Field(default_factory=list)
    target_turn: Optional[dict[str, Any]] = None
    tags: list[str] = Field(default_factory=list)
    initial_memory: Optional[dict[str, Any]] = None

    # 允许状态值
    ALLOWED_STATUSES: ClassVar[set[str]] = {"mock_ready", "pending_real_baseline", "deprecated"}
    ALLOWED_CATEGORIES: ClassVar[set[str]] = {
        "data_question", "report_generation", "clarification", "unsupported",
        "tool_failure", "validation", "memory_conflict", "tool_policy",
        "edge_case", "multiround",
    }
    ALLOWED_EXPECTED_KEYS: ClassVar[set[str]] = {
        "intent", "terminal_state", "memory_commit", "response_type",
        "tool_sequence", "error_type", "inherited_context", "final_memory_version",
        "state_changes", "allowed_tools", "forbidden_tools",
        "measures", "dimensions", "filters", "time_range", "last_dax",
        "last_result_summary", "memory_version",
    }


class GoldenCaseResult:
    """单条 Golden Case 运行结果"""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.passed = False
        self.failed = False
        self.skipped = False
        self.mismatches: list[str] = []
        self.errors: list[str] = []
        self.duration_ms: float = 0.0

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        if self.errors:
            return "error"
        if self.failed or self.mismatches:
            return "failed"
        return "passed"


class GoldenCaseSummary:
    """Golden Cases 运行摘要"""

    def __init__(self):
        self.total = 0
        self.defined = 0
        self.runnable = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.skipped = 0
        self.results: list[GoldenCaseResult] = []

    @property
    def all_runnable_passed(self) -> bool:
        return (self.failed == 0 and self.errors == 0
                and self.passed >= self.runnable - self.skipped
                and self.runnable > 0)


class GoldenCaseRunner:
    """Golden Case 运行器

    职责：
    - 加载 YAML 用例定义
    - Pydantic 强校验 Case 结构
    - 传入全部五类 Scenario Key
    - 运行 MockTurnService
    - 收集 Trace
    - 读取 Repository 验证 Memory
    - 精确比较 expected
    - 输出摘要
    """

    def __init__(self, cases_path: Path, mock_turn_service: MockTurnService):
        self.cases_path = Path(cases_path)
        self.service = mock_turn_service

    def load_cases(self) -> list[GoldenCaseSpec]:
        """加载并校验所有 Golden Cases"""
        cases_file = self.cases_path / "golden_cases.yaml"
        if not cases_file.exists():
            raise FileNotFoundError(f"Golden cases file not found: {cases_file}")

        with open(cases_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw_cases = data.get("cases", [])
        cases = []
        seen_ids = set()
        for raw in raw_cases:
            self._validate_case_structure(raw)
            case = GoldenCaseSpec(**raw)
            # id 唯一
            if case.id in seen_ids:
                raise ValueError(f"Duplicate case id: {case.id}")
            seen_ids.add(case.id)
            cases.append(case)
        return cases

    def _validate_case_structure(self, case: dict[str, Any]) -> None:
        """校验 Case 结构完整性"""
        required = ["id", "category", "status", "input", "expected"]
        for field in required:
            if field not in case:
                raise ValueError(f"Golden case missing required field: {field}")

        case_id = case.get("id", "unknown")
        if case["status"] not in GoldenCaseSpec.ALLOWED_STATUSES:
            raise ValueError(f"Case '{case_id}': invalid status '{case['status']}'")
        if case["category"] not in GoldenCaseSpec.ALLOWED_CATEGORIES:
            raise ValueError(f"Case '{case_id}': invalid category '{case['category']}'")

        # 检查 expected 未知字段
        for key in case.get("expected", {}):
            if key not in GoldenCaseSpec.ALLOWED_EXPECTED_KEYS:
                raise ValueError(f"Case '{case_id}': unknown expected key '{key}'")

    async def run_all_async(self) -> GoldenCaseSummary:
        """异步运行全部 Golden Cases"""
        cases = self.load_cases()
        summary = GoldenCaseSummary()
        summary.defined = len(cases)

        for case in cases:
            result = await self.run_one_async(case)
            summary.results.append(result)
            summary.total += 1

            if result.status == "skipped":
                summary.skipped += 1
            elif result.status == "passed":
                summary.passed += 1
                summary.runnable += 1
            elif result.status == "error":
                summary.errors += 1
                summary.runnable += 1
            else:
                summary.failed += 1
                summary.runnable += 1

        return summary

    async def run_one_async(self, case: GoldenCaseSpec) -> GoldenCaseResult:
        """异步运行单条 Golden Case"""
        case_id = case.id
        result = GoldenCaseResult(case_id)

        # 跳过 pending_real_baseline
        if case.status == "pending_real_baseline":
            result.skipped = True
            result.errors.append(f"Status is 'pending_real_baseline' — 等待真实 Power BI 基线")
            return result

        # 运行时模式检查 — M0.3.1 只允许 Mock
        runtime = case.runtime
        llm_mode = runtime.get("llm_mode", "mock")
        powerbi_mode = runtime.get("powerbi_mode", "mock")
        if llm_mode != "mock" or powerbi_mode != "mock":
            result.skipped = True
            result.errors.append(f"Real mode not supported in M0.3.1 (llm={llm_mode}, pbi={powerbi_mode})")
            return result

        start = time.monotonic()

        try:
            # 处理 setup_turns + target_turn
            if case.setup_turns:
                result = await self._run_with_setup(case, result)
            else:
                result = await self._run_single(case, result)

            result.duration_ms = (time.monotonic() - start) * 1000
        except Exception as e:
            result.errors.append(f"{type(e).__name__}: {e}")
            result.duration_ms = (time.monotonic() - start) * 1000

        return result

    async def _run_single(
        self, case: GoldenCaseSpec, result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """运行单轮 Case"""
        input_data = case.input
        mock_scenario = case.mock_scenario

        # 构建 Scenario（全部五类 Key）
        scenario = MockScenarioSelection(
            intent_key=mock_scenario.get("intent_key", "data_question"),
            query_plan_key=mock_scenario.get("query_plan_key", mock_scenario.get("intent_key", "data_question")),
            dax_key=mock_scenario.get("dax_key", mock_scenario.get("intent_key", "data_question")),
            powerbi_key=mock_scenario.get("powerbi_key", mock_scenario.get("intent_key", "data_question")),
            response_key=mock_scenario.get("response_key", mock_scenario.get("intent_key", "data_question")),
        )

        turn_result = await self.service.execute(
            message=input_data.get("message", ""),
            conversation_id=input_data.get("conversation_id", "test-conv"),
            request_id=input_data.get("request_id", "test-req"),
            semantic_model_key=input_data.get("semantic_model_key", "mock_sales_model"),
            report_template_key=input_data.get("report_template_key"),
            scenario=scenario,
        )

        return await self._compare_and_verify(case, turn_result, result)

    async def _run_with_setup(
        self, case: GoldenCaseSpec, result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """通过 setup_turns 建立多轮真实 Memory"""
        conv_id = case.input.get("conversation_id", "test-conv")

        # 执行 setup turns
        for i, setup in enumerate(case.setup_turns):
            setup_scenario = MockScenarioSelection(
                intent_key=setup.get("intent_key", "data_question"),
                query_plan_key=setup.get("query_plan_key", setup.get("intent_key", "data_question")),
                dax_key=setup.get("dax_key", setup.get("intent_key", "data_question")),
                powerbi_key=setup.get("powerbi_key", setup.get("intent_key", "data_question")),
                response_key=setup.get("response_key", setup.get("intent_key", "data_question")),
            )
            setup_result = await self.service.execute(
                message=setup.get("message", ""),
                conversation_id=conv_id,
                request_id=setup.get("request_id", f"setup-{i}"),
                semantic_model_key=setup.get("semantic_model_key", "mock_sales_model"),
                scenario=setup_scenario,
            )
            if setup_result["terminal_state"] != "completed":
                result.errors.append(
                    f"Setup turn {i} failed: {setup_result['terminal_state']}"
                )
                return result

        # 执行目标 turn
        input_data = case.input
        mock_scenario = case.mock_scenario
        scenario = MockScenarioSelection(
            intent_key=mock_scenario.get("intent_key", "data_question"),
            query_plan_key=mock_scenario.get("query_plan_key", mock_scenario.get("intent_key", "data_question")),
            dax_key=mock_scenario.get("dax_key", mock_scenario.get("intent_key", "data_question")),
            powerbi_key=mock_scenario.get("powerbi_key", mock_scenario.get("intent_key", "data_question")),
            response_key=mock_scenario.get("response_key", mock_scenario.get("intent_key", "data_question")),
        )

        turn_result = await self.service.execute(
            message=input_data.get("message", ""),
            conversation_id=conv_id,
            request_id=input_data.get("request_id", "target-req"),
            semantic_model_key=input_data.get("semantic_model_key", "mock_sales_model"),
            report_template_key=input_data.get("report_template_key"),
            scenario=scenario,
        )

        return await self._compare_and_verify(case, turn_result, result)

    async def _compare_and_verify(
        self, case: GoldenCaseSpec, actual: dict[str, Any],
        result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """比较 expected 并验证 Repository"""
        expected = case.expected

        # 未知 expected 字段检查已在 load 时完成

        mismatches = self._compare(expected, actual)

        # 读取 Repository 验证 Memory 状态
        repo_mismatches = await self._verify_repository(case, actual)
        mismatches.extend(repo_mismatches)

        result.mismatches = mismatches
        if not mismatches:
            result.passed = True
        else:
            result.failed = True

        return result

    async def _verify_repository(
        self, case: GoldenCaseSpec, actual: dict[str, Any]
    ) -> list[str]:
        """通过 Repository 验证 Memory 状态"""
        mismatches: list[str] = []
        repo = self.service.memory_repo

        request_id = actual.get("request_id", "")
        if not request_id:
            return mismatches

        # clarification/unsupported 不创建 pending，跳过 Repository 检查
        terminal = actual.get("terminal_state", "")
        if terminal in ("clarification_required", "unsupported"):
            return mismatches

        memory = await repo.get_by_request_id(request_id)
        if memory is None:
            if terminal not in ("duplicate",):
                mismatches.append("Repository: memory not found for request_id")
            return mismatches

        # 验证 terminal_state 与 Repository 一致
        terminal = actual.get("terminal_state", "")
        if terminal == "completed":
            if memory.state_status.value != "committed":
                mismatches.append(
                    f"Repository: expected committed, got {memory.state_status.value}"
                )
            exp_ver = case.expected.get("final_memory_version")
            if exp_ver is not None and memory.memory_version != exp_ver:
                mismatches.append(
                    f"Repository: expected memory_version={exp_ver}, got {memory.memory_version}"
                )

        # 验证 expected fields 在 committed memory 中
        if memory.state_status.value == "committed":
            for key in ["measures", "dimensions", "filters", "time_range", "last_dax"]:
                exp_val = case.expected.get(key)
                if exp_val is not None:
                    actual_val = getattr(memory, key, None)
                    if actual_val != exp_val:
                        mismatches.append(
                            f"Repository.{key}: expected {exp_val}, got {actual_val}"
                        )

        # 验证工具序列来自真实 Trace
        exp_tools = case.expected.get("tool_sequence")
        if exp_tools is not None:
            actual_tools = actual.get("tool_sequence", [])
            if actual_tools != exp_tools:
                mismatches.append(
                    f"tool_sequence: expected {exp_tools}, got {actual_tools}"
                )

        return mismatches

    def _compare(
        self, expected: dict[str, Any], actual: dict[str, Any]
    ) -> list[str]:
        """精确比较预期与实际结果"""
        mismatches: list[str] = []

        for key, exp_val in expected.items():
            actual_val = actual.get(key)

            if key == "tool_sequence":
                if actual_val != exp_val:
                    mismatches.append(f"tool_sequence: expected {exp_val}, got {actual_val}")
            elif key == "terminal_state":
                if actual_val != exp_val:
                    mismatches.append(f"terminal_state: expected {exp_val}, got {actual_val}")
            elif key == "state_changes":
                actual_changes = actual.get("state_changes", {})
                for sk, sv in (exp_val or {}).items():
                    av = actual_changes.get(sk)
                    if sv is not None and av != sv:
                        mismatches.append(f"state_changes.{sk}: expected {sv}, got {av}")
            elif key == "memory_commit":
                if actual_val != exp_val:
                    mismatches.append(f"memory_commit: expected {exp_val}, got {actual_val}")
            elif key == "final_memory_version":
                if exp_val is not None and actual_val != exp_val:
                    mismatches.append(f"final_memory_version: expected {exp_val}, got {actual_val}")
            elif key == "response_type":
                if actual_val != exp_val:
                    mismatches.append(f"response_type: expected {exp_val}, got {actual_val}")
            elif key == "error_type":
                if exp_val is not None and actual_val != exp_val:
                    mismatches.append(f"error_type: expected {exp_val}, got {actual_val}")
            elif key == "intent":
                if actual_val != exp_val:
                    mismatches.append(f"intent: expected {exp_val}, got {actual_val}")
            elif key == "inherited_context":
                if exp_val is not None:
                    if actual_val is None:
                        mismatches.append(f"inherited_context: expected '{exp_val}', got None")
                    elif actual_val != exp_val:
                        mismatches.append(f"inherited_context: expected '{exp_val}', got '{actual_val}'")
            elif key == "allowed_tools":
                if set(actual_val or []) != set(exp_val or []):
                    mismatches.append(f"allowed_tools mismatch")
            elif key == "forbidden_tools":
                for ft in (exp_val or []):
                    if ft in (actual_val or []):
                        mismatches.append(f"forbidden_tool '{ft}' was called")
            elif key in ("measures", "dimensions", "filters", "time_range",
                        "last_dax", "last_result_summary", "memory_version"):
                if exp_val is not None and actual_val != exp_val:
                    mismatches.append(f"{key}: expected {exp_val}, got {actual_val}")
            else:
                # 未知字段已在加载时拒绝
                pass

        return mismatches

    # ---- 同步兼容入口 ----

    def run_all(self) -> GoldenCaseSummary:
        """同步运行全部（兼容旧入口）"""
        try:
            loop = asyncio.get_running_loop()
            # 已有事件循环，直接使用 run_until_complete 不安全
            # 使用新线程或子进程
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.run_all_async())
                return future.result(timeout=300)
        except RuntimeError:
            return asyncio.run(self.run_all_async())

    def run_one(self, case: dict[str, Any]) -> GoldenCaseResult:
        """同步运行单条（兼容旧入口）"""
        case_spec = GoldenCaseSpec(**case)
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.run_one_async(case_spec))
                return future.result(timeout=60)
        except RuntimeError:
            return asyncio.run(self.run_one_async(case_spec))
