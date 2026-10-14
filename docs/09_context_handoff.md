# 09 — 下一开发者 / AI Cold Start Handoff

> Settings.version=M6.3；M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ数值兼容P1 BLOCKED；M6.4 NOT READY；M5.10.9 COMPLETE；M5.10.9 FIX COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一开发交接 authority；当前项目状态见 [07](07_milestones_status_and_open_questions.md)，路线见 [08](08_development_roadmap.md)。

## 当前阶段 — Current Baseline / Next Milestone

- Current Baseline：Settings M6.3安全封板；M6.4阶段main基线按最新exact-SHA CI / Remote Audit解析。
- M5 FINAL=true；Core Analysis Kernel 与 Local MVP baseline 已 Frozen。
- ACTIVE = 独立M6.4_FIX工程收口：当前实际提交自身CI/Audit/clean后COMPLETE，否则BLOCKED；M6.4 FINAL NOT READY；执行完停止。
- M6 Status：M6.3 Real安全74/74、Late-Response41/41、完整本地回归及Phase A CI通过；Settings.version=M6.3；最终发布条件见下文。

## M6.4_FIX 唯一当前交接（2026-10-14）

M6.0 COMPLETE；M6.1 COMPLETE；M6.2 COMPLETE（保留数值/完整性限制）；M6.3 Security COMPLETE。
起始main@6e8643ba15f4a6f6215f152408c054658fcd5f1f。实现与复现见
[专项](milestones/m6/m6_4_fix_engineering_closure.md)，技术判断见[决策](milestones/m6/m6_4_solo_contract_decision.md)。
资源API复用原会话/报表/Settings/批量契约，正式owner/exact binding复证；native企业数据执行、
外部LLM、留存与旧资源读取在相应流转前服务端拒绝。合成host不会成为native授权开关。
完整Synthetic产品链通过Mock/Fake Entra及正式事实回调验证，非Real；无Frozen Core/Provider/模板/Shape变更。
FIX COMPLETE仅以当前checkout实际main SHA自身Full Validation全部SUCCESS、Remote Audit、clean生效；
仓库外receipt与分层结果在PBIAgentTest/M6.4_FIX/Acceptance，不能继承起始或旧阶段CI。
M6.4 FINAL NOT READY；IQ数值/八Shape完整性、获准逐资源环境、企业披露留存native策略及真实浏览器全链未过。
Arrow为ALTERNATIVE_CANDIDATE；运行保持ADR-020 IQ，无Provider迁移/fallback。Settings.version=M6.3。
本轮结束立即停止；不得自动再开发M6.4.1/M6.5/M6.6。下文全部是历史，不沿用旧PARTIAL作为当前FIX结果。

## 旧solo轮交接（2026-10-14；历史）

进入main基线5b0f22d913dcf47af53903f8b4fae1d3162d2dc1、自身CI已SUCCESS；不重发候选。
本轮native ENTRA_BFF已安全装配Product Service，但business gate关闭，deferred仓库不打开DB；
直接service embedding也不能绕过gate进入Core/外部LLM。正式事实回调与固定Renderer通过完整
Synthetic API/React client链，MOCK来源及owner存储保持，不能作为Real PASS。
[一次合同技术决策与最终差异核验](milestones/m6/m6_4_solo_contract_decision.md)为本轮未决清单。
Int64/Completeness与企业授权仍外部BLOCKED；Cloud完整资源管理及披露/留存落实仍内部PARTIAL，
不报告只剩外部依赖。原M6 Workspace逐资源allowlist、native fail-closed、Settings.version=M6.3保持。
本轮源码/测试/文档白名单发布按实际SHA CI及Remote Audit回执生效，证据在20261014-solo。
收口完成后停止。后续M6.4.1/M6.5及另一开发任务均未授权。下文尚未装配/未发布等描述为旧轮历史。
## M6.4 active handoff（2026-10-13）

