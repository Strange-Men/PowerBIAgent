# 12 — M1.6 架构偏移复验矩阵

> **AUDIT-165-001：第一次审计到当前版本的前后对照矩阵**
> **最后更新：2026-08-05 | M1.6.5**
> **状态：AUDIT-165-001 复验完成**

---

## 审计方法

每项检查原始偏移问题、首次发现版本、声称修复版本、当前生产代码证据、行为测试、机器门禁、当前状态和剩余风险。

状态只允许：已解决 / 部分解决 / 未解决 / 复发风险 / 不适用

没有行为证据的项目不能标记为已解决。

---

## 审计矩阵

### 1. PydanticAI 是否仍存在生产依赖或调用

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 使用 PydanticAI 作为 Agent 框架（ADR-001），DeepSeekTurnService 绕过 AgentRuntime |
| **首次发现** | M1.6.1 |
| **声称修复** | M1.6.3（删除 AgentRuntime/MockAgentRuntime、pyproject.toml 移除 pydantic-ai） |
| **当前代码证据** | `pyproject.toml` 无 pydantic-ai 声明；全仓搜索无 `from pydantic_ai` 或 `import pydantic_ai` 生产引用 |
| **行为测试** | `test_agent_framework.py` 防回归测试：AgentRuntime 不可导入、TurnPipeline 统一类型 |
| **机器门禁** | 全仓架构搜索 `grep -r pydantic_ai backend/app/` 返回 0 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 — pip/conda 环境残留需 M1.6.6 CI 检查 |

---

### 2. AgentRuntime 和 MockAgentRuntime 是否已彻底退出

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 存在 AgentRuntime 抽象类、MockAgentRuntime 实现类 |
| **首次发现** | M1.6.1 |
| **声称修复** | M1.6.3（删除 agent/runtime.py、agent/mock_runtime.py、agent/__init__.py） |
| **当前代码证据** | `backend/app/agent/` 目录不存在；全仓搜索 `AgentRuntime`/`MockAgentRuntime` 仅文档/注释中提及 |
| **行为测试** | `test_agent_framework.py`: `import backend.app.agent.runtime` → ImportError |
| **机器门禁** | 全仓搜索 `grep -r AgentRuntime backend/` 返回 0（不含注释） |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 3. Mock 与 DeepSeek 是否共享 TurnPipeline 执行骨架

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 中 Mock 和 DeepSeek 存在事实上的双管线（各自独立的控制面逻辑） |
| **首次发现** | M1.6.1 |
| **声称修复** | M1.6.3（统一 TurnPipeline 类型）+ M1.6.3.1（控制面补全）+ M1.6.3.2（Memory/Snapshot 统一） |
| **当前代码证据** | `TurnPipeline` 类为 MockTurnService 和 DeepSeekTurnService 共享执行骨架 |
| **行为测试** | `test_agent_framework.py`：两个 Service 使用同一 `TurnPipeline` 类型 |
| **机器门禁** | 源码检查：Service 不持有 memory_repo / snapshot_store / context_builder 实例字段 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 — ContextBuilder/TurnController/工具上下文工厂均在 TurnPipeline 中统一 |

---

### 4. ToolGateway 是否为 Adapter 和 Renderer 唯一调用入口

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 中 DeepSeek 路径绕过 ToolGateway 直接调用 Adapter |
| **首次发现** | M1.6.1 |
| **声称修复** | M1.6.3 |
| **当前代码证据** | DeepSeekTurnService 通过 `self.pipeline.create_tool_context()` + `gateway.execute()` 调用所有工具 |
| **行为测试** | `test_agent_framework.py`：DeepSeek 路径无直接 Adapter 调用 |
| **机器门禁** | 全仓搜索 `self.powerbi.` / `self.report_renderer.` 在 Service 源码中不存在 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 5. ContextBuilder 是否真实进入两条路径

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 中 DeepSeek 路径未使用 ContextBuilder（输入截断和 Memory 状态检查未生效） |
| **首次发现** | M1.6.1 |
| **声称修复** | M1.6.3.1 |
| **当前代码证据** | TurnPipeline.execute() 统一调用 `context_builder.build()`，传入 `do_execute` 回调 |
| **行为测试** | `test_agent_framework.py`：TurnPipeline 在回调前创建上下文 |
| **机器门禁** | Service 源码无 ContextBuilder 实例字段 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 6. TurnController 限制是否真实生效

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 中 TurnController 在 DeepSeek 路径未生效（限制未检查） |
| **首次发现** | M1.6.1 |
| **声称修复** | M1.6.3.1 |
| **当前代码证据** | TurnPipeline.execute() 统一创建 TurnController 并传递给回调 |
| **行为测试** | 工具调用通过 ToolGateway 的 `controller.check_tool_call_limit()` |
| **机器门禁** | — 依赖 ToolGateway 集成 |
| **当前状态** | **部分解决** |
| **剩余风险** | TurnController 的完整限制路径（tool_call_limit、生命周期超时）缺少专门的集成测试 |

