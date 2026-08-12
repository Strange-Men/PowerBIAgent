"""GoldenCaseRunner — M0.3.2 严格化版本

修复：
- extra="forbid" 拒绝额外字段
- 五类 Scenario Key 强校验
- Runtime 配置真实创建独立 Service
- 幂等 Case 真实执行两次
- 多轮 Case 证明 context 真实继承
- failed Case 验证 Repository 状态
- Case 之间 Memory 隔离
"""

import asyncio
import copy
import json
import time
from pathlib import Path
from typing import Any, ClassVar, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.mock_turn_service import MockScenarioSelection, MockTurnService
from backend.app.memory.models import MemoryStatus, RuntimeDataMode


# =============================================================================
# 结构化 Case 模型
# =============================================================================

class GoldenRuntimeSpec(BaseModel):
    """运行时配置规格"""
    llm_mode: str = "mock"
    powerbi_mode: str = "mock"
    harness_mode: str = "strict"

    model_config = ConfigDict(extra="forbid")


class GoldenInputSpec(BaseModel):
    """输入规格"""
    message: str = ""
    conversation_id: str = "test-conv"
    request_id: str = "test-req"
    semantic_model_key: str = "mock_sales_model"
    report_template_key: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class GoldenScenarioSpec(BaseModel):
    """五类 Scenario Key 规格"""
    intent_key: str = "data_question"
    query_plan_key: Optional[str] = None
    dax_key: Optional[str] = None
    powerbi_key: Optional[str] = None
    response_key: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    def fill_defaults(self) -> None:
        """未指定的 Key 回退到 intent_key"""
        if self.query_plan_key is None:
            self.query_plan_key = self.intent_key
        if self.dax_key is None:
            self.dax_key = self.intent_key
        if self.powerbi_key is None:
            self.powerbi_key = self.intent_key
        if self.response_key is None:
            self.response_key = self.intent_key


class GoldenExpectedSpec(BaseModel):
    """预期结果规格"""
    intent: Optional[str] = None
    terminal_state: Optional[str] = None
    memory_commit: Optional[bool] = None
    response_type: Optional[str] = None
    tool_sequence: Optional[list[str]] = None
    error_type: Optional[str] = None
    inherited_context: Optional[str] = None
    final_memory_version: Optional[int] = None
    state_changes: Optional[dict[str, Any]] = None
    allowed_tools: Optional[list[str]] = None
    forbidden_tools: Optional[list[str]] = None
    measures: Optional[list[str]] = None
    dimensions: Optional[list[str]] = None
    filters: Optional[list[dict]] = None
    time_range: Optional[str] = None
    last_dax: Optional[str] = None
    last_result_summary: Optional[str] = None
    memory_version: Optional[int] = None
    # M0.3.2 失败场景验证
    failed_record_exists: Optional[bool] = None
    failure_reason_contains: Optional[str] = None
    failure_stage: Optional[str] = None
    committed_record_exists: Optional[bool] = None
    pending_record_exists: Optional[bool] = None
    # 幂等
    repeat_target_turn: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class GoldenSetupTurnSpec(BaseModel):
    """Setup Turn 规格"""
    message: str = ""
    request_id: str = ""
    semantic_model_key: str = "mock_sales_model"
    intent_key: str = "data_question"
    query_plan_key: Optional[str] = None
    dax_key: Optional[str] = None
    powerbi_key: Optional[str] = None
    response_key: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class GoldenCaseSpec(BaseModel):
    """Golden Case 结构化规格 — M0.3.2 严格化"""
    id: str
    category: str
    status: str
    description: str = ""
    runtime: GoldenRuntimeSpec = Field(default_factory=GoldenRuntimeSpec)
    input: GoldenInputSpec = Field(default_factory=GoldenInputSpec)
    mock_scenario: GoldenScenarioSpec = Field(default_factory=GoldenScenarioSpec)
    expected: GoldenExpectedSpec = Field(default_factory=GoldenExpectedSpec)
    setup_turns: list[GoldenSetupTurnSpec] = Field(default_factory=list)
    target_turn: Optional[dict[str, Any]] = None
    tags: list[str] = Field(default_factory=list)
    initial_memory: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")

    ALLOWED_STATUSES: ClassVar[set[str]] = {
        "mock_ready", "manual_real_baseline", "deprecated"
    }
    ALLOWED_CATEGORIES: ClassVar[set[str]] = {
        "data_question", "report_generation", "clarification", "unsupported",
        "tool_failure", "validation", "memory_conflict", "tool_policy",
        "edge_case", "multiround",
    }


