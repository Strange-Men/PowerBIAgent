# 13 — M1.6 最终候选版架构审计

> **AUDIT-166-001：M1.6.6 最终候选审计**
> **最后更新：2026-08-05 | M1.6.6**
> **状态：AUDIT-166-001 完成**

---

## 审计方法

每项重新核查当前生产代码、行为测试和 CI 门禁。状态仅允许：已解决 / 部分解决 / 未解决 / 复发风险 / 不适用。没有真实行为证据的项目不得标记为已解决。

---

## 审计矩阵

### 1. PydanticAI 生产依赖是否为 0

| 维度 | 内容 |
|------|------|
| **检查对象** | `pyproject.toml` 依赖声明、`backend/app/` 生产 import |
| **当前代码证据** | `pyproject.toml` 无 `pydantic-ai` 声明；全仓 git grep `pydantic.ai` 生产代码返回 0 |
| **行为测试** | `test_agent_framework.py`: `import backend.app.agent.runtime` → ImportError |
| **CI 门禁** | CI 第 4 步含 git grep `pydantic.ai` 残留检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 — pip/conda 环境残留仅影响本地，CI 环境从零安装 |

### 2. AgentRuntime 残留是否为 0

| 维度 | 内容 |
|------|------|
| **检查对象** | `backend/app/agent/` 目录、生产代码 import |
| **当前代码证据** | `backend/app/agent/` 目录不存在；生产代码 `AgentRuntime` 仅在 `mock_turn_service.py` 注释/文档字符串中出现（向后兼容适配器说明） |
| **行为测试** | `test_agent_framework.py`: AgentRuntime 不可导入、TurnPipeline 统一类型 |
| **CI 门禁** | CI 第 4 步含 git grep `AgentRuntime` 生产代码检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 3. Mock 与 DeepSeek 是否共享 TurnPipeline

| 维度 | 内容 |
|------|------|
| **检查对象** | `MockTurnService` 和 `DeepSeekTurnService` 的 `TurnPipeline` 使用 |
| **当前代码证据** | 两个 Service 均使用 `TurnPipeline` 类（`turn_pipeline.py`）；`execute()` 骨架共享 ID 生成、指纹、幂等、TurnController、ContextBuilder |
| **行为测试** | `test_agent_framework.py`: 两个 Service 使用同一 `TurnPipeline` 类型；`test_m166_turn_controller_limits.py`: 验证 TurnController 类型一致 |
| **CI 门禁** | 全量 pytest 覆盖两个 Service 的 TurnPipeline 路径 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 4. 是否存在第二套隐藏执行管线

| 维度 | 内容 |
|------|------|
| **检查对象** | 所有 `do_execute` 回调入口、直接 LLM 调用路径 |
| **当前代码证据** | 仅有 `MockTurnService._do_execute` 和 `DeepSeekTurnService._do_execute` 两个入口；`TurnPipeline.execute()` 是唯一调用入口；没有绕过 TurnPipeline 的 `ChatResponse` 返回路径 |
| **行为测试** | 全量 API 测试均经过 `TurnPipeline.execute()` |
| **CI 门禁** | 全仓架构搜索 + 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 5. ToolGateway 是否仍为唯一工具入口

| 维度 | 内容 |
|------|------|
| **检查对象** | 生产代码中所有 `execute_dax`/`get_schema`/`render_report` 调用 |
| **当前代码证据** | 两个 Service 的 `_do_execute` 中所有工具调用均通过 `self.tool_gateway.execute()`；git grep `self.powerbi.` / `self.report_renderer.` 在 Service 源码返回 0 |
| **行为测试** | `test_m166_prompt_injection_spy.py`: Spy 验证所有 tool 调用经过 Gateway；工具名全在白名单内 |
| **CI 门禁** | CI 第 4 步含直接 Adapter 调用检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 6. 是否存在 Service 直接调用 Adapter

| 维度 | 内容 |
|------|------|
| **检查对象** | `mock_turn_service.py` / `deepseek_turn_service.py` 的 Adapter 直接调用 |
| **当前代码证据** | 所有工具调用经过 `self.tool_gateway.execute("tool_name", ...)`；Adapter 仅作为 Gateway 构造参数注入，不作为直接调用目标 |
| **行为测试** | `test_m166_prompt_injection_spy.py`: Adapter Spy 与 Gateway Spy 调用对应验证 |
| **CI 门禁** | 架构门禁 git grep |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 7. ContextBuilder 是否覆盖两条路径

