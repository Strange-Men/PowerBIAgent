# M5.9.4 — Business Language Stress 与泛化验收

状态：**COMPLETE**（发布以当前 main exact-SHA CI success 为证据）

基线：`main@ef1033ac3c5469adf4d1477aefb66bf1ee55949b`（M5.9.3 COMPLETE）

架构：ADR-008/009/014/015/016/018；ADR-017 runtime frozen；M5.10 NOT STARTED；M5 FINAL=false

## 显式继续授权记录

用户在本轮任务中明确要求：“在进入 M5.10 前，对当前已支持的 Power BI 业务问答能力做系统化自然语言组合压力测试，主动发现并收口潜在语义解析缺陷。”该授权仅用于 M5.9.4 内有 deterministic reproducer 的最小 forward-fix；ERR-594-011 在两次未完整覆盖 selector 分支的修复尝试后，仍须继续收口到同一 COMPLETE 条件，不授权架构扩张或 M5.10 工作。

## 本轮唯一范围

1. 建立可复用、固定 seed、可复现的组合式 Business Language Stress Harness；
2. 用 pairwise / bounded t-way 覆盖八种 Query Shape 与跨域语义因素，不做无意义全笛卡尔积；
3. 建立等价表达 property、显式 modifier fail-closed invariant 与 metamorphic tests；
4. 输出 total/pass/fail 及按 shape、semantic factor、language pattern 分类的安全摘要；
5. 对失败 case 做确定性 shrinking，保存不含 secret、连接属性或 PBIX 路径的最小 descriptor；
6. 仅在 reproducer 证明真实 production bug 后做最小 forward-fix，并加入永久 regression corpus；
7. 从 deterministic corpus 选择 100—300 个高风险代表问题做 DeepSeek-only Real stress；Kimi 仅保留既有 provider abstraction/mock/contract；
8. 完成跨 Sales、Education、Inventory、Logistics 的 deterministic 验收、full gates、residual=0、白名单 commit/push 与 exact-SHA CI。

禁止新增业务能力、按业务词或失败句式修补生产规则、放松 runtime member validation / Semantic Completeness、partial execute known+unknown、缓存 QueryResult/VerifiedFactSet/DAX result，或修改 M5.9.2 runtime、M5.10 report/template、Remote MCP、Entra、PostgreSQL、Deployment。

## Harness 设计合同

### 1. Semantic case descriptor

每个 case 只记录安全、领域无关或 fixture-owned 信息：seed、case id、domain fixture id、shape、measure/dimension/filter/member/time/ranking/turn-relation factors、language pattern、expected canonical digest 与执行预期。失败输出不得包含 secret、connection string、runtime endpoint、PBIX 路径、完整 Provider prompt 或原始响应。

### 2. Covering strategy

生成器使用稳定排序的 factor values、固定 seed 和确定性 greedy pairwise covering；对高风险交互追加 bounded 3-way rows：

- shape × dimension cue × member cue；
- filter × grouping × multiple member；
- time × trend × turn relation；
- ranking × dimension × number form；
- known/unknown × conjunction × member field；
- fresh/follow-up/replace × committed state × explicit clear；
- schema relationship × duplicate field name × technical-key/label peer；
- model/schema switch × conversation state × language mix。

基础 covering rows 再与稳定的 wording/noise/punctuation/order transforms 做 bounded 扩展，目标 deterministic logical cases 不少于 50,000；若运行成本失控，最低不得少于 20,000。

### 3. Three-layer verification

- A — Language/shape：真实 `QuestionRouter`、deterministic temporal parser 与 turn-relation classifier；
- B — Semantic/canonical：现有 Catalog/Grounding/Obligation/StateTransition/Shape Gate，验证 grouping/filter firewall、member 全集、time endpoints、ranking slots 与 Memory inheritance；
- C — Execution/facts：CanonicalPlan → deterministic DAX → independent verifier，以及 synthetic QueryResult → Result Inspection → VerifiedFactSet/scope 一致性。不得执行真实 DAX 来跑数万例。

### 4. Required invariants

1. 等价问法得到等价 QueryShape / canonical semantics；
2. 礼貌词、标点和无业务意义修饰不改变 CanonicalPlan；
3. grouping 与 explicit filter 不互相转换；
4. explicit member 只绑定正确 runtime field；
5. bounded time 保留 start/end/grain；
6. ranking 保留 measure/dimension/N/sort；
7. unknown、ambiguous、known+unknown 都 clarification + ZERO DAX；
8. 任一 explicit modifier 不得静默丢失；
9. fresh 不继承旧业务槽，follow-up/replace 只继承允许状态；
10. model/schema switch 不得 cross-model bleed；
11. DAX 必须可由 CanonicalPlan 确定性重建；
12. QueryResult、VerifiedFactSet 与 effective scope 必须一致。

