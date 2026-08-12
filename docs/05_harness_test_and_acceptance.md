# 05 — Harness、测试与验收

> **状态：** M2.6.1 Known-answer Oracle 与 Multi-turn Harness/Test Set 离线固化完成
> **关联 ADR：** ADR-004
> **当前基线：** pytest 1272 passed、Golden Cases 11 passed / 1 manual-real skipped、安全扫描 PASS
> **真实 Business Golden：** 7/7 passed；最终完整 Smoke 28 次 LLM 调用、0 repair
> **真实 Chat Smoke：** overall_success=true, 6/6 cases passed (data_question, report_generation, clarification, unsupported, idempotent_replay, request_id_conflict)
> **Token 统计：** call_count/repair_count 按 task 独立统计，LLMValidationError 携带 usage
> **模式切换：** Mock+Mock 200 / DeepSeek+Mock 200 / DeepSeek+Local MCP 200 / Remote MCP 503

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

### 12 条定义案例（M0.3.1 制定，11 passed / 1 skipped）

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
| gc_012 | 真实 Power BI 基线 | manual_real_baseline（人工 Smoke 已通过；CI 安全跳过） |

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
- manual_real_baseline 由 `m2_business_golden_smoke.py` 验证，通用 CI Runner 计为 skipped
- actual=None 时不假通过
- 不逐字比较自然语言答案

## 三、测试策略

| 层级 | 覆盖范围 |
|------|---------|
| 单元测试（unit/） | 独立函数和类：Provider、Service、验证器、Model 校验、Prompt 规则、安全扫描 |
| 集成测试（integration/） | Mock 完整链路：问答、报表、多轮、并发、幂等、失败清理 |
| Golden Cases | 端到端场景：12 个定义案例，11 passed / 1 skipped（M1.4.1 基线） |

> 测试数量为事实记录，不作为验收目标。

## 四、M2 DAX 业务语义正确性验收

### Layer 1 — Schema Grounding（M2.2）

**✅ M2.2 已完成候选。** 当前 Local Provider 已通过 ToolGateway → PowerBIAdapter 边界真实读取 `tables`、`columns`、`measures`、`relationships` 与 `hierarchies`。Measure expression、data type、表归属以及关系 active/cardinality 已保留；Table/Column/Measure 的 description 以可选字段兼容真实响应。当前测试模型的 description 均为空，Local 未返回 Prep for AI 专用 metadata，因此不虚构此类语义。Fake MCP 响应用于离线 CI，真实 Schema 只由人工 Smoke 验证。

M2.2 实机验收为 3 tables、19 columns、2 measures、1 relationship、2 hierarchies；`Total Sales` 与 `Total Quantity` 均准确识别为 Measure 且 expression 非空，`Quantity` 与 `UnitPrice` 保持 Column 身份。DAX 执行和 DeepSeek 调用均为 0。

### DAX Execution / QueryResult Boundary（M2.3）

**✅ M2.3 已完成候选。** 当前 Local Provider 已通过 ToolGateway → PowerBIAdapter → Local MCP → Power BI Desktop 真实执行 `dax_query_operations Execute`。固定 ROW 返回 1 row / 1 column 且值为 1；`Total Sales` 与 `Total Quantity` 返回 1 row / 2 columns 的实际数值。结果按真实列顺序映射为二维 rows，`row_count=len(rows)`，并保留 execution time、request_id、`source_mode=real` 与 truncated。

Fake MCP 离线覆盖正常/空/截断、DAX/timeout/permission/connection/MCP protocol 错误、malformed payload 与 Preview missing rows；真实 MCP 只由人工 Smoke 执行。Issue #124 仍为 Open，但当前 beta.12 + mcp 2.0.0 + Desktop 组合未复现，不能写成官方已修复。M2.4 已将 DeepSeek + Local Chat 与 Answer / Snapshot / Replay 的 real source_mode 传播接入同一 TurnPipeline。

### Layer 2 — QueryPlan Semantic Validation（M2.4）

