# 07 — 当前项目状态

> Settings.version=M6.4；同Round 2 Final Git Seal待自身exact-SHA CI/Remote Audit/clean；M5 FINAL/FROZEN有效。

## 当前状态

同一 M6.4 Round 2；必要Local/Cloud Real与版本更新前fresh Full Gates已通过，Settings.version=M6.4。
当前为Final Git Seal待验；只有最终实际main提交自身PowerBIAgent Validation / Full Validation (Windows) SUCCESS、required checks成功、Remote Audit、HEAD=origin/main及worktree/staging clean全部成立，才解析M6.4 FINAL COMPLETE；随后STOP。自身SHA不写入自身提交，不继承旧SHA CI。

Local根因是dotenv来源旧request=120覆盖既有正式parent=180合同；child LLM/MCP/render=120、DAX=30不变。fresh原120秒复现Understanding=4.468秒、Coverage在剩余115.532秒开始、115.547秒后parent取消、累计120.015秒，业务DAX未进入；原115.781秒失败原件保留。无deadline实现bug证据，仅进程级恢复REQUEST_TIMEOUT_SECONDS=180，未读取/修改dotenv或production timeout代码，不扩大SLA。原完整专业Report最终16.688秒Real PASS，三合法LLM阶段、九DAX/九VerifiedFactSet/九section、Power BI Desktop来源、无功能裁减/fallback、MCP/worker残留0。

Cloud原生Admin与Test A Final当前Real PASS：既有owned专业Report view/download、History/Restore、cross-owner History=403/Report=404且与unknown body相同、越权mutation拒绝且session保留、Test A RLS scalar=100/Region A列表绑定VerifiedFactSet。Admin迟到History/Report均403、在途真实DeepSeek响应失去generation后403、ZERO事实Memory/Snapshot；stale generation=409。已成功的rename/archive/unarchive/delete生命周期保持本Round有效checkpoint，未重放非幂等写入。Test A首次Final尾部与普通UI并发产生409，失败保存，仅续跑剩余步骤PASS。既有用户批准Test B不可用例外保留：A允许RestrictedTable，本轮不宣称OLS deny Real PASS。

IQ_ACCEPTED保持；Fabric IQ唯一Cloud Data Plane，REST只作Catalog/Metadata。整个PowerBIAgent-M6-Dev Workspace含未来测试资源获批，其外ZERO request；三个operator test grant独立默认false，测试批准不是production授权。保守inline business N=min(request.max_rows,12)、wire=N+1、最多8列/104cells/66 ASCII JSON bytes每cell或name/8192bytes execution；CSV/超界/unknown/incomplete在Facts前拒绝，不宣称任意大结果完整。Local max_rows=1000和Frozen事实链不变；仅此前获批Report provenance兼容例外。

本轮fresh：Full Backend 3516 PASS/1 existing manual SKIP/15保留warnings；Frontend 160 PASS；Semantic 819 PASS；Golden 11 PASS/1 manual Real SKIP；Typecheck/Lint/Build、Repository Safety、Architecture、Documentation Governance、Error Ledger、Artifact Governance PASS。首次Backend仅文档当前阶段版本位置失败，最小修正文档后全量PASS；Frontend worker启动失败及base Python缺依赖原件保留，使用既有PBI_SYNTHETIC_PYTHON配置重跑全量PASS，未改expected。版本更新后完整发布门再次执行；exact-SHA CI仍须独立证明。

登录性能计时：Auth session=0.015秒、native目录=15.36秒（独立复测9.219秒）、模型Schema选择=6.50秒、模板Schema=6.734秒、Restore Resolve+Schema=8.281秒；不是已证明Auth恢复timeout。UI“正在恢复对话”也用于模板验证，性能/文案后续变更不在当前timeout root cause内。上游RATE_LIMITED失败与正常reload/reselect/Restore恢复保留，不重试产品写操作、不取消Microsoft配额。

