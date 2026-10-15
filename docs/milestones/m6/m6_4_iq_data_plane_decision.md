# M6.4 Round 2 — Fabric IQ Data Plane decision

## 已完成的 M6.4 Final Seal（2026-10-15）

M6.4 FINAL COMPLETE；Final SHA `bdbe7189be21ff043340c2025625a9e3398310b0`，自身 Full Validation 38693083553 SUCCESS，Remote Audit PASS，封板时 worktree/staging clean。当前维护状态见[07](../../07_milestones_status_and_open_questions.md)。M6.4.1 仅将既有 business rows ≤12、wire sentinel=N+1、columns ≤8 明确为 CLOSED_AS_EXPLICIT_LIMIT；Test B OLS deny 为 DEFERRED_BY_TEST_PRINCIPAL。原授权边界、Int64、lineage、QueryShape、completeness 和 provenance 保持。

## 此前Round 2施工证据（历史）

## Final Closure timeout证据（2026-10-15）

同Round 2 Final Closure：旧运行配置parent=120覆盖既有正式180秒合同，child LLM/MCP/render=120、DAX=30不变。fresh复现Understanding=4.468秒，Coverage剩余115.532秒开始，115.547秒后parent取消，总计120.015秒，业务DAX未进入；原115.781秒失败原件保留。仅进程恢复REQUEST_TIMEOUT_SECONDS=180，无production timeout代码或SLA变更、无implementation bug证据。原完整专业Report最终16.688秒Real PASS：三个合法LLM阶段、九DAX/九VerifiedFactSet/九section、Power BI Desktop来源、无功能裁减或fallback、MCP/worker残留0。Cloud Final原生复验和最终fresh gates继续；Settings.version=M6.3，未staging/commit/push，无本轮Final自身CI/Audit。证据在仓库外20261014-round2/final-timeout-root-cause-evidence.json及final-local-timeout-recovery-receipt.json；正式合同见ERR-5106-008。

日期：2026-10-15（Asia/Shanghai）。同一 Round 2；IQ_ACCEPTED；已批准的 provenance fix 已 Real PASS，剩余验收进行中，M6.4 FINAL NOT READY。
Fabric IQ MCP 为唯一 Cloud query Data Plane。Fabric REST 仅用于 Catalog/Metadata；
本轮用户另行批准既有合成模型的 operator-only 日期补充与刷新，不是产品写入能力。
ToolGateway、M5 canonical planning/DAX、ResultInspection、VerifiedFactSet、Answer/Report authority 保持。

## Round 2 IQ FINAL LINEAGE FIX（2026-10-15，当前授权）

### FINAL Provenance Fix 授权与 P0 边界（2026-10-15）

用户已明确批准同 Round 2 的极窄 report provenance compatibility fix，覆盖此前 ERR-64-023 STOP。
重新读取 Microsoft 官方 Fabric IQ MCP 文档：仍为 delegated、read-only、caller permissions/RLS/OLS，
固定 Fabric.Routing.FabricIQ.V1；本 patch 不改变 endpoint、auth、query 或 numeric/completeness 合同。
服务端在创建 ReportDataSnapshot 前，仅以实际 FabricIQPowerBIAdapter 类型及其当前 principal-bound
模型绑定证明 FABRIC_IQ；不根据 real flag、provider 字符串、前端字段或模型名字猜测。
只扩充 source-kind enum、来源选择与展示映射，ReadingContext 继续来自同一 immutable snapshot。
CloudChatRequest 保持 extra=forbid，客户端 source_kind 拒绝；旧 Local/Remote/Fixture 映射不变。
先行 failure-first 7 FAIL/6 PASS；禁止修改 QueryPlan、Builder、Inspection、Facts、八 Shape 或业务值。
完成后先 Real 专业报表来源验证，再按原授权继续剩余验收；未全部通过前版本仍 M6.3。

