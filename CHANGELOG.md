# CHANGELOG

> 完整历史变更记录见 `docs/archive/m0-m1.6_detailed_changelog.md`

## [M3.4] — 2026-08-17

### 自适应报表规划与可视化策略

- 根因修复：M3.3 仍是"固定四查询、固定两种横条"，无法根据自然语言与语义模型能力生成不同报表；M3.4 修复**报表规划能力**，不只是 HTML/CSS
- 新增 ADR-011：固定模板 = 固定设计规则 + 允许能力目录（Design System / Allowed Section Catalog / Visualization / Layout / Theme / Security），不是固定输出内容；ADR-010 固定事实安全边界继续有效，"一个 template 永久绑定一个 fingerprint + 固定四 queries"限制被 supersede；contract version 升至 2.0
- `capability.py` 重构为真实 schema-aware capability engine：9 个 registry-owned sections（SALES_KPI / QUANTITY_KPI / ORDERS_KPI / AOV_KPI / TIME_TREND / CATEGORY_CONTRIBUTION / REGION_COMPARISON / TOP_PRODUCTS / TOP_CUSTOMERS）；三层门控（TemplateContract 声明 + runtime schema 对象与类型 + 已验证非空事实）；缺能力 fail closed，绝不 Mock/占位/空图
- 新增受控 Report Intent weak signal：LLM 只输出 registry-owned section ID；未知/非法 ID 丢弃；确定性 NL 匹配器是地板；"只看…"忽略 LLM 增量；单独计数 `llm_report_intent_call_count`，与事实类计数分开
- 新增 deterministic ReportPlan / ReportPlanner：requested / resolved / unavailable sections、去重 query requirements、provenance；用户没要求的 section 不查询；零可解析 section fail closed
- 新增 VisualizationPolicy（KPI Card / Line / Donut≤8 / Column / HBar，禁止所有 grouped→horizontal bar）、LayoutPolicy（KPI 行 → 全宽趋势 → 2 列对比/排行对）、ThemePolicy（dataviz 验证 8 色 categorical 固定顺序 + blue sequential、系统字体、间距 token）
- `SalesReportRenderer`（原 FixedSalesReportRenderer 更名）支持 charts：KPI cards、inline SVG line/donut、CSS column/hbar；无 JS/CDN/外部资源；空 section 不输出；同一业务事实不重复展示
- 时间趋势真实链：Power BI query → QueryResult → VerifiedFactSet；Renderer 不聚合；已验证时间点仅确定性显示排序（不创造新业务数值）；复用现有 DeterministicDAXBuilder，无第二 DAX builder
- 最小通用扩展：`CanonicalQueryPlan.dimension_tables` / `dimension_order`（star-schema 重名列消歧，None 时 M2 行为不变），DeterministicDAXBuilder / Layer 2 / RestrictedDAXVerifier 同步支持；ChartSpec 增加结构化 `visual_type` / `business_role` / `series` / `layout_hint`
- 测试矩阵：Simple/Rich/synthetic 三模型；5 个 NL cases（只看销售额 / 看看销售趋势 / 按区域看销售表现 / 看看头部客户 / 生成完整销售分析报表）；LLM weak-signal 边界；fact-gate 空结果 drop；全部 anti-fake 回归保留
- Real acceptance（双模型）：Simple PBIX 完整请求解析 4 sections / 4 查询（M3 基线行为不变）；Rich PBIX（fingerprint `31505f7987133c235554bc00e7ca5ce3fd42351b08e984c0c011f48410e56157`）解析 9 sections / 9 真实查询（15 个月度趋势点、3 品类、4 区域、Top 5 产品/客户），4 种 visual；source real；DAX/ReportData/Report factual/Renderer LLM calls 与 fallback/fake QueryResult 全 0
- Fresh acceptance：backend 1477 passed、Golden 11 PASS / 1 manual skip、Architecture / Repository Safety / Error Ledger / Documentation Governance / diff check 全部 PASS；桌面与 430px 截图已产出，程序化 DOM/几何检查 PASS，最终视觉 PASS 待用户人工确认

---

## [M3.3] — 2026-08-17

### 销售报表模板V2与能力驱动布局

