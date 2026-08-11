# 12 — M2 真实 Power BI MCP 统一接入计划

> **状态：** M2.2 真实 Semantic Model Schema 接入完成候选
> **官方资料查询日期：** 2026-08-11
> **边界：** 当前 Demo 使用 Local MCP + Power BI Desktop；Remote MCP 作为 ADR-006 生产化路径延后。二者只能替换 PowerBIAdapter 后的 Provider。

---

## 1. M2 目标

PowerBIAdapter 隔离真实 Power BI Provider，在不改变现有 TurnPipeline、ToolGateway、Harness 与生成主链的情况下完成真实数据问答。

- **当前 Demo 路径（ADR-007）：** `LocalMCPPowerBIAdapter → stdio → Power BI Local Modeling MCP → Power BI Desktop`。
- **延后生产路径（ADR-006）：** `RemoteMCPPowerBIAdapter → Streamable HTTP / OAuth → Power BI Remote MCP`。
- **不变部分：** TurnPipeline 唯一控制面、ToolGateway 唯一业务工具入口、DeepSeek 是唯一 DAX 生成入口、Mock/Real 不静默回退。

固定目标链：

```text
API → TurnService → TurnPipeline → Intent → ToolGateway
→ PowerBIAdapter → Local / Remote MCP Client → Power BI
→ QueryResult → Answer / ReportSpec → Memory / Snapshot
```

### DAX Business Semantic Correctness Contract

- **M2.2：** 获取并保留真实 Semantic Model 的 Schema、Measure 与可用业务语义信息。
- **M2.4：** 对 QueryPlan 的业务指标映射及 DAX 与已验证 QueryPlan 的一致性施加确定性约束。
- **M2.5：** 通过现有 Harness / Golden 体系核对真实业务口径与 Power BI 结果。

永久正确性链为 `Schema / Measure / 明确业务定义 → QueryPlan → DAX → QueryResult`；禁止变成“用户问题 → LLM 猜业务含义 → DAX”。

## 2. Remote 生产化证据基线