| 维度 | 内容 |
|------|------|
| **检查对象** | `TurnPipeline.execute()` 中 ContextBuilder 调用 |
| **当前代码证据** | `TurnPipeline.execute()` 统一调用 `self.context_builder.build()` 并传递 context dict 给两个 `_do_execute` 回调；两个 Service 不再创建自己的 ContextBuilder |
| **行为测试** | `test_agent_framework.py`: `test_mock_service_no_own_context_builder` / `test_deepseek_service_no_own_context_builder` |
| **CI 门禁** | 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 8. TurnController 限制是否真实生效

| 维度 | 内容 |
|------|------|
| **检查对象** | `check_tool_call_limit()` 是否在 `ToolGateway.execute()` 中被调用 |
| **当前代码证据** | `ToolGateway.execute()` 执行 handler 前调用 `controller.check_tool_call_limit()`（line 252）；`TurnPipeline.execute()` 创建 controller 并传递给 `_do_execute` |
| **行为测试** | `test_m166_turn_controller_limits.py`: 10 个合同测试 + 7 个管线集成测试（含真实 Service→Pipeline→Gateway→Controller→Adapter 路径）；Mutation 验证通过 |
| **CI 门禁** | CI 全量 pytest 含 TurnController 限制测试 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 — max_tool_calls 限制仅在 ToolGateway.execute 中生效，DAX/LLM 修复限制在 Service 中独立调用 |

### 9. HarnessConfig 是否统一构建

| 维度 | 内容 |
|------|------|
| **检查对象** | `HarnessConfig.from_settings()` 调用路径 |
| **当前代码证据** | `main.py` lifespan 中统一从 `Settings` 构建一次 `HarnessConfig`，显式传给两个 Service；Settings 版本已同步至 M1.6.6 |
| **行为测试** | `test_m162_config.py`: Settings 与 HarnessConfig Enum 统一、from_settings 全字段映射、lifespan 配置传递 |
| **CI 门禁** | 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 10. Memory 是否只有 TurnPipeline 写入

| 维度 | 内容 |
|------|------|
| **检查对象** | 生产代码中 `memory_repo` 写操作位置 |
| **当前代码证据** | 所有 `create_pending`/`mark_failed`/`commit` 操作均在 `TurnPipeline` 方法中；Service 不持有 `memory_repo` 实例字段（M1.6.3.2 收口） |
| **行为测试** | `test_m1632_transaction_boundary.py`: 源码静态门禁 + Snapshot 调用次数 + Memory 事务边界 |
| **CI 门禁** | 架构门禁 git grep `self.memory_repo` |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 11. Snapshot 是否只有 TurnPipeline 管理

| 维度 | 内容 |
|------|------|
| **检查对象** | 生产代码中 `SnapshotStore` 调用位置 |
| **当前代码证据** | `SnapshotStore.save/complete/abort` 仅在 `TurnPipeline.execute()` 和 `_save_snapshot()` 中调用；Service 不持有 `snapshot_store` 实例字段 |
| **行为测试** | `test_m1632_transaction_boundary.py`: `test_successful_owner_saves_snapshot_exactly_once` |
| **CI 门禁** | 全仓架构搜索 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 12. Service 是否暴露可写 Repository

| 维度 | 内容 |
|------|------|
| **检查对象** | `MockTurnService` / `DeepSeekTurnService` 公开属性 |
| **当前代码证据** | 两个 Service 均无 `memory_repo` @property（M1.6.4 移除）；只读查询通过 `TurnPipeline` 只读方法 |
| **行为测试** | `test_m164_arch_truth_adv.py`: `test_service_has_no_memory_repo_property` |
| **CI 门禁** | 架构门禁 git grep |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 13. Owner/Waiter 幂等是否正常

| 维度 | 内容 |
|------|------|
| **检查对象** | `ResultSnapshotStore.claim/complete/abort` 流程 |
| **当前代码证据** | `TurnPipeline.execute()` 完整实现 claim→OWNER/WAITER/CONFLICT 流程；await claim_future 超时 3 次重试 |
| **行为测试** | Golden Case gc_011（幂等重放）；`test_m1_0_1_fixes.py` 并发 Owner/Waiter 测试 |
| **CI 门禁** | Golden Cases |
| **当前状态** | **已解决** |
| **剩余风险** | 低 — 单进程保证，分布式需后续处理 |

### 14. Mock 和 Real 空间是否隔离