- 新增 `backend/app/report/capability.py`：SectionCapability 概念基于 runtime schema + TemplateContract + VerifiedFactSet 确定性判断 section 是否可渲染；SALES_KPI、CATEGORY_BREAKDOWN、TOP_PRODUCTS 三个正式 section；TIME_TREND / REGION_BREAKDOWN / CUSTOMER_BREAKDOWN 为纯 extension point，无 contract/facts 时自动 UNAVAILABLE，绝不生成占位或伪造内容
- `FixedSalesReportRenderer` 改为 section-capability 感知渲染：每 section 只保留一种主要视觉表达（horizontal bar），移除与 bars 重复的同源明细 table；KPI、Category bars、Top Product bars 各回答独立业务问题；缺失 section 自动 fail closed 不输出
- `sales_report.html` 模板重写：简化为双列 KPI → 品类 bars → 产品 bars → metadata footer；响应式窄屏 Flex 换行；无 JS/CDN/外部资源；无 `<table>` / 重复数据区域
- 新增多语义模型防伪测试：Model A 当前简单 schema 所有 section 正常；Model B 多 Date/Region/Customer 字段不自动生成新 section；Model C 缺 Category/Product 时 contract validation fail closed；anti-fake 验证 production 代码无 oracle、无 LLM/PowerBI authority
- 新增回归测试：no duplicate table visual regression、section capability evidence gates、extension point 不自动激活
- Fresh acceptance：backend 1445 passed、harness 11/12 PASS (1 skip)、Architecture/Repository Safety/Error Ledger/Documentation Governance/diff check 全部 PASS

## [M3.2] — 2026-08-17

### 销售报表最终可视化加固与 M3 收口

- M3.1 commit `fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57` 经 GPT 远程审计后从 M3.0 纯 fast-forward 合入 `main`；`PowerBIAgent Validation` run `31989328261` 对应同一 main push SHA，结论 success，随后安全删除本地与远程开发分支
- `FixedSalesReportRenderer` 直接从已校验的 Category / Top Product rows 生成确定性 CSS 横条；宽度按同组绝对最大值归一化并固定半入舍入到两位小数，横条旁保留真实值与同源明细表，不增加查询、排名、趋势、因果或业务事实
- 固定模板完成桌面与窄屏层级、KPI、横条、表格和弱化 metadata 加固；窄屏横条使用稳定 Flex 换行，无 JavaScript、CDN、外部库、网络请求或自由 HTML
- Renderer / Repository 保存前额外拒绝 `link`、`iframe`、`object`、`embed`、`@import`、CSS `url()` 与 `src=`；Intent / QueryPlan prompt 明确 DeepSeek 仅提供弱语言信号，无模板、查询、KPI、图表事实、HTML/CSS、布局、保存路径或资源引用 authority
- M3 PBIX Real acceptance 通过：fingerprint `d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac`，四查询非空，Total Sales `500821`、Total Quantity `358`，source real，fallback/fake QueryResult 与 DAX/ReportData/Report factual/Renderer LLM calls 全为 0，view/download 200，受管 HTML 与验收副本逐字节一致
- 最终受管 HTML 为 10,230 bytes，SHA-256 `7144438843fae9a626e6122f4b936a2ff3fe2d973dc85c6e20c644f2ede6578d`；以禁止网络/脚本的静态 Renderer 实际渲染后，桌面与 430px 窄屏视觉验收均 PASS
- Fresh acceptance：prompt/report targeted 112、report/contract/API targeted 96、backend 1435、Golden 11 PASS/1 manual Real skip、Architecture 89、Repository Safety 198、Error Ledger 25、Documentation Governance 与 diff check 全部通过
- M3 最终收口；不提交 PBIX/HTML/`local_state/`，不进入 M4/M5 或 Remote MCP，不创建 Tag

## [M3.1] — 2026-08-17

### 销售报表生成与 HTML 资源闭环

