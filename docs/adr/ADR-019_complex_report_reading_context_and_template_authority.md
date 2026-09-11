# ADR-019 — Complex Report Reading Context and Template Authority

- **状态：** accepted
- **日期：** 2026-09-11
- **决策者：** 用户明确批准（M5.10）
- **适用阶段：** M5.10 复杂报表合同与专业销售模板基础

## 背景

现有 `sales_report` 已具备确定性规划、VerifiedFactSet 装配、固定 Renderer 与资源恢复，但复杂经营报表还缺少统一的阅读上下文合同。若直接照参考图实现视觉，会产生四类越权：从原句或 LLM 草稿重建筛选、按指标名称猜税务/比较口径、用 artifact 生成时间冒充数据刷新时间、在缺少正式规则时编造异常结论。

## 决策

1. 模板必须声明 `ReportTemplateTier`。`SIMPLE` 可沿用既有最小元数据；`COMPLEX` 在 Renderer 前必须具备完整 `ReportReadingContext` 与 `ReportDataSnapshot`，缺失或不一致 fail closed。
2. Reading Context 至少包含标题、分析期间、实际筛选、指标定义、异常评估、语义模型、数据来源、数据新鲜度和生成时间。字段是必填状态，不允许以空白代替 UNKNOWN。
3. 分析期间和筛选只能由 CanonicalQueryPlan 与其 VerifiedFactSet 中的 `APPLIED_TIME_RANGE` / `APPLIED_FILTER` 一致证据投影。不得从用户原句、LLM draft 或 presentation text 反解析。无额外筛选固定表达为“无额外筛选”。
4. `MetricDefinition` 由 registry、runtime metadata 或 exact override 提供；LLM authority 为 0。名称相似不证明含税/未税、净额/毛额、财务确认或比较基准。未声明的 tax/comparison basis 保持 `UNKNOWN`。
5. M5.10 只注册 Total Sales、Total Quantity、Total Orders、Average Order Value 四项定义，不扩展新业务指标。
6. 异常状态只有 `EVALUATED` 与 `CANNOT_DETERMINE`。`EVALUATED` 必须绑定 deterministic rule ID 和 VerifiedFactSet evidence；当前无 Target/Budget/Forecast/statistical rule，合法默认是“当前模型未提供可验证的目标、预测或异常判断基准”。
7. `data_updated_at` 表示业务数据真实刷新时间，`generated_at` 表示 artifact 创建时间，二者永不互相填充。MCP query time 也不等于刷新时间。无权威 runtime refresh metadata 时 freshness 必须为 UNKNOWN。
8. 三张参考图分别是 P0 Reading Context、P1 layout intent、P2 style inspiration。**Reference images are NOT factual or functional authority.** 图片中的 YoY/MoM/Forecast/Target/Map/AI Insight/Anomaly/Budget/任意字段和图表不得自动成为能力。
9. `SALES_QUERY_REQUIREMENTS` 是两个销售模板唯一共享 query requirement authority。相同模型、scope 与 requirement 必须经过相同 CanonicalQueryPlan → deterministic DAX → QueryResult → VerifiedFactSet；模板只能改变信息架构、布局、视觉与样式。
10. `ReportDataSnapshot` 固化 semantic model identity、schema fingerprint、QueryResult/VerifiedFactSet provenance、source mode/source kind、可选 data refresh time、queried/snapshot time。`REMOTE_MCP` 仅是保留的 source-kind 值，不绑定 endpoint、auth 或 request schema。
11. 新身份 `sales_executive_report` / “专业销售经营分析模板” / `executive_sales_report` / `COMPLEX` 已注册，但 M5.10 保持 `UNAVAILABLE`，不进入公开目录，也不注册假 Renderer。M5.10.1 完成 fixed Renderer 与 Real Visual Acceptance 后才能开放。
12. LLM 对报表事实、指标口径、刷新时间、异常判断、query requirements、DAX、HTML、CSS 与 SVG authority 全部为 0。

## 备选方案

- 直接复制参考图并补齐其字段：拒绝，图片不是事实或功能 authority。
- 专业模板临时 fallback 到简易 Renderer：拒绝，会伪装成已完成模板并破坏 template identity。
- 用 `generated_at` 或 query time 展示“最后刷新”：拒绝，会制造错误数据新鲜度声明。
- 为未来 Remote MCP 创建独立报表管线：拒绝；未来只替换 PowerBIAdapter 后的 provider/source，以上合同保持稳定。

## 后果

- 正面：未来复杂模板在视觉实现前已有不可伪造的阅读上下文与 provenance；Local → Remote MCP 不要求推翻报表事实架构；简易模板不受影响。
- 负面：当前专业模板保持不可用；真实刷新时间缺失时必须明确显示 UNKNOWN，不能提供看似完整但无证据的时间。
- 后续：M5.10.1 只实现 deterministic professional Renderer 与真实视觉验收；M5.10.2 负责 report hardening/cloud-ready 最终收口。