用户明确授权继续同 Round 2，只在 Fabric IQ provider boundary 使用当前已验证 schema 做唯一、
逐字精确列名归一化：canonical 名或 exact `TableName ColumnName`；冲突/未知/大小写或空格
不符一律 CONTRACT_DRIFT。Measure 仅接受 exact schema 名，不新增通用 alias。
ResultInspection、VerifiedFactSet、M5 Builder/QueryPlan 未修改；内部固定 probe/member alias
只用于服务端拥有的固定投影，不对公开 execute_dax 开放。
Failure-first 5 个正向用例先失败；修复后 IQ 邻近 304 PASS。ENTITY_LIST Real 已证明
`FactSales Region` → 唯一 `FactSales.Region` → `Region` → ResultInspection/VerifiedFactSet PASS，
原始失败回执保留。完整八 Shape Real 8/8 PASS，IQ_ACCEPTED 已授予。
Settings.version=M6.3；三个 capability 仅在仓库外批准测试 Workspace 配置开启。此前来源/字段身份 STOP 均为历史，本次明确批准的 provenance fix 已实测通过。

## Cloud metadata rate forward-fix：授权与 P0（2026-10-15）

普通 uvicorn + Vite 的 Admin Real 验收已证明：批准 Workspace 三模型目录、Rich 已知销售额问答、侧栏重命名、新聊天后 Restore、两个已有模板生成和查看均通过。专业报表来源 Fabric IQ、模型名和数值一致。第二个报表提交后的双资源列表读取仍发生 503 RATE_LIMITED；原报表 completed/committed 且只生成一次，Auth session 仍 200。通过原生重新加载、显式重选 Rich 和 Restore 已恢复三个历史 turn，无重新登录或写操作重放。失败、恢复截图及 artifact hashes 均留在仓库外 ordinary-native-admin-receipt.json；不声称消除 Microsoft 上游配额。Test A 隔离未完成，仍 FINAL NOT READY。

用户已明确批准同 Round 2 的最小 Cloud 请求放大/限流修复（具体提案在仓库外 cloud-operation-rate-proposal.md）。
Fresh fetch 后 main/HEAD/origin/main 仍 d943d02d32140a605a33dd0aca928dbd420e344a，staging 空，只有本轮白名单。
重新读取 Microsoft IQ 官方 limitations：metadata 与 DAX 均可能限流，rate-limit 可退避重试；
Fabric REST 的数值 quota 不移植为 IQ 保证，仅采用 HTTP Retry-After 的有界处理原则。

P0：不复用跨 HTTP 请求/用户/session/epoch 的授权。列表仅在当前请求内按 exact workspace/model/
schema fingerprint/source mode 复用本次新鲜 Microsoft access proof；每条 owner binding、目标 grant、
当前 principal 与原 selection/policy/late-response guards 均保留。资源写入前后仍有独立的真实授权验证。
Resolve+Schema 同次响应已证明的 typed schema 只经 Adapter 返回，去掉紧接着的重复 GetSchema；
未知/错误 binding、schema 身份或 epoch 必须拒绝，普通 query/schema path 不变。

退避仅在固定 IQ endpoint/Variant/原 MCP SDK 内对 ResolveFabricItem/GetSemanticModelSchema 的
HTTP 429 做最多一次只读重试；必须有有效 Retry-After 且可在现有 connection deadline 内等待。
重试前重新验证 Auth、current-principal/token、exact resource 与 policy。无有效 header/预算不足则
保留 RATE_LIMITED；不重试 ExecuteQuery，不重放产品 rename/archive/delete，不扩大 timeout。
Cloud rename 已有服务端 ack 和标题更新，不额外触发无关 transcript+History/Reports 全量同步；
其它 lifecycle 与 Local Desktop 行为保持。先失败用例证明请求数量与拒绝边界，再写 production。
QueryPlan/DAX/Inspection/Facts、IQ numeric/completeness、八 Shape 与来源合同不改变。

## Fresh runtime classification

[Microsoft Fabric IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)
描述 maxRows、embedded CSV 及 caller RLS/OLS。默认 250 不视为 inline 阈值。
固定 Fabric.Routing.FabricIQ.V1；runtime ExecuteQuery tools/list 无 outputSchema。
1001×8 脱敏 envelope 的 structuredContent 只有 artifact_citation，没有 columns/types 或 execution metadata。
executionResult 是五行 human-readable CSV preview；embedded CSV 有 1001 行。
该 CSV 不具备 machine-readable type authority，不能用于完整产品事实；不从 CSV 或 DAX 猜类型。