- M3.0 commit `e4b5c6c6a759cdf22c74c4d87902482563e27cad` 经 GPT 远程审计 PASS 后纯 fast-forward 合入 `main`；`PowerBIAgent Validation` run `31986207118` 对应 main push 与同一 SHA，结论 success
- `sales_report` 固定四查询继续逐项复用 CanonicalQueryPlan → Deterministic DAX → Independent Layer 3 → ToolGateway → PowerBIAdapter → QueryResult → VerifiedFactSet；无第二 Power BI、DAX、Fact、TurnPipeline 或 Memory 控制面
- 新增 deterministic `SalesReportData` 与唯一固定 `ReportSpec`；KPI、Category rows、Top Product 结果位置与全部 provenance 只来自四组 QueryResult / VerifiedFactSet，任一缺失、错绑、伪造、空结果、mixed source 或 fingerprint mismatch 均 fail closed
- 新增 `FixedSalesReportRenderer` 与固定 UTF-8 `sales_report.html`；静态 HTML 无 JavaScript、外部脚本/CDN 或自由用户 HTML，所有动态文本安全转义
- 新增 `ReportArtifact`、原子 `LocalReportRepository`、`GET /api/reports/{report_id}` 与 `/download`；report_id 只由后端生成，路径遍历与 unknown ID 拒绝，幂等 replay 复用同一 artifact
- Real acceptance 使用 M3 PBIX 完成 4 queries → 4 QueryResult → 4 VerifiedFactSet → SalesReportData → ReportSpec → Renderer → ReportArtifact；Total Sales / Total Quantity oracle 匹配、source real、view/download 200、保存内容 hash 一致，DAX/ReportData/Report factual/Renderer LLM authority 与 fallback/fake QueryResult 均为 0
- 本轮不进入 M4/M5 或 Remote MCP，不新增 M3.2 功能，不提交 PBIX/HTML/local_state，不合并 main，不创建 Tag

## [M3.0] — 2026-08-17

### 销售报表合同与开发路线固化

- M0—M2 已由 Tag `m2.6.4-m0-m2-final-seal` 在 `70748da` 正式封板；M3 从该 clean main 基线开始
- M3 MVP 唯一 production template 固化为 `sales_report`；历史 `sales_weekly` / `satisfaction` / `operating_overview` 保留识别但 production availability=false
- 新增 TemplateContract、M3 PBIX model/schema fingerprint binding、fail-closed compatibility validator 与四查询 ReportDataPlan；ReportDataPlan 不消费 LLM draft、QueryResult 或 Known-answer expected
- 四个固定 sub-query 继续复用 CanonicalQueryPlan → Deterministic DAX → Independent Layer 3 → ToolGateway → Local MCP → QueryResult → VerifiedFactSet，没有第二 Power BI/DAX/Fact pipeline
- 新增 ADR-010 与 `sales_report_contract_smoke.py`；M3 专用 PBIX 已验证 runtime schema、四个真实查询、scalar local oracle、`source_mode=real`、fallback/LLM/Renderer 调用均为 0
- Fresh acceptance：targeted 19、backend 1412、Golden 11 PASS/1 manual Real skip、Architecture 86、Repository Safety 193、Error Ledger 25、Documentation Governance 与 diff check 全部通过
- 本轮未实现正式 Renderer、HTML 文件、report resource repository、查看/下载 API，未进入 M3.1/M3.2/M4/M5，未创建 Tag

---

## [M2.6.4] — 2026-08-14

### M0—M2 最终加固与文档治理

- TopN facts 改为显式 `result_position` / QueryResult order，ties 与 truncated 结果不再生成严格 business rank；保持 boundary ties 可超过 N
- Bounded semantic selector 增加 Catalog metadata evidence shortlist 与 post-validation；未知、证据并列、非法 ID 或选择冲突均 fail closed
- data/report-shaped `UNSUPPORTED` 进入 authoritative Grounding/capability check；明确 out-of-scope 请求保持 early-stop，失败不污染 Pending/Committed Memory
- 补齐 approved 数量问法 alias；Real acceptance 观察器直接核对 ToolGateway DAX、fact-bounded output、TopN/tie safety 与 DAX/Answer LLM 零调用
- 恢复 AGENTS/README/00/03/04/05/07/08/09/CHANGELOG 真实性，建立 `docs/index.md`、specs/milestones/archive 分层与 deterministic Documentation Governance Gate
- 完成 M0—M2 fresh offline/Real hardened acceptance 与远程核心审计；长期文档已对齐 Semantic Grounding、Deterministic DAX、VerifiedFactSet 和 Pending/Committed 边界；未创建 Final Tag

---

## [M2.6.3] — 2026-08-14

### Deterministic Execution & Verified Facts

