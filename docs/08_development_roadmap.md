# 08 — 当前及未来开发路线

> Settings.version=M6.4；同Round 2 Final Git Seal待自身exact-SHA CI/Remote Audit/clean；M5 FINAL/FROZEN有效。

## 当前路线

Settings.version=M6.4；同Round 2必要Local/Cloud Real和fresh发布门已通过，Final Git Seal待本提交自身完整exact-SHA CI、Remote Audit与clean，全部成立才解析M6.4 FINAL COMPLETE并STOP。当前合同、timeout根因、Admin/Test A late/stale与RLS证据、既有OLS Test B例外和登录性能限制见[07当前验收](07_milestones_status_and_open_questions.md)。不启动M6.5/M6.6，后续须独立授权。

## 此前阶段记录（历史，不作为当前下一步或Final CI）

> **状态：** Settings.version=M6.3；M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ correctness IQ_ACCEPTED；M6.4 Round 2 Final Closure进行中（Local timeout恢复既有合同并Real PASS）；M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一路线 authority；状态见 [07](07_milestones_status_and_open_questions.md)，实施入口见 [09](09_context_handoff.md)。

## Round 2 Cloud metadata最小修复（2026-10-15，新增明确授权）

同Round 2 Final Closure：旧运行配置parent=120覆盖既有正式180秒合同，child LLM/MCP/render=120、DAX=30不变。fresh复现Understanding=4.468秒，Coverage剩余115.532秒开始，115.547秒后parent取消，总计120.015秒，业务DAX未进入；原115.781秒失败原件保留。仅进程恢复REQUEST_TIMEOUT_SECONDS=180，无production timeout代码或SLA变更、无implementation bug证据。原完整专业Report最终16.688秒Real PASS：三个合法LLM阶段、九DAX/九VerifiedFactSet/九section、Power BI Desktop来源、无功能裁减或fallback、MCP/worker残留0。Cloud Final原生复验和最终fresh gates继续；Settings.version=M6.3，未staging/commit/push，无本轮Final自身CI/Audit。证据在仓库外20261014-round2/final-timeout-root-cause-evidence.json及final-local-timeout-recovery-receipt.json；正式合同见ERR-5106-008。

用户已批准去除重复Schema、请求内exact model/schema新鲜proof去重、Cloud rename减少无关同步、
原deadline内有界退避只读metadata。fresh fetch/main/基线/staging核对通过；官方IQ限流合同已重验。
P0设计见IQ decision；后端failure-first 8FAIL/7PASS，前端1FAIL/23PASS。最小实现后邻近47PASS、安全68PASS、Cloud前端24PASS，Architecture恢复PASS；Semantic819PASS、Golden11PASS/1manualSKIP，全后端3516PASS/1SKIP/15保留warnings、前端160PASS、Typecheck/Lint/Build与治理门均PASS。Admin/Test A普通UI获批Real已完成；Local后置完整Report复验失败，当前STOP见上。
Admin慢速native lifecycle已PASS，仅证明功能/权限可执行，不计产品限流修复；普通启动配置问题已定位并提供独立进程级启动脚本。
普通 uvicorn + Vite 已完成 Admin 登录、获批 Workspace 三模型目录、Rich 已知销售额问答与侧栏重命名；合成 SQLite 只读复核 completed/real/committed 和持久标题均 PASS，未使用验收脚本冷却。新聊天后 Restore 原问答 PASS；两个既有模板均 Real 生成、completed/committed、页面已查看，专业模板 Fabric IQ 来源正确。连续第二个报表后双资源列表刷新仍返回 503 RATE_LIMITED；Auth session 仍 200，已提交报表仍可查看，原生重新加载、重选 Rich 后已 Restore 三个原历史 turn，无重新认证或写操作重放。该失败与截图保留；不能把单次重命名 PASS 解释为上游永不限流。Test A隔离已完成；Local后置完整Report失败为当前唯一blocker。
该授权不改事实链、RLS/OLS/ownership、Local、八Shape或Provider；仍同Round2，M6.3，FINAL NOT READY。

