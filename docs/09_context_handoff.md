# 09 — 跨对话上下文交接

> **当前状态交接入口；Claude / Codex / 其他代码 Agent 必须先从仓库根目录 `AGENTS.md` 进入。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-14 | M2.6.3 Deterministic Execution & Verified Facts 开发分支验收候选**

---

## 当前项目目标

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言查询 Power BI 语义模型数据，以固定模板生成静态 HTML 报表。前端为 GPT 式极简对话网页（M5 React 开发）。

## 当前阶段

**M2.6.3 Deterministic Execution & Verified Facts** — ✅ 已完成开发分支候选，待远程审计。

> ADR-008/009 已固化 `Natural Language → Canonical QueryPlan → Deterministic DAX → Independent Layer 3 → QueryResult → VerifiedFactSet → fact-bounded Answer/Report`。Glossary 绑定 runtime schema fingerprint；PendingClarificationContext 与 committed Memory 分离；Real DAX LLM authority 为 0。正式 clarification contract 为 6 Conversation / 16 Turn，conversation_e 需 e1/e2/e3 三轮补齐，禁止默认 Product。Remote 生产化继续 Deferred。

Fresh Real Gate：Semantic Matrix 34/34、专项 `a1 → a2 → a3` 5/5；production E2E exact Known-answer 8/8、holdout 2/2、6/6 Conversation、16/16 Turn、成功 Real query 51、failure-recovery 1/1、`a1 → a2 → a3` 10/10，fallback=0、pollution=0，两类已知 DAX blocker 均为 0。

## 上一轮

**M2.6** — 数据问答正确性契约与架构治理加固（Commit `91829c845ca710e913b29babd593648b58a81257`，CI Run #31559389973 success）。

## 固定封板 Tag

`m1.7.2-m0-m1正式封板` — 已真实存在，指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`。

## 下一动作

下一动作是远程审计已 push 的 M2.6.3 开发分支；本轮不 merge main、不 push main、不 Tag。远程审计通过后再决定 fast-forward main。M2.6.4 只做 final hardened acceptance、docs consolidation 与 M0—M2 seal；不得提前实施 M3 Renderer。

以后 Claude / Codex / 其他代码 Agent 均以根目录 `AGENTS.md` 为仓库级入口。

## 当前真实能力

- **LLM:** DeepSeek（真实 API）+ Mock（确定性测试）
- **Power BI:** Mock 完整可用；Local MCP + Power BI Desktop 的 Schema、DAX、QueryResult 与 DeepSeek Chat 已真实接入；Remote MCP 未实现并因管理员条件 Deferred
- **管线:** 确定性 TurnPipeline（ADR-005），Mock/DeepSeek 共享执行骨架
- **能力:** 真实 Schema Grounding → Canonical QueryPlan → Deterministic DAX → Independent Layer 3 → VerifiedFactSet → fact-bounded Answer/ReportSpec；幂等重放与请求指纹冲突检测
- **API:** Health 200/503、Chat 可用/不可用，Mock/DeepSeek 模式切换
- **源模式:** Local QueryResult、Turn、Answer/Report、Snapshot、Replay 均传播 `source_mode=real`
- **M2.6 正确性:** Real Filter 仅 `eq=SUPPORTED`；其余 Operator 均 `NOT_VERIFIED` 并受控拒绝。TopN selection 与 presentation ordering 分离验证；ties 可超过 N 行
- **M2.6.1/3 验收基线:** 独立 Oracle 支持 scalar/grouped/ordered；8 个 Case（2 holdout）与正式更正后的 6 Conversation/16 Turn；Conversation 严格要求 all-turn PASS
- **M2.6.2 业务语义:** Business Catalog、Object/Member/Time Grounding、semantic slot 状态契约、deterministic StateTransition 与 Canonical QueryPlan authority 已实现；member lookup 只经 ToolGateway → PowerBIAdapter
- **M2.6.3 确定性执行:** Real path 不调用 LLM 生成 DAX；受限 grammar 与 Independent Layer 3 覆盖 Measure/Dimension/EQ/Time/Sort/TopN
- **M2.6.3 事实边界:** VerifiedFactSet 是数字、排名、极值、筛选、时间和 provenance 的唯一结构化 authority；Answer/Report 不得扩写未验证事实
- **Clarification:** Pending context 非 executable/COMMITTED state，partial slots 完整后才执行并在全链成功后提交正式 Memory
- **Health:** `ready` 兼容 `configuration_ready`；Health 不做实时探针，`powerbi_live_connected=false`

## 当前技术边界

- ADR-005 负责 TurnPipeline 总体架构；ADR-006 负责 Remote 生产化；ADR-007 负责当前 Local Demo；ADR-008 负责 Business Semantic authority；ADR-009 负责 Deterministic Execution / Verified Fact authority，均 accepted
- Adapter 内部使用 `connection_operations`、五类 Schema 工具的 `List` / `Get` 与 `dax_query_operations Execute`；业务层只暴露 Schema、bounded members 与 DAX Execute 抽象能力
- 任何 Local / Remote MCP SDK 只能位于 PowerBIAdapter 边界之后；Service/API/LLM 不得直接调用 MCP；Real 失败不得回退 Mock
- M2.1—M2.5 只沿现有 Adapter/控制面完成 Local Demo 验证；会话持久化属 M4，报表正式渲染属 M3，React 属 M5
- `local_mcp.py` 职责冻结为 Provider / protocol Adapter；M3/M4/M5 默认不得修改，Renderer/Memory/UI 逻辑不得进入

## 运行命令

```
# 全量测试（Mock 模式，无网络）
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q

