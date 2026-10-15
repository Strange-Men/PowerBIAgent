# 09 — 下一开发者 / AI Cold Start Handoff

> Settings.version=M6.4.1；稳定基线 M6.4 FINAL COMPLETE；M5 FINAL/FROZEN 有效。

## 当前阶段 — M6.4.1 维护 / 发布判定

M6.4 FINAL COMPLETE；Final SHA `bdbe7189be21ff043340c2025625a9e3398310b0`；自身 [Full Validation 38693083553](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38693083553) SUCCESS，Remote Audit PASS，封板时 HEAD=origin/main、worktree/staging clean。

M6.4.1 仅处理仓库外测试资产治理、README 信息架构、current-state 一致性、IQ 保守结果边界明确化及 Test B OLS 证据状态；不实施 Schema cache、connection reuse、Favorites/Preferences，不进入 M6.5。

Folder Governance：448 文件 / 44,252,661 bytes 原始副本验证通过；10 synthetic DB 仅 byte copy/hash。用户已人工删除旧五目录与仓库误生成五目录，fresh 验证 MANUAL_DELETE_COMPLETE；旧目录=0、仓库临时目录=0、active old-path reference=0、SHA mismatch=0。

IQ 正式 Cloud business rows ≤12，wire sentinel=N+1，columns ≤8；超界在 Facts 前 fail closed。CLOSED_AS_EXPLICIT_LIMIT，不扩大 completeness、QueryShape、Provider 或 Frozen Core。Test B 当前没有可用验收 principal，DEFERRED_BY_TEST_PRINCIPAL；后续生产安全封板仍须独立 Real OLS deny，不能用 Test A 或历史 PASS 替代。

专项交接见 [M6.4.1](milestones/m6/m6_4_1_test_asset_governance_and_post_final_closure.md)。M6.4 既有 Local/Cloud Real、Int64、lineage、完整性、报告来源、owner/RLS/late-stale 验收不重新打开。本轮无生产事实链变更；发布须本轮 Final commit 自身完整 exact-SHA CI、Remote Audit 和 clean，不继承 M6.4 CI。

Cold Start：fetch origin → main/HEAD/origin/status/staging/diff/log；本轮起点必须为上述 M6.4 Final SHA。仅白名单改动；未知修改或 remote drift 停止。外部根使用 PBIAGENT_TEST_ROOT；本地 runner 显式 milestone/run cache_dir，CI 保持原方式。Local parent180/child120/DAX30 合同不变。

本地 runner 已使用正确引用的正斜杠路径和 canonical owned temp；误生成五目录共2,928文件已归档并由用户清理，根因/失败证据保留，当前清理阻塞已解除。README 改为项目首页；配置排障及历史信息分别落在09/专项文档。fresh gates已通过，Settings.version=M6.4.1；发布按自身CI/Audit/clean生效。

## 稳定运行入口（README移出细节）

- Conda首次PowerShell激活异常可执行 `conda init powershell`，重开终端后激活PBIAgent；
  用 `python -c "import sys; print(sys.executable)"` 确认当前解释器。uvicorn缺失先检查环境。
- dotenv只接受KEY=value、注释与空行；`python scripts/check_startup_config.py --env-file .env`
  只报告安全配置状态/非法行号，不输出Secret。端口占用先确认owner/命令行，不能盲目关闭进程。
- Kimi配置使用 `LLM_MODE=openai_compatible`、`LLM_DEFAULT_PROFILE=kimi-k2.6`、
  KIMI_BASE_URL/KIMI_API_KEY及 `KIMI_MODEL=azure/Kimi-K2.6`；用户自有gateway，禁止dump或自动fallback。
- health仅证明配置，不探测Desktop在线；model catalog/probe才证明当前实例能力。
  Local parent180/child120/DAX30、MAX_TOOL_CALLS=8、readonly合同保持。
- Cloud要求ENTRA_BFF+fabric_iq，同源callback与cookie配置由operator管理；LOCAL_DEV+local_mcp
  是Desktop入口。session200后403先区分服务初始化、policy/grant和Microsoft资源拒绝。
  query_execution/external_llm_disclosure/business_persistence各自默认关闭，登录不自动授权。
- SQLite支持历史/搜索，Memory/Snapshot恢复仍按完整payload与终态证据；HTML由文件repository管理。
  LOCAL_DEV conversation API显式namespace、page1–50及opaque cursor；Cloud接口以OpenAPI为准。
