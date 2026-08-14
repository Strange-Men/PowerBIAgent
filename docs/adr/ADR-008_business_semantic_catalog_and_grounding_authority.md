# ADR-008 — Business Semantic Catalog and Grounding Authority

- **状态：** accepted
- **日期：** 2026-08-13
- **决策者：** 用户明确批准
- **适用阶段：** M2.6.2 Business Semantic Grounding Foundation

---

## 背景

M2.6.1 的真实验证证明，仅有 Power BI runtime schema 和 QueryPlan/DAX 的结构合法性不足以保证业务正确。当前模型的 description 为空、未提供可依赖的 synonyms 或 linguistic metadata 时，诸如“销量”一类稳定业务术语无法在 `Total Sales` 与 `Total Quantity` 之间由 schema 独立消歧。Intent 和 QueryPlan LLM 若重复解释这些术语，即使 Layer 2、DAX 与 QueryResult 均合法，也可能提交业务含义错误的状态。

## 决策内容

### 1. 业务语义 Source of Truth

Canonical QueryPlan 的业务事实只来自以下权威数据：

1. runtime `SemanticModelSchema` metadata；
2. 与 `semantic_model_key` 严格绑定的 model-scoped Business Glossary；
3. 经 ToolGateway → PowerBIAdapter 获取的 runtime bounded member values；
4. 后端固定规则和注入 clock 形成的结构化时间范围。

Glossary 是业务定义数据，不是 Prompt example。加载时必须校验 model key、runtime 对象存在性、对象类型、表归属、隐藏状态、alias 非空与 alias 冲突。未知、隐藏或类型错误对象拒绝加载；冲突 alias 不得静默选择。

Friendly `semantic_model_key` 不能单独证明当前 Desktop 模型身份。Glossary 还必须绑定由 visible tables、columns/types、measures/types/expressions 与 active relationship endpoints 稳定排序、规范序列化后计算的 SHA-256 `schema_fingerprint`。端口、路径、session ID、业务行数据与展示 description 不进入 fingerprint。key 或 fingerprint 不匹配必须 fail closed。

### 2. Intent 与 QueryPlan LLM 的权限

Intent 继续负责任务分类和基础语言提取，`detected_measures`、`detected_dimensions`、`detected_filters` 只允许作为当前输入中的 weak signal 或 diagnostic，不是 canonical semantic authority。

QueryPlan LLM 输出仅为语言理解草稿。它不能定义 Measure、Dimension、Filter Field、member 或 Date Field，也不能覆盖 Grounding 结果。确定性 Grounding 无法唯一处理且当前输入确实表达了该槽位时，只允许一次基于候选 ID 的 bounded selection；输出只能是候选 ID、`AMBIGUOUS` 或 `UNRESOLVED`。

### 3. Grounding 是 canonical semantic authority

Grounding 按以下顺序将当前明确表达映射到 runtime 对象：canonical exact、unique normalized alias、unique runtime description、bounded candidate selection；否则 clarification。

每个 semantic slot 区分：

- `NOT_MENTIONED`：当前轮未表达新要求；
- `RESOLVED(X)`：权威数据唯一解析为 X；
- `AMBIGUOUS`：当前轮已表达但有多个合法候选；
- `UNRESOLVED`：当前轮已表达但无可靠目标；
- `EXPLICIT_CLEAR`：当前轮明确取消该槽位。

`NOT_MENTIONED` 不等于 `UNRESOLVED`，未提及的槽位不得触发 clarification。

Filter member 必须在已 Ground 的 field 上执行 read-only、bounded runtime lookup；不得将用户原字符串直接写入 Canonical QueryPlan。时间语义必须绑定唯一 runtime Date field，并转为 `TimeRangeSpec`；多个合理 Date fields 时 clarification。

### 4. StateTransition 是 deterministic state change authority

Grounding 只回答当前用户明确表达的语义；StateTransition 只把 Grounded Semantic Delta 与最近一次 successful committed state 合并：

- 普通槽位：`KEEP` / `REPLACE` / `CLEAR`；
- Filter：`KEEP` / `ADD` / `REPLACE_SAME_FIELD` / `REMOVE` / `CLEAR`。

当前明确且已 Ground 的语义优先于 committed state；未提及的槽位从 committed state 继承。`AMBIGUOUS`、`UNRESOLVED`、clarification、QueryPlan/DAX/QueryResult failure 均不得提交或污染后续轮次。

### 4.1 多轮 clarification 的非提交上下文

一次澄清可以只补齐一个已权威解析的 slot。未完成链使用 Repository 内、由 TurnPipeline 统一读写的 `PendingClarificationContext`，只保存 chain identity、已解析 slots、missing slots、固定 analysis intent、model/fingerprint 与 provenance；它没有 `MemoryStatus`、DAX、QueryResult 或 commit evidence，不能进入 committed version chain，也不能作为可执行 QueryPlan。

槽位优先级固定为 current explicit grounded semantic > pending clarified semantic > 允许继承时的 last successful committed semantic。只有 missing slots 为空才形成完整 Grounded Delta 进入正常 Layer 2/执行链，且仍须完整成功后才能提交正式 Memory。歧义、未解析 member、下游失败、明确放弃或不兼容请求均不得把 pending 误提交或污染 last successful state。

### 5. 验收边界与后续验证职责

Grounding + StateTransition 是 canonical semantic slots 的唯一写入者。既有 Layer 2 继续验证 runtime 对象存在性、对象类型、隐藏状态、关系可达性与已支持能力，但不猜用户业务含义。DAX、Answer、ReportSpec 与 Memory 只能消费已形成的 Canonical QueryPlan。

M2.6.2 correctness boundary 是 `Natural Language → Canonical QueryPlan → Layer 2`。Real acceptance 必须观测正式 Pipeline 形成的 intermediate artifacts；不得从 expected 直接构造 QueryPlan，也不得使用 Mock schema/member。DAX 与 Layer 3 继续原样运行并记录 downstream status，但其生成正确性属于 M2.6.3：`Canonical QueryPlan → Deterministic DAX → Verified FactSet`。

## 备选方案

- 继续增强 Prompt 让 DeepSeek 更会猜：拒绝，无法形成稳定业务事实来源。
- 引入 Vector DB、Embedding DB、RAG、Knowledge Graph 或 Ontology Service：拒绝，超出 MVP 且不能替代 model/runtime 绑定校验。
- 新建第二个 Agent、Pipeline 或 LLM Judge：拒绝，违反 ADR-005 的确定性控制面。
- 将全部业务 alias 写入生产 Python：拒绝，业务定义应保存在 model-scoped glossary 数据中。

## 后果

- 正面：业务术语、runtime 对象、member、日期字段和多轮状态变更均可追溯；LLM 输出合法但业务错误的概率入口被隔离在 canonical 边界之外。
- 负面：每个真实模型必须维护并验证 glossary；member lookup 会增加一次有界只读 Power BI 调用；歧义会降低功能覆盖并要求用户澄清。
- 运维要求：模型 schema 或 glossary 变化后必须重新通过绑定校验；Real member lookup 失败不得回退 Mock。

## Non-goals

- Deterministic DAX Builder 与 DAX AST；
- Verified FactSet 与 Answer factual grounding 重构；
- RAG、向量检索、知识图谱或 ontology；
- M3 报表正式渲染、M4 持久化 Memory、M5 React；
- Remote MCP 生产化。

---

*最后更新：2026-08-13 | accepted*
