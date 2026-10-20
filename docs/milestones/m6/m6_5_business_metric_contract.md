# BUSINESS_METRIC_CONTRACT — UCI Online Retail II

## 2026-10-20 获批补充：TYPED_NUMERIC_STRING_NORMALIZATION

仅Fabric IQ Adapter normalization消费current numeric runtime schema object+exact result lineage，
纯ASCII `-?[0-9]+(\.[0-9]+)?`，原字符串直接Decimal解析；不经float、不locale猜测、不currency/
grouping/text/NaN/Infinity，不接受尚未runtime证明的exponent。缺一条件CONTRACT_DRIFT。
不修改Frozen inspection/Facts/output/Memory authority；parsed value沿既有链继续验证。
wire小数位原样保留，不以Oracle补精度。Total Sales/Cancelled Amount继续scale4 exact，
AOV继续原独立ratio及<=0.0001 GBP容差；raw wire→Decimal→Oracle分层保存。
numeric-final-de9f099e三scalar wire→Decimal→Oracle对账PASS；product-3ebceafa / product-cbb2eb15
经获批 verified Decimal compatibility 后正式 Facts/Answer/Memory PASS。原 Raw/Canonical Oracle未改。
M6.5 Final仍取决于完整mandatory/Gates/自身CI/Audit，不能只以scalar通过宣称封板。

合同ID：`M6.5-DRAFT-GROSS-POSITIVE-v1`（保留原ID以保持Oracle引用稳定）。当前状态：已批准测试模型合同；
完整 offline profile、用户建模/重新发布及 Cloud known-value 已验证。这是明确 gross-positive 测试口径，
不宣称财务收入定义。当前状态见07，验收设计见
[M6.5](m6_5_cloud_real_business_validation.md)。

## 2026-10-16 获批补充：Canonical Product Identity

原合同ID与Raw Source Oracle原件保留；新增独立`M6.5-MODEL-CANONICAL-PRODUCT-v1`，只用于模型
canonical product-member对账。金额/eligible/cancellation/订单/缺客户/日期口径保持原合同。

| evidence | identity / purpose |
|---|---|
| Raw Source Oracle | 原始StockCode，case/space sensitive，5,305 literals；provenance/audit only，文件不覆盖 |
| Model Canonical Product Oracle | 去掉末尾U+0020空格→invariant uppercase→保留其它字符；5,131 members，用于Cloud产品查询 |

Sales模型新增StockCodeRaw（原始nominal StockCode）、StockCodeCanonical（明确等价类）。
全部1,067,371行保留；不删除大小写/空格变体或改原始workbook。Power BI文本编码仍可能折叠
StockCodeRaw，精确raw identity证据由原workbook、旧Raw Oracle、SourceSheet+SourceRow承担，
不得用loaded Raw的DISTINCTCOUNT冒充5,305个case-sensitive source literals。

正式rule ID：`TRAILING_SPACE_UPPER_INVARIANT_ASCII_V1`。完整source产品key均为printable ASCII；
普通Python ASCII uppercase与Power Query `Text.Upper(Text.TrimEnd(value, {" "}), "")`逐字符一致。
不去掉leading/internal spaces，不NFKC或转写，不改标点；未证明的非ASCII/control输入fail closed，
不通过LLM或fuzzy补canonical。15056BL/15056bl→15056BL；47503J/尾随空格47503J→47503J。

新独立计算只扫描产品key、eligible Quantity/Price，按原Excel number解码和scale4/Decimal定义，
不重做完整profile，Raw Oracle SHA仍`1e70c99fb552c6b1f5bd63c6e2def0ddd97fe530359486020472a31d24975f27`。
canonical distinct=5,131，174 collision groups，174 merged literal excess；总Sales=20,972,594.5680、
Quantity=11,420,305，整数/Decimal核对一致。canonical15056BL Quantity=9,772、Sales=49,685.4100；
canonical47503J Quantity=348、Sales=2,759.3600。raw15056BL Quantity=9,646仍保留，不混称。

新evidence仅外部`PBIAgentTest/M6.5/Model/operator-canonical-v2`：canonical-product-oracle.json、
canonical-product-aggregates.json、source-to-canonical.json、collision-groups.json及asset-receipt。
quantity/sales Top10分别按当前metric desc、canonical literal asc；Cloud ties遵守既有Builder/envelope，
不把离线排序注入Plan。代表mapping和每个raw member→canonical member单独保留。

