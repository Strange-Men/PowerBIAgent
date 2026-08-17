# ADR-011 — Adaptive Report Planning and Visualization Authority

- **状态：** accepted
- **日期：** 2026-08-17
- **决策者：** 用户明确批准（M3.4）
- **适用阶段：** M3.4 Adaptive Report Planning + Visualization/Layout Policy

---

## 背景

M3.0—M3.3 的 ADR-010 把 `sales_report` 模板绑定到单一 PBIX schema fingerprint 并固定四个 sub-query（Total Sales、Total Quantity、Category、Top Product）。实际效果是"固定四查询 + 固定两种横条"：用户说"只看销售额"与"生成完整销售分析报表"结果差异过小；Rich 语义模型的 Date/Region/Customer/Orders 能力无法进入报表；所有分类数据几乎都被 Renderer 强制成 horizontal bar；capability.py 不是真正的 schema-aware capability engine；ReportSpec 已有 ChartSpec，但 production renderer 反而拒绝 charts。

根因不是 HTML/CSS，而是**报表规划能力**：报表内容没有由"用户需求 ∩ runtime schema 能力 ∩ 允许目录"决定。

## 决策内容

### 1. 固定模板的新定义（supersede ADR-010 的固定四查询限制）

ADR-010 的**固定事实安全边界继续有效**：确定性事实链、VerifiedFactSet 唯一事实 authority、无 LLM DAX/数字/HTML/CSS authority、Real 失败不回退 Mock——全部保留。

ADR-010 中"一个 template 永久绑定一个 model fingerprint + 固定四 queries"的限制，由本 ADR **supersede**。

固定模板现在是：**固定设计规则 + 允许能力目录**，不是固定输出内容：

- Design System（固定视觉词汇、主题、排版、间距、安全规则）
- Allowed Section Catalog（registry-owned 能力集）
- Visualization Policy（business role + data shape + cardinality 决定 visual）
- Layout Policy（固定 section 槽位与 1/2 列布局、响应式）
- Theme Policy（固定调色板、字体、KPI 卡片样式）

最终显示哪些 section 由以下交集确定：

```
用户自然语言需求
∩ runtime semantic capability（schema + registered requirements + facts）
∩ sales_report allowed section catalog
```

示例映射（由确定性普通代码实现）：

- "只看销售额" → Total Sales KPI（最小单主题报表）
- "看看销售趋势" → Sales KPI + Trend（Line）
- "按区域看销售情况" → Region comparison（Column）
- "生成完整销售分析报表" → 当前模型所有被允许且有真实事实支持的 section

禁止：空 section、假 placeholder、Mock 补数据、无数据补图。

### 2. Capability Engine 真正 schema-aware

`capability.py` 不再只看 template_key/source_mode/row_count。每个 section 必须同时满足：

- TemplateContract 声明该 section（allowed capability catalog）；
- runtime schema 提供每个必需对象且类型匹配（registered semantic requirements）；
- 密封执行链为该 section 的 query requirements 产生已验证非空事实（validated query/fact evidence）。

M3.4 只支持明确 registry-owned 的 sales capabilities：

```
SALES_KPI / QUANTITY_KPI / ORDERS_KPI / AOV_KPI
TIME_TREND / CATEGORY_CONTRIBUTION / REGION_COMPARISON
TOP_PRODUCTS / TOP_CUSTOMERS
```

不做通用任意 BI semantic inference。schema extra fields 不自动生成任意 business section；缺能力 → section UNAVAILABLE（不 Mock、不补数据、不生成空图）。

### 3. Report Intent 是受控 weak signal

DeepSeek 在 M3.4 新增一个受控 Report Intent / Report Planning Draft，只回答"用户想看哪些分析目标"，且**只能输出 registry-owned ID**（如 `sales_kpi`、`time_trend`、`region_comparison`、`top_customers`）。

禁止 LLM 输出：DAX、HTML、CSS、数字、自由字段名、任意 visual type、任意 query。

LLM draft 只是 weak signal：未知/格式错误 ID 一律丢弃（fail closed）；确定性 NL 匹配器总是地板；用户明确"只看…"时忽略 LLM 增量。最终 authority 由 deterministic planner 产生 Canonical ReportPlan：

```
runtime schema + semantic catalog + capability registry + allowed section catalog
→ resolved sections → query requirements → CanonicalQueryPlan → 现有 M2 执行链
```

用户没要求的 section 默认不查询；完整销售报表才查询完整 capability set。

### 4. ReportPlan 概念

新增 deterministic ReportPlan：

- requested sections（请求的 registry ID）
- resolved sections（请求 ∩ schema capability）
- unavailable sections（请求但不可用——记录、不渲染）
- query requirements（resolved sections 去重后的查询需求，按固定视觉层级排序）
- data plan（CanonicalQueryPlan 集合，复用 M2 密封链）
- provenance（signals、schema fingerprint）

