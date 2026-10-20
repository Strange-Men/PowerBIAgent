# M6.5 — Cloud Real Business Data Validation

## M6.5 收口候选（2026-10-20）

Settings.version=M6.5；公开真实业务数据 Cloud mandatory 已完成。发布仅在本提交自身
Full Validation、Remote Audit、HEAD=origin/main、clean 和 owned service shutdown 全部成立后生效。
本提交不保存自身 SHA；最终 SHA/CI/Audit 以 main 与外部回执解析，不能继承历史 CI。

完整 Online Retail II flat Sales：1,067,371行，canonical Product=5,131；Raw Source Oracle
5,305 literals与独立 Canonical Product Oracle并存，174碰撞组审计保留，不修改源数据或旧Oracle。
八QueryShape逐case Fabric IQ真实执行、确定性DAX、Facts/Answer/Memory和Oracle PASS；
TREND三proven YEAR、BOUNDED_TREND六ordered月；完整25月/43country超过12拒绝，ZERO事实提交。
wire纯numeric string仅fresh numeric schema+exact lineage+ASCII lexical后直接Decimal；金额scale4
exact，AOV<=0.0001 GBP，wire精度原样保留。无currency/locale/fuzzy或通用string coercion。

两现有模板显式Total Sales KPI原生生成/view/download/hash/Facts PASS；runtime四KPI eligibility
只为能力证明，不冒充查询了四KPI。只看月份趋势的请求因现有模板无eligible趋势section而拒绝，
ZERO DAX/artifact/Facts/Memory；不假称执行了高基数report查询。含“全部”的原negative走既有
FULL_AVAILABLE并生成四KPI，不满足原negative断言，原件与合同分类审计保留，未改Planner或expected。
五轮exact measure/filter/time/Oracle PASS；旧固定SCALAR harness失败保留，按既有interpreted-or-
inherited contract独立审核，未改expected或生产shape semantics。

history/rename/restore/archive/unarchive/browser reload、report delete/tombstone/history delete、
general ZERO business mutation和stale generation已native验证（lifecycle-8acc52d8.json）。
真实迟到响应在generation/policy变化后拒绝且ZERO Memory/snapshot（race-c5de68cf.json）。
Admin/Test A原生Fabric IQ安全fixture分别300/100与Region范围、owner/IDOR/unknown-id等价拒绝
PASS（security-admin-fd3b0f9b.json / security-test-a-d6b4d3a2.json）；无新权限，Test B DEFERRED_BY_TEST_PRINCIPAL留M6.6。
RATE_LIMITED原件与现有fresh restore恢复PASS保留；未新增Provider/retry/reuse/cache架构。

前序production快照本地Backend3815PASS/1SKIP/15既有warnings，Semantic819PASS，Golden11PASS/
1manualSKIP，Frontend160PASS，Typecheck/Lint/Build及Security/Ledger/Architecture/Documentation/
Artifact/diff PASS。seal后仍fresh验证最终candidate并运行自身exact-SHA CI；此前PASS不能冒充Final。
所有assets仅PBIAgentTest/M6.5，正式tests/fixture定义/doc在Git，无PBIX/DB/token/data dump提交。
Frozen存在明确批准的窄correctness forward-fix，authority/QueryShape/Plan/DAX/12-row保持；
ERR-65-012仅保留用户当前完整table[column]语言限定，leaf-only触发现有bounded repair，
runtime仍证明对象；failure-first e0f5b9f7四RED、最小修复9cf029ba专项邻近124PASS。
relationship cardinality CONTRACT_GAP已知限制、available horizon超限UNKNOWN、refresh UNKNOWN。

后续只预留M6.5.1 Chinese / English Localization Platform、M6.5.2 Web / SSO Productization、
M6.6 Enterprise Production Readiness Seal。本轮零实施；Final全部成立后STOP。

日期：2026-10-15。本文拥有本轮专项设计与验收合同；状态/路线/唯一交接分别见07/08/09。
用户正式授权 M6.5；先设计与 failure-first baseline，Cloud MCP First，无新增产品能力。

