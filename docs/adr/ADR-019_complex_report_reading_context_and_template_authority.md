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
8. 三张参考图的 presentation authority 固定为：`01` 是 P0 Reading Context 信息完整性 authority，`02` 是 P1 professional template layout authority，`03` 是 P1 professional visual-language authority。它们约束 UI、layout、card、color、table、chart presentation、hierarchy 与 spacing；**仍不是 factual、DAX、semantic 或 metric authority。** 图片中的 YoY/MoM/Forecast/Target/Map/AI Insight/Anomaly/Budget/任意字段不得自动成为能力。
9. `SALES_QUERY_REQUIREMENTS` 是两个销售模板唯一共享 query requirement authority。相同模型、scope 与 requirement 必须经过相同 CanonicalQueryPlan → deterministic DAX → QueryResult → VerifiedFactSet；模板只能改变信息架构、布局、视觉与样式。
10. `ReportDataSnapshot` 固化 semantic model identity、schema fingerprint、QueryResult/VerifiedFactSet provenance、source mode/source kind、可选 data refresh time、queried/snapshot time。`REMOTE_MCP` 仅是保留的 source-kind 值，不绑定 endpoint、auth 或 request schema。
11. 新身份 `sales_executive_report` / “专业销售经营分析模板” / `executive_sales_report` / `COMPLEX` 在 M5.10 foundation 注册；M5.10.1 完成 fixed Renderer 与 Real Visual Acceptance 后已开放，并与 `sales_report` 一同要求用户显式选择。
12. LLM 对报表事实、指标口径、刷新时间、异常判断、query requirements、DAX、HTML、CSS 与 SVG authority 全部为 0。
13. M5.10.2 的 coverage 只有 `REQUESTED` 与 `FULL_AVAILABLE` 两种 typed mode。`FULL_AVAILABLE` 必须是 selected template ∩ runtime capability ∩ registered section catalog ∩ non-empty VerifiedFactSet evidence；weak LLM、通用工具预算或 Renderer 不得缩减、扩展或伪造该集合。unavailable 与 facts 后 dropped section 必须带确定性原因进入 audit。
14. 专业报表的友好名称、状态、单位和时间只属于 presentation projection。canonical model/source/status/timestamp/metric provenance 必须原样保留并可审计；projection 不得修改值、scope、顺序或 provenance。
15. `queried_at`、`snapshot_at`、`generated_at` 分别表示查询结果取得、VerifiedFactSet 快照完成和 artifact 生成三个不同 application-clock 事件；`data_updated_at` 仍只接受 runtime refresh metadata。失败或取消后若 artifact 已创建但 Memory 未提交，必须通过正式 repository API 补偿删除，不能形成第二持久化管线。
16. `sales_executive_report` 是 fixed executive dashboard template。repository-owned presentation contract 决定 theme、typography、spacing、section order、12-column grid、KPI component、visual/table mapping 与 responsive variants；runtime 只能以 VerifiedFactSet-backed `ReportSpec` 填充预定义 slot。不得按 cardinality 为同一 section 改换图表类型，也不得退化为 Simple adaptive card layout。
17. 专业报表 presentation timezone 固定为 `Asia/Shanghai`；aware timestamp 转换后标示“北京时间”，canonical aware UTC 值保持不变。naive timestamp 继续显示“时区未声明”。generic `currency` 不能证明 CNY，因此不得显示元、¥ 或人民币；ranking position 必须以整数展示。

## 备选方案

- 直接复制参考图并补齐其字段：拒绝，图片不是事实或功能 authority。
- 专业模板临时 fallback 到简易 Renderer：拒绝，会伪装成已完成模板并破坏 template identity。
- 用 `generated_at` 或 query time 展示“最后刷新”：拒绝，会制造错误数据新鲜度声明。
- 为未来 Remote MCP 创建独立报表管线：拒绝；未来只替换 PowerBIAdapter 后的 provider/source，以上合同保持稳定。

## 后果

- 正面：未来复杂模板在视觉实现前已有不可伪造的阅读上下文与 provenance；Local → Remote MCP 不要求推翻报表事实架构；简易模板不受影响。
- 负面：真实刷新时间缺失时必须明确显示未知，完整覆盖可能因 runtime capability 不足而只有可证明子集，但必须审计缺失原因而不能伪造完整度。
- 后续：M5.10.1 deterministic professional Renderer 与真实视觉验收、M5.10.2 product refinement/hardening 已完成本地收口；M5.10.3 Final Real E2E/stress/mutation/historical closure 尚未启动，M5 FINAL=false。
