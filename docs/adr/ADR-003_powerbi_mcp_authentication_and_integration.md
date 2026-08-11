# ADR-003 — Power BI MCP 认证与接入方案

- **状态：** partially superseded by ADR-006
- **日期：** 2026-07-31
- **决策者：** PowerBIAgent 项目组

---

> **后续状态说明（2026-08-11）：** Remote MCP、Entra App、PowerBIAdapter 隔离方向继续有效；Device Code + 独立 MSAL + 本地缓存文件的实现选择，以及自动 Fallback 设想，由 ADR-006 的官方 MCP Python SDK、Authorization Code + PKCE、受控 TokenStorage 和显式失败边界替代。本文保留为历史决策上下文。

## 一、Context

PowerBIAgent 需要通过 Power BI MCP 连接 Power BI 语义模型，读取模型结构和执行 DAX 查询。MVP 使用项目负责人的 Microsoft 账号，后端统一连接 MCP。

Microsoft 提供两种 MCP Server：
1. **Remote MCP Server** (Fabric-hosted) — `https://api.fabric.microsoft.com/v1/mcp/powerbi`，Streamable HTTP + Entra ID OAuth
2. **Local MCP Server** — 本地 stdio 进程

核心认证挑战：VS Code 等预注册客户端可自动获得 Client ID，但自定义 FastAPI 客户端必须手动注册 Entra Application。

## 二、当前产品使用方式

- 项目负责人使用个人 Microsoft 账号
- 目标：访问个人 Power BI 工作区中的语义模型
- 仅需只读查询权限
- MVP 单用户，不处理 RLS 和多用户

## 三、接入方式比较

| 方式 | 优点 | 缺点 | 适用性 |
|------|------|------|--------|
| Remote MCP (Fabric) | 官方支持、Streamable HTTP、无需本地进程 | 需 Entra App Registration、早期 2026 年有中断报告 | M2 目标方案 |
| Local MCP Server | 标准 MCP stdio、可自定义、python 实现 | 需本地运行、需自行管理认证 | 备选方案 |
| 直接调用 Power BI REST API + XMLA | 最大控制权、无 MCP 依赖 | 需自行处理 DAX 执行、失去 MCP 工具抽象 | M2 降级方案 |
| 社区 proxy (`powerbi-mcp-proxy`) | 解决 Microsoft 端点 bug | 额外维护负担、非官方 | 仅在 Microsoft 端点不可用时 |

**Decision：M2 优先使用 Remote MCP Server，M0.3 完成设计、接口和 Mock，Remote 骨架。**

## 四、认证流程

### Entra App Registration

必须在 Microsoft Entra 管理中心创建应用注册：

1. **名称：** PowerBIAgent MCP Client
2. **账户类型：** 仅此组织目录（单租户）
3. **重定向 URI：** 需根据 MCP Client 类型配置
   - 对于自定义 FastAPI 后端（非预注册客户端），可能为 `http://localhost:8000/auth/callback`
4. **允许公共客户端流：** 否（除非使用 device code flow）

### 委托权限

需要向 Power BI Service API (`https://analysis.windows.net/powerbi/api`) 授予：

| 权限 | 说明 | 类型 |
|------|------|------|
| `Dataset.Read.All` | 读取所有可访问的语义模型 | 委托 |
| `Workspace.Read.All` | 读取可访问的工作区 **(待验证)** | 委托 |

**注意：** `MLModel.Execute.All` 在某些文档中被提及，但 Power BI 语义模型查询需要的是 **Build 权限** 而非 ML 执行权限。具体权限组合待 M2 实机验证。

### Power BI Build 权限

- 用户需要目标语义模型的 **Build** 权限
- 在工作区中授予：语义模型 → 管理权限 → 添加用户 → Build
- 或在 Tenant 设置中启用 "允许用户使用 Power BI MCP Server 端点（预览）"

### Tenant 设置

Power BI 管理员必须启用：
- "Users can use the Power BI Model Context Protocol server endpoint (preview)"

### Token 获取方式

| 方式 | 说明 | 适用阶段 |
|------|------|---------|
| `az account get-access-token` | Azure CLI 获取 token，手动注入 | M2 早期验证 |
| MSAL device code flow | 浏览器登录 + 本地缓存 refresh token | M2 开发 |
| Service Principal (client secret) | 自动化，适合生产 | 延后（需权限） |
| OBO (On-Behalf-Of) flow | 多用户场景，需前端传 token | M5+ |

**M2 决策：优先使用 MSAL device code flow + 本地 token 缓存。**

### Token 刷新和存储

- Token 有效期通常 1 小时
- 使用 MSAL 的自动 refresh token 机制
- Token 存储：M2 使用内存 + MSAL cache 文件；生产阶段使用系统 Keyring 或 Azure Key Vault
- M0.3 不存储任何真实 Token

### 安全约束

- Token 不写入日志、Trace 或 Git
- Token 不使用环境变量明文持久化（`.env` 除外且在 `.gitignore` 中）
- 登录失效时返回明确 401，不静默降级
- `repr`、日志和 Trace 必须过滤 OAuth Token

## 五、Python MCP Client 认证

### 携带 Token 方式

