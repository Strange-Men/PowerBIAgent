# M5.9.3 — Business Semantic Parsing Correctness Closure

状态：**COMPLETE；发布以当前 main exact-SHA CI success 为证据**

基线：`main@b43f5268d288cab2864b2f7dbff04d4075950727`（M5.9.2 COMPLETE）

架构：ADR-008/009/014/015/016/018；ADR-017 runtime frozen；M5.10 NOT STARTED；M5 FINAL=false

## 本轮唯一范围

1. GROUPED / MEMBER_SET shape 冲突；
2. 显式月范围 deterministic normalization；
3. Completeness 对显式 time/ranking/filter/grouping 义务的完整检查；
4. grouping → filter firewall；
5. deterministic clarification reason 分类；
6. Sidebar conversation icon/layout 一致性；
7. 与以上问题直接相关的 semantic regression。

本轮不修改 M5.9.2 worker pool、retry、cancellation、singleflight，不新增 semantic/object/factual authority，不开始 M5.10。

## 顺序与完成证据

执行顺序固定为：production-path deterministic reproducer → 邻近 regression → 最小实现 → 跨域 deterministic matrix → DeepSeek-only Real acceptance → full gates → residual/git/secret audit → 白名单 commit/push → exact-SHA CI。

核心 invariant：

- grouping evidence 不得变成 filter 或 MEMBER_SET；
- MEMBER_SET 必须存在多个显式 member，并对全集做 runtime validation；
- bounded time 必须完整保留 start/end/grain；
- 任一显式义务未 canonicalize 必须 clarification + ZERO DAX/QueryResult/factual Memory commit；
- ranking 不得丢失 measure/dimension/sort/N；
- Sidebar normal/failed/processing 与长短标题使用同一固定 icon geometry。

Real 只运行 DeepSeek；Kimi 仅复用既有 provider abstraction/mock/contract regression。最终证据必须包含 CanonicalPlan、DAX scope、QueryResult、VerifiedFactSet、Answer/Table 一致性以及 automation-owned residual=0。

## 完成证据

- 80-case 跨 Sales/Education/Inventory/Logistics deterministic matrix 与 production-path API 覆盖 grouping/MEMBER_SET、弱 filter firewall、月范围 separator/NFKC、端点丢失、中文/数字 TopN；
- DeepSeek-only `PowerBIAgent_M3_Rich_Test` 9/9 场景通过，8 个真实 DAX witness 均与 CanonicalPlan deterministic rebuild 一致，QueryResult→VerifiedFactSet 与 StructuredPresentation rebuild 一致，known+unknown member ZERO DAX；
- Sidebar ready/failed 实际浏览器 wrapper/SVG geometry 均为 16×16，长标题 ellipsis 且无裁切；processing 复用同一 wrapper 并由组件 regression 覆盖；
- M5.9.2 worker/session/cache/singleflight/cancellation frozen regression 128 PASS；Semantic Compatibility 773 PASS；backend 2566 PASS / 1 manual-real SKIP；frontend 90 PASS + typecheck/lint/build；Golden 11 PASS / 1 manual-real SKIP；五项治理、compileall、diff-check 与 automation-owned residual 均通过。

## M5.9.4 后续规划

M5.9.4 = **PLANNED / NOT STARTED**。它才负责大规模业务自然语言组合压力测试、covering-array/property/metamorphic generation、数万至十万级 deterministic semantic harness，以及 DeepSeek-only Real LLM stress。Kimi 不重复 Real token 压力测试，只保留 provider abstraction/mock/contract。完成 M5.9.3 后停止，不自动启动 M5.9.4。