## Historical — 前序验收 checkpoint（2026-10-20）

完整 flat Sales 模型由用户重新发布：1,067,371 rows、canonical Product=5,131；无再次 Desktop 操作。
Raw/Canonical Oracle 不变。用户批准的窄 numeric/Decimal、YEAR inspection 和语言证据修复均
failure-first 后经实际 Cloud 复验；8/8 QueryShape 与两个现有 KPI 报告正例已 PASS。
五轮 exact measure/filter/time/Oracle 对账 PASS，原 harness 固定 shape 失败与独立合同审计分开保留。
当前正在生命周期、安全邻接及 Final Gates 收尾。Settings.version=M6.4.1，未 stage/commit/push。

见[当前 Matrix](m6_5_cloud_acceptance_matrix.md)与[合同历史及现有限制](m6_5_cloud_runtime_contract_stop.md)。
12 business rows / N+1 wire / 8 columns 不变；关系缺 cardinality 保持已知 gap，单表不依赖关系。
Test B 无批准 principal，DEFERRED_BY_TEST_PRINCIPAL 留 M6.6；不得冒充安全 PASS。
下文为前序设计与停点历史，不能替代顶部当前进度。

## Fresh Cold Start

已先 fetch origin；main，HEAD=origin/main=`63287db28b519d7043bd762622e7eef586351201`；
单一 worktree、初始 worktree/staging/diff 均为空。前六提交及 AGENTS → Charter → CLAUDE →
07/08/09 → README/CHANGELOG → Error Ledger → accepted ADR 已重新读取。
用户确认批准 Workspace 中尚无 Online Retail II 模型。没有创建/发布 Cloud 模型、改变角色或由Agent读取凭据。
版本保持 M6.4.1；本次设计不宣称 M6.5 COMPLETE，不提交提前发布 marker。

## Historical — Flat Model Cloud Real Path

2026-10-16最新用户已授权继续，仅Canonical Product Identity+Numeric Measure Format，取代上次STOP。
旧profile/Raw Oracle/ValueSearch证据保留。新增独立canonical Oracle5,131 members/174碰撞组，
完整1,067,371行、metric totals与原Oracle一致；Raw Oracle SHA不变。Adapter按runtime列声明执行
尾随U+0020→invariant ASCII uppercase→bounded ValueSearch→exact verification，raw provenance列
不进入产品Grounding。Frozen Core/numeric validator/12-row envelope保持。failure-first10RED已保留，
专项/集成156PASS，完整后端3602PASS/1SKIP/15既有warnings，Semantic819PASS、Golden11PASS/1manualSKIP及架构/治理门PASS；新operator资产仅外部Model/operator-canonical-v2。
下一步回归通过后由用户替换同一自建Online Retail II M6.5，回复“已重新发布”后继续Cloud Real。
旧P0停点保留为历史；按最新STOP条件执行。后续M6.5.1尚无实施授权，版本保持M6.4.1。


2026-10-16 actual Cloud runtime：已证明新StockCode identity/Oracle P0，按用户单表新P0条件STOP。
结论与全部脱敏回执见[Cloud Runtime STOP](m6_5_cloud_runtime_contract_stop.md)。此前等待登录/发布记录为历史。

2026-10-16：用户确认已发布。fresh fetch仍既定main基线，staging空、只有授权diff；官方GA/
delegated/scopes/selector/只读消费合同已重读并保存外部Diagnostics/20261016-cloud-real/
official-contract-fresh.json。当前启动新的隔离原生宿主与空的owned测试存储，旧Auth会话已失效，
等待Admin恢复登录后运行新模型runtime及native HTTP product矩阵。发布前checkpoint在下方保留；
用户发布确认不代表模型结构、数据控制总数、Oracle或产品链已PASS。

