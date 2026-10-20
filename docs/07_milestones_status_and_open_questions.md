# 07 — 当前项目状态

> Settings.version=M6.5.1；M6.5.1 FINAL COMPLETE（以本提交自身 exact-SHA Full Validation、Remote Audit、HEAD=origin/main、clean/shutdown 全部成立后生效）；M5 FINAL/FROZEN有效。

## M6.5.1 — Chinese / English Localization Platform FINAL COMPLETE（2026-10-21）

扩展现有 DisplayLocalizationService/Registry/Formatter/Renderer，统一 zh-CN/en-US Presentation
Context；i18next/react-i18next bundled resources、typed keys、Babel 与 Localization Completeness Gate。
全局入口为“设置 → 常规 → 语言”；本地持久偏好，无账号 DB preference。已有结果和报告复用
immutable typed presentation recipe，只重新展示，不重新理解、Grounding、Plan、DAX 或查询。
缺 recipe 的旧历史明确不可重投影，不反解析旧回答。Locale 不进入事实、Memory、模型或授权 authority。

最小 native Cloud：SCALAR、GROUPED、单 KPI Report 各一次成功事实分析，zh/en/zh 投影 hash/raw
rows 一致，ZERO 新增 Fabric IQ/ExecuteQuery；Report 一个 KPI、一个查询，双语 view/download
分别一致。原始 Report Assembly 一致性复核保留，切换不进入 Facts 构建/复核。
Backend 10b01f6d=3839PASS/1SKIP/15既有warnings；Semantic 127a316e=819PASS；Golden
 e4ad24b9=11PASS/1manualSKIP；Frontend 9db4fcee=173PASS；Typecheck/Lint/Build 与治理门 PASS。
失败原件、generic display hints 最小修复与报告既有限定词/默认覆盖边界见
[M6.5.1 milestone](milestones/m6/m6_5_1_chinese_english_localization_platform.md)。

PHASE 0 独立提交 bac2f33b093fc436615bdadb4670eb950ec1fdc0 / 自身 Full Validation
39403675734 SUCCESS，Remote Audit/clean/shutdown PASS；不与本轮功能提交混合。
M6.5.1 发布仅按本提交自身 exact-SHA Full Validation、Remote Audit、HEAD=origin/main、clean/
shutdown 全部成立生效，不继承旧 CI；自身 SHA/CI 回执置仓库外 Governance，避免循环自引用。
M5 Frozen Core、12-row/N+1/8-column、relationship cardinality CONTRACT_GAP、Test B
DEFERRED_BY_TEST_PRINCIPAL → M6.6 保留。后续为 M6.5.2 Web / SSO Productization →
M6.5.3 VM Remote Deployment & Internal Pilot → M6.6 Enterprise Production Readiness Seal。
本轮完成后 STOP；不进入后续阶段。

## M6.5 FINAL COMPLETE（2026-10-20）

