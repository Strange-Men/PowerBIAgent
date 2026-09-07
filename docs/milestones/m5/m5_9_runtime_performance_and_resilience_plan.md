# M5.9 — Performance / Concurrency / Resilience / Cloud-Ready Runtime

状态：**COMPLETE**
基线：`main@e8a79c3edcd7f648600bd4aa271d084d65cb62a1`（CI #51 exact-SHA success）
架构：`ADR-017`；M5.8.5 correctness frozen；M5.10 NOT STARTED；M5 FINAL=false

## 不可变 authority

`QuestionRouter → Intent weak draft → Template Gate → ToolGateway → PowerBIAdapter → runtime SemanticModelSchema → ModelSemanticContext → optional exact override → SemanticCatalog/Grounding/runtime members → StateTransition → CanonicalQueryPlan → deterministic DAX → Power BI → QueryResult → Result Inspection → VerifiedFactSet → Answer/Report → Memory/Snapshot` 保持唯一。M5.9 不缓存 Answer、CanonicalQueryPlan、DAX result、QueryResult 或 VerifiedFactSet，不跳过真实 business DAX。

## 实施合同

- Measurement：request-local safe phase timing、retry/timeout、cache/session、queue/worker metadata；Mock turn 基线与 Local MCP transport 基线分开，LLM latency 与 MCP latency分开。
- MCP：独立 session worker pool、bounded global admission/queue、per-request bound、FIFO dispatch、deadline/cancellation、worker crash isolation/rebuild、graceful drain/close。
- Resilience：LLM transient bounded retry；MCP transient read retry；validation/ambiguity/unsupported/stale identity 不重试；provider/profile/model snapshot 不变。
- Report：仅并行最终 plan 中独立且已通过 pre-execution correctness gates 的查询；稳定恢复 plan 顺序；QueryResult 与 VerifiedFactSet 不合并造数。
- Cloud-ready：保留 PowerBIAdapter、Repository、auth/config、lifespan 与 safe telemetry 边界；Remote MCP、Entra、PostgreSQL、Docker/K8s/Deployment 均 Deferred。

## 当前 fresh evidence

### Request / query-shape baseline

Deterministic Mock HTTP 全链覆盖 scalar/grouped/ranking/trend/report 和 1/4-way。最终 fresh 样本：cold scalar wall 49.313ms；warm scalar/grouped/ranking/trend/report 分别为 2.864/2.336/2.264/2.394/7.174ms；1-way wall 5.150ms，4-way wall 11.033ms、p95 9.858ms；residual=0。Mock 不产生真实 LLM/PBI phase latency，不能替代 Real 数据。

### Worker scaling

相同 20ms in-process external-transport fixture、100-way、queue capacity 100：

| workers | wall ms | throughput/s | p95 ms | queue wait p95 ms | errors | session residual |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3111.582 | 32.138 | 2951.368 | 2921 | 0 | 0 |
| 2 | 1462.586 | 68.372 | 1366.072 | 1328 | 0 | 0 |
| 4 | 774.938 | 129.043 | 740.270 | 719 | 0 | 0 |
| 8 | 400.050 | 249.968 | 367.977 | 344 | 0 | 0 |

8-worker 结果只证明离线实现可扩展，不构成真实默认值依据。默认 2 workers 是在吞吐改善、stdio process 数和真实 Desktop 未完成验证之间的保守选择。

### Backpressure / fault / lifecycle

- 默认 2 workers / queue 32 / admission 500ms：1/4/20/50 全成功；fresh 100-way 为 62 success + 38 controlled `local_mcp_overloaded`，max queue depth 31，session residual=0。较早同配置样本为 64/36，反映调度边界的正常小幅波动，不把最好样本当固定结果。
- 强制过载 4 workers / queue 8 / admission 20ms：20/50/100 分别受控拒绝 12/42/92，唯一错误类型 `local_mcp_overloaded`，max queue depth 7，FIFO dispatch，session residual=0。
- focused regression 已覆盖 canceled queued item ZERO execute、request deadline isolation、单 worker crash 不拖死其他 worker、session rebuild、shutdown close、stale identity fail closed、LLM 429/500/503/connection reset/timeout/malformed response，以及 cancellation Snapshot abort exactly once。

### 2h offline soak

2 workers / concurrency 20 / operation 20ms / queue 32 连续运行 7200.040 秒：23,290 batches、465,800 successes、0 errors、64.694 operations/s；batch p95 最大 780.979ms、max queue depth 19；2 sessions created、2 closed、session residual=0。测试期间未扩大 timeout 或修改断言。

### Fresh local gates

- Semantic Compatibility：743 PASS；backend full：2425 PASS / 1 个既有 manual-real SKIP；Golden：11 PASS / 1 个既有 manual-real SKIP。
- frontend：10 files / 87 tests PASS；typecheck、lint、production build PASS。
- Repository Safety：361 files；AI Error Ledger：59 entries；Architecture：133 production files；Documentation Governance、Artifact Governance、compileall、`git diff --check` PASS。
- 14 个本轮早期 automation-owned `local_state/test_runs/m59_*` 目录经用户明确批准，以最小管理员权限逐个 exact path 恢复 ACL 并删除；父目录仅在空目录时移除，未触及其他 local_state。最终 residual=0。

### Real Local MCP 1/2/4 worker acceptance

- 原 false blocker 来自 manual smoke 把 raw adapter catalog 的默认 `selectable=false` 当成正式 discovery-service 结果；修复后只按唯一 exact display name 选择 available/connected raw instance，并立即执行 compatibility probe。production API、adapter authority、identity validation 与 DAX 路径未改。
- Rich PBIX 4-way DAX：1 worker wall 8135.308ms / 0.492 operations/s / queue p95 6172ms；2 workers 6345.809ms / 0.630 operations/s / queue p95 2547ms；4 workers 5700.045ms / 0.702 operations/s / queue p95 0ms。三档 errors=0，worker IDs 与配置一致。
- 真实 session lifecycle：1 worker 创建/关闭 1/1，2 workers 2/2，4 workers 4/4；每档 `session_residual=0`、`active_workers=0`，退出后无 smoke/MCP 遗留进程。4 workers 对 2 workers 的增益有限且增加 Desktop/stdin process 成本，默认值保持数据驱动的 2。

## 尚未满足的正式条件

- 本地正式条件全部闭合；主实现提交 `179dd24f704d1f2059b37f5e7a6a0bb1ef87218f` 已 push main，PowerBIAgent Validation #52 / Full Validation (Windows) exact-SHA completed/success。M5.9 COMPLETE。
- 本文件只记录真实结果；不得把离线 fixture 冒充 Real，也不得把历史 M5.8.1 最佳值冒充 M5.9 before。