用户最新批准完整单表Sales路径：保留1,067,371行、真实原始字段及Date/Year/YearMonth/
IsCancelled/IsSaleEligible/LineAmount，7 measures均在Sales。不建立维表或关系，不造Category/Region。
当前profile、BUSINESS_METRIC_CONTRACT、独立Oracle与acceptance matrix保留，不重做。
此前runtime关系缺cardinality的CONTRACT_GAP作为已知Cloud capability gap保留；本轮不改
relationship normalization/Grounding/Frozen Core，不再因该已知gap停止同表实施。

唯一correctness实现为explicit literal bounded scoped ValueSearch→exact runtime member proof→
现有Grounding→现有CanonicalQueryPlan。Cloud service的task-local ContextVar只传现有SemanticFrame
及当前问题支持的verbatim literal，finally reset；没有第二语言parser/Planner/Grounding/Memory。
Adapter对categorical text/string explicit literal使用artifactId/searchTerms/scope精确表列调用，
每次最多12候选，max12 hints；citation模型identity、schema/table/column/value exact匹配才证明存在。
Score仅校验数值，不选值；fuzzy/casing mismatch/wrong column/unknown不绑定；重复exact保留供既有
Grounding判歧义。返回truncated=True说明定向存在proof不是完整vocabulary，日期grain/full
enumeration仍遵守完整快照规则。无explicit literal的国家/商品全量枚举>12继续fail closed。

actual用户Admin native Auth probe的ValueSearch inputSchema及非空输出已证明，无新增权限：

```json
{"artifactId":"<current bound model>","searchTerms":["<explicit literal>"],
 "scope":[{"tableName":"<exact table>","columnNames":["<exact column>"]}]}
```

输出为单一JSON text的Results term bucket，候选Table/Column/Value/Score；structuredContent
artifact_citation.ArtifactId绑定模型，resultType=complete。bucket首字母大小写在runtime变化，
bucket casefold只验证搜索请求；Value exact equality独立验证canonical member。MWCRaid只作诊断，
不作为model authority。先前短值/未知空候选及四个已有测试模型非空候选证据分开保存，不能将其
称为Online Retail II Real；otherWorkspace ZERO request、无LLM或business storage。

证据仅外部M6.5/Diagnostics/20261015-value-search：runtime-probe-receipt.json、
value-search-wire.redacted.json、value-search-positive-runtime.json。正式tests使用synthetic身份和
actual wire字段结构；不提交真实model ID/payload。原关系probe hash及9RED/18PASS failure-first
在下方历史段保留。最新版implementation不改business12/wireN+1/columns8、Core、DAX/Facts或八Shape。

fresh regression：focused26PASS（b901acdf）、Cloud/safety174PASS（c359ed08）、现有Grounding
集成17PASS（c1e0df97），Semantic819PASS（fddc13f7），Golden11PASS/1manualSKIP（38164e22），
Architecture（8a10c727）/Repository Safety（696d788f）PASS。首次全后端06dc1681为
3570PASS/2FAIL/1SKIP/15既有warnings；新增callback测试错误以SimpleNamespace调用super及09当前
标题缺version两处已修正，原件保留。补充923cbaf7发现08单行含稳定版本和进行中使既有版本一致性
校验误读，改正文为正在验证而不弱化test。前端首轮d636839d worker启动timeout保留；原命令重跑
f006b867为160PASS；typecheck369efd93/lint143900cc PASS。完整后端与最终治理门已PASS，实际回执见下文。

补充多literal failure-first：6a6d0869证明France精确候选可能被既有Grounding normalized路径
用于france非精确literal。Adapter最小forward-fix要求同列每个当前literal各自拥有exact proof后
才暴露共享集合；缺任何一个proof则返回空的incomplete集合，不改Grounding。b6099bba为初始
测试fixture类型失败，亦保留。修复后658cad42为126PASS，再加exact/unknown/nonexact多literal
覆盖后f9cc74e4为128PASS。08bd987a完整后端3572PASS/1SKIP/15既有warnings对应修复前采集；
最终当前代码ad98eea6完整后端3575PASS/1SKIP/15既有warnings，不能用旧运行替代当前证据。e00b4fb5相关callback/settings53PASS，
frontend build1c04374f PASS；Documentation218444c4/Ledgerf1b9efe9/Artifact5fe72e1a/
Architecture815f933c PASS；最终Safetyf20bb551/Ledgerd0fa6240/Documentation089432f8/Artifactf8b706b6 PASS。只读probe宿主已停止，5173无监听，Auth/Transport生命周期结束。