最新定向工作基于候选`4f17b9319b6310e511d6754d36062b59edcf393a`；候选exact-SHA CI SUCCESS已验证，不重复候选发布。
本轮授权完成Cloud Chat/History/Report受控服务/API与前端接线、Settings恢复、exact binding和Late Response合成验收。
native FabricIQ执行及业务History/Report仍存储前拒绝；真实外部LLM路径不开放。仅显式host注入的既有Mock服务可执行合成链，不能由env或客户端开启。
新增owner绑定迁移只验合成DB；旧会话无绑定不回放，恢复Resolve+Schema fingerprint重新证明；A/B、撤权、Schema drift和迟到字节均有负例。
真实固定Renderer保持原合同；Mock报告使用既有MockRenderer，不能计正式VerifiedFactSet或Real报告通过。
本轮证据在`PBIAgentTest/M6.4/Acceptance/20261013-directed`；最新main提交标题/当前checkout及发布回执解析其exact-SHA CI与Remote Audit，不继承候选CI。
Git网络应自行恢复（已用本次公共DNS核实后命令级curloptResolve成功fetch），不因常规网络失败重开开发；push前远端前进仍按原规则停止。
剩余外部条件：公司及账号所有者批准原M6 Workspace逐资源Real验收；单独批准业务LLM披露与留存；Microsoft可证明Int64及八类完整性合同。
内部Final条件：在这些证据具备后最小落实对应native执行/隐私保护，完成正式Chat→VerifiedFactSet→Answer/Report与浏览器Real、RLS/OLS验收，再更新M6.4版本。
Settings.version=M6.3、M6.4 PARTIAL/BLOCKED。范围限定原M6.4；M6.4.1与M6.5未获开发授权。下方旧入口状态由本段及07最新状态限定。

最新用户授权优先收口现有48项修改：一次阶段候选Commit/Push main、候选exact-SHA Full Validation CI与Remote Audit，不是Final Seal。
本轮已成功fresh fetch，main/HEAD/origin/main相同、staging空；修改路径与上一轮最终隔离记录完全一致，未发现新增混入文件。
候选标题`M6.4_云端产品阶段候选与安全边界`；SHA通过当前checkout与仓库外候选回执解析，不把本提交自身SHA写入本提交。
本节后面的“不Commit/Push”均为旧轮历史状态；本次用户候选授权替代该限制，长期main单线/白名单/正常push/自身CI流程不变。
Settings.version=M6.3、M6.4 PARTIAL/BLOCKED、Final NOT READY；业务API及测试History/Report/LLM准备继续拒绝，不能为候选而放开。
必要Real因授权/Int64/Completeness未满足记NOT_TESTED/BLOCKED；不强行执行，也不继承旧宽目录测试为当前隔离PASS。
fresh验证与候选审计见专项候选收口章节及PBIAgentTest/M6.4/Acceptance/20261013-candidate；原始失败与历史证据保留。

最新测试隔离轮本地后端3275 PASS/1 SKIP/12 warnings，隔离31项；前端132 PASS与Typecheck/Lint/Build，Semantic819、Golden11/1 manual Real SKIP；必要Real及完整Chat→Facts→Answer/Report未通过，未提交发布。

本轮最高P0：所有Real仅原始获批M6测试Workspace/model/report。CloudTestPolicy默认开启、缺配置拒绝；本地allowlist和runner已接，reports为空。重新fetch成功基线不变。未来不得执行旧宽目录runner或企业Schema/LLM probe；旧History/Report缺持久exact资源/当前授权证明保持拒绝。原44项成果保留，最新证据在PBIAgentTest/M6.4/Acceptance/20261013-test-isolation；Real/完整业务/封板仍BLOCKED。

