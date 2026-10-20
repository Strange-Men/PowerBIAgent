# M6.5 — Cloud Runtime Contract STOP

## 当前合同状态（2026-10-20）

旧 numeric / Decimal representation / temporal compatibility 停点均已被用户明确窄 correctness
授权取代，failure-first、最小实现与 Cloud 全链复验成立。8/8 QueryShape PASS，当前无上述 STOP。
详细原始失败保留在下方历史与 Error Ledger；不将旧禁止措辞继续作为当前授权。

唯一保留的 Cloud capability gap：Fabric IQ relationship payload 缺 cardinality，不能建立现有
跨表执行需要的关系 authority；relationships=[] / NOT_VERIFIED 不变。已批准 flat Sales 模型
不依赖该能力，不推断、不实现 relationship normalization。

numeric string 仅在 fresh exact runtime numeric object + exact result lineage + strict ASCII lexical
proof 后原字符串直接 Decimal；currency/grouping/locale/exponent/unknown type 拒绝。YEAR integer
仅 exact model/fingerprint/table/column 与可信 YEAR binding 后接受；没有该 authority 仍 fail closed。
available horizon 超限诚实 UNKNOWN；full25months 超12 CONTRACT_DRIFT，ZERO Facts/Memory。

所有证据仅 PBIAgentTest/M6.5；状态/剩余项见07/09与验收 Matrix。Settings.version=M6.5发布候选；仅自身CI/Audit/clean/shutdown全部成立后生效。

## 历史：整数年份结果检查 STOP（已被后续明确授权取代）

product-25d5ebdd / ERR-65-008 的正确 year DAX 曾被 _date_value 拒绝，ZERO Facts/Memory。
最新用户允许 proven YEAR integer compatibility；24RED reproducer 后最小 forward-fix，
product-0e705d77 正式 TREND、product-eec816f2 六月 BOUNDED_TREND 全链及 Oracle PASS。
既有 MONTH/DAY date representation、Plan/DAX/Facts authority 未改变。

## 历史：时间粒度 authority STOP（最新operator授权已取代）

最新用户已授权普通correctness持续修复。ERR-65-005 Year展示与ERR-65-007语言证据已完成
failure-first、最小修复、邻近回归及正式Cloud复验；六Shape已有正例，金额/成员/分组Oracle不变。
当前未完成项为TREND/BOUNDED_TREND及其后续验收，不能写M6.5 FINAL COMPLETE。

fresh normalized temporal-authority-c5ad16f3及raw-temporal-authority-1504b4c8/e7297345证明：
实际GetSemanticModelSchema temporal列只有Name、Type、FormatString，无表达式、source/key、
hierarchy或grain。Year Integer不证明year grouping；YearMonth DateTime/D不证明month projection。
product-5fe5407e T01已精确绑定Year但被existing completeness拒绝；B01无法证明唯一date/grain；
两者均ZERO DAX/Facts/Memory。合成永久负例test_m6_5_temporal_authority_gap.py证明类型/格式
不能单独授予trend执行authority。

现有Grounding month fallback需要完整runtime members；该列25成员超过12 business rows。
采用first12、分页或有界子集补证会改变完整性authority。现有ModelOverrideRegistry可承载明确
exact-model temporal绑定，但当前未配置、未取得runtime grain proof；identity/fingerprint仅证明
对象未换，不能证明日期投影语义。不得把离线模型设计或Oracle作为production proof注入。

当前合同缺口为CONTRACT_GAP_TEMPORAL_GROUPING_AUTHORITY（ERR-65-006）。继续两trend需要
额外获证明的既有temporal binding，或改变Grounding/Plan completeness authority；后者命中
用户最新明确STOP边界。保留关系cardinality已知gap、Frozen factual chain和12-row不变。
版本仍M6.4.1；未stage/commit/push/新CI，最终服务与本地验证回执见07/09。

## 前序 checkpoint 历史（以下停点已被后续授权取代）

## 最新STOP：ERR-65-005 Integer Year presentation（2026-10-20）

ERR-65-004窄Decimal compatibility已failure-first→minimal fix→357专项PASS。正式Cloud
三个金额Answer/Facts/Memory与Oracle PASS，AOV沿用预定容差；未修改Facts authority/DAX/Oracle。
新product-e863ff2f：按Sales[Year]分组的真实DAX返回2009/2010/2011及正确金额，但
answer_generation/presentation_date_invalid，Memory=false。9beaefea四永久RED分别int/Decimal
金额来源、AnswerBuilder/StructuredPresentation证明Year名称被判为MONTH，然后formatter拒绝2009。
该缺陷独立于Decimal合法numeric type，修复需改变Frozen time-grain presentation判定；本轮仅授权
representation兼容。按用户新P0 STOP条件保留证据，不自行扩修、不改expected、不封板。
剩余八Shape及下游未完整PASS；版本M6.4.1，未提交/push/Exact-SHA CI；服务关闭证据在外部Diagnostics。

以下为前序合同停点历史，最新状态以上述段与07/09为准。

