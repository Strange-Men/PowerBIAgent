# M6.4 单人收口：Fabric IQ 技术决策与最终差异核验

日期：2026-10-14。状态：PARTIAL/BLOCKED，非 Final Seal。用户授权只覆盖原M6.4；
不修改验收定义、ADR-020、Git流程、Frozen Core、Provider、八类QueryShape或两种模板。

## 一次有界合同判断

本轮成功读取[精确Fabric IQ官方合同](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)，
HTTP200；页面SHA256及脱敏摘录在PBIAgentTest/M6.4/Acceptance/20261014-solo/official-contract.json。
公开endpoint为`https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq`；私链地址只允许显式配置，
不因失败切换。delegated OAuth、tools/list authority、RLS/OLS、默认maxRows=250仍适用。
官方明确CSV仍受查询限制且可能截断；页面没有Int64编码或可用于本项目事实验收的完整性标志合同。

复用既有脱敏结论：COUNTROWS曾返回Int64/int且值通过，但truncated=true；销售额scalar/grouped
返回Int64/str并被CONTRACT_DRIFT拒绝；执行/表层无可信complete/hasMore/totalRows证明。
本轮没有重复企业查询、读取原始业务证据、转换数字字符串或修改Expected。

| 能力 | 当前可证明范围 | 当前不能证明 |
|---|---|---|
| Auth/Catalog/Resolve/Schema | 官方delegated合同、服务端资源绑定及合成权限负例 | 当前获批逐资源Real及企业元数据披露授权 |
| Int64 | 人工响应严格int边界；bool/float/str拒绝 | IQ标为Int64的字符串语义、精度、null及encoding合同 |
| SCALAR | 有限合成表的行数与值；固定ROW构造的语法约束 | ROW基数不能证明IQ返回内容完整、未受上游截断/错误影响 |
| 其余七类Shape | 既有deterministic DAX与合成事实检查 | IQ分页/CSV/截断与每类实际覆盖的可验证证明 |
| Answer/Report | MOCK命名空间内正式事实回调、固定Renderer、API/React合成链 | 原IQ完整Real业务链及当前A/B RLS/OLS |

结论：现有IQ合同足以继续目录/身份与离线服务开发，当前不能支持原定完整Real事实验收。
未知完整性仍truncated=true，native product在facts/LLM/持久化前拒绝；严格类型检查不变。
没有新官方或批准wire证据时停止同一调查。

可选技术决策（本轮不实施）：

1. 保持IQ，等待精确endpoint可验证Int64与完整性证据，再最小修复并执行获批Real。
2. 用户另行批准仅调查[Power BI Execute Queries REST](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries)
   作为执行接口的可行性。现有REST限额/错误合同不自动成为IQ证据，也不自动保证八Shape完整；
   仍需身份、RLS/OLS、精度、截断、错误、限额及事实验证。不得自动换Provider或fallback。

## 三层验收与隐私

Synthetic：离线Mock LLM + 有限人工模型 + 模拟Entra身份，实际经过TurnPipeline、Grounding、
CanonicalQueryPlan、Deterministic DAX、Layer3、VerifiedFactSet、FactOutputValidator、固定Renderer、
owner SQLite与API。React测试使用真实API client，以stdio连接同一离线FastAPI host；无监听端口。
旧Core以is_mock选择旧fixture分支，测试专属branch view显式选择正式回调，不能作为Provider或授权。
请求模式、LLM profile/protocol、QueryResult/facts、Memory/Snapshot/Artifact及public API均为MOCK；
内部canonical draft的旧is_mock字段不作为Real验收证据。本轮不改Frozen Core。

Contract：人工IQ响应、既有脱敏证据、八Shape未知标志与严格Int64/错误/超时/权限负例。
Authorized Real：本轮BI请求0、外部LLM请求0，全部NOT_TESTED/BLOCKED。

