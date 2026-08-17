# ADR-010 — Deterministic Report Template and Data Plan Authority

- **状态：** accepted
- **日期：** 2026-08-17
- **决策者：** 用户明确批准
- **适用阶段：** M3 固定模板静态 HTML 报表

---

## 背景

M2 已封板 Canonical QueryPlan、Deterministic DAX、Independent Layer 3 与 VerifiedFactSet，但历史 ReportSpec/Mock Renderer 只服务兼容测试，不能决定正式报表需要哪些查询，也不能证明多个查询如何组成同一报表。若继续让 LLM 或单次用户 QueryPlan 临时决定报表内容，会重新引入模板、DAX、数字和 section 幻觉。

## 决策内容

1. M3 MVP 唯一 production template 是 `sales_report`。`sales_weekly`、`satisfaction`、`operating_overview` 仅可保留为历史兼容 key，M3 production availability 必须为 false；未知模板同样 fail closed。
2. `TemplateContract` 是模板内容与查询需求的唯一 authority。它绑定 `semantic_model_key=local_desktop_model` 与 M3 专用 PBIX runtime schema fingerprint `d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac`；model、必需对象、类型或 fingerprint 不匹配时不得生成 ReportDataPlan。
3. `sales_report` 固定四个 sub-query：`Total Sales`、`Total Quantity`、按 `Category` 的 `Total Sales`、按 `Total Sales desc` 的 `Product TopN 5`。数据来源、筛选、时间范围与生成时间是固定 metadata contract，不由 LLM 扩写。
4. `ReportDataPlanBuilder` 只接受 registry-owned template key 与已验证 runtime schema，不接受 Intent/QueryPlan LLM draft、QueryResult、Known-answer expected 或自由查询描述。
5. 每个 sub-query 后续必须逐个复用 M2 封板链：Canonical QueryPlan → Deterministic DAX → Independent Layer 3 → ToolGateway → PowerBIAdapter → Power BI → QueryResult → VerifiedFactSet。M3 不创建第二套 DAX、Fact、Power BI 或 Pipeline。
6. 多个 VerifiedFactSet 之后才允许由普通代码形成 deterministic Report Data Contract 与 deterministic ReportSpec。Fixed Renderer 只消费该结构化结果，不拥有事实、HTML/CSS 选择权以外的业务 authority，也不得调用 Power BI。
7. M3.0 只落地 contract、binding、validator、ReportDataPlan、测试与 Real smoke；Renderer/HTML 属于 M3.1，资源保存与查看/下载 API 属于 M3.2，最终 hardened acceptance 视需要进入 M3.3。

## LLM authority

LLM 在 M3 可做语言理解和受限表达，但以下 authority 永久为 0：template canonical authority、报表查询集合、Canonical QueryPlan slots、DAX、KPI 数字、表格 rows、结果顺序/排名、趋势、因果、Report factual truth、HTML 与 CSS。

## 备选方案

- 让 LLM 根据用户问题动态规划报表查询：拒绝，无法形成固定模板和可审计数据需求。
- 复用单次 ReportSpec/QueryResult 填满全部 section：拒绝，缺失数据会诱发伪造或错误补算。
- 为报表新建专用 DAX/Power BI/Fact pipeline：拒绝，违反 ADR-005/009。
- 同时上线多个模板：拒绝，扩大 M3 MVP 与 schema compatibility 面。

## 后果

- 正面：同一 runtime schema 始终得到相同四查询；缺对象或 fingerprint 漂移在执行前失败；M3.1/3.2 不能重新解释模板事实。
- 负面：M3 PBIX schema 变化必须显式审核并更新 binding；M3.0 本身不产生 HTML，也不提供报表 API。
- 运维：PBIX、Real 输出与未来 HTML acceptance 文件保持 gitignored；未来 HTML 只允许保存到 `local_state/reports/`。

---

*最后更新：2026-08-17 | accepted*