- Real Canonical QueryPlan 只经 Deterministic DAX Builder；Independent Layer 3 独立验证 exact group-by、EQ/time、TopN/ORDER BY 与无额外业务语义，Real DAX LLM calls=0
- 建立 VerifiedFactSet factual authority，Answer/Report 只消费可追溯的数字、结果顺序、极值、筛选、时间、rows 与 provenance
- PendingClarificationContext 与 committed Memory 分离，partial clarification 完整后才执行并在全链成功后提交
- 正式多轮 contract 更正为 6 Conversation / 16 Turn，禁止从欠指定 ranking 默认 Product；`dax_unplanned_group_by_dimension` 与 `dax_filter_structure_not_verifiable` 收口为 0

---

## [M2.6.2] — 2026-08-13

### Business Semantic Grounding

- 建立 model-scoped Business Semantic Catalog，并以 friendly model key + runtime schema fingerprint 绑定
- Grounding 成为 Measure/Dimension/Filter Field/runtime Member/Time 的 canonical authority；Intent/QueryPlan LLM 只保留 weak signal
- 结构化 semantic slot 状态与 deterministic StateTransition 支持 KEEP/REPLACE/CLEAR 及 Filter ADD/REPLACE/REMOVE
- Canonical QueryPlan 只能消费 runtime schema、approved glossary、bounded member values 与固定时间边界；歧义或未解析必须 clarification

---

## [M2.6.1] — 2026-08-12

### Known-answer 独立数值 Oracle 与多轮 Harness 固化

- 在 Harness/Test 边界新增独立 Known-answer Oracle，Expected 只从显式 baseline 读取，不依赖 LLM、当前 DAX、Answer 或 Actual QueryResult 反向生成
- 支持 scalar、按业务 Key canonicalize 的 grouped rows，以及校验顺序并允许第 N 名 ties 超过 N 行的 ordered/TopN；数值默认绝对/相对容差均为 `1e-9`，并限制可配置上限
- 固化 8 个 Known-answer Case（含 2 个 holdout）和 6 组、15 Turn 的 Power BI 多轮 MiniSuite；Conversation 只有所有 Turn 全部 PASS 才成功
- 唯一 M2.6.1 Runner 通过正式 Chat API 在 Fake/Mock 模式验证 Filter refinement、Dimension switch、Filter replacement、Metric switch、Clarification 与失败 Turn Memory 完整性
- 真实 expected baseline 仅允许位于 Git 忽略的 `local_state/`；缺失或覆盖不完整时明确失败，不回退 committed fictional example baseline
- 修复 Harness module docstring 的 invalid escape warning，并更新 `ChatResponse.powerbi_mode` 描述为 `mock / local_mcp / remote_mcp（Deferred）`
- 本轮真实 DeepSeek、Local MCP 与 Power BI Desktop 调用均为 0；未修改 TurnPipeline、ValidationService、Architecture Gate 或 `local_mcp.py`，M2.6.2 真实验收仍未执行

---

## [M2.6] — 2026-08-12

### 数据问答正确性契约与架构治理加固

- Filter Layer 3 对可确定验证的 `eq` 检查 field/operator/value，并拒绝额外业务 Filter；Real 路径其余 Operator 明确为 `NOT_VERIFIED`，Mock 兼容路径不变
- TopN 验证 N、单一 Measure 与方向；显式 sort 另要求查询末尾 `ORDER BY`，不再以 `row_count <= top_n` 否定合法 ties
- Architecture Gate 升级为 AST + ownership：MCP SDK/raw call、ToolGateway、平行生产控制面、Provider 反向依赖与禁用框架均进入 CI 门禁
- Health 保留 `ready` 兼容字段，新增 `configuration_ready` 与 `powerbi_live_connected=false`，不把配置就绪描述为 Desktop 实时在线
- 冻结 `local_mcp.py` 的 Provider / protocol Adapter 职责；本轮未修改其业务逻辑，未调用 DeepSeek、Local MCP 或 Desktop
- 仅固化 M2.6.1 Known-answer Oracle 与 Real Multi-turn Harness 成功契约；未实现后续验收

---

## [M2.5] — 2026-08-12

### 真实业务 Golden 回归验收与 M2 封板

