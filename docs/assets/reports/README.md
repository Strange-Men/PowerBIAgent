# Report Reference Assets

本目录保存 M5.10 复杂报表合同与专业销售模板的三张参考图片。它们按下列优先级使用，实际文件名以仓库为准：

| 优先级 | 文件 | Authority |
|---|---|---|
| P0 | `01_reading_context_hard_requirements.png` | 复杂报表 Reading Context 硬合同参考 |
| P1 | `02_sales_executive_primary_layout.png` | 专业销售模板信息架构与主布局意图 |
| P2 | `03_sales_executive_visual_style.png.png` | 颜色、字体、卡片、圆角、阴影、header、grid 密度与视觉层次灵感 |

## P0 — Hard Contract

所有复杂报表必须在用户阅读业务数字前明确提供：

1. 报表标题；
2. 分析时间范围；
3. 当前筛选状态；
4. 指标定义 / 口径状态；
5. 异常 / 关注状态；
6. 数据模型 / 数据来源；
7. 数据更新时间状态；
8. 报表生成时间。

任一必填项缺失时必须 fail closed，不得进入复杂 Renderer。无额外 filter 时必须明确显示“无额外筛选”；无法取得权威刷新时间时必须显示“数据更新时间：模型未提供”。

## P1 — Layout Intent

专业销售模板的推荐顺序为：

`Header / Reading Context → KPI Summary → Hero Sales Trend → Region + Category → Top Products + Top Customers → Detail / Ranking → Audit Footer`

该顺序只约束未来 M5.10.1 的信息架构。section 仍须满足用户需求、runtime capability、共享 sales requirements 与 VerifiedFactSet 证据，缺失能力不显示空区块。

## P2 — Style Inspiration

颜色、字体、卡片、圆角、阴影、header 风格、grid 密度和视觉层次可按固定模板设计系统调整。P2 不决定查询、指标、数据、图表类型或业务结论。

**Reference images are NOT factual or functional authority.**

图片中即使出现 YoY、MoM、Forecast、Target、Map、AI Insight、Anomaly、Budget、任意指标、任意图表或任意字段，只要当前 registry、runtime schema、canonical plan 与 VerifiedFactSet 没有共同证明，就不得实现、推断或展示。LLM 对这些能力、事实与最终 HTML/CSS/SVG 的 authority 为 0。
