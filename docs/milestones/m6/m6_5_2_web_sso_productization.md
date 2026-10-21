# M6.5.2 — Web / SSO Productization

状态：M6.5.2 Web / SSO Productization FINAL COMPLETE（本提交自身 exact-SHA Full Validation、
Remote Audit、HEAD=origin/main、clean/shutdown 全部成立后生效）。Settings.version=M6.5.2。
用户于 2026-10-21 明确授权本阶段；不得进入 M6.5.3 / M6.6。

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

全部Real与fresh gates通过后Settings.version=M6.5.2、07/08/09/README/CHANGELOG收口。
中文提交`M6.5.2_Web与SSO产品化`，fetch无drift、whitelist staging、ordinary push main。
FINAL COMPLETE仅在自身exact-SHA Full Validation、Remote Audit、HEAD=origin/main、staging空/
worktree clean/owned shutdown全部成立后生效。自身SHA/CI/remote receipt在仓库外，避免循环引用。
完成立即STOP。下一阶段仅记录M6.5.3 VM Remote Deployment & Internal Pilot与M6.6 Enterprise
Production Readiness Seal；不实施。
