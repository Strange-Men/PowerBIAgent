# 07 — 里程碑状态与待确认事项

> **状态：** M3.0 — Report Architecture + Sales Contract Baseline；fresh offline/Real acceptance 已通过
> 详细历史见 `CHANGELOG.md`、`docs/08_development_roadmap.md` 与 Git。

## 里程碑总览

| Milestone | 交付范围 | 状态 |
|---|---|---|
| M0—M1 | 项目基础、契约、Harness、FastAPI、DeepSeek、统一 TurnPipeline | ✅ 已封板 |
| M2 | Local MCP + Desktop、Semantic Grounding、Deterministic DAX、VerifiedFactSet | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | 报表架构、单一销售模板合同、M3 PBIX schema/Real baseline | ✅ 已完成；等待远程审计 |
| M3.1 | 多查询事实聚合、deterministic ReportSpec、Fixed Renderer、静态 HTML | ⬜ 未开始 |
| M3.2 | report resource repository、ID、查看/下载 API | ⬜ 未开始 |
| M3.3 | 必要时的 hardened acceptance、安全与文档收口 | ⬜ 视 M3.1/3.2 结果决定 |
| M4 | 持久化会话与历史搜索 | ⬜ 未开始 |
| M5 | React + Vite 前端与联调 | ⬜ 未开始 |

## 当前能力状态

| 能力 | 状态 |
|---|---|
| TurnPipeline / ToolGateway / PowerBIAdapter 单一控制面 | ✅ M2 封板基线保持不变 |
| Business Semantic / Canonical QueryPlan authority | ✅ ADR-008 |
| Deterministic DAX / Independent Layer 3 | ✅ ADR-009；Real DAX LLM=0 |
| VerifiedFactSet / factual output | ✅ ADR-009；数字、顺序、筛选、时间与 provenance authority |
| M3 production template | ✅ 仅 `sales_report`；其他 key unavailable |
| TemplateContract / schema binding | ✅ `local_desktop_model` + M3 PBIX fingerprint |
| ReportDataPlan | ✅ 固定四查询；不读取 LLM draft |
| M3 Real contract smoke | ✅ 四查询经 M2 链执行；source real，fallback/LLM/Renderer=0 |
| Fixed Renderer / HTML | ⬜ M3.1 |
| Resource ID / 保存 / 查看 / 下载 | ⬜ M3.2 |
| Persistent Memory / React | ⬜ M4 / M5 |

## M3.0 固定边界

- `sales_report` 固定内容：Total Sales、Total Quantity、Sales by Category、Top 5 Products by Total Sales，以及来源/筛选/时间/生成时间 metadata。
- 缺 Measure、Category、Product、类型或 schema fingerprint 不匹配时整个 ReportDataPlan fail closed；不得伪造或补齐 section。
- 每个 sub-query 必须复用 Canonical QueryPlan → Deterministic DAX → Independent Layer 3 → ToolGateway → PowerBIAdapter → QueryResult → VerifiedFactSet。
- M3.0 不生成正式 HTML，不实现 Renderer、报表文件、resource repository 或 API。

## 待确认事项

| 事项 | 决策时点 |
|---|---|
| M3.1 Fixed Renderer 的模板文件布局、样式与本地 HTML acceptance | 用户明确批准 M3.1 后 |
| M3.2 report_id、保存、查看与下载契约 | M3.1 验收后 |
| M3.3 是否必要以及 hardened acceptance 范围 | M3.2 验收后 |
| M4 持久化介质与会话搜索策略 | M4 开始前 |
| M5 前端状态管理与展示范围 | M5 开始前 |
| Remote MCP 管理员与授权条件 | 重新批准 Remote 后 |

## 当前真实风险

- M3 PBIX runtime `OrderDate` 类型实际为 `Int64`；M3.0 如实绑定但不扩展 M2 time grammar。未来需要日期过滤时必须先修正模型/契约并重新 fingerprint acceptance。
- Local Modeling MCP 仍为 Preview；官方包、Desktop 或协议变化后需重新人工 Smoke。
- TopN ties 可合法超过 5；Report 不得把 result position 宣称为严格 business rank。
- M3 专用 PBIX 不替换 M2 封板 PBIX。PBIX、真实输出和未来 HTML acceptance 文件均禁止提交；HTML 未来只放 `local_state/reports/`。

## Tag 与基线

| 项目 | 值 |
|---|---|
| M0—M1 正式 Tag | `m1.7.2-m0-m1正式封板` → `23d8ddb` |
| M2 Local Demo Tag | `m2-local-powerbi-demo-release` → `c9af48a` |
| M0—M2 Final Seal | `m2.6.4-m0-m2-final-seal` → `70748da` |
| M3.0 开发分支 | `dev/m3.0-report-contract` |
| 本轮 Tag | **none；禁止创建** |

---

*最后更新：2026-08-17 | M3.0 sales_report contract baseline*