- 新增唯一 M2 Business Golden 人工 Smoke，通过正式 Chat API 完成 7 个真实 Case，覆盖 Measure、Dimension、Filter、Top N/Sort 与 3 个未在 Prompt 点名的对象/组合
- 将 `gc_012_real_baseline` 固化为 Local Desktop 人工真实基线，通用 CI 继续只使用 Mock/Fake，不接 Desktop、PBIX、DeepSeek 或 Microsoft 凭据
- 20 类关键 Bad Case、Answer provenance、Replay、Real 不回退 Mock、M0—M1 Golden 与 Mock 全量回归通过
- ValidationService 生产代码变化为 0，未新增完整 DAX Parser、业务词典、Pipeline、Service 或 Provider；现有 Prompt 无需为 Golden 增加固定答案
- Remote MCP 生产化继续 Deferred；M2 能力限定为 Local MCP + Power BI Desktop Demo，下一阶段为 M3 固定模板报表正式渲染

---

## [M2.4] — 2026-08-11

### 现有 TurnPipeline 接入真实 Power BI

- 将 `LocalMCPPowerBIAdapter` 作为 Provider 注入既有 DeepSeekTurnService / TurnPipeline / ToolGateway，没有复制 Service、Pipeline 或工具网关
- 落地真实 Schema 驱动的 QueryPlan Semantic Validation，以及 Measure/Dimension/Filter、group-by 和 `SUMMARIZECOLUMNS` 参数顺序的确定性 Layer 3 校验
- 将 `source_mode=real` 传播到 Turn、Answer/Report、Snapshot、Replay 与 Trace；幂等 Replay 不重复执行 DeepSeek 或 Power BI
- 真实跑通总销售额、总数量和带类别过滤的销售额三个自然语言 Case；Answer provenance 严格引用 QueryResult.columns
- 保持 Real 失败不回退 Mock、Remote Deferred、Issue #124 Open；修复 stdio 异常组掩盖既有 DAX 错误分类的问题

---

## [M2.3] — 2026-08-11

### 真实 DAX 执行与 QueryResult 标准化

- 在既有 ToolGateway → PowerBIAdapter → Local MCP 边界内，以单次只读 stdio/Desktop 会话调用 `dax_query_operations` 的 `Execute`
- 依据 beta.12 实机 schema 使用 `resultMode=Inline`，标准化有序 columns、二维 rows、实际 row_count、execution time、request_id、`source_mode=real` 与 truncated
- 新增 DAX、timeout、permission、connection、malformed、MCP protocol、oversized 与 Preview row-data missing 错误分类；仅 NETWORK 最多重试一次，Real 不回退 Mock
- 新增 Fake MCP 回归与脱敏人工 DAX Smoke；固定 ROW 值 1 及 `Total Sales` / `Total Quantity` 实际数值均验证成功
- 当前实机未复现仍为 Open 的 Issue #124；未调用 DeepSeek、未接完整 Chat、未修改 TurnPipeline / DeepSeekTurnService / main / routes

---

## [M2.2] — 2026-08-11

### 真实 Semantic Model Schema 接入

- 保留公开可复现的 Local MCP 实机固定版本 `0.5.0-beta.12`，并用 npm 官方 Registry 与隔离缓存复核
- 在既有 ToolGateway → PowerBIAdapter → Local MCP 边界内，以单次只读会话调用五类 Schema 工具的 `List` / `Get`
- 将真实 Table、Column、Measure、Relationship 与 Hierarchy 映射为向后兼容的 `SemanticModelSchema`，保留 Measure expression、数据类型与基础关系语义
- 新增 Fake MCP 回归与脱敏人工 Schema Smoke；真实验收为 3 tables、19 columns、2 measures、1 relationship、2 hierarchies
- `Total Sales` 与 `Total Quantity` 已准确识别为 Measure；未执行 DAX、未调用 DeepSeek、未接完整 Chat、未修改 TurnPipeline

---

## [M2.1] — 2026-08-11

### Local Power BI MCP 最小真实连接验证