[本轮专项证据](milestones/m6/m6_4_cloud_product_e2e.md)。初始main/HEAD/clean校验完成；两次有界fetch失败后，
本轮依用户明确许可用GitHub连接器核对远端main与本地HEAD一致，仅继续本地开发/测试。
此许可仅限本轮，不修改下方Mandatory Cold Start或长期Git规则；成功fetch且基线未前进前禁止Commit/Push/Final Seal。
后续本轮fetch曾成功；最新两次有界重试再次失败，连接器fresh main SHA仍等于原基线。
main/HEAD/cached origin/main一致、staging空；原16项成果已保留，当前恢复开发新增文件清单见获准Acceptance/current-modified-files.md；提交前仍需fresh fetch成功且基线未变。
Charter旧状态与08的M9规划已先修正；Catalog REST/Service与Auth精确只读scope、逐模型schema-before-bind已本地实现。
本地Full Backend/Semantic/Golden与Catalog安全测试见专项记录；不继承M6.3 Real结果作为本轮PASS。
Viewer A已真实登录并执行首轮审计；Real Catalog PASS，6个模型可访问，workspace scope complete，individual-share覆盖仅configured seeds，整体PARTIAL。
首轮count/scalar/grouped均在ExecuteQuery之前被临时harness遗漏allowed_semantic_models阻断，不能记为上游数值失败或查询PASS。
仓库外harness仅补入当前已验证ref.server_model_key；实际native probe回归先2 FAIL，再与边界测试合计12 PASS。
已重启本人创建的临时服务加载修复，用户重新登录后完成Real复验（02:12:54 UTC）：Catalog再次PASS、6模型、整体PARTIAL。
三条查询均ExecuteQuery HTTP200；count严格int值匹配但truncated=true，销售额scalar/grouped在HTTP wire和SDK均Int64配str，FAIL CONTRACT_DRIFT。
所有响应无完整性字段；官方重验仍无足够编码/完整性合同，当前阻塞不再是登录/consent。不得重复要求用户重新配置已有效权限。
安全证据位于仓库外runs/20261013T020906Z-8d579b58ddbc48e7b39bfdaddc3f632d/audit-001.json。
本次Real后已关闭临时审计进程并恢复native app。GET审计页（后端及Vite代理）404；未登录POST先被CSRF拒绝401，
隔离synthetic有效session+CSRF验证POST审计路径404、产品API403；原生路由集合无m64临时入口。
仓库外native-cleanup-evidence.json记录8项PASS；fabric_iq_contract_support_note.md为脱敏支持草稿，尚未发送任何第三方。
仓库外临时只读审计：D:\AAA_Workfile\PowerBIAgent_M6_4_Acceptance；不由production导入，不读取/迁移业务DB。
正式ENTRA业务API保持关闭；Cloud产品接线/UX/浏览器Query与Report E2E未完成；数值P1/完整性仍UNRESOLVED。
未来正式接线必须使用FabricIQAdapterFactory.create_product，在Core前拒绝未知完整性的结果；普通create仅保留审计合同。
现有Sales报表直接组装可丢失truncated标记的合成失败证据已保留，M5 Core未修改。
Settings.version=M6.3；M6.4发布NOT READY，不Commit/Push，不宣称封板。

用户2026-10-13恢复原M6.4并要求测试目录治理：唯一新总目录D:\AAA_Workfile\PBIAgentTest，历史五目录仅盘点未迁移。
原16文件已备份到该总目录Cache；后续工具/输出在M6.4/Acceptance、RealEvidence，pytest显式cache_dir并以仓库为cwd。
恢复开发时fetch曾失败并经连接器核验；最新HTTP/1.1 fetch成功，HEAD/origin/main仍等于原基线。提交前仍须fresh fetch且基线未变。
新增正式Cloud Control Plane与前端目录/显式选择/Settings；业务执行仍fail closed，未打开既有DB。
CloudProductServiceFactory复用LLMTurnService与PrincipalScopedRepositoryFactory，selection lease阻止失效写入；尚未挂生产业务执行API。
用户另行明确批准仅model_semantic_context.py六处声明兼容：五项bool接受None及来源枚举增加fabric_iq；不修改默认值、过滤或其他Core合同。
274项相关focused、819项Semantic Compatibility通过；完整文件对HEAD严格六处声明替换检查通过，其他Frozen Core未改。
最新全量后端3244 PASS、1 SKIP、12 warnings（259.86秒），见backend-full-p0-privacy-final-local.txt；3240及此前记录为历史。
最新前端131 PASS/Lint/Build；模板失败不清除已验证模型，模型名称仅本地筛选，401/旧generation仍拒绝，Cloud发送仍禁用。
Viewer A正式产品页6模型/Settings/退出已观察。Viewer B目录15模型PARTIAL；18工作区REST先完成，123候选IQ授权耗尽预算。
有界并发三及同一绝对deadline的scoped PARTIAL已实现；后续发现限流被误计不可访问并持续扇出，四项负例先FAIL，第二轮停止调度修复后41 focused PASS。
此前synthetic fixture选择两次RATE_LIMITED；最后一次新native会话返回6模型、115未验证且fixture选择成功，模板资格未验。
用户随后补充企业P0并确认完整测试授权未确认，原生Real服务现已停止；不要重复要求登录或继续企业资源操作。
正式首页为http://localhost:5173/；旧/auth/m64-audit已卸载。不要以临时probe、mock或单独控制面冒充产品E2E。
新增owner只读History/Report服务组合：不依赖当前模型选择，不恢复Memory；scope和返回前native身份重验，跨用户/伪造principal/迟到响应负例通过。
仍无正式业务API/存储生命周期接线、Cloud业务前端及跨登录恢复模型映射；旧opaque模型key不可凭名称或同schema猜测新资源。
Fact合同研究及七项OFFLINE scalar候选核验在获准Acceptance目录；不授予完整性，Int64仍严格拒绝字符串，产品Adapter仍拒绝truncated结果。
原生runner在PBIAgentTest/M6.4/Acceptance/run_native.py，当前已停止；原审计路由未恢复。
当前run_synthetic_product.py仅LOCAL_DEV/Mock BI/Mock LLM，未加载.env、无企业身份，新合成SQLite与报告root均在获准Cache。
合成浏览器问答、新聊天、旧历史重开已观察；报表未选有效模板明确拒绝，未做Report生成/下载；不计Cloud Real PASS。
P0审计在获准Acceptance/p0_privacy_audit.md：通用Provider透传columns/rows，Observer计数summary不含正文，但Secret scrubber不证明业务数据最小化。
History/Report仅owner检查不足以证明当前模型RLS/OLS；正式业务HTTP仍关闭。需要完成资源绑定/撤权验证与披露边界，不能放行企业数据到外部LLM。
六目录脱敏扫描只报告风险候选；10个历史DB、归档/图片/二进制内容未读，无文件迁移删除。历史企业数据来源和历史传输仍未证明。
公司/账号所有者明确授权后才恢复Real；外部LLM企业数据披露仍单独视为未授权。此P0同样约束用户提及的M6.4.1 PREP边界。
旧五个测试目录未迁移；新证据仅PBIAgentTest。未Commit/Push，未执行本轮CI或Final Seal。M6.5未启动。

