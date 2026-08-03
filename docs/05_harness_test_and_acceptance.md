# 05 — Harness、测试与验收

> **状态：** M1.3.2 同步更新
> **关联 ADR：** ADR-004
> **当前基线：** pytest 706 passed、Golden Cases 11 passed / 1 skipped、安全扫描 PASS

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

### M0.3.1 12 条

| ID | 类别 | 状态 |
|----|------|------|
| gc_001 | 普通数据问答成功 | mock_ready |
| gc_002 | 多轮筛选继承（setup_turns） | mock_ready |
| gc_003 | 报表生成成功（含 render_report） | mock_ready |
| gc_004 | clarification 不创建 pending | mock_ready |
| gc_005 | unsupported 不创建 pending | mock_ready |
| gc_006 | 工具超时不提交 Memory | mock_ready |
| gc_007 | 虚假字段回应 response_failed | mock_ready |
| gc_008 | 权限拒绝被 Gateway 拒绝 | mock_ready |
| gc_009 | 超大结果被截断 | mock_ready |
| gc_010 | DAX 错误 | mock_ready |
| gc_011 | request_id 幂等 | mock_ready |
| gc_012 | 真实 Power BI 基线 | pending_real_baseline |

### 运行命令

```powershell
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
```

### GoldenCaseRunner（`backend/app/harness/cases/case_runner.py`）

- Async-first：`run_one_async()` / `run_all_async()`
- 传入全部五类 Scenario Key
- Pydantic 强校验 Case 结构
- Runtime 配置真实生效
- 读取 Repository 验证 Memory
- pending_real_baseline 计为 skipped
- actual=None 时不假通过
- 不逐字比较自然语言答案

## 三、测试策略

| 层级 | 覆盖 | 数量 |
|------|------|------|
| 单元测试（unit/） | 独立函数和类 | 6 文件 |
| 集成测试（integration/） | Mock 完整链路 | 1 文件 |
| Golden Cases | 端到端场景 | 10 条 YAML |

## 四、706 测试覆盖（M1.3.1 基线，本轮无变化）

| 测试文件 | 内容 |
|---------|------|
| test_intent.py | IntentSpec + FilterSpec + 跨字段规则 + 真实 Intent |
| test_llm.py | Mock LLM + Fixture + Registry + DeepSeek Provider |
| test_memory.py | 状态 + 版本语义 + 幂等 + 准入 + Mock 空间 + Correction |
| test_agent_framework.py | AgentRuntime + PydanticAI Smoke |
| test_powerbi.py | Mock Adapter 全部场景 |
| test_harness.py | ToolGateway + ContextBuilder + TurnController + Trace + Validation |
| test_memory_repository.py | 版本 + 证据验证 + 隔离 + 原子性 + 失败审计 |
| test_mock_pipeline.py | 问答/报表/多轮/Gateway链路/冲突/幂等/失败清理/并发 |
| test_settings.py | Settings 默认/覆盖/校验/Secret/隔离 |
| test_health.py | Health 200/模式/敏感字段/不调用LLM |
| test_chat.py | Chat 问答/报表/边界/并发/Real拒绝 |
| test_query_plan.py | QueryPlan 真实验证集成测试 |
| test_dax.py | DAX 表—归属验证测试 |
| test_repository_safety.py | 仓库安全（26 测试） |

---

## 五、未来验收项（M1.4—M5）

### M1.4 验收

- Answer 数据真实性：AnswerSpec.answer 内容与 QueryResult 数据一致
- 表格字段与 QueryResult.columns 一致
- 图表字段与 QueryResult.columns 一致
- ReportSpec 字段真实性
- source_mode 真实性：Mock QueryResult 不得标为 real

### M5 前端验收

- 前端不得把 Mock 数据描述为真实 Power BI 数据
- 不得把未接入模型（GPT-5.6 等）展示为可用
- 不得把 Mock 展示为用户正式模型
- 表格数据必须来自 API 返回的 QueryResult
- 图表数据必须来自 API 返回的 QueryResult
- 未实现功能（查看报表、下载 HTML 等）必须明确禁用

---

*最后更新：2026-08-03 | M1.3.2 前端视觉与结构化回答契约固化*
