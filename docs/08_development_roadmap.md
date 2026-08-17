# 08 — 开发路线

> **状态：** M3.0 — Report Architecture + Sales Contract Baseline 已完成；M3.1 未获授权
> **用途：** 只记录当前路线、阶段边界和已封板摘要；逐版本历史见 `CHANGELOG.md`、Git 与 archive。

## 路线总览

| Milestone | 目标 | 状态 |
|---|---|---|
| M0—M1 | Foundation、DeepSeek、统一 TurnPipeline、Harness 与安全治理 | ✅ 已封板 |
| M2 | Local MCP + Power BI Desktop 真实数据问答与 Truth Boundary | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3 | 单一固定销售模板到静态 HTML 的确定性闭环 | 🟨 M3.0 完成；M3.1 未开始 |
| M4 | 持久化会话、搜索与最近对话 | ⬜ 未开始 |
| M5 | React + Vite 极简对话前端与联调 | ⬜ 未开始 |

M0—M2 Final Seal 为 `m2.6.4-m0-m2-final-seal`，指向 `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。M3 从该 clean `main` 开始；本轮不更新 `main`、不创建 Tag。

## 已封板阶段摘要

M0—M1 完成 Pydantic 契约、Memory/Snapshot、FastAPI、Mock/DeepSeek、确定性 TurnPipeline、ToolGateway、Harness、安全与 CI。M2 完成 Local MCP + Power BI Desktop、Business Semantic Catalog、Grounding/StateTransition、Pending Clarification、Canonical QueryPlan、Deterministic DAX、Independent Layer 3、VerifiedFactSet 与 fact-bounded Answer/Report 边界。

M2 的永久事实链为：

```text
Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet
```

Real DAX/Answer factual authority 不回到 LLM；Real failure 不回退 Mock。

## 当前阶段：M3.0

### 目标

在任何 Renderer/HTML 开发前，先固化 M3 报表架构、唯一销售模板的数据需求、M3 专用 PBIX binding 与 fail-closed compatibility gate。

### 唯一 production template

M3 MVP 只提供 `sales_report`。历史 `sales_weekly`、`satisfaction`、`operating_overview` 可以继续服务旧 Mock/test compatibility，但不得被 Catalog 或文档声明为 M3 production available。

### TemplateContract 与 ReportDataPlan

```text
sales_report
├─ total_sales
│  └─ Measure: Total Sales
├─ total_quantity
│  └─ Measure: Total Quantity
├─ sales_by_category
│  ├─ Measure: Total Sales
│  └─ Dimension: Category
└─ top_products
   ├─ Measure: Total Sales
   ├─ Dimension: Product
   ├─ Sort: desc
   └─ TopN: 5
```

TemplateContract 还固定数据来源、筛选、时间范围与生成时间 metadata，并绑定 `local_desktop_model` 与 M3 PBIX schema fingerprint。ReportDataPlanBuilder 只接受 template key + runtime schema；不接受 LLM draft、QueryResult、Known-answer expected 或自由 DAX。

### M3 Truth Boundary

```text
Natural Language
→ Intent / Template Grounding
→ Semantic Grounding
→ TemplateContract + runtime schema compatibility
→ deterministic ReportDataPlan
→ Canonical QueryPlan（per sub-query）
→ Deterministic DAX → Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult → VerifiedFactSet（per sub-query）
→ deterministic Report Data Contract（M3.1）
→ deterministic ReportSpec（M3.1）
→ Fixed Renderer（M3.1）
→ static HTML
```

LLM 对 template canonical key、报表查询集合、DAX、KPI/rows、排名、趋势、因果、Report factual truth、HTML/CSS 的 authority 均为 0。

### M3.0 Acceptance

- unknown/legacy template fail closed；LLM wrong weak signal 不覆盖 Catalog。
- missing Measure/Dimension/type 或 fingerprint mismatch 不产出 partial/fake plan。
- 固定四查询可重复相等，且每项是 CanonicalQueryPlan。
- production contract module 不导入 QueryResult、PowerBIAdapter、ToolGateway、DAX builder 或 Fact builder，不包含业务 oracle 数值。
- Real smoke 使用 M3 专用 PBIX，经现有 M2 链执行四查询并构建 VerifiedFactSet；`source_mode=real`，fallback/LLM/Renderer=0。
- full offline pytest、Golden、Architecture、Repository Safety、Error Ledger、Documentation Governance 与 `git diff --check` fresh 通过。

## M3 后续路线

### M3.1 — Deterministic Report Assembly + Fixed Renderer

- 在现有 TurnPipeline 控制面内编排 ReportDataPlan 的四个 sub-query；每个查询继续独立经过 M2 执行与 FactSet 边界。
- 由普通代码把多个 VerifiedFactSet/QueryResult 组成 deterministic Report Data Contract 与 deterministic ReportSpec。
- 实现唯一 `sales_report` Fixed Renderer 与静态 HTML；无 JavaScript、自由 HTML、用户模板、PDF 或复杂图表框架。
- 本地 HTML acceptance 只写 `local_state/reports/`，禁止提交。

### M3.2 — Report Resource Contract

- 实现 report resource repository、report_id、保存生命周期、查看与 HTML 下载 API。
- API 不暴露任意路径或外部 URL；资源只引用后端生成内容。
- 不进入 M4 persistence 或 M5 React。

### M3.3 — Optional Hardened Acceptance

若 M3.1/3.2 需要独立收口，则执行 Real/failure/security/HTML safety/文档治理与远程审计；不得借此扩展模板、图表或前端范围。

## 永久阶段边界

- 不使用 LangGraph、多 Agent 或 PydanticAI。
- 不复制 Pipeline/Service，不绕过 TurnPipeline、ToolGateway、PowerBIAdapter、Harness、Independent Layer 3 或 VerifiedFactSet。
- 不扩展 M2 grammar；Report query 只能使用已封板 Measure/Dimension/EQ/resolved Time/Sort/TopN 能力。
- M3 MVP 不做 PDF、自由 HTML、用户模板、JavaScript、动态 Power BI Report、React UI 或 Remote MCP。
- M3.0 未验收前不得进入 M3.1；M3.1 未验收前不得进入 M3.2。
- 普通轮次不创建 Tag；禁止 force push。

---

*最后更新：2026-08-17 | M3.0 sales_report contract + PBIX binding route*