不再让 ReportDataPlan 永远固定四查询。resolved section → deterministic query requirement(s) → CanonicalQueryPlan → 现有 M2 执行链。不引入任意 DAX。

### 5. Visualization / Layout / Theme Policy

新增 deterministic 策略（普通代码选择，不由 DeepSeek 自由选择）：

| Business role | Visual |
|---|---|
| scalar KPI | KPI Card |
| time series | Line Chart（inline SVG） |
| category composition（类别较少，≤8） | Donut（inline SVG）；过多 → horizontal bar |
| region comparison | Vertical Column |
| Top N / ranking | Horizontal Bar |
| detail rows | Table（仅当真正需要明细；M3.4 报表不使用） |

禁止：所有 grouped result → horizontal bar；相同业务事实重复图+表；LLM 选图。

Layout/Theme：固定调色板（dataviz 验证的 8 色 categorical 固定顺序 + blue sequential）、系统字体栈、间距/圆角 token、KPI 卡片样式、section 宽度（full/half 1/2 列）、响应式 1024px / 430px。无 JS、无 CDN、无外部资源；允许确定性 inline SVG/CSS 图形，但必须 HTML escape、无可执行内容。

推荐综合 sales_report 布局（完整能力时）：Header → 4 KPI → 全宽 Sales Trend → 2 列 Category Donut | Region Column → 2 列 Top Products | Top Customers → Footer metadata。实际解析到较少 section 时自动成为简洁单主题报表，绝不显示空 dashboard。

### 6. ReportSpec 最小结构化扩展

复用现有 KPISpec / ChartSpec / TableSpec / ReportSpec；修正 production renderer 拒绝 `report.charts` 的历史限制。ChartSpec 增加最小结构化字段：`visual_type`、`business_role`、`series`（已验证数据的结构化序列）、`layout_hint`。禁止 HTML/CSS/free-form executable config。ReportSpec 只能引用已验证 ReportData / Fact evidence（装配器逐对重建 FactSet 防篡改）。

### 7. 时间趋势

Trend 必须来自 Power BI query → QueryResult → VerifiedFactSet。Renderer 不得自行从 Sales rows 聚合。允许普通代码对已验证的 grouped time points 做确定性显示排序（display order only，不创造新业务数值）。复用现有 DeterministicDAXBuilder（grouped query 直接支持）；不做第二套 DAX builder。

### 8. 表归属消歧（最小通用扩展）

Rich star-schema 中 `Region/Customer/Product/Category` 同时存在于 Sales 与维度表，M2 唯一名解析会失败。对 M2 密封链做最小通用扩展：`CanonicalQueryPlan.dimension_tables`（dimension → 表）与 `dimension_order`（显示排序方向）两个可选字段，默认 None 时行为与 M2 完全一致；仅 deterministic 报表代码可设置，LLM 草稿契约不暴露。DeterministicDAXBuilder、Layer 2 验证、Independent Layer 3 一致性验证同步支持该提示。

## LLM authority

LLM 在 M3.4 的 authority 总账：

- 新增且唯一：Report Intent / planning weak-signal draft（只输出 registry-owned section ID），单独计数 `llm_report_intent_call_count`，与事实类计数分开；
- 保持 0：template canonical authority、报表查询集合、CanonicalQueryPlan slots、DAX、KPI 数字、报表 rows、结果顺序/排名、趋势数值、因果、Report factual truth、HTML/CSS、chart data、report path/reference。

## 备选方案

- 让 LLM 自由规划报表 section：拒绝，无法保证 registry 边界与可审计性。
- 继续固定四查询、仅换 HTML：拒绝，未解决"固定输出"根因。
- 为报表新建专用 DAX/Power BI/Fact pipeline：拒绝，违反 ADR-005/009。
- 为维度表消歧改 LLM 草稿契约：拒绝，draft 不拥有表归属 authority；使用确定性 hint。

## 后果

- 正面：同一用户需求 + 同一 runtime schema 得到确定的 section 集合与查询集；Simple PBIX 保持 M3 基线四查询行为；Rich PBIX 获得完整能力驱动报表；缺能力 fail closed；LLM 无法影响事实、DAX、数字、HTML/CSS。
- 负面：报表内容随 runtime schema 变化，schema 审核责任从 fingerprint 绑定转为 capability 目录审核；`sales_report` contract version 升为 2.0。
- 运维：PBIX、Real 输出与 HTML acceptance 文件保持 gitignored；HTML 只允许保存到 `local_state/reports/`。

---

*最后更新：2026-08-17 | M3.4 Adaptive Report Planning + Visualization/Layout Policy，accepted*
