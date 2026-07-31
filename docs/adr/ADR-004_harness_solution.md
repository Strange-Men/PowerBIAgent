# ADR-004 — Harness 方案：轻量 ETCLOVG 控制面

- **状态：** accepted
- **日期：** 2026-07-31
- **决策者：** PowerBIAgent 项目组

---

## 一、Context

PowerBIAgent MVP 需要一个轻量控制面来约束 Agent 行为、防止开发偏移并持续验证数据结果。控制面必须：

1. 限制 Agent 只能使用白名单工具
2. 确保所有 LLM 输出经过 Pydantic 校验
3. 管理每个 Turn 的生命周期
4. 强制记忆提交准入条件
5. 提供完整的 Trace 审计
6. 支持 Golden Cases 回归

MVP 不引入 Docker、Kubernetes、LangGraph、OpenTelemetry、Redis、Celery 或任何重量级基础设施。

## 二、候选方案

### 方案 A：轻量 ETCLOVG（当前选择）

与当前项目结构和开发生命周期对齐的轻量职责划分：

| 缩写 | 职责 | 实现 |
|------|------|------|
| E — Execution | 运行配置和模式管理 | HarnessConfig |
| T — Tooling | 工具注册、权限、执行 | ToolGateway |
| C — Context | 安全上下文组装 | ContextBuilder |
| L — Lifecycle | Turn 状态机和资源限制 | TurnController |
| O — Observability | JSON Trace 事件记录 | TraceRecorder |
| V — Verification | 统一验证入口 | ValidationService |
| G — Governance | 白名单、策略、边界 | Policies + Guard |

### 方案 B：LangGraph 编排

- 状态图驱动，适合复杂 Agent 流程
- MVP 禁止使用，过度设计

### 方案 C：无 Harness

- 业务代码中散落 if/else 检查
- 缺乏统一的 Trace、验证和生命周期管理
- 不满足项目要求

## 三、Decision

**选择方案 A：轻量 ETCLOVG 控制面。**

核心理由：
1. 与 MVP 单 Agent 架构一致
2. 职责清晰、可独立测试
3. 无外部依赖
4. 可在 M0.3 完整实现并验证

## 四、架构

```
用户请求
→ ContextBuilder (C)
→ 意图识别
→ MockAgentRuntime (E)
→ TurnController (L)
→ ToolGateway (T)
→ MockPowerBIAdapter
→ ValidationService (V)
→ Memory Commit Guard (G)
→ AnswerSpec / ReportSpec
→ TraceRecorder (O)
```

## 五、Consequences

**正面：**
- 所有组件可独立单元测试
- Trace 完整记录每次请求
- 策略可在 Harness 中统一管理
- Golden Cases 可直接验证控制面行为

**负面：**
- ETCLOVG 不是行业标准术语（项目内部使用）
- M0.3 组件数量较多（需保持边界清晰）

## 六、M0.3/M0.4 边界

| | M0.3 | M0.4 |
|------|------|------|
| HarnessConfig | Pydantic 模型 | Pydantic Settings (环境变量) |
| ToolGateway | 完整实现 | — |
| ContextBuilder | 完整实现 | — |
| TurnController | 完整实现 | — |
| TraceRecorder | 内存 + JSON | — |
| ValidationService | 完整实现 | — |
| GoldenCaseRunner | 完整实现 | — |
| FastAPI 集成 | ❌ | ✅ |

---

*创建日期：2026-07-31 | M0.3 数据接入与验证闭环*