## M6.3 sealed security handoff

[设计、完整证据、范围调整与迁移恢复](milestones/m6/m6_3_multi_user_ownership_authorization_rls_ols.md)。
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

补丁基线为main@419dfd5cdde5c7550d62bbdaca12c7de853cea65；恢复时保留全部未提交成果与历史失败证据。
仓库外工具与safe evidence位于D:\AAA_Workfile\PowerBIAgent_M6_3_Acceptance；本轮Late synthetic存储位于D:\AAA_Workfile\M63Late；fixture位于D:\AAA_Workfile\M63Fixture。
临时延迟hook/诊断路由已从运行中服务卸载；正式代码从未导入仓库外工具。真实账号、token/cookie、raw identity GUID不进入Git。
Alembic head=f63a1b2c3d40，八表历史行归local:legacy；现有用户DB未读取/迁移。回滚仅恢复M6.2离线完整备份，禁止合并principal IDs。
Phase A固定中文commit：M6.3_多用户归属与权限隔离候选；Final：M6.3_多用户安全隔离与真实验收封板。
候选普通push当时被服务器管理员豁免（事实保留）；随后main曾只新增enforce_admins=true，原required check/App绑定及其他规则未变。
M6.3 Final当时经临时交付ref→PR required CI→受保护合入main→Final main exact-SHA CI完成；这是历史操作，不是未来开发的强制流程。
Phase A SHA/CI见下节；Final自身SHA不写入自身提交，逐项验证main checkout exact-SHA CI，完成后立即停止，不自动开始M6.4。

## M6.2 历史 handoff

本轮用户已明确批准M6.2；fresh Cold Start exact基线1c71dee7，官方2026-10-10重验。
[实施合同与当前验收](milestones/m6/m6_2_fabric_iq_cloud_adapter.md)。
Cloud Adapter已实现；Settings.version=M6.2；两模型Real、Phase A及final自身CI38012437829已通过。M6.2结束时M6.3须独立批准；本轮授权与进度见上方active handoff。
旧PREP证据已脱敏、不含模型URL；bootstrap与smoke harness只存repo外临时目录。
没有永久debug route；仅Auth broker获取token；ENTRA_BFF旧product gate保持。

## M6.1 历史 handoff

