# ADR-020 — Fabric IQ Cloud Consumption Contract & Cloud Model Discovery Authority

- **Status: ACCEPTED**
- **日期：** 2026-10-09
- **决策范围：** M6.0 消费架构/身份/目录/UX合同；不包含production implementation或部署授权。
- **依据：** [M6.0 official/runtime evidence与完整handoff](../milestones/m6/m6_0_fabric_iq_cloud_contract_audit.md)。

## 背景

ADR-006已SUPERSEDED，legacy RemoteMCP仍未实现。M5确定性factual chain保持Frozen。
2026-10-09重新读取Microsoft官方Fabric IQ GA合同，现有delegated客户端实际连接、加载6个tools、
两个已知模型resolve/schema/scalar/grouped通过；名称搜索仍empty；虚构URL可以parse，后续schema拒绝。
因此不能把name search或URL parse当作目录完整性/授权authority。

## 决策

1. Cloud consumption data plane选Fabric IQ MCP，默认
   `https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq`，Streamable HTTP，Entra delegated user。
   required Power BI Service scopes为Item.Read.All/Item.Execute.All/Dataset.Read.All；不支持service
   principal/application-only。私链endpoint只允许显式部署配置，禁止故障自动fallback。
2. future transport固定`X-Variants: Fabric.Routing.FabricIQ.V1`于全部MCP请求；运行时tools/list为
   tool/inputschema authority，必需capability不足failclosed。当前CLI测的是defaultcontract，
   不是fixedheaderwire attestation；M6.2实现启用前必须验证pin/fingerprint/normalizedfixtures。
3. 新`FabricIQPowerBIAdapter`设计复用PowerBIAdapter/ToolGateway/既有deterministic DAX与result
   inspection；不实现、不填入旧RemoteMCP。schema/query完整性不足禁止产出事实；不造expression、
   hiddenflags、relationship方向或truncation=false。未来DTO最小扩展需独立scope。
4. Resolve是管理员配置/deeplink bootstrap；schema/access验证之后才能binding。Discover仅候选搜索。
   M6.4权威目录由**Fabric REST current-principal workspace + semanticModels/reports分页**的
   Cloud CatalogService提供，后续增加delegatedWorkspace.Read.All。
5. REST的Viewer前提意味着individual-share资源覆盖存在缺口。server/admin维护seed资源集，
   经当前principal真实access验证并入；coverage必须声明scope/partial。不能声称列出未配置的所有
   individually-shared模型；不能要求普通用户输入URL/ID弥补，也不能靠adminscanner/SP扩大权限。
6. DataPlane管resolve/schema/value/query；ControlPlane管catalog/metadata及以后另行授权的
   refresh/lifecycle/embed。可以facade委托目录service，不为分层强拆Core。
7. key opaque/server-owned/principal-bound；CloudSemanticModelRef与PrincipalContext置于
   Adapter/catalog/Auth边界，URL不作长期key。validatedprincipal+Microsoft response才是authority；
   客户端ID不授予权限；所有cache/history/report/Memory资源按tenant/principal ownership隔离。
8. M6.1推荐same-origin **BFF opaque session + backend confidential authorization code/PKCE**。
   Auth负责acquire/refresh/logout，Transport注入token；React/通用domain/persistence/prompt/trace
   无token。需要Webredirect与confidentialcredential，仅M6.1开始时配置，当前不修改Entra。
9. RLS/OLS继承调用者权限。M6.3使用UserA/B受限Viewer验证；当前单账号不是RLS验收。
   failure通过现有单一typedmapper最小扩展，不一律500、不rawmessage泄漏、不静默Local/Mock fallback。
10. Product UX保持Chat-first，CurrentChatGPTWeb为layout/UXreference、当前PowerBIAgent为visual
    authority。本次reference可靠访问受限已披露；只做保守contract。普通用户登录→自动目录→选择→问数，
    不输入基础设施字段；切模型新conversation；logout/epoch清理防跨用户泄漏。

## 备选与tradeoff

- IQ Discover单一目录：实现简单，但本tenant已知模型搜索empty、无穷尽性证据，拒绝。
- 仅URL配置：bootstrap稳定但普通用户配置体验不合格，只保留管理员补充资源路径。
- Power BI REST Groups/Datasets/Reports：可行替代，权限/元数据与scope组合不同；当前选择Fabric
  REST统一workspace/itemcatalog，不引入隐式多provider fallback。
- SPA PKCE：publicclient无需secret，但JS持token/refresh、XSS面与OBO/APIaudience复杂度更高；
  BFF增加CSRF/session/credential运维，却更适合当前React→FastAPI→delegatedMCP结构。
- 直接复用旧RemoteMCP/OAuth SDK假设：过时endpoint与未验证tokenstorage不构成productioncontract。

## 后果与验收边界

本决策有official+两模型runtime支持，故ACCEPTED；接受的是边界设计，不声称所有未来能力已验证。
固定selectorwire、customappOAuth、RESTcatalogruntime、PK/FK完整schema映射、大结果/timeout与
双账号RLS/OLS分别是M6.1/2/3/4入口门槛。nameempty与referencepartiallyunavailable是已分类限制，
不把核心Cloudsmoke判为BLOCKED。
M6.0productionbehaviorchange=0，M5Core不解冻；M6.5公开真实商业数据验证纳入路线；M6.6最终生产
readiness独立验收。旧ADR-006的endpoint/previewstatus/SDKOAuth自动负责全部生命周期/预注册client
注入/旧工具名与friendlykey白名单足以授权等假设正式废弃；ToolGateway/Adapter/no-fallback原则保留。

## 官方来源

- [Fabric IQ MCP，GA/endpoint/auth/tools/selector/RLS](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)，读取2026-10-09，更新2026-09-15。
- [Fabric Workspaces listing](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/list-workspaces) 与
  [SemanticModels listing](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/list-semantic-models)，v1，读取2026-10-09。
- [Microsoft code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow) 与
  [OIDC/BFF guidance](https://learn.microsoft.com/en-us/aspnet/core/security/authentication/configure-oidc-web-authentication?view=aspnetcore-10.0)，读取2026-10-09；应用到FastAPI为本项目架构判断。
- [Power BI RLS](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security)，读取2026-10-09。