证据均在仓库外PBIAgentTest/M6.4/Acceptance/20261014-round2：final-timeout-root-cause-evidence.json、final-local-timeout-recovery-receipt.json、final-native-admin-receipt.json、final-native-test-a-receipt.json及final-native-stage-timings.json。测试服务关闭，仓库不含诊断observer/acceptance runner/debug route/DB/PBIX/业务dump/credential。M6.4不等于enterprise production ready；single-process session、SQLite/filesystem、Preview MCP、LLM长尾、配额及既有MSAL/Alembic warnings公开保留。M6.5/M6.6未启动，后续须独立授权。

## 此前阶段记录（历史，不作为当前下一步或Final CI）

> **状态：** Settings.version=M6.3；M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ correctness IQ_ACCEPTED；M6.4 Round 2 Final Closure进行中（Local timeout恢复既有合同并Real PASS）；M5.10.9 COMPLETE；M5.10.9 FIX COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一当前项目状态 authority；路线见 [08](08_development_roadmap.md)，开发交接见 [09](09_context_handoff.md)。

## 当前状态

同Round 2 Final Closure：旧运行配置parent=120覆盖既有正式180秒合同，child LLM/MCP/render=120、DAX=30不变。fresh复现Understanding=4.468秒，Coverage剩余115.532秒开始，115.547秒后parent取消，总计120.015秒，业务DAX未进入；原115.781秒失败原件保留。仅进程恢复REQUEST_TIMEOUT_SECONDS=180，无production timeout代码或SLA变更、无implementation bug证据。原完整专业Report最终16.688秒Real PASS：三个合法LLM阶段、九DAX/九VerifiedFactSet/九section、Power BI Desktop来源、无功能裁减或fallback、MCP/worker残留0。Cloud Final原生复验和最终fresh gates继续；Settings.version=M6.3，未staging/commit/push，无本轮Final自身CI/Audit。证据在仓库外20261014-round2/final-timeout-root-cause-evidence.json及final-local-timeout-recovery-receipt.json；正式合同见ERR-5106-008。

| 项目 | 状态 |
|---|---|
| Current Version | M6.3 |
| Current Release State | M6.3 Security COMPLETE；以Final自身exact-SHA CI + remote audit生效；IQ correctness已证明，产品Final未验收；M5 FINAL=true |
| Frozen | M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN |
| Post-final | M5.10.9 FIX COMPLETE — documentation semantic consistency / CI test stability forward-fix |
| Next | 当前Round 2 Cloud Final、fresh Full Gates、自身CI/Audit后STOP；不启动M6.5/M6.6 |
| Current implementation status | Round 1 COMPLETE；Round 2 IQ_ACCEPTED（Int64、completeness、8/8 Real）；Native capability/Workspace 边界已实施；Admin/Test A 获批产品 Real PASS；Local timeout配置恢复及完整Report Real PASS；Final复验继续 |
| Ready state | Fresh main baseline d943d02d32140a605a33dd0aca928dbd420e344a；自身Full Validation 38521027447 SUCCESS（23 steps）；不是Round 2发布CI |

## Round 2 Cloud metadata最小修复（2026-10-15，新增明确授权）

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

## M6.4 Round 2 前次合同失败（2026-10-14，历史）

