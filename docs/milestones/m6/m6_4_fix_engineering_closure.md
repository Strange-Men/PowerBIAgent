# M6.4_FIX — 工程偏移修复

日期：2026-10-14。用户授权独立 FIX，基线 main@6e8643ba15f4a6f6215f152408c054658fcd5f1f。
状态：本地工程验收PASS；M6.4_FIX COMPLETE仅以本提交自身CI与Remote Audit及clean生效；M6.4 FINAL NOT READY；Settings.version=M6.3。

## 实施前 P0 合同

Fresh fetch 成功，main/HEAD/origin/main 相同，初始 worktree/staging clean。
Microsoft 官方 IQ、Execute Queries JSON、Execute DAX Queries Arrow 页面已于本轮重新读取。
本轮不调用 Microsoft 业务服务或外部 LLM，不读取历史 DB、PBIX、真实业务证据。

资源管理复用 PrincipalScopedRepositoryFactory、ConversationHistoryService、PrincipalReportRepository
和既有 ResourceManager/Sidebar。只有正式资源 API 可以写资源，不能注册 LLM 删除工具。
列表、搜索、历史、报表及操作先校验当前 Auth Principal，再验证 owner 持久 exact model binding、
当前 Resolve/Schema fingerprint 与权限；缺投影拒绝。异步操作前后验证 session/selection generation。
破坏当前会话的生命周期操作先使旧 generation 失效，后续提交使用新租约；跨用户 cursor 保持签名隔离。
报表独立删除复用 durable delete intent 和 History tombstone，不删除会话。

企业数据边界由服务端拥有：问题、schema、成员、QueryResult、VerifiedFactSet、LLM I/O、Memory、
Snapshot、History、HTML、Trace 和测试证据不能凭客户端 synthetic/consent 标志获得披露或留存许可。
本 FIX 无企业数据授权，native business execution/disclosure/retention 保持拒绝；不提供配置开关。
合成路径只接受受信任 host 注入的 Mock Adapter/Mock Provider，public/persisted provenance 必须 MOCK。
Auth/Transport token 与权限缓存按既有 session/epoch 隔离；安全日志只保留必要类别、状态和计数。
generic Secret Redaction 不是业务 DLP。历史资源授权不能从历史 owner 或旧 cache 推导。

## 验收记录

| 已确认偏移 | 修复与证据分类 |
|---|---|
| Cloud资源只有Recent与不可用按钮 | cloud_routes / cloud_product_services复用既有分页、搜索、全历史、rename/archive/unarchive/delete；CloudWorkspace / ResourceManager / Sidebar复用原Settings与批量契约。SYNTHETIC_PASS |
| 全历史恢复最多500条 | client保留逐页上限与cursor防循环，遍历完整历史；client.test验证550条/11页及每页AbortSignal。SYNTHETIC_PASS |
| 报表独立生命周期与删除中断 | 原report repository与History tombstone不删会话；get_for_delete只读owner intent，当前exact binding复证后恢复HTML清理；下载不暴露intent。SYNTHETIC_PASS |
| 撤权/Principal/旧response风险 | current Auth、exact model、fingerprint、ResourceLease验证SQL/commit；当前会话archive/delete先new-chat使旧响应失效；前端401/403清空资源并失效generation，Settings/search不接受旧页。SYNTHETIC_PASS |
| 通用redaction被当作企业许可 | 服务端require_cloud_business_data独立于execution gate拒绝非Mock执行/LLM/留存/历史下载；Deferred开库前拒绝。客户端synthetic/disclosure/retention不能授予权限。CONTRACT_PASS；未实现企业许可或DLP分类器 |
| Mock/API200冒充Real | formal factual callbacks的合成桥与全部结果/存储显式MOCK；新matrix覆盖八Shape、正式多轮、两固定模板、非Sales目录、Provider/Int64拒绝；旧incomplete/idempotency/isolation负例复用。SYNTHETIC_PASS |
| 文档把旧阶段状态当当前 | 07/08/09及入口同步；旧正文保留并标历史；PRD/ADR-020/M6.5–M9目标不改。技术决策ALTERNATIVE_CANDIDATE，不迁移 |

