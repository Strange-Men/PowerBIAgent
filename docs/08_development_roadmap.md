# 08 — 当前及未来开发路线

> **状态：** Settings.version=M5.10.9；M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一路线 authority；状态见 [07](07_milestones_status_and_open_questions.md)，实施入口见 [09](09_context_handoff.md)。

## 路线总览

| Milestone | 定位 | 当前路线 |
|---|---|---|
| M5 | Core Analysis Kernel | FROZEN；保留 failure-first correctness forward-fix |
| M6 | Cloud Consumption & Enterprise Identity | 下一阶段；只规划，未实现 |
| M7 | Freshness & Report Lifecycle | 后续规划 |
| M8 | Enterprise Pilot Platform | 后续规划 |
| M9 | Advanced Analytics & Controlled Authoring | 后续规划 |

M0—M4 已封板；M5.10.8 与 FIX COMPLETE。M5 小阶段历史移交 CHANGELOG / milestone docs / Git，
旧路线原文见 [Historical snapshot](archive/m5_pre_final_08_development_roadmap.md)。本轮不进入 M6。

## M5 — Core Analysis Kernel

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

## M6 — Cloud Consumption & Enterprise Identity

目标：Local Desktop MVP → Enterprise Power BI / Fabric consumption system。
第一阶段先做官方能力验证与 identity/auth/tenant/principal/ownership 设计，取得 accepted contract，
再通过既有 Adapter / Repository / Service 小步扩展；生产级后端风险优先于功能数量。

M5 Local MCP = Developer / Desktop Provider；M6 Cloud Provider = Production Cloud Consumption Provider。
当前实现为 MockPowerBIAdapter、LocalMCPPowerBIAdapter 与未完成的 RemoteMCP skeleton，Real 失败
不得回退 Mock。未来 Cloud PowerBI Adapter 继续服从 PowerBIAdapter 与 ToolGateway，不能复制管线。

```
SemanticFrame → Grounding → CanonicalQueryPlan → Deterministic DAX
→ Power BI data plane → QueryResult → ResultInspection → VerifiedFactSet → Answer / Report
```

任何 M6 implementation 前必须重新验证 Microsoft 官方 API / MCP / Fabric 文档，保存日期、
官方来源、endpoint、auth、tenant/identity、capability/tool schema、RLS/OLS 与 fail-closed probe
证据。Fabric IQ MCP 是需要评估的默认方向之一，尚未确认其适用性或 production contract。
ADR-006 已 SUPERSEDED；历史 Power BI Consumption MCP endpoint、SDK 版本、认证假设不得直接
当成当前稳定合同。本轮没有验证或实现 Cloud MCP / Entra。

| 未来职责 | 范围 |
|---|---|
| PowerBIDataPlane | discover、schema、member/value search、query、execute deterministic DAX |
| PowerBIControlPlane | refresh、refresh history、workspace metadata、report resource metadata、embed metadata、lifecycle |

refresh API 不得塞入 execute_dax adapter。以上为 M6 架构方向，尚无本轮代码实现。

### Production risk baseline

Authentication / Entra identity、tenant namespace、principal namespace、Authorization、Ownership、
IDOR、OAuth token lifecycle、Secret leakage、cross-user cache isolation、RLS / OLS identity propagation、
fail-closed external authority handling 均为 P0。当前 M5 的本地 `test_user` 与 Mock/Real namespace
不是 enterprise identity 或 authorization；不得部署后仅替换显示用户名。

Token 只能存在 Auth / Transport boundary，不得进入 UserContext、Memory、Trace、Conversation
persistence。后续 persistence resource identity 必须包含 `tenant_id`、`principal_id`、
`conversation_id`。Report / Snapshot / Conversation / Memory 均需 server-side ownership validation；
客户端传来的 ID、tenant、principal 与 model key 均不能自行证明授权。跨用户 cache key 和
RLS / OLS identity 必须来自服务端验证的主体，外部 auth/schema/result authority 不完整时 fail closed。

multi-worker、multi-instance、restart behavior、transactions、idempotency、retry、timeout、
failure recovery、PostgreSQL migration path、Blob/Object Storage path、cache strategy、
distributed coordination when justified、schema migration、observability、audit、deployment、
upgrade compatibility。先证明资源归属、事务/重放/取消/失败恢复与隔离，再增加功能数量。
PostgreSQL / Blob / Redis 均尚未实现，不能把本地 SQLite + filesystem 的保证描述为生产云保证。

## M7 — Freshness & Report Lifecycle

现有 HTML Report 定义为 historical snapshot，刷新不得 silently overwrite。
未来 ReportDefinition / ReportRecipe + ReportArtifact versions：重新 query → 新 QueryResult
→ 新 VerifiedFactSet → 新 Report version，保留旧版本；refresh time 继续来自真实 Control Plane authority。

## M8 — Enterprise Pilot Platform

Entra login、RLS / OLS acceptance、resource isolation、report center、semantic model asset catalog、
Embedded、refresh/version、Audit/Trace、Usage/Cost 与 internal pilot。建议范围：5–10 users、
2–3 roles、1–3 semantic models、20–50 real business questions；必须先满足 M6 安全与隔离。

## M9 — Advanced Analytics & Controlled Authoring

新分析能力需独立 contract 与 factual proof，不自动解冻 Core。写操作必须：
Draft → Preview Diff → Validate → User Approval → Apply → Verify → Rollback。
禁止 LLM → Tool → direct production write；禁止把 ToolGateway readonly=False 当作 authoring implementation。

## Release discipline

main 是唯一活动开发线。流程为 failure-first → minimal implementation → fresh gates →
必要且有界 Real → 白名单 staging → 中文 commit → push main → exact-SHA CI → remote audit。
不得 git add . / git add -A、force push、rebase、history rewrite、reset --hard、clean、删除分支；
push 前 fetch，remote main 已前进则停止，不覆盖用户变更。不打 Tag。

同一 root cause 的 P1 不因每次失败都停止：保留 reproducer、更新证据，在已授权边界内最多两轮
minimal forward-fix；达到上限仍失败，或出现新根因、修改边界扩大、architecture risk 时停止重新
评估。不得降低 validator、删除 negative tests、改 expected 迎合错误、Mock Real 或隐藏 warning/error。
新的额外修复轮次必须取得明确授权并记录到 Error Ledger。

Local automated、Local Real、Remote exact-SHA CI 分层记录；历史 PASS 不替代 fresh evidence。
不读取/输出/提交 .env、Secret、Token、PBIX、DB、真实业务数据、完整真实 prompt/response/trace dump。
临时资源必须标明 ownership 并 finally teardown，不自动删除用户或 ownership 不明资源。