最新用户明确授权继续同 Round 2。Fabric IQ MCP 为唯一 Cloud query Data Plane；禁止新 Provider 或 Frozen Core 修改。
fresh runtime/raw envelope 已读取：structuredContent 仅 citation，无 CSV column type metadata。
按用户允许的 conservative inline 路径，实测宽表 18→19 行转换 CSV；更小 profile N=12、wire=13
已证明 0/1/N/N+1、overflow 与重复完整性。Int64 min/max/null 及 2^53±1 精确通过。
最小 IQ boundary failure-first 实施及相关 227 tests PASS；M5 Core production diff=0。
用户批准的原合成模型日期补充与刷新完成，原定义备份及官方 TOM/TMDL 校验保留。
SCALAR Real PASS；ENTITY_LIST 返回已知 A/B 两行且未截断，但 IQ 列名为 `FactSales Region`，
canonical 字段为 `Region`。raw descriptor 只有 name/type，无 canonical lineage；
ResultInspection 拒绝 `result_inspection_field_missing_or_ambiguous`。不从 friendly label 推断身份，
不改 Frozen Core、不绕过事实验证；其余六形状未运行，八 Shape 未全部 PASS。
[短合同与当前证据](milestones/m6/m6_4_iq_data_plane_decision.md)；IQ_ACCEPTED 未授予。
按本轮新合同根因/八 Shape 停止条件：M6.4 FINAL BLOCKED，STOP。探测服务已关闭；
执行/披露/留存未开启；Admin/Test A 产品、Local Desktop 与发布未完成。
本地后端3413 PASS/1 SKIP/15 warnings，前端159 PASS；Semantic819、Golden11/1 manual SKIP，
Typecheck/Lint/Build及治理检查通过，仅计 Local automated，不能替代 Real 或自身 SHA CI。
Settings.version=M6.3；没有本轮 commit/push，不继承 baseline CI 封板。
Test B 不作为 blocker；一个批准 Real Workspace 加既有多 Workspace synthetic matrix 可验收。
此前 CSV STOP 为历史，已被最新 continuation 覆盖；不创建新 Round，不自动进入 M6.5。
以下旧轮记录均属历史，不覆盖本节。

## M6.4_FIX / Round 1历史状态（2026-10-14）

M6.0 COMPLETE；M6.1 COMPLETE；M6.2 COMPLETE（保留Int64/完整性限制）；M6.3 Security COMPLETE；M6.4_FIX COMPLETE。
Baseline / previous green main：`81d3b2e78330936504361494e3fdd90bd2fadcd3`；
[自身Full Validation 38503188109](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38503188109) SUCCESS。
旧FIX与运行时失败只保留在[工程专项](milestones/m6/m6_4_fix_engineering_closure.md)及
[运行时专项](milestones/m6/m6_4_fix_runtime_regressions.md)，不作为当前失败状态。

Round 1 Boundary Cleanup：operator配置为workspaces[1..100]，每Workspace独立model/report白名单，
metadata只定向请求；单资源拒绝不注销有效Session。Authentication/Resource/Test Scope/Execution/
Disclosure/Persistence分开；只有AUTH_REQUIRED/AUTH_EXPIRED注销Session，资源403局部恢复，
execution-blocked保留Catalog/合法Selection，409同步服务端状态，network/5xx保留登录。
Recovery focused后端159PASS、前端36PASS；完整本地Gates与发布结果按本轮仓库外回执解析。
Round 1已以d943d02d32140a605a33dd0aca928dbd420e344a自身Full Validation 38521027447 SUCCESS、
Remote Audit及当轮clean正式COMPLETE；该发布证据不证明Round 2验收。

Real Query Execution、Real External LLM Disclosure、Real Business Persistence仍BLOCKED。
Remaining work：Data Plane correctness（精确数值/完整性）+ approved Real E2E；
真实业务执行/披露/留存的许可与native策略仍是上述验收前提，本轮不开放。
M6.4 FINAL NOT READY；Settings.version=M6.3；M5 Frozen Core diff=0；Round 2未实施。
本轮安全证据和exact-SHA CI/Remote Audit回执位于PBIAgentTest/M6.4/Acceptance/20261014-round1。
完成本轮即STOP；下文同日solo及早期段落全为历史，不覆盖本节。

## M6.4 旧solo轮记录（2026-10-14；历史）