## Conservative Cloud inline envelope

实测 8 String 列、每格 64 ASCII 字符：18 行 typed inline，19 行开始无类型 CSV。
采用更小的 Cloud business_limit=min(DAXRequest.max_rows,12)，wire maxRows=business_limit+1。
最大 profile：8 列、最多 104 wire cells、JSON ASCII 编码后每格/列名最多 66 bytes（含引号），
typed executionResult compact JSON 最多 8192 bytes。13 行最宽列名/内容的实测 execution JSON 为 7765 bytes。
wire=13 的 0/1/12 行精确完整；13 行重复三次精确；已知 14/1001 行返回 13 行 sentinel。
返回 sentinel 时只保留最多 business_limit 行并 truncated=true；product 在 Facts 前拒绝。
返回低于 sentinel、profile 内且无 error/incomplete/矛盾 metadata 才可 truncated=false。
任何 CSV、未知类型或 profile 超限 fail closed。普通 normalize 调用没有 wire proof，仍 incomplete。
公开 Settings.max_query_rows=1000 与 Local Desktop 行为保持；不删除 QueryShape。

## Strict Int64

provider 声明 Int64/long/integer 时，canonical ASCII decimal string 经共享 integer parser 与 signed range 验证转 Python int。
null 保持 null；bool/float、指数、小数、加号、前导零、负零、空白、非 ASCII、越界继续 CONTRACT_DRIFT。
未验证的 Int32 inline string 保持拒绝；CSV integer utility 与 inline 共用 parser，不授予 CSV product authority。
Real CONVERT(...,INTEGER) 精确证明 signed Int64 min/max、0/1/-1、2^53-1/2^53/2^53+1/null，provider Int64。
原直接边界字面量引擎溢出回执保留。Python 回执拥有整数证据；浏览器 Number 展示不参与判定。

## Current acceptance

IQ_ACCEPTED：2026-10-15 原生 Auth/Fabric IQ 完整八 Shape Real 8/8 PASS。每项已知值、行数、
无截断、Layer3、原 ResultInspection/VerifiedFactSet 均通过。ENTITY_LIST 单独证明
raw `FactSales Region` → 唯一 schema `FactSales.Region` → canonical `Region` → Inspection/Facts PASS。
`iq-accepted-lineage-receipt.json` 索引 Entity/8 Shape/inline envelope/Int64 四份脱敏 evidence hash。
原始 CSV/lineage 失败证据保留，已由本次批准的 schema-bound 唯一 exact 映射收口。
Measure 只匹配 exact schema 名；不做 alias/suffix/case-fold 猜测，歧义或输出名冲突拒绝。
批准日期补充与刷新已完成，原两行 100/200、RLS/OLS/权限保留；fresh schema 与月初日期值已验证。
证据在仓库外 PBIAgentTest/M6.4/Acceptance/20261014-round2，无 token/raw 业务 dump 入库。

同 Round 2 Native Product E2E 已证明 Admin 原生 Fabric IQ/DeepSeek Answer=300、历史重命名及简单报表 view/download。
此前专业报表被错误标记 Local Desktop 的 evidence 保留为历史，用户已批准极窄 provenance compatibility fix。
ReportDataSourceKind 新增 FABRIC_IQ；服务端实际 FabricIQPowerBIAdapter 类型及当前已绑定模型决定来源。
ReadingContext 与页面继续使用同一 snapshot，旧 Local/Remote/Fixture 行为不变；不接受客户端 source_kind。
原生专业报表已显示 Fabric IQ · 实时查询、source_kind=fabric_iq，真实模型名及合成 KPI 不变；
real-product-provenance-fixed-receipt.json 保存 HTML 与页面截图 hashes，旧错误回执不覆盖。
Failure-first 7 FAIL/6 PASS，修复及邻近 103 PASS；后端全量 3493 PASS/1 SKIP/15 warnings，
Semantic 819 PASS、前端 159 PASS、Golden 11 PASS/1 manual SKIP、Typecheck/Lint/Build/Architecture PASS。
首次完整后端运行仅受 Windows GBK/UTF-8 子进程输出解码影响；按 CI 的 PYTHONUTF8=1 重跑后通过，未改 validator 或断言。
Local Desktop 实测 Answer 与完整专业报表通过，九个原有查询/章节全部保留，Desktop 来源正确，关闭后会话/worker 残留为零。
旧 Answer smoke 使用已移除的 mutable llm_provider 属性，仓库外验收器改用当前正式 registry/service 接口后通过；未改产品事实链。
Admin/Test A 其余资源生命周期及发布验收进行中；Settings.version=M6.3；未 commit/push，无本轮 exact-SHA CI/Audit。
IQ_ACCEPTED 不代表 M6.4 FINAL；baseline d943d02d32140a605a33dd0aca928dbd420e344a 的 CI38521027447 仅证明 Round 1。