# =============================================================================
# 结果模型
# =============================================================================

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


# =============================================================================
# 运行器
# =============================================================================

class GoldenCaseRunner:
    """Golden Case 运行器 — M0.3.2 严格化"""

    def __init__(self, cases_path: Path, service_factory=None):
        self.cases_path = Path(cases_path)
        self._service_factory = service_factory

    def _create_service(self) -> MockTurnService:
        """创建独立的 Service — 每个 Case 默认隔离"""
        if self._service_factory:
            return self._service_factory()
        return MockTurnService()

    def load_cases(self) -> list[dict[str, Any]]:
        """加载原始 YAML Cases（保留用于向后兼容的 _validate_case_structure）"""
        cases_file = self.cases_path / "golden_cases.yaml"
        if not cases_file.exists():
            raise FileNotFoundError(f"Golden cases file not found: {cases_file}")

        with open(cases_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw_cases = data.get("cases", [])
        # 验证基础结构
        seen_ids = set()
        for raw in raw_cases:
            self._validate_case_structure(raw)
            case = GoldenCaseSpec(**raw)
            if case.id in seen_ids:
                raise ValueError(f"Duplicate case id: {case.id}")
            seen_ids.add(case.id)
            # 校验五类 Scenario Key 全部存在
            self._validate_scenario_keys(raw, case.id)
        return raw_cases

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

    def _validate_scenario_keys(self, case: dict[str, Any], case_id: str) -> None:
        """校验五类 Scenario Key 全部存在"""
        mock_scenario = case.get("mock_scenario", {})
        required_keys = ["intent_key", "query_plan_key", "dax_key", "powerbi_key", "response_key"]
        for key in required_keys:
            if key not in mock_scenario:
                raise ValueError(f"Case '{case_id}': missing scenario key '{key}'")

    async def run_all_async(self) -> GoldenCaseSummary:
        """异步运行全部 Golden Cases"""
        cases = self.load_cases()
        summary = GoldenCaseSummary()
        summary.defined = len(cases)

        for raw in cases:
            case = GoldenCaseSpec(**raw)
            # 每个 Case 独立 Service
            service = self._create_service()
            result = await self.run_one_async(case, service)
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

    async def run_one_async(
        self, case: GoldenCaseSpec, service: Optional[MockTurnService] = None
    ) -> GoldenCaseResult:
        """异步运行单条 Golden Case"""
        case_id = case.id
        result = GoldenCaseResult(case_id)

        if case.status == "manual_real_baseline":
            result.skipped = True
            result.errors.append(
                "Status is 'manual_real_baseline' — 真实基线由人工 Local Desktop "
                "Business Golden Smoke 验证，通用 CI Runner 不连接 Desktop"
            )
            return result

        runtime = case.runtime
        llm_mode = runtime.llm_mode
        powerbi_mode = runtime.powerbi_mode
        if llm_mode != "mock" or powerbi_mode != "mock":
            result.skipped = True
            result.errors.append(f"Real mode not supported (llm={llm_mode}, pbi={powerbi_mode})")
            return result

        if service is None:
            service = self._create_service()

        start = time.monotonic()

        try:
            # 填充 Scenario Key 默认值
            case.mock_scenario.fill_defaults()

            if case.setup_turns:
                result = await self._run_with_setup(case, service, result)
            else:
                result = await self._run_single(case, service, result)

            # M0.3.2 幂等重放
            if case.expected.repeat_target_turn is not None and case.expected.repeat_target_turn > 1:
                result = await self._verify_idempotent_replay(case, service, result)

            result.duration_ms = (time.monotonic() - start) * 1000
        except Exception as e:
            import traceback
            result.errors.append(f"{type(e).__name__}: {e}")
            result.duration_ms = (time.monotonic() - start) * 1000

        return result

    async def _run_single(
        self, case: GoldenCaseSpec, service: MockTurnService, result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """运行单轮 Case"""
        scenario = case.mock_scenario
        turn_result = await service.execute(
            message=case.input.message,
            conversation_id=case.input.conversation_id,
            request_id=case.input.request_id,
            semantic_model_key=case.input.semantic_model_key,
            report_template_key=case.input.report_template_key,
            scenario=MockScenarioSelection(
                intent_key=scenario.intent_key,
                query_plan_key=scenario.query_plan_key or scenario.intent_key,
                dax_key=scenario.dax_key or scenario.intent_key,
                powerbi_key=scenario.powerbi_key or scenario.intent_key,
                response_key=scenario.response_key or scenario.intent_key,
            ),
        )

        return await self._compare_and_verify(case, turn_result, service, result)

    async def _run_with_setup(
        self, case: GoldenCaseSpec, service: MockTurnService, result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """通过 setup_turns 建立多轮真实 Memory"""
        conv_id = case.input.conversation_id

        for i, setup in enumerate(case.setup_turns):
            qp_key = setup.query_plan_key or setup.intent_key
            d_key = setup.dax_key or setup.intent_key
            p_key = setup.powerbi_key or setup.intent_key
            r_key = setup.response_key or setup.intent_key
            setup_result = await service.execute(
                message=setup.message,
                conversation_id=conv_id,
                request_id=setup.request_id,
                semantic_model_key=setup.semantic_model_key,
                scenario=MockScenarioSelection(
                    intent_key=setup.intent_key,
                    query_plan_key=qp_key,
                    dax_key=d_key,
                    powerbi_key=p_key,
                    response_key=r_key,
                ),
            )
            if setup_result["terminal_state"] != "completed":
                result.errors.append(
                    f"Setup turn {i} failed: {setup_result['terminal_state']}"
                )
                return result

        # 验证 setup 建立了真实 committed memory
        repo = service.pipeline.memory_repo
        latest = await repo.get_latest_committed(conv_id, RuntimeDataMode.MOCK)
        if latest is None:
            result.errors.append("Setup turns did not establish committed memory")
            return result

        # 执行目标 turn
        scenario = case.mock_scenario
        turn_result = await service.execute(
            message=case.input.message,
            conversation_id=conv_id,
            request_id=case.input.request_id,
            semantic_model_key=case.input.semantic_model_key,
            report_template_key=case.input.report_template_key,
            scenario=MockScenarioSelection(
                intent_key=scenario.intent_key,
                query_plan_key=scenario.query_plan_key or scenario.intent_key,
                dax_key=scenario.dax_key or scenario.intent_key,
                powerbi_key=scenario.powerbi_key or scenario.intent_key,
                response_key=scenario.response_key or scenario.intent_key,
            ),
        )

        result = await self._compare_and_verify(case, turn_result, service, result)

        # M0.3.2 多轮 Context 真实继承验证
        if case.expected.inherited_context is not None:
            # 验证目标 turn 收到了 setup turn 的 committed context
            if turn_result.get("inherited_context") is None:
                result.mismatches.append(
                    "Multiround: inherited_context is None — context not inherited"
                )
        # 验证 target turn 的 base_memory_version > 0
        target_mem = await repo.get_by_request_id(case.input.request_id, RuntimeDataMode.MOCK)
        if target_mem is not None and target_mem.state_status == MemoryStatus.COMMITTED:
            if target_mem.base_memory_version < 1:
                result.mismatches.append(
                    f"Multiround: base_memory_version={target_mem.base_memory_version}, "
                    f"should be >= 1 (no context inherited)"
                )

        return result

    async def _verify_idempotent_replay(
        self, case: GoldenCaseSpec, service: MockTurnService, result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """M0.3.2 幂等真实重放 — 执行第二次并验证"""
        repo = service.pipeline.memory_repo

        # 记录第一次的状态
        before_count = repo._get_count()
        before_latest = await repo.get_latest_committed(
            case.input.conversation_id, RuntimeDataMode.MOCK
        )
        before_version = before_latest.memory_version if before_latest else 0

        # 第二次执行（相同 request_id）
        scenario = case.mock_scenario
        replay_result = await service.execute(
            message=case.input.message,
            conversation_id=case.input.conversation_id,
            request_id=case.input.request_id,
            semantic_model_key=case.input.semantic_model_key,
            report_template_key=case.input.report_template_key,
            scenario=MockScenarioSelection(
                intent_key=scenario.intent_key,
                query_plan_key=scenario.query_plan_key or scenario.intent_key,
                dax_key=scenario.dax_key or scenario.intent_key,
                powerbi_key=scenario.powerbi_key or scenario.intent_key,
                response_key=scenario.response_key or scenario.intent_key,
            ),
        )

        # 验证第二次结果
        if replay_result["terminal_state"] not in ("duplicate", "completed"):
            result.mismatches.append(
                f"Idempotent replay: expected duplicate/completed, got {replay_result['terminal_state']}"
            )

        # 版本不应递增
        after_latest = await repo.get_latest_committed(
            case.input.conversation_id, RuntimeDataMode.MOCK
        )
        after_version = after_latest.memory_version if after_latest else 0
        if after_version != before_version:
            result.mismatches.append(
                f"Idempotent replay: version changed from {before_version} to {after_version}"
            )

        # 数量不应增加
        after_count = repo._get_count()
        if after_count != before_count:
            result.mismatches.append(
                f"Idempotent replay: record count changed from {before_count} to {after_count}"
            )

        return result

    async def _compare_and_verify(
        self, case: GoldenCaseSpec, actual: dict[str, Any],
        service: MockTurnService, result: GoldenCaseResult
    ) -> GoldenCaseResult:
        """比较 expected 并验证 Repository"""
        expected = case.expected
        mismatches = self._compare(expected, actual)

        # 读取 Repository 验证 Memory 状态
        repo_mismatches = await self._verify_repository(case, actual, service)
        mismatches.extend(repo_mismatches)

        result.mismatches = mismatches
        if not mismatches:
            result.passed = True
        else:
            result.failed = True

        return result

    async def _verify_repository(
        self, case: GoldenCaseSpec, actual: dict[str, Any],
        service: MockTurnService
    ) -> list[str]:
        """M0.3.2 通过 Repository 验证 Memory 状态（含失败场景）"""
        mismatches: list[str] = []
        repo = service.pipeline.memory_repo

        request_id = actual.get("request_id", "")
        if not request_id:
            return mismatches

        terminal = actual.get("terminal_state", "")
        if terminal in ("clarification_required", "unsupported"):
            return mismatches

        memory = await repo.get_by_request_id(request_id, RuntimeDataMode.MOCK)
        expected = case.expected

        # M0.3.2 失败场景验证
        if expected.failed_record_exists is True:
            if memory is None:
                mismatches.append("Repository: expected failed record exists, got None")
            elif memory.state_status != MemoryStatus.FAILED:
                mismatches.append(
                    f"Repository: expected failed status, got {memory.state_status.value}"
                )
            # committed 不应存在
            if expected.committed_record_exists is False:
                latest = await repo.get_latest_committed(
                    case.input.conversation_id, RuntimeDataMode.MOCK
                )
                if latest is not None:
                    mismatches.append("Repository: unexpected committed record exists")
            # failure reason 包含具体内容
            if expected.failure_reason_contains and memory is not None:
                reason = memory.failure_reason or ""
                if expected.failure_reason_contains not in reason:
                    mismatches.append(
                        f"Repository: failure_reason does not contain '{expected.failure_reason_contains}'"
                    )
            # failure stage
            if expected.failure_stage and memory is not None:
                if memory.failure_stage != expected.failure_stage:
                    mismatches.append(
                        f"Repository: failure_stage expected '{expected.failure_stage}', "
                        f"got '{memory.failure_stage}'"
                    )
            return mismatches

        # 成功场景
        if memory is None:
            if terminal not in ("duplicate",):
                mismatches.append("Repository: memory not found for request_id")
            return mismatches

        if terminal == "completed":
            if memory.state_status.value != "committed":
                mismatches.append(
                    f"Repository: expected committed, got {memory.state_status.value}"
                )
            exp_ver = expected.final_memory_version
            if exp_ver is not None and memory.memory_version != exp_ver:
                mismatches.append(
                    f"Repository: expected memory_version={exp_ver}, got {memory.memory_version}"
                )

        if memory.state_status.value == "committed":
            for key in ["measures", "dimensions", "filters", "time_range", "last_dax"]:
                exp_val = getattr(expected, key, None)
                if exp_val is not None:
                    actual_val = getattr(memory, key, None)
                    if actual_val != exp_val:
                        mismatches.append(
                            f"Repository.{key}: expected {exp_val}, got {actual_val}"
                        )

        # 工具序列来自真实 Trace
        exp_tools = expected.tool_sequence
        if exp_tools is not None:
            actual_tools = actual.get("tool_sequence", [])
            if actual_tools != exp_tools:
                mismatches.append(
                    f"tool_sequence: expected {exp_tools}, got {actual_tools}"
                )

        return mismatches

    def _compare(
        self, expected: GoldenExpectedSpec, actual: dict[str, Any]
    ) -> list[str]:
        """精确比较预期与实际结果"""
        mismatches: list[str] = []

        # 遍历 expected 中所有显式设置的字段
        for key in expected.model_fields_set:
            exp_val = getattr(expected, key, None)
            if exp_val is None:
                continue
            actual_val = actual.get(key)

            if key == "tool_sequence":
                if actual_val != exp_val:
                    mismatches.append(f"tool_sequence: expected {exp_val}, got {actual_val}")
            elif key == "terminal_state":
                if actual_val != exp_val:
                    mismatches.append(f"terminal_state: expected {exp_val}, got {actual_val}")
            elif key == "memory_commit":
                if actual_val != exp_val:
                    mismatches.append(f"memory_commit: expected {exp_val}, got {actual_val}")
            elif key == "final_memory_version":
                if actual_val != exp_val:
                    mismatches.append(f"final_memory_version: expected {exp_val}, got {actual_val}")
            elif key == "response_type":
                if actual_val != exp_val:
                    mismatches.append(f"response_type: expected {exp_val}, got {actual_val}")
            elif key == "error_type":
                if actual_val != exp_val:
                    mismatches.append(f"error_type: expected {exp_val}, got {actual_val}")
            elif key == "intent":
                if actual_val != exp_val:
                    mismatches.append(f"intent: expected {exp_val}, got {actual_val}")
            elif key == "inherited_context":
                if actual_val is None:
                    mismatches.append(f"inherited_context: expected '{exp_val}', got None")
                elif actual_val != exp_val:
                    mismatches.append(f"inherited_context: expected '{exp_val}', got '{actual_val}'")
            elif key == "allowed_tools":
                if set(actual_val or []) != set(exp_val or []):
                    mismatches.append("allowed_tools mismatch")
            elif key == "forbidden_tools":
                for ft in (exp_val or []):
                    if ft in (actual_val or []):
                        mismatches.append(f"forbidden_tool '{ft}' was called")
            elif key in ("measures", "dimensions", "filters", "time_range",
                        "last_dax", "last_result_summary", "memory_version"):
                if actual_val != exp_val:
                    mismatches.append(f"{key}: expected {exp_val}, got {actual_val}")
            # 跳过内部验证字段（failed_record_exists 等在 _verify_repository 中使用）
            elif key in ("failed_record_exists", "failure_reason_contains", "failure_stage",
                        "committed_record_exists", "pending_record_exists", "repeat_target_turn",
                        "state_changes"):
                pass
            else:
                mismatches.append(f"Unknown expected field: {key}")

        return mismatches

    # ---- 同步兼容入口 ----

    def run_all(self) -> GoldenCaseSummary:
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.run_all_async())
                return future.result(timeout=300)
        except RuntimeError:
            return asyncio.run(self.run_all_async())

    def run_one(self, case: dict[str, Any]) -> GoldenCaseResult:
        case_spec = GoldenCaseSpec(**case)
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.run_one_async(case_spec))
                return future.result(timeout=60)
        except RuntimeError:
            return asyncio.run(self.run_one_async(case_spec))
