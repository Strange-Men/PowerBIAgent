# 07 — 里程碑状态与待确认事项

> **状态：** M3.1 — Sales Report Full Generation + Static HTML + Report Resource 已完成，等待 GPT 远程审计
> 详细历史见 `CHANGELOG.md`、`docs/08_development_roadmap.md` 与 Git。

## 里程碑总览

| Milestone | 交付范围 | 状态 |
|---|---|---|
| M0—M1 | 项目基础、契约、Harness、FastAPI、DeepSeek、统一 TurnPipeline | ✅ 已封板 |
| M2 | Local MCP + Desktop、Semantic Grounding、Deterministic DAX、VerifiedFactSet | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | 报表架构、单一销售模板合同、M3 PBIX schema/Real baseline | ✅ commit/push/GPT remote audit PASS；已合入 main |
| M3.1 | 真实销售报表、固定 HTML、ReportArtifact、查看/下载 | ✅ 已实现并 fresh offline/Real 验收；等待远程审计 |
| M3.2 | 必要时的 hardened acceptance / M3 final seal | ⬜ 非功能轮；仅在用户批准后进入 |
| M4 | 持久化会话与历史搜索 | ⬜ 未开始 |
| M5 | React + Vite 前端与联调 | ⬜ 未开始 |

## M3.0 合并与 CI truth

- M3.0 commit：`e4b5c6c6a759cdf22c74c4d87902482563e27cad`。
- GPT 远程架构审计：PASS。
- `main` 从 M2 seal `70748daabfa5d3dd250f17fe22f0c892c7a30b74` 纯 fast-forward 到 M3.0 commit，无 merge commit/rebase/force push。
- main push 触发 `PowerBIAgent Validation` run `31986207118`，head SHA 与 M3.0 commit 一致，结论 `success`。
- dev branch push 本身不代表 CI；当前 workflow 只覆盖 main push、PR → main 与 workflow_dispatch。本地 pytest、Golden、Real smoke 和 GitHub CI 是不同证据，必须分别描述。

## 当前能力状态

| 能力 | 状态 |
|---|---|
| TurnPipeline / ToolGateway / PowerBIAdapter 单一控制面 | ✅ M2 封板骨架保持不变 |
| M3 production template | ✅ 仅 `sales_report`；legacy/unknown unavailable |
| ReportDataPlan | ✅ 全量数据固定四查询，不读 LLM draft |
| SalesReportData / ReportSpec | ✅ 四组 QueryResult / VerifiedFactSet 确定性组装 |
| Fixed Renderer | ✅ 固定 UTF-8 static HTML；无 JS/CDN/自由 HTML；动态文本 escape |
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

## 待确认事项

| 事项 | 决策时点 |
|---|---|
| M3.2 是否需要以及 hardened acceptance / final seal 范围 | M3.1 GPT 远程审计后由用户决定 |
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
| M3.1 开发分支 | `dev/m3.0-report-contract` |
| 本轮 Tag | **none；禁止创建** |

---

*最后更新：2026-08-17 | M3.1 sales_report HTML resource closure*