## Native product capability P0 boundary（2026-10-15）

IQ_ACCEPTED：lineage Real 和完整八 Shape 8/8 PASS，Int64/inline profile 回执有独立 hash 索引。
不作为产品 E2E、外部 LLM 或发布通过。以下为原 Round 2 授权内最小服务端策略设计。

- operator allowlist 每 Workspace 三个 StrictBool：query_execution、external_llm_disclosure、business_persistence，默认 false；native 仅明确批准测试 Workspace 可用。owner-approved 不授予 capability。
- Query/LLM 使用当前 principal、session、selection 的 exact workspace/model。客户端参数不读取这些开关。Mock 标记只决定来源，不能授予权限；离线宿主显式注入 synthetic_product 才能运行合成验收。
- 进入 owner storage 前必须有明确 persistence grant；内部读取 owner binding 后仍逐资源检查目标 Workspace grant、Resolve/Schema fingerprint/RLS/OLS。不能由当前另一个模型的 grant 授权返回旧资源。
- 既有 selection/resource lease 在 await/commit/return 前重验；operator policy snapshot 改变使在途 lease 失效。资源 lease 每次验证 exact binding persistence grant。无绑定的历史保持拒绝。
- 复用 PrincipalScopedRepositoryFactory，不迁移或读取既有业务 DB。产品不创建表；验收仅 operator 预置新的 synthetic SQLite。
- 外部 LLM 继续现有 bounded semantic/fact context，只用批准合成数据；不发 raw schema dump、GUID、token 或其它 Workspace 内容。依旧 no LLM DAX。

先验证默认拒绝、三个 grant 独立、严格 bool、跨 Workspace/Model、owner-approved 非总开关、Mock 非授权、迟到撤销拒绝等负例，再最小实现。Frozen Core 仍不修改。

## Workspace test scope P0 correction（2026-10-15）

用户明确批准整个 PowerBIAgent-M6-Dev 的现有及后续测试资源只读访问；此授权取代逐 Model/Report 人工名单。
官方 Fabric List Semantic Models / List Reports 均提供指定 Workspace 的分页 GET；默认 recursive=true。
只定向 GET 配置的 Workspace 和它的两个 collection，不调用全局 /workspaces，不访问其它 Workspace。
collection 每项必须 exact workspaceId/type；continuation 必须保持同 host/path，不接受跨 Workspace URI。
旧 operator models/reports 可读以兼容配置，但不再决定资源访问或三个 capability。三个开关仍由 operator 按 Workspace 独立配置且默认 false。
IQ 每个连接携带服务端的 exact workspace/model 上下文；Resolve URL 必须一致，artifact-only 工具必须匹配该上下文。
无上下文的 artifact-only 调用拒绝；Resolve 返回的 Workspace/model 仍由 Adapter 严格核对，GetSchema 仍证明当前 principal 可访问。
每次 wire call 与 await 返回均重验策略；模型 key、客户端参数、owner-approved、Mock 标记不授予权限。
Report 仅作同 Workspace 控制面 metadata，不能借 report 访问其它 Workspace 的 model。
先验证新资源可枚举、跨 Workspace ZERO request、缺失/错误上下文拒绝、跨 Workspace 分页拒绝和 capability 默认关闭，再最小实现。
不执行尚未明确批准的 measure home-table 模型写入；优先只读核对已有测试模型。

官方依据：
[List Semantic Models](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/list-semantic-models)、
[List Reports](https://learn.microsoft.com/en-us/rest/api/fabric/report/items/list-reports)。