| 维度 | 内容 |
|------|------|
| **检查对象** | `RuntimeDataMode` 在 Memory 和 Snapshot 中的使用 |
| **当前代码证据** | `InMemoryMemoryRepository` 使用 `(runtime_mode, ...)` 复合键；`ResultSnapshotStore` 使用 `(runtime_mode, request_id)` 复合键；Mock 和 REAL 互不可见 |
| **行为测试** | `test_m1_2_intent_isolation.py` + Golden Cases 隔离验证 |
| **CI 门禁** | 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 15. Provider 错误是否结构化映射

| 维度 | 内容 |
|------|------|
| **检查对象** | `routes.py` 错误映射 + `deepseek.py` 异常分类 |
| **当前代码证据** | 10 种 LLM 异常类型 + HTTPX 细化（ConnectTimeout/ReadTimeout/WriteTimeout/PoolTimeout）；402 独立映射为 `insufficient_balance`；未知配置错误不再伪装为 `api_key_missing` |
| **行为测试** | `test_m165_exception_integration.py`: 23 个 ASGI 集成测试（17 种异常类型） |
| **CI 门禁** | CI 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 16. AI 数值是否可追溯到 QueryResult

| 维度 | 内容 |
|------|------|
| **检查对象** | Answer evidence 绑定、KPI/Table/Chart 数据来源 |
| **当前代码证据** | `AnswerSpec.evidence` 强制绑定 `result_id/semantic_model_key/row_count/source_mode`；`ValidationService` 验证数值一致性、KPI bool/None/str 拒绝、虚构值拒绝 |
| **行为测试** | `test_m164_arch_truth_adv.py`: AI 真实性门禁 |
| **CI 门禁** | CI 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 — Mock QueryResult 场景下虚构检测覆盖有限 |

### 17. Prompt 注入行为测试是否有真实调用证据

| 维度 | 内容 |
|------|------|
| **检查对象** | ToolGateway Spy 记录、Adapter Spy 记录 |
| **当前代码证据** | `test_m166_prompt_injection_spy.py`: 20 个 Spy 测试，ToolGateway.execute 被 `Mock(wraps=...)` 记录真实调用 |
| **行为测试** | Spy 验证：实际调用工具名、白名单约束、危险工具 0 次、Registry 不变、Config 不变、Adapter 对应、无绕过 |
| **CI 门禁** | CI 全量 pytest 含 Spy 测试 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 18. 纸面测试是否被错误当作行为证据

| 维度 | 内容 |
|------|------|
| **检查对象** | 现有测试是否仅做静态字符串/源码检查而无真实执行路径 |
| **当前代码证据** | M1.6.4 的 `test_m164_arch_truth_adv.py` 含部分静态源码搜索测试（如 `test_service_has_no_memory_repo_property`）；M1.6.5—M1.6.6 新增 ASGI/Spy/Pipeline 测试覆盖真实执行路径 |
| **行为测试** | `test_m165_prompt_injection.py`: 真实 ASGI 路径；`test_m165_exception_integration.py`: 真实 ASGI 路径；`test_m166_prompt_injection_spy.py`: Spy 真实调用证据；`test_m166_turn_controller_limits.py`: Pipeline 集成路径 |
| **CI 门禁** | 两类测试均在 CI 中运行 |
| **当前状态** | **部分解决** |
| **剩余风险** | 中 — 静态源码搜索测试仍作为辅助门禁保留；部分"行为验证"仍依赖响应字段断言而非执行路径拦截点 |

### 19. 错题本是否可执行、可校验

| 维度 | 内容 |
|------|------|
| **检查对象** | `scripts/check_ai_error_ledger.py` + YAML 文件 |
| **当前代码证据** | YAML 无 U+FFFD、8 条条目、所有 resolved 条目的 Commit SHA 经 Git 验证存在；校验器 47 个单元测试全部通过；支持 --json 输出 |
| **行为测试** | `test_m165_error_ledger.py`: 47 个测试（含 M1.6.6 新增 8 个） |
| **CI 门禁** | CI 第 2 步 `python scripts/check_ai_error_ledger.py` |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 20. CI 是否真实运行全部关键门禁

| 维度 | 内容 |
|------|------|
| **检查对象** | `.github/workflows/m16_candidate_validation.yml` |
| **当前代码证据** | 工作流含：安全扫描、错题本校验、文档一致性、架构门禁、全量 pytest、Golden Cases、git diff check |
| **行为测试** | GitHub Actions 远程运行结果（Push 后验证） |
| **CI 门禁** | 自包含 |
| **当前状态** | **部分解决**（本地代码已就绪，远程 CI 结果待 Push 后确认） |
| **剩余风险** | 低 — CI 使用 `windows-latest`，需确认远程 Golden Cases 在 Windows CI 可正常执行 |