Remote MCP Server 使用 Streamable HTTP，Python MCP Client (`mcp` 或 `fastmcp`) 需要在 HTTP 请求中携带 Bearer Token：

```python
# 通过 httpx 自定义 headers
headers = {"Authorization": f"Bearer {access_token}"}
```

**重要：** `fastmcp` 3.4.5 已安装在当前环境中。M2 需验证其认证注入方式。

### VS Code 预注册客户端与自定义客户端的区别

| | VS Code | 自定义 FastAPI 客户端 |
|------|--------|----------------------|
| Client ID | 微软预注册 | 需自行在 Entra 注册 |
| 重定向 URI | VS Code 内置 | 需自行配置 |
| 认证流程 | 自动完成 | 需实现 MSAL flow |
| Token 管理 | 框架管理 | 需自行管理 |

**结论：VS Code 能访问 Power BI 不代表自定义 FastAPI 客户端已可用。M0.3 必须完成 Entra App Registration 调研和设计，但不需要实机注册。**

## 六、超时、重试和错误分类

| 错误类型 | 说明 | 重试 | M0.3 |
|---------|------|------|------|
| 认证失败 (401) | Token 过期或无效 | 刷新后重试 1 次 | Mock 场景 |
| 权限不足 (403) | 无 Build 权限 | 不重试 | Mock 场景 |
| 模型不存在 (404) | semantic_model_key 无效 | 不重试 | Mock 场景 |
| 超时 | 查询超过 timeout | 重试 1 次 | Mock 场景 |
| DAX 错误 | 语法或语义错误 | 不重试（修复 DAX） | Mock 场景 |
| 服务不可用 (503) | MCP 端点故障 | 指数退避重试 | Mock 场景 |
| 限流 (429) | 请求过于频繁 | 等待后重试 | 暂不处理 |

## 七、Schema 缓存边界

- M0.3：Mock Schema 直接从 Fixture 读取
- M2：真实 Schema 首次获取后缓存到内存，会话内复用
- M3+：可持久化缓存（文件或 SQLite）
- Schema 变更时不自动刷新，需用户手动触发

## 八、M0.3/M2/M3 边界

| 项目 | M0.3 | M2 | M3 |
|------|------|----|----|
| PowerBIAdapter 接口 | ✅ 完整定义 | — | — |
| MockPowerBIAdapter | ✅ 可运行 | — | — |
| Remote Adapter | ✅ 骨架 (NotImplementedError) | ✅ 真实连接 | — |
| OAuth/Token | ✅ 设计文档 | ✅ MSAL 实现 | — |
| 真实 DAX 查询 | ❌ | ✅ | — |
| Schema 持久化缓存 | ❌ | ❌ | ✅ |
| 报表数据查询 | ❌ | ✅ | ✅ |

## 九、Decision

1. **M2 使用 Remote MCP Server** (`https://api.fabric.microsoft.com/v1/mcp/powerbi`)
2. **M2 使用 MSAL device code flow** 进行认证
3. **M0.3 完成 PowerBIAdapter 接口、Mock 实现和 Remote 骨架**
4. **M0.3 不进行真实 Microsoft 登录或 Power BI 连接**

## 十、Consequences

**正面：**
- Remote MCP Server 是官方支持的标准方式
- MSAL 提供成熟的 Python 认证库
- Mock Adapter 保证 M0.3 无外部依赖运行

**负面：**
- Entra App Registration 需要 Azure 管理员权限（可能阻塞 M2）
- Microsoft 端点早期 2026 年有中断报告（需关注）
- Tenant 设置需要 Power BI 管理员启用（可能阻塞 M2）

## 十一、Risks

| 风险 | 缓解措施 | 状态 |
|------|---------|------|
| Entra App Registration 权限不足 | M2 早期验证，必要时使用 `az login` 手动获取 token | 待验证 |
| Remote MCP 端点不稳定 | 备选：Local MCP Server 或直接 REST API + XMLA | 关注中 |
| Tenant 设置未启用 | 联系 Power BI 管理员提前确认 | M2 前确认 |
| Build 权限未授予 | 确认目标语义模型权限 | M2 前确认 |
| 预览功能 Breaking Changes | 通过 Adapter 隔离，关注 Microsoft 更新 | 持续 |

## 十二、Fallback

如果 Remote MCP Server 不可用：
1. 使用社区 `powerbi-mcp-server` (npm/stdio) 或 Python 本地 MCP Server
2. 直接调用 Power BI REST API + XMLA endpoint 执行 DAX
3. 以上两种方式均需 Backend Adapter 隔离，不改变 Agent 层接口

## 十三、待验证事项

- [ ] Power BI 管理员是否已启用 "Users can use MCP server endpoint"
- [ ] 项目负责人是否有 Entra App Registration 权限
- [ ] 目标语义模型是否已授予 Build 权限
- [ ] Remote MCP Server 端点在当前 Tenant 是否可用
- [ ] `fastmcp` 3.4.5 的认证注入 API
- [ ] MSAL device code flow 是否适用于服务端场景

*检索日期：2026-07-31 | 来源：Microsoft Learn (learn.microsoft.com) Power BI MCP 文档*

---

*创建日期：2026-07-31 | 2026-08-11 认证实现部分由 ADR-006 替代*
