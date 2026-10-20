# M6.5 — Cloud Real Acceptance Matrix

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

## Historical — 前序 Cloud Real Matrix（2026-10-20，Final 尚未成立）

本节取代下方历史停点。8/8 正例、两固定 KPI 模板和五轮语义/Oracle 对账已成立；
生命周期、安全邻接及 Final Gates 继续，Settings.version=M6.4.1，未提交或推送。

| Shape / case | 原生 Fabric IQ Cloud 证据 | 判定 |
|---|---|---|
| SCALAR S01/S02/S03 | product-3ebceafa / product-cbb2eb15；Total Sales、Cancelled Amount、AOV | PASS；前两 scale4 exact，AOV ≤0.0001 GBP |
| ENTITY_LIST E01 | product-bff94686；完整三 Year 成员 | PASS |
| GROUPED G01 | product-5fe5407e；三年金额及整数 category 展示 | PASS |
| RANKING R01/R02 | product-3ebceafa / product-cbb2eb15；Country Top5、canonical Product Top10 | PASS |
| MEMBER_SET M01 | product-5fe5407e；UK/France/Germany exact targeted proof | PASS |
| FILTERED_AGGREGATION F01 | product-bff94686；实际 filtered_aggregation 与 France Oracle | PASS |
| TREND T01 | product-0e705d77；proven YEAR、2009/2010/2011 ordered rows | PASS；Inspection/Facts/Answer/Memory 全链 |
| BOUNDED_TREND B01 | product-eec816f2；2011-01 至 2011-06 六 ordered 月 | PASS；requested scope/coverage/Oracle 全链 |
| 全25月 negative | product-eec816f2；CONTRACT_DRIFT | PASS negative；ZERO Facts/Memory，12-row 不变 |

product-8bbee2f8 RP01 sales_report 与 product-86648043 RP02 sales_executive_report 原生生成、
view/download/content hash、shared Facts/Answer/Memory PASS。仅真实可用四 KPI；未造其它 section。
product-8bbee2f8 RP02 RATE_LIMITED 与后续失效拒绝保留；现有 restore fresh schema 后专业模板恢复 PASS。

product-624a9569 五轮指标/国家/时间与独立 Oracle、Inspection/Facts/Answer/Memory PASS。
原脚本最后一轮固定 SCALAR 断言为 false，原件保留；multiturn-contract-audit 依据既有
StateTransition 的 interpreted-or-inherited shape 和各自 Completeness，核对 exact scope 后 PASS。
最后一轮实际 FILTERED_AGGREGATION，用户没有要求固定 shape；没有修改 Oracle 或生产 shape semantics。
第二次 DAX 为独立 available-horizon probe，超限仍 UNKNOWN，不影响已验证 business scalar。

raw/canonical Oracle 独立保留；relationship cardinality CONTRACT_GAP、Test B
DEFERRED_BY_TEST_PRINCIPAL 继续显式记录。全国家/商品/月完整枚举超过12拒绝，targeted proof不冒充全集。
最终 mandatory 与自身 exact-SHA CI/Audit/clean/shutdown 全成立前不宣布 M6.5 FINAL COMPLETE。

## 前序 checkpoint 历史（不作为当前判定）

最新STOP为ERR-65-005 Integer Year→MONTH presentation。product-e863ff2f G01真实DAX正确，
但answer_generation/presentation_date_invalid、Memory=false；9beaefea四int/Decimal RED。
未修改time grain语义或expected，按用户新P0条件STOP；不宣称M6.5 FINAL COMPLETE。
Decimal专项3c30583a=357PASS，正式S01/S02/S03金额、R01/R02 ranking Oracle PASS。
E02 full-country超限fail closed、N01/KN01 unknown拒绝PASS；F01/K1/K2/K3数值Oracle一致但
shape为scalar，不能计为预期FILTERED_AGGREGATION PASS。E01/M01/T01/B01及下游仍未完成。

最新2026-10-20：用户已授权窄Frozen Decimal type compatibility，取代下方历史STOP。
product-3ebceafa正式S01与R01 PASS；product-cbb2eb15正式S02 Cancelled Amount、S03 AOV PASS，
均existing Facts/Answer/Memory链及Oracle一致；AOV仅批准容差。失败与RATE_LIMITED保留。
专项1ddba09a=252PASS。E01/G01/M01及剩余矩阵/下游/Final Gates未完成，当前为PARTIAL CLOUD REAL。

