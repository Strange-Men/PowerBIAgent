# ADR-001 — Agent 框架选择

- **状态：** accepted
- **日期：** 2026-07-31
- **决策者：** PowerBIAgent 项目组

---

## 一、Context

PowerBIAgent 需要一个成熟、轻量的 Python Agent 框架来支撑单 Agent 架构。核心需求：

1. **单 Agent** — 整个对话生命周期由单个 Agent 管理，不使用 LangGraph 或多 Agent
2. **意图识别** — Agent 必须包含明确、独立、可测试的意图识别模块
3. **DeepSeek** — 真实 LLM 前期只有 DeepSeek（OpenAI-compatible API）
4. **Mock LLM** — 必须提供完全可运行的 Mock，用于无 Key/无网络/流程调试
5. **结构化输出** — LLM 输出必须符合固定 Pydantic Schema（IntentSpec、QueryPlan、DAX、AnswerSpec、ReportSpec）
6. **FastAPI** — 后端使用 FastAPI 异步框架
7. **Memory** — 记忆系统是核心卖点，需要可靠的提交机制
8. **工具调用** — Agent 需要调用 Power BI MCP 工具
9. **不从零手写 Agent Runtime**
10. **Python 3.11**

## 二、候选方案

### 方案 A：PydanticAI

- **维护方：** Pydantic 团队（HelloRobot Ltd）
- **许可证：** MIT
- **首次发布：** 2024 年底，v1 于 2025 年 9 月
- **GitHub Stars：** 16,500+
- **Python 要求：** 3.9+

**核心特性：**
- 模型无关（OpenAI、Anthropic、DeepSeek、Gemini、Ollama 等）
- DeepSeek 通过 OpenAIProvider 原生支持
- 结构化输出自动校验和重试（`result_type`）
- 工具调用（函数式 + `Tool` 对象）
- 依赖注入（`deps_type`）
- 消息历史（`message_history`）
- MCP 协议集成
- FastAPI 无缝集成（流式/WebSocket）
- Logfire 可观测性/Tracing
- `pydantic-ai-slim[openai]` 轻量安装

### 方案 B：Microsoft Semantic Kernel

- **维护方：** Microsoft
- **许可证：** MIT
- **Python 支持：** 以 .NET/C# 为主，Python 为二等公民
- **架构：** Plugin/Kernel 模式，企业级抽象

**核心问题：**
- Python SDK 功能滞后于 C# 版本
- 2025 年 AutoGen 与 Semantic Kernel 合并重组，独立功能进入维护模式
- 企业级抽象层过重，学习曲线高
- 依赖较重（Azure SDK、企业连接器等）
- 对单 Agent MVP 而言过度封装

### 方案 C：其他轻量方案

- **CrewAI：** 面向多 Agent 协作，不符合单 Agent 原则
- **AutoGen：** 已与 Semantic Kernel 合并，方向不稳定
- **LangChain：** 过重，且项目明确禁止 LangGraph
- **手写 Agent Loop：** 违反"不从零手写复杂 Agent Runtime"约束

## 三、比较