Cloud模型尚未建立；本页[operator单表步骤](m6_5_operator_test_model_setup.md)已对齐全量合同。
ValueSearch实现与完整回归已PASS，下一步用户一次性创建并发布Online Retail II M6.5到PowerBIAgent-M6-Dev；
随后Resolve→Schema→known-value scalar→八Shape→multi-turn→reports eligibility→history/resources→
security→recovery→Oracle→Full Gates。日期grain、time authority及report section必须实际证明，
不能从offline模型定义推断或改变template。单表若暴露新P0 architecture blocker再STOP；同根因
继续failure-first/minimal fix/regression/Cloud Real。没有新增Cloud authoring Provider或Local完整重复。
M6.5尚未完成，Settings=M6.4.1，未stage/commit/push，无自身CI/Remote Audit，M6.5.1零实施。

## 历史 — Cloud Semantic Proof Minimal Scope / relationship CONTRACT_GAP

以下为被用户最新单表授权取代的旧停点记录；关系gap及失败证据仍有效，旧“targeted未实现”不代表当前。


用户2026-10-15新增明确授权仅两个blocker：explicit literal bounded ValueSearch proof和IQ明确
relationship authority的最小normalize。原profile/Oracle/matrix保持不重做；12-row、Frozen事实
authority、QueryShape/Provider/模板保持不变。先fresh fetch，同基线main=origin/main，staging空，
只有上一轮已授权diff；无unknown用户变更。旧停点仅由本scope取代，新的停止条件按本节。

仓库外M6.5/Diagnostics/20261015-semantic-proof原生Auth只读host，用户实际Admin登录并点击
probe，fresh2026-10-15已批准测试模型Resolve+完整Schema成功。没有UCI模型，没有新增grant，
otherWorkspace请求0、externalLLM0、business storage未打开。
runtime pin=Fabric.Routing.FabricIQ.V1，SDK2.0.0；initialize1/tools-list1/tools-call2；model身份精确。
指纹`3db4195269815aa856b0cfa934c288cc7af6064a706f8110da98e446ed217d18`。

ValueSearch实际inputSchema：required artifactId:string、searchTerms:string[]；optional scope数组，
entry为tableName:string/null、columnNames:string[]/null。可精确限定table/column，但没有outputSchema，
返回值shape/identity/completeness尚未probe。工具description的Score=1.0或下一步GenerateQuery只是
untrusted metadata，不授予member/DAX authority；本产品不引入GenerateQuery或按score/fuzzy选值。
本次只证实工具schema可用，没有ValueSearch运行/显式member Real PASS。

**关系实际payload仅PK、FK、UnidirectionalFilter三键，schema只有Tables/ActiveRelationships。**
单关系方向文本明确`'DimRegion' filters 'FactSales'`，PK/FK分别是精确表列引用；没有
from/to cardinality或显式isActive字段。ActiveRelationships集合可表达active来源，但不能由PK/FK
标签自动补出one/many，也不能把方向文本转成未经证明的完整canonical关系。
ModelSemanticContextBuilder的关系日期key与Grounding的同名维度归属/one-side member-field选择
实际读取cardinality。现有normalize保持relationships=[]、NOT_VERIFIED；跨表选择由既有validator
拒绝。用户要求“Fabric IQ runtime无足够relationship authority：STOP”，故本次结论为
**CONTRACT_GAP / STOP**，生产normalize及targeted member实现均未开始。没有自行设计第二套关系推理。