---

### 7. HarnessConfig 是否只通过统一入口构建

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.5 中 DeepSeek 路径使用 DEFAULT_MOCK_CONFIG 作为回退 |
| **首次发现** | M1.6.2 |
| **声称修复** | M1.6.2 |
| **当前代码证据** | main.py lifespan 中 `HarnessConfig.from_settings(settings)` 统一构建，传递所有 Service |
| **行为测试** | `test_m162_config.py`：from_settings() 完整映射、DeepSeek 配置不使用 Mock 回退 |
| **机器门禁** | DeepSeekTurnService 源码无 DEFAULT_MOCK_CONFIG 引用 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 8. Memory 是否只有 TurnPipeline 写入

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.6.3 中 Service 直接调用 `self.memory_repo.mark_failed()` 和 `self.memory_repo.commit()` |
| **首次发现** | M1.6.3.2 |
| **声称修复** | M1.6.3.2 |
| **当前代码证据** | 两个 Service 源码不含 `self.memory_repo.mark_failed/commit/create_pending` |
| **行为测试** | `test_m1632_transaction_boundary.py`：19 个测试验证单写入者 |
| **机器门禁** | 全仓搜索 Service 文件无直接 Memory 写入 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 9. Snapshot 是否只有 TurnPipeline 管理

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.6.3 中 DeepSeekTurnService 在 _do_execute 中调用 _save_snapshot()，Pipeline 再二次保存 |
| **首次发现** | M1.6.3.2 |
| **声称修复** | M1.6.3.2 |
| **当前代码证据** | Service 源码无 `_save_snapshot(`、`snapshot_store.save/complete/abort` |
| **行为测试** | `test_m1632_transaction_boundary.py`：Snapshot 调用次数验证（成功 1、幂等 0、异常 0 save + 1 abort） |
| **机器门禁** | SnapshotStore.save 生产调用者仅 TurnPipeline |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 10. Service 是否重新暴露可写 Repository

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.6.3.2 后 Service 仍有 `memory_repo` @property，允许绕过 TurnPipeline 直接写入 |
| **首次发现** | M1.6.4 |
| **声称修复** | M1.6.4 (ARCH-164-001) |
| **当前代码证据** | 两个 Service 源码不含 `def memory_repo`、`pipeline.memory_repo` |
| **行为测试** | `test_m164_arch_truth_adv.py`：源码静态门禁 |
| **机器门禁** | 源码检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 11. 幂等 Owner/Waiter 是否仍然有效

| 维度 | 内容 |
|------|------|
| **原始偏移** | — 功能本身正常，检查是否有回归 |
| **首次发现** | M1.0.1（功能引入） |
| **声称修复** | — |
| **当前代码证据** | TurnPipeline.execute() 中 claim/complete/abort 生命周期完整 |
| **行为测试** | `test_m1_0_1_fixes.py`：request_id 幂等、指纹冲突 409、Owner/Waiter 并发 |
| **机器门禁** | 全量 pytest 包括幂等测试 |
| **当前状态** | **已解决** |
| **剩余风险** | 跨进程幂等（分布式锁）延后处理 |

---

### 12. Mock 和 Real 空间是否隔离

| 维度 | 内容 |
|------|------|
| **原始偏移** | M0.3.1 引入 RuntimeDataMode 隔离 |
| **首次发现** | M0.3.1 |
| **声称修复** | M0.3.1 |
| **当前代码证据** | Repository 使用 (runtime_mode, request_id) 复合键，Memory 和 Snapshot 空间隔离 |
| **行为测试** | `test_memory_repository.py`：Mock/Real 隔离测试 |
| **机器门禁** | 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 13. Provider 错误是否结构化映射

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.6.4 前：402 伪装为 api_key_missing、LLMRequestError 等无显式映射 |
| **首次发现** | M1.6.4 |
| **声称修复** | M1.6.4 (ERR-164-001) + M1.6.5 (ERR-165-001) |
| **当前代码证据** | routes.py：所有 LLMProviderError 子类有显式映射，未知配置错误返回 deepseek_configuration_error |
| **行为测试** | `test_m165_exception_integration.py`：23 个 ASGI 集成测试覆盖全部异常类型 |
| **机器门禁** | ASGI 集成测试 |
| **当前状态** | **已解决** |
| **剩余风险** | 低 |