[M6.1 contract/evidence](milestones/m6/m6_1_entra_identity_login_session.md)记录本轮设计、tests和验收。
本轮用户已批准Auth/Session/Account；Real+Phase A exact-SHA CI全绿后，最终封板更新Settings.version=M6.1。
首次Real OAuth前的fake/local gates与人工Portal配置停点已完成。用户确认Portal配置并亲自接受首次用户同意。
真实Microsoft组织账号login/callback/account/reload/logout及跨标签退出均PASS；非模拟Test A。截图repo外，真实身份与credential不入库。细分证据见M6.1专项文档。
Phase A push及自身CI成功；本次最终COMPLETE仅按下方exact-SHA CI与remote audit规则生效，不继承Phase A或M6.0历史CI。
repo外secure-input helper已准备并用synthetic tempfile验证，真实`.env`未由Agent读取/展示。
LOCAL_DEV保留M5；ENTRA_BFF不初始化业务持久化/provider，全部旧product API fail closed。
ENTRA_BFF multi-user persistence: NOT ENABLED BY DESIGN UNTIL M6.3 OWNERSHIP。
production+in-memory SessionStore拒绝启动；process-local cache不具备multi-worker保证。
M6.1封板时要求M6.2 trusted authorization projection必须由validated Principal + server-owned model binding +
authorization evidence创建，不能client self-declare；Auth broker是唯一delegated token获取入口。
M6.1封板时M6.2/M6.3/M6.4未实施；当前M6.2进度见上方active handoff；后续阶段须另行授权。

## M6.0 accepted handoff

[M6.0 evidence / Product/Auth UX](milestones/m6/m6_0_fabric_iq_cloud_contract_audit.md) 与
[ADR-020 ACCEPTED](adr/ADR-020_fabric_iq_cloud_consumption_and_catalog_authority.md) 是当前Cloud设计合同。
官方Fabric IQ GA、delegated-only三scopes、X-Variants selector已重验；现有客户端两模型probe PASS，
名称discovery empty已分类。M6.1采用same-origin BFF code/PKCE，token仅Auth/Transport；Webredirect
及credential已由用户在M6.1开发环境配置。M6.2新Adapter，禁止填旧Remote skeleton；
必须实测固定selector/rawschema/PK-FK/result完整性与failurefixtures。M6.3双Viewer授权/RLS/OLS矩阵。
M6.4由FabricREST catalogservice提供normalized scoped目录；individual-share覆盖缺口由管理员
seed补充并标partial，不向普通用户要求URL/ID。前端沿用现有视觉、chat shell/compact rows，
auth/catalog状态机、logout/epoch/换模型新conversation见M6.0第11节；M6.0当时没有实施UI，当前Auth实现见上节。
M6.5 UCI Online Retail II，M6.6 production seal；不启动M7/M8。所有implementation需freshColdStart、
官方重验、适用P0边界验证与用户具体scope授权；M6.0完成后立即停止。

下一开发者可进入 M6 研究/设计，完成下列 prerequisite 并取得具体 patch scope 授权后才实施。
M5 Final baseline 已成立；post-final 文档修复不重新开启 M5 功能开发，也不解冻 Core。

## Mandatory Cold Start

1. 先 git fetch origin，再 git status、git branch --show-current、git rev-parse HEAD / origin/main、git log -8，
   检查 staging，初始核对 main、clean worktree/staging、HEAD==origin/main 与获批 baseline。
   开发中允许本轮已授权白名单改动；未知用户修改、非获批分支或 remote main 相对本轮基线前进立即停止。
2. AGENTS.md → PROJECT_CHARTER.md → CLAUDE.md。
3. docs/07 → docs/08 → docs/09；README、CHANGELOG 作为导航与历史摘要。
4. Error Ledger 的 schema、有效 prevention/prohibited rules 与相关条目；ADR README 和任务相关
   accepted ADR。ADR-006 是历史 SUPERSEDED 路线，不能当成当前 endpoint/auth contract。
5. 当前用户指定文档、涉及 production code、邻近 tests、CI required checks。
6. 输出简短 reality audit 后在已授权范围内继续。不得以聊天记忆或历史 PASS 代替 fresh 证据。

冲突优先级：当前明确用户指令 → PROJECT_CHARTER → 正式 PRD → accepted ADR → 当前专项设计
→ 08 → 09 → CLAUDE → code/fresh tests → Archive。07/08/09 分别只拥有状态/路线/交接。