### 5. Failure lifecycle

失败必须先 shrink 为最小可复现 descriptor，再记录 expected/actual、root-cause layer、P0/P1/P2、minimum fix。根因分类固定为 Router/Query Shape、Intent weak draft、SemanticCatalog eligibility、Grounding object selection、member lookup、time normalization、turn relation、Semantic Completeness、Canonical Shape、DAX build/verifier、Result Inspection、Memory transition、Presentation 或 Provider protocol。没有确定性 reproducer 不修改 production。

## Checkpoints

执行顺序固定为：

S1 contract / baseline → S2 generator + reporter → S3 language/shape 20k+ failure run → S4 shrinking + regression corpus → S5 minimal production fix（仅如有）→ S6 semantic/canonical properties → S7 DAX/result/fact invariants → S8 50k+ cross-domain stress → S9 focused semantic + permanent Semantic Compatibility → S10 DeepSeek-only Real 100—300 → S11 backend/frontend/Golden/governance/full gates → S12 residual/git/.env audit → S13 final docs → whitelist commit/push → exact-SHA CI。

任一未处理 P0/P1/P2、generated failure、canonical mismatch、silent modifier loss、incorrect DAX execution、unknown/ambiguous violation、cross-model bleed 或 automation residual 都阻止 COMPLETE。若修复要求大规模 Semantic Architecture 重构，立即停止并报告，不在 M5.9.4 扩域。

## Completion wording

允许的最终表述仅为：

> 系统化覆盖当前产品支持的业务语义组合空间及主要语言变体。

不得声称覆盖所有自然语言。只有 50k+ deterministic stress（最低 20k）、DeepSeek-only Real representative stress、全部 regression/full gates、residual=0、clean local main==origin/main 与 exact-SHA CI completed/success 同时成立，才可标记 M5.9.4 COMPLETE=true。完成后停止；M5.10 NOT STARTED，M5 FINAL=false。

## 完成证据

- **Harness：** `backend/tests/stress/business_language_stress.py` 与 `scripts/run_business_language_stress.py` 使用固定 seed `59420260909`、稳定 factor 顺序、greedy pairwise、bounded 3-way 与 seeded unique sampling；支持安全 descriptor、最小化失败问题、按 shape/semantic factor/language pattern 聚合。
- **覆盖：** 51,200/51,200 PASS；Sales/Education/Inventory/Logistics 各 12,800，SCALAR/GROUPED/RANKING/TREND/BOUNDED_TREND/ENTITY_LIST/MEMBER_SET/FILTERED_AGGREGATION 各 6,400。factor cardinality 覆盖 register/courtesy/noise/punctuation/order/relation/object surface、filter/member/time/ranking/grouping 等 23 个维度。
- **Property / metamorphic：** 3,438 groups、50,746 variants；semantic execution cases 1,986，unknown/ambiguous cases 20,438。canonical mismatch、silent modifier loss、incorrect DAX execution、unexpected clarification/execution、ZERO-DAX invariant failure、cross-model bleed 均为 0。
- **缺陷：** ERR-594-001—014 共 14 项（P0=0、P1=10、P2=4），全部有 reproducer、root cause、最小修复与 focused regression；未处理 P0/P1/P2=0。修复仅触及通用 shape/time/relation/Coverage/Grounding 边界，没有新增业务词 authority、放松 runtime member validation 或扩大到 M5.9.2/M5.10。
- **DeepSeek Real：** `PowerBIAgent_M3_Rich_Test` + `PowerBIAgent_M3_Test` 完成 108/108：104 completed、4 clarification + ZERO DAX/Memory commit，八 shape、24 metamorphic groups、双 PBIX、多轮 KEEP/REPLACE/follow-up、unknown/known+unknown 与 cross-model isolation。Canonical、deterministic DAX rebuild、QueryResult、VerifiedFactSet、Presentation 全链一致；business/temp residual=0。一次前序完整 run 的外部 request deadline 504 被如实判 FAIL，同 case 单例正常后仍从头重跑，最终证据不拼接、不提高 timeout。
- **Fresh gates：** stress-focused 52 PASS；Semantic Compatibility 774 PASS；backend 2596 PASS / 1 manual-real SKIP；Golden 11 PASS / 1 manual-real SKIP；frontend 90 PASS + typecheck/lint/build；Repository Safety 372、AI Error Ledger 81、Architecture 135、Documentation/Artifact Governance、compileall 与 diff-check PASS。
- **范围结论：** 系统化覆盖当前产品支持的业务语义组合空间及主要语言变体。Kimi 只运行冻结的 mock/contract/full regression，不做重复 Real token stress。M5.10 NOT STARTED，M5 FINAL=false。