### 21. 文档是否夸大实际能力

| 维度 | 内容 |
|------|------|
| **检查对象** | `README.md`、`docs/08`、`docs/09` |
| **当前代码证据** | README 明确"M1.6.6 二审候选版"、真实 Power BI 属 M2、不声称正式发布；docs/08 明确"不创建Tag、不执行真实DeepSeek Smoke"；docs/09 明确"等待仓库二审" |
| **行为测试** | `test_m1_0_1_fixes.py` 文档一致性测试通过 |
| **CI 门禁** | CI 第 3 步文档一致性检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 22. 是否提前实现 M2

| 维度 | 内容 |
|------|------|
| **检查对象** | `backend/app/powerbi/` 是否存在真实 MCP 连接代码；OAuth 实现 |
| **当前代码证据** | `remote_mcp.py` 仅有骨架 stub（返回 503）；无 OAuth/Entra 代码；无真实 DAX 执行 |
| **行为测试** | Health: `powerbi_mode=remote_mcp` → 503 |
| **CI 门禁** | 全量 pytest 中 Remote MCP 路径测试均为 skip |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 23. 是否出现绕过 ADR-005 的新入口

| 维度 | 内容 |
|------|------|
| **检查对象** | API 路由、Service 入口、直接 LLM 调用路径 |
| **当前代码证据** | 仅有 `/api/v1/chat` POST 和 `/health` GET；无其他公开 API 端点；TurnPipeline 为唯一执行入口 |
| **行为测试** | 全量 API 测试均经过 TurnPipeline |
| **CI 门禁** | 架构门禁 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 24. 是否存在 Secret、真实 Prompt 或真实响应入库

| 维度 | 内容 |
|------|------|
| **检查对象** | Memory 持久化内容、Snapshot 内容、Trace 事件 |
| **当前代码证据** | `TraceRecorder._safe_summary()` 排除完整数据；Memory 不存储 LLM prompt/response 原文；Prompt 模板无 Secret 嵌入；.env 未被 Git 跟踪 |
| **行为测试** | `test_m165_prompt_injection.py`: Secret 模式不出现；`test_m166_prompt_injection_spy.py`: Gateway 参数无 Secret |
| **CI 门禁** | 安全扫描 + Secret 检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

### 25. 是否存在无限循环、无限重试或自动反复调用 LLM

| 维度 | 内容 |
|------|------|
| **检查对象** | 重试循环、LLM 修复限制、工具重试限制 |
| **当前代码证据** | Intent/QueryPlan/DAX/Answer 各阶段最多 1 次修复（Provider 调用 ≤ 2 次）；工具重试 ≤ `max_retries`（默认 1）；Owner/Waiter 协调 ≤ 3 次；TurnController 强制 `max_tool_calls=3` |
| **行为测试** | `test_m166_turn_controller_limits.py`: DAX 修复限制、LLM 重试限制测试通过 |
| **CI 门禁** | 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

## 审计统计

| 状态 | 数量 | 项目 |
|------|------|------|
| 已解决 | 23 | #1—#7, #9—#17, #19, #21—#25 |
| 部分解决 | 2 | #18（纸面测试残余）、#20（CI 远程结果待确认） |
| 未解决 | 0 | — |
| 复发风险 | 0 | — |
| 不适用 | 0 | — |

---

## P0 阻塞项

无。

## P1 非阻塞项

1. **#18 纸面测试残余** — 部分静态源码检查测试仍作为行为证据保留，建议 M2 前全部替换为 Spy/Pipeline 集成测试
2. **#20 CI 远程结果** — 本地代码已就绪，需 Push 后 GitHub Actions 真实运行确认

## 可延后到 M2 的事项

- 真实 Power BI MCP 接入（含 OAuth、Entra、Remote MCP）
- 真实 DAX 语义模型验证
- 报表正式渲染管线
- 会话持久化与搜索
- React 前端开发
- 分布式幂等与持久化锁
- 纸面测试全部替换为集成测试

## 是否具备进入二审条件

**是。** 25 项审计中 23 项已解决、2 项部分解决（均为非阻塞项）。本地全部门禁通过（1230 pytest、11/11 Golden Cases、安全扫描 PASS、错题本校验 PASS）。无 P0 未解决项。可以创建候选 Commit 并 Push，等待仓库二审。

**不得在二审通过前声称 M1.6 正式封板完成。**

---

*最后更新：2026-08-05 | M1.6.6 最终候选审计完成*