稳定进入基线5b0f22d9已通过自身CI。本轮仅原M6.4：native ENTRA_BFF安全装配Product Service，
延迟storage在业务gate前不开库；直接native服务调用也先校验租约和关闭的执行gate。
新增正式事实回调/固定Renderer的完整Synthetic API与React真实client E2E，不将Synthetic计Real。
Catalog、Chat/History/Report合成接线及owner/撤权/迟到响应验证完成；Settings资源管理仍PARTIAL。
Int64/八Shape完整性无新可信合同；企业披露/留存策略与当前获批Real仍BLOCKED。真实调用0。
[一次技术决策及六项最终差异核验](milestones/m6/m6_4_iq_data_plane_decision.md)区分内部缺口与外部依赖。
Settings.version=M6.3；M6.4 PARTIAL/BLOCKED，不能封板。本轮完成后停止，不启动后续阶段。
本轮分层日志和exact-SHA CI/Remote Audit回执在PBIAgentTest/M6.4/Acceptance/20261014-solo。
当前checkout发布SHA须通过自己的完整CI；不继承5b0f22d9或候选CI。
## M6.4 当前开发（2026-10-13，阶段候选；非 Final Seal）

### 候选后的定向收口（2026-10-13）

基于已通过exact-SHA CI的候选`4f17b9319b6310e511d6754d36062b59edcf393a`继续用户授权scope；候选CI不重复运行。
本轮Cold Start已成功fetch并核对clean main；GitHub连接采用本次公共DNS验证后的命令级解析恢复，未改变系统或长期Git配置。

| 原定模块 | 本轮状态与边界 |
|---|---|
| Catalog / Allowlist | DONE（本地）；保持定向测试范围与逐调用拒绝，正式current-principal架构不变 |
| Chat / History / Report API | DONE（受控合成接线）；原生FabricIQ业务仍BLOCKED；旧历史无绑定拒绝 |
| Cloud选择 / 新会话 / 恢复 / 模板资格 | DONE（合成）；owner不可变exact绑定与Resolve/Schema复证，模板显式资格 |
| Settings / 前端恢复 / 跨会话竞态 | DONE（合成）；Chat/历史/报表链接接线，401恢复与abort/generation拒绝旧响应 |
| Principal / 撤权 / RLS-OLS | 合成Ownership与撤权DONE；真实RLS/OLS仍NOT_TESTED |
| Int64 / 八类Completeness | BLOCKED；无新增可验证Microsoft wire合同，保留严格类型与truncated=true |
| 企业隐私P0 / 完整Real E2E | PARTIAL/BLOCKED；native业务存储前拒绝，本轮BI与外部LLM真实调用0 |

新增迁移只在合成临时SQLite验证，没有打开、迁移、删除或搬迁真实DB；既有migration head断言改为解析当前head，数据结构/owner负例不变。
Mock报表只验证原Mock链与受保护API/HTML，不能作为正式Renderer、VerifiedFactSet或Real PASS。
正式外部LLM业务披露保护仍需最小化/批准的输入输出及持久化策略；通用Trace/Provider不是业务DLP。原M5 Frozen Core本轮无修改。
本轮质量/发布回执统一在`PBIAgentTest/M6.4/Acceptance/20261013-directed`；实际新main提交必须通过自身一次完整CI和Remote Audit。
Settings.version=M6.3；M6.4 PARTIAL/BLOCKED、Final NOT READY。上轮候选发布授权已完成，本轮仅发布通过本地门槛的定向必要修改。
定向最终本地：后端3329 PASS/1 SKIP/13 warnings，前端141 PASS与Typecheck/Lint/Build；Semantic819、Golden11/1 manual Real SKIP与全部治理检查PASS。
候选文件33项Secret/新增身份扫描无风险命中；本轮真实BI/外部LLM请求0。新提交的CI与Remote Audit以actual main SHA回执解析。

用户最新明确授权一次M6.4阶段候选提交、正常Push main、该exact SHA Full Validation CI及Remote Audit；范围冻结，不新增功能。
本轮fresh fetch成功，main/HEAD/origin/main一致，暂存区为空；48项既有源码/测试/文档修改与上一轮最终清单一致。
候选基线以提交标题`M6.4_云端产品阶段候选与安全边界`对应的当前checkout exact SHA及远端回执解析；不继承历史CI。
Settings.version继续M6.3；M6.4保持PARTIAL/BLOCKED、Final NOT READY。后文历史“不Commit/Push”限制已由本次候选授权替代；Final仍须全部原定验收。
未验证业务HTTP、测试History/Report回放与外部LLM准备继续fail closed；Real NOT_TESTED/BLOCKED不妨碍安全候选提交，不计Real PASS。
fresh本地质量门槛、候选CI与远端审计结果见[专项候选收口记录](milestones/m6/m6_4_cloud_product_e2e.md)。

