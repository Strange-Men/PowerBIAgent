# ADR-014 — Question Routing 与 Query Shape Authority

- **状态：** accepted
- **日期：** 2026-08-28
- **决策者：** 用户明确批准
- **适用阶段：** M5.8.2

## 背景

既有 Intent/Grounding 路径把多数 `DATA_QUESTION` 隐式等同于 measure query，导致产品帮助、模型信息、基础算术、实体列表以及部分排名/member-set 问题错误进入“请明确业务指标/筛选字段”。这既产生不必要澄清，也会让非业务请求触及不需要的 Power BI 语义链。

## 决策

1. 在 Semantic Grounding 前增加 code-owned Question Router，只判定能力类别；非业务类别直接形成安全终态并保持 ZERO schema/member/DAX/semantic Memory mutation。
2. Router 不选择任何 Power BI 对象、成员、日期角色或事实值。业务对象继续由 ADR-008 的 runtime schema、model-scoped glossary、runtime member 与 Grounding 决定。
3. 业务查询携带领域无关 Query Shape。Shape 只定义 required slots，不定义 slot identity：SCALAR、ENTITY_LIST、GROUPED、RANKING、MEMBER_SET、FILTERED_AGGREGATION、TREND、BOUNDED_TREND。
4. Canonical QueryPlan 可表达无 measure 的 ENTITY_LIST，以及同字段 runtime-validated member set。StateTransition、Pending Clarification、DAX Builder 和独立 verifier 必须使用同一 shape contract。
5. `RANKING` 的极值单项表达确定性产生 `top_n=1` 与方向；dimension/measure 仍必须由 Grounding 唯一证明。TOPN 对 ties 的既有事实安全语义保持不变。
6. Calculator 使用长度、深度、token 类型和数值幅度均受限的递归下降解释器；禁止 `eval`、`exec`、名称、属性、调用与任意代码。
7. Product Help 只来自 code-owned capability contract；System Info 只来自当前 immutable `LLMModelProfile` 的公开 display metadata。
8. REPORT_REQUEST 继续复用 M5.7.2 的 Intent 后 Template Gate，不改变 ReportData/ReportSpec/Renderer/template authority。

## 后果

- 正面：只有真正缺失的 shape-required slot 才澄清；非业务请求与 Power BI 完全隔离；新增 shape 可由 deterministic DAX/Layer 3 独立验证。
- 代价：QueryPlan、Grounding、Memory compatibility、DAX grammar 与事实展示必须同步理解 shape；旧 payload 需以安全默认值兼容。
- 风险控制：benchmark 问题/答案不得进入 production lookup；路由 grammar 只表达通用能力句式，model-specific alias 必须绑定 schema fingerprint 并通过 runtime validation。

## Non-goals

MCP-driven ModelSemanticContext、任意 PBIX 自动语义适配、ontology/RAG/vector DB、MCP 性能架构、Provider、第二报表模板和 renderer 变更均不属于本 ADR。