2026-10-20最新增量：用户授权typed numeric string合同后numeric-final-de9f099e三金额scalar
原wire→Decimal→Oracle PASS，scale4精确/AOV既定容差。正式S01在product-88da72af实际DAX成功，
回答因Frozen validator的Decimal类型不兼容response_failed、Memory=false；不是正式S01 PASS。
E01/G01亦未PASS，其失败保留而未改expected。当前ERR-65-004需要Frozen correctness scope，
依用户边界STOP；余下矩阵与FullGates未完成，不以168专项PASS替代Final。

2026-10-20实际增量：canonical targeted Adapter/Grounding大小写/尾空格正例与unknown、全国家
fail closed已取得fresh Cloud证据；81专项PASS。numeric Provider合同仍不足，按用户最新
Provider contract gap STOP条件记录CONTRACT_GAP_NUMERIC_AUTHORITY；余下正式八Shape/
multi-turn/report/resources/security/FullGates未执行完成。见Cloud runtime合同停点当前段。
原矩阵与Oracle保留，无positive替换或expected调整。

状态：DESIGNED / CLOUD NOT RUN。完整公开数据、固定现有八QueryShape、fixed模板、
strict envelope；每个case必须用fresh runtime Schema/member确认才冻结。当前状态见07；
定义见 [Metric Contract](m6_5_business_metric_contract.md)，风险见 [M6.5](m6_5_cloud_real_business_validation.md)。

2026-10-17用户确认同一批准模型已Desktop重新发布；新runtime/product矩阵驱动已准备，
当前等待恢复原Admin会话。尚无republish后的Cloud业务结果，不将发布确认当PASS。

追加actual checkpoint：runtime-96e8467e的Schema/完整控制数/Country targeted proofs及四整数
指标通过。canonical产品lookup为空；三个0.0000 Decimal measures仍string被拒绝；后续遭
RATE_LIMITED。补充contract probe待运行，republish后正式八Shape及下游Gates尚未执行。

2026-10-16当前追加合同：正式product dimension/filter只用runtime-proven StockCodeCanonical。
Raw StockCode5,305 literals仅审计；新增Canonical Product Oracle5,131 members/174碰撞组独立保留。
R02的商品key/expected迁至新canonical Oracle，原Raw TopN不覆盖；republish后的actual schema冻结后
才运行。新增15056BL/15056bl、47503J尾空格正例，unknown/ambiguous/non-equivalent ZERO DAX负例。
三个numeric金额format去掉currency text，原numeric validator不改。模型重发布尚未完成，非Cloud PASS。

## 八Shape与数据negative

| ID/Shape | 问题/条件（fresh schema后替换canonical对象名） | 独立Oracle/判定 |
|---|---|---|
| S01 SCALAR | Total Sales总销售额 | eligible整数amount与Decimal一致，1行 |
| S02 SCALAR | Total Orders、Unique Customers、Cancelled Orders、Cancelled Amount各单问 | each1行，独立population/sign/count核对 |
| E01 ENTITY_LIST | 有哪些销售年份 | 真实存在且≤12的Year维度，非凭空造Category；exact sorted set |
| E02 ENTITY_LIST negative | 有哪些国家（全部） | 完整source country count>12时fail closed、zero factual commit；不能把first12当全部 |
| G01 GROUPED | 各销售年份销售额 | ≤12行，source按实际year聚合、顺序/字段一致 |
| G02 GROUPED negative | 各国家销售额/各商品销售额（全部） | >12真实result必须拒绝；不maxRows扩容/分页 |
| R01 RANKING | Total Sales最高前5国家 | eligible country amount排序，N=5≤12，ties/ORDER BY独立核对 |
| R02 RANKING | Total Quantity最高前10商品 | StockCode唯一key、eligiblequantity排序，N=10；不按Description猜唯一产品 |
| R03 RANKING negative | 前13/20国家或商品 | actual result>12时closed，不截断；不存在13行也不能机械断言拒绝 |
| M01 MEMBER_SET | United Kingdom/France/Germany分别销售额 | 3个explicit exact Country定向证明，三行scope，不把分组与aggregate混淆；ValueSearch实现已完成，UCI Real待验 |
| F01 FILTERED_AGGREGATION | United Kingdom销售额 | 1行country exact filter，country-known-value；member proof必须先成立 |
| F02 FILTERED_AGGREGATION | United Kingdom/France/Germany销售额加总 | one aggregate与M01不同shape，Oracle同三国union |
| F03 FILTERED_AGGREGATION | 2011年1月至6月Total Sales | 原始timestamps[2011-01-01,2011-07-01)，不能漏6月30日时间 |
| T01 TREND | 最近6/12月Total Sales趋势 | 必须先证明measure-aware available horizon与canonical recent policy；当前2026与source2011差异显式披露，不改clock/假造数据 |
| T02 TREND negative | 全量月份/超过12月趋势 | 真实>12行拒绝，zero Facts/commit；完整月份grounding若已拒绝，记录前置stage |
| B01 BOUNDED_TREND | 2011年1月至6月逐月销售额 | 六ordered rows、month-start field/日期/完整coverage须runtime证明；当前25月member grain proof可能阻塞，待验 |
| B02 BOUNDED_TREND | 2010年逐月销售额 | 12ordered rows、N+1=13且无sentinel；全部月及timescope与source独立对账 |
| N01 semantic negative | unknown Country；known+unknown成员；不存在Category | DAX前clarification/no-match，ZERO QueryResult/Facts/semantic commit |
| N02 temporal negative | 反向/模糊时间，超source日期范围 | 与真实requested/observed/horizon独立，不能将empty/partial称完整有数据 |