Settings.version=M6.5；M6.5 FINAL COMPLETE。公开真实业务数据 Cloud mandatory 已完成。
Final SHA：`8e63f0bd770c3ec819a789f13c20128456fec591`；自身
[Full Validation 39400357886](https://github.com/Strange-Men/PowerBIAgent/actions/runs/39400357886) SUCCESS。
Remote Audit PASS；封板时 HEAD=origin/main，worktree/staging clean，owned service shutdown 成立。
本轮 POST-FINAL CLOSURE 只更新文档，其自身 CI/Audit 独立于上述 M6.5 功能封板证据。

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
Artifact/diff PASS。最终发布自身 exact-SHA CI 已 SUCCESS；前序本地证据与远程 CI 分层记录。
所有assets仅PBIAgentTest/M6.5，正式tests/fixture定义/doc在Git，无PBIX/DB/token/data dump提交。
Frozen存在明确批准的窄correctness forward-fix，authority/QueryShape/Plan/DAX/12-row保持；
ERR-65-012仅保留用户当前完整table[column]语言限定，leaf-only触发现有bounded repair，
runtime仍证明对象；failure-first e0f5b9f7四RED、最小修复9cf029ba专项邻近124PASS。
relationship cardinality CONTRACT_GAP已知限制、available horizon超限UNKNOWN、refresh UNKNOWN。

后续正式路线：M6.5.1 Chinese / English Localization Platform → M6.5.2 Web / SSO Productization
→ M6.5.3 VM Remote Deployment & Internal Pilot → M6.6 Enterprise Production Readiness Seal。
用户已配置远程虚拟机，作为 M6.5.3 基础；内部远程 Pilot 不冒充 Enterprise Production Seal。
POST-FINAL documentation closure 已独立通过自身 CI/Audit/clean，fresh main 已进入本轮批准的
M6.5.1；不提前实施 M6.5.2/M6.5.3/M6.6。
12-row / N+1 / 8-column、relationship cardinality CONTRACT_GAP、Test B
DEFERRED_BY_TEST_PRINCIPAL → M6.6 与 M5 Frozen Core 全部保留。

## Historical — 前序验收进度 — 2026-10-20 temporal correctness closure

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

## 历史停点 — M6.5 Explicit Temporal Binding（已被最新授权替代）（Settings.version=M6.4.1）

**当前边界 STOP：CONTRACT_GAP_YEAR_TREND_INSPECTION / ERR-65-008（2026-10-20）。**

最新用户明确允许existing ModelOverrideRegistry作为server/operator temporal semantic authority。
配置仅在PBIAgentTest/M6.5/Evidence/20261020-explicit-temporal，经native approved Workspace/model
selection、exact runtime identity及fresh schema fingerprint验证；Year→year、YearMonth→month、
Date→existing typed default role，不新增DAY grain。production仅model_override拒绝矛盾runtime
grouping并保留runtime优先；failure-first326b4df8=2RED/14PASS，c69fa187=107PASS；更新focused
f55e6532=143PASS（六文件，27.93秒），runner temp_cleanup=true。

普通fresh host/native Auth/Fabric IQ的product-25d5ebdd：T01 binding/completeness通过，年度DAX
真实返回2009/2010/2011与825685.7600/10303952.4040/9842956.4040，独立Oracle金额一致；
ResultInspection._date_value拒绝整数年份，result_trend_temporal_value_invalid，ZERO Facts/Memory。
外部failure-first3d16f63f=1RED；永久boundary test保留原始轴且拒绝inspection绕过。
B01在semantic_coverage_incomplete拒绝，ZERO工具/Facts/Memory，缺失语言span未被现有observer
保存，尚未精确诊断；不能算BOUNDED_TREND正例。T02全25月CONTRACT_DRIFT，ZERO Facts/Memory，
超限负例PASS。六种既有Cloud正例保留，两个trend与下游仍未完成。

本轮用户明确禁止修改ResultInspection，现有inspect仅接收plan/result而无validated grain证明；
要验证integer year顺序须明确该既有结果验证边界的兼容合同。当前未改Inspection/Plan/DAX/Facts，
未合成年份日期、未改shape或Oracle、未放宽12-row。ERR-65-006原分组authority阻塞已解除，
不再作为当前停点；relationship gap与Test B deferred保留。版本M6.4.1，未stage/commit/push/新CI。
历史完整Backend/Frontend等Gates仅证明其当时快照，不能继承为本轮Final。
本轮Security4ca76b36、Ledger9325b200、Architecture739fb1aa、Documentationc8735d1e、
Artifact0c8bdd03及git diff --check PASS；不冒充完整Final Gates。owned host126604/runner126364
已核对parent与exact外部路径后停止，owned进程0/5173监听0；runner3407ecc9 temp_cleanup=true，
受控终止exit不是validation PASS。最终治理/cleanup回执见外部closure-audit.json；配置/DB/证据原件保留，
host restart改变runtime key后原配置fail closed，不自动重绑定。

### 前序 checkpoint — 原 temporal grouping authority STOP（已被最新operator授权取代）

**历史 architecture STOP：CONTRACT_GAP_TEMPORAL_GROUPING_AUTHORITY。**
最新用户授权已取代此前普通P0机械STOP；ERR-65-005已最小presentation修复，整数category
原样展示，月份/日期只消费现有canonical/runtime binding。failure-first eee2ae4a四RED；
c42ab1e4专项167PASS、7d9a7917邻近311PASS；product-5fe5407e G01/M01正式Cloud PASS。
ENTITY_LIST language维度缺失有界repair及filter shape提示修复后，product-bff94686 E01/F01
正式Cloud completed、目标shape、Facts/Memory和独立Oracle全部PASS。F01确为FILTERED_AGGREGATION。
历史金额和ranking正式证据保留；六shape已有正例，TREND/BOUNDED_TREND未PASS。
两次fresh原始GetSemanticModelSchema只含Name/Type/FormatString，无expression/key/grain；
Year Integer不证明year temporal grouping，YearMonth DateTime不证明month-start projection。
现有完整month成员fallback在该25成员列与12-row合同冲突，不能枚举first12/分页/targeted subset自证。
product-5fe5407e T01在canonical_shape_trend_temporal_dimension_required拒绝，ZERO DAX/Facts/Memory。
继续这两shape需要当前未获证明的temporal binding或改变现有Grounding/Plan completeness authority；
按最新用户真正architecture STOP条件停止，不增加Provider/QueryShape/proof，不改Oracle或模型。
当前代码验证：focused618ee569=175PASS，Semantic428220e3=819PASS，Goldenafece63c=11PASS/1manualSKIP，
完整后端067ac239=3751PASS/1SKIP/15保留warnings；typecheckc8f1e295、lintb553556f、buildc5a0d9ea PASS。
Securitya65cd7b6、Ledgerc4dd2f1d、Architecture266b8b1f、Artifactae79ce7e、Documentation56abc4dd PASS；
前端首轮worker/等待超时d8140c21及低并发972bb141超时原件保留，后端结束后正常命令
89bf6494独立复核160PASS，无timeout/expected修改。当前本地验证通过，不能当M6.5 Final；
下游multi-turn/report/resources/security未全验。
版本仍M6.4.1，未stage/commit/push/新CI。测试资产仅PBIAgentTest/M6.5；owned DB保留。
本轮Admin经用户选择恢复，后续未要求Desktop。owned host121172/runner113464已核对父进程及
外部host路径后停止，5173无监听、owned进程0、runner temp_cleanup=true；owned DB与证据保留。
当前runtime外部driver动态刷新真实production Understanding，无auth/claim/proof注入；最终必须普通启动复验。

以下为本轮checkpoint历史，当前状态以上述最新architecture边界为准。
2026-10-20最新用户已授权ERR-65-004窄Frozen Decimal compatibility，取代下方历史STOP。
仅verified numeric representation支持finite Decimal；来源值不转float、不round、不解析string，
bool/nonfinite/string及无provenance拒绝。Answer metric/Report KPI/FactOutputValidator/展示numeric门
已failure-first；Report projection模型pre-validator防止Pydantic先coerce bool/string，Renderer直接保留Decimal。
专项252PASS（1ddba09a）；123 Adapter/presentation/inspection PASS（c44f859c）。完整后端2f8056bd
3682PASS/1SKIP/15既有warnings属于较早代码快照，后续修复仍须最终重跑，不能冒充Final验证。
当前Cloud：product-3ebceafa S01与R01 completed/Oracle一致/Memory=true；product-cbb2eb15
S02 Cancelled Amount与S03 AOV正式Facts/Answer/Memory PASS，AOV沿用<=0.0001 GBP容差。
E01 Year澄清、G01展示ValueError、M01非verbatim语言证据拒绝未PASS；限流失败保留并paced recovery。
fresh Year runtime exact/qualified对象可证明，未修改Grounding。owned5173宿主运行，现有Microsoft
登录自动恢复，无本轮人工登录或Desktop操作。八Shape/下游与Final Gates仍未完成；版本M6.4.1，未提交。

以下为前序checkpoint历史，当前状态以上述最新段与实时证据为准。

2026-10-20最新授权Numeric Authority Closure已实施极窄TYPED_NUMERIC_STRING_NORMALIZATION：
fresh numeric schema对象/exact lineage/ASCII小数形式/Decimal直接解析/既有检查链；无currency、
grouping、locale或exponent。failure-first9fbf748a为7FAIL/32PASS；邻近9a383308为168PASS。
numeric-final-de9f099e实际Cloud三scalar通过：Total Sales与Cancelled Amount精确scale4对账，
AOV523.3075在<=0.0001 GBP预定容差内，raw wire→Decimal→Oracle记录完整、不增加wire精度。
当前新STOP：ERR-65-004，Frozen ValidationService只接受int/float，Decimal由既有Facts传入Answer
后触发answer_metric_non_numeric。正式Cloud S01=execute_dax成功/response_failed/
answer_validation_failed/Memory commit=false（product-88da72af）；synthetic正式链e9338ba4同根因
RED保留。Report KPI同类型限制。修复必须改Frozen validator；不把Decimal转float绕过用户合同。
当前只改Adapter normalization与测试/状态文档，Frozen Core production diff=0；不封板/提交/push，
版本仍M6.4.1，FullGates未完成。owned5173宿主已停止、runner退出并清理temp；证据均M6.5。
后续路线按最新授权记入08：M6.5.1 Localization Platform、M6.5.2 Web/SSO、M6.6 Seal，本轮零实施。

2026-10-20当前停点：owned验收宿主5173已恢复，用户一次补充探针完成后现有Admin会话有效；
同会话自动follow-up无需再次登录/发布。focused-contract-18f2dc1c实际证明15056BL/85123A/France
exact model/table/column/value；contract-followup-11ee05f6经现有Adapter与Grounding证明15056BL、
15056bl→15056BL、47503J尾空格→47503J，unknown空候选；full countries仍CONTRACT_DRIFT。
fresh专项81PASS（6ad58a57）。numeric仍STOP CONTRACT_GAP_NUMERIC_AUTHORITY：三个金额格式
确认0.0000，Decimal cell是string；ExecuteQuery只有artifactId/daxQueries/maxRows，无outputSchema
或raw-numeric选项。AOV wire523.3075与独立ratio不同，diagnostic表达式也不能授予精确编码authority。
官方文档fresh重验未提供此编码合同；不解析展示string、不改Builder/Frozen Core/12-row、不改Oracle。
本轮无production修改、无业务Facts commit/Cloud写入；八Shape/下游/FullGates仍未完成。
用户最新允许Provider contract gap STOP；详情见[合同停点](milestones/m6/m6_5_cloud_runtime_contract_stop.md)。
host保留供后续同会话消费，资产仅PBIAgentTest/M6.5；版本M6.4.1，未stage/commit/push。

2026-10-17新runtime-96e8467e已实际完成原Admin读取：17列/7 measures/零关系；两列声明、
1,067,371完整行/43国/5,131 canonical商品/25月通过，France/Germany/UK scoped proof通过。
三个金额measure Schema格式确认0.0000，但实际Decimal cell仍为string（20972594.5680、
523.3075、-1526667.8600），原numeric validator正确拒绝CONTRACT_DRIFT；四个整数指标对齐。
canonical StockCode四个lookup为空，后续聚合及full countries检查被RATE_LIMITED，不能当身份
不一致或completeness PASS。已准备一次缩小的原候选/数值结构补充探针并请求同会话点击，
不重新登录/发布、不改生产validator/Builder；当前尚未进入republish后的产品八Shape/Gates。

2026-10-17用户明确回复“已重新发布”，确认同一批准测试模型Desktop Replace已完成。
fresh fetch/main/HEAD=origin/main核对通过，staging空，只有既有授权diff。重新读取官方IQ消费合同，
新隔离宿主及bounded canonical/numeric驱动位于外部Acceptance/20261017-canonical-real；
旧collation入口未复用。当前Microsoft登录页超时，已请求一次恢复原Admin会话并运行新探针。
用户确认不替代runtime Schema、ValueSearch或numeric PASS；尚无本次republish后Cloud结果。
后续收到探针结果立即继续原授权Cloud验收；Frozen Core/12-row/Provider与版本均保持。

2026-10-16最新用户已授权继续，仅Canonical Product Identity+Numeric Measure Format，取代上次STOP。
旧profile/Raw Oracle/ValueSearch证据保留。新增独立canonical Oracle5,131 members/174碰撞组，
完整1,067,371行、metric totals与原Oracle一致；Raw Oracle SHA不变。Adapter按runtime列声明执行
尾随U+0020→invariant ASCII uppercase→bounded ValueSearch→exact verification，raw provenance列
不进入产品Grounding。Frozen Core/numeric validator/12-row envelope保持。failure-first10RED已保留，
专项/集成156PASS，完整后端3602PASS/1SKIP/15既有warnings，Semantic819PASS、Golden11PASS/1manualSKIP及架构/治理门PASS；新operator资产仅外部Model/operator-canonical-v2。
下一步回归通过后由用户替换同一自建Online Retail II M6.5，回复“已重新发布”后继续Cloud Real。
旧P0停点保留为历史；按最新STOP条件执行。后续M6.5.1尚无实施授权，版本保持M6.4.1。


2026-10-16当前STOP：实际Cloud模型完整行数/四计数指标及explicit ValueSearch已PASS，正式Total Orders
通过Plan/DAX/Layer3/Facts/Memory。原始StockCode5,305个与Power BI5,131个身份不一致；官方case-
insensitive/trailing-space语义及真实literal filter/source对账完全复现。原始15056BL=9,646 quantity，
模型exact member filter=9,772（含15056bl的126），当前raw literal/Oracle与模型member合同冲突。
按用户“单表暴露新P0 architecture blocker再STOP”停止实施/完整Cloud验收，不修改Core或expected。
另三个金额measure的¥格式让IQ返回Decimal string，严格拒绝；unformatted数值诊断对齐但非产品PASS。
详细结论及actual回执见[Cloud runtime STOP](milestones/m6/m6_5_cloud_runtime_contract_stop.md)。
下方等待登录/发布为前序checkpoint；本次已实际登录和读取新模型，STOP由本段定义。


2026-10-16用户确认测试模型已发布。fresh fetch仍为既定main基线，无远端漂移，只有本轮授权diff，
staging空。官方Fabric IQ GA/delegated/scopes/selector/只读合同已重读；隔离原生Cloud Real宿主及
新的空测试存储均在PBIAgentTest/M6.5/Acceptance/20261016-cloud-real。旧宿主关闭后Auth会话失效，
当前等待恢复已批准Admin登录，再验证实际模型Resolve/Schema/控制总数/指标/八Shape。
用户发布确认不替代runtime模型或业务PASS；下方“未建立”为发布前checkpoint，当前已由本段更新。

用户最新批准完整单表Sales路径，取代此前关系CONTRACT_GAP的停止处置。全部1,067,371行保留，
不建DimDate/DimCountry/DimProduct/DimCustomer或关系，不造Category/Region。IQ实际relationship
payload缺cardinality的CONTRACT_GAP保留为已知Cloud capability gap，本轮不normalize或补猜。

完整profile、BUSINESS_METRIC_CONTRACT、独立Oracle和acceptance matrix保留，不重做：
43国、25月、5,305 StockCodes；missing Customer ID243,007、重复余项34,335及异常/取消行均保留。
Total Sales expected=20,972,594.5680 GBP，scaled integer与独立Decimal已对账。
公开数据和全部test/cache/evidence/model资产仅PBIAgentTest/M6.5。

fresh fetch仍main、HEAD=origin/main=`63287db28b519d7043bd762622e7eef586351201`，staging空，
只有本轮授权改动。用户实际Admin已完成只读IQ探针；工具schema与非空ValueSearch payload已证明：
artifactId/searchTerms/scope(tableName,columnNames)，Results bucket及Table/Column/Value/Score，
artifact_citation.ArtifactId和resultType=complete。原空候选及补充非空证据分开保存，不把metadata
probe计为UCI业务Real PASS。otherWorkspace ZERO request，未新增grant/Provider/Cloud authoring。

唯一correctness最小实现已完成：Cloud service传递当前SemanticFrame中的verbatim explicit literal，
Adapter scoped ValueSearch，exact model/table/column/value验证后交给既有Grounding。Score不选值；
fuzzy/wrong-column/unknown不绑定，duplicate exact保留歧义，targeted proof标为truncated以拒绝
完整词表/日期grain证明。无literal仍full snapshot，>12 fail closed；business12/wireN+1/columns8不变。
Frozen Core、CanonicalQueryPlan、DAX Builder、VerifiedFactSet、八QueryShape无修改。

failure-first 9RED/18PASS原件保留，最小实现后focused26PASS、Cloud/safety邻近174PASS、
Adapter/Grounding集成17PASS；Semantic819PASS、Golden11PASS/1manualSKIP、Architecture与Safety PASS。
首次全后端3570PASS/2FAIL/1SKIP/15既有warnings，两处为新增测试实例与文档当前版本标题问题，
已最小修正并保留失败回执。多literal exact/unknown/nonexact安全回归128PASS；最终当前代码
ad98eea6完整后端3575PASS/1SKIP/15既有warnings，前端160PASS、typecheck/lint/build PASS。
Safety/Ledger/Architecture/Documentation/Artifact治理门PASS，worker启动超时原件保留；全部runner temp清理。
Owned只读probe已停止、5173无监听；fresh fetch无remote drift、staging空。
上述automated和已有模型metadata probe不替代Online Retail II Cloud Real。

Cloud测试模型尚未建立。ValueSearch最小实现及完整回归PASS，下一步由operator按[单表步骤](milestones/m6/m6_5_operator_test_model_setup.md)
一次性创建并发布Online Retail II M6.5到批准的PowerBIAgent-M6-Dev，再继续Resolve→Schema→known-value
scalar→八Shape→multi-turn→report eligibility→history/resource→security→recovery→Oracle→Full Gates。
日期grain/模板section仅由实际schema及runtime证明；不能用模型定义注入authority或改模板迎合验收。
若单表仍证明新P0 architecture blocker再STOP，否则同根因failure-first/minimal fix/regression/Cloud Real。

Local MCP Real不做完整重复；Test B仍DEFERRED_BY_TEST_PRINCIPAL。M6.5未完成，Settings仍M6.4.1，
未stage/commit/push，无本轮exact-SHA CI/Remote Audit；不进入M6.5.1，不新增cache/reuse/Favorites。
详细runtime、历史失败及证据见[M6.5专项](milestones/m6/m6_5_cloud_real_business_validation.md)。

## Historical — M6.4.1 维护 / 发布判定

M6.4 FINAL COMPLETE；Final SHA `bdbe7189be21ff043340c2025625a9e3398310b0`；自身 [Full Validation 38693083553](https://github.com/Strange-Men/PowerBIAgent/actions/runs/38693083553) SUCCESS，Remote Audit PASS，封板时 HEAD=origin/main、worktree/staging clean。

M6.4.1 仅处理仓库外测试资产治理、README 信息架构、current-state 一致性、IQ 保守结果边界明确化及 Test B OLS 证据状态；不实施 Schema cache、connection reuse、Favorites/Preferences，不进入 M6.5。

Folder Governance：448 文件 / 44,252,661 bytes 原始副本验证通过；10 synthetic DB 仅 byte copy/hash。用户已人工删除旧五目录与仓库误生成五目录，fresh 验证 MANUAL_DELETE_COMPLETE；旧目录=0、仓库临时目录=0、active old-path reference=0、SHA mismatch=0。

本地 runner 已使用正确引用的正斜杠路径和 canonical owned temp；误生成五目录共2,928文件已归档并由用户清理，根因/失败证据保留，当前清理阻塞已解除。README 改为项目首页；配置排障及历史信息分别落在09/专项文档。fresh gates已通过，Settings.version=M6.4.1；发布按自身CI/Audit/clean生效。

IQ 正式 Cloud business rows ≤12，wire sentinel=N+1，columns ≤8；超界在 Facts 前 fail closed。CLOSED_AS_EXPLICIT_LIMIT，不扩大 completeness、QueryShape、Provider 或 Frozen Core。Test B 当前没有可用验收 principal，DEFERRED_BY_TEST_PRINCIPAL；后续生产安全封板仍须独立 Real OLS deny，不能用 Test A 或历史 PASS 替代。

专项交接见 [M6.4.1](milestones/m6/m6_4_1_test_asset_governance_and_post_final_closure.md)。M6.4 既有 Local/Cloud Real、Int64、lineage、完整性、报告来源、owner/RLS/late-stale 验收不重新打开。本轮无生产事实链变更；发布须本轮 Final commit 自身完整 exact-SHA CI、Remote Audit 和 clean，不继承 M6.4 CI。

本轮fresh：后端3521PASS/1SKIP/15既有warnings、Semantic819PASS、Golden11PASS/1manualSKIP、前端160PASS、Typecheck/Lint/Build及治理门PASS；补充runner/IQ负例16PASS。Local/Cloud Real未重复运行（无事实production行为变化）；不能计为fresh Real PASS。中文发布提交为`M6.4.1_测试资产治理与封板遗留收口`；自身CI/Remote Audit/clean全部成立后FINAL COMPLETE并STOP，不进入M6.5。exact-SHA回执按main当前提交和外部Governance解析，不继承旧CI。

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
