# ADR-006 — 真实 Power BI Remote MCP 生产接入架构

- **状态：** accepted
- **日期：** 2026-08-11
- **决策者：** PowerBIAgent 项目组
- **证据基线：** `docs/milestones/m2/12_m2_powerbi_mcp_integration_plan.md` 的 Remote 生产化证据基线

---

## 背景

ADR-005 已确定 TurnPipeline、受控 LLM 与 ToolGateway 总体架构。M2 需要在不复制 Real Pipeline、不改变已封板生成主链的前提下，把真实 Power BI Remote MCP 接入现有 PowerBIAdapter 边界。Microsoft 当前将 Remote MCP 标记为 Public Preview，协议和工具响应仍可能变化。

> ADR-007 accepted 后，本文原有 “M2.1 / M2.3 实机验证” 表述保留为 Remote 生产化实施序列的历史语义；当前 M2.1 Local Demo 不实现或宣称完成这些 Remote 验证项。

## 决策

1. **总体方案：** 使用 Microsoft Fabric 托管的 Power BI Remote MCP endpoint `https://api.fabric.microsoft.com/v1/mcp/powerbi`，通过 Streamable HTTP 接入；不使用本地 Modeling MCP 作为 M2 主路径。
2. **Python Client：** M2.1 采用官方 `mcp` Python SDK v2 稳定线，基线版本 `2.0.0`。默认使用高层 `Client` 生命周期；底层 `ClientSession` 只作为兼容检查或必要逃生口。Power BI endpoint 实际协商协议及 initialize/discover 行为标记为 **待 M2.1 实机验证**。
3. **OAuth：** 采用单租户 Entra App、用户委托的 Authorization Code + PKCE 浏览器流程；由 SDK `OAuthClientProvider` 负责发现、PKCE、Token 刷新和授权头注入。默认不单独实现 MSAL，也不采用 Device Code 作为产品主流程。预注册 Entra client ID 如何注入 SDK 存储标记为 **待 M2.1 实机验证**。
4. **Entra App 边界：** 自定义 FastAPI/Python 客户端必须使用同 Tenant 的 Entra App Registration、精确匹配的 Public client/native redirect URI，以及 Microsoft 当前列出的 Power BI 委托权限。用户或管理员同意策略由 Tenant 决定。
5. **Adapter 隔离：** MCP SDK、OAuth Provider、TokenStorage、Microsoft 原始工具名和原始响应只能位于 PowerBIAdapter 边界之后。Service、API、LLM、Memory 与 Report 不得依赖它们。
6. **唯一工具入口：** Schema 和 DAX 调用必须由 TurnPipeline 驱动并经过 ToolGateway；不得从 Service/API/LLM 直接调用 MCP。
7. **工具白名单：** M2 只允许 Remote MCP 的 Get Semantic Model Schema 与 Execute Query 能力。实际工具标识和输入 schema 通过 M2.1 `list_tools` 固定。Get Report Metadata 与 Generate Query 不进入 M2 白名单。
8. **单一 DAX 入口：** 禁止使用 Power BI Generate Query。现有 DeepSeek → QueryPlan → DAX 是唯一 DAX 生成链，Remote MCP 只负责 Schema 与已生成 DAX 的执行。
9. **共享管线：** Mock 与 Real 共用现有 TurnPipeline、ToolGateway、Memory/Snapshot 控制面和 Intent → QueryPlan → DAX → Answer / ReportSpec 主链；不得复制 Real Service 或 Real Pipeline。
10. **失败边界：** Real 失败必须显式返回标准化错误，禁止静默降级到 Mock。401 只允许受控刷新后一次重试；403、DAX、畸形响应与超大结果不做掩盖性重试。429 语义与 `Retry-After` 支持标记为 **待 M2.1/M2.3 实机验证**。
11. **Token / Secret：** Token、refresh token、client secret、Authorization header 不进入 Git、`.env`、日志、Trace 或 Fixture。首次 Smoke 可使用进程内 TokenStorage；可重复运行采用操作系统安全存储或等价受控存储，禁止明文缓存文件。具体持久化实现标记为 **待 M2.1 实机验证**。
12. **认证主体：** M2 内部 MVP 使用用户委托认证，以继承用户 Power BI 权限并执行 RLS。Client Credentials / Service Principal 不作为 M2 主路径；Microsoft 明确其当前不支持 RLS，不适合面向用户的数据问答。
13. **模型 ID：** API 只接收 friendly `semantic_model_key`。ToolGateway 按 UserContext 白名单校验，Remote Adapter 再通过注入的只读配置映射为真实 semantic model ID；客户端不得任意提交真实 ID。
14. **CI 与 Smoke：** 自动 CI 完全离线，使用 Fake/Stub MCP Client/Session 与脱敏 Fixture，不含 Microsoft Token、DeepSeek Key 或真实业务数据。真实 OAuth、initialize/协商、`list_tools`、Schema 与 DAX 只在人工 Smoke 中运行。
15. **Preview 风险：** 工具名、输入/输出 schema 和协议协商均通过 Adapter 隔离并由 M2.1 实机固定；Preview 变更不得向上泄漏为业务契约变化。
16. **Fallback：** ADR-006 的 Remote 生产化实施不使用 Local MCP、社区 Proxy、REST/XMLA 或 Real → Mock 自动回退。官方 Remote MCP 若不可用则明确失败并停止；ADR-007 是用户另行批准的 Demo Provider 决策，不是 Remote 失败时的运行时 fallback，且仍受 PowerBIAdapter 与 ToolGateway 约束。

## 与其他 ADR 的关系

- ADR-005 继续负责 Agent / TurnPipeline 总体架构；ADR-006 不替代它。
- ADR-003 的 Remote MCP、Entra App 和 Adapter 方向保留；Device Code + 独立 MSAL + 本地缓存文件及自动 Fallback 实现设想被本 ADR 部分替代。
- ADR-007 仅在管理员前置条件暂不可得时选择 Local MCP 作为 Demo 验证路径；不 supersede ADR-006。管理员条件具备并获用户批准后，生产化仍回到本 ADR。

## 后果

- 正面：只有一个控制面、一个 DAX 生成入口和一个 Power BI 工具入口；Microsoft Preview 变化被隔离；用户委托权限与 RLS 语义保持一致。
- 负面：M2.1 必须具备 Tenant、App Registration、账号和 Build 权限；浏览器回调与安全 TokenStorage 增加基础设施工作；Preview 仍需人工兼容验证。

---

*最后更新：2026-08-11 | M2.0 accepted*
