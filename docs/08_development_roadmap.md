# 08 — 当前及未来开发路线

> **状态：** Settings.version=M6.3；M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ数值兼容P1 BLOCKED；M6.4 NOT READY；M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一路线 authority；状态见 [07](07_milestones_status_and_open_questions.md)，实施入口见 [09](09_context_handoff.md)。

## 路线总览

| Milestone | 定位 | 当前路线 |
|---|---|---|
| M5 | Core Analysis Kernel | FROZEN；保留 failure-first correctness forward-fix |
| M6 | Cloud Consumption & Enterprise Identity | M6.2 COMPLETE；M6.3 Security COMPLETE（Final自身CI与remote audit生效），数值兼容P1 BLOCKED；M6.4 NOT READY |
| M7 | Freshness & Report Lifecycle | 后续规划 |
| M8 | Enterprise Pilot Platform | 后续规划 |
| M9 | Advanced Analytics & Controlled Authoring | 后续规划 |

M0—M4 已封板；M5.10.8 与 FIX COMPLETE。M5 小阶段历史移交 CHANGELOG / milestone docs / Git，
旧路线原文见 [Historical snapshot](archive/m5_pre_final_08_development_roadmap.md)。
M6 每个 implementation patch 必须另行获批，并满足 09 的官方能力与 P0 安全前置条件。

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
当前实现为 MockPowerBIAdapter、LocalMCPPowerBIAdapter、FabricIQPowerBIAdapter 与未完成的 RemoteMCP skeleton，Real 失败
不得回退 Mock。Cloud PowerBI Adapter 继续服从 PowerBIAdapter 与 ToolGateway，不能复制管线。

```
SemanticFrame → Grounding → CanonicalQueryPlan → Deterministic DAX
→ Power BI data plane → QueryResult → ResultInspection → VerifiedFactSet → Answer / Report
```

任何 M6 implementation 前必须重新验证 Microsoft 官方 API / MCP / Fabric 文档，保存日期、
官方来源、endpoint、auth、tenant/identity、capability/tool schema、RLS/OLS 与 fail-closed probe
证据。[M6.0 audit](milestones/m6/m6_0_fabric_iq_cloud_contract_audit.md) 已核验Fabric IQ官方GA
消费合同与两个模型小型runtime probe；[ADR-020](adr/ADR-020_fabric_iq_cloud_consumption_and_catalog_authority.md)
接受消费/目录/identity边界。ADR-006旧endpoint/SDK/OAuth假设废弃；M6.1 Entra开发runtime已实现，M6.2 Cloud Adapter两模型Real与Phase A CI通过（最终自身CI/remote audit生效），multi-worker production尚未实现。
固定selector wire、自建app OAuth、REST catalog与双用户RLS/OLS各在对应implementation入口验收。

| 未来职责 | 范围 |
|---|---|
| PowerBIDataPlane | IQ resolve、schema、member/value search、execute deterministic DAX；Discover仅候选 |
| PowerBIControlPlane | Fabric REST current-principal workspace/model/report catalog与metadata；未来refresh/embed/lifecycle |

refresh API 不得塞入 execute_dax adapter。Control Plane/Catalog仍为后续M6架构方向；M6.2 Data Plane证据见当前阶段。

### M6 正式分阶段路线

| 阶段 | 目标 / 验收 |
|---|---|
| M6.0 | COMPLETE：Fabric IQ官方合同 + 真实targeted probe + Accepted Consumption/Discovery ADR + Product/Auth UX设计；最终自身CI / remoteaudit解析 |
| M6.1 | COMPLETE：Entra Identity、same-origin BFF code/PKCE Login/Session、基础Account UX；token仅Auth/Transport；真实Entra与Phase A CI PASS，final marker以自身CI/remote audit生效 |
| M6.2 | COMPLETE（自身CI/remote audit生效）；两模型Real与Phase A CI PASS：新FabricIQPowerBIAdapter；固定X-Variants、tools/list validation、schema/result/error normalization与完整性failclosed；复用Core |
| M6.3 | Security COMPLETE（Final自身CI与remote audit生效）：ownership/IDOR/迁移、真实RLS/OLS 74/74、Late-Response 41/41、临时路由清理；销售额兼容仍P1 BLOCKED。见[M6.3合同](milestones/m6/m6_3_multi_user_ownership_authorization_rls_ols.md) |
| M6.4 | NOT READY、须独立批准；Fabric IQ数值兼容P1须在Product E2E前解决：Fabric REST authoritative scoped Cloud Catalog + 管理员shared-resource seeds；自动加载/compactselector/全Product E2E；普通用户零URL/ID配置 |
| M6.5 | Public Real Business Data Validation：UCI Online Retail II；不增加QueryShape/报表模板 |
| M6.6 | Enterprise Production Readiness Seal：安全/部署/恢复/并发/observability与真实能力限制汇总；M7/M8仍独立 |

