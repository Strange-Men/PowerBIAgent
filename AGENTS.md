# AGENTS.md — PowerBIAgent 仓库入口

> Claude、Codex 与其他代码 Agent 修改文件前必须先读本文件。
> 当前状态见 `docs/07_milestones_status_and_open_questions.md`；路线见
> `docs/08_development_roadmap.md`；下一开发者交接见 `docs/09_context_handoff.md`。

## 当前开发入口

- 当前版本：**M6.3**（多用户归属与权限隔离）。
- M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY；M5.10.8 与 FIX COMPLETE。
- M6.1 COMPLETE（以自身exact-SHA CI与remote audit生效）；ADR-020 ACCEPTED；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ数值兼容P1 BLOCKED；M6.4 NOT READY。
- M6.3安全封板按自身exact-SHA CI与remote audit生效；Settings.version=M6.3。数值P1及下一阶段交接见07/08/09；不得自动开始M6.4或开放ENTRA产品API。
  每个 implementation patch 必须有用户明确批准的具体 scope、fresh Cold Start、Microsoft 官方
  能力重新验证与先完成的 P0 security boundary 设计/验证；未满足前不得直接写 M6 Cloud code。
- 07 是当前状态，08 是当前/未来路线，09 是唯一开发交接；根入口不重复保存浮动 SHA/CI。
- 发布基线按 09 的当前 checkout exact-SHA CI 和 remote audit 解析，不继承旧阶段 CI。

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
    LLM DAX、LLM 任意代码、未经审批的生产写/删/更新。migration、MCP runtime/Provider 扩展、
    Forecast/Target/Budget、新 YoY/MoM capability 与报表视觉变更只能按独立获批 scope 和正式合同实施，
    不得由 M6 READY 自动授权或绕过 Frozen Core。

## 固定 Cold Start

初始审计先 `git fetch`，核对 main、clean worktree、HEAD==origin/main 与获批 baseline。
交付阶段允许本轮临时分支和白名单改动，须核对分支归属、diff 与 origin/main 仍等于 Cold Start SHA；
不得把初始 main/clean 要求用于拒绝本轮已授权交付。未知用户修改或非预期 remote main 前进立即停止。
受保护 PR 合入后回到 main，以 `git pull --ff-only` 同步，再审计 HEAD==origin/main、worktree clean。

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

- main 是唯一活动开发线与正式发布基线。流程固定为：
  Cold Start → Failure-first → Minimal Patch → Local Gates → 必要 Real 验收 → 白名单 Staging → 中文 Commit → 临时交付分支 → PR Required CI → 受保护合入 main → Main Exact-SHA CI → Remote Audit。
  临时交付分支仅用于本轮 PR，不作为长期并行开发线；本地可先从已核验 main 创建分支再提交，禁止直接 push main。
  管理员同样必须通过 required checks，禁止绕过 branch protection；PR required CI 不替代最终 main exact-SHA CI。
- 禁止 `git add .`、`git add -A`、force push、rebase、history rewrite、`reset --hard`、`clean`、未经授权删除分支。
  push/merge 前 fetch；除本轮受保护 PR 合入外，remote main 相对 Cold Start SHA 前进即停止。不覆盖用户修改，不自动打 Tag。
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

生产级后端风险优先于功能数量；每个M6 implementation按09重新验证Microsoft官方能力与适用P0边界。ADR-020接受Cloud消费/目录设计，ADR-006已SUPERSEDED。Token只允许Auth/Transport；tenant/principal/ownership与RLS/OLS必须先证明。

*最后更新：2026-10-10 | M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ数值兼容P1 BLOCKED；M6.4 NOT READY；M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY；当前状态以07/08/09及自身exact-SHA CI为准*