# Golden Cases
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# M2.6.1 Known-answer / Multi-turn Fake/Mock 离线验收
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode offline

# M2.1 Local MCP 人工连接 Smoke（先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_connection_smoke.py

# M2.2 Local MCP 人工 Schema Smoke（先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_schema_smoke.py

# M2.3 Local MCP 人工 DAX Smoke（先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_dax_smoke.py

# M2.4 DeepSeek + Local Power BI Chat Smoke（先打开测试 PBIX，需本地 DeepSeek 配置）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_local_powerbi_chat_smoke.py

# M2.5 Business Golden Smoke（7 个真实 Case；先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_business_golden_smoke.py

# M2.6.2 Real Semantic Gate（先打开测试 PBIX，需本地 DeepSeek 配置）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_semantic_grounding_smoke.py --historical-repeats 5

# M2.6.3 production E2E（exact known answers + 6/16 + a1-a2-a3 x10）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode real --historical-repeats 10

# 人工验收 Smoke（需 .env 中 DEEPSEEK_API_KEY）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_chat_smoke.py

# 安全扫描
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py

# CI（本地模拟）
LLM_MODE=mock POWERBI_MODE=mock D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
```

## 未完成事项

- M2.6.4: final hardened acceptance、docs consolidation、M0—M2 final seal
- M3: 报表正式渲染管线、报表资源 ID
- M4: 会话持久化、搜索、最近对话
- M5: React 前端
- Remote 生产化：公司 Tenant setting、Entra App、委托权限与目标模型权限（Deferred，等待管理员条件和用户批准）

## 重要 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m1.7.2-m0-m1正式封板` | `23d8ddb` | M0—M1 正式封板基线 |
| `m2-local-powerbi-demo-release` | `c9af48a` | M2.5 Local Demo 正式封板基线；保持不变 |
| `m1-deepseek-pipeline-release` | `a926b5e` | M1 DeepSeek 全链路封板 |
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## 近期变更摘要

- M2.5: 7 个真实 Business Golden、3 个未点名对象/组合、20 类 Bad Case、`gc_012` 人工真实基线与 full regression 完成；未新增业务词典、完整 Parser 或主架构
- M2.6: eq Filter field/operator/value、TopN/Sort 语义、Architecture ownership 与 Health 真实性加固；未实现数值 Oracle 或 Real Multi-turn
- M2.6.1: Harness/Test 层独立 scalar/grouped/ordered Oracle、8 个 Known-answer Case（2 holdout）与 local-only real baseline 契约完成；M2.6.3 将欠指定 clarification contract 正式更正为 6 Conversation/16 Turn
- M2.6.2: ADR-008、model-scoped glossary、Object/Member/Time Grounding、semantic slot 状态契约与 deterministic StateTransition 完成；Real Semantic Matrix 与 fresh `a1 → a2 → a3` 5/5 通过，fallback=0、pollution=0
- M2.6.3: ADR-009、schema fingerprint、PendingClarificationContext、Deterministic DAX、Independent Layer 3、VerifiedFactSet 与 factual Answer/Report boundary 完成；Real LLM DAX authority=0
- M2.4: Local Provider 注入现有 DeepSeekTurnService / TurnPipeline；Layer 2/3、Answer provenance、real Snapshot/Replay 与三个真实自然语言 Case 完成候选
- M2.3: 通过 ToolGateway → LocalMCPPowerBIAdapter 真实执行固定 DAX 并获取 row data；QueryResult、错误与截断边界已标准化，当前实机未复现 Issue #124
- M2.2: 通过 ToolGateway → LocalMCPPowerBIAdapter 单次只读会话真实读取并标准化 Schema；Measure 与基础模型关系已可用于 Semantic Grounding
- M2.1: Demo 路径调整为 Local MCP + Power BI Desktop；新增 ADR-007、Local Adapter / stdio Client 与只读安全边界；Remote ADR-006 完整保留
- M2.0: 官方证据复核、ADR-005 文件化、ADR-006 与原始 M2.1—M2.5 路线固化；生产业务实现为 0
- M1.8: Codex 接管准备与仓库上下文固化
- M1.7.2: M0—M1 正式封板（`23d8ddb`，Tag `m1.7.2-m0-m1正式封板`）
- M1.7.1: 最终状态收口与封板候选修复（`1dd20de`，CI Run #30991136311 success）
- M1.7: MVP轻量化与通用CI固化（`e5d1740`）
- M1.6.6: CI建立、最终架构审计、文档收尾（`084aa76`）
- M1.6.5: 真实测试、机器错题本、架构防偏移治理（`e850f14`）
- M1.6.4: AI真实性门禁、异常处理与对抗测试加固（`4217b66`）
- M1.6.3: 统一TurnPipeline与旧Agent抽象清理（`d6665bd`→`d99d243`→`d57e38c`）
- M1.6.1-2: 架构定案、Harness与配置收口

---

*最后更新：2026-08-14 | M2.6.3 Deterministic Execution & Verified Facts 开发分支验收候选*