- 本地pytest/semantic/frontend/Real工具必须由canonical runner设置cache/TMP/TEMP/output；
  仓库既有用户local_state、tmp等不在本轮删除授权内，不读取或搬迁业务数据。

本轮fresh：后端3521PASS/1SKIP/15既有warnings、Semantic819PASS、Golden11PASS/1manualSKIP、前端160PASS、Typecheck/Lint/Build及治理门PASS；补充runner/IQ负例16PASS。Local/Cloud Real未重复运行（无事实production行为变化）；不能计为fresh Real PASS。中文发布提交为`M6.4.1_测试资产治理与封板遗留收口`；自身CI/Remote Audit/clean全部成立后FINAL COMPLETE并STOP，不进入M6.5。exact-SHA回执按main当前提交和外部Governance解析，不继承旧CI。

## 此前阶段记录（历史，不作为当前下一步或Final CI）

> Settings.version=M6.3；M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ correctness IQ_ACCEPTED；M6.4 Round 2 Final Closure进行中（Local timeout恢复既有合同并Real PASS）；M5.10.9 COMPLETE；M5.10.9 FIX COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一开发交接 authority；当前项目状态见 [07](07_milestones_status_and_open_questions.md)，路线见 [08](08_development_roadmap.md)。

## 当前阶段 — M6.3 / M6.4 Round 2 Final Closure

2026-10-15 用户授权继续同 Round 2 Final Closure，取代下方此前 STOP。Cold Start：main、HEAD=origin/main=d943d02d32140a605a33dd0aca928dbd420e344a，staging 空；44项既有 Round 2 成果完整保留。Local timeout 根因已证明为运行配置漂移：Settings() request=120、禁用 dotenv 后=180，child LLM=120；未读取或修改 dotenv。既有正式合同（ERR-5106-008）为 parent 180 / LLM、MCP、render child 120 / DAX 30。fresh 120复现：Understanding 4.468秒，Coverage在剩余115.532秒时开始，115.547秒后被parent deadline取消，request总计120.015秒；业务DAX未进入，metadata preflight曾经Gateway/MCP。没有重复扣减或取消传播implementation bug证据。仅进程级恢复REQUEST_TIMEOUT_SECONDS=180，不改production timeout代码或SLA。原完整九查询/九VerifiedFactSet/九section专业报表最终16.688秒PASS，来源Power BI Desktop、无事实裁减、无fallback、MCP/worker残留0。原115.781秒失败与fresh诊断原件保留在仓库外20261014-round2证据目录；不回填原失败缺失的绝对时间。Cloud Final原生session、late/stale及fresh Full Gates继续；Settings.version=M6.3，未staging/commit/push，无本轮Final自身CI/Audit。

此前停止记录（由上方当前授权取代）：Cloud Real 后 Local 完整专业 Report 复验两次 TimeoutError；原始失败与 timing-only 原生重验均保留。第二个 LLM generate 在 115.781 秒后 CancelledError，外层 TurnPipeline TimeoutError，未到 DAX/render；MCP 2 started/2 closed/0 residual/0 workers。Local Answer PASS。禁止自动第三次重验、修改 timeout、改 M5/LLM/事实链或发布；M6.4 FINAL BLOCKED，Settings.version=M6.3，未 staging/commit/push，无新 exact-SHA CI/Audit。仓库外 release metadata 草稿未运行，其 PASS 前置条件不成立。Admin/Test A 获批 Real、IQ_ACCEPTED、自动化 PASS 不替代该失败。证据已封存，Test A已退出，owned uvicorn/Vite已停止，8000/5173无监听；STOP。根AGENTS/CLAUDE/README仅同步当前阻塞状态，CHANGELOG移除旧技术候选current措辞；均属本轮文档白名单，无版本或治理规则修改。

- Settings.version=M6.3；fresh baseline SHA：d943d02d32140a605a33dd0aca928dbd420e344a；自身Full Validation 38521027447 SUCCESS，23 steps全部success。
- M5 FINAL=true；Core Analysis Kernel 与 Local MVP baseline 已Frozen；查询/事实Core production diff保持0；Report provenance按用户极窄兼容授权例外，未改变事实链。
- M6.4_FIX及Round 1 COMPLETE；同 Round 2 conservative inline 已实施；Fabric IQ唯一Cloud Data Plane；IQ_ACCEPTED；Admin/Test A获批产品Real PASS；Next=完成同Round 2 Final Closure；Local timeout恢复及完整Report Real PASS。
- 当前Real证据及短合同见[IQ decision](milestones/m6/m6_4_iq_data_plane_decision.md)；不继承历史PASS或基线CI作为本轮发布证据。

