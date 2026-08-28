# M5.8.1 — 前置性能加速与本地 MCP 会话复用

> 状态：COMPLETE
> 基线：`m5/rebuild` / `117cafa0d0669d8f1d63c66cd9f87328ab54defa`
> M5.8 已完成并冻结；M5 FINAL=false。

## 目标

在相同输入和相同 PBIX 状态下保持 canonical plan、DAX、QueryResult、Memory、Report 与用户可见业务结果完全不变，仅降低重复 Local MCP startup、tool discovery、Desktop discovery、compatibility/schema/member metadata 读取成本。

## 允许范围

- 使用 `time.monotonic()` / `time.monotonic_ns()` 记录 total turn、intent LLM、MCP startup、tool discovery、Desktop discovery、compatibility probe、schema、semantic catalog、member lookup、grounding、QueryPlan、DAX build、DAX execution、answer/presentation 与 persistence。
- Backend lifetime 内持有一个 application-owned read-only Local MCP stdio worker/client，并在 shutdown 清理。
- tool discovery 在 MCP session generation 内复用。
- discovery、成功 compatibility probe 与 schema 使用短 TTL、bounded、identity-scoped cache。
- member lookup 使用短 TTL、bounded cache，key 至少覆盖 semantic model identity、schema fingerprint、table、field、normalized request 与 limit。
- startup、discovery、probe、schema 与 identical member lookup 使用 per-key async singleflight。
- 使用一个最小 bounded semaphore 保护 MCP operation 并发。

## 不变量

- 每次连接或使用所选模型前仍重新枚举并精确匹配 opaque PBIX identity；禁止 `instances[0]`、名称猜测或 fallback 其他 PBIX。
- Desktop process/start-time/data-source identity、selected PBIX 或 MCP session generation 变化，以及 validation failure，都必须失效相关 cache。
- cache 只保存可重新验证的 metadata/member lookup，cache hit 与 runtime read 语义等价；cache 永不成为新的 semantic authority。
- 不缓存 Answer、Report HTML、LLM semantic answer、Canonical QueryPlan、DAX、DAX execution result、QueryResult 或 VerifiedFactSet。
- 不引入 Redis、distributed/cross-process cache、复杂 queue/backpressure、20/50/100 production acceptance、large fault matrix、long soak 或 Remote MCP performance。
- 不修改 Intent、Grounding、Time/Member/TopN、StateTransition、Deterministic DAX、VerifiedFactSet、M5.8 Provider、Report factual authority或前端业务 UX。

## 实施顺序

1. 记录未优化的 cold/warm baseline 与阶段分布。
2. 建立 session manager 生命周期、generation 与 clean shutdown。
3. 增加 session tool cache、identity-scoped discovery/probe/schema cache。
4. 增加 schema-fingerprint-scoped member cache。
5. 增加 singleflight 与最小 semaphore。
6. 完成 session/PBIX/stale/expiry/failure/cancellation 回归。
7. 完成 focused Real、跨域、全量 gates、人工验收、文档与提交。

## 验收

- 冷启动、首个普通 scalar、立即第二问、相同 schema 不同问题、member lookup、trend、顺序 10 问、小并发分别记录 total/MCP/LLM/DAX/cache/session 指标。
- 20 个相同 schema 请求与 20 个相同 member lookup 只触发约 1 次 underlying read。
- leader failure 不写 cache；timeout/cancellation 不永久占用 key；后续 retry 可恢复。
- PBIX A/B、Desktop restart、MCP crash、backend shutdown 均通过 fail-closed/clean-close 验证。
- Semantic Compatibility、backend full pytest、Golden、frontend tests/typecheck/lint/build、全部 governance 与 Real Rich PBIX correctness/residual/remote CI 全部通过后才可标记 COMPLETE。

## 完成证据

- 优化前 metadata cold/warm：discovery `6297/7860ms`、schema `9078/10172ms`、member `19422/20890ms`、DAX `11047/8094ms`；优化后 fresh sample：discovery `3782/0ms`（startup `3406ms`）、probe `1468/157ms`、schema `422/156ms`、member `515/172ms`、DAX `485/515ms`。
- 正式 full-turn 冷启动旅程 `18172ms`；外部 LLM 波动下首两轮 `9250/17922ms`；稳定热态连续 10 轮 `13000ms`（单轮 `1000–1891ms`），4 路小并发 `3719ms`。cache hit/session reuse 在稳定 warm turn 均为 `1.0`。
- Local MCP focused `91 passed`；Semantic Compatibility `306 passed`；backend `1950 passed, 1 skipped`；frontend `86 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Repository Safety、Architecture、Error Ledger、Documentation/Artifact Governance、compileall 与 diff check PASS。
- Rich PBIX 双 Provider correctness、multi-turn、report 与并发/切换回归通过，canonical plan/result digests 一致，residual=0。无 Redis、无 factual/semantic result cache、无 M5.8.2 或完整 M5.9 范围扩张。