E01/G01只在模型实际有Year后执行；如果没有，重新由fresh低基数真实字段设计。不能创建虚构业务
字段、缩短full数据或按已知答案直接构造Plan。R01/R02允许高基数维度TopN但不能机械保证positive，
Grounding若为prove dimension读取full member仍需记失败。M01/F01/B01尚无positive证明，
不能用上述设计表宣称八Shape完成。

## 多轮与产品链

| ID | 实际序列与对账 |
|---|---|
| P01 | fresh Total Sales → follow-up France → replace Total Quantity → member correction Germany → time correction2011H1；逐轮measure/filter/time/oracle，不继承无关slot |
| P02 | fresh question清旧scope；general current-message-only/ZERO工具、schema、member、pending、Memory变更；后续formal query只承接合法committed状态 |
| P03 | 模型刷新/重新选择/换model/new conversation；stale generation、晚到response拒绝，不跨model/policy继承 |
| P04 | 完成问答 → history读取 → rename → 新聊天restore → archive/restore → browser reload/session；owner+current access，展示title不改事实/HTML |
| P05 | 显式选择sales_report及sales_executive_report各生成 → view/download；只使用fresh eligible section，source=Fabric IQ；值/scope/order/provenance与sharedFacts一致，unknown refresh/tax保持UNKNOWN |
| P06 | 完整25月/高基数report section超界；必须在Facts/artifact/Memory前失败；不能悄悄drop已验证必需section或fallback另一template |

Report同scope两模板应使用同一query requirement/factual contract；各次generation按实际产品
查询执行并记录，不声称两次独立Real请求零重复。未来语言切换的单次分析是M6.5.1，不在本轮实施。

## Security adjacency 与性能

Admin独立scope/known-value，Test A实际Viewer RLS population单独Oracle；比较country/row/horizon与
role限制，不能用Admin oracle直接期望A相同。owner交叉history/report/unknown-ID等价拒绝；
late/stale、policy撤销、session失效在response/commit前阻止，otherWorkspaceZEROrequest。
Test B没有已批准usable principal：DEFERRED_BY_TEST_PRINCIPAL，不伪造OLS denyPASS。

每case收集Resolve/Schema/Query/LLM/whole/report耗时、stage call counts、低基数failure code、
429/timeout、Retry-After处理次数、recovery结果。未知数字quota不猜；不触发人为大规模load/LocalReal。
恢复通过真实普通产品reload/reselect/restore，区分慢速脚本推进与实际普通产品可用性。

## Evidence & Oracle comparison 合同

每个case有固定ID、问题定义hash、source/model definition/schema fingerprint、principal类别、
contractID、independentexpectedhash、实际terminal state。只保存脱敏低基数投影或artifact/hash索引，
不存token/GUID/raw schema/fullprompt/response/businessDB。公开source原始行仅外部dataset目录。

逐层观测User Question → SemanticFrame → CanonicalPlan → deterministic DAX → IQ QueryResult →
Inspection → Facts → Answer → Report；expected不能注入production/LLM。确证measure/filter/time/N/
ORDER BY/source/observedcoverage/horizon，无truncation误称complete。DAX执行LLMcall=0、无fallback。
Negative需检查前置stage与ZERO factualcommit，不能只检查HTTP错误码。

失败保持reproducer及rootcause；仅已授权correctness minimal forward-fix可focused后Cloudrerun。
当前批准单表Sales及explicit literal scoped ValueSearch最小路径；无literal全量成员仍>12拒绝。
若单表暴露新的P0 architecture blocker、需要扩大Frozen Core/12-row合同或Cloud authoring Provider则STOP。
relationship CONTRACT_GAP保留为已知能力限制，不normalize，不阻止同表查询。
Final需全部mandatoryReal、freshautomated/FullGates、自身exactSHA CI/RemoteAudit及clean；
下方原始设计不单独授予Real PASS；当前逐case判定与失败保留见顶部Cloud Real Matrix。