**✅ M2.4 已实现。** QueryPlan 不仅验证字段存在，还确定 Measure/Column 身份、隐藏对象、字段归属和关系可达性。关键指标已有明确 Measure 时不得以裸数值列重新构造口径；Measure、Dimension 与 Filter 必须来自真实 Schema，无法唯一消歧时进入 clarification。

### Layer 3 — DAX Structural / Semantic Consistency（M2.4）

**✅ M2.4 已实现。** 在 `DAXSafetyValidator` 之上确定性检查模型 key、Measure/Dimension/Filter 引用；只有 QueryPlan.dimensions 可成为 group-by，Filter 字段不会自动成为维度；`SUMMARIZECOLUMNS` 强制 group-by → filter table → name/expression 对的顺序并拒绝不成对参数。未增加第二个 LLM Judge 或完整 DAX AST Parser。

### M2.6 Filter / TopN / Sort Correctness Contract

Filter Capability Matrix 只使用 `SUPPORTED` / `NOT_VERIFIED`：

| Operator | QueryPlan 契约 | Prompt | Layer 3 | Fake/Mock | Real 证据 | 状态 |
|---|---|---|---|---|---|---|
| `eq` | 有 | 明确 | field/operator/value 与 extra filter 可验证 | 有 | M2.4/2.5 eq Case | `SUPPORTED` |
| `ne` / `gt` / `gte` / `lt` / `lte` | Enum 有 | Real 不输出 | 未形成已验收可靠链 | 兼容 | 无 | `NOT_VERIFIED` |
| `in` / `not_in` / `contains` | Enum 有 | Real 不输出 | 未形成已验收可靠链 | 兼容 | 无 | `NOT_VERIFIED` |

Real semantic validation 仅放行 `eq`；其余 Operator 在进入 Power BI 前以 `filter_operator_not_verified` 受控失败。Layer 3 只识别直接字面量相等谓词与单值 `TREATAS`，不对无法可靠解释的 DAX 猜测。Mock 旧路径不启用该 Real capability gate。

TopN selection 与 presentation ordering 是两个契约：TOPN 必须匹配 QueryPlan 的 N、单一 Measure 与方向；显式 sort 另要求查询末尾 `ORDER BY [Measure] ASC|DESC`。第 N 名 ties 允许结果超过 N 行，因此 Golden 不再以 `row_count <= top_n` 为正确性标准。

### Known-answer 独立数值 Oracle（M2.6.1）

**✅ 已完成离线固化。** `backend/app/harness/oracles/known_answer.py` 只属于 Harness/Test infrastructure。Expected 只从显式 baseline 文件加载，禁止由 LLM、当前 DAX、Answer 或 Actual QueryResult 反向生成。Oracle 支持：

- scalar：精确列/单行指标值比较；
- grouped：按明确业务 Key canonicalize 后比较，不依赖 raw row 顺序；
- ordered/TopN：比较成员和值并独立验证排序方向；同一指标值的 ties 可交换顺序，第 N 名并列可使行数超过 N。

数值默认 `abs_tolerance=1e-9`、`rel_tolerance=1e-9`；绝对/相对容差配置上限分别为 `0.01` 与 `1e-6`。分类维度 exact match，`None` 显式比较。committed `harness/baselines/example_known_answers.yaml` 仅含虚构测试值；M2.6.2 真实 baseline 固定为 Git 忽略的 `local_state/m2_known_answers.yaml`，缺失时返回 `real_baseline_not_configured`，覆盖不完整时返回 `real_baseline_incomplete`，均禁止回退 example baseline。

`harness/cases/known_answer_cases.yaml` 固化 8 个语义 Case，其中 2 个 holdout 不进入 QueryPlan Prompt 示例，也未引入业务词典或 Prompt 特化。

### Real Multi-turn Harness/Test Set（M2.6.1）

