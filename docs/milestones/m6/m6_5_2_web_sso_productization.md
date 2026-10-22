# M6.5.2 — Web / SSO Productization

状态：M6.5.2 Web / SSO Productization FINAL COMPLETE（本提交自身 exact-SHA Full Validation、
Remote Audit、HEAD=origin/main、clean/shutdown 全部成立后生效）。Settings.version=M6.5.2。
用户于 2026-10-21 明确授权本阶段；不得进入 M6.5.3 / M6.6。

## M6.5.2_FIX2 — Persistence Readiness + Cloud UX Layout Closure（2026-10-22）

独立scope；Settings.version保持M6.5.2，不进入M6.5.3。fresh fetch后main/HEAD/origin/main为
用户指定4a19aa5基线且worktree/staging clean。首次fetch网络失败后重试成功，不继承旧CI。

根因A：Sidebar resource errors leaked into chat-main。History与Report各自在Sidebar资源区
显示compact单行状态和retry icon；主聊天不渲染资源错误。登录后异步summary不依赖模型选择，
资源failure不会阻塞Catalog、选择或Chat UI。

根因B：Composer popover anchored to variable-height wrapper。独立composer-anchor仅含
输入栏与两菜单，statusNotice在前、selection在后。统一320px bounded width/border/radius/
shadow/8px offset，数据左对齐、LLM右对齐；不根据文字高度计算。

根因C：Cloud Normal Product SQLite schema readiness missing。唯一check_persistence只读
revision与正式table metadata，验证DB可访问和artifact root可创建/写；旧或空DB显式
PERSISTENCE_SCHEMA_OUTDATED。native startup记录安全revision，health与Cloud status区分
configuration与persistence；Chat路由在服务/LLM/ExecuteQuery/Facts/Memory前fail closed。
允许的资源操作仍经原有principal/ownership/policy，readiness不赋权。

operator helper显式`--upgrade`调用现有Alembic forward migration，目标来自当前Settings，
不依赖ini默认值；支持自定义路径和特殊字符。无删库、重建或reseed，无startup自动迁移。
本机真实DB先SQLite一致性备份并完整性验证；副本copy/hash核对后升级并比较8表1024行
旧列内容摘要；随后真实DB升级到ab64d10e7f20并重复原列摘要、integrity与FK验证，全部PASS。
legacy资源保留local:legacy owner，不自动归给登录principal。

永久测试涵盖旧/空/head与缺表、artifact不可写、exact环境自定义路径/default untouched、
代表性Conversation/Memory/Snapshot/Report旧行保留与新owner/binding表可用。
failure-first后端645be674=6RED；前端be8b2218=5RED/51PASS；ef74981f=56PASS，
a3c618f1后端专项19PASS；前端全量488b5fd5=196PASS，Typechecka80e033f/Lint9a1e508a/
Buildc6af8bd9 PASS。外部Visual真实Chromium几何1280/390宽度、1/3/5行、两菜单等宽8px、
资源503主canvas不变PASS。synthetic仅辅助，不能替代本机Normal真实浏览器验收。
长证据目录下两报表邻近测试ToolExecutionError失败保留，短目录M652F2同测试通过，未改
validator/断言/timeout；M652F2是本轮test runner短路径别名，原备份仍M6.5.2_FIX2。