最新测试隔离轮本地后端3275 PASS/1 SKIP/12 warnings，隔离31项；前端132 PASS与Typecheck/Lint/Build，Semantic819、Golden11/1 manual Real SKIP；必要Real及完整Chat→Facts→Answer/Report未通过，未提交发布。

测试Workspace强制隔离已本地实现，定向逐项REST及Adapter/Transport allowlist默认拒绝；原始回执/seed身份本机匹配。企业隐私P0仍PARTIAL，History/Report/外部LLM链保持拒绝；Real未运行，M6.4未发布。详见专项最新测试隔离章节。

[本轮合同与分层证据](milestones/m6/m6_4_cloud_product_e2e.md)。Charter旧状态与08的M9规划已先行修正。
Catalog增加current-principal只读REST与逐模型Resolve/Schema验证，复用ToolGateway和现有Adapter。
恢复开发已接正式Cloud控制面接口、显式模型选择、Settings/Data与既有Composer；业务执行入口仍关闭。
用户另行明确批准model_semantic_context.py六处类型兼容声明，None仍为未知、fabric_iq来源保留；其他Frozen Core不改。
Viewer A已完成真实登录；本轮Real Catalog PASS（6个可访问模型），目录仍诚实标为PARTIAL。
首轮三条固定查询在ToolGateway前置策略处被临时harness遗漏的模型授权上下文阻断，尚未到达ExecuteQuery；
仓库外最小接线修复经12项OFFLINE测试通过；Viewer A重新登录后，三条查询均已真实到达ExecuteQuery。
COUNTROWS严格数值与独立预期匹配（但truncated=true）；销售额标量/分组在HTTP wire和SDK中均为Int64列配字符串，FAIL CONTRACT_DRIFT。
三条响应均无完整性信号，官方合同重验仍不足，严格CONTRACT_DRIFT与truncated=true保留；不是登录或consent停点。
Viewer B正式首页已发现15个已验证模型（含获准共享synthetic fixture）；REST的18工作区目录完成，123候选的IQ授权串行耗尽预算。
已复用有界并发和同一deadline返回scoped PARTIAL；后续Real选择遭遇RATE_LIMITED，模板资格本轮未通过。
新负例定位未知授权失败误计不可访问并继续扇出；最小修复停止当前批次、drain任务并保留unverified范围，Real复验待新native会话。
CloudProductServiceFactory复用既有TurnPipeline/owner repositories；新增History和Report owner只读组合，身份在await前后重验。
正式业务API、Cloud Chat/History/Report前端完整链和会话恢复尚未完成；最新前端131项/Lint/Build通过，后端全量3244 PASS、1 SKIP、12 warnings。
八类Shape已逐项研究，SCALAR与标量FILTERED_AGGREGATION在既有合同内存在候选证明路径，但尚未取得可信Real证明；不要求所有问题无条件等待Microsoft。
Settings.version=M6.3，M6.4发布仍NOT READY。
本轮按用户明确许可，在fetch失败后以GitHub连接器核对相同main SHA，仅继续本地开发/测试。
成功fetch且远端基线未变化前禁止Commit/Push/Final Seal；该临时例外不改变长期Git规则。
本轮有界fetch曾失败并用连接器核验；最新HTTP/1.1 fetch已成功，main/HEAD/origin/main仍为原基线，staging为空。
产品Adapter新增完整性保护，正式API继续关闭。

