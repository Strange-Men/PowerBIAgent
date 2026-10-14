# M6.4 — Cloud Product E2E（阶段已发布，FINAL NOT READY）

当前2026-10-14独立[M6.4_FIX](m6_4_fix_engineering_closure.md)修复资源/隐私拒绝/合成链/文档偏移，
自身CI与Remote Audit生效后工程COMPLETE；不等于M6.4 FINAL。Settings.version=M6.3，native IQ fail closed。
当前技术决策见[有界比较](m6_4_solo_contract_decision.md)。下文保留各旧轮原始记录，均属历史时间状态。

日期：2026-10-13。用户已批准原 M6.4 scope；Settings.version 仍为 M6.3。
M5 FINAL / Frozen Core 继续有效。此文件是本轮设计与分层证据，不替代 07/08/09。

## Reality Audit / 临时 Cold Start 校验

本地初始 main、HEAD=9eaf55f2c4e3f7e12bde5254de31e85532d8d9d6，worktree/staging clean。
本轮两次有界 fetch（默认、单次 HTTP/1.1）均连接重置；DNS 解析成功，GitHub HTTPS 443 探测超时。
GitHub 连接器重新读取 main，远端 SHA 与本地 HEAD 一致。用户明确批准此临时方式仅用于本地开发与测试；
不修改 AGENTS 或长期 Git 规则。成功 fetch 并确认远端基线未前进之前禁止 Commit / Push / Final Seal。
基线 exact-SHA push CI38278945986 completed/success，Full Validation (Windows) 全部 23 steps success；
这是基线证据，不是 M6.4 CI。

本地回归完成后又做一次25s预算内fetch，git fetch origin返回0；
main / HEAD / origin/main与连接器main均仍为上述基线SHA，staging为空，仅本轮白名单改动。
这是当时的成功fetch记录。最新恢复执行时两次有界fetch再次失败（默认连接重置、HTTP/1.1连接443失败）；
连接器fresh main SHA仍等于原基线，本地main/HEAD/cached origin/main一致、staging为空，仅本轮16项改动。
网络尚不稳定，提交/推送前仍须fresh fetch成功且基线未前进。当前没有Commit/Push/新增CI。

## 先行文档修复

- Charter 十八节：旧“M6 尚未实现”改为 M6.1/M6.2/M6.3 Security COMPLETE、M6.4 获批开发、数值 P1 未解决；
  文末不再保存旧 Settings.version=M6.0 / M6.1 READY，仍委托 07/08/09。
- 08 M9：补齐同比/环比、异常、贡献度、下钻、根因及后期受控 DAX/语义模型/PBIR 修改；全部标为后续未实施，
  原 Draft → Preview Diff → Validate → User Approval → Apply → Verify → Rollback 保持。
- 修改后 Documentation Governance PASS；git diff --check 无错误，Git 提示已有 LF/CRLF 转换政策。

## Microsoft 官方重验（2026-10-13）

- [Fabric IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)：delegated-only、固定 selector、
  runtime tools/list authority、RLS/OLS；默认 250 行、embedded CSV 仍可能截断。
  本次页面仍不足以证明 Int64 JSON 字符串编码合法性或完整性信号；不得以通用 JSON 惯例作证明。
- [Workspaces](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/list-workspaces)：current-principal、
  delegated Workspace.Read.All、continuation、429 Retry-After。