## Round 2 FINAL Provenance Fix（2026-10-15，当前授权）

用户明确批准极窄 Report provenance / presentation compatibility，覆盖此前 ERR-64-023 的 STOP。
fresh fetch 成功；main / HEAD / origin/main 仍为 d943d02d32140a605a33dd0aca928dbd420e344a，staging 空，只有本轮授权修改。
ReportDataSourceKind 新增 FABRIC_IQ=fabric_iq；创建快照前由服务端实际 FabricIQPowerBIAdapter
及当前 principal/session-bound 模型证明来源；不依赖 real flag、前端字段或 friendly 字符串。
ReadingContext、professional projection 共用同一 immutable snapshot；旧 Local/Remote/Fixture 映射保留。
QueryPlan、DAX Builder、ResultInspection、VerifiedFactSet、八 Shape 和 IQ numeric/completeness 合同无新增改动。
failure-first 7 FAIL/6 PASS，修复及邻近 103 PASS；原生专业报表显示 Fabric IQ · 实时查询，
审计来源 fabric_iq，真实模型名保留、合成 KPI 未变，native completed/real/mock=false/Memory committed。
仓库外 real-product-provenance-fixed-receipt.json 保存 artifact 与 screenshot hashes；旧错误来源回执仍保留。
IQ_ACCEPTED（Int64、completeness、八 Shape 8/8）保持。当前继续原授权剩余产品/安全验收。Local Desktop Answer/完整九查询专业报表已 Real PASS；全后端 3493 PASS/1 SKIP，Semantic 819 PASS、前端 159 PASS、Golden 11 PASS/1 manual SKIP，Typecheck/Lint/Build/Architecture PASS。
Settings.version=M6.3；未 commit/push，无本轮 exact-SHA CI/Remote Audit；不得提前计为 M6.4 FINAL COMPLETE。
以下 lineage/provenance STOP 为此前历史；当前授权和进度以本节为准，不启动新 Round 或 M6.5。

## Round 2 IQ FINAL LINEAGE FIX（2026-10-15，此前记录）

同一 Round 2，Fabric IQ 唯一 Cloud Data Plane。当前已验证 schema 是 lineage authority：
exact canonical 名或唯一 exact `TableName ColumnName` 才可归一化；未知、歧义、大小写/空格偏移拒绝。
Measure 仅 exact schema 名；内部固定投影 alias 不对公开 execute_dax 开放。
Failure-first 后 lineage 32 tests PASS；Real `FactSales Region` → `FactSales.Region` → `Region`
→ 原有 ResultInspection/VerifiedFactSet PASS。完整八 Shape Real 8/8 PASS，已核对已知值、行数、
无截断、Layer3、Inspection 与 Facts。Int64 min/max/null 和 N=12/wire=13 profile 证据共同授予 IQ_ACCEPTED。
外部 `iq-accepted-lineage-receipt.json` 保存四份脱敏 evidence 的 hash 索引；原始失败证据保留。

继续原授权 Real Product E2E：三个服务端 Workspace capability 独立 StrictBool、默认 false，
只在仓库外 operator 配置启用批准测试范围。owner-approved、Mock 标记、客户端字段不授予权限。
复用原有 owner repository 与 exact-resource/selection lease，policy 撤销使在途操作失败。
Admin 原生 Fabric IQ + DeepSeek 已返回 Total Sales=300，历史重命名已通过；只用新建的合成验收 DB，未读/迁移既有业务 DB。
Disclosure monitor 只记录计数和无 GUID/raw-schema-dump 检查，不保存真实 prompt/response。

用户纠正测试范围为整个 PowerBIAgent-M6-Dev Workspace，包括现有及后续测试 Model/Report。
目录只定向读取批准 Workspace 和其分页 collections，其它 Workspace ZERO request；不再逐资源人工白名单。
IQ 每连接使用服务端 exact Workspace/artifact 上下文，Resolve 返回身份与当前 principal GetSchema 仍必须验证。
新增 Workspace failure-first 7 FAIL/4 PASS，修复后 Workspace/产品边界组合 100 PASS；全量后端 3480 PASS/1 SKIP/15 warnings；前端 159 PASS、Semantic 819 PASS、Golden 11 PASS/1 manual SKIP，Typecheck/Lint PASS。
两个旧负例依赖缺失/伪造 service 时现为明确 AUTH_FORBIDDEN，原负例保留。

