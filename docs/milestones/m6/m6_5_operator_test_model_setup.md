# M6.5 — 一次性 Online Retail II 测试模型建立

2026-10-16最新授权为同一用户自建测试模型Replace；新版完整步骤与Sales.pq/Measures.dax/列Description
仅在外部 `D:/AAA_Workfile/PBIAgentTest/M6.5/Model/operator-canonical-v2/operator-setup.md`。
以下为首次建立的历史步骤，canonical更新必须使用v2资产，不能按旧StockCode定义重新建模。

本页为operator步骤，不是production authoring Provider。只使用批准的PowerBIAgent-M6-Dev Workspace，
不覆盖既有模型，不创建账号/扩权，不修改M6.5.1。遵守[BUSINESS_METRIC_CONTRACT](m6_5_business_metric_contract.md)，
原始1,067,371行保留，当前offline Oracle不重做。

Microsoft官方：IQ为只读消费，没有item creation；[Desktop publish](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-upload-desktop-files)
将model/report发布到所选Workspace。直接上传local Excel到Service不再是推荐可refresh路径。
本会话工具没有Cloud authoring能力，因此由operator在Desktop建立后发布一次；这不是Local MCP Real验收。

## 操作步骤

1. 新建空白Power BI Desktop文件。Get Data → Excel，选外部已验证完整
   `D:/AAA_Workfile/PBIAgentTest/M6.5/Dataset/uci502-verified/online_retail_II.xlsx`。
   两sheet分别Year 2009-2010/Year 2010-2011，共525,461/541,910行。全部选中Transform Data。
   PBIX/PBIP和所有导入文件只保存PBIAgentTest/M6.5/Model的新目录。
2. 每sheet先提升header，再加SourceSheet和SourceRow（从2起，保留Excel行号），Append成Sales。
   保留全部8个原始字段；不要自动remove duplicates、remove errors、filter rows或drop null。
   Invoice/StockCode/Customer ID转nominal文本，Description/Country文本，Quantity整数，
   InvoiceDate datetime，Price固定小数4位；确认转换错误=0。缺Customer ID保持null。
3. 加派生列：Sales.Date=Date.From(InvoiceDate)，Sales.Year=Date.Year(Date)，
   Sales.YearMonth=Date.StartOfMonth(Date)（date），
   Sales.IsCancelled=文本Invoice以C开头（case-insensitive），
   Sales.IsSaleEligible=非取消且Quantity>0且Price>0，
   Sales.LineAmount=Quantity×Price（固定4位小数）。原始Price/Quantity/InvoiceDate不覆盖。
   不ABS、不round到2位；取消正Quantity1行也必须IsCancelled=true。
4. 模型只加载一张宽表Sales；原sheet source queries仅作连接，关闭它们的Enable Load。
   不创建Date或DimDate/DimCountry/DimProduct/DimCustomer，不建立关系；关闭该文件auto date/time
   以免额外自动日期表。Sales同表保留Invoice、StockCode、Description、Quantity、InvoiceDate、Price、
   Customer ID、Country、Date、Year、YearMonth、IsCancelled、IsSaleEligible、LineAmount，另可保留
   SourceSheet/SourceRow provenance。所有行完整保留，不造Category/Region。
5. Schema要求Sales.Date/YearMonth为date、Year/Quantity为整数、Price/LineAmount固定小数4位，
   IDs为文本。StockCode是商品literal，不用first Description改成Product；缺Customer ID保留null。
   不把IQ关系CONTRACT_GAP补成one/many。本轮单表不依赖关系，gap作为已知能力限制留给后续。
6. 在Sales上创建下列7个semantic measures；Amount/Price保留4位精度，GBP来源描述明确。
   不创建Category/Region等source不存在的业务分类；两个现有Sales模板仅由fresh eligibility决定可用section。
7. 设置各列/measure description：来源UCI502、contract ID、gross-positive口径、缺客户和取消signed规则。
   在Desktop用只读card/table核对本页下方控制总数。全部匹配后保存新文件，命名
   `Online Retail II M6.5`，Publish → **PowerBIAgent-M6-Dev**。若同名冲突停止，不能覆盖旧model。
   不发布到其它Workspace；不变更共享权限/Test A/B角色。