- [Semantic models](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/list-semantic-models) 与
  [Reports](https://learn.microsoft.com/en-us/rest/api/fabric/report/items/list-reports)：Viewer、递归文件夹、分页。
- [Fabric authentication guidance](https://learn.microsoft.com/en-us/fabric/workload-development-kit/authentication-guidelines)：
  列 workspace 的具体 scope 为 https://analysis.windows.net/powerbi/api/Workspace.Read.All。
  仅使用 delegated read scope；新增 consent 必须用户/组织 operator 完成，不自动改租户。

## P0 边界 / 本轮实施合同

1. Catalog 是独立 Service / REST Transport；Data Plane 仍经 ToolGateway → FabricIQPowerBIAdapter。
   只 GET 固定 Fabric v1 workspace/semanticModels/reports 路径，无 scanner、管理员代读、fallback 或写操作。
2. 构造时绑定 AuthService 已验证的 session/principal；每次 token、await 前后重验。
   Auth 只允许既有 IQ scopes 或精确 Workspace.Read.All scopes；token 不进入 DTO/日志/Memory。
3. continuation 仅采用服务响应 token 重建同源、同路径请求；拒绝恶意 continuationUri、循环、越界分页。
   429/timeout 有界处理，局部失败只降级为 PARTIAL；不能冒充 EMPTY。
4. Catalog candidate 无权限 authority；每项由当前 principal 重新 Resolve + Schema 后才分配 opaque key。
   shared seeds 仅 server/admin 配置，同样逐项验证；显示名称过滤控制字符并限制长度，无 GUID/URL 外泄。
5. 完整覆盖只限声明的 workspace membership + configured seeds；未配置的 individually-shared 模型覆盖始终未知。
   即使 scope 内枚举完成也明确 PARTIAL，不声称企业全量目录。零候选但覆盖未知不能标 EMPTY。
6. session/epoch 切换不复用 transient refs；授权失败沿用 M6.3 立即清理与重新登录策略。
   生产业务 API 在事实正确性和 Real 安全门槛通过前保持关闭。
7. 先 failure-first synthetic negative tests；Real Microsoft 与 synthetic 分层记录。
   不迁移或读取用户现有 DB/报表资产，不改 Frozen Core、QueryShape 或模板。

## 本地实施 / Failure-first 与 fresh gates

Catalog Transport/Service先新增失败reproducer，再实现最小只读边界；新增跨用户Adapter误配负例先RED，
修复构造时Auth实例/session/principal一致性后，4个新增测试文件49 PASS。
Transport/Auth/MSAL focused 68 PASS；Catalog与原生Adapter/cell regression 242 PASS。
上述全部为synthetic/OFFLINE，不是Microsoft Real。

2026-10-13本地fresh检查（当前未提交工作区）：

| 检查 | 结果 |
|---|---|
| Repository Safety / Error Ledger / Architecture / Documentation Governance | PASS；468 files / 最新125 entries / 160 production Python files |
| Full Backend | Catalog初轮3204 PASS / 1 SKIP / 12 warnings；保护后重跑3208 PASS / 1 SKIP / 12 warnings（418.63s） |
| Semantic Compatibility | 819 PASS；143 production files scanned |
| Golden | 11 PASS / 0 FAIL / 1 SKIP（manual Real baseline） |
| Frontend首轮 | 105 PASS，但1个worker启动timeout，整轮FAIL；未改测试或断言 |
| Frontend有界单worker重跑 | 112 PASS（11 files）；Typecheck/Lint/Build PASS；Build保留plugin timings提示 |
| 仓库外只读审计边界 | 初始9 PASS；用户发现临时login链接问题后新增负例先1 FAIL/9 PASS，修复后10 PASS；均OFFLINE |

Backend warnings完整保留：3条既有Alembic临时表主键声明SAWarning，9条MSAL建议form_post提示
（其中1条来自本轮新增scope测试）。不因warning修改迁移、Auth协议或隐藏日志。
临时审计入口在仓库外，运行时仅native Auth + Catalog + 固定synthetic fixture三条只读查询，
保留wire/SDK primitive类型、runtime工具合同与完整性字段，不保存token/cookie/raw payload/真实结果值。
原Viewer A身份与synthetic预期映射独立于查询返回；普通用户不能提交DAX/URL/ID/身份。

## Cloud完整性边界审计（本轮Synthetic）

仓库外`test_cloud_completeness_audit.py`：3 PASS / 1 FAIL。排名对truncated拒绝；分组不生成extrema；
即使观测月份齐全，bounded trend在truncated时仍为PARTIAL。失败reproducer证明直接调用现有
SalesReportDataAssembler能接受truncated分组结果，而SalesReportSpecBuilder不传递该标记。
这是接线风险，不能用旧通用Core的局部结果披露能力当作Cloud报表完整性保证。

不修改M5 Frozen Core。新增server-owned`FabricIQAdapterFactory.create_product`，
复用同一Adapter/Auth/ToolGateway链；产品执行和normalize_result均在向Core交付QueryResult前
拒绝truncated（CONTRACT_DRIFT）。普通`create`保留审计合同，可返回显式不完整结果供只读诊断，
不能用于未来正式产品接线。failure-first产品负例先3 FAIL / 1 PASS，再实现最小边界。
当前normalizer无充分完整性authority，所有Cloud产品查询仍被该保护阻断；这不是完整性问题已解决。
正式API仍关闭，direct Core失败reproducer保留，没有反转expected、放宽validator或新建事实链。
产品完整性保护与Catalog/原生Adapter/cell focused回归：254 PASS / 1 MSAL warning（11.24s）。
上表3204条Full Backend发生于此保护之前；保护后完整回归3208 PASS / 1 SKIP / 12 warnings。
完整输出保存在仓库外PowerBIAgent_M6_4_Acceptance/local-full-backend.txt。

## 临时审计登录链接修复

用户截图`/auth/login?return_to=/auth/m64-audit`返回AUTH_FORBIDDEN；AuthService.start仅允许return_to=/，
发生在Microsoft跳转之前，与Workspace.Read.All是否配置无因果证据。
仅修仓库外链接为`/auth/login`，页面注明登录完成后切回审计页；10条OFFLINE边界回归通过。
已重启本人创建的临时进程，浏览器新链接核验通过；不修改Auth白名单、CSRF或租户配置。
旧错误URL刷新仍会被拒绝，这是安全边界正常生效。错误总账新增ERR-64-001/002。

## 当前交付对照（PARTIAL / BLOCKED，非 Final Seal）

### Viewer A首轮Real与临时接线修复

2026-10-13 02:01:53 UTC：Viewer A已真实Microsoft登录，原生Catalog PASS：可访问6个模型，
workspace_scope_complete=true、individual_share_coverage=configured_seeds_only、inaccessible_count=0，
整体status=partial。只证明当前principal和声明覆盖范围，不表示企业目录完整。
安全投影证据位于仓库外runs/20261013T014303Z-c7a0cc8e4042472c8c7d79feef1d3e47/audit-001.json。

count/scalar/grouped三条查询均在ExecuteQuery之前失败：临时harness只设置allowed_tools，
遗漏allowed_semantic_models，UserContext保留默认mock模型白名单。没有QueryResult，不能据此认定新上游故障。
runtime ExecuteQuery tools/list metadata SHA256为23a80c87654574ad3cffb3e5cb40443df7d73bf2ba379b5e5bbf69a9acbc46c6；
未提供outputSchema，也无充分数值编码或完整性合同。

新增覆盖实际native_probe→ToolGateway→Adapter的OFFLINE回归先2 FAIL；仅传入已Resolve/Schema验证的
当前opaque ref.server_model_key后，与原HTTP边界测试合计12 PASS（11.93s）。数值字符串负例仍被CONTRACT_DRIFT拒绝。
原生网关与模型白名单策略未改。旧Real失败证据保留；已重启本人创建的临时服务加载修复，
内存会话不持久化，等待Viewer A重新手动登录并运行只读检查。该停点来自真实人工登录依赖。
production backend/frontend检索无临时审计路由、固定fixture query或仓库外harness导入；运行中清理结果见下节。

### 修复后Real复验：数值与完整性前置门槛未通过

2026-10-13 02:12:54 UTC，用户重新登录Viewer A并运行审计，证据保存在仓库外
runs/20261013T020906Z-8d579b58ddbc48e7b39bfdaddc3f632d/audit-001.json。
Catalog再次PASS（6个模型、workspace scope complete、整体PARTIAL）。三条固定查询均到达ExecuteQuery，HTTP200。

| 固定查询 | HTTP wire与SDK类型 | 验收 |
|---|---|---|
| COUNTROWS | Int64列，int单元格 | 独立synthetic值匹配；仅值/类型PASS，truncated=true |
| Total Sales标量 | Int64列，str单元格 | FAIL CONTRACT_DRIFT |
| Region分组Total Sales | String/Int64列，str/str单元格 | FAIL CONTRACT_DRIFT |

三条query的payload/execution/table均无complete/truncated/isTruncated/hasMore/totalRows等完整性字段；
runtime ExecuteQuery无outputSchema；未嵌入CSV。HTTP200、少量返回与独立synthetic预期不能证明正式查询完整。
故原生Adapter继续truncated=true，产品create_product在Core之前拒绝；Completeness FAIL / authority UNRESOLVED。
未强转数字字符串、修改业务模型或expected，也未放宽M5 ResultInspection/VerifiedFactSet。

同日再次检查Microsoft Learn及Microsoft fabriciq skill，仅得到行数上限与可能截断的说明，
仍无本端点Int64字符串编码合法性或可采信完整性信号的合同。
检索到的Graph GQL编码和另一个Arrow DAX endpoint属于不同API，不能移植合同或自动新增Provider。
当前已经完成用户登录依赖；继续正式产品接线将越过原Prompt要求的数值/完整性先决条件。
需要Fabric IQ本端点的官方合同证据/服务修复；若改换执行Provider则必须另行明确批准范围，不能由当前授权推导。

### 临时设施卸载与原生边界恢复

Real证据保存后关闭本人创建的临时审计进程，恢复同配置native create_app；未关闭用户Vite进程。
仓库外run_native.py不导入fixture、harness或诊断模块；真实session不提取、不跨重启持久化。
native-cleanup-evidence.json：8项PASS，明确区分运行中HTTP检查与隔离OFFLINE有效session检查：

- 运行中backend与Vite代理GET /auth/m64-audit均404；GET产品API及/auth/session未登录401。
- 未登录POST先被native CSRF拦截401，不能单凭此状态证明路由不存在。
  首次清理脚本将其预期设为404、把未登录/auth/session预期设为200而FAIL；已核查既有代码，未改生产边界。
- 隔离native app的synthetic有效session+CSRF下，GET审计页与POST probe均404、产品API403；路由集合没有m64路径。

临时审计路由已卸载，仓库外源文件与历史失败/安全证据保留，不进入Git或production导入。
脱敏支持草稿fabric_iq_contract_support_note.md已准备；Agent未向第三方发送消息或资料。

以下表为恢复开发前的历史审计切面，不能替代下方当前模块状态或新增源文件清单。

| 原验收项 | 恢复前历史状态 |
|---|---|
| Cold Start / 基线 | main@9eaf55f；初始clean；fetch曾成功、最新两次失败，连接器fresh SHA仍相同；提交前须成功fetch |
| 两处文档修复 | 完成；治理PASS；前后内容见上节与Git diff |
| 文件与架构 | 5个production文件、5个新增test文件、6个文档/ledger；共16项本地改动；M5 Frozen Core未改 |
| 数值P1 | 修复后Real scalar/grouped均已执行，wire/SDK Int64配str，FAIL CONTRACT_DRIFT；官方合法编码合同仍UNRESOLVED |
| Completeness | Real无充分完整性信号，FAIL/UNRESOLVED、truncated=true；合成3 PASS/1 FAIL揭示直接报表路径风险，产品Adapter保护保留 |
| Catalog | Viewer A Real PASS，6个模型可访问；workspace scope complete，individual-share仅configured seeds，整体PARTIAL |
| ENTRA正式API | 保持fail-closed；未接通业务服务 |
| Cloud UX | 未接通；临时仓库外审计页不是产品UX |
| 浏览器Query/Report E2E | NOT_TESTED；临时login链接修复不计作Cloud产品E2E |
| A/B、RLS/OLS、Late Response | native既有自动化回归通过；本轮Microsoft Real矩阵NOT_TESTED，不继承旧阶段PASS |
| LOCAL_DEV / M5 | 自动化Full Backend、Semantic、Golden与前端回归通过；Local Real DeepSeek+MCP本轮NOT_TESTED |
| 本地与CI | 见上表；仅基线CI已核验，尚无本轮exact-SHA CI |
| Commit / Git | 未Commit/Push；staging为空；main保留本轮16项已授权未提交改动 |
| 临时设施 | 审计进程已关闭、native恢复；8项清理检查PASS，临时路由不存在；证据保留仓库外 |
| 未解决 / 跳过 | 数值编码、完整性authority、正式接线、Cloud UX和Real产品矩阵；Backend 1 SKIP、Golden 1 SKIP分别保留 |
| M6.4结论 | 本地PARTIAL；Real/产品验收BLOCKED，Settings.version=M6.3，发布NOT READY |
| M6.5交接 | 不启动、不实施；仅记录待M6.4正式验收后另行授权 |

ACTION REQUIRED：登录/consent停点已完成。当前需要Fabric IQ ExecuteQuery本端点可核验的数值编码与完整性合同
或服务修复；如需改换执行Provider，须另行批准具体范围。现有授权不允许越过这一架构/事实前置门槛。
不需要重复登录、配置Workspace.Read.All或发送凭据。
正式产品开通与最终单SHA提交/CI仍等待原M6.4前置门槛通过。

## 恢复开发前历史验收

数值 P1 / 完整性：UNRESOLVED；严格 CONTRACT_DRIFT 与 truncated=true 保留。
Cloud Catalog：本地已实现，Viewer A两次Real PASS / scoped PARTIAL；查询修复后已Real复验，数值/完整性仍FAIL。
Product wiring / UX / Real E2E：前置门槛未通过，正式API继续关闭，NOT_TESTED；不能记PASS。
M6.5–M9：未开发。

## 用户恢复授权与本轮P0接线合同（2026-10-13）

用户批准保留全部成果并继续原M6.4，先治理仓库外测试目录；正式测试不移出Git。
本轮fresh fetch成功，main/HEAD/origin/main仍为9eaf55f基线、staging空；原16项源文件已在获准Cache内备份。
唯一新增测试总目录为D:\AAA_Workfile\PBIAgentTest；五个历史目录按用户要求仅盘点、未移动/删除/清理。
用途/大小/来源/引用和迁移建议详见该总目录README。以后pytest cwd固定仓库，cache_dir显式指向总目录Cache；
临时工具cwd固定M6.4/Acceptance，Real输出固定M6.4/RealEvidence。历史迁移仍需单独确认，不阻塞开发。

新增Cloud产品接线按以下P0边界实施与负例验证：

1. 正式Control Plane接口只允许精确method/path集合，经native session、CSRF、额外输入拒绝和safe DTO；不放开/api前缀。
2. 每个session只有一个principal-bound Catalog/Adapter上下文；容量受限、await前后和返回前重验，logout/epoch旧响应丢弃。
3. 客户端opaque key只能查当前Catalog已授权映射，选择时重新Schema验证；模型切换分配新conversation，旧模型业务上下文不继承。
4. server-owned shared seeds来自typed部署配置，普通用户无URL/ID/tenant/principal输入。目录状态与事实可执行状态独立。
5. Catalog/模型选择/模板eligibility/公开LLM配置可独立接通；Chat/Report等业务执行仍被显式事实门槛拒绝，用户配置不能绕过。
6. 后续产品Service组合复用LLMTurnService、ToolGateway和M6.3 PrincipalScopedRepositoryFactory；不创建第二事实链，不自动打开或迁移既有DB。
7. 前端复用Sidebar/Composer/Settings视觉；显式选模型，即使单模型也不自动选。请求generation/Abort与身份/模型选择绑定，旧响应不能覆盖新状态。
8. Int64与完整性独立记录，先研究可信SCALAR/标量FILTERED_AGGREGATION证明；DAX ROW/HTTP200/少量返回均不能单独授予完整性。
   当前拒绝策略保留，不把统一guard视为八种Shape均无法支持的结论。Microsoft支持仅为补合同渠道，不冻结无关模块。

### 恢复开发模块状态（随实质模块更新）

| 模块 | 实现状态 | 本地测试 | Real验收 | 剩余问题 |
|---|---|---|---|---|
| 测试目录治理 | PARTIAL | DONE | NOT_STARTED | 五目录已盘点，新资料统一PBIAgentTest；历史移动等待用户确认 |
| Cloud Catalog/模型选择Control Plane | PARTIAL | DONE | PARTIAL | 正式接口/typed seeds/CAS已接线；B历史十五模型，最新六模型及115未验证，fixture选择成功；企业授权未确认，Real已暂停 |
| Cloud Chat服务 | PARTIAL | DONE | BLOCKED | 组合既有LLMTurnService/owner repositories及selection lease；正式业务API/生产存储生命周期与Chat前端未完成；fact gate关闭 |
| History/Memory | PARTIAL | DONE | BLOCKED | owner只读list/read及迟到响应保护已组合；跨用户/跨登录所有权本地通过；正式API/UI与旧模型恢复映射未完成 |
| Cloud Report | PARTIAL | DONE | BLOCKED | 固定双Renderer与owned HTML view/download读取组合已准备；模板/正式生成查看下载API/UI及Real链未完成 |
| Settings/Cloud UX | PARTIAL | DONE | PARTIAL | 正式Account/Data、显式选择、本地名称筛选与恢复；最新前端131 PASS/Lint/Build；A/B账户设置退出已观察，模板Real资格未通过 |
| 权限隔离/竞态 | PARTIAL | DONE | PARTIAL | native principal/opaque key/owner/CAS/epoch本地负例通过；Real快速模型选择旧响应未覆盖新选择；业务IDOR、RLS/OLS与业务Late Response尚未验 |
| Int64 | BLOCKED | DONE | BLOCKED | 原严格负例保留，Real销售额失败；缺服务专属编码证据 |
| Query Completeness | BLOCKED | PARTIAL | BLOCKED | 八种Shape逐项研究及七项离线scalar候选核验；未授予完整性，当前产品guard拒绝未知结果；不以所有Shape均须等Microsoft作为结论 |
| Real产品全链 | BLOCKED | PARTIAL | BLOCKED | 正式浏览器登录/目录/选择/设置部分已观察；问答→VerifiedFactSet→Answer/Report→History及双用户业务矩阵未通过 |
| 企业隐私P0 | PARTIAL | DONE | BLOCKED | 已停止未获完整授权Real；合成wire证明披露路径与当前HTTP拒绝；历史数据来源、披露授权与当前RLS/OLS/撤权链仍未证明 |

Cloud控制面新增服务器选择generation比较，拒绝迟到的旧选择请求；前端409最多读取一次新状态并重试当前选择，旧generation不重试。
服务端未知key/跨用户key不能凭generation授予访问。新增负例先因缺少expected_generation参数FAIL，再最小实现CAS。
前端初轮effect lint失败保留：第一次拆分同步setState仍FAIL；第二轮采用已有hook相同的可取消0ms初始化调度后Lint/Typecheck PASS。
未关闭规则、未改变业务expected；CloudWorkspace切conversation重新挂载Composer，清理旧输入和模板状态。

### 当前恢复开发证据与剩余工作

原16文件完整保留；当前改动及SHA256清单位于获准Acceptance/current-worktree-manifest.json。
Frozen Core全文与HEAD对照，仅用户批准的六处声明替换；None、旧默认值和过滤逻辑保留。
274 focused/819 Semantic Compatibility通过；最新全量Backend 3244 PASS、1 SKIP、12 warnings（259.86秒），3240及此前为历史记录。
最新前端131 tests / 13 files、Lint、Build通过；warning与manual Real skip保留，不把自动化PASS换算为Real产品完成。

目录定位：固定低基数计时仅记录REST/IQ阶段、成功/失败和毫秒，不记录身份、ID、名称、URL或异常原文。
Viewer B的18工作区REST目录完成，123候选IQ逐模型串行授权耗尽约120秒预算；第一轮有界并发三后Real返回15模型PARTIAL。
第二轮在同一绝对deadline预留取消预算，返回仅完成验证的条目；shared seed只改变验证优先级、不会授予访问。
目录authorization_scope_complete/unverified_count只属于元数据覆盖，不是QueryResult完整性。
之后Real共享fixture选择两次RATE_LIMITED；未记录模板资格PASS。未知验证失败误计inaccessible并持续扇出为另一已定位根因：
四个负例先FAIL；第一轮分类修复后仍在取消前多启动两个任务，第二轮先halt再drain，41相关回归通过。
该修复已加载native服务，新会话Real目录显示6个已验证模型、115个尚未验证，stage span 38591ms（不是完整HTTP RTT）；fixture选择成功，模板资格未验。

新增owner只读服务复用现有HistoryService与PrincipalReportRepository，固定REAL source；不要求选模型、不恢复业务Memory。
await前后核验native principal；跨owner不可读、伪造principal拒绝、logout后的已完成读取不发布。
仅用synthetic DB测试，未打开/迁移用户DB；正式业务HTTP gate依旧关闭。
模板请求失败只恢复模板局部状态，不清除已验证模型；401与旧generation仍拒绝，发送保持disabled。

后续顺序：完成当前全量/Gates与一次有界B控制面复验；继续正式业务服务/API/前端接线及历史恢复的资源绑定设计；
按现有合同闭合scalar/标量filtered的完整性证明和Int64合法编码证据；严格门槛通过后才执行完整浏览器业务矩阵。
跨登录旧opaque key不能凭模型显示名或相同schema猜测资源，也不能直接恢复旧Memory；该映射尚未实现。
事实合同矩阵/支持问题草稿在获准Acceptance/fact_contract_review.md，未发送第三方。
旧五目录仅盘点未迁移；正式审计路由已卸载。未Commit/Push/本轮CI/Final Seal；Settings.version=M6.3，不启动M6.5。

### 新增企业数据与隐私P0（立即生效）

用户确认公司及账号所有者完整测试授权未确认；受影响企业Real已暂停，本人创建的native Real进程停止。
继续合成数据测试、原M6.4功能与安全审计。此P0约束用户提及的M6.4.1 PREP，不新增功能或改动路线/Git/Frozen Core授权。
未经企业明确批准，真实BI行、敏感Schema、业务事实不能发往DeepSeek/Kimi等外部Provider。
不能从Microsoft权限、账号登录或原安全测试PASS推导账号所有者/公司授权或外部披露授权。

两个Provider profile通过in-process MockTransport接收合成Answer columns/rows marker，证明通用Provider透传能力；
Observer summary不含marker，但通用TraceRecorder仅遮Secret，任意业务marker仍可进入其内存JSON。
该测试是披露风险证据，不是企业隐私PASS；Frozen Provider/Trace未改。现有Cloud业务HTTP配置外部Provider仍零次generate。
owner只读History/Report组合尚未证明持久资源的当前模型RLS/OLS及撤权链，正式HTTP继续关闭。

PBIAgentTest与五历史目录只输出文件数/大小/匿名hash及风险分类；有报表/结构化数据/邮箱样式候选，不能据此认定真实泄漏。
十个历史DB及图片/归档/二进制内容未读，不能宣称已无敏感信息。没有移动、删除、复制或上传敏感内容。
P0前浏览器工具输出曾含账号显示信息和企业目录名称；已停止继续采集，不在文档重现；既往记录授权与保留需授权方复核。
报告与统计在获准Acceptance/p0_privacy_audit.md、privacy-directory-audit.json，不要求用户发送凭据或敏感原文。

合成功能继续：Cloud名称筛选的failure-first用例先缺searchbox FAIL，最小前端实现后26 focused及131全前端PASS；不改变目录授权或事实gate。
LOCAL_DEV浏览器使用无.env/无企业身份、Mock BI/LLM与新合成存储，问答、新聊天、历史重开通过，未选择有效模板的报表请求明确拒绝。
仅作为合成LOCAL_DEV记录；Report生成/查看/下载及Cloud Real链未通过。原生Real服务不得在公司/账号授权明确前恢复。
最新fetch已成功且原main基线未变；staging为空。业务事实和P0门槛仍未通过，禁止发布封板。

## M6.4 测试资源隔离与隐私 P0（2026-10-13，未发布）

本轮用户明确授权先关闭测试范围/隐私P0，再继续原M6.4；不启动M6.4.1、M6.5、i18n或Azure。
原44项未提交成果已逐文件盘点并保留。fresh fetch最终成功，main/HEAD/origin/main仍为原基线，staging为空。

### 官方重验与实施合同

2026-10-13重新读取Microsoft官方[Workspace GET](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/get-workspace)、
[SemanticModel GET](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/get-semantic-model)、
[Report GET](https://learn.microsoft.com/en-us/rest/api/fabric/report/items/get-report)及[Fabric IQ](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)。
单资源GET支持已知workspace/item路径；workspace需Viewer及Workspace.Read.All，item可用既有Item.Read.All。
IQ继续delegated-only、RLS/OLS、runtime tools/list、固定selector；官方仍未声明本服务Int64字符串编码和可信完整性信号。

- 仅M6 Real测试环境启用CloudTestPolicy；本地默认开启，缺allowlist fail closed。正式产品部署显式关闭环境测试策略后仍按ADR-020 current-principal Catalog，不施加永久单Workspace限制。
- 服务端配置含唯一workspace、逐model/report批准和合成来源标记；report必须绑定已批准model。非合成资源另需公司/账号所有者批准，凭登录、Viewer或REST发现不能获得测试授权。
- 测试Catalog仅GET已配置Workspace和逐项允许资源，不调用全Workspace/模型/Report列表、不执行名称Discover；未知seed在任何外部调用前拒绝。
- REST在每次token获取和发送前检查路径，返回后验证exact资源身份、类型与workspace，只投影批准资源显示字段；不返回敏感标签、描述及其他资源元数据。
- Adapter在Resolve前、每次Binding/Schema/Execute/成员/normalization及await后验证范围；Transport在IQ call与实际发出tools/call前再次验证，ValueSearch/GetReportMetadata亦受限，未知工具拒绝。
- Cloud business HTTP继续关闭；测试服务组合在打开持久化或构造外部LLM事实链前拒绝。旧History/Report尚无持久化exact资源绑定和当前RLS/OLS证明，因此保持关闭，不能凭owner alone回放。
- 既有Int64、ResultInspection、VerifiedFactSet、八Shape与六字段Core批准范围保持；未新增Provider、QueryShape、模板、parser、planner或migration。

### 原始测试资源与本地配置

原始M6.3 deployment receipt与M6.4 native shared seed在本机核对workspace/model一致，receipt合成来源成立；真实身份只在本地配置，不输出/入Git。
本地m6-test-allowlist.local.json由匹配回执生成，仅合成模型，reports为空，公司/账号授权false。
仓库外run_native.py强制fabric_test_mode=true、必读本地allowlist并禁用宽范围seed；本轮未启动Real服务、未发真实资源请求。
用户批准的fixture来源不自动证明当前公司/账号测试授权；下一Real仍等待必要授权及事实合同。

### 企业隐私审计结论

Auth/Transport token仅本机内存与Microsoft传输；Catalog/Schema cache为principal/session/epoch范围。
通用LLM Provider可发送上层列名、成员、问题、rows与Verified Facts；受限上下文不是脱敏，事实验证也不构成外部披露授权。
Trace secret scrubber能处理token字段，但任意业务rows仍可进入to_json；Core存在schema fingerprint、canonical及coverage诊断，不能宣称业务DLP。
Memory/Snapshot/History含业务查询状态及展示内容，Report metadata/HTML落本机SQLite/filesystem；owner防跨principal读取，但旧记录缺当前model测试范围/RLS-OLS重验。
上述未闭合链路在测试模式及native HTTP保持拒绝，未把企业内容传入DeepSeek/Kimi；合成wire与负例证据独立于Real验收。

仓库外6个历史目录只做脱敏风险复扫：930文件、13数据库内容未读、credentials/JWT候选0；结构化数据/邮箱/报表候选需授权方本地复核。
未复制敏感匹配、未删除/迁移历史资料、未读取DB/secret/image/archive内容；不能据此认定历史无泄漏。
证据统一位于PBIAgentTest/M6.4/Acceptance/20261013-test-isolation，不在AAA_Workfile根目录新增目录。

### 当前模块与验收

| 模块 | 状态 | 剩余门槛 |
|---|---|---|
| 测试资源隔离 | DONE（本地实现）；Real BLOCKED | 原始资源已核对；逐项配置/授权和native Real尚待验收 |
| Cloud Catalog与恢复 | PARTIAL | 产品current-principal组合已有；测试定向REST及拒绝完成；仅安全合成回归 |
| Cloud Chat | BLOCKED | 正式业务gate关闭；不以Mock代替Real |
| History/Report/恢复 | PARTIAL / BLOCKED | owner组合已有；持久exact资源绑定、当前RLS/OLS、旧会话恢复未闭合，读取拒绝 |
| Settings/前端UX | PARTIAL | 目录/选择/账户已接线；完整业务页面/恢复未完成 |
| Principal/Ownership/Late Response | PARTIAL | 既有synthetic及新测试范围拒绝；当前Real验收待授权 |
| Int64 | BLOCKED | 服务专属合法编码合同不足；保留CONTRACT_DRIFT |
| 八Shape完整性 | BLOCKED | 无可信Real完整性证明；候选scalar推论不授予truncated=false |
| M5/LOCAL_DEV | 验证中 | Full/Semantic/Golden分层记录 |
| 发布 | BLOCKED | 安全/数值/完整性/完整Real E2E未通过；不Commit/Push/Final Seal |

Settings.version=M6.3；M6.4 NOT READY，不标COMPLETE。测试结果以本节随后fresh validation记录为准。

### 最新本地验证与限制（本轮）

初版全量后端3269 PASS、1 SKIP、12 warnings；该次包含25项隔离测试，后续新增HTTP/跨principal/日志负例另行回归，不继承初版数字作为最终文件集全量证明。
后续隔离31项、关联Auth/Cloud/Adapter回归234 PASS；Semantic Compatibility819 PASS、Golden11 PASS/1 manual Real SKIP；前端131 PASS、Typecheck/Lint/Build全部通过。
Repository Safety、Architecture、Documentation Governance、Error Ledger、Artifact Governance全部PASS；git diff --check PASS。
access log伪造ID/query-string负例先FAIL后修复，API路径遮蔽；未标记资源默认非合成，未经company/account approval拒绝。
原始44项路径仍全部存在；六字段Core差异仍6 additions/6 deletions，不扩大授权范围。
全量最终更新后再以fresh记录解析；本地验证不构成Real E2E或远端exact-SHA CI。

前端新增并发Profile401身份失效负例先FAIL，修复清空目录/选择/模板/Profile并触发既有身份恢复，避免兄弟Catalog成功掩盖会话失效；不改变业务执行gate。

### Final 本地验证（非发布）

最终完整后端3275 PASS、1 SKIP、12既有warnings（488.59秒）；31项测试隔离负例全部包含。
最终前端132 PASS（新增并发Profile401），Typecheck/Lint/Build PASS；最终Semantic819 PASS；Golden11 PASS/1 manual Real SKIP。
Repository Safety、Architecture、Documentation、Error Ledger、Artifact Governance与diff check PASS。
本轮Real调用0；最终exact-SHA CI及Remote Release Audit未运行，未Commit/Push。M6.4仍NOT READY。

收尾fetch因连接reset失败；本轮此前fresh fetch成功且基线未变，但最新remote audit未完成。全部成果保留，staging空，无Commit/Push。

## M6.4 阶段候选收口（2026-10-13；非 Final Seal）

用户明确授权一次`M6.4_云端产品阶段候选与安全边界`候选提交、正常Push main、该exact SHA Full Validation CI与Remote Audit。
前文“不Commit/Push”和fetch失败为历史记录，保留原始证据；本轮成功fresh fetch后按既有Git流程收口，不修改开发规则。
初始main/HEAD/origin/main相同、staging为空；48个修改文件与上一轮最终隔离清单一致，无新增/缺失路径。
旧哈希manifest差异对应已记录的隔离/隐私/前端401补丁；Frozen Core仍严格限六处声明。本轮不新增功能、不扩大已批准兼容范围。

| 模块 | 候选状态 | 后续门槛 |
|---|---|---|
| 测试Workspace隔离 | DONE（本地）；Real NOT_TESTED/BLOCKED | allowlist默认拒绝、定向GET、Adapter/Transport复核与合成越权负例；当前Real待授权 |
| Catalog / 选择 / Settings / UX | PARTIAL | 控制面与合成接线已有；完整正式Cloud浏览器Real E2E待验 |
| Principal / Ownership / Late Response | PARTIAL | 本地否定用例已实现；当前隔离环境A/B Real待验 |
| Cloud Chat | BLOCKED | 业务HTTP、执行ready固定关闭 |
| History / Report / 恢复 | PARTIAL / BLOCKED | owner组合已有；exact资源持久绑定与当前授权证明缺失，测试读取/准备拒绝 |
| 企业隐私P0 | PARTIAL / BLOCKED | native路径拒绝阻止未授权披露；通用Provider/Trace不是业务DLP，历史候选需授权方复核 |
| Int64 / 八Shape Completeness | BLOCKED | 不强转、不改Expected、不关闭完整性；保持CONTRACT_DRIFT及未知完整性拒绝 |
| M5 Frozen / LOCAL_DEV | 本地验证 | Full / Semantic / Golden / frontend分层验证，六声明之外Core未变 |

### 候选质量门槛与证据

本轮fresh完整后端3275 PASS、1 manual Real SKIP、12既有warnings（486.45秒），包含31项隔离负例；Semantic819 PASS、Golden11 PASS/1 manual Real SKIP。
前端首轮worker启动超时，125项通过但运行器报错，原日志保留；只降低本地maxWorkers=2后完整132 PASS（13文件），Typecheck/Lint/Build全部PASS，未改测试或Expected。
Repository Safety、Error Ledger、Architecture、Documentation Governance、Artifact Governance及diff check全部PASS；48项候选文件扫描无新增真实资源身份、JWT或二进制数据，合成URL负例与HEAD既有命中已分类。
本轮只更新四项候选状态文档，未改源码；当前轮哈希确认没有其他并发源码修改。提交前再次fresh fetch成功且远端基线未前进。
仓库外初始哈希清单、修改清单和分层日志仅放PBIAgentTest/M6.4/Acceptance/20261013-candidate；历史企业资料的风险候选仍未获授权复核，不将源码检查解释为完整隐私PASS。
对48项候选文件进行Secret/凭据/企业身份与数据检查，不读取.env或真实DB，不复制/移动/删除历史资料。
本轮真实BI资源请求及外部LLM真实请求均为0；旧Real失败记录仍保留，完整Chat→VerifiedFactSet→Answer/Report仍NOT_TESTED/BLOCKED。
候选SHA、CI链接/结果与Remote Audit以本次提交当前checkout及仓库外candidate回执解析；本段不预报成功、不引用旧SHA CI。

Settings.version=M6.3，M6.4 PARTIAL/BLOCKED、Final NOT READY。候选不开放未验证链路、不标COMPLETE。
剩余ACTION REQUIRED：公司/账号所有者逐Workspace/model/report真实测试与外部LLM披露授权、可信Int64/Completeness证据、exact资源恢复与正式Cloud/A-B/Report Real E2E。
Microsoft合同调查已有有界官方证据，不重复同一调查；只剩外部依赖时停止开发，不自动进入M6.4.1/M6.5。

## 候选后定向产品接线（2026-10-13，实施中）

用户批准补齐原定Chat/History/Report API、模型绑定/恢复、前端及撤权竞态；不扩大Provider/Shape/模板或Frozen Core。
fresh fetch通过本次命令限定DNS解析恢复，main/HEAD/origin/main仍为候选基线、clean；不改系统网络或长期Git规则。
官方Fabric IQ页本轮读取成功，delegated/RLS边界仍适用，未新增Int64或完整性编码合同；不发Real资源请求。

P0实施设计：服务端持久exact conversation/model绑定与schema fingerprint位于owner repository边界，旧缺绑定记录拒绝。
每次恢复/历史/报表读取先用当前principal重新Resolve+Schema，验证exact资源与fingerprint；失败、撤权及迟到响应拒绝。
原opaque key仅在owner绑定证明成立后由Adapter恢复；客户端ID、名称、旧session或schema相似均不授权。
受控服务API使用既有TurnPipeline/Repository；native Fabric IQ执行与回放在未获安全/事实验收前继续关闭。
合成完整链仅显式in-process Mock BI/Mock LLM注入，标为mock，不以部署开关或客户端请求打开真实业务。
持久扩展只增加绑定元数据，不迁移/读取真实数据库；本轮schema验证仅新合成DB，正式数据库迁移需operator授权。
本轮受控API：Chat/new-chat/restore/history/reports/view/download均位于同源Cloud BFF，Auth+CSRF先于路由；
Chat不接收客户端principal/model/conversation字段，分页与重复字段有界校验，异常只返回安全类别，HTML设CSP sandbox/no-store。
前端复用既有ConversationView/Composer/Sidebar，接Chat、历史恢复、新会话、受保护报表引用及Settings401恢复。
客户端abort和generation仅作显示保护，服务器owner+selection租约仍在每次持久化与响应前后验证。
模板仍原注册集合；合成模板资格使用测试专属canonical schema，Mock报告复用既有MockRenderer，不能计正式Renderer或真实VerifiedFactSet PASS。

Int64有界调查未得到可验证编码合同，string/bool/float严格拒绝；八类已有QueryShape代表DAX的未知响应和未文档化complete/totalRows标记均保留truncated=true。
没有修改Expected迎合数值错误、关闭完整性检查、更换Provider或扩大六字段Frozen补丁。本轮真实BI、外部LLM均0。
完整本地验证及当前main exact-SHA CI/Remote Audit见本轮仓库外directed回执；失败记录保留，M6.4保持PARTIAL/BLOCKED。

定向本地最终结果：后端3329 PASS/1 SKIP/13 warnings；前端141 PASS、Typecheck/Lint/Build PASS；
Semantic819 PASS、Golden11 PASS/1 manual Real SKIP；Allowlist+产品API focused44 PASS（随后新增missing-binding负例纳入全量）。
Repository Safety、137项Error Ledger、Architecture、Documentation Governance、Artifact Governance与diff check PASS。
33项白名单源码/测试/文档扫描未发现Secret、JWT或新增真实身份字面值；Frozen Core diff为空。
迁移警告与MSAL form_post建议均完整保留，不隐藏；新增绑定迁移只在合成临时DB验证。
后端最初完整3324 PASS后补充exact恢复/历史投影负例，最终全量重验3329 PASS；前端测试构造错误与文档表述修正记录保留。
待发布提交为定向必要修改，非Final；提交后仅以该actual main SHA的一次Full Validation CI与Remote Audit生效，不能继承候选CI。

## 单人模式本轮收口（2026-10-14；非 Final）

基于稳定5b0f22d9，Cold Start/fetch/clean确认后继续授权scope，没有重启或丢弃成果。
本轮native安全服务装配、直接服务拒绝P0、完整正式事实回调Synthetic API/React E2E、固定Renderer
及owner/撤权/迟到/错误合成验证见[一次技术决策与最终差异核验](m6_4_solo_contract_decision.md)。
该记录明确六项审计偏移、M6.0–M6.4状态、内部未完成和外部条件，不用新结论覆盖原始失败记录。
本轮未修改Frozen Core、Provider、Shape、模板、Expected、AGENTS或Git规则；version保持M6.3。
本轮真实BI/外部LLM请求0，M6.4 PARTIAL/BLOCKED、不能封板。完成本轮发布与审计后停止。
Full/Semantic/Golden/frontend/gates与actual-SHA CI回执仅以20261014-solo fresh记录为准。

本轮fresh本地结果：后端3335 PASS/1 manual Real SKIP/13既有warnings（483.64秒）；
Semantic819 PASS；Golden11 PASS/1 manual Real SKIP；前端142 PASS，Typecheck/Lint/Build PASS。
合成事实持久化补充断言4 PASS（full后新增assert-only，生产代码未再改）；Contract/Isolation71 PASS。
Repository Safety、Architecture、Error Ledger、Documentation、Artifact Governance及diff check PASS。
合成fixture初始正式语言分支限制、人工语言与canonical不匹配、stdio缺Origin及长路径导致atomic store
失败均保留本地日志；仅校准测试host/路径、修正来源和文档表述，未修改Expected迎合数值错误。
native直接调用负例先FAIL，唯一生产P0修复后PASS；M5 Frozen Core diff为空。
实际发布只按本次main新SHA的完整CI和Remote Audit生效；本节不预报远端成功。
