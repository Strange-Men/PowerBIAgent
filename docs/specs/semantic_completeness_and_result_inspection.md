# M5.8.5 Semantic Completeness + Result Inspection + Presentation Truth

## 目标与非目标

本规范在现有唯一语义链增加四个 correctness invariant：Semantic Obligation Coverage、Canonical Shape Completeness、Result Semantic Inspection、Deterministic Query Scope。它不重写 M5.8.4，不创建并行语义 authority，不修改 Provider/MCP performance/Report template，也不缓存 QueryResult、facts 或 final answer。

## 1. Semantic Obligation Coverage

`SemanticObligation` 包含 kind、status、source 与安全 evidence。kind 至少覆盖 measure、dimension/grouping、filter/member、time、ranking/top_n/sort、turn relation 和 explicit clear。status 只能为：

- `RESOLVED`：已由 runtime/Catalog/member/time/analysis authority 唯一证明；
- `EXPLICITLY_CLEARED`：用户明确清除该修饰；
- `UNSUPPORTED`：现有 capability 明确不支持；
- `NEEDS_CLARIFICATION`：当前明确要求存在，但不能完整绑定。

Gate 只追踪会改变业务结果的 semantic modifier。不得把所有自然语言 token 当义务；不得将 polite text、问句词或 Router grammar 当业务对象。显式 member set 的每一项必须完整 runtime validation，任何未知项使整个 set 停止。当前 modifier residue 只能作为 fail-closed 证据，不能生成字段或 member。

## 2. Canonical Shape Completeness

| Shape | 必需合同 |
|---|---|
| SCALAR | measure；无 ranking residue |
| ENTITY_LIST | dimension；无 measure |
| GROUPED | measure + dimension |
| RANKING | 单 measure + dimension + sort + top_n |
| MEMBER_SET | dimension + authoritative same-field filter + complete member set |
| FILTERED_AGGREGATION | measure + authoritative filter binding |
| TREND | measure + temporal grouping |
| BOUNDED_TREND | measure + temporal grouping + bounded time range |

残缺 plan 返回 clarification/validation failure 并保持 ZERO DAX。Gate 只验证 StateTransition 产出的 CanonicalQueryPlan，不补槽、不选对象、不降级 shape。

## 3. Result Semantic Inspection

Inspection 位于 QueryResult structure validation 与 VerifiedFactSet 之间：

- RANKING：Top1 exactly one row；TopN row_count <= N；metric 按 canonical direction 单调；第一行是返回集合中的 canonical extreme；
- TREND：temporal key 非降序；BOUNDED_TREND 的每个时间 key 位于 canonical range；
- FILTER/TIME：inspection witness 绑定 exact plan scope、DAX/Layer3 pass、result identity 与 model identity；
- ENTITY_LIST：返回投影保持 distinct；
- 任意失败：`result_semantic_consistency_failed`，ZERO facts/Answer/Presentation/Memory commit。

Inspection 不修改 rows、values、columns 或 provenance。

## 4. Query Scope 与排序

scope descriptor 的 canonical 构成顺序为 time → filters → grouping/ranking → measure。所有字段显示名来自当前 model/object/schema-scoped localization，值由 deterministic formatter 处理。descriptor 必须进入 AnswerContext/evidence 与最终可见 Answer。

排序合同：

1. explicit canonical sort：DAX selection/order → QueryResult → inspection → table/chart，保持原 order；
2. temporal trend：display 始终 time ASC；
3. categorical grouped + 单 measure 且无 explicit sort：PresentationDataset 可按 metric DESC 排序；
4. table/chart 共用同一 PresentationDataset；facts 和 QueryResult 不变。

## 5. Turn relation

有限 deterministic fresh cues 包含“独立问题 / 新问题 / 重新开始 / 忽略之前 / 单独问 / 重新分析”及等价的受控英文 cue。`TurnRelationEvidence` 在 PendingClarification 与 TurnInheritancePolicy 之间共享；explicit fresh 优先于旧 pending、Memory 和 LLM draft。禁止为业务对象继续扩张 turn-relation regex。

## 6. 失败与审计

execution audit 至少记录 obligations、grounded delta、inheritance decision、canonical plan、DAX executed、result inspection、effective scope、result row/order digest。不得记录 Secret、完整 prompt、原始 Provider response 或真实结果行。

## 7. 最终验收

本规范已由 2,304 个 domain-independent stress case、三 PBIX × DeepSeek/Kimi Real 高风险链、A→B→C→A isolation、Semantic Compatibility 743、backend 2397 PASS / 1 SKIP、frontend 87、Golden 与全部 governance gate 验证。unknown/known+unknown 均 ZERO DAX；TopN、trend、scope、fresh 与 table/chart shared-order contract 均有 permanent regression。M5.9/M5.10 NOT STARTED，M5 FINAL=false。
