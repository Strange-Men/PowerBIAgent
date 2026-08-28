# ADR-013 — LLM Model Profiles and Request-Scoped Provider Selection

- **状态：** accepted
- **日期：** 2026-08-27
- **决策者：** 用户明确批准

## 背景

现有真实 LLM 路径以 DeepSeek 命名并直接承载 OpenAI-compatible Chat Completions 协议。M5.8 需要增加 Kimi-K2.6，同时保持 ADR-005 的单一 TurnPipeline、M5.7.1 的 semantic authority 和多会话并发隔离。若通过进程级 default 切换模型，或为 Kimi 复制 TurnService/Intent/QueryPlan/Answer 栈，会导致并发会话串模型、协议逻辑漂移和双管线。

## 决策内容

1. 保留 `LLMProvider` 作为上层协议；Mock provider 不变，真实 profiles 共用唯一 `OpenAICompatibleLLMProvider`。
2. 引入不可变 `LLMModelProfile`，保存 public profile identity、display name、protocol、base URL、model、timeout、协议 capability flags 与可选 pricing metadata；API Key 由后端 Secret-bearing runtime configuration 独立提供。
3. Provider Registry 只提供 `profile_key → provider/profile` 显式解析和只读 public catalog，不使用 `set_default()` 或其他全局 mutable default 实现用户选择。
4. 每个 turn 开始时解析 profile key，建立 immutable provider/profile snapshot，并把同一 snapshot 注入该 turn 的全部 LLM tasks。UI 后续切换不改变 in-flight turn。
5. 新会话使用提交时显式选择；同 conversation 下一轮允许切换。Structured Memory 与 canonical slots 按既有规则保留，provider opaque session state 不进入 authoritative Memory。
6. unknown/stale/unavailable profile、配置缺失或 provider failure 全部 fail closed；禁止 DeepSeek↔Kimi silent fallback、auto-routing 或 ensemble。
7. Provider error/usage/trace 使用统一结构；trace 仅记录 public profile/protocol/model/task/usage/error class。Secret、Authorization、secret URL query、完整 prompt 与原始敏感响应不得记录。未配置价格时 estimated cost 为 null。
8. Provider 只输出受 Pydantic contract 约束的 language draft。SemanticGrounding、StateTransition、Deterministic DAX、QueryResult 与 VerifiedFactSet authority 不变。

## 备选方案

- 运行时修改 Registry 全局 default：拒绝；并发 conversation 与 in-flight turn 会产生 cross-contamination。
- 为 Kimi 复制 TurnService 与任务 Service：拒绝；形成双管线并扩大 provider-specific 分支。
- provider 自动路由、fallback 或 ensemble：拒绝；隐藏故障并破坏用户显式选择与可审计性。

## 后果

- 正面：协议实现复用，模型选择可并发隔离、可审计，Provider 差异不进入 semantic authority。
- 负面：所有 LLM call site 必须接收同一 turn snapshot；API/frontend contract 需要携带 public profile key；配置与错误测试矩阵扩大。
- M5.9 MCP lifecycle/performance 与 M5.10 第二报表模板不在本 ADR 范围。

---

*本 ADR 在 M5.8 S1 合同阶段建立；完成证据以 fresh tests、Real smoke 与远程 CI 为准。*