runtime canonical列Description声明`PBIAGENT_MEMBER_IDENTITY_V1:`后接严格JSON：role=canonical、
rule、source_field、input_name；source列声明role=provenance_only。这是模型当前schema提供的合同，
Adapter验证列存在/type/相互绑定、未知规则拒绝；provenance_only不进入产品semantic eligibility，
并非Microsoft OLS状态。仅declared column可以归一化当前literal→scoped ValueSearch→exact candidate；
candidate自身不归一化，wrong column/fuzzy/unknown仍不绑定，duplicate保留歧义。
既有Grounding消费已证明候选并负责canonical写入；无第二Grounding或LLM authority。

三个金额measures保持numeric定义；operator格式去掉¥/$/£等货币文本，首选纯`0.0000`（无grouping）。
GBP只放description/metric contract/presentation metadata；不解析currency string，不改numeric validator。
纯数值FormatString是否返回可接受typed payload仍须republish后实际IQ证明，不能以格式定义称PASS。
本轮授权仅同一个用户自建Online Retail II M6.5在PowerBIAgent-M6-Dev内Publish/Replace，由用户执行。

## 官方来源与原始语义

[UCI Online Retail II / dataset502](https://archive.ics.uci.edu/dataset/502/online%2Bretail%2Bii)，
2026-10-15重读。Chen, D. (2012), DOI [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D)，
CC BY 4.0。UK非实体店gift-ware交易，2009-12-01至2011-12-09，官方1,067,371行。
官方文字使用InvoiceNo/UnitPrice/CustomerID；实际workbook预期为Invoice/Price/Customer ID。
只有实际header严格核对后可映射；若不一致停止profile，不能把Online Retail一年的文件当II。

## 行保留、类型与业务口径

| 项目 | DRAFT定义 |
|---|---|
| Grain | 一条原始发票行；两表append，source sheet+row为provenance，完整行数必须对账 |
| Invoice | 原始nominal文本ID；整数Excel值无损转文本。以C/c开头为取消发票，字母前缀不能丢。原始ID不去前缀、不跨日期猜唯一交易 |
| Cancellation/return | Invoice取消与quantity<0独立标记。不能声称所有负数都是customer return；无cancel reference不能匹配原订单 |
| Quantity | 原始signed整数；不abs、不改负为零。zero保留并诊断 |
| Price/UnitPrice | 原始GBP单价，使用Decimal及scale4 exact integer oracle，不逐行四舍五入到2位；负/零单价保留。无法无损scale4的值拒绝并报告 |
| Missing customer | 所有销售仍可纳入金额/数量/订单；Unique Customers只计非空ID。missing是unknown，不伪造customer ID，也不drop所有缺客户行 |
| Country | source原始值；官方定义客户所在国家，不假设shipping region/币种/客户唯一国家。不合并EIRE/UK等名，不进行地理分类 |
| Product | StockCode为nominal产品key；Description是原始行描述，不能据first description生成唯一产品事实。非数字item codes仍保留，无官方类别不生成Category |
| Duplicate rows | 完全重复也保留，重复participating/excess分别profile；没有官方行ID证明冗余，不能为好看dedup。维度distinct仅建立唯一key，不能去掉Fact行 |
| Date/time | 保留原始Excel日期时间；时区UNDECLARED，不猜UTC/北京时间。Date key为source日期；月key为当月1日。日期范围[开始日,下一期开始)包含末日全部时间 |
| Currency/tax | GBP/sterling有官方来源；tax/discount/freight/net-accounting未明，保持UNKNOWN。不能显示CNY/人民币、把raw signed amount称财务净收入 |
| Sale eligibility | 非C/c发票 AND quantity>0 AND price>0；全部excluded行仍保留且signed amount对账。这是明确gross-positive定义，不是偷偷清洗或官方财务定义 |
| Fact horizon | 原始及每measure eligible行分别min/max；horizon不是Date表范围，不是refresh。2011-12只到9日须披露partial latest month |

## Fresh full-data profile（离线，Cloud尚未执行）

完整workbook SHA-256 `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`，
45,622,278 bytes；官方ZIP经CRC及copy hash验证。两sheet分别525,461/541,910行，append后
1,067,371行，与官方实例数一致。实际header为Invoice/StockCode/Description/Quantity/
InvoiceDate/Price/Customer ID/Country，逐sheet严格匹配。

| Diagnostic | Fresh count/value |
|---|---:|
| Source Country / StockCode / nonempty Customer ID | 43 / 5,305 / 5,942 |
| Month count / timestamp bounds | 25 / 2009-12-01 07:45至2011-12-09 12:50（时区未声明） |
| Missing Customer ID / Description | 243,007 / 4,382 |
| 完全重复余项 / 参与重复行 | 34,335 / 67,242（全部保留） |
| C/c取消行 / distinct取消Invoice | 19,494 / 8,292 |
| 取消行正Quantity | 1（取消定义不能等于Quantity<0） |
| Quantity<0 / 非取消Quantity<0 | 22,950 / 3,457 |
| Quantity=0 / Price=0 / Price<0 | 0 / 6,202 / 5 |
| Price超过两位小数行 | 18（不逐行round到pence） |
| StockCode对应多Description | 2,848（不能用first description作为唯一业务成员） |
| 同Invoice多Country / 多非空Customer | 0 / 0（不证明invoice跨时点都是同一交易，date冲突待专门核对） |
| Eligible / excluded sale rows | 1,041,670 / 25,701（excluded仍在Fact中） |

按DRAFT口径：Total Sales=20,972,594.5680 GBP，Total Quantity=11,420,305，
Total Orders=40,077，Unique Customers=5,878，AOV=523.3074972677595628415300546 GBP。
Cancelled Amount=-1,526,667.8600 GBP（保留signed），raw signed amount=19,287,250.5680 GBP，
excluded signed amount=-1,685,344.0000 GBP。整数聚合与独立Decimal逐行eligible计算完全一致。
这些是公开source的离线expected，不是PowerBIAgent或Fabric IQ的实际结果。

2011H1 Sales=4,002,720.3510 GBP；France/2011H1 Sales=80,338.5300 GBP。
Top5国家按销售额依次United Kingdom、EIRE、Netherlands、Germany、France；source中的EIRE
保持原值。完整country/month/product expected仅仓库外Profile JSON，禁止进入production lookup。

首次profile读取被并行备用下载覆盖的working副本，EOFError失败回执保留；备用下载timeout后
停止，原部分副本标失败。官方完整ZIP另copy/hash到verified目录再extract，immutable snapshot
读取并CRC校验。第二次profile在保守cross-max × rowcount溢出上界被拒绝，未输出PASS；改为
每行乘积上界 + Python整数Σabs(actual amount)聚合边界后fresh PASS。两个失败不冒充当前证据。

## Measures 与独立计算

以下measures作为测试模型数据定义；产品只消费runtime semantic measures，不能在production
添加UCI名/答案或LLM业务计算。Cancelled及Unique可用于既有SCALAR，不注册新Report section。

| Measure | 确定性定义（同current filter context） |
|---|---|
| Total Sales | eligible行Σ(quantity × price)，GBP gross-positive，取消/负quantity/零负price不计 |
| Total Quantity | eligible行Σquantity，与Sales同population |
| Total Orders | eligible行distinct原始Invoice；不是行数、不是全数据含取消invoice数量 |
| Average Order Value | Total Sales/Total Orders；denominator=0时blank。country/time/product切片后的金额/订单均是当前scope，不伪称完整invoice basket平均 |
| Unique Customers | eligible行distinct非空Customer ID；缺失不算一个客户，金额/订单仍保留 |
| Cancelled Orders | 原始取消行distinct Invoice，独立于eligible sale population，不因price无效就删除取消invoice |
| Cancelled Amount | 原始取消行且price>0的Σ(quantity×price)，保留signed negative；不abs。不与原始订单匹配，也不称已退款现金；零负price排除影响需单独披露 |

Total Sales + excluded signed amount = raw signed amount只是数据分解，对账不等于gross与net业务定义
可互换。Oracle整数counts/IDs/members/date/order精确匹配；scale4金额exact对账；AOV保存Decimal
ratio，Cloud double传输核验numeric tolerance预先≤0.0001 GBP，展示到2位仅在显示层，不能改expected。
排序比较完整ordered rows；TopN ties按现有canonical semantics，若N边界并列须记录并保持envelope。

## Model design 与验收前核对

Full raw dataset不裁剪年份/countries/products；source SHA、行数、bytes、sheet header、missing/
duplicate/sign/precision/Invoice冲突先profile。typed column transformations是明确derived数据，
raw fields/provenance不覆盖。关系key唯一性、fact foreign keys、missing unknown及日期range另做
model reconciliation。原始关系raw/normalized authority未知时禁止开始跨表生产事实查询。

合同原始DRAFT ID及Oracle原件保持；已批准测试模型与后续Cloud证据见顶部当前说明。
offline输出及所有public rows只在仓库外PBIAgentTest/M6.5。
known expected从公开原始source独立计算，不从IQ结果或LLM返回值导出。
fresh Schema/Principal/RLS一致后，冻结model definition/export hash与oracle contract ID，
才可对每个Real corpus条目执行business correctness比较。