新增资源failure-first先3 FAIL（缺API）；删除中断report retry先1 FAIL/1 PASS，最小owner-intent读取修复后PASS。
合成专业报表夹具先被来源校验拒绝；仅测试host在原validator前使用TEST_FIXTURE，保持MOCK，不改变Core/validator。
新resource+shape matrix 22 PASS；最终全量结果见下节。失败不是Real上游证据。

累积M5最终至起始main简短审计：Auth/Adapter/Repository/Service/UI扩展为主；此前已获批DTO声明兼容
保留。本FIX无Frozen Core改动、无第二Planner/Memory/事实链；未新增Provider/Shape/模板/Renderer设计。
未读取或清理历史DB/PBIX/用户数据；自动生成与删除只限新合成资源。

### 复现及证据

PowerShell设置LLM_MODE=mock、POWERBI_MODE=mock、PYTHONUTF8=1。
`python -m pytest backend/tests/api/test_cloud_resource_lifecycle.py backend/tests/api/test_cloud_product_shape_acceptance.py -q`
复用test_cloud_product_api / test_cloud_factual_e2e / test_cloud_bound_recovery / test_cloud_privacy_boundary。
`npm test`包括CloudWorkspace.factual.test：真实API client通过stdio接入离线FastAPI，Fake Entra→Catalog→
选择→正式Grounding/Plan/DAX→ResultInspection/VerifiedFactSet→Answer/Report→History/Restore→Settings资源操作。
这是可复现模拟身份产品链，非原生Entra登录或真实浏览器Real。既有Mock数据、有限人工值均不授予Real PASS。

本轮新输出仅在`D:/AAA_Workfile/PBIAgentTest/M6.4_FIX/Acceptance`；不读旧测试证据目录。
完整本地后端/前端日志、治理结果和最终发布receipt由当前实际checkout SHA解析；不在提交正文写自引用SHA。
CI及Remote Audit全部通过且clean才M6.4_FIX COMPLETE，否则BLOCKED。

本地全量：backend 3359 PASS / 1 SKIP / 13既有warnings；随后最终资源9 PASS（追加intent撤权负例及title长度合同后）。
Semantic Compatibility 819 PASS；Golden 11 PASS / 1 manual Real SKIP；Repository Safety、Error Ledger、
Architecture、Documentation、Artifact Governance PASS。前端Typecheck/Lint/Build PASS；最终全量144 PASS，
Settings迟到页不返回旧Principal资源；最终资源/八Shape/两模板/隐私矩阵28 PASS。
保留本轮验证失败：Sidebar同步effect触发lint，改授权状态key重挂载后PASS；新测试按钮名错误修正后PASS；
一次定向前端命令未指定Conda Python导致bridge缺pytest，指定现有测试解释器重验，不改依赖/CI或隐藏错误。

### M6.4 FINAL 最少未决Gate

1. 可信Int64/完整性合同和八Shape真实数值；当前native IQ仍BLOCKED。替代接口须另行批准。
2. 自有合成模型或原M6获准逐资源测试环境、当前Principal/RLS/OLS与服务规则；账号可见性不自动授予测试。
3. 明确企业披露/留存许可后最小实现对应native策略，并通过撤权/迟到写入/下载负例；当前仅拒绝政策。
4. 原生Entra/Catalog→Chat/Facts/Answer/两报表→History/生命周期的获准真实浏览器E2E及本阶段最终SHA CI/Audit。

BI与外部LLM真实请求均0：Real NOT_TESTED/BLOCKED，REAL_PASS无新增。Settings.version=M6.3。
FIX结束立即停止，不启动M6.4.1/M6.5/M6.6。