M6.1 stage boundary延续：M6.3安全验收不自动开放ENTRA_BFF旧product API；
M6.3 Alembic迁移仅在synthetic DB验收，生产迁移仍须operator备份、验证与授权。实现证据见[M6.1](milestones/m6/m6_1_entra_identity_login_session.md)。

M6.4 workspace catalog需要Workspace.Read.All与Viewer；individual share不保证完整覆盖，返回partial
而非“无模型”，不以Discover空结果判空。目录覆盖范围、管理员seed/access验证详见M6.0第5节。
M6.0 Product/Auth UX第11节是M6.1/4handoff：CurrentChatGPTWeb布局/交互参考，现有PowerBIAgent
visualtokens authority；本轮无前端实现，不复制品牌，不做dashboard。

M6.5首选[UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online%2Bretail%2Bii)：约百万真实
商业交易，订单/商品/客户/国家/数量/价格/取消适配当前Sales事实链。目标FactSales、DimDate、
DimProduct、DimCustomer、DimCountry；measures Total Sales、Total Quantity、Total Orders、
Average Order Value、Cancelled Orders、Cancelled Amount、Unique Customers。先明确取消金额正负、
退货/缺失值/币种等口径再建模；M6.0不下载/导入。Amazon Reviews为后续customer voice/after-sales/
product review候选。各阶段须独立获批scope，M6.0结束立即停止。

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

main 是唯一活动开发线与正式发布基线。流程固定为：
Cold Start → Failure-first → Minimal Patch → Local Gates → 必要 Real 验收 → 白名单 Staging → 中文 Commit → 临时交付分支 → PR Required CI → 受保护合入 main → Main Exact-SHA CI → Remote Audit。
临时交付分支仅用于本轮 PR，不作为长期并行开发线；本地可先从已核验 main 创建分支再提交，禁止直接 push main。
管理员同样必须通过 required checks，禁止绕过 branch protection；PR required CI 不替代最终 main exact-SHA CI。
禁止 git add . / git add -A、force push、rebase、history rewrite、reset --hard、clean、未经授权删除分支。
push/merge 前 fetch；除本轮受保护 PR 合入外，remote main 相对 Cold Start SHA 前进即停止。不覆盖用户修改，不自动打 Tag。
Cold Start 初始要求 main、HEAD==origin/main、clean worktree；交付阶段允许本轮临时分支及白名单改动，
核对分支归属与 diff，未知用户修改立即停止。PR 合入后回到 main，以 git pull --ff-only 同步并重新审计 clean。
封板只依据最终 main SHA 自身的 CI 与 remote audit，不继承 PR CI 或旧 SHA 的结果。

同一 root cause 的 P1 不因每次失败都停止：保留 reproducer、更新证据，在已授权边界内最多两轮
minimal forward-fix；达到上限仍失败，或出现新根因、修改边界扩大、architecture risk 时停止重新
评估。不得降低 validator、删除 negative tests、改 expected 迎合错误、Mock Real 或隐藏 warning/error。
新的额外修复轮次必须取得明确授权并记录到 Error Ledger。

Local automated、Local Real、Remote exact-SHA CI 分层记录；历史 PASS 不替代 fresh evidence。
不读取/输出/提交 .env、Secret、Token、PBIX、DB、真实业务数据、完整真实 prompt/response/trace dump。
临时资源必须标明 ownership 并 finally teardown，不自动删除用户或 ownership 不明资源。
