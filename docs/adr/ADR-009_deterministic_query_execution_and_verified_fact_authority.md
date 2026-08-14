# ADR-009 — Deterministic Query Execution and Verified Fact Authority

- **状态：** accepted
- **日期：** 2026-08-14
- **决策者：** 用户明确批准
- **适用阶段：** M2.6.3 Deterministic Execution & Verified Facts

---

## 背景

ADR-008 已把自然语言收口为 Canonical QueryPlan，但自由生成 DAX 仍可能加入未计划的 group-by、使用不可独立验证的 filter 形态或改写业务计算；即使 QueryResult 成功，自由 Answer/Report 也可能声称结果没有证明的数字、排名、趋势或原因。因此，语义正确还必须延伸到确定性执行与可证明事实边界。

## 决策内容

### 1. 唯一真实执行链

Real canonical path 固定为：

```text
Canonical QueryPlan
→ Deterministic DAX Builder
→ Independent Layer 3 Verifier
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet
→ fact-bounded Answer / ReportSpec
```

DeepSeek 不再拥有 Real DAX 生成权。历史 DAX service 可保留作 Mock/test compatibility，但生产 Real canonical path 的 DAX LLM 调用数必须为 0。

### 2. 受限确定性 DAX grammar

Builder 是普通代码，只接受 Canonical QueryPlan 与 runtime SemanticModelSchema。M2 MVP 只支持 Measure、Dimension、EQ Filter、resolved TimeRangeSpec、single-measure Sort 与 TopN；comparison 和非 EQ operator 受控拒绝。

所有对象重新从 runtime schema 唯一确认类型、可见性和 table ownership，DAX 只写 canonical runtime names。`QueryPlan.dimensions` 是 group-by 的唯一来源；filter field 不能被提升为维度。固定 grammar 使用稳定 literal serialization、固定 EQ/time pattern，并分别表达 TopN selection 和 final ORDER BY。

### 3. 独立 Layer 3

Layer 3 不以再次调用 Builder 并比较字符串作为唯一证明。独立 verifier 解析受限 grammar，逐项证明 model key、Measure references、exact group-by set、EQ field/value、time field/boundaries、TopN/direction、ORDER BY、无额外 business filter、无 raw-column reaggregation，并继续执行 DAX safety validation。任何不一致 fail closed。

### 4. VerifiedFactSet 是 factual claim authority

`VerifiedFactSet` 只能从 Canonical QueryPlan + QueryResult 确定性构建，并绑定 result ID、model key、source mode、source fields、row references/aggregation rule、filters、time range、row count、truncation 与 plan semantics。M2 支持 scalar、grouped rows、TopN/ranking order，以及由结果直接证明时的 min/max；趋势只有结构充分时才允许，comparison 和 causal explanation 不生成。

数值不得来自 LLM arithmetic、自然语言推算或 Answer text 反解析。

### 5. Answer / Report factual boundary

Real Answer 使用 deterministic fact-bounded sentence builder。任何数字、排名、极值、趋势、筛选或时间范围必须引用 VerifiedFactSet；无法验证的因果结论不输出。

ReportSpec 的 KPI、chart fields、table projection 与 insights 同样受 FactSet/QueryResult 约束。Chart 只能使用 verified result fields，Table 只能投影完整 QueryResult rows；无法安全证明的 insight 省略。Renderer 不获得扩大事实范围的权限。

### 6. Clarification 与提交边界

ADR-008 的 PendingClarificationContext 与 committed business Memory 严格分离。未补齐的 chain 不可执行、不可报告为 COMMITTED；完成后才形成当前 Grounded Delta，且 DAX、Layer 3、QueryResult、FactSet 与 factual output 全部成功后才提交正式 Memory。Real failure 禁止回退 Mock。

## 备选方案

- 继续依靠 DAX Prompt 与多次修复：拒绝，同一计划不能得到单一可审计执行形态。
- 用 Builder 自己重建 expected DAX 做唯一 Layer 3：拒绝，同一缺陷会自证正确。
- 仅在 Prompt 中要求 Answer 不幻觉：拒绝，不能形成 deterministic claim boundary。
- 构建通用 DAX compiler、知识图谱或 M3 renderer：拒绝，超出 M2.6.3 范围。

## 后果

- 正面：相同 Canonical QueryPlan 得到稳定 DAX；Layer 3 可独立拒绝额外语义；所有对外事实可追溯到 QueryResult。
- 负面：M2 grammar 有意受限；无法验证的分析与 insight 会被拒绝或省略，表达丰富度低于自由生成。
- 运维要求：schema fingerprint 必须与 glossary 同步；Real acceptance 必须观测 production TurnPipeline、actual committed Memory、LLM DAX call count、fallback/pollution 与 exact known-answer oracle。

## Non-goals

- comparison analytics、非 EQ filter 或通用 DAX compiler；
- M3 Renderer 正式开发、M4 persistence、M5 React；
- Remote MCP/OAuth 扩展；
- RAG、Vector DB、Knowledge Graph 或 ontology platform。

---

*最后更新：2026-08-14 | accepted*