| 决策项 | 官方结论 | 官方来源 | 项目影响 | 状态 |
|---|---|---|---|---|
| Remote MCP endpoint | `https://api.fabric.microsoft.com/v1/mcp/powerbi` | [Get started with the remote Power BI MCP server](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-get-started)，查询日期 2026-08-11 | ADR-006 唯一 Remote 生产 endpoint；不手写 REST 协议 | 已确认 |
| Preview 状态 | Remote 与 Local 均为 Public Preview，工具定义、请求与响应可能变化 | [Overview of the Power BI MCP servers](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)，查询日期 2026-08-11 | 所有 Provider 变化必须由 Adapter 隔离 | 已确认 |
| Transport | Remote 使用 Streamable HTTP；Local 使用 stdio | [Overview of the Power BI MCP servers](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)，查询日期 2026-08-11 | Remote 不使用 SSE、stdio 或手写 httpx JSON-RPC | 已确认 |
| Python SDK | 官方包名 `mcp`；v2 是稳定线，`v2.0.0` 于 2026-07-28 发布 | [MCP Python SDK v2.0.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0) 与 [官方 README](https://github.com/modelcontextprotocol/python-sdk)，查询日期 2026-08-11 | 项目锁定 `mcp==2.0.0`，Local / Remote 共用，不选第三方替代 Client | 已确认 |
| Client 生命周期与 initialize | v2 高层 `Client` 以 `async with` 管理生命周期并自动协商；`ClientSession` 为底层逃生口 | [The Client — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/)，查询日期 2026-08-11 | Remote 实际协议与生命周期留待生产化实机验证 | 已确认 SDK；Remote 待验 |
| list_tools / call_tool | `list_tools()` 返回工具定义；`call_tool()` 返回 `content`、`structured_content`、`is_error` | [The Client — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/)，查询日期 2026-08-11 | Remote 工具精确标识由生产化实机固定 | 已确认 SDK；Remote 待验 |
| OAuth 方式 | SDK `OAuthClientProvider` 实现 Authorization Code + PKCE、发现、Bearer 注入和刷新；Provider 挂载到 `httpx2.AsyncClient(auth=...)` 后交给 Streamable HTTP transport | [OAuth clients — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | 产品主流程不选 Device Code；默认不独立实现 MSAL | 已确认总体方案 |
| Entra App | Entra 当前不支持该场景的客户端动态注册；外部/自定义客户端需自行注册同 Tenant 单租户 App 并提供 client ID | [Register the remote Power BI MCP server with external MCP clients](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-external-clients)，查询日期 2026-08-11 | Remote 生产化前必须获得 App Registration 或管理员协助 | 已确认 |
| Redirect URI | 外部客户端为 Public client/native，必须使用客户端精确 callback URI；公共客户端流默认保持 No，除非客户端明确要求 | [Register the remote Power BI MCP server with external MCP clients](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-external-clients)，查询日期 2026-08-11 | callback 与预注册 client ID 注入由 Remote 生产化实机固定 | Remote 待验 |
| Delegated permissions | 当前官方列出 `Dataset.Read.All`、`MLModel.Execute.All`、`Workspace.Read.All` | [Register the remote Power BI MCP server with external MCP clients](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-external-clients)，查询日期 2026-08-11 | 纠正 ADR-003 对 `MLModel.Execute.All` 的旧疑问；只申请官方列出的委托权限 | 已确认 |
| Tenant setting | 管理员必须启用 “Users can use the Power BI Model Context Protocol server endpoint (preview)” | [Get started with the remote Power BI MCP server](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-get-started)，查询日期 2026-08-11 | 未启用时 Remote 路径 Deferred，不尝试绕过 | 已确认 |
| Build permission | Execute Query 要求用户至少有目标 semantic model 的 Build；Contributor 及以上工作区角色通常自带 Build，Viewer 需单独授予 | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools) 与 [Build permission for shared semantic models](https://learn.microsoft.com/en-us/power-bi/connect-data/service-datasets-build-permissions)，查询日期 2026-08-11 | Remote 生产化前确认账号、工作区访问和目标模型 Build | 已确认 |
| Schema 工具 | Get Semantic Model Schema 返回表、列、度量值、关系、类型、层级与可用 AI 元数据 | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | M2.2 映射为现有 `SemanticModelSchema` | 已确认能力；响应待验 |
| DAX 执行工具 | Execute Query 接收 semantic model ID 与 DAX，在认证用户上下文执行 | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | M2.3 映射为现有 `QueryResult` | 已确认能力；响应待验 |
| 官方工具集合 | 当前逻辑工具为 Execute Query、Get Semantic Model Schema、Get Report Metadata、Generate Query | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | M2 只白名单 Schema + Execute；精确 MCP 标识以 `list_tools` 为准 | 已确认逻辑集合 |
| Generate Query 策略 | 官方允许禁用并由客户端 LLM 直接生成 DAX；该工具还要求 Copilot license/capacity | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | 禁用/不调用，避免形成第二个 DAX 生成入口 | accepted |
| Token 策略 | SDK `TokenStorage` 管 access/refresh token 与 client info，自动刷新；存储可替换 | [OAuth clients — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | Smoke 可内存；复用需系统安全存储，禁止明文文件、`.env`、日志和 Trace | 总体确认；Remote 后端待验 |
| 用户委托与 RLS | 用户认证按其权限执行并强制 RLS；Service Principal 当前不支持 RLS | [Remote Power BI MCP server tools](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-tools)，查询日期 2026-08-11 | 内部 MVP 选用户委托；Client Credentials/SP 不作为 M2 主路径 | accepted |
| Error handling | 工具失败可由 `is_error` 返回；OAuth 失败有结构化异常；Power BI Preview 文档未承诺 429/Retry-After 契约 | [The Client](https://py.sdk.modelcontextprotocol.io/client/) 与 [OAuth clients](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | Adapter 统一标准化；401 刷新一次，403/DAX/畸形/超大不掩盖，429 待实机 | 部分待 M2.3 验证 |
| CI 策略 | 官方 SDK 支持 in-memory Client 作为测试通道；真实 OAuth 必须经 HTTP/browser | [Client transports](https://py.sdk.modelcontextprotocol.io/client/transports/) 与 [OAuth clients](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/)，查询日期 2026-08-11 | CI 用 Fake/Stub Session 与脱敏 Fixture；真实 MCP 仅人工 Smoke | accepted |

结论：ADR-003 的 Remote MCP、Entra App 与 Adapter 方向仍正确；ADR-006 生产化证据完整保留。当前外部管理员条件只使该路径 Deferred，不代表 Remote 方案失败。

## 3. Local Demo 官方证据

| 决策项 | 官方结论 | 项目决定 |
|---|---|---|
| Server / package | Microsoft 官方 Local Modeling MCP Server；npm 包为 `@microsoft/powerbi-modeling-mcp`，Public Preview | M2.1/M2.2 实机验证固定 `0.5.0-beta.12`，不使用 `@latest`；Preview 升级必须重新 Smoke |
| npm 可复现性 | 2026-08-11 通过 npm CLI 验证公开 versions、dist-tags、精确版本查询，并用全新隔离缓存重新解析 beta.12；精确版本公开可获取，查询时 `latest` dist-tag 为 beta.12 | 保留实机固定版本，不随 dist-tag 漂移 |
| Runtime / transport | Microsoft Learn 要求 Local 路径使用 Windows 上的 Node.js 20+ / npx；transport 为 stdio | Node/npm 是外部运行时，不写入 Python 依赖 |
| 启动方式 | 官方配置以 `npx -y <package> --start` 启动 | 项目增加 `--readonly`，禁止 M2.1 写模型 |
| Python Client | MCP Python SDK v2 高层 `Client` 接受 `stdio_client(StdioServerParameters(...))`，上下文进入时连接并协商协议 | 锁定 `mcp==2.0.0`；SDK 只存在于 `backend/app/powerbi/` |
| Desktop connection | `connection_operations` 连接 Power BI Desktop 或 Fabric；官方 ConnectToPowerBIDesktop prompt 会搜索并连接匹配实例 | M2.1 仅执行 `ListLocalInstances` 与 `Connect`，不读取模型元数据 |
| Schema capability | Local Server 按 `model/table/column/measure/relationship/user_hierarchy` 等 `*_operations` 分组 | M2.1 只发现能力；M2.2 依据真实返回决定 Schema 契约扩展 |
| DAX capability | `dax_query_operations` 支持执行与验证 DAX | M2.1 只发现能力；M2.3 才允许执行 DAX |
| Safety | 官方支持 `--readonly`；默认 read-write 会暴露大量建模操作 | Demo 强制只读；M2.1 业务允许工具集合仅含 `connection_operations`，写工具不进入 ToolGateway / LLM |

官方来源：[Microsoft Learn MCP overview](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)、[Microsoft Power BI Modeling MCP GitHub](https://github.com/microsoft/powerbi-modeling-mcp)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)。查询日期均为 2026-08-11。

## 4. 当前代码到 M2 目标映射

### LocalMCPPowerBIAdapter

- M2.1：正式 `mcp` Client 通过 stdio 启动固定版本的官方 Local Server，只实现 `health_check()`、协议/工具发现、Desktop 发现与连接。
- M2.2：`get_semantic_model_schema()` 已在一次 stdio / Desktop 连接生命周期内读取并映射真实 Schema；上层只接收 `SemanticModelSchema`。
- M2.3：`execute_dax()` 与结果标准化继续明确 `NotImplementedError`。
- 安全：强制只读、诊断不包含 PBIX 路径、模型名、连接串或业务数据；失败不回退 Mock。

### RemoteMCPPowerBIAdapter

保持 ADR-006 生产化骨架，所有 Remote OAuth / transport /业务方法仍未实现。当前 Demo 不提交 Entra OAuth、PKCE callback、TokenStorage 或 Remote smoke 半成品。

### 上层控制面

- `DeepSeekTurnService`、`main.py`、`routes.py`、TurnPipeline、ToolGateway、Intent、QueryPlan、DAX、Answer、ReportSpec、Memory / Snapshot 在 M2.1 均不修改。
- M2.4 只能把 Local Adapter 注入现有组合根并传播真实 `source_mode`；不得复制 Service / Pipeline。
- ToolGateway 未来仍只看到 PowerBIAdapter 的 Schema 与 DAX 两类抽象能力，不直接依赖 Local / Remote SDK 工具名。

### Settings

版本为 M2.2；Local 配置增加 friendly `local_desktop_model` key，不接受端口、数据库名、PBIX 路径或连接串作为业务输入。Remote 历史配置保留，Local 不要求 Tenant ID、Client ID 或 Redirect URI；M2.4 前 Local / Remote 模式均不代表 Chat ready。

## 5. M2.0—M2.5 当前 Demo 路线

### M2.0｜官方证据复核、架构设计与路线固化

**状态：** ✅ 已完成候选。Remote 生产化证据与 ADR-006 保留。

### M2.1｜Local MCP 最小真实连接验证

**状态：** ✅ 已完成候选。已证明 `stdio → initialize/协议协商 → list_tools → Desktop discovery → Desktop connection`。未读取完整 Schema、未执行 DAX、未调用 DeepSeek、未接 Chat。

### M2.2｜真实 Semantic Model Schema 接入

**状态：✅ 已完成候选。** Local Adapter 通过五类工具的 `List` / `Get` 读取真实 tables、columns、measures、relationships 与 hierarchies，并映射到现有 `SemanticModelSchema`。业务语义 Grounding 已获得真实 Measure、expression、data type、表归属与基础关系输入；未执行 DAX。

### M2.3｜真实 DAX 执行与 QueryResult 标准化

**下一阶段。** 完成 `DAXRequest → ToolGateway → Local Adapter → Local MCP → Power BI Desktop → QueryResult`；DeepSeek 尚不接 Chat。

### M2.4｜接入现有 TurnPipeline

跑通 `用户问题 → DeepSeek → QueryPlan → DAX → ToolGateway → Local MCP → Power BI Desktop → QueryResult → Answer`，保持单一 Pipeline、单一 DAX 入口与无静默回退。

### M2.5｜真实 Demo 全链路验收

通过 Harness / Golden 验证 Schema 真实性、DAX 业务语义与执行、QueryResult、Answer、幂等、Trace、Mock 回归和架构无偏移。

Remote 生产化不塞入当前 M2.1—M2.5 Demo 路线；管理员前置条件具备后，按 ADR-006 并经用户另行批准恢复。

## 6. 每轮 M2 防偏移门禁

每轮修改生产代码前必须确认：职责属于已有模块、复用 PowerBIAdapter、业务 Power BI 调用经过 ToolGateway、TurnPipeline 仍是控制面。出现第二套 Real Pipeline、Service/API/LLM 直连 MCP、LLM 自主调用工具、Real → Mock 回退或提前开发 M3/M4/M5时立即停止。

## 7. 测试与验收边界

- CI 完全离线，不启动 Node、Local Server 或 Power BI Desktop，不使用 Microsoft Token 或 DeepSeek Key。
- MCP Client 使用 Fake boundary；优先补充已有 Power BI / Settings / Harness 测试，不创建版本型测试文件。
- 自动 CI 通过 Fake MCP `List` / `Get` 响应验证 Local Adapter → `SemanticModelSchema`；不启动 Node 或 Desktop。
- 真实 Local MCP 只跑人工 Smoke；不记录 PBIX 路径、模型名、连接串、业务数据、Measure expression 全文或原始响应。
- M2.2 的 DAX 执行与 DeepSeek 调用均为 0；Golden 真实 Power BI Case 继续 pending / skipped。

## 8. 外部前置与停止条件

### Local Demo

必须是 Windows，Node.js 20+、npm/npx 与官方 Local Server 命令可用，Power BI Desktop 已启动且打开测试 PBIX。Desktop 未发现、连接失败或 npm 网络失败时按 `LOCAL_PREREQUISITE / MCP_STARTUP / MCP_PROTOCOL / DESKTOP_NOT_FOUND / DESKTOP_CONNECTION / NETWORK` 分类，不改代码碰运气。

### Remote Production（Deferred）

Tenant 管理员启用 Remote MCP Preview、同 Tenant Entra App、委托权限、redirect URI 与目标模型权限仍是 ADR-006 恢复条件。当前 Demo 不尝试登录或绕过这些治理条件。

## 9. M2.1 实机观察

- Local Server：M2.1/M2.2 实机验证固定 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`，通过 `npx` 以 `--start --readonly` 启动。
- Python Client：官方 `mcp==2.0.0` 高层 `Client` + `stdio_client`。
- 协议：成功协商 `2025-11-25`；`list_tools` 返回 21 个工具。
- Desktop：`ListLocalInstances` 检测成功，`Connect` 后由 `ListConnections` 验证连接成功。
- 相关能力：`connection_operations`；Schema 相关 `table_operations`、`column_operations`、`measure_operations`、`relationship_operations`、`user_hierarchy_operations`；DAX 相关 `dax_query_operations`。分组工具的 input schema 顶层为 object；本轮真实使用的连接工具采用 `request` envelope，M2.2/M2.3 再依据具体 operation 的真实结构扩展业务契约。
- 安全：业务允许集合在 M2.1 仅含 `connection_operations`；大量建模写工具虽然可发现，但未进入 ToolGateway / LLM，且 Server 处于只读模式。
- 调用计数：完整 Schema 读取 0，DAX 执行 0，DeepSeek 调用 0。

## 10. M2.2 实机 Schema 观察

- **真实读取操作：** `table_operations`、`column_operations`、`measure_operations`、`relationship_operations`、`user_hierarchy_operations`；每类仅允许 `List` 与 `Get`。Server `--readonly` 与 Adapter operation whitelist 形成双层只读边界。
- **响应形状摘要：** `List` 返回 `operation/message/data`；Table 与 Relationship 为扁平 data 列表，Column 与 Measure 按 `tableName` 分组，Hierarchy 为 `tableName + hierarchy + levels`。`Get` 返回 `results/summary`，每个 result 的 `data` 是对象详情。未知字段被忽略，缺少必需结构、对象归属不一致或失败 item 会标准化失败。
- **真实契约字段：** Table 新增可选 `description`、`is_hidden`、`is_system_managed`；Column 新增可选 `description`；Measure 新增可选 `description`、`is_hidden`；Relationship 新增 `is_active` 与可选双向 cardinality。旧 fixture 依赖的字段及 defaults 保持兼容。
- **Grounding：** 实机读取 3 tables、19 columns、2 measures、1 relationship、2 hierarchies；`Total Sales`、`Total Quantity` 均归属正确并识别为 Measure，expression 与 data type 非空；`Quantity`、`UnitPrice` 等列保持 Column 身份。
- **未实现 metadata：** Local `Get` 的 Table/Column/Measure/Hierarchy description 字段在当前测试模型中存在但为空；未返回 Prep for AI / Copilot 专用 metadata，因此未扩展此类字段。annotations / extendedProperties 未作为 AI metadata 猜测映射。
- **安全与范围：** 对外只接受 friendly `local_desktop_model`；隐藏/系统管理标志被保留，避免把 Local 明确返回的系统对象误当业务表。人工 Smoke 不输出完整 Schema、expression、连接信息或业务数据。DAX 执行 0，DeepSeek 调用 0。

## 11. M2.3 已知 Preview 风险

- Microsoft 官方仓库未关闭 [Issue #124](https://github.com/microsoft/powerbi-modeling-mcp/issues/124)（查询日期 2026-08-11）报告 0.5.x 的 `dax_query_operations Execute` 可能成功执行并返回 metrics，却缺少 row data。其报告客户端/版本与本项目不完全相同，因此这是明确的兼容性风险，不是本项目已复现结论。
- M2.3 必须用当前固定 beta.12、官方 Python MCP SDK 与本项目 stdio 边界实机验证 Execute 的 columns / rows / rowCount / execution time 响应；不得在 M2.2 写 workaround，不得未经用户批准切换 REST/XMLA 或并行固定另一版本。

---

*最后更新：2026-08-11 | M2.2 真实 Semantic Model Schema 接入完成候选；Remote 生产化路径保留*