## Round 2 Cloud metadata最小修复（2026-10-15，新增明确授权）

用户已批准去除重复Schema、请求内exact model/schema新鲜proof去重、Cloud rename减少无关同步、
原deadline内有界退避只读metadata。fresh fetch/main/基线/staging核对通过；官方IQ限流合同已重验。
P0设计见IQ decision；后端failure-first 8FAIL/7PASS，前端1FAIL/23PASS。最小实现后邻近47PASS、安全68PASS、Cloud前端24PASS，Architecture恢复PASS；Semantic819PASS、Golden11PASS/1manualSKIP，全后端3516PASS/1SKIP/15保留warnings、前端160PASS、Typecheck/Lint/Build与治理门均PASS。Admin/Test A普通UI获批Real已完成；Local后置完整Report复验失败，当前STOP见上。
Admin慢速native lifecycle已PASS，仅证明功能/权限可执行，不计产品限流修复；普通启动配置问题已定位并提供独立进程级启动脚本。
普通 uvicorn + Vite 已完成 Admin 登录、获批 Workspace 三模型目录、Rich 已知销售额问答与侧栏重命名；合成 SQLite 只读复核 completed/real/committed 和持久标题均 PASS，未使用验收脚本冷却。新聊天后 Restore 原问答 PASS；两个既有模板均 Real 生成、completed/committed、页面已查看，专业模板 Fabric IQ 来源正确。连续第二个报表后双资源列表刷新仍返回 503 RATE_LIMITED；Auth session 仍 200，已提交报表仍可查看，原生重新加载、重选 Rich 后已 Restore 三个原历史 turn，无重新认证或写操作重放。该失败与截图保留；不能把单次重命名 PASS 解释为上游永不限流。Test A隔离已完成；Local后置完整Report失败为当前唯一blocker。
该授权不改事实链、RLS/OLS/ownership、Local、八Shape或Provider；仍同Round2，M6.3，FINAL NOT READY。

Test A 已亲自登录普通产品，批准目录与模型选择、RLS SCALAR=100、ENTITY_LIST=Region A/单行/未截断/绑定 VerifiedFactSet 均 PASS；Admin-owned History=403、Report=404 且与 unknown 资源 body 相同，session 保留。自有专业 Report 显示 Fabric IQ、已知值一致，侧栏只显示自有两段历史/一份报表，rename 和新聊天后 Restore PASS。Marker NL probe 仅澄清、ZERO ExecuteQuery/事实提交，不冒充 OLS 拒绝；当前 A role 配置允许 RestrictedTable，Test B 不可用按用户批准不作为 blocker，本轮没有新增 OLS deny Real PASS。仓库外 ordinary-native-test-a-receipt.json 保存独立证据。原生 uvicorn:8000 与 Vite:5173 保持运行，无额外验收 endpoint；Cloud后Local Answer已PASS，完整专业Report两次超时；按当前STOP段结束，保持M6.3、未commit/push。Admin 普通 UI 和 lifecycle 证据、限流与正常恢复失败原件保留。

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

## 当前补充验收：限流与普通手动启动（2026-10-15）

用户要求核清产品限流体验与普通前后端启动的权限提示。原生 resource rename 的 Real 回执已出现
RATE_LIMITED；冷却后的 Restore、两个模板 view/download、三轮历史读取均通过，但连续 rename 再次限流。
当前仓库外验收器的冷却/慢速节奏仅用于保留步骤推进，不是产品限流修复，不可据此宣称常规使用体验已解决。
现有 resource mutation 在写入前后重做 Resolve/Schema 校验；去重/退避若实施须保留 caller、exact resource、
policy epoch 与权限撤销安全边界，不能通过省略授权或放宽 Frozen Core 收口。
专用宿主显式加载批准 Workspace 的三个 capability 与 owned synthetic SQLite/report root；普通 Settings 启动
不会自动继承该进程内注入。用户提供普通 uvicorn/Vite 命令与 auth/session=200 后两条 API=403；只读 native startup 诊断确认 ENTRA_BFF+local_mcp，Cloud service 未初始化、operator policy 未配置，足以解释粗粒度 route refusal，不能判为 Microsoft 账号权限不足。仓库外 start-cloud-native-backend.ps1 仅准备进程级已批准测试配置后执行正式 backend.app.main:app；CheckOnly 已证明 fabric_iq/Cloud service/三个 grant 均正确初始化，零 Data Plane 请求、未打开业务存储；完整普通前后端 Real 仍待切换后验证。
普通前后端可复现验收及失败分类须核清；未通过前保持 M6.3，禁止提前 Final Seal。

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