最新2026-10-20：用户已授权ERR-65-004窄Frozen Decimal compatibility；下方STOP为历史。
finite Decimal representation正例/invalid负例failure-first与最小修复完成，专项252PASS；
正式Cloud三个金额Answer/Facts/Memory及Top5 Country Oracle PASS。剩余矩阵与下游仍在执行，
Year对象/展示和语言证据失败正在诊断，限流恢复保留失败证据。未升版本/提交/封板。

## 当前STOP：Frozen Decimal兼容（2026-10-20最新授权；取代下方停点）

用户已明确批准TYPED_NUMERIC_STRING_NORMALIZATION，原Provider numeric gap已获保守合同处置。
实现只在fabric_iq_normalization：current runtime numeric schema object、exact result lineage、
纯ASCII小数lexical、直接Decimal解析；缺任一条件CONTRACT_DRIFT。exponent未实际出现，不允许。
不parse currency/grouping/locale，不经float、不增加wire精度、不改DAX或Frozen authority。

failure-first9fbf748a=7FAIL/32PASS，补充runtime freshness测试66c628a7=1FAIL/40PASS；
实现后9a383308=168PASS。原无schema numeric文本拒绝仍PASS。
numeric-final-de9f099e实际Cloud：20972594.5680、-1526667.8600精确scale4一致；
523.3075与独立AOV ratio差<=0.0001 GBP。记录raw wire/normalized Decimal/type/Oracle/tolerance，
不宣称IQ提供未证明精度。

新根因ERR-65-004：现有Facts和AnswerBuilder支持Decimal，但Frozen ValidationService
_check_metric_provenance仅允许int/float，触发answer_metric_non_numeric；报告KPI同类型限制。
正式Cloud product-88da72af S01经现有deterministic DAX取得未截断真实结果，随后
answer_validation_failed/response_failed、Memory=false。synthetic正式链e9338ba4复现同错误，
positive RED永久保留；错误值不得进入Facts/Memory的negative独立回归保留。
把Decimal转float会违背本轮原字符串Decimal合同；修复该validator属于Frozen Core，用户明确要求
必须修改Frozen才STOP，故当前结束而不自行改Core。尚未完成八Shape/下游/FullGates，不能发布M6.5。

前序503有两个独立原因：owned空DB未初始化（copy/hash后既有Alembic完成）及metadata限流；
未当numeric失败或PASS，原回执保留。owned host5173与runner已关闭，owned temp cleanup=true；
未读取/改用户DB。Settings.version=M6.4.1；未stage/commit/push、无本次Exact-SHA CI。

## 当前合同停点（2026-10-20；取代下方历史停点）

用户已完成同模型Desktop Replace；canonical身份原P0已有正式合同与独立Oracle，未重做数据。
本轮恢复owned5173宿主，用户一次补充探针后现有Admin会话有效。后续同会话自动运行，不再登录。

fresh actual focused-contract-18f2dc1c的ValueSearch返回complete、citation绑定模型，
15056BL/85123A/France均exact table/column/value证明。contract-followup-11ee05f6通过现有
Adapter与Grounding证明15056BL、15056bl→15056BL、47503J尾空格→47503J；未知商品无绑定。
这些都是targeted existence，未声称5131完整词表。full countries实际CONTRACT_DRIFT，未扩大12行。
wrong-column/fuzzy/duplicate ambiguity及numeric拒绝等focused regression共81PASS（6ad58a57）。

当前STOP：**CONTRACT_GAP_NUMERIC_AUTHORITY**。实际三个金额FormatString均0.0000，
inline Decimal cell仍string。相同ROW诊断中measure是string、measure+0是JSON number；
AOV两者均523.3075，独立ratio约523.30749726775956。另scaled/residual探针返回523307500/0，
无法据此定位为纯传输舍入或已发布measure定义差异；runtime Schema不提供expression authority。
独立Oracle的预定AOV容差不是授权把任何formatted cell解析为numeric fact。

fresh tools/list的ExecuteQuery只有artifactId、daxQueries、maxRows，无outputSchema、
raw-numeric或格式控制选项。2026-10-20重读
[Microsoft官方IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)
也未提供Decimal字符串精确编码规则。没有足够合同支持本轮Adapter-only精确数值forward-fix。
原numeric validator继续CONTRACT_DRIFT；不解析货币或其它display string、不加零改生产DAX，
不以外部诊断QueryResult替代事实链，不改Oracle/expected/Frozen Core/Provider。

按用户本轮Provider contract gap STOP条件结束当前推进；八Shape、multi-turn、report、resource、
security adjacency及FullGates尚未完成，不称M6.5 COMPLETE。Settings.version仍M6.4.1，
无新production修改、Cloud写入或业务Facts commit，无stage/commit/push/本次Exact-SHA CI。
官方HTML、合同诊断、截图与summary均只在PBIAgentTest/M6.5；宿主保持运行保留会话。

日期：2026-10-16；Settings.version=M6.4.1。

最新用户已明确批准Canonical Product Identity+Numeric Measure Format处置；本文保留旧STOP原件，
当前实施与operator重发布状态以07/09及Metric Contract补充为准。用户已发布Online Retail II M6.5。
当前用户条件为“如果单表模型仍暴露新的P0 architecture blocker，再STOP”。
本次STOP是原始StockCode literal身份与Power BI模型身份/Oracle合同冲突；不重新打开关系normalize。