新增P0拒绝边界：native ENTRA_BFF装配CloudProductServiceFactory，storage factory延迟且先校验
业务gate；启动/阻塞请求不创建engine、不迁移或读取真实DB。native TurnService直接调用也先验证
principal、selection lease和关闭的执行gate，不能绕过HTTP/PreparedCloudProduct让Core接收业务数据。

Auth/Transport凭据仅在本机内存与Microsoft传输；Catalog/Schema缓存按principal/session/epoch。
通用Provider若被开放可发送问题/schema/成员/事实，Trace通用secret scrubber不等于业务DLP。
Memory/History/Snapshot及Report HTML包含业务内容，本机owner隔离不等于公司留存批准。
当前native在这些链路前拒绝，不宣称企业隐私全部闭环；历史风险资料仅保留脱敏结论，不读取、
移动或删除原始证据。未来Real需原M6 Workspace逐资源许可及独立披露/留存策略。

## 最终对照PRD与Roadmap

依据正式[PRD](../../00_product_requirements_document.md)、[Roadmap](../../08_development_roadmap.md)、
[ADR-020](../../adr/ADR-020_fabric_iq_cloud_consumption_and_catalog_authority.md)及M6.0 Product UX。

| 审计发现 | 本轮处理 | 未决验收 |
|---|---|---|
| 原生ENTRA_BFF未装配Product Service | 已安全装配；延迟storage并在开库前拒绝 | 开放native需合同/隐私/Real门槛 |
| 业务只支持受控Mock | 新增正式事实回调与固定Renderer的完整Synthetic API/React E2E | Synthetic不代表Real，native不自动启用 |
| Int64/Completeness未解决 | 上述一次合同判断；严格拒绝保持 | 外部精确合同或另行批准接口调查 |
| 企业传输隐私P0未闭环 | 补直接服务调用拒绝、native无storage活动负例 | 披露/留存策略、历史本地复核与Real证明 |
| 当前/历史状态混杂 | 07/09最前当前摘要明确本轮；旧记录标为历史保留 | 最新SHA/CI以本轮发布回执解析 |
| Cloud Sidebar有未实现操作 | 复核搜索/rename/archive/delete未展示；new/restore/reports已有合成接线 | Cloud完整资源管理/Settings全量管理仍内部PARTIAL |

未展示的Sidebar操作不会被当作已实现；PRD完整资源管理与Cloud当前精简Settings存在差异。
本轮范围是既定安全组合、Chat/History/Report与错误恢复，未新实现资源写/删生命周期。
该内部差异不由微软合同造成，不能报告“只剩外部阻塞”或“单人再无可开发事项”。
正式Cloud报表模板仍按已有注册合同与LOCAL_DEV binding scope验证，不将opaque Cloud key
强行替换模板合同、不更改模板定义；其跨模型Real适配仍需明确资源/合同验收。

| 版本 | 真实状态 |
|---|---|
| M6.0 | COMPLETE：合同/设计阶段已封板；不代表后续业务事实合同解决 |
| M6.1 | COMPLETE：Entra BFF阶段，按自身CI/remote audit生效 |
| M6.2 | COMPLETE：Adapter阶段，历史小型Real范围；数值/完整性限制保留 |
| M6.3 | Security COMPLETE：自身封板安全范围；Int64 P1仍BLOCKED |
| M6.4 | PARTIAL/BLOCKED：Synthetic事实链及P0补丁可提交，Real/隐私/合同未满足，不能封板 |

Settings.version保持M6.3。本轮收口后停止，不自动启动下一阶段。

本地验证：backend3335 PASS/1 manual Real SKIP，13既有warnings；frontend142 PASS与
Typecheck/Lint/Build PASS；Semantic819 PASS；Golden11 PASS/1 manual Real SKIP；治理检查PASS。
CI/Remote Audit以本轮actual main SHA及PBIAgentTest/20261014-solo回执解析；不继承历史CI。