| 维度 | PydanticAI | Semantic Kernel | 手写 |
|------|-----------|----------------|------|
| Python 3.11 兼容 | ✅ | ✅ | ✅ |
| FastAPI 异步支持 | ✅ 原生集成 | ⚠️ 需额外适配 | ⚠️ 需自行实现 |
| DeepSeek/OpenAI 兼容 | ✅ OpenAIProvider | ⚠️ 需自定义 Connector | ⚠️ 需自行实现 |
| Mock Model/测试支持 | ✅ DI + 可替换 Model | ⚠️ 较复杂 | ✅ 完全控制 |
| 工具调用 | ✅ 函数式 + Tool | ✅ Plugin 系统 | ⚠️ 需自行实现 |
| Pydantic 结构化输出 | ✅ `result_type` | ⚠️ 需手动处理 | ⚠️ 需自行实现 |
| 输出校验和重试 | ✅ 内置自动重试 | ❌ 需自行实现 | ❌ 需自行实现 |
| 消息历史 | ✅ `message_history` | ✅ ChatHistory | ⚠️ 需自行实现 |
| 依赖注入 | ✅ `deps_type` | ✅ DI 容器 | ⚠️ 需自行实现 |
| 外部 MCP Client 接入 | ✅ MCP 集成 | ⚠️ 支持不成熟 | ⚠️ 需自行实现 |
| Trace/测试便利性 | ✅ Logfire + Evals | ⚠️ Azure Monitor | ⚠️ 需自行实现 |
| 框架锁定风险 | 低（MIT，接口隔离良好） | 中（.NET 生态绑定） | 无 |
| 学习成本 | 低 | 高 | 无框架但实现成本高 |
| 维护状态 | ✅ 活跃 | ⚠️ 重组期 | — |
| 过度封装 | ❌ 否 | ✅ 是 | ❌ 否 |
| 单 Agent 适配 | ✅ 天然适配 | ⚠️ 可适配但冗余 | ✅ 完全控制 |

## 四、Decision

**选择 PydanticAI 作为 Agent 框架。**

核心理由：

1. **Python 原生优先** — 非 .NET 生态的二等公民
2. **Pydantic 天然集成** — 项目大量使用 Pydantic，结构化输出校验无缝衔接
3. **轻量但不简陋** — 提供 Agent 所需核心能力（工具调用、消息历史、DI、结构化输出），无过度封装
4. **DeepSeek 无障碍** — OpenAI-compatible Provider 即可接入
5. **Mock 友好** — DI 机制天然支持测试和 Mock
6. **FastAPI 同源** — 来自同一生态，集成顺畅
7. **MIT 许可证** — 无商业使用风险
8. **活跃维护** — v1 已发布，社区活跃

## 五、Consequences

**正面：**
- 结构化输出（IntentSpec、QueryPlan 等）与 Pydantic 校验深度集成
- DI 机制使 Memory、LLM Provider、PowerBIAdapter 可以清晰解耦
- `message_history` 简化多轮对话实现
- Mock LLM 可通过实现 Model 接口完成

**负面：**
- 框架尚新（2025 v1），API 可能存在 Breaking Changes
- 国内文档和社区资源较少
- Logfire 可观测性需额外学习

## 六、Risks

| 风险 | 缓解措施 |
|------|---------|
| PydanticAI API Breaking Changes | 通过 AgentRuntime Adapter 隔离框架；锁定版本 |
| 框架功能不满足需求 | 保留手写 Agent Loop 的降级路径 |
| DeepSeek 兼容性问题 | Mock LLM 先行验证接口契约 |

## 七、Fallback

如 PydanticAI 无法满足需求，降级路径：

1. 保留 `backend/app/agent/` 中的 AgentRuntime Adapter 抽象层
2. 将工具调用、消息历史等核心逻辑提取到 Adapter 内部
3. 可降级为基于 OpenAI SDK + 手写 Agent Loop 的最小实现
4. 或评估 Semantic Kernel 在降级时的成熟度

## 八、框架隔离策略

**核心业务契约不得直接绑定 PydanticAI。**

隔离方式：

```
业务层 (IntentService, MemoryRepository, etc.)
       │
       ▼
AgentRuntime Adapter (backend/app/agent/runtime.py)
       │
       ▼
PydanticAI (Agent, Tool, Model, etc.)
```

- 业务层只依赖 `AgentRuntime` 接口，不直接 import `pydantic_ai`
- `AgentRuntime` 封装 Agent 创建、工具注册、运行、结构化输出
- 如需替换框架，只需修改 `AgentRuntime` 实现

**M0.2 本轮不实现完整 Agent Runtime。** 本轮仅定义接口契约和 Adapter 骨架。

---

*创建日期：2026-07-31 | M0.2 智能体架构与记忆设计*