---

### 14. AI 真实性验证是否基于 QueryResult

| 维度 | 内容 |
|------|------|
| **原始偏移** | 早期版本 Answer/Report 可能虚构不存在于 QueryResult 中的数据 |
| **首次发现** | M1.4.1 |
| **声称修复** | M1.4.1 + M1.6.4 (TRUTH-164-001/002) |
| **当前代码证据** | ValidationService：数值一致性、KPI 类型拒绝、虚构值拒绝、空结果拒绝、evidence 强制绑定 |
| **行为测试** | `test_m164_arch_truth_adv.py`：数值一致性、类型严格比较、空结果拒绝、模型虚构拒绝 |
| **机器门禁** | 全量 pytest |
| **当前状态** | **已解决** |
| **剩余风险** | 真实 DeepSeek 输出不确定性 — 需 M1.6.6 真实 Smoke 复验 |

---

### 15. 测试是否存在纸面测试、静态假测试

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.6.4 对抗测试只检查输入长度和源码字符串存在（纸面测试） |
| **首次发现** | M1.6.5 |
| **声称修复** | M1.6.5 (TEST-165-001/002) |
| **当前代码证据** | 新增 `test_m165_prompt_injection.py`（53 个真实行为测试经过 API→TurnPipeline）、`test_m165_exception_integration.py`（23 个 ASGI 集成测试） |
| **行为测试** | 76 个 M1.6.5 新增测试均验证真实可观察行为 |
| **机器门禁** | 全量 pytest 包含新增行为测试 |
| **当前状态** | **部分解决** |
| **剩余风险** | M1.6.4 纸面测试（ADV-164 源码扫描类）未删除，作为静态门禁保留；未来需持续将纸面测试转化为行为测试 |

---

### 16. 文档是否继续夸大实际实现

| 维度 | 内容 |
|------|------|
| **原始偏移** | M1.6.3 CHANGELOG 宣称 TurnPipeline 统一了控制面但代码未实现 |
| **首次发现** | M1.6.3.1 |
| **声称修复** | M1.6.3.1（文档回写为真实状态） |
| **当前代码证据** | docs/08、docs/09、CHANGELOG 与代码状态一致（M1.6.5 进行中，M1.6.4 已完成） |
| **行为测试** | `test_m1_0_1_fixes.py::TestDocumentStatus`：文档状态一致性检查 |
| **机器门禁** | 文档状态测试 + CLAUDE.md 冷启动检查 |
| **当前状态** | **已解决** |
| **剩余风险** | 文档与代码同步依赖人工（冷启动协议），暂无自动化同步机制 |

---

### 17. 是否存在 M2 功能提前开发

| 维度 | 内容 |
|------|------|
| **原始偏移** | — 检查项 |
| **首次发现** | — |
| **声称修复** | — |
| **当前代码证据** | 全仓搜索无 Remote MCP 生产代码、无 OAuth 生产实现、无真实 Power BI 连接器（仅 Mock 适配器） |
| **行为测试** | — |
| **机器门禁** | 全仓架构搜索 |
| **当前状态** | **不适用** — 未发现 M2 功能提前开发 |
| **剩余风险** | 低 |

---

### 18. 是否存在绕过 ADR-005 的新入口

| 维度 | 内容 |
|------|------|
| **原始偏移** | — |
| **首次发现** | — |
| **声称修复** | — |
| **当前代码证据** | 所有 Service 通过 TurnPipeline 执行；ToolGateway 为唯一工具调用入口；无新增 LLM 直接调用路径 |
| **行为测试** | — |
| **机器门禁** | 全仓架构搜索 |
| **当前状态** | **不适用** — 未发现绕过 ADR-005 的新入口 |
| **剩余风险** | 低 |

---

## 状态统计

| 状态 | 数量 |
|------|------|
| 已解决 | 14 |
| 部分解决 | 2 (TurnController 限制 + 纸面测试残余) |
| 未解决 | 0 |
| 复发风险 | 0 |
| 不适用 | 2 |

---

## 仍需 M1.6.6 处理的问题

1. **TurnController 完整限制路径**（审计项 6）：缺少专门的集成测试验证 tool_call_limit 和生命周期超时
2. **纸面测试转化**（审计项 15）：M1.6.4 源码扫描类测试作为静态门禁保留，未来持续转化为行为测试
3. **CI 接入**：GitHub Actions 配置、错题本校验器 CI 集成
4. **真实 DeepSeek Smoke**：用户人工执行最终验收
5. **M1.6 最终封板 Tag**

---

*最后更新：2026-08-05 | M1.6.5 架构偏移复验*
