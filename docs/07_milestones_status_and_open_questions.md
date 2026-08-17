# 07 — 里程碑状态与待确认事项

> **状态：** M3.2 — Hardened Sales Report Visual Acceptance 已完成，M3 final closure
> 详细历史见 `CHANGELOG.md`、`docs/08_development_roadmap.md` 与 Git。

## 里程碑总览

| Milestone | 交付范围 | 状态 |
|---|---|---|
| M0—M1 | 项目基础、契约、Harness、FastAPI、DeepSeek、统一 TurnPipeline | ✅ 已封板 |
| M2 | Local MCP + Desktop、Semantic Grounding、Deterministic DAX、VerifiedFactSet | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | 报表架构、单一销售模板合同、M3 PBIX schema/Real baseline | ✅ commit/push/GPT remote audit PASS；已合入 main |
| M3.1 | 真实销售报表、固定 HTML、ReportArtifact、查看/下载 | ✅ 远程审计 PASS、已合入 main，CI success |
| M3.2 | 确定性 CSS 可视化、静态安全、Real 与视觉 hardened acceptance | ✅ 完成；M3 final closure，无 Tag |
| M4 | 持久化会话与历史搜索 | ⬜ 未开始 |
| M5 | React + Vite 前端与联调 | ⬜ 未开始 |

## M3 合并与 CI truth

- M3.0 commit：`e4b5c6c6a759cdf22c74c4d87902482563e27cad`。
- GPT 远程架构审计：PASS。
- `main` 从 M2 seal `70748daabfa5d3dd250f17fe22f0c892c7a30b74` 纯 fast-forward 到 M3.0 commit，无 merge commit/rebase/force push。
- main push 触发 `PowerBIAgent Validation` run `31986207118`，head SHA 与 M3.0 commit 一致，结论 `success`。
- M3.1 commit：`fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57`；远程审计后从 M3.0 纯 fast-forward 合入 main，main push run `31989328261` 对应同一 SHA，结论 `success`；本地与远程开发分支随后删除。
- GitHub CI、本地 pytest/Golden/gates、Real Power BI smoke 与静态视觉检查是不同证据，必须分别描述。

## 当前能力状态

| 能力 | 状态 |
|---|---|
| TurnPipeline / ToolGateway / PowerBIAdapter 单一控制面 | ✅ M2 封板骨架保持不变 |
| M3 production template | ✅ 仅 `sales_report`；legacy/unknown unavailable |
| ReportDataPlan | ✅ 全量数据固定四查询，不读 LLM draft |
| SalesReportData / ReportSpec | ✅ 四组 QueryResult / VerifiedFactSet 确定性组装 |
| Fixed Renderer | ✅ 固定 UTF-8 static HTML；确定性 Category / Top Product CSS 横条与同源表格；无 JS/CDN/外部资源/自由 HTML |
| ReportArtifact | ✅ report_id、provenance、content type/hash、原子本地保存 |
| Resource API | ✅ view/download；unknown/path traversal 拒绝 |
| Idempotency / Memory | ✅ replay 复用 report_id；render/store failure 不成功提交 Memory |
| Persistent sessions / React | ⬜ M4 / M5，未提前实现 |

## `sales_report` 固定 MVP 范围

当前报表只针对整个 M3 PBIX 全量数据；不接受月份、Category filter、比较、趋势、用户自由 ReportDataPlan 或任意 DAX。

| Requirement | Measure | Dimension | Sort / TopN |
|---|---|---|---|
| `total_sales` | Total Sales | — | — |
| `total_quantity` | Total Quantity | — | — |
| `sales_by_category` | Total Sales | Category | — |
| `top_products` | Total Sales | Product | desc / 5 |

TopN 对外只使用 `result_position` / QueryResult order，不声明严格 business rank；boundary ties 可使结果超过 5 行。

## M3.2 hardened acceptance

- 未新增 template、query、DAX、filter、business fact、chart type、resource API、persistence 或 frontend；只把既有两组 `ChartSpec` / table rows 以固定 CSS 横条和同源表格呈现。
- 横条宽度由已验证行值在组内按绝对最大值归一化，固定半入舍入到两位小数；可视数值仍显示原始已验证值。
- 窄屏使用固定 Flex 换行保持 label/value/bar 对齐；桌面与 430px 静态渲染均经视觉检查 PASS。
- HTML 保存前拒绝 active script、external URL 及 `link` / `iframe` / `object` / `embed` / `@import` / `url()` / `src=`。
- DeepSeek prompt 明确只保留弱语言信号；报表 template、四查询、KPI、chart/table 事实、HTML/CSS、布局、保存与资源引用 authority 均为 0。

## 待确认事项

| 事项 | 决策时点 |
|---|---|
| M4 持久化介质与会话搜索策略 | M4 开始前 |
| M5 前端状态管理与展示范围 | M5 开始前 |
| Remote MCP 管理员与授权条件 | 重新批准 Remote 后 |

## 当前真实风险

- M3 PBIX runtime `OrderDate` 为 `Int64`；当前全量报表不使用时间筛选，不得伪装为 DateTime。
- Local Modeling MCP 仍为 Preview；官方包、Desktop 或协议变化后需重新人工 smoke。
- ReportRepository 是 M3 artifact resource，不是 M4 session persistence；进程内 metadata 不承诺跨进程恢复。
- PBIX、真实输出、HTML 与 `local_state/` 永不提交。

## Tag 与基线

| 项目 | 值 |
|---|---|
| M0—M2 Final Seal | `m2.6.4-m0-m2-final-seal` → `70748da` |
| M3.0 main | `e4b5c6c`；CI run `31986207118` success |
| M3.1 main | `fa4cc0c`；CI run `31989328261` success；开发分支已删除 |
| M3 final Tag | **none；本轮未授权且未创建** |

---

*最后更新：2026-08-17 | M3.2 hardened visual acceptance；M3 final closure*
