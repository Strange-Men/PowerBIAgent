# AGENTS.md — PowerBIAgent 仓库入口

> Claude、Codex 与其他代码 Agent 修改文件前必须先读本文件。当前状态见
> `docs/09_context_handoff.md`，路线见 `docs/08_development_roadmap.md`。

## 当前开发入口

- 当前版本：**M5.10.9**（Documentation Governance & M5 Final Seal）。
- M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY；M5.10.8 与 FIX COMPLETE。当前只做治理、version 与 12px CSS polish，不做 M6 implementation。
- 07 是当前状态，08 是当前/未来路线，09 是唯一开发交接；根入口不重复保存浮动 SHA/CI。
- 前置绿色基线 main@409fd521 / CI 36665958820；本阶段 final baseline 必须按当前 checkout exact-SHA CI 和 remote audit 解析。

## Authority boundary

1. `TurnPipeline` 是唯一确定性控制面；Mock 与 Real 共用执行骨架。
2. Power BI 只能经 `ToolGateway → PowerBIAdapter`；Local/Remote 只替换 Adapter 后的
   Provider。Real 失败不得静默回退 Mock。
3. M5.10.6+ 的原则是 **LLM understands. Runtime proves.** LLM 可解释开放语言并输出
   bounded candidate/draft，但不拥有 canonical object/member/date、DAX、QueryResult、
   coverage、available horizon、numeric fact、business Memory 或 report fact authority。
4. Runtime `SemanticCatalog` 与 `Grounding` 证明业务对象、成员和 canonical identity；
   `StateTransition` 与 `Completeness` 证明可执行 canonical state。歧义/未知/残缺必须在
   DAX 前 clarification/no-match，且 ZERO factual Memory commit。
5. QueryShape 固定为八种：`SCALAR`、`ENTITY_LIST`、`GROUPED`、`RANKING`、
   `MEMBER_SET`、`FILTERED_AGGREGATION`、`TREND`、`BOUNDED_TREND`。
6. Real 只执行受限 Deterministic DAX；Independent Layer 3、Result Inspection 与
   `VerifiedFactSet` 分别保留执行/结果/外部事实 authority。业务数学不得由 LLM 计算。
7. General conversation 默认开放，但必须 current-message-only、no-tool、ZERO schema/
   member/DAX/report/business Memory/pending mutation；若需要组织业务事实必须升级到正式链。
8. Natural presentation 可由 LLM 组织措辞，但只能消费 Verified Facts、verified user-facing
   scope 与真实 data availability context，且必须经过 `FactOutputValidator`；失败只能 repair
   或 deterministic safe fallback。
9. `requested_query_scope`、`observed_data_coverage`、`available_data_horizon` 三者独立。
   horizon 必须 measure/fact-family + temporal-dimension aware，来自真实数据；不得用 Date 表
   最大值、当前日期、requested end、provenance 时间或 LLM 猜测，也不得冒充 refresh time。
10. Report 复用同一 Verified Facts 与 availability context，不得新增 parser、planner、
    availability 逻辑或事实解释。固定模板与 Renderer authority 保持不变。
11. PendingClarification 与 committed Memory 分离；general turn 不消费、不改写业务 pending 或
    Memory。模型切换不得继承旧模型业务上下文。
12. 禁止第二 Planner/Grounding/Memory、Agent、LangGraph、RAG/vector DB、ontology server、
    migration、MCP runtime/Provider rewrite、LLM DAX、任意代码、写/删/更新、Forecast/Target/
    Budget、新 YoY/MoM capability、报表视觉重构；本轮不进入 M6 implementation。

## 固定 Cold Start

按顺序读取：

1. `AGENTS.md`
2. `PROJECT_CHARTER.md`
3. `CLAUDE.md`
4. `docs/07_milestones_status_and_open_questions.md` → `docs/08_development_roadmap.md` → `docs/09_context_handoff.md`
5. `README.md`、`CHANGELOG.md`（导航与历史摘要）
6. `docs/ai_development_error_ledger.yaml` 的结构、有效规则与当前相关项
7. `docs/adr/README.md` 与当前相关 accepted ADR
8. 当前 Prompt 指定文档、涉及的 production code 与邻近 tests

不得用聊天记忆或历史 PASS 数字代替 fresh 仓库证据。文档冲突顺序：用户当前明确要求
→ `PROJECT_CHARTER.md` → 正式 PRD → accepted ADR → 当前专项设计 → 08 → 09 →
`CLAUDE.md` → 代码与 fresh 测试 → Archive。

## Git contract

- `main` 是唯一活动开发线；流程固定为 failure-first → minimal implementation → fresh gates
  → Real → 白名单 staging → commit → push main → exact-SHA CI → remote audit。
- 本轮两阶段：`M5.10.9_文档治理与最终封板候选` → exact-SHA CI success → `M5.10.9_M5最终封板` → 最终 exact-SHA CI / remote audit；不打 Tag。
- 禁止 `git add .`、`git add -A`、force push、rebase、history rewrite、`reset --hard`、
  `clean`、branch deletion。remote main 已前进则停止。
- CI 失败只允许 forward-fix；同一 root cause 最多两轮，P1 不因每次失败都停止；上限仍失败、新根因、边界扩大或 architecture risk 才停止重新评估。禁止降低 validator、删除 negative
  tests、修改 expected 迎合错误、Mock Real 或隐藏 warning/error。
- 不读取、输出或提交 `.env`/Secret、真实业务数据、PBIX、DB、真实 prompt/response dump。
- Local automated、Local Real DeepSeek + MCP、Remote exact-SHA CI 必须分层记录。

---


## Frozen Core / M6 扩展纪律

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

生产级后端风险优先于功能数量；M6 开始前按 09 重新验证 Microsoft 官方能力，ADR-006 已 SUPERSEDED。Token 只允许 Auth / Transport boundary；tenant/principal/ownership 与 RLS/OLS 必须先证明。

*最后更新：2026-09-30 | M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY；当前状态以 07/08/09 为准*
