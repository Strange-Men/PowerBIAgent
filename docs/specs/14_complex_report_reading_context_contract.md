# Spec 14 — Complex Report Reading Context Contract

## 1. 适用范围

本合同适用于所有 `tier=COMPLEX` 的固定模板，不限定 Sales。它只定义阅读上下文、事实/来源绑定和 fail-closed 规则，不授予新查询、指标、图表或 Renderer 能力。

## 2. 必填 Reading Context

复杂报表在渲染前必须有完整 `ReportReadingContext`：

| 字段 | 含义 | Authority |
|---|---|---|
| `report_title` | 报表主题 | template/ordinary code |
| `analysis_period` | bounded 时间范围或全部可用数据 | canonical + verified scope |
| `active_filters` | 实际生效的 dimension/member filters | canonical + verified scope |
| `metric_definitions` | 口径、单位、聚合、tax/comparison state | registry/runtime metadata/exact override |
| `exception_assessment` | evaluated 或 cannot determine | deterministic rule registry + facts |
| `semantic_model` | 精确模型 identity | runtime/snapshot |
| `data_source` | source kind/mode/展示名 | adapter/snapshot |
| `data_freshness` | known timestamp 或 explicit unknown | runtime refresh metadata only |
| `generated_at` | artifact 生成时间 | application clock |

缺少任一字段、字段为空、ReadingContext 与 ReportSpec/Snapshot 不一致，均须在 Renderer 调用前失败。

## 3. Scope 投影

所有报表子查询必须证明共同 scope。每个 CanonicalQueryPlan 的 filters/time range 必须与对应 VerifiedFactSet 的 `APPLIED_FILTER` / `APPLIED_TIME_RANGE` 一致；不一致或子查询 scope 不同则拒绝装配。无时间限制显示“全部可用数据”；无额外筛选显示“无额外筛选”。不得读取用户原句、LLM draft 或 presentation text 重建 scope。

## 4. Metric Definition

每项定义包含 `canonical_measure`、`display_name`、`unit`、`format`、`aggregation`、`semantic_source`、`tax_basis`、`comparison_basis`、`definition_source`。未知 facet 必须是 `status=UNKNOWN, value=None, source=unknown`；名称如 Sales/Revenue/销售额不能推导含税、未税、净额、毛额或同比基准。`definition_source` 不接受 LLM。

## 5. Exception / Anomaly

`EVALUATED` 必须有 registry-owned rule ID 和 VerifiedFactSet evidence IDs。缺少目标、预算、预测或统计规则时只能是 `CANNOT_DETERMINE`，不得根据折线形状、任意阈值或 LLM 文字生成异常事实。

## 6. Freshness

`data_updated_at != generated_at`。`queried_at`/`snapshot_at` 只记录查询/快照生命周期，也不得冒充 refresh time。无 runtime refresh metadata 时，canonical contract 保持：

`state=UNKNOWN, data_updated_at=None, display_text="数据更新时间：模型未提供"`。

professional presentation 可把 `UNKNOWN` 映射为“暂不可获取”等友好文案，但不得更改 canonical state 或填造时间。`queried_at`、`snapshot_at`、`generated_at` 分别由查询结果取得、VerifiedFactSet 快照完成和 artifact 生成阶段独立取时；不得复制同一时间冒充三个事件。aware datetime 在缺少用户/application timezone authority 时统一显示 UTC；naive datetime 必须注明“时区未声明”，禁止猜测本地时区。

## 7. Data Snapshot / Source Boundary

`ReportDataSnapshot` 是不可变 provenance contract：模型 identity、schema fingerprint、成对 QueryResult/VerifiedFactSet IDs、source mode、source kind、可选 refresh time、query/snapshot time。Local/Remote 共享该结构；`REMOTE_MCP` 当前仅保留枚举，不代表已接入 Remote MCP。

## 8. Template Gate

- SIMPLE：不强制本合同，不改变现有 `sales_report` 生成链。
- COMPLEX：完整 ReadingContext + Snapshot 是 Renderer 前置条件。
- unknown/unavailable/stale template：fail closed。
- 不允许 default、first-item、simple renderer fallback 或假 renderer。

## 9. Sales 首个采用者

`sales_report` 与 `sales_executive_report` 共用同一 `SALES_QUERY_REQUIREMENTS`。专业模板已在 M5.10.1 以独立 fixed Renderer 开放。两模板的事实语义相同，差异只允许位于固定信息架构、layout、visualization、style 与 presentation-only projection。

M5.10.2 新增 `REQUESTED` / `FULL_AVAILABLE` coverage。`FULL_AVAILABLE` 的最终 section 集合固定为 selected template、runtime capability、registered catalog 与 non-empty VerifiedFactSet evidence 的交集；unavailable/dropped section 必须有原因，禁止 weak LLM、预算截断、placeholder 或 fake zero 改写完整度。专业主阅读区使用友好 display，exact canonical identity/source/timestamp/metric provenance 保留在低权重 audit footer。

## 10. 验收

永久测试覆盖模板 tier、全部必填字段、scope authority、UNKNOWN metric basis、CANNOT_DETERMINE exception、四类时间分离、共享 sales requirement identity、typed coverage、presentation/canonical 边界、无 fallback 和简易模板回归。Mutation sanity 必须能抓住生成时间冒充刷新时间、complex 绕过 ReadingContext、executive requirement 漂移、主区泄漏 raw technical token、Reading Context 过高和 FULL_AVAILABLE section 缺失。
