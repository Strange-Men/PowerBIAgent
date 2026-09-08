# ADR-017 — Bounded Runtime Concurrency 与 Resilience

- **状态：** accepted
- **日期：** 2026-09-07
- **决策者：** 用户明确批准 M5.9
- **适用阶段：** M5.9；M5.8.5 correctness authority 冻结

## 背景

M5.8.1 已让 Local MCP stdio session 由应用持有并复用，也建立了短 TTL bounded metadata cache 与 per-key singleflight。但所有业务 MCP 操作仍经一个 session worker 串行执行；高并发下 queue wait 成为主要长尾。LLM Provider 已有错误分类，却没有统一的 bounded retry 与整体 request deadline。未来 Remote MCP、PostgreSQL 和云运行时还需要清晰替换边界，但这些 provider 的正式实现不属于 M5.9。

## 决策

1. 唯一事实链保持不变。M5.9 只在 `TurnPipeline`、`ToolGateway`、`PowerBIAdapter`、LLM Provider 与既有 Repository 边界增加 timing、admission、deadline、retry 和 lifecycle 能力；不新增 semantic、planner、grounding、DAX 或 fact authority。
2. Local MCP 使用固定数量的 worker pool。每个 worker 独占一个 stdio client/session；coroutine 不直接共享 session。所有 worker 共用有界 admission/queue，每个请求另有有界 MCP operation 配额，队列按提交顺序 dispatch。
3. worker/session 生命周期由应用 lifespan 持有。单个 session 的 fatal transport failure 只终止并重建该 worker 的 session；关闭时停止接收新工作、drain 已接纳工作、关闭全部 stdio session，并等待 worker 结束。`closed` 复核与 queue enqueue 必须在同一 lifecycle lock 内完成：成功 enqueue 才算正式接纳，shutdown 开始后尚未 enqueue 的请求快速失败。
4. 每轮建立 request-local monotonic deadline。LLM、ToolGateway、MCP admission、session startup 和 MCP operation 的局部 timeout 不能超过剩余预算。caller cancellation 必须释放 admission slot；尚未执行的已取消项不得调用 MCP；TurnPipeline owner 必须 abort Snapshot claim，禁止重复 Memory commit 或 ReportArtifact。
5. 仅 transient 且可安全重放的只读操作可重试。LLM 的 429、5xx、连接和 timeout 使用 exponential backoff + jitter，最大尝试次数为 3；malformed response、validation、semantic ambiguity、unsupported 和认证失败不重试。Local MCP transport retry 的唯一 owner 是 `LocalMCPPowerBIAdapter`：只对明确标记 retryable 的 network/startup/timeout 做至多一次额外尝试；已声明 Adapter ownership 的 schema/member/DAX `ToolSpec` 不再叠加 Gateway transport retry。stale PBIX identity 永不重试或切换模型。
6. 性能观测是 request-local、data-safe 的进程内 contract：phase duration、retry/timeout count、cache/session state、queue depth 和 worker ID。不得记录 Secret、Authorization、完整 prompt、原始敏感响应、PBIX path 或 connection string。设计保持 OpenTelemetry-friendly，但 M5.9 不部署 telemetry backend。
7. 报表只并行最终 `ReportDataPlan` 已证明互不依赖、且已经完成 CanonicalQueryPlan、deterministic DAX 与 Layer 3 validation 的查询。执行有界、结果恢复原 plan 顺序；每个 QueryResult 仍逐一通过 Result Inspection 并建立自己的 VerifiedFactSet 后才进入既有 ReportData/ReportSpec。
8. transport、auth、repository、configuration、telemetry 和 lifecycle 只保持可替换边界。Remote MCP 必须复用现有 ModelSemanticContext/Catalog/Grounding/DAX/fact 链；PostgreSQL 必须实现现有 Repository contract。M5.9 不实现 Remote MCP、Entra、PostgreSQL migration 或 Deployment。

## 数据驱动默认值

离线 deterministic transport fixture 的 100-way、20ms operation 比较中，1/2/4 workers 的 throughput 分别约为 32.3/65.9/128.7 operations/s，p95 分别约为 2941/1454/745ms，且 session residual 均为 0。Real Local MCP 4-way DAX acceptance 的 1/2/4 workers throughput 分别为 0.492/0.630/0.702 operations/s，errors=0、session residual=0。8 workers 离线可运行，但真实 Desktop 的 process/session 成本和稳定性尚不能由 fixture 证明。因此生产默认保持 2 workers、32 个全局 pending operations、每请求 2 个 operation、500ms admission timeout；是否上调必须重新取得 Real Local MCP 数据。

## 后果与边界

有界队列会在过载时返回受控 `local_mcp_overloaded`，而不是无限等待或耗尽资源。跨 worker completion 可以重排，但 FIFO dispatch 与调用方的输入顺序恢复合同保持确定。性能收益不得通过跳过真实 business DAX、降低 correctness gate、缓存 QueryResult/VerifiedFactSet/CanonicalQueryPlan 或扩大 timeout 获得。

M5.9.1 对 shutdown/enqueue 线性化与 retry ownership 的专项审计以 deterministic reproducer、exact call-count 回归、full gates、residual=0、clean main 与当前 main exact-SHA Full Validation (Windows) success 为发布证据。M5.10 NOT STARTED，M5 FINAL=false。