## 最终 baseline 解析

M6.3 Security Final 已通过 [PR #1](https://github.com/Strange-Men/PowerBIAgent/pull/1) 合入
`2179e3f118cf0b33b55143c819d9e1e521a19ae0`；
[Final exact-SHA CI38039151643](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38039151643)
为该 main SHA 的 push 事件，completed/success，安全封板已成立。

后续 Documentation Governance FIX 的 PR 交付授权被用户明确撤回；
[PR #2](https://github.com/Strange-Men/PowerBIAgent/pull/2) 已关闭、未合并，
其提交 `ff1c42b87006b81054315bc696d30100db7fde94` 及 PR CI38040853620 SUCCESS仅保留为历史，不证明 main 发布。
用户已手动取消管理员强制约束；本轮 fresh远程审计为protected=true、enforcement_level=non_admins，
原Full Validation (Windows)/App15368保留。历史PR/保护调整不构成长期强制PR或双CI规范。
本轮仅恢复 main 单线工作流；最终实际文档提交仍须自身一次完整main exact-SHA CI及remote audit。
不继承历史CI、不重开M6.3功能；M6.4尚未获批、尚未开始，完成本轮后立即停止。

M6.3 Phase A：`47fb74c512dea64d2644f193b4f76095535bca17` /
[exact-SHA CI38037929168](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38037929168)，
push事件、head_sha精确匹配、Full Validation (Windows)与全部23 steps success。
Final marker更新Settings.version=M6.3；自身SHA不写入自身提交。读取main checkout exact SHA的
PowerBIAgent Validation / Full Validation (Windows) completed/success并逐项检查required steps；
M6.3 Final当时fetch后HEAD==origin/main、worktree clean、管理员保护启用且无临时授权入口，已解析为M6.3 Security COMPLETE。
后续工作流恢复不改变该安全验收结论；后续发布按最终实际main SHA自身CI与remote audit验证，不以管理员强制约束作为安全状态续存条件。
Final通过不等于销售额或M6.4 Cloud Product E2E通过；禁止继承候选/旧M6.2 CI充当Final。
M6.2历史Phase A daeb5b63e81364da97eabdd0d20b835c868388df / CI37972741912；
历史Final 419dfd5cdde5c7550d62bbdaca12c7de853cea65 / CI38012437829；均不证明本轮marker。

### M6.1 历史基线

M6.1 Phase A：`5549d0973473eed7849f48465ccbd13af96a5015` /
[exact-SHA CI37954913373](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37954913373)
completed/success，push事件、Full Validation (Windows)及全部required steps实际success，无skipped step。
最终seal更新Settings.version=M6.1；自身SHA不写入自身提交。查询当前checkout exact SHA的
PowerBIAgent Validation / Full Validation (Windows) completed/success，逐项核验required steps，
fetch后HEAD==origin/main且worktree clean，才解析为最终M6.1 COMPLETE / M6.2 READY。
M6.1封板时Auth已实现；当前FabricIQAdapter已实现；Cloud Catalog、multi-user persistence ownership仍未实现。

### M6.0 历史基线

M6.0 Phase A：`e437908a67e6fe57a2259415df6d2e3dbf6dca74` /
[exact-SHA CI37904870868](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37904870868)
completed/success，Full Validation (Windows)与全部正常requiredsteps实际success，无skippedstep。
最终seal更新Settings.version=M6.0；自身SHA不写入自身提交。必须查询当前checkout exactSHA的
PowerBIAgent Validation / Full Validation (Windows) completed/success，核验全部正常steps，
fetch后HEAD==origin/main且worktreeclean，才解析为最终M6.0 COMPLETE。不得继承PhaseACI代替finalCI。
M6.0封板时真实production仍是M5 Local MVP；当时无FabricIQAdapter/Entra/frontendauth实现。

### M5 历史基线（保留，不覆盖M6.3当前baseline）

既有 M5 Final baseline：`86aaaec7d2172c041e97392c3de03adcca77ca1b` /
[exact-SHA CI 36678384015](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36678384015)
completed/success，2026-09-30 fresh REST + fetch 核验。M5 FINAL=true 持续有效。
FIX 候选 `9196bb7e52fbc8869daff7233518ac896bc813ca` /
[exact-SHA CI 36686978579](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36686978579)
completed/success，required Full Validation (Windows) 与全部 steps 已核验全绿。
Phase B `953be2683d539fbf4b43d59cca086a3fd598928c` /
[exact-SHA CI 36688714620](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36688714620)
completed/failure，2026-10-09 fresh fetch / failure logs 核验；其 FIX COMPLETE marker 未生效。
失败为既有 health lifespan 测试的 id/address reuse oracle，不是 production lifecycle regression。
用户获批的 Phase C 测试修复 `f8641f4d588e1823f521a6d1e9e4e459e6c920f3` /
[exact-SHA CI 37871771667](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37871771667)
completed/success；Full Validation、全部正常 steps（含 Golden / frontend / typecheck / lint /
build / strict diff）实际 success，无 skipped；fresh fetch 后 HEAD==origin/main、clean。
Phase D 只做 marker/evidence patch，仍须其自身 exact-SHA CI 与 remote audit。旧失败 run 保留，
不以 rerun 偶然通过替代修复。
最新 FIX 自身 SHA 不写入自身提交；以当前 checkout 的 `git rev-parse HEAD`、该 exact SHA 的
PowerBIAgent Validation / Full Validation (Windows) completed/success、fetch 后 HEAD==origin/main
与 clean worktree 联合解析最新发布基线。FIX COMPLETE 须有最终 FIX exact-SHA CI 和 remote audit。
运行 git log -8 --oneline 查当前中文提交，并按该 SHA 查询 Actions；祖先 CI 不覆盖当前 SHA。

## M5 Frozen Core

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

SemanticFrame 只输出 bounded language draft；Catalog/Grounding 证明 canonical object/member，
StateTransition/Completeness 证明可执行 state。QueryShape 固定八种；无证据/歧义/残缺在 DAX 前
clarification/no-match + ZERO factual Memory commit。DeterministicDAXBuilder + DAXSafety + Independent
Layer 3、ResultInspection + VerifiedFactSet 保留执行/事实 authority；LLM 不做业务数学。
General current-message-only/no-tool，ZERO schema/member/DAX/report/business Memory/pending mutation。
Natural Presentation 只消费 verified facts/scope/真实 availability 并经 FactOutputValidator；失败 repair
或 deterministic safe fallback。Report 复用同一链，固定 Renderer authority 不变。
requested scope、observed coverage 与 measure-aware available horizon 独立；未知 freshness 明示未知。

## 当前 provider 分层与 M6 第一阶段

M5 Local MCP = Developer / Desktop Provider；M6 Cloud Provider = Production Cloud Consumption Provider。
当前实现为 MockPowerBIAdapter、LocalMCPPowerBIAdapter 与未完成的 RemoteMCP skeleton，Real 失败
不得回退 Mock。未来 Cloud PowerBI Adapter 继续服从 PowerBIAdapter 与 ToolGateway，不能复制管线。

```
SemanticFrame → Grounding → CanonicalQueryPlan → Deterministic DAX
→ Power BI data plane → QueryResult → ResultInspection → VerifiedFactSet → Answer / Report
```

任何 M6 implementation 前必须重新验证 Microsoft 官方 API / MCP / Fabric 文档，保存日期、
官方来源、endpoint、auth、tenant/identity、capability/tool schema、RLS/OLS 与 fail-closed probe
证据。M6.0已验证官方Fabric IQ合同与当前两模型只读smoke；defaultclientprobe不等于自建app
或fixedselectorwire已验收。ADR-020接替ADR-006的Cloud合同；Cloud/Entra production尚未实现。

### M6 prerequisite 顺序

1. Fresh Cold Start。
2. External Microsoft capability verification（官方能力、endpoint、tool schema 与日期证据）。
3. Auth / identity / RLS-OLS evidence（包括拒绝与 fail-closed probe）。
4. Threat model。
5. Tenant / principal / resource identity。
6. Ownership / IDOR。
7. Token lifecycle。
8. Cache isolation。
9. Accepted implementation contract。
10. 用户明确批准具体 patch scope。
11. 才开始 production implementation。

未完成上述 prerequisite 或未获用户授权前，禁止直接实现 M6 production path。

### M6 first-step technical debt — RemoteMCP legacy skeleton（P0 prerequisite）

`backend/app/powerbi/remote_mcp.py` 是 legacy deferred skeleton。ADR-006 已 SUPERSEDED；
旧 endpoint、constructor defaults 与 NotImplemented message 中的 ADR-006 wording 均不是
M6 production contract。不得看到 skeleton 就直接实现。先按上列顺序验证 endpoint/auth/
identity/tool schema/RLS-OLS，再以 accepted contract 与获批 scope 决定后续 Adapter 实施。
旧FIX仅校正模块docstring；M6.0不修改server_url/异常/class行为/transport/auth/provider selection。
Settings只在M6.0最终seal作版本metadata更新。风险与回归记录见FIX evidence / M6.0 contract。

| 未来职责 | 范围 |
|---|---|
| PowerBIDataPlane | IQ resolve/schema/value/deterministic DAX；Discover仅候选 |
| PowerBIControlPlane | FabricREST current-principal catalog/metadata；未来refresh/embed/lifecycle |

refresh API 不得塞入 execute_dax adapter。Control Plane/Catalog仍为后续M6架构方向；M6.2 Data Plane证据见上方active handoff。

## Production Backend — P0

Authentication / Entra identity、tenant namespace、principal namespace、Authorization、Ownership、
IDOR、OAuth token lifecycle、Secret leakage、cross-user cache isolation、RLS / OLS identity propagation、
fail-closed external authority handling 均为 P0。当前 M5 的本地 `test_user` 与 Mock/Real namespace
不是 enterprise identity 或 authorization；不得部署后仅替换显示用户名。

Token 只能存在 Auth / Transport boundary，不得进入 UserContext、Memory、Trace、Conversation
persistence。后续 persistence resource identity 必须包含 `tenant_id`、`principal_id`、
`conversation_id`。Report / Snapshot / Conversation / Memory 均需 server-side ownership validation；
客户端传来的 ID、tenant、principal 与 model key 均不能自行证明授权。跨用户 cache key 和
RLS / OLS identity 必须来自服务端验证的主体，外部 auth/schema/result authority 不完整时 fail closed。

## Production Backend — P1

multi-worker、multi-instance、restart behavior、transactions、idempotency、retry、timeout、
failure recovery、PostgreSQL migration path、Blob/Object Storage path、cache strategy、
distributed coordination when justified、schema migration、observability、audit、deployment、
upgrade compatibility。先证明资源归属、事务/重放/取消/失败恢复与隔离，再增加功能数量。
PostgreSQL / Blob / Redis 均尚未实现，不能把本地 SQLite + filesystem 的保证描述为生产云保证。

## 明确禁止事项

禁止第二 Planner/Grounding/Memory、Agent、LangGraph、RAG/vector DB、ontology server、LLM DAX、
任意代码/自由 HTML、直接生产写操作、无审批 authoring、自动 Real→Mock fallback、silent report overwrite。
Entra/Fabric IQ/PostgreSQL/Blob/Redis/migration 与新模板/分析能力只能在各自获批 scope、正式合同
及适用安全前置条件完成后扩展；M6 READY 不构成 implementation 授权。不得绕过 Frozen Core、
共享事实链、eligibility 或 Token boundary。
当前报告是 historical snapshot；M7 规划 Recipe + Artifact versions，不能用刷新覆盖历史证据。

## 测试 / CI / release 与 debugging

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

测试按当前 patch 风险与用户 scope 选择；CI required matrix 保持完整。基础检查包含 Documentation
Governance、Version Consistency、Architecture、Repository Safety、Error Ledger、Artifact Governance、
Semantic Compatibility、Golden、backend suite、frontend tests/lint/typecheck/build。
Local Real / Browser / stress 只在适用且获批时运行，分层记录；历史数字不代替 fresh evidence。

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts/check_documentation_governance.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_artifact_governance.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_semantic_compatibility.py
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
```

post-final evidence 见 [M5.10.9 FIX](milestones/m5/m5_10_9_fix_document_semantic_consistency_and_m6_handoff.md)；
原封板记录见 [M5.10.9](milestones/m5/m5_10_9_documentation_governance_and_final_seal.md)。旧长交接见
[Historical snapshot](archive/m5_pre_final_09_context_handoff.md)，仅作历史，不能继承旧 pending/current state。