原始脱敏结构/runtime工具schema/receipt只在外部Diagnostics，hash：

| artifact | SHA-256 |
|---|---|
| runtime-tool-schemas.json | 337207e9e0cfd83f3956d2ab036560c329994a6ad4fc61991680c173ac191bf9 |
| relationship-structure.json | 6149392b93516108c0deb4a57d86db7f5f21be243f647ec2bd97d0dc593fb953 |
| runtime-probe-receipt.json | d2a3ac1cdd5d13d3b52671cc8d79428b71e74c34cbf12f20818e3a5d74d78514 |

failure-first正式测试新增explicitFrance/Germany/UK、StockCode、unknown/fuzzy/nonexact/ambiguous/
wrong-column requirements；缺少实现函数时保持RED，不伪造输出schema或将失败改SKIP/PASS。
已有full enumeration>12负例保留。missing/observed insufficient relationship canonical edge及
cross-table拒绝/无one-side temporal authority测试使用fresh wire字段结构，结构对象名为synthetic。
首轮测试构造缺normalized_question、第二轮错误用legacy QueryPlan table hint及temporal属性名已修正
到真实contracts；前两失败回执保留，不能把fixture错误当production根因。合法explicit
relationship positive G未获runtime充分proof，未造authority fixture宣称Cloud准入PASS。
最终fresh6735ac8c为9RED/18PASS：9个缺targeted proof实现的要求保持RED；existing full enumeration
和关系缺失/不足/无one-side日期authority负例PASS。不是已解决blocker，也不是业务Real PASS。

Cloud authoring工具不存在，未引入Provider/REST/XMLA/Arrow executor。已完成一次性
[operator建模步骤](m6_5_operator_test_model_setup.md)，完整dataset/measure/control totals对齐既有
Metric Contract；因本次CONTRACT_GAP停止，没有请求用户立即发布无可验收的模型。
版本M6.4.1，无production/Core改动、未commit/push，八Shape/多轮/report/security/Oracle Cloud Real
尚未运行。Runtime metadata Real probe不能当UCI business Real验收。Local MCP Real无重复。
本次收口：Repository Safety/AI Error Ledger/Architecture/Documentation/Artifact Governance五门
fresh PASS，git diff check通过，再次fetch基线未前进、staging空。Owned只读probe已停止，5173无监听，
没有Local MCP worker或business DB创建。failure-first9RED仍在，完整CI/业务Cloud Real/版本发布未通过。

适用 ADR：005/008/009/014/016/018/019/020。Error Ledger 重点：ERR-641-001（资产/路径）、
ERR-64-024（请求放大/只读退避）、ERR-64-023（来源）、ERR-64-022（lineage）、
ERR-64-012/014（范围/迟到撤销）、ERR-5106-008（既有 deadline）。

## Microsoft 官方 Cloud 合同重新核验

读取 [Fabric IQ 官方文档](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)，
核验日期2026-10-15，页面更新2026-09-15。以下是文档证据，不是本轮 delegated runtime PASS。