批准 Workspace 内现有 M3 Rich 合成模型已通过两个固定模板的 KPI 生成；简单报表 view/download 已验证。
专业报表生成不能计为验收通过：实际查询来自 Fabric IQ，但 canonical snapshot 的 source_kind 为
`local_mcp`、source_display_name 为 `Power BI Desktop`，专业报表原样显示了错误来源。
根因在 Frozen Core `backend/app/application/deepseek_turn_service.py:2664` 创建快照时写死来源；
当前没有来源注入参数。本轮禁止改 Core，也不允许在创建后改写来源快照绕过 authority。
唯一当前 blocker 为专业报表来源真实性；M6.4 FINAL BLOCKED，STOP。验收宿主已关闭。
脱敏 `real-product-report-source-blocker-receipt.json` 保存 HTML、Core source 与截图 hash；生成成功不冒充通过。
日期补充已获批准并完成；移动 measure 到 Sales 主表的离线提案未获明确批准，未执行。
Test A、RLS/OLS、完整资源生命周期、Local Desktop 与发布验收未完成；停止后不继续这些工作。
Settings.version=M6.3；未 commit/push；没有本轮 exact-SHA CI/Remote Audit，不将 IQ_ACCEPTED 计为 Final。
ResultInspection/VerifiedFactSet/Builder/QueryPlan/Renderer 等 M5 Frozen Core production diff=0。
下面旧停止记录为历史；当前以本节专业报表来源 blocker 为准，STOP，不启动新 Round 或 M6.5。

## 路线总览

2026-10-14用户授权继续同一M6.4 Round 2：Fabric IQ MCP为唯一Cloud Data Plane，
Fabric REST仅Catalog/Metadata；先Real Int64/N+1/size合同，PASS后最小boundary实现及完整Real/Local/Final验收。
短合同见[IQ decision](milestones/m6/m6_4_iq_data_plane_decision.md)，当前状态以07为准。
最新 continuation 已完成 raw envelope 分类：CSV 无 machine-readable type authority。
用户允许 conservative inline 路径；N=12/wire=13 与 Int64 已获 Real 证据并最小实施。
八 Shape Real 已经 schema-bound lineage 修复后全部 PASS，IQ_ACCEPTED。
产品验收发现专业报表来源在 Frozen Core 被写死为 Local Desktop；按当前禁止改 Core 的停止条件，FINAL BLOCKED，STOP。
不创建新Round、不扩大max_query_rows或Frozen Core；停止条件按当前用户授权和09执行。
下表仍为原路线；M6.5只在M6.4 Final实际COMPLETE后成为Next，不自动启动。

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

2026-10-14独立M6.4_FIX只修既有内部偏移，不新增正式里程碑，不改变下文M6.5–M9目标。
资源管理/企业数据服务端拒绝/合成E2E/技术决策见[FIX](milestones/m6/m6_4_fix_engineering_closure.md)；
COMPLETE按自身CI/Remote Audit/clean生效。M6.0–M6.2 COMPLETE（M6.2保留数值/完整性限制），
既有FIX后续[运行时回归](milestones/m6/m6_4_fix_runtime_regressions.md)继续同一scope收口，不新增阶段或改变原路线。
M6.3 Security COMPLETE；M6.4 FINAL NOT READY，M6.5/M6.6未启动。Settings.version=M6.3。

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

M6.4本轮新增测试安全顺序：先原始测试Workspace/model/report服务器allowlist与隐私P0，再产品E2E；仅测试环境收窄，正式产品保留current-principal Catalog。缺配置/授权fail closed，合成开发继续；不自动进入M6.4.1、M6.5、i18n或Azure。

