# M5.8.5 — Semantic Completeness + Result Inspection + Presentation Truth

状态：COMPLETE。基线 `m5/rebuild` / `ea0f65c3bbf31673728178f03d7487f72519e6a9`；M5.8.4 COMPLETE。本提交 exact-SHA CI 为发布证据。M5.9/M5.10 NOT STARTED，M5 FINAL=false。

## 已确认根因

1. Grounding 输出 resolved delta/clarification，但没有本轮业务义务的 closed-world coverage witness；弱草稿或 member discovery 丢条件后仍可能看起来是完整 scalar。
2. StateTransition 与 ValidationService 只有局部槽位约束，没有八种 Query Shape 的统一完整性 Gate。
3. QueryResult 只验证 row/column/source 结构；ranking/trend/distinct/scope 的语义一致性在 VerifiedFactSet 前没有 deterministic inspection。
4. Pending abandon 与 inheritance relation 使用不同 cue/规则；显式 fresh 没有统一结构化优先级。AnswerBuilder 又把 scope 作为尾部附注，Presentation 复制返回顺序，导致上下文与展示不稳定。

## 顺序

1. P0 Cold Start、ADR-016/spec、现有调用链与根因审计。
2. P1 production-path failure reproducers：未知 modifier、known+unknown set、残缺 ranking、错误 TopN/order、trend 越界、fresh pending/Memory 污染、scope 缺失、table/chart order。
3. P2 SemanticObligationCoverageGate 与审计合同。
4. P3 CanonicalShapeCompletenessGate 与 DAX 前 fail-closed wiring。
5. P4 ResultSemanticInspectionGate、TOPN deterministic tie boundary 与 facts 前 wiring。
6. P5 shared TurnRelationEvidence、Pending/fresh 与 StateTransition 修复。
7. P6 DeterministicQueryScopeDescriptor、AnswerContext/evidence 与 PresentationDataset 排序投影。
8. P7 500–1000+ seeded cross-domain/property/invariant case；schema/member/date/context mutation 与 provider/model isolation。
9. P8 targeted、Semantic Compatibility、backend、Golden、frontend tests/typecheck/lint/build、全部治理、compileall、diff check。
10. P9 三 PBIX × DeepSeek/Kimi Real 行为矩阵、cold/warm/4-way 仅观测、browser/validation/temp residual=0。
11. P10 文档/版本同步、白名单 commit/push、exact-SHA CI completed/success。

## Real 合同

三份 PBIX 为 Rich Sales、原 M3 Test、Logistics Test。每份使用自身 runtime metadata 和领域问法，不给 Logistics 增加中文 synonym 或 PBIX-specific override。两个 Provider 都覆盖 scalar、time/filter follow-up、measure replace、grouped、Top1/Top3、trend/bounded trend、entity list、member set、known/unknown/mixed member、fresh/follow-up/replace、Report→Data→Report、provider switch 与 A→B→C→A。

每轮仅记录安全 metadata：user text、obligation status、grounded delta、inheritance decision、canonical plan、DAX yes/no、QueryResult shape/order digest、inspection、effective scope 与 final answer。真实行、Secret、完整 prompt/response 不落盘、不提交。

## 完成条件

所有本地与 Real Gate、residual=0、版本/治理文档、白名单 commit/push、新 exact SHA 的 PowerBIAgent Validation completed/success、local SHA == origin SHA、working tree clean 同时成立后，M5.8.5 COMPLETE=true。M5.9/M5.10 仍为 NOT STARTED；M5 FINAL=false。

## 最终证据

- Targeted correctness 邻近回归 475 PASS；domain-independent stress 为 2,304 logical cases，覆盖 coverage、shape、ordering、scope、fresh/follow-up/replace、member set、provider consistency 与 multi-model isolation。
- Rich Sales、M3 Test、Logistics Test 使用同一行为模板映射各自 runtime schema，DeepSeek/Kimi 的 canonical plan/result consistency 通过；unknown 与 known+unknown member 均 ZERO DAX；Logistics date/grouped/TopN/trend/fresh 与 A→B→C→A 通过。诊断批次失败真实保留，最终修复最小复跑 6/6、business/temp residual=0。
- Semantic Compatibility 743 PASS；backend 2397 PASS / 1 SKIP；Golden 11 PASS / 1 manual-real SKIP；frontend 87 PASS 与 typecheck/lint/build PASS；Repository Safety、Architecture、Error Ledger、Documentation/Artifact Governance、compileall、diff-check 全绿。
- 单轮外部 Provider 冷启动约 56s，仅作为性能观察；未做 M5.9 优化。Settings.version=M5.8.5，`.env` 未读取/打印/修改。