| 项目 | Fresh 官方合同与本轮约束 |
|---|---|
| Availability | Fabric IQ MCP 为 GA；不将 authoring preview 状态套在消费端点 |
| Endpoint | `https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq`；private link 只显式配置 `https://api.fabric.microsoft.com/v1/mcp/fabriciq`，无故障切换 |
| Transport | Streamable HTTP/MCP lifecycle；不是 REST Execute Queries |
| OAuth | Entra delegated user，Power BI Service `Item.Read.All`、`Item.Execute.All`、`Dataset.Read.All`；SP/app-only 不支持 |
| Contract pin | 所有 initialize/tools-list/tools-call 使用 `X-Variants: Fabric.Routing.FabricIQ.V1` |
| Tools | DiscoverArtifacts、ResolveFabricItem、GetReportMetadata、GetSemanticModelSchema、ValueSearch、ExecuteQuery；实际 names/input schemas 必须 runtime tools/list 证明 |
| Required implementation | Resolve: fabricItemId string；Schema: artifactId string；ExecuteQuery: artifactId string + daxQueries string array，maxRows integer/null。这些是现有严格 capability validator，fresh runtime 核验仍待执行 |
| Binding | Resolve 成功不等于授权。返回 exact Workspace/model identity 与 current-principal Schema 必须一致；catalog 只批准 Workspace 定向请求，other Workspace ZERO request |
| Permissions | MCP 不增加资源权限，RLS/OLS 随当前用户；无 admin impersonation |
| Result | 默认250行，large response可 embedded CSV，仍可能截断；默认/CSV 均不能替代本产品≤12 business rows、N+1 sentinel、≤8 columns、typed lineage/completeness proof |
| Throttle | metadata/DAX均受服务端限流；官方允许退避，没有 IQ 数字 quota/最大 Retry-After/SLA 承诺。不能搬用 REST Execute Queries quota |
| Current retry | 仅 Resolve/Schema 按有效 Retry-After、原 deadline 内最多一次 wire retry；重验 principal/policy。ExecuteQuery/资源 mutation 不自动重放 |
| Limits | home region须支持全部Fabric workloads；Power BI-only/sovereign regions不支持。单次一个模型，不能跨模型join。无dashboard/RDL/app/ontology/data-agent消费，无item creation |
| Refresh | 查询reflect模型上次成功refresh；查询时间、requested end、Date最大值不证明refresh time |

