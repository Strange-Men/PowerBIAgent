# 08 — 开发路线

> **状态：** M3.3 — Report Template V2 / Non-redundant Business Information Architecture
> **用途：** 只记录当前路线、阶段边界和已封板摘要；逐版本历史见 `CHANGELOG.md`、Git 与 archive。

## 路线总览

| Milestone | 目标 | 状态 |
|---|---|---|
| M0—M1 | Foundation、DeepSeek、统一 TurnPipeline、Harness 与安全治理 | ✅ 已封板 |
| M2 | Local MCP + Power BI Desktop 真实数据问答与 Truth Boundary | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | Report Architecture + Template/DataPlan Contract | ✅ 完成、远程审计 PASS、已合入 main |
| M3.1 | Sales Report Full Generation + Static HTML + Report Resource | ✅ 远程审计 PASS、已合入 main，CI success |
| M3.2 | Hardened visual acceptance / M3 final closure | ✅ 完成；不含新业务能力，无 Tag |
| M3.3 | Report Template V2 / Non-redundant Business Information Architecture | ✅ 已完成 |
| M4 | 持久化会话、搜索与最近对话 | ⬜ 未开始 |
| M5 | React + Vite 极简对话前端与联调 | ⬜ 未开始 |

M0—M2 Final Seal 为 `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。M3.0 commit `e4b5c6c6a759cdf22c74c4d87902482563e27cad` 已纯 fast-forward 合入 main，main CI run `31986207118` success。M3.1 commit `fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57` 经远程审计后纯 fast-forward 合入 main，main CI run `31989328261` success，开发分支已删除。M3.2 直接在 main 完成 hardened acceptance；不创建 Tag。

## 永久 M2 事实链

```text
Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet
```

Real DAX/factual authority 不回到 LLM，Real failure 不回退 Mock。

## M3.0 — 已完成合同基线

- 唯一 production template 为 `sales_report`；legacy keys 仅历史 Mock compatibility，production unavailable。
- TemplateContract 绑定 `local_desktop_model` 与 M3 PBIX fingerprint。
- ReportDataPlan 固定四查询：Total Sales、Total Quantity、Category × Total Sales、Product × Total Sales desc TopN 5。
- 缺对象、类型、model 或 fingerprint mismatch 时不生成 partial plan。
- M3.0 commit/push/GPT remote audit/main ff-only merge/main CI 均完成。

## M3.1 — 已完成正式生成链

### 唯一正式链

```text
Natural Language / Template Grounding
→ TemplateContract + runtime schema validation
→ deterministic ReportDataPlan
→ 4 × CanonicalQueryPlan
→ 4 × Deterministic DAX + Independent Layer 3
→ 4 × ToolGateway → PowerBIAdapter → Power BI
→ 4 × QueryResult → 4 × VerifiedFactSet
→ deterministic SalesReportData
→ deterministic ReportSpec
→ FixedSalesReportRenderer
→ static UTF-8 HTML
→ ReportArtifact / ReportRepository
→ report_id / view / download
→ Memory / Snapshot
```

### Fixed sales content

- 标题：销售分析报表。
- KPI：总销售额、总销量。
- Section：按类别销售额；Top 5 产品销售额。
- Metadata：数据来源、source_mode、contract version、generated_at。
- TopN 仅显示 `result_position`；不制造严格业务名次、趋势或原因分析。

### Resource contract

- `ReportArtifact` 固定 report_id、template/contract/model/fingerprint、四组 QueryResult/FactSet IDs、source_mode、content type/hash 与 created_at。
- 正式 HTML 原子保存于 `local_state/reports/<report_id>.html`；验收副本只能复制同一 Renderer 输出到 `m3_sales_report.html`。
- `GET /api/reports/{report_id}` 查看；`GET /api/reports/{report_id}/download` 下载。
- 后端生成 reference；repository 拒绝任意路径、unknown ID 与内容 hash 不一致。
- 同 request_id 重放只读 Snapshot，复用同一 report_id，不重新执行 Power BI 或生成第二 artifact。

### Truth Boundary

LLM 对 template canonical authority、查询集合、CanonicalQueryPlan factual slots、DAX、KPI/rows、结果顺序、趋势、因果、Report factual truth、HTML/CSS 和 report reference 的 authority 均为 0。LLM 只保留现有受控 Intent/语言理解职责。

## M3.2 — 已完成 hardened visual acceptance

M3.2 未新增模板、查询、DAX、业务语义、图表类型、资源 API、前端或持久化能力；只把 M3.1 已有 Category / Top Product `ChartSpec` 与同源 table rows 以固定 CSS 横条呈现，并完成静态安全、Real PBIX、桌面/430px 视觉、文档与 CI 收口。

- 横条几何只由已验证行值按组内绝对最大值确定性归一化，实际显示值与同源表格不变。
- 响应式布局固定为窄屏 Flex 换行；无 JavaScript、CDN、外部库或网络请求。
- Renderer / Repository 拒绝更多外部资源载体；DeepSeek prompt 明确无报表事实、HTML/CSS、布局、保存或 reference authority。
- M3 final closure 不创建 Tag；后续不得继续扩展 M3 或进入 M4/M5，除非用户另行明确授权。

## M3.3 — Report Template V2 / Non-redundant Information Architecture

M3.3 未新增业务查询、DAX、filter、template、LLM authority 或事实来源；重构 sales_report 信息架构，引入 capability-aware section 设计。

- 新增 `backend/app/report/capability.py`：SectionCapability 概念，根据 runtime schema + TemplateContract + VerifiedFactSet 确定性判断 section availability；SALES_KPI、CATEGORY_BREAKDOWN、TOP_PRODUCTS 三个可渲染 section；TIME_TREND / REGION_BREAKDOWN / CUSTOMER_BREAKDOWN 为纯 extension point，无 contract/facts 时自动 UNAVAILABLE，绝不生成占位或伪造内容
- `FixedSalesReportRenderer` 改为 section-capability 感知渲染：每 section 只保留一种主要视觉表达（horizontal bar），移除与 bars 重复的同源明细 table；KPI、Category bars、Top Product bars 各回答独立业务问题
- `sales_report.html` 模板重写：简化为双列 KPI → 品类 bars → 产品 bars → metadata footer；响应式窄屏 Flex 换行；无 JS/CDN/外部资源；无 `<table>` 或重复数据区域
- 多语义模型防伪测试：Model A 当前 schema 所有 section 正常；Model B 多 Date/Region/Customer 字段不自动生成 section；Model C 缺 Category/Product 时 contract validation fail closed；production 代码验证无 oracle、无 LLM/PowerBI authority

## 永久阶段边界

- 不使用 LangGraph、多 Agent 或 PydanticAI。
- 不复制 Pipeline/Service，不绕过 TurnPipeline、ToolGateway、PowerBIAdapter、Independent Layer 3、VerifiedFactSet 或 Memory/Snapshot。
- 当前报表针对 M3 PBIX 全量数据；不新增动态月份、Category filter、comparison、趋势、用户自由 ReportDataPlan 或任意 DAX。
- M3 不做 PDF、自由 HTML、用户模板、JavaScript、复杂图表框架、React UI 或 Remote MCP。
- M3 已最终收口；未经用户另行明确批准不得继续扩展 M3 或进入 M4/M5；普通轮次不创建 Tag；禁止 force push。

---

*最后更新：2026-08-17 | M3.2 hardened visual acceptance；M3 final closure*