## 已取得的实际证据

批准PowerBIAgent-M6-Dev Workspace中模型名唯一，Resolve和当前Admin Schema identity一致。
实际只有Sales，16列（含SourceSheet/SourceRow）和7 measures，零关系。
COUNTROWS=1,067,371、Country distinct=43、YearMonth distinct=25。
Total Quantity=11,420,305、Total Orders=40,077、Unique Customers=5,878、Cancelled Orders=8,292，
全部经实际IQ、原有typed normalization及独立Oracle核对。

scoped ValueSearch→exact model/table/column/value verification已实际证明France/Germany/
United Kingdom/StockCode 85123A；未知国家返回空候选。targeted proof不声称完整词表。
正式native HTTP Total Orders完成：scalar plan、1条deterministic DAX、40,077、Layer3/Facts/Presentation
一致、Memory commit=true、LLM DAX calls=0。Year枚举在dimension_unresolved澄清、ZERO DAX/事实提交；
不是ENTITY_LIST PASS，未更改Prompt或Frozen Grounding以迎合。

## P0：原始literal与模型member identity不一致

原始Oracle StockCode区分大小写/尾随空格，共5,305个；实际模型distinct为5,131。
[Microsoft官方数据类型说明](https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-data-types)
明确Power BI文本引擎case insensitive，自动去掉trailing spaces（读取2026-10-16）。
独立单列审计为173组case变体，加1组尾随空格变体，完全解释174个distinct差额；原数据没有删除。

| 原始literal | source行数 | source eligible quantity | exact ValueSearch | Cloud filter诊断 |
|---|---:|---:|---|---|
| 15056BL | 923 | 9,646 | 15056BL | 1,016行 / 9,772 |
| 15056bl | 93 | 126 | 空 | 1,016行 / 9,772 |
| 47503J | 80 | 347 | 47503J | 81行 / 348 |
| 47503J尾随1空格 | 1 | 1 | 空 | 空 / 0 |

这些filter仅为明确别名的只读诊断，不是由用户产品Plan生成的业务PASS。
Power BI按其已声明文本语义执行；现有Grounding exact成员证明也正确拒绝不存在的raw spelling。
冲突是当前批准验收要求同时保留原始literal身份、原始case-sensitive Oracle与未加identity键的
宽表模型。存在证明只能证明model member，不能证明该member等同一个原始source literal。
不能将9,772声称为原始15056BL的9,646，也不能把5,305 expected改成5,131来隐藏差异。

合法处置需要明确选择model canonical identity/equivalence和对应Oracle合同，或独立批准无损
source identity建模方案；本轮不自行选择、不编码UCI例外、不改DAX/Facts/Grounding/原数据。
按用户新P0条件STOP，不继续八Shape/报告/安全等发布验收，不宣布M6.5 COMPLETE。

## 独立测试模型格式问题

三个Decimal measures的实际FormatString带¥与千分位，IQ返回如¥20,972,594.568的string，
原有numeric validator拒绝CONTRACT_DRIFT。GBP来源没有改变，¥展示不符合Metric Contract。
明确诊断表达式measure+0返回numeric：20,972,594.568、-1,526,667.86、523.3075；前两金额对齐，
AOV与预定<=0.0001 GBP tolerance一致。但诊断不改变正式Builder，也不计正式金额query PASS。
未解析currency text、未放宽数值合同、未修改model格式或republish。
operator格式修正可独立准备；不能解除上面的StockCode身份P0。

## Evidence与收口

所有actual数据/receipt只在PBIAgentTest/M6.5：

- Acceptance/20261016-cloud-real/runtime-7484b23f.json：首个scalar FAIL。
- runtime-5a6a91b4.json：actual Decimal descriptor/string wire结构。
- runtime-c1663c21.json：formats/四指标PASS/控制数失败。
- runtime-4eec9f5f.json：actual targeted proofs与unformatted numeric diagnostic。
- product-counts-998ee225.json：正式Total Orders PASS与Year clarification。
- collation-eebadf09.json：实际case/space lookup及filter诊断。
- Diagnostics/20261016-cloud-real/stockcode-case-reconciliation.json、
  stockcode-collation-reconciliation.json、literal-source-comparison.json、official-text-collation.json。

新numeric text boundary负例及既有targeted/inline回归由canonical runner记录；不修改production。
fresh专项b7cebe6a为66PASS；Ledger1cd10d91、Documentation17900f94、Repository Safetydfbba656、
Artifact Governance66d0f392 PASS。owned probe进程与5173 listener均为0；五个空的owned runner temp
在确认外部绝对路径、空目录且无活跃owner后清理；失败runner未生成receipt不伪造为正常退出。
stop/cleanup hash receipt仅在外部Diagnostics/20261016-cloud-real，测试DB/证据保留。
旧失败原件保留；profile/Oracle/accepted matrix不重做。版本保持M6.4.1，未stage/commit/push，
无M6.5自身CI/Remote Audit。没有Local MCP重复Real、model写入、权限变更或第三Provider。
