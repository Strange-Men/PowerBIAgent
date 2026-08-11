# 12 — M2 真实 Power BI Remote MCP 接入计划

> **状态：** M2.0 已完成候选；M2.1—M2.5 未开始
> **官方资料查询日期：** 2026-08-11
> **边界：** 本文只固化证据、架构、轮次与门禁，不实现 Remote MCP、OAuth 或真实数据问答。

---

## 1. M2 目标

把现有 MockPowerBIAdapter 替换为可注入的 RemoteMCPPowerBIAdapter，在不改变现有 TurnPipeline 主链的情况下完成真实 Power BI 数据问答。

固定目标链：

```text
API → TurnService → TurnPipeline → Intent → ToolGateway
→ PowerBIAdapter → MCP Client → Power BI Remote MCP
→ QueryResult → Answer / ReportSpec → Memory / Snapshot
```

## 2. 官方证据矩阵

| 决策项 | 官方结论 | 官方来源 | 项目影响 | 状态 |
|---|---|---|---|---|
| Remote MCP endpoint | `https://api.fabric.microsoft.com/v1/mcp/powerbi` | [Get started with the remote Power BI MCP server](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-get-started)，查询日期 2026-08-11 | 作为唯一 M2 Remote endpoint；不手写 REST 协议 | 已确认 |
| Preview 状态 | Remote 与 Local 均为 Public Preview，工具定义、请求与响应可能变化 | [Overview of the Power BI MCP servers](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)，查询日期 2026-08-11 | Adapter 隔离并在 M2.1 固定实机 schema | 已确认 |
| Transport | Remote 使用 Streamable HTTP；Local 才是 stdio | [Overview of the Power BI MCP servers](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)，查询日期 2026-08-11 | 不使用 SSE、stdio 或手写 httpx JSON-RPC | 已确认 |
| Python SDK | 官方包名 `mcp`；v2 是稳定线，`v2.0.0` 于 2026-07-28 发布 | [MCP Python SDK v2.0.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0) 与 [官方 README](https://github.com/modelcontextprotocol/python-sdk)，查询日期 2026-08-11 | M2.1 锁定 `mcp==2.0.0`，不选 FastMCP 第三方客户端 | 已确认 |
| Client 生命周期与 initialize | v2 高层 `Client` 以 `async with` 管理生命周期，自动协商；对旧服务器回退 initialize，`ClientSession` 为底层逃生口 | [The Client — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/)，查询日期 2026-08-11 | M2.1 验证 Power BI 实际协议、initialize/discover 与生命周期 | 待 M2.1 实机验证 |
| list_tools / call_tool | `list_tools()` 返回工具定义；`call_tool()` 返回 `content`、`structured_content`、`is_error` | [The Client — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/)，查询日期 2026-08-11 | 工具名/输入 schema 由实机发现后锁入 Adapter 白名单 | 已确认 SDK；Remote 细节待验 |
| OAuth 方式 | SDK `OAuthClientProvider` 实现 Authorization Code + PKCE、发现、Bearer 注入和刷新；Provider 挂载到 `httpx2.AsyncClient(auth=...)` 后交给 Streamable HTTP transport | [OAuth clients — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | 产品主流程不选 Device Code；默认不独立实现 MSAL | 已确认总体方案 |
| Entra App | Entra 当前不支持该场景的客户端动态注册；外部/自定义客户端需自行注册同 Tenant 单租户 App 并提供 client ID | [Register the remote Power BI MCP server with external MCP clients](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-external-clients)，查询日期 2026-08-11 | M2.1 前必须获得 App Registration 或管理员协助 | 已确认 |
| Redirect URI | 外部客户端为 Public client/native，必须使用客户端精确 callback URI；公共客户端流默认保持 No，除非客户端明确要求 | [Register the remote Power BI MCP server with external MCP clients](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-external-clients)，查询日期 2026-08-11 | FastAPI callback URI 与 SDK 预注册 client ID 注入方式需实机固定 | 待 M2.1 实机验证 |
| Delegated permissions | 当前官方列出 `Dataset.Read.All`、`MLModel.Execute.All`、`Workspace.Read.All` | [Register the remote Power BI MCP server with external MCP clients](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-external-clients)，查询日期 2026-08-11 | 纠正 ADR-003 对 `MLModel.Execute.All` 的旧疑问；只申请官方列出的委托权限 | 已确认 |
| Tenant setting | 管理员必须启用 “Users can use the Power BI Model Context Protocol server endpoint (preview)” | [Get started with the remote Power BI MCP server](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-get-started)，查询日期 2026-08-11 | 未启用即为外部阻塞，不尝试绕过 | 已确认 |
| Build permission | Execute Query 要求用户至少有目标 semantic model 的 Build；Contributor 及以上工作区角色通常自带 Build，Viewer 需单独授予 | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools) 与 [Build permission for shared semantic models](https://learn.microsoft.com/en-us/power-bi/connect-data/service-datasets-build-permissions)，查询日期 2026-08-11 | M2.1 前确认账号、工作区访问和目标模型 Build | 已确认 |
| Schema 工具 | Get Semantic Model Schema 返回表、列、度量值、关系、类型、层级与可用 AI 元数据 | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | M2.2 映射为现有 `SemanticModelSchema` | 已确认能力；响应待验 |
| DAX 执行工具 | Execute Query 接收 semantic model ID 与 DAX，在认证用户上下文执行 | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | M2.3 映射为现有 `QueryResult` | 已确认能力；响应待验 |
| 官方工具集合 | 当前逻辑工具为 Execute Query、Get Semantic Model Schema、Get Report Metadata、Generate Query | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | M2 只白名单 Schema + Execute；精确 MCP 标识以 `list_tools` 为准 | 已确认逻辑集合 |
| Generate Query 策略 | 官方允许禁用并由客户端 LLM 直接生成 DAX；该工具还要求 Copilot license/capacity | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | 禁用/不调用，避免形成第二个 DAX 生成入口 | accepted |
| Token 策略 | SDK `TokenStorage` 管 access/refresh token 与 client info，自动刷新；存储可替换 | [OAuth clients — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | Smoke 可内存；复用需系统安全存储，禁止明文文件、`.env`、日志和 Trace | 总体确认；后端待 M2.1 |
| 用户委托与 RLS | 用户认证按其权限执行并强制 RLS；Service Principal 当前不支持 RLS | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | 内部 MVP 选用户委托；Client Credentials/SP 不作为 M2 主路径 | accepted |
| Error handling | 工具失败可由 `is_error` 返回；OAuth 失败有结构化异常；Power BI Preview 文档未承诺 429/Retry-After 契约 | [The Client](https://py.sdk.modelcontextprotocol.io/client/) 与 [OAuth clients](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | Adapter 统一标准化；401 刷新一次，403/DAX/畸形/超大不掩盖，429 待实机 | 部分待 M2.3 验证 |
| CI 策略 | 官方 SDK 支持 in-memory Client 作为测试通道；真实 OAuth 必须经 HTTP/browser | [Client transports](https://py.sdk.modelcontextprotocol.io/client/transports/) 与 [OAuth clients](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | CI 用 Fake/Stub Session 与脱敏 Fixture；真实 MCP 仅人工 Smoke | accepted |

结论：ADR-003 的 Remote MCP、Entra App 与 Adapter 方向仍正确；Device Code + 独立 MSAL + 本地缓存文件被 ADR-006 的 Authorization Code + PKCE、官方 SDK OAuth 与受控 TokenStorage 部分替代。

## 3. 当前代码到 M2 目标映射

### RemoteMCPPowerBIAdapter

- 当前：只有 `NotImplementedError` skeleton，构造器提前写入 MSAL 假设。
- M2：成为 MCP/OAuth/工具名/原始响应与现有契约之间的唯一隔离层；SDK 支撑代码位于 Adapter 边界之后。

### DeepSeekTurnService

- 当前：构造参数类型绑定 `MockPowerBIAdapter`，多处 `source_mode="mock"`，并覆盖 `QueryResult.source_mode`。
- 目标（M2.4）：依赖 `PowerBIAdapter` 抽象并传播 Adapter/QueryResult 的真实来源；不得复制第二套 Real Service。

### main.py

- 当前：只注入 Mock+Mock 或 DeepSeek+Mock；Remote 模式不初始化 Service。
- 目标（M2.4）：在组合根创建并注入 Remote Adapter；M2.1—M2.3 不提前接 Chat。

### routes.py

- 当前：Remote 模式固定返回 503。
- 目标（M2.4）：完整接通后才移除固定 503；API 仍不直接接触 MCP。

### source_mode 与 Snapshot

- 当前：`QueryResult`、Answer/Report 契约已有 `source_mode`，但 DeepSeek 路径和 TurnPipeline replay 写死 `mock`；`TurnResultSnapshot` 未保存 `source_mode`。
- 目标（M2.4）：由真实 QueryResult/Adapter 状态向 Answer、Report、API 与 Snapshot 传播；Snapshot 做最小字段扩展，使 Real 幂等重放保持 `real` 且不重复访问 MCP。本轮只设计，不修改契约。

### UserContext 与真实 Model ID

- 当前：`allowed_semantic_models=["mock_sales_model"]`，ToolGateway 以 friendly key 做白名单检查。
- 目标（M2.2）：保持 API 只接收 friendly `semantic_model_key`；ToolGateway 先校验 UserContext，Remote Adapter 再用注入的只读配置执行 `friendly key → real semantic model ID` 映射。未知 key、未授权 key 与客户端直接提交真实 ID 均拒绝。

### Settings

本轮只把版本更新为 M2.0，不增加字段。后续最小配置设计：复用 endpoint/tenant/client ID；M2.1 增加精确 redirect URI 与安全 TokenStorage 选择；M2.2 增加 friendly key 映射。用户委托主路径不使用现有 `powerbi_client_secret`，是否弃用在实现轮决定。

## 4. M2.0—M2.5 开发路线

### M2.0｜官方证据复核、架构设计与路线固化

**状态：** ✅ 已完成候选。生产业务实现 = 0；不登录、不取 Token、不连接 Power BI。

### M2.1｜MCP Client + OAuth + 最小真实连接验证

只证明 `OAuth → initialize/协议协商 → list_tools → MCP connection/health`。允许引入最终确认的 SDK/OAuth 依赖、最小 Client 基础设施、真实认证与人工 Smoke；禁止接 Chat、改 TurnPipeline、执行完整自然语言问答。属于“连得上”。

验收必须记录：协商协议、initialize/discover 行为、工具精确名称与 input schema、预注册 client ID 注入、redirect callback、刷新与退出生命周期。外部条件不齐时停止。

### M2.2｜真实 Semantic Model Schema 接入

完成 `ToolGateway → RemoteMCPPowerBIAdapter → MCP → SemanticModelSchema`、`get_semantic_model_schema()` 与真实 Model ID 安全映射。禁止真实数据问答主链。属于“看得懂模型”。

### M2.3｜真实 DAX 执行与 QueryResult 标准化

完成 `DAXRequest → ToolGateway → Remote Adapter → MCP → QueryResult`，覆盖 success、401、403、timeout、官方实际支持的 rate limit、DAX error、malformed response、oversized result。禁止完整 Chat。属于“查得到数据”。

### M2.4｜接入现有 TurnPipeline

接通 DeepSeek + Real Power BI：Service 依赖 Adapter 抽象，main 注入 Remote Adapter，routes 移除固定 503，ToolGateway 仍是唯一入口，`source_mode=real` 与 Snapshot 正确传播，Real 失败不回退 Mock，不复制 Real Pipeline。属于“自然语言真的能查 Power BI”。

### M2.5｜真实全链路验收与 M2 封板候选

验证真实 Schema/DAX/QueryResult、核心数值一致、相同 request_id 幂等重放且不重复访问 MCP、OAuth 失效、permission denied、timeout、DAX error、Trace 脱敏、Mock/CI 回归与架构无偏移。完成后停止并等待仓库审计，不自动创建 M2.6。

## 5. 每轮 M2 防偏移门禁

每轮修改生产代码前必须检查：

1. 新职责是否属于已有模块？
2. 是否复用了 PowerBIAdapter？
3. Power BI 调用是否经过 ToolGateway？
4. 是否仍由 TurnPipeline 控制？
5. 是否建立第二套 Real Pipeline？
6. Service/API 是否直接调用 MCP？
7. LLM 是否获得 MCP 工具自主权？
8. 是否出现 Real → Mock 静默回退？
9. 是否修改已封板 Intent / QueryPlan / DAX / Answer / ReportSpec？
10. 是否提前开发 M3/M4/M5？

第 5 / 6 / 7 / 8 / 10 项任一为“是”，立即停止，不得增加例外绕开。

## 6. 测试与验收边界

- CI 完全离线，不访问 Power BI，不使用 Microsoft Token 或 DeepSeek Key。
- MCP Client 使用 Fake/Stub Session；Adapter 使用脱敏 Fixture；优先补充已有领域测试。
- 禁止批量创建 `test_m2_xxx.py`；一个 Bug 对应最接近真实入口的回归测试。
- 真实 MCP 只跑人工 Smoke；真实业务数据、原始响应、Token、Prompt 不进入 Fixture、日志或 Trace。
- M2.0 不新增业务测试。

## 7. M2.1 前置停止条件

必须同时具备：可用 Microsoft 账号、可访问 Power BI Tenant、Tenant 已允许 Remote MCP、Entra App 注册能力或管理员协助、目标 Semantic Model、用户必要权限/Build 权限、真实 Semantic Model ID。M2.0 不登录、不读取 Token、不猜测公司 Tenant 配置。

最关键外部阻塞项：

1. Tenant 管理员未启用 Remote MCP Preview 设置。
2. 无 Entra App Registration 权限或无法配置精确 redirect URI/委托权限。
3. 无可访问目标 Semantic Model、真实 ID 或 Build 权限。

---

*最后更新：2026-08-11 | M2.0 规划完成候选；真实业务实现尚未开始*