Microsoft当前官方[Fabric IQ合同](https://learn.microsoft.com/fabric/iq/connectors/fabric-iq-mcp)
fresh重验：delegated current-principal、RLS/OLS及只读消费保持；没有新权限、Provider或
事实链变更。[Alembic官方](https://alembic.sqlalchemy.org/en/latest/cookbook.html)支持显式
programmatic Config/upgrade。M6.5.3合同：Deploy→explicit migration→readiness→backend
start→health ready；migration ≠ application startup，仅路线不实施。

真实本地Normal报告暴露既有Artifact Governance仍按flat文件查找，误报正式principal目录。
69d5559f失败和4aca84e6永久RED保留；只读audit按registered owner匹配真实namespace，
未注册目录/嵌套目录/孤儿文件继续拒绝，symlink明确拒绝。4d0165fc专项26PASS、4df229a4
真实Artifact gate PASS；不删除或迁走真实产品报告。后端完整门在该最小治理修复后重跑。
1ef59f22完整后端3957PASS/1SKIP/22warnings；增加空文件DB用例后e22aa59a专项9PASS。
b5c6dcd4完整门3958PASS/1SKIP但既有Local MCP短TTL用例一FAIL，整轮FAIL保留；b053cdea
同例独立原命令PASS。未修改Local Provider、TTL、sleep、断言或timeout，完整门再次fresh重跑。
Semantic41eb5912=819PASS，Goldend95510dc=11PASS/1manualSKIP；Persistence/Cloud Runtime/
Failure Classification/Metadata Amplification/English Natural Query组合8f7a10fe=424PASS/1SKIP。
Securitydcc7e1c9、Architecture949130ef、Documentationbc70c5ce、Ledgercf83f742、
Localizationa3be8597 PASS；最终文档及staging后再核对治理。
最终diff发现selection响应会覆盖readiness提示，4dc35829永久四RED；统一status/selection/
link/new-chat/restore/resource mutation的API状态投影后bd4e4f8e邻近PASS。
c3979089旧源码完整门主动中止，不计PASS；owned process/temp均已清理，按最终源码重新运行。
不改Workspace service或factual authority；普通uvicorn已重启，真实产品流程独立重验。

最终后端04fe25ad=3959PASS/1SKIP/22warnings，runner temp_cleanup=true；最终状态响应邻近
bd4e4f8e=35PASS。无Local Provider/TTL/sleep/断言/timeout修改，先前失败与中止保留。

REAL_BROWSER_ACCEPTANCE=PASS；REAL_LOCAL_DB_REVISION=ab64d10e7f20；
FABRIC_TEST_MODE=false；POWERBI_MODE=fabric_iq。使用真实.env凭据、既有真实本地DB、普通
`python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`（仅关闭敏感access log）
与`npm run dev`。公开Normal operator flags仅在进程显式启用，Secret未修改；没有测试宿主、
Mock、synthetic runtime、test-only DB或allowlist dependency。最终代码重启后一次真实Admin
登录，未选模型时History/Report summary自动恢复；选择Online Retail II，指定总额和year
英文问题、正式Report、浏览器View/Download、refresh/旧History、en-US/zh-CN与Logout均PASS。
最新三正式快照均completed/real/deepseek/is_mock=false/Memory committed；只记录安全元数据。
真实backend-final.log中PERSISTENCE_UNAVAILABLE/RESOURCE_NOT_ACCESSIBLE/cloud_failure/ERROR
均0；既有MSAL warning保留。最终再次核对8张旧表1024行原列摘要、integrity/FK全PASS。
首次额外措辞`Generate a report with the Total Sales KPI.`出现SemanticInterpretationError/
VALIDATION_FAILED，ZERO Memory；截图原件保留。改用既有明确正式报告措辞后通过，并在最终
代码重启后的新登录会话完整复跑成功；未修订理解/事实链或隐去失败。
浏览器Microsoft账户页的控制读取timeout通过重新绑定及DOM读取恢复，不改认证配置。
真实截图、下载hash、geometry、native launch manifest与acceptance JSON均在外部RealBrowser。

M6.5.2_FIX2 FINAL COMPLETE仅在自身exact-SHA Full Validation、Remote Audit、
HEAD=origin/main、worktree/staging clean及owned shutdown全部成立后生效；不继承旧CI。
备份/迁移回执在外部M6.5.2_FIX2，自动验证及真实浏览器证据在外部M652F2。

## Initial Reality Audit 与 continuation

2026-10-21 `git fetch origin` 成功，main、HEAD 与 origin/main 均为
`4f031c688c49f96b6b73e73b8921c18e3464cf5e`，worktree / staging 空。
读取 AGENTS、Charter、CLAUDE、07/08/09、README/CHANGELOG、Error Ledger、ADR index、
ADR-020 及相关 Auth / ownership / Catalog 合同。既有 CloudWorkspaceService、native Auth、
IQ Adapter、ToolGateway 和 owner repositories 可复用。当前三个 capability 仅从 Test Policy
授予；原目录对全部候选做 Resolve/Schema，不能作为正常产品的大目录路径。
最终continuation重新fetch核对同一baseline，保留本轮已授权未提交diff；staging为空，
未reset/clean/覆盖成果。以下初始失败记录为本轮历史，最终fresh证据见后文。

## 授权与控制面设计

- 唯一部署能力边界为 `CloudProductAuthorizationPolicy`，由现有 Workspace Service 消费。
  Test Mode 仍委托 `CloudTestPolicy`，保留 allowlist 与三个独立 bool；普通产品模式不消费
  allowlist grants。正常 query 要求已验证 session/principal、精确资源和 server binding；
  external disclosure / persistence 另要求部署级 `ALLOW_EXTERNAL_LLM_DISCLOSURE` /
  `ALLOW_BUSINESS_PERSISTENCE`，两者默认 false，HTTP DTO 不接受这些字段。
- Normal bootstrap 不枚举资源、不执行 IQ。新的 workspace / resource metadata 分页接口使用
  当前 delegated principal、固定 Fabric REST paths；候选 key 与 continuation 为当前 session
  私有 opaque 值，不能授权业务执行。每响应至多 50 行，每请求至多两页上游 metadata；
  上游 page 最大 5,000，cursor 四个、candidate 2,000 个、TTL 300 秒，超界/未知 fail closed。
  搜索限于实际扫描 metadata，continuation / partial 明示剩余范围；individual share 不冒充全量。
- 显式选择后重新 GET 精确 Workspace/item，再通过 ToolGateway 调用既有 IQ Adapter。
  Report 入口从 Microsoft Report metadata 的 SemanticModel.Id 与 ReportMetadata.Id / Report
  citation 证明 exact model GUID，再通过 exact GUID Resolve 取得独立 Workspace identity；
  不能按名称、schema 相似度或 Report workspace 猜模型。真实 wire 与选择已 PASS。
- 当前 server binding 组合 tenant、principal、workspace、model、opaque key、schema fingerprint、
  source、generation、authorization epoch 和 proof 类型；模型切换仍创建新 conversation。
  历史 owner binding 仍由原 Repository 存储；不迁移用户数据库。
- selection、factual prepare、history/restore、report view/download 与 durable commit 重验当前访问。
  SQLAlchemy 原 owner `before_commit` hook 经官方 async driver bridge 复用同一 Workspace boundary，
  Microsoft 拒绝则事务回滚；非 Cloud / 旧 Test Mode 保留原验证行为。
- SQLite、filesystem、process-local sessions 仅 single-process；无 Redis / PostgreSQL / HA 承诺。

## Auth failure-first 与协议

新增 Auth trace 只接受固定事件枚举与 bool，不接受 token、code、cookie 值、claim 或身份字段。
事件覆盖 flow create、callback、cookie presence、state、consume、token exchange、ID verification、
account resolution、session creation、cookie emission、redirect 与 session lookup。

合成复现确认非 canonical origin 创建 flow 会导致配置 callback 主机收不到其 host-scoped cookie。
登录入口现在先跳转固定配置 origin，再创建 flow。单次用户点击、一个 callback 后 session=200
由自动化证明；这未证明最初人工首登401的历史根因。最终native首登trace和session200
已通过，真实证据与合成复现分层记录。
不使用重试登录掩盖问题，不放宽 state、nonce、PKCE、tenant、account 或签名验证。

实际代理复验曾暴露本轮回归：Vite 字符串 proxy 改写 Host，导致 origin guard 循环 302。
`b3febff7` 在真实 Vite→HTTP synthetic upstream 复现 Host 错误，改 `/auth` 为显式
`changeOrigin:false` 后 `009c55f3` PASS，实际入口恢复跳 Microsoft。
`Real/product-9faf32d1` 保留失败 receipt；修复后的 Admin 首次 UI 登录仅一个 callback，
cookie/state/consume/token/ID/account/session/cookie emission 均成功，随后 session=200。
预先无 cookie 的 HTTP 诊断另创建一个未使用 flow，不能算成第二次用户登录。
这证明本轮首登路径成立；未将最初人工首登 401 的历史根因写成已证结论。

保留 code-only GET/query callback：SameSite=Lax 适用于 cross-site 顶层 GET；flow 一次性，
state/nonce/PKCE 仍由 MSAL 与现有 Auth 验证，backend confidential exchange，callback 立即
302 干净 `/`，no-store / no-referrer，access log 去 query。token 不在 URL 或浏览器。
切 form_post 将涉及 cross-site POST cookie / CSRF 合同，不能为消 warning 机械修改。

官方重验（2026-10-21）：

- [Microsoft authorization code / PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [MSAL Python response mode](https://learn.microsoft.com/en-us/python/api/msal/msal.application.clientapplication?view=msal-py-latest)
- [OAuth Security BCP RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- [Current-principal workspaces](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/list-workspaces)
- [Semantic models](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/list-semantic-models)
- [Reports](https://learn.microsoft.com/en-us/rest/api/fabric/report/items/list-reports)
- [Fabric IQ](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)
- [Microsoft IQ tool reference](https://github.com/microsoft/skills-for-fabric/blob/main/skills/fabriciq/SKILL.md)
- [SQLAlchemy async event bridge](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-awaitable-only-driver-methods-in-connection-pool-and-other-events)

## UI Mapping / gate 状态

用户明确修订本轮 Design Gate：以当前 PowerBIAgent 已有 ChatGPT-Web 风格组件为第一参考，
直接复用 Sidebar、User menu、Settings modal、Composer +、search/popover/compact row。
无需等待外部 ChatGPT Web 链接；该用户授权覆盖最初参考访问阻塞。

| PowerBIAgent | 采用的现有模式 | position / spacing / icon / interaction |
|---|---|---|
| Sign out | 用户明确要求复用 Settings compact account row | 同一 account-menu class / padding / gap / 行高 / hover；LogOut 16px、默认同 stroke |
| Avatar | 用户明确要求复用既有圆形容器 | 登录前后 UserRound 16px；右侧姓名 / UPN 保留；无 Graph Photo |
| Workspace / Model / Report selector | 既有 Composer + → 数据与报表选项 | 同 menu-group / menu-heading / menu-option / filter；50 行一页；现有轻边框圆角；16px chevron、14px refresh；返回工作区、搜索、类型行与下一页 |
| Loading / partial / empty / error | 既有 menu-empty-state / Cloud status 文本 | 原位置及间距；无独立卡片；AbortController + epoch 忽略迟到响应 |
| Settings 数据目录说明 | 既有 Data & Models 文本行 | 无新图标按钮；Normal 说明从 Composer 浏览，不把 selected count 当完整目录数量；General → Language 不移动 |

## 本轮证据（全部 OFFLINE，不冒充 Real）

回执仅 `D:/AAA_Workfile/PBIAgentTest/M6.5.2/Acceptance/<run>`；缓存/temp 同 milestone 外置，
runner receipts 均记录 temp cleanup。原失败输出保留。

| Run | 结果与范围 |
|---|---|
| 960ef531 | 7 RED，Product Policy 模块尚不存在 |
| b7b754c8 | 7 PASS，独立 query / disclosure / persistence 与 revoke |
| 3b6f46f3 | 3 RED，canonical login origin / structured trace |
| e950a4af | Auth + native MSAL 邻近 51 PASS，10 条 form_post 建议 warning 保留 |
| 962f8da4 | Catalog paging 模块不存在，4 RED |
| 4a56051f | 3 PASS / 1 fixture FAIL，Report fixture 错发 SemanticModel type；修正 fixture，未放宽 validator |
| f95f9aff | Native product selection 接口尚不存在，2 RED |
| 8cc10623 | Product policy / lazy catalog / native selection 13 PASS |
| f13fb25d | 46 PASS / 6 legacy fixture FAIL：旧测试把 Normal Product 当永远执行关闭 |
| 2eb9d53a | 将旧拒绝测试显式设为 Test Mode，原断言保留；52 PASS |
| 354d6fb2 | 2 PASS / 1 RED，撤权后 durable write 原来仍成功 |
| 417dce91 | 29 PASS，commit 撤权回滚 + owner / resource lifecycle |
| 9a7214c3 | Report mapping 方法不存在，5 RED |
| f672db51 | Report mapping / IQ transport / adapter 97 PASS |
| 02fdcce1 | Product binding / policy / scalability / Report mapping / IQ 邻近 58 PASS |
| 915d62a4 | 首次 Full Backend：3852 PASS / 13 FAIL / 1 SKIP；12 个 synthetic factual fixture 动态 schema 与新 drift guard 冲突，1 个 forged key 错误分类顺序；仅 synthetic product 豁免动态 schema，native drift 负例保留 |
| 537fa790 | 八 Shape / year / isolation / native binding focused 56 PASS |
| 46fb5977 | CloudWorkspace 26 PASS，包括 normal lazy bootstrap、显式 Report candidate 绑定、重登后未选模型恢复 |
| b94e5820 | 8 PASS / 1 RED，history summary 跨 source mode 未拒绝 |
| 00ba8f41 | 修复 summary source mode，9 PASS；未选模型历史摘要全程零 IQ，Microsoft 撤权拒绝 |
| f41a6e9a | CloudAccountSettings 5 PASS，Normal 不声称 verified catalog count，切语言零重新读取 |
| 1fffc3d8 | Frontend lint PASS |
| 3007f60a | 17 files / 175 tests PASS，但另一个 worker 启动超时；整轮 FAIL，需独立完整重跑，未调低测试或改 timeout |

大目录 metadata=1,500，首屏=50，分页及搜索；选择前 Schema=0、IQ Resolve=0、ExecuteQuery=0。
正常模式测试不配置 Test Allowlist。所有 identity / HTTP / DB 均 synthetic，未读取用户 DB。

## 最终 correctness 与 fresh 验收

Report 实际 envelope 为单一text JSON，SemanticModel.Id、ReportMetadata.Id与独立Report citation。
failure-first26d1d07b为1RED/11PASS；专用identity normalization只读取这三个身份，不消费visuals/
filters/业务值。exact model GUID Resolve取得workspace，再沿用Resolve/Schema/binding。
focused Real selection200，Resolve3/Schema2/GetReportMetadata1/ExecuteQuery0；跨workspace、
缺失/错误Report/model/citation、upstream error均有负例。无UCI hardcode或事实envelope放宽。

HTTP body ClientDisconnect由所有Cloud GET/POST共享bounded读取转固定400；残缺body不进入
Service/Facts/Memory/resource mutation，async cancellation保留。d3ef4c0b四GET RED；
cc0c5c43=57PASS，最终邻近1b6b7438=54PASS。原stale/late/revoke tests保持。
IQ403清除adapter binding后status清除selection/increment generation；9a2f58ec RED、
6ccbc1d0=120PASS。Frozen factual boundary无变化。

Vitest fork原3007f60a/b93619bd在不同worker startup握手超时，涉事独立fork25PASS；
仓库最小改为isolated threads，正式npm test固定runner config loader。断言/expected/timeout/
覆盖不改，两worker并行cd52c39b=181PASS。最终overlapping gates17ca212a为180PASS/1UI
wait超时，机器可用内存约410MB；该轮失败保留，不当PASS。Semantic重叠run人工终止并保留
receipt；串行fresh正式npm test ac349296=18files/181PASS，无worker启动超时。

最终native Real receipt只含boolean/count/hash，位于仓库外Real/product-9faf32d1：

- final-product-receipt：Normal FABRIC_TEST_MODE=false、无allowlist、一次native Admin Login/
  session200；Workspace search/bounded page、Semantic Model及Report exact mapping selection。
  SCALAR/GROUPED/Report completed、factual Memory commit；zh/en/zh零新增IQ/ExecuteQuery，
  user_message verbatim、Memory与factual hash不变；Report view/download两locale200。
  History restore200/零ExecuteQuery、forged workspace/candidate403、stale409；模型切换新
  conversation且无旧factual Memory。Real Workspace只有一页，真实多页不冒称PASS，synthetic覆盖。
- final-restart-receipt：backend restart后一次native relogin；未选模型可读取owner History/Report
  summary且零IQ；restore/view/download200，HTML hash与重启前一致，ExecuteQuery增量0。
  logout200，session/history/report/view/download全部401。
- 英文GROUPED欠确定filter field返回clarification，补全英文一次SemanticInterpretationError；
  RATE_LIMITED原件也保留，不计PASS。GROUPED正式正例沿用既有明确中文输入，不限制输入语言，
  不改变Understanding/Grounding或用模型hardcode补意图。

大目录backend1500/frontend1200 metadata，首屏50、分页、搜索、取消、迟到response忽略、
bounded调用；explicit selection前Schema=Resolve=ExecuteQuery=0。Normal/Test policy边界均有负例。

| Final fresh run | 结果 |
|---|---|
| f8eadecc | Full Backend3904PASS/1SKIP/15既有warnings |
| f865313a | Semantic819PASS |
| 5b8807ad | Golden11PASS/1manualSKIP |
| ac349296 | 正式npm test18files/181PASS |
| df2c3114 | Auth51PASS、Catalog31PASS、Product Authorization31PASS |
| 82a8cbdc | UI Localization48PASS |
| 642269a1 / d4db6dd4 / fffd09a1 | Typecheck/Lint/Production Build PASS |
| db2735e0 | Security/Architecture/Documentation/Ledger/Artifact/Localization/diff PASS |

Final diff分类A Auth/B Product Authorization/C Catalog binding/D frontend/E tests/F docs，G=0。
Normal不依赖allowlist，Test Mode保留；token仅Auth/Transport，无eager schema/name mapping/
model hardcode/weakened validator/Frozen factual drift/M6.5.3或M6.6 implementation。
12-row/N+1/8-column、relationship cardinality CONTRACT_GAP、Test B deferred→M6.6保留。

## Release closure

首个产品提交b195612a7fb1d0b71b9e8750d344cbb0aec1f9ca的CI39558741067失败：
Artifact Governance → local_state_missing。该目录被Git忽略，clean checkout无runtime state；
原Security/Ledger/Architecture/Documentation通过，后续gates skipped，不继承为FINAL证明。
按用户明确forward-fix，仅修artifact审计语义：absent state继续source-tree扫描，无artifacts则
PASS；existing valid state PASS，partial/malformed/unauthorized/orphan/pending cleanup/ownership
residual仍FAIL。永久测试failure-first a0b54ab2为3RED/13PASS，fixture与owned测试目录分离；
无CI mkdir、无validator降低、无M6.5.2产品功能修改。新提交仍须自身完整exact-SHA CI。
治理专项da84aaf3=16PASS；fresh Artifact674ece92、Backend adb0ecb8=3908PASS/1SKIP/
15既有warnings、Semantic43edefc4=819PASS、Golden6855c79d=11PASS/1manualSKIP；
Auth/Catalog/Product7f05c90e=51/31/31PASS、治理0a77fc1e PASS、正式npm test2bafe96e=
181PASS、Typecheck2d53e57a、Lint422a4436、Build73477f55、UI Localization81f065af=48PASS。
中文forward-fix提交`M6.5.2_修复无运行状态的CI产物治理`，仍按自身CI/Audit/clean/shutdown生效。

全部Real与fresh gates通过后Settings.version=M6.5.2、07/08/09/README/CHANGELOG收口。
中文提交`M6.5.2_Web与SSO产品化`，fetch无drift、whitelist staging、ordinary push main。
FINAL COMPLETE仅在自身exact-SHA Full Validation、Remote Audit、HEAD=origin/main、staging空/
worktree clean/owned shutdown全部成立后生效。自身SHA/CI/remote receipt在仓库外，避免循环引用。
完成立即STOP。下一阶段仅记录M6.5.3 VM Remote Deployment & Internal Pilot与M6.6 Enterprise
Production Readiness Seal；不实施。

## M6.5.2_FIX — Cloud Product Runtime & Pilot Readiness Closure

2026-10-21 用户独立授权；baseline `ef6f754fb619ef832d002aa7f4a8587f233cef83`。
Cold Start fresh fetch/main/HEAD=origin/main/clean/staging empty；Settings.version 保持 M6.5.2。
本节为后续 FIX，前文原验收为历史，不继承其 CI 或英文/配额结论。
本地门与Normal Product Cloud Real已完成；FINAL COMPLETE仅按下述自身exact-SHA
Full Validation、Remote Audit、clean/shutdown条件全部成立后生效。

### Reality Audit / failure-first

- templatesLoading 被传给 loadingConversation；selection boolean 将未知 Chat503 误报模型
  不可访问，所有 error 显示 reload-model；History/Report Promise.all 污染主链。
  024fc0e7=8RED/26PASS，0851f6f0=34PASS；后续独立 loading/retry/恢复回归一并全量。
- select/bound_projection/templates 重复 REST/Schema；任意 REST 失败清 selection。
  f5911ecc=4RED/10PASS；c0b25501 typed failure/trace RED；8cf0e76d 链接 parser 缺失 RED。
- Real DeepSeek english_before 的纯英文 GROUPED/RANKING draft 正常，但具名成员半年
  aggregate 错为 SCALAR；通用 grammar guidance 后 english_after 为 FILTERED_AGGREGATION。
  不写入 UCI/Total Sales 特例，不改 evidence validator、Grounding、日期/成员 authority。
- b15d008b 证明投影失败后同消息成功仍残留 failed；成功清除此状态，Facts 不变。
  首轮 native body 中断另源于验收 observer 的 audit rename 文件锁，不冒充产品根因。
  observer 后续写回执异常不影响产品请求；runtime-closure 原件保留。
- 首轮 Backend85dfd111=3914PASS/17FAIL/1SKIP，未计 PASS。模板投影先放在 service status
  破坏旧 equality，改为 API selection 专用响应；exact403/404 拒绝仍失效。
  SCHEMA_UNAVAILABLE 按当前用户合同保留 binding，原失败请求仍 raises；对应旧断言增补
  preservation 分支，未将失败改为成功或删除负例。mismatched exact identity 仍撤销 proof。
  report_atomic_store_failed 在长本地测试根复现；短独立 D:/PBIAgentTest 的 f92372ba 中
  report tests 恢复通过，未改 report/storage authority 或 expected。未读/移动用户 DB。
- 初次 typecheck e7925221 缺 link CatalogOption.description，补齐后 build/typecheck PASS。

### 安全合同与官方能力重验

仅复用 Adapter/Service/Repository/ToolGateway，新增 ContextVar operation proof 容器。
proof key 含 service/adapter identity、session、validated principal/epoch、exact workspace/model、
generation；Schema 验证 key/fingerprint/epoch。finally 失效清空，子任务继承的已结束 scope
也不能再用。每个 factual HTTP request fresh REST/Schema；当前 operation 内 prepare/Core
schema/template/durable lease 复用 proof。session/owner/policy/epoch/generation 与 late/stale
checks 每次仍执行，无 global 或跨请求 permission cache。

selection 同响应返回 template projection；独立 template API 仍 fresh IQ Schema。
Report metadata 证明 exact model GUID，Resolve 该 GUID 独立证明 Workspace；不立即重复
Resolve 同一 model URL，Schema 仍验证 exact artifact。12 rows/N+1/8 columns 不变。

structured trace 仅固定 request_id/operation/stage/failure_code/retryable/provider/HTTP category。
stage 覆盖 catalog_rest/resource_verify/iq_resolve/iq_schema/iq_execute/llm/persistence/
presentation/internal；包裹的 IQ 原因不被 persistence 覆盖。无 exception repr、credential、
prompt、DAX、rows、schema 或 PII。HTTP category 为 API 响应类别，不冒充 Microsoft 原始状态。
未知异常明确 INTERNAL_FAILURE，LLM/Persistence 分别保留专属公开 failure code。

2026-10-21 重读官方合同：

- [Get Semantic Model](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/get-semantic-model)：
  caller 需 item read；固定 exact item path，严格 ID/type/workspace。直接 item proof 不再
  额外要求 Workspace membership GET。
- [Fabric IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)：delegated caller
  原权限与 RLS/OLS 保留；selector 不授予权限，Schema/result 合同不变。
- [Get Dataset](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-dataset)：可按 caller
  permission 访问其他 Workspace model；本轮未增加第二 data plane 或 auth scopes。

optional link entry 是用户对 ADR-020 第5条 discovery UX 的明确补充；主目录保留，不要求普通
用户必须输入链接，不宣称列出所有 individual-share。仅 HTTPS exact allowlisted Microsoft host
与带 Workspace GUID 的 reports/datasets/semanticmodels 路径；foreign host、credentials/port、
未知 query、fragment、malformed identity 拒绝，不 fetch URL。Report mapping 与 model exact
proof 独立；前端无 permission authority。short/share links、groups/me 或缺 exact identity 的
URL 不猜，Microsoft REST/IQ 无法证明即 fail closed。individual-share 专用 principal/resource
未提供，synthetic/官方合同覆盖，Real Pending 保留。

### Fresh gates（本地，不继承历史）

| Run | 结果 |
|---|---|
| 11fdc76d | Backend3947PASS/1SKIP/15既有warnings |
| 07af082f | 补MSAL网络清理回归后Backend3949PASS/1SKIP/17warnings；新增两例相同MSAL提示，未隐藏 |
| ee126006 | Semantic819PASS |
| cf3ea2f0 | Golden11PASS/1manualSKIP |
| 5e1c69c3 | Frontend19files/191PASS |
| 16238a20 / 3cd68aa7 | Typecheck/Build、Lint PASS |
| e4321b2d | Security/Architecture/Documentation/Ledger/Artifact/Localization PASS，最终文档后须重跑 |
| b32bc272 | 更新FIX文档后的六项治理门PASS，后续文档变更仍须重跑 |
| c8efd0c8 | Auth51/Catalog31/Product39/Runtime43/Failure13/Amplification31/English91 PASS |
| f4c19717 | 最终代码后重跑：Auth53/Catalog31/Product39/Runtime43/Failure13/Amplification31/English91 PASS |
| 68eb124f | 最终代码后Golden11PASS/1manualSKIP |
| 3a016a50 / 98eb6835 / cacbc626 | 最终代码后Typecheck/Lint/Build PASS |
| 7a1d9464 | 补Real边界与working diff审计后六项治理门PASS |
| 72622c14 | 最终代码后Semantic819PASS |
| 8e7aac3b | Frontend18files/157PASS但CloudWorkspace线程启动timeout，整轮FAIL；原件保留，原命令独立重跑，不调timeout/断言 |
| 36e5e6f8 | 原完整Frontend命令独立重跑19files/191PASS，无代码或validator修改 |

runner/cache/temp/receipt 均在仓库外 PBIAgentTest；早期长根
D:/AAA_Workfile/PBIAgentTest/M6.5.2FIX，最终本地门为短独立 D:/PBIAgentTest/M6.5.2FIX。
不迁移旧证据或用户 DB；Real 自建 synthetic host DB 的 ownership 明确。

### Real / release（仅按自身发布门生效）

Normal FABRIC_TEST_MODE=false，无 allowlist；final-native 为 native Auth/IQ/DeepSeek。
登录前网络 ERR_CONNECTION_CLOSED 与 Auth initiate UPSTREAM_UNAVAILABLE 原件保留，均无
callback，不计首登成功。恢复后浏览器选 Admin，native flow/token/ID/account/session 均通过。
normal-product-first-failure 保留最终六条中的失败：前五条SCALAR×3/GROUPED/RANKING均
completed/Memory commit、原文不改、zh/en投影与零新增IQ、每次Chat Schema1；第六条France
H1 2011为clarification_required/ZERO commit，原因是模型没有default temporal role，非
English evidence或shape validator错误。独立Understanding实测generic guidance后该问题
draft为FILTERED_AGGREGATION，但draft不能授予canonical date authority。

现有Grounding明确禁止即使单一typed date也自动推断默认日期；负例
test_missing_metadata_never_defaults_single_measure_or_date保留。用户随后明确批准通过现有
operator registry声明Sales[Date]。date-approved宿主先fresh exact REST/Resolve/Schema，
核对typed field、exact workspace/model/resource fingerprint与语义上下文fingerprint，再写
仓库外operator配置，并由既有SemanticCatalogBuilder校验。两份fingerprint各按原合同
使用，不混用。没有修改Grounding、registry解析器、evidence validator或生产模型特例；
新key/fingerprint不匹配仍fail closed，不把单个模型角色变成通用默认日期。

date-approved/english-product-final中的六条纯英文均completed/Memory commit且为正式
SCALAR×3/GROUPED/RANKING/FILTERED_AGGREGATION，原文保持、zh/en Assistant投影语言正确、
每次Chat Schema1、locale ZERO IQ且Memory immutable；Report generate/双语view/download、
History restore/read、stale/forged均PASS。该长流程末尾switch使用开场5分钟前的Catalog
selector，正确403使整轮原回执FAIL，原件保留，不计整轮PASS或延长TTL。

date-approved/adjacency-product-final独立fresh回执17项PASS：重启后原生Admin重新登录，
owner History/Report恢复与读取、fresh Catalog后switch200/新conversation/空Memory、
stale/forged拒绝、logout与五类protected resource401；该阶段ZERO ExecuteQuery。
这是修正验收selector生命周期后补验失败检查，不修改生产授权或expected。

remaining-product-final 独立回执PASS：中文问题原文+英文Assistant、既有单KPI模板生成、
zh/en view/download、读取零ExecuteQuery、History restore/read、stale/forged fail closed、
模型切换新conversation/空Memory、logout及五类protected resource401。
所有调用使用浏览器原生登录产生的session，在同一宿主正常HTTP endpoint执行；未注入
Auth/IQ/LLM mock，未读取用户持久化DB。individual-share专用资源仍Real Pending。

宿主shutdown另暴露MSAL get_accounts/remove_account可能触发instance discovery网络失败，
本地cache purge不能被它阻断。93fbb58d两例failure-first RED，988a801a因新trace事件未注册
仍失败；补固定事件allowlist后07af082f完整后端PASS。finally始终清cache/account_id，
仅吞已知RequestException并输出固定安全event，不降低认证验证或记录异常内容。
临时429/503保留model/conversation/catalog由failure-first注入矩阵证明；未主动制造
Microsoft限流。individual-share专用资源按用户允许保留Real Pending，不伪造真实分享PASS。
M6.5.2_FIX FINAL COMPLETE仅在本提交自身exact-SHA Full Validation、Remote Audit、
HEAD=origin/main、clean/shutdown全部成立后生效，最终自身SHA/CI回执保存仓库外。
验收owned backend/Vite已正常shutdown，8000/5173无listener；原生logout界面截图在仓库外。

### 基线到M6.5.2_FIX最终diff审计

基线为用户指定ef6f754fb619ef832d002aa7f4a8587f233cef83；审计时fresh fetch无remote drift，
42个授权文件按白名单staging，远端须再比对文件清单。A runtime correctness：CloudWorkspace
loading、侧栏隔离、presentation
重试恢复及MSAL本地销毁。B failure handling：operation上下文、公开typed code、bounded trace。
C proof dedupe：workspace service、Fabric IQ Adapter、template schema projection；D English
semantics：仅Understanding通用prompt；E shared-resource discovery：严格URL parser、catalog
selector、API与Composer compact UI；F tests：negative/回归及四个CI门；G docs：07/09/
CHANGELOG/本milestone/Error Ledger；H accidental drift=0。

Settings.version保持M6.5.2。未改TurnPipeline、Grounding、CanonicalQueryPlan、DAX builder、
ResultInspection、VerifiedFactSet、Memory/Report factual authority或requested/observed/horizon。
未增加Test Allowlist依赖、permission长期cache、第二事实链、模型专用language逻辑或RLS/OLS
放宽。旧SCHEMA_UNAVAILABLE测试分支按本轮明确合同修正为保留binding，但当前失败仍raise；
access denial和forged identity的negative断言继续保留。

保留 cardinality CONTRACT_GAP、Test B OLS deferred→M6.6、single-process/SQLite/filesystem/
in-memory coordination、refresh freshness UNKNOWN；不进入 M6.5.3/M6.6。