**✅ 已完成 Fake/Mock 离线固化；真实执行未开始。** `harness/cases/multi_turn_conversations.yaml` 定义 6 个 Conversation、15 个 Turn，覆盖 Filter refinement、Dimension switch + TopN、Filter replacement、Metric switch、Clarification 及失败 Turn Memory 完整性。Runner 复用正式 `create_app → /api/v1/chat`，同一 Conversation 使用同一 `conversation_id`、不同 `request_id`，上下文只由上一成功 Turn 正常 commit 形成，不直接写 Memory Repository。

数据 Turn 的正式 M2.6.2 成功契约同时要求 semantic expectation、Layer 2、Layer 3、Oracle、Answer provenance、Memory、`source_mode=real` 与 Real→Mock=0；Clarification 不执行 Power BI 且不 commit；失败 Turn 必须停在预期阶段、不 commit、不污染上一成功状态。Conversation 使用严格 `all(turn.passed)`，任一 Turn 或 Oracle 失败都会使整组失败，最终真实封板要求 6/6。

本轮唯一入口：

```powershell
# Fake/Mock 离线执行
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode offline

# M2.6.1 仅校验 local-only baseline 配置，不执行真实调用
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode real
```

### Layer 4 — Business Golden Verification（M2.5）

**✅ M2.5 已完成。** 通过正式 `create_app → /api/v1/chat → DeepSeekTurnService → TurnPipeline → ToolGateway → LocalMCPPowerBIAdapter` 运行 7 个真实 Business Golden：总销售额、总数量、Category Filter、按 Category 看销售额、Top 3 Product 销售额、按 Product 看总数量、Top 3 Category 总数量。逐 Case 与最终完整 Smoke 均 7/7 通过；每个 Case 同时核对 Intent、model key、Measure、Dimension、Filter、sort/top_n、Layer 2、Layer 3、真实 QueryResult、Answer provenance 与 Memory commit。

其中 Product、Product × Total Quantity、Category × Total Quantity × Top 3/desc 三个对象/组合未在 QueryPlan Prompt 中显式点名，全部首次成功且 0 repair。结论是当前 Prompt 示例未阻碍 Schema 驱动泛化；本轮保留示例但未增加任何“业务词 → 固定 Measure”词典。多轮真实 Case 未执行，因为现有 Mock Golden 已覆盖上下文继承，而 M2.5 无需为可选 Case 增加架构或真实调用成本。

### M2.5 Bad Case Verification

20 类关键 Bad Case 均由现有 Fake/Mock 定向回归覆盖并受控失败：不存在 Measure、Column/Measure 身份混淆、隐藏对象、非法 Filter、无关跨表、model key 不一致、额外 group-by、非法 `SUMMARIZECOLUMNS` 顺序、未知 DAX 对象、写操作、Local 连接失败、DAX execution error、Issue #124 missing rows、malformed QueryResult、Answer source_field/数值不可证明、Real 不回退 Mock、Replay 不重执行以及 request_id 指纹冲突。失败路径保持错误分类明确、Memory 不错误提交。

## 五、自动化测试覆盖

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
| test_known_answer_oracle.py | scalar/grouped/ordered、容差、TopN ties、local-only baseline 与独立 Expected 边界 |
| test_multi_turn_benchmark.py | 6 Conversation / 15 Turn、Memory 完整性、Oracle 与严格全 Turn 评分 |

---

## 六、未来验收项（M1.4—M5）

### M2.6.2 Known-answer / Real Multi-turn 最终验收（未执行）

- 使用 local-only 真实 PBIX baseline，通过 DeepSeek + Local MCP + Desktop 运行同一套 8 Case / 6 Conversation 契约。
- 单 Turn：Intent、QueryPlan、Filter/operator/value、Layer 2、Layer 3、QueryResult Oracle、Answer provenance、Memory、`source_mode=real` 与 Real→Mock=0 必须全部 PASS。
- Conversation：所有 Turn 全部成功才 PASS；只有 6/6 才允许 M0—M2 hardened 最终封板。
- M2.6.1 的 Fake/Mock 通过不等同于真实数值、多轮或 Desktop 验收通过。

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

*最后更新：2026-08-12 | M2.6.1 Oracle 与多轮 Harness 离线固化完成*