用户补充企业数据P0并确认公司及账号所有者完整授权尚未确认；受影响Real操作暂停，本人创建的原生Real服务已停止。
暂停前最后一次目录返回6个已验证模型、明确115个尚未验证，获准synthetic fixture模型选择成功；模板资格及业务Real链未通过。
合成开发继续：模型名称本地筛选、隐私边界审计、LOCAL_DEV合成问答/新聊天/历史恢复已验；结果不计Cloud Real PASS。
DeepSeek/Kimi通用Provider实际可接收上层columns/rows；两个profile仅经in-process合成wire验证，未向外部发送企业数据。
现有Secret scrubber不是业务数据DLP；History/Report当前模型RLS/OLS重验与跨登录绑定未完成，P0保持PARTIAL/BLOCKED。
仓库外六目录仅脱敏风险扫描，十个历史DB及二进制/归档等内容未读；风险候选不能冒充已确认泄漏或“安全PASS”。
P0证据在PBIAgentTest/M6.4/Acceptance/p0_privacy_audit.md；同样约束用户提及的M6.4.1 PREP边界，不新增版本或实施范围。
当前可运行服务仅LOCAL_DEV合成实例；公司/账号授权明确前不恢复企业Real，也不向外部LLM发送真实BI或敏感Schema。

## M6.3 安全里程碑

[完整合同、证据与遗留问题](milestones/m6/m6_3_multi_user_ownership_authorization_rls_ols.md)。
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

Phase A exact-SHA CI已全步骤success；Final采用管理员同受保护的PR路径。最终基线按09解析，禁止继承候选或M6.2 CI代替Final证据。

## M6.2 已发布基线

2026-10-10用户明确批准Fabric IQ只读Data Plane scope。
[合同与验收](milestones/m6/m6_2_fabric_iq_cloud_adapter.md)：独立SDK transport、request/session绑定Adapter、
required capability negotiation、schema-before-bind、unknown metadata与结果完整性fail closed。
Settings.version=M6.2；两模型Real与Phase A全步骤CI通过；最终自身CI38012437829与remote audit已重验。
M6.2封板时ownership尚未实施；当前M6.3进度见上节。Cloud Catalog / Product E2E未实施；ENTRA_BFF旧/api仍关闭。

## M6.1 历史封板

用户2026-10-09已批准身份/登录/Session/Account scope。实现与安全合同见
[M6.1 evidence](milestones/m6/m6_1_entra_identity_login_session.md)。Settings.version=M6.1；
LOCAL_DEV保留M5，ENTRA_BFF只开放Auth/Account/安全diagnostics。
ENTRA_BFF multi-user persistence: NOT ENABLED BY DESIGN UNTIL M6.3 OWNERSHIP。
首次Real OAuth前人工Portal配置停点已完成；真实login/callback/account/reload/logout与跨标签退出PASS。Phase A exact-SHA CI全绿；COMPLETE marker以最终封板自身CI全绿、fetch后HEAD==origin/main、worktree clean生效。M6.1封板时M6.2未实施；当前实施见上节。

## M6.0 历史审计

[M6.0 evidence](milestones/m6/m6_0_fabric_iq_cloud_contract_audit.md) 与
[ADR-020 ACCEPTED](adr/ADR-020_fabric_iq_cloud_consumption_and_catalog_authority.md)：Fabric IQ GA、
delegated-only、两模型resolve/schema/query PASS；DiscoverArtifacts名称搜索仍empty，属于已知限制。
Fabric REST current-principal workspace/model/report listing作为M6.4 scoped catalog authority，
管理员seed补共享资源，明确partial coverage；BFF delegated code/PKCE为M6.1推荐。
Product/Auth UX为设计合同；当前ChatGPT reference可靠访问受限，现有前端视觉authority保持。
Phase A exact-SHA CI37904870868全绿后进入最终seal，Settings.version=M6.0。
final自身SHA不写入自身提交；以09的exact-SHA CI / remoteaudit联合解析最终成立状态。
M6.0封板时M5 factual Core与所有production behavior保持，M6.1/2/3/4当时尚未实施；当前M6.1状态见上节。

