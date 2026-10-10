# M6.3 — Multi-user Ownership / Authorization / RLS-OLS Isolation

日期：2026-10-10。用户已批准专项及最终两阶段封板。Settings.version暂为M6.2。
当前安全验收通过：Real A→B→A 74/74；Real Late-Response 41/41；临时设施已卸载。
Phase A / Final exact-SHA CI尚未执行；此候选文档不提前宣称正式COMPLETE。
Fabric IQ销售额数值兼容P1 BLOCKED，M6.4 Product E2E未完成。下文第7节是保留的历史失败轨迹，不代表当前停点。

## 1. Fresh Cold Start 与官方能力

首次修改前 main、clean，fetch 后 HEAD==origin/main==`419dfd5cdde5c7550d62bbdaca12c7de853cea65`。
已按 AGENTS 固定顺序阅读 charter、CLAUDE、07/08/09、README/CHANGELOG、ledger、ADR-020 与相关实现/tests。
2026-10-10 fresh GitHub 查询确认 baseline [CI 38012437829](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38012437829)
event=push、head_sha 精确匹配、completed/success；Full Validation (Windows) 及全部 23 steps success。
它只证明 M6.2 baseline，不证明当前未提交 patch。

2026-10-10 重新核验 Microsoft 官方资料：

- [Fabric IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)：delegated caller authority、Item.Read.All / Item.Execute.All / Dataset.Read.All；官方 endpoint/selector 与 tools/list 合同沿用 M6.2；不能使用 app-only 或 administrator impersonation 证明用户隔离。
- [Fabric RLS](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security)：Viewer 才受 RLS 约束；Admin/Member/Contributor 不构成 RLS 证据。
- [Fabric OLS](https://learn.microsoft.com/en-us/fabric/security/service-admin-object-level-security) 与 [tabular OLS](https://learn.microsoft.com/en-us/analysis-services/tabular-models/object-level-security?view=sql-analysis-services-2025)：数据与 metadata 均受限制；restricted table 可设 metadataPermission=none；RLS/OLS 应在同一个角色组合定义，不能以不同角色叠加推断隔离。

RLS/OLS authority 永远是 Microsoft semantic model。应用不复制过滤条件、不在客户端筛选结果、不模拟授权。
Fabric IQ completeness 仍保守：无法证明完整的结果保留 truncated=true，不因安全 smoke 放宽。

## 2. 修改前 reality audit

| 资源 / 边界 | M6.2 实际 identity 与风险 |
|---|---|
| Conversation / conversation delete intent | PK runtime_mode + conversation_id，无 principal |
| WorkMemory | surrogate id；unique runtime_mode + request_id；committed version 仅 runtime + conversation |
| PendingClarification | surrogate id；unique runtime_mode + conversation_id |
| ResultSnapshot | surrogate id；unique runtime_mode + request_id |
| ReportArtifact / presentation / delete intent | 全局 report_id；source_mode 只区分 mock/real |
| Query / search / count / lifecycle | runtime + 资源 ID；没有企业 owner SQL predicate |
| Cursor | kind + runtime + query scope；未绑定 principal / epoch |
| Idempotency | 每个 SnapshotRepository 自身 tracker；仅 runtime + request_id |
| Files | 本地 managed root 与 report_id，尚无企业 principal root |
| Cloud schema / model binding | M6.2 request/session scoped，principal + epoch；权限失败后 transient 清理需补足 |
| Cloud result / members | 无全局 cache；member 每次执行受 binding 保护的查询 |
| LOCAL schema/result/member caches | Local MCP / mock 路径，仅 LOCAL_DEV；ENTRA 不创建这些服务 |
| ENTRA_BFF | 业务 persistence/TurnService 未初始化；旧 /api/* fail closed，是正确基线 |
| Migration | Alembic 是正式 authority；SQLite batch recreate 涉及旧 unnamed FK/UQ 与 PK/index |

runtime_mode/source_mode 始终只代表 mock/real，不能承担授权 identity。

## 3. P0 设计与实现合同

身份链：validated AuthService session → immutable PrincipalContext → ResourceOwnerScope → scoped Repository/Service。
factory 对 session projection 做 equality 验证，不能由客户端提交 tenant/principal 或构造任意 owner。
ResourceOwnerScope 包含 tenant_id、principal_id、identity_mode、authorization_epoch。

- resource_owners 是 DB namespace authority：owner_id PK，identity_mode + tenant_id + principal_id unique，identity check。
- LOCAL_DEV 固定 `local:legacy` / local / legacy；所有历史行只迁入此 namespace，永不归属首个登录用户。
- ENTRA_PRINCIPAL 验证 canonical tenant/principal UUID；owner_id 为稳定 tenant+principal SHA256 投影，FK 指向 namespace。
- durable ownership 不含 epoch，因此同用户重新登录仍能访问自己的历史；transient key 包含 epoch，旧 cursor/claim/binding 失效。
- 八种资源表 owner_id NOT NULL + FK。Conversation 与相关 intent 的 PK 为 owner+runtime+ID；report 系列为 owner+report_id。
- Memory/Snapshot/Pending 保留 SQLite autoincrement surrogate id；业务 unique 与 committed-version partial unique 加 owner。ORM mapper identity 含 owner，使 ORM UPDATE/DELETE 也含 owner predicate。
- 对话子资源复合 FK 包含 owner+runtime+conversation，阻止跨 owner 关联；migration 为既有 indexes 加 owner 前缀。
- 所有 repository SELECT/COUNT/SEARCH/EXISTS/UPDATE/DELETE 直接带 owner WHERE；INSERT 显式 owner。没有先全局查询再 Python 检查的授权路径。
- Scoped session 在 DB await 前后、flush/commit 前重新验证会话；guard 拒绝跨 owner row 写入及 owner 变更。
- report 文件使用独立 owner managed root；每次 file access 先查 scoped metadata，不信任旧内存 artifact cache。清理要求本 owner durable delete-intent witness。
- factory app-owned shared idempotency tracker，key 包含 owner+authorization_epoch+runtime+request；claim await 后再验证，失效则 abort 清理。
- 六类 cursor 使用 app-owned random secret 的 HMAC，签名覆盖 owner+epoch+原 kind/runtime/query scope。LOCAL 既有 cursor 行为保留。
- logout/epoch mismatch 清理 Adapter binding/schema；HTTP 401/403/404 或等价结构化权限错误撤销 session，必须重新登录且 schema-before-bind。
- 不存在和他人资源都表现为同一 NotFound；没有“属于他人”的 public message。沿用已有 auth/failure contract。

没有把 tenant/principal 传入 SemanticFrame、Grounding、StateTransition、QueryPlan、DAXBuilder、VerifiedFactSet、Renderer 等 Frozen Core。
没有第二 Planner/Memory/Agent、RAG、LLM DAX、新 QueryShape、生产业务写删或生产数据库迁移。

## 4. Migration 与恢复

Alembic head：`f63a1b2c3d40`，down_revision=`c2e4f6a8b130`。
仅 synthetic tempfile DB 执行过 fresh/M6.2 upgrade；Agent 未读取或迁移用户现有 DB、PBIX 或业务数据。

迁移前停止应用和所有 DB writers；由 operator 对 SQLite 与 managed report root 做离线完整备份，并记录备份可恢复性。
对备份副本执行既有 Alembic upgrade head，核验 revision、八表 row count/内容、local owner、FK 与 indexes，再执行正式迁移。
新增 namespace 和八表 batch recreate 在正式迁移链内完成，保留 JSON payload、report paths 与 local 文件布局。
无 NULL/everyone owner；迁移后的 legacy 文件仍由 LOCAL repo 原 root 访问。
downgrade 明确拒绝：principal 同 ID 不可安全合并。回滚须停应用、恢复 M6.2 离线备份并使用对应 M6.2 checkout；禁止从 M6.3 数据猜测合并身份。

测试证明：fresh DB、包含八表数据的 M6.2 DB、重复 upgrade no-op、payload 原样保留、foreign_key_check 无 orphan、unknown owner FK 拒绝、forward-only downgrade 不改变 head，以及升级后 A/B 同 ID 各自 commit version=1。
历史 migration `01dc0d90` 的 SQLAlchemy PK reflection warning 如实保留；不是 ownership FK 失效，未隐藏 warning 或重写旧 migration。

## 5. Synthetic acceptance / cache audit

| 验证 | 证据位置 |
|---|---|
| 同 tenant 不同 principal / 跨 tenant、相同 IDs 独立、Memory commit/fail/pending、snapshot | tests/unit/persistence/test_m63_ownership.py |
| history/read/search/count/rename/archive/restore/delete、report access/下载/文件、crash delete-intent | tests/unit/persistence/test_m63_ownership.py |
| recent/archive/search/history/conversation reports/global reports 六类 cursor owner/epoch/tamper | tests/unit/persistence/test_m63_ownership.py |
| shared idempotency、LOCAL legacy 隔离、logout/late DB response/late claim | tests/unit/persistence/test_m63_ownership.py |
| 真实 Alembic schema 升级、约束、同 ID versioning | tests/unit/persistence/test_m63_migration.py |
| server derives owner、客户端 spoof extra 拒绝、foreign/missing 同 404、正式 product gate | tests/api/test_m63_ownership_boundary.py |
| A key → B schema/query/member 拒绝（包括 copied ref）、同模型不同 schema/result/member 不交叉、旧 epoch、401/403/404 清理 | tests/unit/test_fabric_iq_adapter.py |

无 Cloud global query/member cache；schema/binding 只在被 validated session 绑定的 Adapter 中。测试通过不等于真实 RLS/OLS 已生效。
process-local Auth sessions、HMAC secret 与 in-flight tracker 仍是 single-process development 基础；非 multi-worker production 保证。
权限变化只能由 Microsoft 拒绝或重新登录重新确认，无后台权限变更订阅；fail closed 后强制 fresh login，不能宣称连续权限同步。

failure-first：最初新增 owner tests 因缺 factory/module RED；权限撤销测试因 binding 未清理 RED。随后最小实现与 regression。
迁移修复两轮分别补齐 reflected unnamed FK 与 unnamed UQ 命名；未删除 negative tests 或弱化约束。
新增测试 fixture 漏 response_type 导致第一轮 full pytest 1 failed/3018 passed/1 skipped；修正 synthetic fixture 必填字段后重跑。
既有 schema assertion 仅同步新 head、owner PK/FK 以及 composite ORM get key，不改业务 expected。

## 6. 初次实现Local gates（历史记录，不代替最终回归）

- focused persistence + Fabric IQ + HTTP ownership：328 passed / 1 skipped；历史 migration warning 3。
- Semantic Compatibility：819 passed。
- Golden：11 PASS，manual Real baseline 1 SKIP。
- Frontend：11 files / 112 tests PASS；typecheck、lint、production build PASS。
- 最终 full backend（CI同一wrapper，未deselect）：3030 passed / 1 skipped / 11 warnings，314.14s。
- warning如实保留：历史Alembic PK reflection 3项；既有MSAL response_mode建议8项。没有隐藏或降低validator。
- Architecture PASS（158 production files）；Repository Safety PASS（458 files）；Ledger PASS（121 entries）；Documentation Governance、Artifact Governance、git diff --check PASS。
- 本轮 Local Real DeepSeek + MCP：未执行；Cloud Real A/B：未执行；M6.3 Phase A / final exact-SHA CI：未执行。

## 7. 历史部署与失败证据轨迹（原文保留；当前结论见第9—11节）

2026-10-10后续用户确认：同tenant两个独立测试用户已加入PowerBIAgent-M6-Dev且均为Viewer；用户本人保持Admin仅做配置，不计入RLS/OLS证据。
按后续授权，Agent已在仓库外生成D:\AAA_Workfile\M63Fixture：单一synthetic PBIP/PBIR、model.bim、官方TOM生成的TMDL、create-only XMLA和固定Fabric REST payload。
Microsoft公开JSON schema六项与Microsoft.AnalysisServices 19.114.12 TOM/TMDL反序列化/角色属性检查PASS；20个定义文件SHA256 manifest。无真实用户成员、外部data source或业务数据。
仓库外publish_fixture.py使用既有localhost回调，独立管理员Fabric SemanticModel.ReadWrite.All流程；token只在临时Auth/Transport内存，不改产品DELEGATED_SCOPES。
固定用户指定工作区和模型，空POST+native CSRF，只创建不覆盖/删除；201、202轮询、冲突、网络结果不明停止、禁止重复创建及product gate离线检查PASS。
用户管理员已在http://localhost:5173/auth/m63-publisher完成交互登录；实际Fabric create-only API成功返回已创建SemanticModel，safe deployment-receipt.json已写入仓库外。当前CREATED_REFRESH_AND_ROLES_PENDING，未证明刷新/角色分配或Real RLS/OLS。
后续operator确认两个角色已分配，已触发刷新但尚不知刷新结果；该确认不等于已验证角色成员配置或Real查询，refresh_verified与real_rls_ols_verified继续false。验收入口HTTP200、未登录probe401已检查。
再后续operator提供Fabric UI“最近一次刷新成功: 2026/10/10 11:13:07”；仓库外receipt记录refresh_reported_success及evidence source，不冒充Agent已执行查询。Real RLS/OLS仍未开始。
仓库外automatic_acceptance.py完成71项offline A→B→A集成检查，包含distinct caller/错账号拒绝、fixed scalar/grouped/schema/restricted、对称资源IDOR、foreign/stale key、same-ID各自create/delete、native CSRF、product gate和logout后拒绝。所有测试仅synthetic identity/transport，不是Real。
Real临时服务器已重启至新的synthetic root，原三只读scopes不变；页面在用户自行完成登录后自动触发固定POST流程。safe evidence只记录principal hashes、query/schema/rows hashes、shape/status与预设check labels；不记录token/cookie/真实身份/DAX响应dump。
/auth/m63-evidence当前evidence_mode=REAL、stage=AWAIT_A_LOGIN、automatic_matrix_passed=false、real_rls_ols_verified=false。管理员排除仍生效。基础自动矩阵通过也不会自动宣称完整M6.3验收通过，剩余Real/cleanup/gates分别证明。
首次Real A已执行：Resolve PASS、schema PASS且RestrictedTable可见，scalar因synthetic_shape_mismatch FAIL，2026-10-10T03:29:28.851880+00:00 STOPPED；B尚未开始。safe失败记录保存在原run root，不删除或冒充PASS。
因原harness仅记录shape guard，实际返回类别未保留，不能据此断言RLS绕过或数据未加载。补充仅针对synthetic scalar的有限枚举诊断，以及固定DimRegion/FactSales COALESCE COUNTROWS（只允许0/1/2）；其他返回完全redact。blank、unfiltered300、numeric-string仍FAIL，诊断不会改变expected或normalize生产逻辑。
离线新增负例与完整71项矩阵回归PASS。临时harness重启到新root，Auth会话随进程销毁；当前等待A重新登录诊断，不进入B/Phase A，不commit/push。
第二次Real A重测已完成（2026-10-10T03:36:37.962153+00:00）：Resolve/schema PASS，RestrictedTable可见；scalar HTTP409，diagnostic=numeric_string_100、row_count=1、truncated=true；固定counts DimRows=1/FactRows=1。数据已加载且A可见一条Dim/Fact的证据已取得，但字符串类型严格检查仍FAIL，B尚未开始。
本地生成模型的[Total Sales]含formatString=0，格式传播是待验证原因，不能据此改生产normalizer或硬转字符串。仅仓库外harness把相同scalar/grouped固定查询表达式改为CONVERT([Total Sales], INTEGER)；Microsoft官方CONVERT文档确认整数返回类型。A/B预期仍为数值100/200，numeric-string/blank/unfiltered负例仍STOPPED FAIL，truncated未知仍true。71项offline矩阵与诊断负例再次PASS。页面触发器按AWAIT阶段记录，支持同页后续B/A登录。新的Real进程需重新登录A验证；不commit/push。
第三次A在2026-10-10T03:44:18.145267+00:00 Resolve HTTP401即停止，新整数表达式尚未执行。caller fingerprint与第二次不同，但operator明确确认同一个A，原因待查；不输出真实identity或猜测选错账号。旧runner未记录public Auth failure code，因此不能从401断言token、scope或权限具体根因。
用户要求先查全问题再集体重测后，仓库外runner改为独立检查汇总：先执行当前有效身份的synthetic资源检查，再cloud；scalar/schema/grouped等独立失败不终止其他检查；缺已证明key/resource或session丢失明确SKIP，绝不当PASS。A/B/A所有阶段的FAIL/SKIP统一阻止MATRIX通过，OLS网络错误不能当授权拒绝。增加public Auth failure code、Auth内delegated acquisition有限枚举、wire列/cell类型，无原始response/value/token/cookie输出或持久化；expected和normalizer不放宽，bool不能充当RestrictedCount整数1。
临时/retest由native Auth/CSRF和原始A保护，仅空POST；新矩阵使用新synthetic目录，原evidence归档，Auth会话不随重测重启。页面触发器包含本轮matrix/stage/原生CSRF会话变化，foreign/stale/own checks使用独立名称。新增collect-all negative suite覆盖同时三个失败、Auth丢失、resolve依赖SKIP、B OLS网络错误、最后A成功不能抹掉历史失败、wrong caller/CSRF拒绝、旧evidence保留与新storage。71项正例及该套负例offline PASS；尚无collect-all Real或B证据，不commit/push。
创建成功后关闭独立管理员发布器，切换仓库外run_security_harness.py与原三只读scopes；入口/auth/m63-acceptance，原Vite保持。官方发布管理员hash被显式拒绝进入验收probe；此排除、临时/auth前缀、CSRF与product gate offline检查PASS。
现有Power BI Desktop为2.114（2023版），未证明可打开当前PBIP，因此优先使用上述Fabric REST发布路径；用户无需手写模型或更新应用代码。

A. 使用专用、纯合成模型 `PowerBIAgent_M6_3_SecurityFixture`；当前未确认已部署的安全 fixture，不能复用两个旧真实业务模型来假装验收。
模型合同：DimRegion 两行 A/B；FactSales 各一行，A=100、B=200；active one-to-many DimRegion→FactSales；[Total Sales]=SUM(FactSales[Amount])；无关系 RestrictedTable 只有一行 synthetic marker。
模型部署/安全角色定义由具备权限的 operator 完成；用户无需修改应用代码。若无法取得模型与角色配置权限，保持 BLOCKED。

B. 同 tenant 的两个独立 Entra 测试用户 A/B，均为测试 workspace Viewer，具备目标模型访问权。最新[Fabric IQ官方说明](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)明确无需workspace role或Build；本fixture选Viewer用于明确验证RLS，不额外要求Build或扩大权限。
不得使用 Admin/Member/Contributor；测试管理员使用第三个身份。没有第二用户则需要有权限的 tenant 管理员创建独立测试用户，密码/token/secret 不发送到聊天。

C. A 只加入 `M63_RegionA`：DimRegion[Region]="A"。B 只加入 `M63_RegionB_Restricted`：DimRegion[Region]="B"。
不要给 A/B 叠加额外宽权限角色；用户/组继承权限也须检查。

D. OLS 与 RLS 在上述同一角色组合内：A role 可读 RestrictedTable；B role 对 RestrictedTable metadataPermission=none。
仅隐藏视觉/字段不是 OLS。平台不能配置 OLS 时本 milestone 仍 BLOCKED。

E. 两个独立 browser profiles：先 A 登录建立自己的 schema/key、synthetic resource 与 query evidence；再 B 登录执行相同 scalar/grouped DAX、schema/OLS denial 和 A key/资源 ID 负例；反向 B→A；A logout→B login；最后 A 重新登录验证自己资源仍可访问。
Agent 负责临时 harness 启停、schema/query 与证据收集，用户只做浏览器/Microsoft 登录/Power BI 权限操作。
用户配置后只需回复：**M6.3 RLS/OLS 测试用户配置完成**。

仓库外 `D:\AAA_Workfile\PowerBIAgent_M6_3_Acceptance\security_harness.py` 已准备，未启动Real服务器。
仅 synthetic resource、server-owned fixture bootstrap、固定 scalar/grouped/restricted DAX；require_principal + native CSRF；不接受 tenant/principal/token/任意 DAX。
harness 使用新的独立 synthetic DB/root；不读取开发者业务 DB。不得将它挂入 production app 或提交为永久 debug route。
仓库外validate_harness.py offline dry-run PASS：native OAuth协议fake、A/B synthetic resource/相同ID、server-derived owner、spoof拒绝、foreign/missing拒绝、schema/scalar/grouped/restricted、旧key/epoch与native product 403/临时path404。此结果只证明harness可用，不证明Microsoft RLS/OLS。
结束后关闭临时进程并验证正式应用所有 /m63-security 路径 404；只记录 safe identity hash、PASS/denial、synthetic labels、row counts/hash/shape。

真实门槛尚缺：A/B实际登录principal证明、已发布/刷新并分配角色的fixture、同 DAX 各自分区、restricted schema/query denial、跨 principal binding/cache/resource负例、退出/切换与 late response Real。用户对两个Viewer的准备确认已收到，但不能代替实际调用证据。
synthetic tests 不能替代这些证据。

## 8. 当前Closure contract

2026-10-10用户批准先完成安全、Real Late-Response、清理与完整回归，然后白名单staging，
创建M6.3_多用户归属与权限隔离候选，正常push main并等待该exact-SHA Full Validation (Windows)全required steps success。
之后更新文档与Settings.version=M6.3，创建M6.3_多用户安全隔离与真实验收封板，再等待Final exact-SHA CI。
HEAD==origin/main、worktree clean、正式路由无绕过且M5 Core未重构才正式COMPLETE。无tag、不自动启动M6.4。

历史初次实现停点remote audit：再次fetch origin main成功；branch=main，HEAD==origin/main==`419dfd5cdde5c7550d62bbdaca12c7de853cea65`；staging为空，worktree含本轮patch，预期dirty。不存在M6.3候选/final SHA与CI，不继承M6.2 CI作本轮closure。


## 9. 验收范围调整与真实安全结果

用户在最终封板指令中明确批准：M6.3作为安全里程碑独立封板，将Fabric IQ销售额数值兼容转为M6.4 Product E2E前P1阻塞项。
这是显式范围调整；原销售额标量/分组FAIL保留，没有把原完整查询验收改写成PASS。
真实同tenant双Viewer安全矩阵74/74 PASS（A17、B31、A返回26；0 FAIL/0 NOT_TESTED）。
COUNTROWS标量/分组为严格数字，Region为A/B/A；A可读RestrictedTable，B实际schema隐藏且固定查询被拒绝。
真实Late-Response 41/41 PASS：7类A在途操作在native logout及B登录后全部AUTH_REQUIRED；
Memory/Snapshot/Report/History零过期提交、A binding清除且不可复用，B资源/会话/Idempotency不受影响；A返回身份与原A一致。
Late测试使用真实Entra/MSAL/BFF、IQ Transport/Adapter及原生Repository；延迟注入仅在仓库外，synthetic DB/HTML。
完整Cloud Product UI/E2E、外部角色撤销通知NOT_TESTED，不以该测试冒充上述产品能力。
临时服务已关闭，正式native app已恢复；临时/auth/m63-*及/m63-test路径原生后端404；未登录正式API401、合成登录产品gate403。
Vite对未代理未知路径仍返回SPA shell，不能把该200当作后端路由存在；/auth代理路径404已实测。
按用户2026-10-10最终封板指令显式调整验收范围：M6.3 Security独立封板，销售额标量/分组仍FAIL CONTRACT_DRIFT。
Fabric IQ数值兼容为M6.4 Product E2E前P1 BLOCKER；不得强转、改expected、降低M5 ResultInspection/VerifiedFactSet或伪造PASS。
旧401首次拒绝层、旧第三轮A指纹差异UNRESOLVED；本轮principal比较来自validated tenant+principal稳定hash，不依赖session/epoch或邮箱。
Cloud完整性仍保守truncated=true；M6.4 Catalog、完整Chat/Report/History UI与Product E2E未实施，须独立批准。

| Real阶段 | PASS | FAIL | NOT_TESTED（该固定矩阵内） |
|---|---:|---:|---:|
| A | 17 | 0 | 0 |
| B | 31 | 0 | 0 |
| A返回 | 26 | 0 | 0 |
| 独立Late-Response | 41 | 0 | 0 |

云端实际TMDL/TOM已只读核验：DimRegion A/B String、FactSales Amount Int64 100/200、Total Sales=SUM(FactSales[Amount])、无FORMAT、关系active且单向；RestrictedTable存在。
实际M63_RegionA过滤A；M63_RegionB_Restricted过滤B并RestrictedTable metadataPermission=none；与本地核心定义一致，不仅检查本地源文件。
云端TOM19.114.12与角色定义证据脱敏保存在仓库外，管理员仅部署，不作为RLS验收身份。

Safe原始证据路径与SHA256（仅摘要进入Git，无token/cookie/raw GUID/真实业务数据）：
- audits/20261010-decoupled-security/real-security-matrix.json：8f5f3e3aac286ece2675991f9587bdb2e9b4d2fecab0d3a5b69bc92a377e04a1。
- audits/20261010-final-seal/real-late-response.json：f04cac4b8c194223e7d6f267366df41a5f61dd8704d1c23590769c7cbc0f4f6d。
- audits/20261010-final-seal/native-route-cleanup.json：ba21cf7c7637a9e9c1f9c4142a6d091974b346094cd8af34f73eb6509b0379fa。
仓库外根目录为D:\AAA_Workfile\PowerBIAgent_M6_3_Acceptance；历史三轮失败、离线失败、撤回CONVERT的原记录全部保留。

## 10. 数值合同与独立未决项

| 问题 | 状态与证据 | 修改边界 / 后续 |
|---|---|---|
| 销售额Int64声明/JSON字符串 | VERIFIED首次可观测差异已在HTTP wire；SDK仍str，Adapter严格拒绝CONTRACT_DRIFT。云模型/DAX均数值。上游内部为何编码为str及其是否合法UNRESOLVED | P1 BLOCKER，M6.4 Product E2E前解决；只按充分官方/运行时合同做Adapter边界修复，不改M5或强转 |
| Runtime tools/list | VERIFIED ExecuteQuery只有artifactId/daxQueries/maxRows；无outputSchema或raw numeric输出参数；metadata SHA256=23a80c87654574ad3cffb3e5cb40443df7d73bf2ba379b5e5bbf69a9acbc46c6 | 不能把任意Protobuf/一般Int64 JSON惯例当作本服务授权合同 |
| 旧Resolve 401 | UNRESOLVED：旧Harness未保存首次public failure/stage；新真实安全及Late查询无异常401 | 不猜测Broker/Session/IQ/模型权限，不因旧症状修改认证代码 |
| 历史A第三轮指纹差异 | UNRESOLVED：用户确认同A，旧validated claim证据不足；Harness两套算法已统一并记录版本 | 稳定tenant+principal比较，本轮A返回匹配；不能倒推旧差异已解决 |
| Cloud查询完整性 | UNRESOLVED：缺完整性authority，继续truncated=true | M6.4 Product E2E必须证明完整性或安全失败，不静默true→false |
| 外部角色撤销 / 完整Cloud UI E2E | NOT_TESTED | 不属于本次已批准安全封板证据，后续独立授权 |

保留Fabric IQ严格按列JSON验证、Int64上下界、bool不得冒充int、null、CSV canonical整数与JSON/CSV镜像一致性。
100合法；字符串100、abc、true、溢出及不明确格式拒绝；CSV列类型解析不代表允许JSON字符串强转。Frozen Core与数值expected不变。

## 11. 最终本地回归 / 候选发布状态

- Backend最终完整：3155 passed / 1 skipped / 11 warnings，458.92s；包含新增正式路由不存在性测试，CI同一wrapper、未deselect。
- Semantic Compatibility：819 passed，141 production backend files扫描。
- Golden：11 PASS / 1 manual Real baseline SKIP；不把SKIP计PASS。
- Frontend：11 files / 112 tests PASS；typecheck、lint、production build PASS。
- Persistence / LOCAL_DEV历史与报表 / Auth / 临时路由focused：291 passed / 1 skipped / 3 warnings。
- Alembic Fresh / M6.2八表Upgrade / 重复upgrade / FK完整性 / forward-only恢复与LOCAL legacy测试已实际执行。
- Architecture158 files、Repository Safety460 files、Ledger122 entries、Documentation Governance与diff check PASS；候选文档更新后Ledger、Documentation Governance、Repository Safety与diff check再次PASS。
- 真实Late工具离线1 PASS、41条检查；不是Real替代品。Real41单独记录。
- warnings原样保留：历史Alembic PK reflection与MSAL form_post建议；未过滤。
- Phase A / Final SHA及CI待产生，Settings.version=M6.2；本地PASS不代替远端exact-SHA CI。
