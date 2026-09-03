# ADR-016 — Semantic Completeness、Result Inspection 与 Presentation Truth

- **状态：** accepted
- **日期：** 2026-09-02
- **决策者：** 用户明确批准 M5.8.5
- **适用阶段：** M5.8.5；不启动 M5.9/M5.10

## 背景

M5.8.4 已能在现有 runtime Catalog 中跨语言绑定对象和成员，但仍缺少四个端到端 correctness invariant：当前输入中真正影响结果的语义修饰可能没有形成可审计的最终状态；不同 Query Shape 的完整槽位没有统一硬校验；Power BI 返回结果只经过结构校验，尚未验证 ranking/trend/distinct 的 canonical 语义；Answer 与 table/chart 没有共同的确定性 effective scope 与排序合同。

## 决策

1. 唯一 authority 链保持不变：QuestionRouter → runtime SemanticModelSchema / ModelSemanticContext → existing SemanticCatalog / Grounding → StateTransition → CanonicalQueryPlan → deterministic DAX / Layer 3 → Power BI → QueryResult → VerifiedFactSet → Answer / Presentation。
2. Grounding 后建立本轮 `SemanticObligationSet`。义务只来自 Router shape、当前 Grounding 结果、runtime member validation、确定性 time/ranking/clear/fresh evidence，以及受控的当前 modifier residue；不要求所有 token 绑定，不创建对象，不替代 Catalog。每项终态只能是 `RESOLVED`、`EXPLICITLY_CLEARED`、`UNSUPPORTED` 或 `NEEDS_CLARIFICATION`。存在未闭合义务时在 DAX 前 fail closed。
3. StateTransition 后执行 `CanonicalShapeCompletenessGate`。SCALAR、ENTITY_LIST、GROUPED、RANKING、MEMBER_SET、FILTERED_AGGREGATION、TREND、BOUNDED_TREND 分别验证 required slots；不得把残缺 ranking/member/time shape 降级为更宽查询。
4. QueryResult 结构验证后、VerifiedFactSet 前执行 `ResultSemanticInspectionGate`。它验证 canonical ranking row count 与单调顺序、trend 时间升序与 bounded range、entity distinct，以及 result/model/plan scope lineage。失败是 internal semantic consistency failure，不进入 Answer、Presentation 或 Memory commit。
5. TOPN selection 与最终排序继续分离。Deterministic DAX 必须以 canonical metric sort 选取并以 query `ORDER BY` 返回同一主顺序；必要的稳定次级键只解决 ties 的确定性边界，不升级为业务名次。
6. `DeterministicQueryScopeDescriptor` 只消费最终 CanonicalQueryPlan、canonical display binding 与确定性 formatter，输出 measure、filter、time、grouping、ranking/top_n/sort 的 effective scope。Answer 必须显式包含该 scope；LLM 不得决定、删除或改写 scope truth。
7. PresentationDataset 是 display-only projection。显式 canonical sort 原样保持；普通 categorical grouped + 单指标可按 metric DESC 做展示投影；temporal trend 始终 time ASC。table 与 chart 只引用同一 dataset；QueryResult、VerifiedFactSet、数值与 provenance 不修改。
8. fresh/follow-up/replace 使用同一 bounded `TurnRelationEvidence`。显式 fresh cue 的优先级高于 PendingClarification、committed Memory 和 LLM relation draft；fresh 清除不兼容旧槽，follow-up 只补真正省略且兼容的槽，replace 只替换明确槽。
9. Provider、M5.8.1 MCP session/cache/singleflight/concurrency、Report template/renderer、resource lifecycle 与 Remote MCP 均冻结。不得新增第二套 Model、Catalog、Planner、Grounding、Memory 或 LLM DAX。

## 验收

- 永久 stress/property/invariant suite 覆盖多 shape、known/unknown、fresh/follow-up/replace、provider/model switch 与 schema/member/date/context mutation，至少数百个确定性 case。
- 三份真实 Desktop PBIX 分别按领域映射运行同一语义行为模板，DeepSeek/Kimi 都必须证明 canonical plan、facts、scope 与排序合同一致；unknown 与 known+unknown 成员必须 ZERO business DAX。
- Semantic Compatibility、backend/frontend/Golden/governance、compileall、diff check、residual 与 exact-SHA CI 全部通过后才可声明 M5.8.5 COMPLETE。

## 后果与边界

义务或 shape 证据不足会增加澄清，但不会扩大查询范围。Result Inspection 可能拒绝 Power BI 返回的语义不一致结果，但不得修值或静默重排事实。M5.9/M5.10 保持 NOT STARTED，M5 FINAL=false。

## 实施状态

M5.8.5 已完成实现与本地/Real 验收：2,304-case invariant stress、三 PBIX × DeepSeek/Kimi 定点链、backend 2397 PASS / 1 SKIP、Semantic Compatibility 743 PASS、frontend 87 PASS、Golden 与全部治理门禁通过，automation-owned residual=0。发布以本提交 exact-SHA CI completed/success 为最终证据。