- 经用户批准将当前 Demo 验证路径从受管理员前置条件阻塞的 Remote MCP 调整为 Local MCP + Power BI Desktop；Remote 不是失败，ADR-006 生产化路线完整保留
- 新增 accepted ADR-007 与统一 M2 Local Demo / Remote Production 计划
- 引入官方 `mcp==2.0.0`，新增只读 stdio Local Adapter、脱敏连接诊断与人工 Smoke
- 真实验证 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12` 启动、协议 `2025-11-25`、21 个工具发现以及 Power BI Desktop 连接
- 保留并泛化 Semantic Grounding 与 DAX 业务语义四层验收契约
- M2.1 不读取完整 Schema、不执行 DAX、不调用 DeepSeek、不接 Chat

---

## [M2.0] — 2026-08-11

### 真实 Power BI Remote MCP 接入规划与开发路线固化

- 修复 AGENTS / CLAUDE 冷启动遗漏 Error Ledger 的治理矛盾
- 将 ADR-005 从 ADR 索引拆分为正式独立文件
- 基于 Microsoft 与 MCP 官方资料复核 Remote MCP、OAuth、权限与 Python SDK
- 新增 accepted ADR-006，固化 Adapter、ToolGateway、OAuth、工具白名单与失败边界
- 固化 M2.1—M2.5 开发路线、防偏移门禁和离线 CI / 人工 Smoke 边界
- 生产业务逻辑变化为 0；真实 LLM 调用为 0；真实 Power BI 调用为 0

---

## [M1.8] — 2026-08-11

### Codex 接管准备与仓库上下文固化

- 新增 `AGENTS.md` 仓库级 Agent 入口、冷启动协议与架构铁律
- 将 `CLAUDE.md` 扩展为 Claude / Codex / 其他代码 Agent 通用开发协议
- 同步 Settings、README、路线图与交接状态至 M1.8
- 核实封板 Tag `m1.7.2-m0-m1正式封板` 指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`
- 生产业务逻辑变化为 0；M2 尚未开始

---

## [M1.7.2] — 2026-08-05

### M0—M1 最终文档收口与封板

**目标：** M0—M1 最后一个版本，只修正文档状态并建立封板流程，不新增功能、不修改业务逻辑、不进入 M2。

**主要变更：**
- 文档状态最终同步：docs/08、docs/09、README 全部更新至 M1.7.2
- 历史 Commit 和 CI 事实回填：M1.7 回填 `e5d1740`，M1.7.1 回填 `1dd20de` 及 CI Run #30991136311
- 新增"文档先于 Commit"规则：固化为 CLAUDE.md 硬规则，Commit 后禁止再回填文档
- 版本同步至 M1.7.2（Settings.version、README、docs/08、docs/09）
- 不修改生产业务逻辑（变化为 0）
- 不执行真实 LLM（调用次数为 0）

**固定封板 Tag：** `m1.7.2-m0-m1正式封板` — 该 Tag 必须指向本封板基线提交，远程 CI 通过后创建。

**Commit：** 该 Tag 必须指向本封板基线提交

---

## [M1.7.1] — 2026-08-05

### 最终状态收口与封板候选修复

**目标：** M1.7 终审发现 4 个小问题的收口修复，不新增功能、不进入 M2。

**修复内容：**
- 修正 docs/08 M1.6.6 详细章节状态冲突（进行中 → 已完成）
- 修正 docs/09 PydanticAI 错误描述（已从生产依赖移除，ADR-001 已被 ADR-005 替代）
- 删除恒真测试 `test_no_stale_tag_for_current_version`（仅 `assert True`）
- 加固 CI 工作区干净检查（git diff --check + git diff --exit-code + git status --porcelain）

**最终测试结果：**
- pytest：1119 passed（M1.7 的 1120 减去 1 个删除的恒真测试）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- 错题本校验：PASS
- 架构门禁：PASS
- 真实 LLM 调用次数：0
- 生产业务逻辑变化：0
- 未创建 Tag

**Commit：** `1dd20de`

---

## [M1.7] — 2026-08-05

### MVP轻量化与通用CI固化

**目标：** M0—M1 正式封板前最后一次整理 — 测试收敛、CI通用化、文档轻量化、Smoke移出生产包。

**主要变更：**
- 测试收敛：删除4个旧集成测试文件（已被更强领域测试覆盖），版本化测试文件重命名为领域名称
- CI通用化：`.github/workflows/ci.yml`（PowerBIAgent Validation），动态版本一致性由pytest保护
- Smoke轻量化：删除4个阶段性Smoke，只保留一个人工验收入口（`scripts/manual_smoke/deepseek_chat_smoke.py`）
- 文档轻量化：归档M1.6审计文档、压缩docs/09和活跃CHANGELOG
- 版本同步至M1.7