2026-10-13用户授权现有M6.4成果阶段候选提交及自身exact-SHA CI/Remote Audit；不新增功能，Settings.version=M6.3，阶段保持PARTIAL/BLOCKED。
该候选记录为历史；当时还有Cloud资源及隐私内部缺口，当前由独立FIX修复。候选不授予业务执行或Final资格。

| 阶段 | 目标 / 验收 |
|---|---|
| M6.0 | COMPLETE：Fabric IQ官方合同 + 真实targeted probe + Accepted Consumption/Discovery ADR + Product/Auth UX设计；最终自身CI / remoteaudit解析 |
| M6.1 | COMPLETE：Entra Identity、same-origin BFF code/PKCE Login/Session、基础Account UX；token仅Auth/Transport；真实Entra与Phase A CI PASS，final marker以自身CI/remote audit生效 |
| M6.2 | COMPLETE（自身CI/remote audit生效）；两模型Real与Phase A CI PASS：新FabricIQPowerBIAdapter；固定X-Variants、tools/list validation、schema/result/error normalization与完整性failclosed；复用Core |
| M6.3 | Security COMPLETE（Final自身CI与remote audit生效）：ownership/IDOR/迁移、真实RLS/OLS 74/74、Late-Response 41/41、临时路由清理；销售额兼容仍P1 BLOCKED。见[M6.3合同](milestones/m6/m6_3_multi_user_ownership_authorization_rls_ols.md) |
| M6.4 | 已获用户批准并在本地开发/验证，发布NOT READY；Fabric IQ数值兼容P1须在Product E2E前解决：Fabric REST authoritative scoped Cloud Catalog + 管理员shared-resource seeds；自动加载/compactselector/全Product E2E；普通用户零URL/ID配置 |
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

后续规划包括同比 / 环比、异常分析、贡献度分析、下钻分析、根因分析，以及后期受控 DAX / 语义模型 / PBIR 修改。以上均为 M9 后续规划，当前未实施；不属于 M6.4，不增加本轮 QueryShape、Planner、DAX、报表模板或写操作。

新分析能力需独立 contract 与 factual proof，不自动解冻 Core。写操作必须：
Draft → Preview Diff → Validate → User Approval → Apply → Verify → Rollback。
禁止 LLM → Tool → direct production write；禁止把 ToolGateway readonly=False 当作 authoring implementation。

## Release discipline

main 是唯一正式活动开发线，默认在 main 开发、提交、推送。流程固定为：
Cold Start → Main 开发 → Failure-first → Minimal Implementation → Local Validation → 必要 Real → 白名单 Staging → 中文 Commit → Push main → 一次 Main Exact-SHA CI → Remote Audit。
不强制临时开发分支、PR 或 Phase A / Final 双 CI；仅当用户明确要求或 GitHub 权限客观要求时才使用 PR。
不自动修改 GitHub 分支保护；普通 push 被拒绝即停止报告，不以 force push、关闭更多保护或另建 PR 绕过。
管理员豁免是既有工作流的权限条件，不允许忽视失败的 CI；每个最终实际 main 提交必须通过自身完整 CI，不能继承旧 SHA 或 PR CI。
禁止 git add . / git add -A、force push、rebase、history rewrite、reset --hard、clean、未经授权删除分支。
不覆盖用户修改，不自动打 Tag；push 前 fetch，remote main 相对本轮基线前进即停止。

同一 root cause 的 P1 不因每次失败都停止：保留 reproducer、更新证据，在已授权边界内最多两轮
minimal forward-fix；达到上限仍失败，或出现新根因、修改边界扩大、architecture risk 时停止重新
评估。不得降低 validator、删除 negative tests、改 expected 迎合错误、Mock Real 或隐藏 warning/error。
新的额外修复轮次必须取得明确授权并记录到 Error Ledger。

Local automated、Local Real、Remote exact-SHA CI 分层记录；历史 PASS 不替代 fresh evidence。
不读取/输出/提交 .env、Secret、Token、PBIX、DB、真实业务数据、完整真实 prompt/response/trace dump。
临时资源必须标明 ownership 并 finally teardown，不自动删除用户或 ownership 不明资源。