8. 发布后向当前chat提供模型显示名称和“已发布”。内部model/workspace ID只由后端catalog/Resolve读取，
   不粘贴token/Secret/业务DB。之后先IQ runtime Schema确认单表，再进入consumption Real。

## 可复制的单查询导入

可以用准备好的外部文件替代步骤1–4的手工append：
`D:/AAA_Workfile/PBIAgentTest/M6.5/Model/operator-flat-sales-v1/Sales.pq`。
Desktop → Transform Data → New Source → Blank Query，命名Sales，在Advanced Editor粘贴该文件全文。
它读取两张完整sheet，检查原始header及525,461/541,910/1,067,371行数，保留source row/sheet，
转换nominal IDs和4位Price，加同表派生字段；不filter、dedup或remove errors。
Close & Apply后继续步骤5–8，仍须关闭auto date/time并创建7 measures。
该M定义为operator准备文件，尚未经Desktop实际执行；导入错误或控制总数差异必须保留并报告，
不能删除异常行或修改expected。全量加载需等待完成，preview的1,000行不能当完整模型。

## 模型定义（仅operator authoring）

下面是固定数据模型measure定义；外部Model/operator-flat-sales-v1/Measures.dax已保存同一全文，
每个measure须在Desktop分别创建。不能在PowerBIAgent中开放LLM DAX或增加executor。
用户查询的DAX仍由现有DeterministicDAXBuilder生成。

```dax
Total Sales =
CALCULATE(SUM('Sales'[LineAmount]), KEEPFILTERS('Sales'[IsSaleEligible] = TRUE()))

Total Quantity =
CALCULATE(SUM('Sales'[Quantity]), KEEPFILTERS('Sales'[IsSaleEligible] = TRUE()))

Total Orders =
CALCULATE(DISTINCTCOUNT('Sales'[Invoice]), KEEPFILTERS('Sales'[IsSaleEligible] = TRUE()))

Average Order Value = DIVIDE([Total Sales], [Total Orders])

Unique Customers =
CALCULATE(DISTINCTCOUNTNOBLANK('Sales'[Customer ID]), KEEPFILTERS('Sales'[IsSaleEligible] = TRUE()))

Cancelled Orders =
CALCULATE(DISTINCTCOUNT('Sales'[Invoice]), KEEPFILTERS('Sales'[IsCancelled] = TRUE()))

Cancelled Amount =
CALCULATE(SUM('Sales'[LineAmount]), KEEPFILTERS('Sales'[IsCancelled] = TRUE()), KEEPFILTERS('Sales'[Price] > 0))
```

Date/Year/YearMonth为同表派生列，来自每行InvoiceDate；没有独立Date表。
Sales.Date最大值仍不是measure-aware available horizon或refresh time authority。
InvoiceDate时区未声明，不转换为UTC或北京时间。scope中的月份按source日期，不能漏末日时间。

## 发布前控制总数

| 项目 | expected（全部数据，无filter） |
|---|---:|
| Sales raw rows | 1,067,371 |
| Missing Customer ID / Description | 243,007 / 4,382 |
| Duplicate excess保留 | 34,335 |
| Country / StockCode / Month | 43 / 5,305 / 25 |
| IsCancelled行 / 非取消负Quantity行 | 19,494 / 3,457 |
| Price=0 / Price<0 / 超2位小数Price | 6,202 / 5 / 18 |
| IsSaleEligible行 | 1,041,670 |
| Total Sales GBP | 20,972,594.5680 |
| Total Quantity / Total Orders | 11,420,305 / 40,077 |
| Unique Customers | 5,878 |
| Cancelled Orders / Cancelled Amount GBP | 8,292 / -1,526,667.8600 |
| Average Order Value GBP | 523.3074972677595628415300546 |

counts/member/日期精确；金额按4位exact decimal、AOV预定numeric tolerance见Metric Contract。
若有差异保留原始定义及失败记录，不能清洗source或改expected迎合。源workbook SHA-256：
`bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`。

单表路径由用户新授权取代旧星型setup；模型尚未创建，Cloud business Real未计PASS。
IQ关系CONTRACT_GAP保持已知限制，不阻止本轮同表验收；禁止新增relationship normalize或Frozen Core。