M5.10.8 与 FIX、M5.10.9 已完成。原 Final baseline：
`86aaaec7d2172c041e97392c3de03adcca77ca1b` /
[CI 36678384015](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36678384015)
completed/success，2026-09-30 fresh REST + fetch 核验。
post-final FIX 只校准文档与治理回归，M5 FINAL=true 持续有效。
最新 FIX 发布基线按 09 的当前 exact-SHA CI / remote audit 解析，不用祖先 CI 代替。
FIX 候选 `9196bb7e52fbc8869daff7233518ac896bc813ca` /
[CI 36686978579](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36686978579)
completed/success；最终 FIX marker 以最终 exact-SHA CI + remote audit 成立为准。

2026-10-09 重新核验：Phase B `953be2683d539fbf4b43d59cca086a3fd598928c` /
[CI 36688714620](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36688714620)
completed/failure；跨 lifespan 的整数 id 断言产生测试假失败，该提交的 FIX COMPLETE 尚未生效。
Phase C `f8641f4d588e1823f521a6d1e9e4e459e6c920f3` /
[CI 37871771667](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37871771667)
completed/success；required check 与全部正常 steps success，fresh fetch 后 HEAD==origin/main、clean。
最终 FIX marker 仍以其自身 exact-SHA CI 与 remote audit 成立为准，不用 Phase C CI 覆盖最终 SHA。

## M5 Core Analysis Kernel 冻结边界

M5 是后续 enterprise productionization 复用的 Core Analysis Kernel。

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

LLM understands. Runtime proves. LLM 仅解释语言并组织 verified wording；runtime Catalog/Grounding
拥有对象/成员绑定，StateTransition/Completeness 拥有可执行 state，Deterministic DAX/Independent
Layer 3 拥有执行校验，ResultInspection/VerifiedFactSet 拥有结果事实。Report 复用同一事实链。
requested_query_scope、observed_data_coverage、available_data_horizon 独立；horizon 只由真实
measure/fact-family + temporal-dimension-aware 数据证明，不能冒充 refresh time。

## Local MVP baseline 与限制

- React + Vite、FastAPI、SQLite/Repository、readonly Local MCP + Desktop、DeepSeek/Kimi Registry。
- 模型感知目录由 backend runtime metadata 确定；Sales 两模板为简易销售分析模板与专业销售经营分析模板。
  Logistics 没有适配模板仍可正常数据问答；未新增物流模板、未放宽 eligibility。
- 当前生成的 HTML Report 是 historical snapshot；真实 refresh metadata 缺失时明确 UNKNOWN。
- 本地 identity、SQLite/filesystem、Preview MCP 与进程内 coordination 尚不具备 enterprise backend 保证。

## 下一阶段与非阻塞风险

下一阶段：M6 — Cloud Consumption & Enterprise Identity；必须另行获批 implementation。
下一实施阶段为M6.4，须独立批准；数值合同P1必须在Product E2E前解决，存储/部署风险见08/09。
Local Modeling MCP Preview、LLM 长尾、无权威刷新时间、本地 single-machine persistence 是已知限制，
不能作为推倒 Core 或提前实现 M6 的理由。

## 证据与历史

M5.10.x 详细变更见 [CHANGELOG](../CHANGELOG.md)、[M5.10.8](milestones/m5/m5_10_8_mvp_final_test_seal.md)、
[M5.10.8 FIX](milestones/m5/m5_10_8_fix_model_aware_report_template_catalog.md) 和
[M5.10.9 evidence](milestones/m5/m5_10_9_documentation_governance_and_final_seal.md)。
post-final 分层证据见 [M5.10.9 FIX](milestones/m5/m5_10_9_fix_document_semantic_consistency_and_m6_handoff.md)。
旧状态长记录保留于 [Historical snapshot](archive/m5_pre_final_07_milestones_status_and_open_questions.md)。
历史 milestone / ADR / archive 不另设当前状态。最终 seal 必须以最终 exact-SHA CI 为准。