另 fresh 读取 [RLS](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security)
及 [OLS](https://learn.microsoft.com/en-us/fabric/security/service-admin-object-level-security)。
Admin/Member/Contributor edit身份不受RLS；Test A必须实际Viewer受限身份。Admin正常数值不能证明RLS。
OLS受限对象/metadata应对Viewer不可见；Test B仍DEFERRED_BY_TEST_PRINCIPAL，不创建账号或扩权。

IQ 只有消费功能，不能用其创建测试模型。数据模型authoring/导入是一次性测试资产准备，不能新增产品
executor/Provider。发布使用批准Workspace现有operator流程；本轮未执行任何Cloud写入。

## 数据审计、模型与 Oracle

官方 UCI 502、CC BY 4.0、原始两张工作表、真实缺失/负数/重复数据及单位先审计。
定义见 [BUSINESS_METRIC_CONTRACT](m6_5_business_metric_contract.md)。
完整offline profile已PASS：1,067,371行、43国、25月、5,305产品；eligible销售额
20,972,594.5680 GBP经scaled integer/独立Decimal完全对账。此为DRAFT口径expected，Cloud未执行。
正式离线脚本 `scripts/profile_online_retail_ii.py` 只下载公开文件/profile/独立整数与Decimal计算，
不是产品事实来源，不导入production、不训练/查表回答、不生成LLM DAX、不发布模型。

数据及所有cache/receipt仅仓库外 `PBIAgentTest/M6.5/Dataset|Profile|Acceptance|Cache`。
启动命令必须经 `scripts/run_local_validation.py --milestone M6.5 -- <bundled Python> ...`；
源文件保持原始；下载失败/部分副本/首次profile拒绝保留并标失败，不能复写PASS。
可重复运行必须新output目录；官方ZIP CRC及复制SHA已证明，profile读immutable byte snapshot。

此前星型备选（最新单表授权已取代，不实施）：FactSales(原始行 + source sheet/row provenance + typed derivatives)、DimDate、
DimProduct(StockCode唯一)、DimCustomer(非空ID唯一 + 显式missing member)、DimCountry(原始Country)。
单向维度→Fact，day date去时间键，但保留原始InvoiceDate。不要因模板/12行限制删除数据或造类别。
UCI无真实商品Category和销售Region层级，不将Country改称Region或把任意Description当唯一Product。
Product查询以StockCode唯一键；多description不能使用first作为唯一业务事实。

现有固定模板required measure table为Sales；Date.YearMonth要求date/datetime，
Sales.Category/Region/Product/Customer各有既有固定section要求。若完整星型模型仅有FactSales/Dim*，
不能把模板目录为空/section不可用视为correctness bug，不能新增模板或重写ReportPlanner。
可以在模型design中使用Sales作为事实表的真实名称并保留source字段定义；无来源的Category/Region
继续不可用，不能伪造事实。模板应由fresh schema eligibility明确证明可选及可证明section集合。

同时 `normalize_schema` 对IQ PK/FK只保存原始evidence，relationships=[]、mapping=NOT_VERIFIED。
跨表filter/time reachability不能靠离线模型设计宣告成立。星型关系需要fresh runtime proof与现有
contract审计；不得未经授权填补未知方向/cardinality或编写第二Grounding。

## P0/P1 风险与进入条件

| 级别/风险 | 证据与入口检查 | 当前处置 |
|---|---|---|
| P0 指标口径 | gross-positive、cancelled signed、missing IDs、重复/异常价格分开统计，原始数据无删除 | 先profile及contract，Cloud comparison待验 |
| P0 超界完整性 | ≤12 business/N+1/≤8 columns，真实高基数negative | 保持CLOSED_AS_EXPLICIT_LIMIT，不扩大/分页 |
| P0 高基数member grounding | get_column_members对100请求发TOPN101，但wire13；第13行sentinel使product拒绝 | 13/25/43/5000 synthetic failure-first复现；不绕过，需scope重新评估 |
| P0 月粒度证据 | IQ expression未知；完整月份snapshot若>12也被拒绝 | 完整25个月不能用6月question暗中缩短模型；formal trend proof待验 |
| P0 关系authority | IQ normalization不证明direction/cardinality | 星型不能先声称可执行；必要扩展先STOP |
| P0 身份与范围 | approved Workspace，exact binding，三个grant独立true；Token仅Auth/Transport | automated邻近PASS，fresh login/Cloud未执行 |
| P0 owner/IDOR/revoke | owner namespace + current session/access + generation/policy epoch逐项校验 | 聚焦既有拒绝/late-stale，Real待验 |
| P0 source/report | FabricIQ实际adapter证明source；same Facts/scope，历史snapshot不可改写 | baseline邻近PASS，UCI两个模板待验 |
| P0 oracle independence | Decimal与scaled integer reconcile，不用LLM/query输出做expected | 离线source计算；fresh Principal scope另匹配 |
| P1 产品适配 | fixed template canonical names；Category不存在、Product description重复 | schema-derived corpus，不造semantic fields或新模板 |
| P1 限流/超时 | 计Resolve/Schema/Query/LLM/whole/report、429/timeout/retry/recovery | 只形成evidence/backlog；无cache/reuse优化 |
| P1 Test B | 无approved可用principal | DEFERRED_BY_TEST_PRINCIPAL，M6.6封板条件保留 |
| P1 下载/数值 | 不可变snapshot、CRC/SHA、scale4、逐行及聚合signed bounds | 原失败保留，offline脚本forward修复独立于Frozen Core |

## 历史 — 初轮 Failure-first 与 scope 停点（已由最新授权取代）

Fresh现有邻近79PASS；新增审计13PASS，其中高基数4cases是期望拒绝，不是八Shape业务成功。
离线script最终改动后13项再跑PASS；Repository Safety、Error Ledger、Architecture、Documentation、
Artifact Governance五门fresh PASS。git diff --check通过（保留既有LF/CRLF提示）；再次fetch无remote drift。
证据分别由canonical runner receipt记录；Local MCP Real=NOT RUN，无事实/Adapter/Core变更不机械重跑。
Cloud model=NOT CREATED，runtime tools/schema/principal/result=NOT RUN，Full Gates/CI/Remote Audit未成立。

已发现受限结果envelope与完整member/month证明之间的架构范围问题。现有public member request无
requested-literal参数，不能用ValueSearch或定向过滤偷偷换合同；也不能改变结果边界、分页或截断冒充
完整。用户要求出现architecture scope扩展则STOP：本次完成设计/profile/failure-first后停在该点，
不实施production修复、Cloud模型发布、提前version bump或发布提交。下一scope需明确该边界处置。

## Cloud Real 执行及封板计划

完整矩阵见 [Cloud Real acceptance](m6_5_cloud_acceptance_matrix.md)。顺序：
Data Contract → approved model Import/Resolve/Schema/known-value → product八Shape/multi-turn/report/
security adjacency/recovery → focused/Semantic/backend/frontend/Golden/governance/必要Cloud/Full Gates。
每行记录actual schema/member/source/coverage/Facts/Answer/report一致性；失败保持zero factual commit。
不计接口200或历史PASS为business correctness。

全条件成立才Settings.version=M6.5，中文commit `M6.5_公开真实业务数据云端验收`，
白名单stage、push前fresh fetch无drift、普通push main、自身exact-SHA Full Validation/Remote Audit，
HEAD=origin/main、worktree/staging clean、test-owned服务关闭，再FINAL COMPLETE并STOP。
未完成不发布，不继承63287db/旧M6.4 CI。

下一阶段已预留M6.5.1 Chinese/English Product Localization：全局switch、单次分析与Cloud query、
language-independent plan/DAX/result/Facts、UI/errors/presentation/report本地化与双语事实parity。
本轮零i18n实现；之后M6.6 Enterprise Production Readiness Seal。M6.5 Final时正式整理08/09路线。

## 当前验收进度 — 2026-10-20 temporal correctness closure

Settings.version=M6.4.1；M6.5进行中，未stage/commit/push，Final尚未成立。
最新用户明确授权ResultInspection接受exact model/schema fingerprint/table/column的proven YEAR
integer axis，以及既有Understanding的generic temporal coverage correction。先前禁止修改该边界的
STOP已被本次授权替代，历史失败原件保留。新inspection只接受proven year的exact int 1..9999，
无catalog/schema、drift、wrong identity、bool/float/Decimal/year-string均拒绝；不转换数值或合成日期。
Data/Report使用现有fresh schema/catalog；Plan/DAX/Facts authority不变。

failure-first f74664f1为24RED；fffb8bc6为64PASS，faf5f783为100PASS，API a9f3a4cd为2PASS。
发现bounded时间端点一直完整，真正遗漏的是explicit grouping field语言span。既有一次bounded
repair保留missing_span，并要求dimension literal原样保留；重现57ff1d3c为2RED/4PASS，最小缺轴
structural check后7bc385b1为51PASS。无runtime canonical补猜、无UCI production lookup。

native Admin Auth/Fabric IQ product-0e705d77：T01三年、B01六个月正式completed/Inspection/Facts/
Answer/Memory=true，ordered amount与独立Oracle精确一致；结合六Shape既有Real为8/8正例。
T02该轮RATE_LIMITED不作为超限证明；补充product-9906e4f0的T02为CONTRACT_DRIFT且ZERO
Facts/Memory，完整25月拒绝成立。B01补跑语言遗漏安全拒绝，保留该失败并继续同根因修复。
fresh v3 owned host已恢复现有Admin SSO，无Desktop操作；时间audit及下游Cloud验收继续。

多轮、两固定模板、history/restore/rename/archive/reload、resource lifecycle、owner/IDOR、
Test A RLS adjacency、late/stale/policy revoke、rate-limit/recovery与Final Oracle仍待完成。
full backend当前运行仅阶段进度，不能计PASS。relationship CONTRACT_GAP与Test B
DEFERRED_BY_TEST_PRINCIPAL保留；12-row/N+1/8-column不变；Local完整Real不重复。
所有runtime资产只在PBIAgentTest/M6.5，原始Oracle未覆盖。全部mandatory及fresh Gates后才version
M6.5/中文commit/push/自身exact-SHA CI/Remote Audit/clean/shutdown，之后STOP。