**最终测试结果：**
- pytest：1120 passed
- Golden Cases：11 passed，1 skipped
- 真实 LLM 调用次数：0
- 生产依赖变化：0
- 生产业务逻辑变化：0
- 未创建 Tag

**Commit：** `e5d1740`

---

## [M1.6] — 2026-08-04 ~ 2026-08-05

### 架构收口与加固（M1.6.1—M1.6.6）

**目标：** 审计复验、架构定案、Harness收口、统一TurnPipeline、旧Agent清理、AI真实性加固、错题本治理、CI建立。

**关键架构决定：**
- ADR-005：确定性TurnPipeline与受控LLM调用架构（废弃PydanticAI）
- Memory单写入者：TurnPipeline为唯一事务入口
- ToolGateway为Power BI/Renderer唯一调用入口
- AST架构门禁替代grep检查

**最终验收（M1.6.6）：**
- pytest：1253 passed | Golden Cases：11 passed，1 skipped
- 安全扫描：PASS | 远程CI（Run #30983637121）：全部通过
- Commits：`0f6424f` → `208bca4` → `d6665bd` → `d99d243` → `d57e38c` → `4217b66` → `e850f14`/`cb2826e`/`762f4cf` → `084aa76`

---

## [M1.5] — 2026-08-03

### 全链路验收与M1封板

**Tag：** `m1-deepseek-pipeline-release` | **Commit：** `a926b5e`

**主要能力：**
- DeepSeek Chat全链路：Intent → QueryPlan → DAX → Mock QueryResult → Answer/ReportSpec → Memory
- TurnServiceProtocol通用协议 + Mock/DeepSeek双Service
- API模式切换：Mock/DeepSeek Health 200/503
- ChatResponse扩展 + Token/repair统计

**测试结果：** pytest 937 passed | Golden Cases 11/1 | 安全扫描 PASS

---

## [M1.4] — 2026-08-03

### 真实Answer与ReportSpec生成（含M1.4.1修复）

**主要能力：** DeepSeekAnswerService/ReportSpecService、Evidence强制绑定、KPI/Table/Chart严格验证、模板冲突拒绝

**测试结果：** pytest 936 passed | Golden Cases 11/1

---

## [M1.3] — 2026-08-03

### 真实QueryPlan与DAX生成（含M1.3.1修复、M1.3.2前端文档）

**主要能力：** DeepSeekQueryPlanService/DAXService、DAX只读安全验证器、QP真实验证、结构化回答契约

**测试结果：** pytest 706 passed | Golden Cases 11/1

---

## [M1.2] — 2026-08-03

### 真实意图识别

**Commit：** `53cf43e`

**主要能力：** DeepSeekIntentService、IntentContextSnapshot、意图严格化、集中式Prompt

**测试结果：** pytest 604 passed | Golden Cases 11/1

---

## [M1.1] — 2026-08-03

### DeepSeek Provider基础接入

**Commit：** `073a819`

**主要能力：** DeepSeekLLMProvider、10种异常类型、Provider Factory、真实连通测试

**测试结果：** pytest 506 passed | Golden Cases 11/1

---

## [M1.0 — M1.0.2] — 2026-07-31

### M0遗留收口、幂等并发、密钥安全

**Commits：** `9247322`、`c223d7b`、`5726959`

**主要能力：** 请求指纹与冲突检测、并发Owner/Waiter防重、Report快照结构化、密钥安全规则固化

**测试结果：** pytest 415 passed | Golden Cases 11/1

---

## [M0.4 — M0.4.1] — 2026-07-31

### 项目骨架与阶段收尾

**Tags：** `m0.4.1-foundation-release`、`m0.4-foundation-release`

**主要能力：** FastAPI最小骨架、API骨架真实性修复、请求级并发上下文收口

**测试结果：** pytest 285 passed | Golden Cases 11/1

---

## [M0.1 — M0.3] — 2026-07-31

### 仓库初始化、架构设计与验证闭环

**主要能力：** 项目文档基线、四层记忆系统、Power BI MCP设计（ADR-003）、ETCLOVG Harness（ADR-004）、ToolGateway、Golden Cases

---

*最后更新：2026-08-11 | M2.0 Remote MCP 接入规划与开发路线固化*
