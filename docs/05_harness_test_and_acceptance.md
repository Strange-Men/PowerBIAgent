# 05 — Harness、测试与验收

> **状态：** M0.3 实质性完成（轻量 ETCLOVG 设计）
> **关联 ADR：** ADR-004

---

## 一、Harness ETCLOVG 设计

### E: Execution — HarnessConfig

- APP_ENV、LLM_MODE、POWERBI_MODE、HARNESS_MODE
- 超时、最大行数、工具调用限制、重试限制
- 默认 Mock 执行模式，Production 必须 strict

### T: Tooling — ToolGateway

- 工具注册、重复注册拒绝、未注册工具拒绝
- Intent 权限检查、UserContext 权限检查
- 输入/输出 Pydantic 校验
- async timeout、有限重试
- 工具策略矩阵（Intent → 允许的工具）

### C: Context — ContextBuilder

- 注入：系统规则、当前输入、committed memory、最近5轮、Schema子集、Mock标记
- 禁止：全部历史、完整Schema、Secret、failed/pending memory
- 输入长度限制、Secret字段递归排除

### L: Lifecycle — TurnController

- 12 个正常状态 + 7 个终止状态
- 合法状态转换表，非法跳转拒绝
- 工具调用次数/DAX修复/LLM格式重试/PowerBI查询重试限制
- MemoryCommitEvidence 生成
- can_continue()、can_commit_memory() 判断

### O: Observability — TraceRecorder

- 15 种 Trace 事件类型
- JSON 结构化 logging + 内存事件列表
- 递归 Secret 过滤
- M0.3 内存实现，不实现 SQLite/OpenTelemetry

### V: Verification — ValidationService

- Intent、QueryPlan、DAX、QueryResult、Report、Memory 六类验证
- 结构化 ValidationResult（valid + errors + warnings）

### G: Governance — Policies

- LLM Provider 白名单、Power BI Adapter 白名单
- 语义模型白名单、报表模板白名单
- 工具白名单、只读查询、禁止跨模型
- Secret 过滤、Mock/Real 隔离、UserContext 权限

## 二、Golden Cases

### 位置
`harness/cases/golden_cases.yaml`

### M0.3 首批 10 条

| ID | 类别 | 状态 |
|----|------|------|
| gc_001 | 普通数据问答成功 | mock_ready |
| gc_002 | 多轮筛选继承 | mock_ready |
| gc_003 | 报表生成成功 | mock_ready |
| gc_004 | clarification 不调用工具 | mock_ready |
| gc_005 | unsupported 不调用工具 | mock_ready |
| gc_006 | 工具失败不提交 Memory | mock_ready |
| gc_007 | 虚假字段被拒绝 | mock_ready |
| gc_008 | Memory 版本冲突 | mock_ready |
| gc_009 | 未注册工具被拒绝 | pending_real_baseline |
| gc_010 | 超大结果被截断 | mock_ready |

### GoldenCaseRunner（`backend/app/harness/cases/case_runner.py`）

- 加载 YAML、校验结构
- 注入 initial_memory、运行 MockTurnService
- 收集 Trace、比较 expected
- 输出单条和全量结果
- 重点比较：Intent、Tool 序列、状态流转、Memory 提交、Error Type、Response Type
- 不逐字比较自然语言答案

## 三、测试策略

| 层级 | 覆盖 | 数量 |
|------|------|------|
| 单元测试（unit/） | 独立函数和类 | 6 文件 |
| 集成测试（integration/） | Mock 完整链路 | 1 文件 |
| Golden Cases | 端到端场景 | 10 条 YAML |

## 四、166 测试覆盖

| 测试文件 | 内容 |
|---------|------|
| test_intent.py | IntentSpec + FilterSpec + 跨字段规则 |
| test_llm.py | Mock LLM + Fixture + 注册表 + DeepSeek 安全 |
| test_memory.py | 状态 + 版本 + 幂等 + 准入 + Mock 空间 + Correction |
| test_agent_framework.py | AgentRuntime + PydanticAI Smoke |
| test_powerbi.py | Mock Adapter 全部场景 |
| test_harness.py | ToolGateway + ContextBuilder + TurnController + Trace + Validation |
| test_memory_repository.py | InMemoryMemoryRepository 全功能 |
| test_mock_pipeline.py | 问答/报表/多轮/冲突/幂等集成 |

---

*最后更新：2026-07-31 | M0.3 数据接入与验证闭环*