## Round 2 唯一当前交接（2026-10-15）

继续同一 Round 2。用户已明确批准 report provenance enum / presentation compatibility，
原生专业报表来源修复已验证；旧 ERR-64-023 STOP 保留为历史，不覆盖当前授权。
验收宿主 localhost:5173 使用 native Auth/IQ/DeepSeek 与仓库外 owned synthetic DB/report root。
当前继续两个模板 view/download、History/Restore/资源生命周期、Admin/Test A RLS/OLS 与 Local Desktop 回归。
所有验收及 Full Gates 通过后才可升 Settings.version=M6.4、白名单中文 commit/push、自身 exact-SHA CI/Remote Audit。
不改变事实链、M5 查询语义、IQ 数值/完整性或新增 Provider；若需要这些改动立即 STOP。
整个 PowerBIAgent-M6-Dev 的测试资源读取授权保持；其它 Workspace ZERO request。
以下旧轮交接均属历史，不覆盖本节或用户当前授权。

## M6.4_FIX / Round 1历史交接（2026-10-14）

M6.0 COMPLETE；M6.1 COMPLETE；M6.2 COMPLETE（保留数值/完整性限制）；M6.3 Security COMPLETE；M6.4_FIX COMPLETE。
Previous green main：`81d3b2e78330936504361494e3fdd90bd2fadcd3`；
[该SHA的Full Validation 38503188109](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38503188109) SUCCESS。
旧失败与复现保留在[工程专项](milestones/m6/m6_4_fix_engineering_closure.md)及
[运行时专项](milestones/m6/m6_4_fix_runtime_regressions.md)，不是当前发布失败。

Round 1只整理Cloud边界：workspaces[1..100]逐Workspace独立model/report批准；只定向metadata，
未批准资源ZERO request。正式current-principal Catalog不变；Resources经Resolve/Schema复证。
Auth/CSRF/coarse route归Middleware；资源访问、执行、披露和持久化各由service明确拒绝/验证。
AUTH_REQUIRED/AUTH_EXPIRED才注销Session；resource-level AUTH_FORBIDDEN、不可访问、Schema/Model
及Test Scope拒绝不注销，有关transient binding/selection局部失效，其它资源继续工作。
前端401清登录，resource403局部恢复，execution403保留Catalog/合法Selection，409同步server state；
临时network/5xx保留登录，generation与迟到身份/数据拒绝合同保持。
Recovery focused后端159PASS、前端36PASS；完整本地Gates及发布以仓库外分层回执为准。
当前Round 1新提交只有自身Main Full Validation SUCCESS + Remote Audit + clean后才能判COMPLETE；
成立前为待发布验收，禁止继承previous green CI。自身SHA不写入自身提交。

Real Query Execution / External LLM Disclosure / Business Persistence继续BLOCKED；Synthetic不计Real。
Remaining work：Data Plane correctness + approved Real E2E；真实业务执行/披露/留存许可和native策略
仍为验收前提。M6.4 FINAL NOT READY；Settings.version=M6.3；M5 Frozen Core diff=0。
证据目录PBIAgentTest/M6.4/Acceptance/20261014-round1；当前是Round 1 Final Closure，无Round 2实施授权。
发布完成后立即STOP，不启动Data Plane、Real E2E或后续阶段。下文全部为历史，不覆盖当前交接。

## 旧solo轮交接（2026-10-14；历史）

进入main基线5b0f22d913dcf47af53903f8b4fae1d3162d2dc1、自身CI已SUCCESS；不重发候选。
本轮native ENTRA_BFF已安全装配Product Service，但business gate关闭，deferred仓库不打开DB；
直接service embedding也不能绕过gate进入Core/外部LLM。正式事实回调与固定Renderer通过完整
Synthetic API/React client链，MOCK来源及owner存储保持，不能作为Real PASS。
[一次合同技术决策与最终差异核验](milestones/m6/m6_4_iq_data_plane_decision.md)为本轮未决清单。
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
仓库外临时只读审计：PBIAGENT_TEST_ROOT/M6.4/Acceptance/legacy-root；不由production导入，不读取/迁移业务DB。
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
仓库外工具与safe evidence位于PBIAGENT_TEST_ROOT/M6.3/Acceptance；本轮Late synthetic存储位于PBIAGENT_TEST_ROOT/M6.3/LateResponse；fixture位于PBIAGENT_TEST_ROOT/M6.3/Fixtures。
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
