# M6.0 — Fabric IQ Cloud Contract Audit & Accepted Cloud Consumption Contract

日期：2026-10-09。Phase A：RELEASE CANDIDATE。Settings.version=M5.10.9。
M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN。
本阶段仅研究、只读 probe、设计与文档；M6 production runtime implemented: NO。
正式决策见 [ADR-020](../../adr/ADR-020_fabric_iq_cloud_consumption_and_catalog_authority.md)。

## 1. M6.0 CURRENT REALITY AUDIT

| Cold Start | Fresh evidence |
|---|---|
| branch | main |
| initial HEAD / fetched origin/main | 6405c942c13f7ae0781f94c52865150aea8775e8 |
| initial worktree | clean；无 merge/rebase/cherry-pick |
| baseline commit | M5.10.9_FIX_CI稳定性修复与最终封板 |
| exact baseline CI | [37873468783](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37873468783)，completed/success，exact SHA 匹配 |
| Settings.version | M5.10.9 |
| Frozen Core | 全部既有 factual authority 保持冻结 |
| scope decision | ALLOWED：M6.0 audit/design；不包含 M6.1/6.2 implementation |

修改前执行 status → branch → HEAD/origin → log -8 → fetch → status/HEAD/origin。
依次阅读 AGENTS、PROJECT_CHARTER、CLAUDE、PRD、07/08/09、README、CHANGELOG、Error Ledger、
ADR 索引/006 与相关 accepted ADR；审计 base/local_mcp/remote_mcp、Settings、ToolGateway、
discovery、schema/result/error DTO、report eligibility 与邻近 tests、frontend 与 CI。

当前 `PowerBIAdapter`：health_check、get_semantic_model_schema、execute_dax、normalize_result、
normalize_error 为抽象接口；另有 get_column_members、discover_semantic_models、probe_compatibility、
aclose、owns_transport_retries 与 provider_name/is_mock。ToolGateway 是既有调用入口。
Local MCP 已有 Desktop discovery、schema normalization、bounded member/query 与 compatibility；
`RemoteMCPPowerBIAdapter` 只有 constructor/properties，核心方法均 NotImplementedError，旧默认
`/v1/mcp/powerbi` 与 ADR-006 异常措辞仍为 historical/deferred debt，不修改、不复用为 Fabric IQ 实现。
QueryResult 的完整性/形状验证、PowerBIError 与 FailureInfo 是现有消费边界，云端不得绕过。

## 2. Official Contract Evidence

所有下列页面于 **2026-10-09** 重新联网读取。未显示最后更新时间的页面记为未提供；
REST 的 v1/无 preview 标记不自动等同于额外 GA 公告。Microsoft 文档是外部合同 authority，
运行时是本 tenant 的实际证据；PREP、旧 ADR、CLI 模型解释均不替代官方合同。

| ID / 官方页面标题与 URL | status / 最后更新 | 关键事实 | 与本次 runtime |
|---|---|---|---|
| F1 [Get started with the Fabric IQ MCP server](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp) | GA；2026-09-15 | endpoint、Streamable HTTP、delegated-only、六工具、selector、只读与现有权限 | connection/schema/query 一致；名称搜索 empty 为已知限制 |
| F2 [Workspaces - List Workspaces](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/list-workspaces) | v1；无 preview 标记；更新时间未提供 | current-principal workspace listing；Workspace.Read.All；pagination/429 | 本轮只设计，未用 Copilot token 调 REST |
| F3 [Items - List Items](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items) | v1；无 preview 标记；未提供 | workspace Viewer 前提、类型筛选、分页 | 未实测 |
| F4 [Items - List Semantic Models](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/list-semantic-models) | v1；无 preview 标记；未提供 | Viewer、Workspace.Read.All、semanticModels、folders/continuation | 未实测 |
| F5 [Items - List Reports](https://learn.microsoft.com/en-us/rest/api/fabric/report/items/list-reports) | v1；无 preview 标记；未提供 | reports listing；Viewer 与分页 | 未实测 |
| F6 [Groups - Get Groups](https://learn.microsoft.com/en-us/rest/api/power-bi/groups/get-groups) | REST v1.0；无 preview 标记；未提供 | Power BI workspace catalog alternative；权限传播可能延迟 | 未实测 |
| F7 [Datasets - Get Datasets In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-datasets-in-group) | REST v1.0；无 preview 标记；未提供 | Dataset.Read.All；只读权限可能只返回部分属性 | 未实测 |
| F8 [Reports - Get Reports In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/reports/get-reports-in-group) | REST v1.0；无 preview 标记；未提供 | Report.Read.All；report catalog alternative | 未实测 |
| A1 [Microsoft identity platform and OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow) | 稳定协议文档；2026-01-09 | code、PKCE、redirect、confidential client credential | custom app flow 留 M6.1 |
| A2 [OAuth 2.0 On-Behalf-Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow) | 稳定协议文档；2025-01-04 | API audience incoming token 才可 OBO downstream | 本轮不实施 |
| A3 [Refresh tokens in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens) | 稳定文档；2025-11-05 | refresh lifecycle/revocation | 本轮未读取 token |
| A4 [Configure OpenID Connect Web (UI) authentication in ASP.NET Core](https://learn.microsoft.com/en-us/aspnet/core/security/authentication/configure-oidc-web-authentication?view=aspnetcore-10.0) | 稳定指南；2026-09-20 | confidential OIDC + code/PKCE，BFF 的安全建议 | 应用于 FastAPI 是架构推论，不是 Microsoft FastAPI SDK 承诺 |
| A5 [ID token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference) | 稳定参考；2025-03-27 | validated tid/oid/issuer/audience；display claims 非授权依据 | raw claims 未采集 |
| A6 [Redirect URI (reply URL) best practices and limitations](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url) | 稳定参考；2025-05-14 | 精确注册 Web redirect；localhost port有文档例外，不注册仅端口不同的重复项 | 仅 handoff，不配置 Portal |
| S1 [Row-level security (RLS) with Power BI](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security) | 产品指南；2026-05-13 | RLS 对 Viewer 生效；Admin/Member/Contributor 编辑角色绕过 | 单账号 smoke 不证明 RLS |
| S2 [Object-level security (OLS)](https://learn.microsoft.com/en-us/fabric/security/service-admin-object-level-security) | 产品指南；2026-07-01 | 表/列访问限制 | 双账号 OLS 留 M6.3 |
| U1 [Sign in with Microsoft branding guidelines](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-branding-in-apps) | 品牌指南；2023-12-15 | 官方 Microsoft 登录标识/文案规范 | 设计遵守；本轮不下载/绘制按钮 |
| D1 [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online%2Bretail%2Bii) | 公共数据集；页面更新时间未提供 | 1,067,371 真实交易记录、取消/缺失值 | 只进入路线，不下载 |

### Accepted official endpoint/auth contract

默认：`https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq`，Streamable HTTP。
private-link 部署可显式配置 F1 所列 `https://api.fabric.microsoft.com/v1/mcp/fabriciq`；
这是部署选择，不是故障 fallback。只支持 Entra delegated user OAuth；service principal /
application-only **unsupported**。三项 Power BI Service delegated scopes：
`Item.Read.All`、`Item.Execute.All`、`Dataset.Read.All`。默认不要求 admin consent，但 tenant policy 可要求。
`X-Variants: Fabric.Routing.FabricIQ.V1` 应用于 initialize、tools/list、tools/call；URL v1 不代表工具版本。

用户需 work/school account 与受支持 item 访问权。tenant home region 必须支持全部 Fabric workloads；
Power BI-only region / sovereign clouds 不支持。Fabric/Premium capacity 并非 IQ 通用必要条件；
本环境 Trial/Capacity PASS 不应转写为所有用户必须 Trial。现有 licensing/sharing 权限继续适用。
tenant/admin 负责 consent policy、region 与内容授权；IQ 本身不要求 workspace role/Build，
但选用的 REST catalog 有独立 Viewer 前提。Copilot CLI 是本次验证客户端，不是未来产品依赖。

工具只读；执行调用者已有权限、继承 RLS/OLS；不提供管理员 impersonation、authoring/admin。
每次 ExecuteQuery 针对一个模型。默认 maxRows=250；大响应可能 embedded CSV 且仍可能截断。
官方未给出 MCP 的固定 timeout、最大 row ceiling 或统一 error JSON；不把其他 REST execute API
的数值上限冒充 MCP 合同。小查询成功不证明大结果完整性或 timeout 行为。

## 3. Runtime Probe Evidence

### 方法与 provenance

已有安全 PREP 报告仍存在并已读取：系统 Temp 的
`PowerBIAgent-M6-PREP-20261009/M6-PREP-FabricIQ-Independent-Smoke.md`。
PREP：FABRIC IQ CORE SMOKE PASS WITH KNOWN DISCOVERY LIMITATION。
本次重新运行现有 Copilot CLI 1.0.94 / 已配置 FabricIQ 连接，沿用客户端管理的 delegated OAuth；
未创建 secret/certificate/redirect，未更改 App Registration，未读取 auth cache/token/cookie。
只执行已知自有测试模型的小型只读工具调用；CLI execution cards 证明实际调用，而非只采纳模型自报。
仓库只保存本节 normalized summary，不提交 raw terminal/session/schema/data/auth dump。
tenant/client/resource GUID 与业务结果值均省略。两模型显示名称是用户批准的测试 fixture 名。

证据层级：client-connected handshake + client-loaded tools/list + actual tool cards/result summaries。
未抓取原始 initialize packet/protocolVersion、HTTP headers、raw JSON-RPC 或完整 outputSchema。
既有 CLI 配置无 X-Variants override，因此本轮实测 **default tool contract**；不能声称 wire-level pin
已验证。M6.2 必须在其自有 transport 上验证固定 selector 与 schema fingerprint，作为启用门槛。
这不阻断已知 data-plane 消费架构定稿，也不等于生产 transport 已验收。

### Fresh checks

| Probe | M3 Rich Test | M5_8_5 Logistics Test | Evidence / boundary |
|---|---|---|---|
| OAuth / connection / initialize | PASS | 同一连接 | cached client-managed delegated access 有效；非自建 app OAuth PASS |
| tools/list | PASS | 同一 session | 6 个 client-loaded tools；下表完整 normalized summary |
| ResolveFabricItem(browser URL) | PASS | PASS | SemanticModel；相同 workspace、不同 artifact identity |
| GetSemanticModelSchema | PASS | PASS | 5 tables/4 measures/4 active relationships；4/7/3 |
| scalar query，maxRows=1 | PASS，1 row | PASS，1 row | probe: Double / Int64；无业务值保存 |
| grouped query，maxRows=5 | PASS，4 rows | PASS，5 rows | Region Region:String / DimHub HubName:String + probe |
| DiscoverArtifacts exact display name | empty，0 | empty，0 | artifactTypes SemanticModel/maxResults5；复现 PREP limitation |
| cross-model identity separation | PASS | PASS | identity 与 schema/count 分离；不是 cross-user test |

四条正向 DAX（只列 schema identifiers，不保存返回成员/数值）：

```dax
EVALUATE ROW("probe", [Total Sales])
EVALUATE TOPN(5, SUMMARIZECOLUMNS('Region'[Region], "probe", [Total Sales]), 'Region'[Region], ASC)
ORDER BY 'Region'[Region] ASC
EVALUATE ROW("probe", [Total Shipments])
EVALUATE TOPN(5, SUMMARIZECOLUMNS('DimHub'[HubName], "probe", [Total Shipments]), 'DimHub'[HubName], ASC)
ORDER BY 'DimHub'[HubName] ASC
```

| Negative / diagnostic | Observed | Accepted interpretation |
|---|---|---|
| sentinel model UUID (all-zero) within known workspace URL | resolver 返回 parsed SemanticModel identity；schema 返回 error envelope | parse success 不证明 existence/access；negative PASS：未返回 schema/facts |
| invalid DAX：`EVALUATE __M6_0_INVALID_SYNTAX__` | tool error text，DAX name/syntax rejection；无稳定 code 暴露 | negative PASS；QUERY_REJECTED；不从文字猜 HTTP 状态 |
| naturally inaccessible resource | UNAVAILABLE IN CURRENT TEST ENVIRONMENT | 未访问他人资源；真正 authorization/RLS negative 留 M6.3 |
| initial schema projections | lower-case path / missing Measures 的 keys / unsupported flatten / non-object PK/FK keys 返回 projection errors | 保留失败事实；修正为独立简单 projections 后 schema/count/column/measure PASS；不是 OAuth 故障 |

Resolve output：`fabricItemId:string,itemType:string,workspaceId:string,instructions:string`。
Schema text query 根：`schema:{Tables,ActiveRelationships}`、
`semanticModel:{ArtifactId,Name,Description,Url,IconUrl}`；外层可见 `artifact_citation`。
Tables 的 Name/Columns/Measures，column Name/Type；measure M3 Name/Type，Logistics 可含 FormatString；
relationship keys PK/FK/UnidirectionalFilter。最终简单type projection确认PK/FK为qualified-column
strings，UnidirectionalFilter亦为string；此前keys(non-object)失败已解释。具体delimiter/方向值
与from/to/cardinality仍需M6.2最小脱敏fixture对照，不能根据名字猜或把string直接转bool。
本次未观察 measure Expression、完整 hidden flags、hierarchies、refresh time、security role metadata；
schema 不能证明业务 metric/fact-family、可用时间范围、refresh 或模型没有 OLS。

Query 成功根：`executionResult:object,semanticModel:object`；`executionResult.tables:array`，
table.columns 为 `{name,type}` 数组，rows 为 positional arrays；没有显式 completeness/truncation indicator。
未知 artifact schema failure：`Answer:string,Status:string,Error:object,DurationMs:number`；
Error 下 Code=`InvalidArgument`、Source、HttpStatusCode、Message、IsRetryable、IsUserError。
未保存 Message/ID；client view 未暴露 MCP isError，不能推断 wire isError=false。
无效 DAX 为另一 text error 形态；HTTP 200/tool delivery 成功不可当作业务成功。

### Runtime tool inventory（2026-10-09，client-loaded tools/list）

`FabricIQ-` 是 CLI namespace，不是 server tool name。以下 required/optional 来自客户端加载定义；
描述性限制与 schema constraints 分开。所有 outputSchema 在 client representation 中未声明，
不推断原始服务一定没有 outputSchema。

| Server name / purpose | Required args | Optional args / descriptions | Relevant observed output |
|---|---|---|---|
| DiscoverArtifacts / convenience name search | searchQuery:string | artifactTypes:string[]或null；maxResults:int或null；描述 default5/max50 | 本次只有 no artifacts 文本；非完整 catalog schema |
| ResolveFabricItem / supported browser URL bootstrap | fabricItemId:string | 无 | parsed identity/instructions；非 access proof |
| GetSemanticModelSchema / model metadata | artifactId:string | queries:string[]，client annotation default null；描述 max5 JMESPath projections | schema/semanticModel 与 citation；projection 也可能返回错误 |
| ExecuteQuery / readonly DAX | artifactId:string；daxQueries:string[] | maxRows:int或null；描述 1–4 queries、default250 | tables/columns/rows；成功与 text/structured failure 都需检查 |
| ValueSearch / stored value search | artifactId:string；searchTerms:string[] | scope:array或null，tableName/columnNames optional；描述 terms1–20 | 本轮未调用；不是 bounded distinct enumeration completeness authority |
| GetReportMetadata / report metadata | reportObjectId:string | queries:(string或null)[]或null；描述 max5 | 本轮未调用；不证明 report lifecycle/admin capability |

## 4. Known Limitations 与 accepted readiness

本轮 classification：**FABRIC IQ CORE SMOKE PASS WITH KNOWN DISCOVERY LIMITATION**。
没有把 empty name search 升级为整个 Cloud BLOCKED。双账号、custom-app callback、固定 selector wire、
REST catalog runtime、large-result/timeout、PK/FK 结构和完整 schema metadata 是明确的后续实现门槛，
不是已完成能力。ADR 接受的是消费/授权/目录边界；不批准上线或宣称 M6 production READY。

## 5. Discovery Strategy / Control Plane authority

| Layer | Authority / accepted use | Must not claim |
|---|---|---|
| Resolve bootstrap | 管理员部署配置的 supported browser URL → ResolveFabricItem → validated model identity → schema/access check | URL 是 primary key；parse=授权；普通用户必须复制 URL |
| Convenience search | DiscoverArtifacts 产生候选，后续验证；可改善名称查找 | 空结果=无权限模型；全企业 catalog 完整性 |
| Enterprise catalog | **Fabric REST current-principal Workspaces + per-workspace SemanticModels/Reports，完整分页**；服务端 normalized CatalogService | IQ 搜索是唯一 authority；跨未枚举授权范围的全量保证 |

M6.4 前端自动加载目录明确由 **Cloud CatalogService / PowerBIControlPlane（Fabric REST）**提供。
使用 delegated `Workspace.Read.All`，后续获批阶段才添加/consent；本轮注册权限保持原三项。
列 workspace 后，逐个列 semanticModels/reports，处理 continuation、folder recursion、429、局部失败、
dedup 与 stale。返回 opaque key、safe display_name/workspace_display_name/provider、accessibility、
coverage/status、timestamp；不返回 GUID/URL/token/raw diagnostics。

F4/F5 要 workspace Viewer。IQ 可消费 individual share 且无需 workspace role，故 REST membership
catalog **不保证覆盖所有单独分享资源**。补充服务器/管理员维护的资源 seeds，经当前 principal 的
schema/access check 后并入；用户不输入 URL。此覆盖缺口明确显示 PARTIAL，管理员按正常组织分享
流程配置覆盖，不能把空/denied REST 结果叫 complete empty。M6.4 的 acceptance scope 是已声明的
workspace membership + configured shared-resource set；不能承诺自动找到未配置的任意 individual share。

选择 Fabric REST 的原因：同一 workspace/item family，显式分页与 current-principal contract；
Power BI REST Groups/Datasets/Reports 可行但拆分 scopes/元数据权限形态，不作为隐式 fallback。
如将来切换必须另立有证据的 scope。不能用全 tenant admin scanner/SP 扩大用户可见性。
REST coverage 与每条资源 accessibility 独立；执行时仍由 Microsoft 校验当前权限。

PowerBIDataPlane 负责 resolve/schema/value search/deterministic DAX。IQ 六工具中 Resolve、Schema、
ValueSearch、ExecuteQuery 是消费能力；Discover 是候选查找，GetReportMetadata 是只读上下文。
PowerBIControlPlane 负责 workspace/model/report catalog/metadata，未来 refresh/lifecycle/embed/resource
management 才按 M7/M8 另行授权。不要把 workspace/admin/refresh/embed 塞进 execute_dax。
现有 discover_semantic_models 可由 future facade 委托 CatalogService，保留既有 public contract；
不为理论分层强拆 Frozen ToolGateway 或复制 factual pipeline。

## 6. Accepted Cloud Adapter Contract（设计，未实现）

新 provider 概念名 `FabricIQPowerBIAdapter`；优先新类与 Adapter/catalog DTO 最小扩展，
不往 legacy RemoteMCP 塞实现，不把 CloudSemanticModelRef/PrincipalContext 塞进 factual Core model。

| Existing interface | Future mapping / fail closed |
|---|---|
| health_check | request/session-scoped authenticated MCP initialize + tools/list + required capability validation；bool 不证明所有模型授权；不沿用 optimistic compatibility default |
| get_semantic_model_schema(key) | 服务端 principal-bound key lookup → GetSemanticModelSchema(artifactId) → typed normalize；校验 response identity；必要元数据不足则 capability unavailable |
| execute_dax(DAXRequest) | server-resolved key + 既有 deterministic DAX + safety → ExecuteQuery 单模型/单查询为默认，显式 row budget/deadline；禁止自然语言生成 DAX tool |
| normalize_result | 检查 transport/MCP/structured/text errors、resource identity、tables 数量、column order/type、row arity/count/null、CSV完整性；source_mode=real；不改列名猜语义 |
| normalize_error | 安全分类为 PowerBIError/PowerBIAdapterError → 统一 FailureInfo；上游 raw message 不进入公开 DTO/Trace/Prompt |
| get_column_members | 复用已验证 canonical column 的 deterministic bounded DAX；ValueSearch 仅精确候选搜索，不能冒充完整 distinct set |
| discover_semantic_models | delegation to Cloud CatalogService，保留 normalized frontend catalog；不依赖 name search 完整性 |
| probe_compatibility / aclose | 真实观测 negotiated/tools/schema/query 状态；释放 principal transport；禁止继承默认全 true 作为云验收 |

`CloudSemanticModelRef` 概念字段：server_model_key、tenant_id、workspace/resource identity、semantic_model_id、
display_name、provider/source、principal/security scope、resolved_identity_evidence、validation_epoch、
catalog_coverage。URL 只是 bootstrap input，不作内部长期 primary key。server_model_key 随机 opaque、
server-owned，至少 request/session 范围稳定，server mapping 绑定 tenant/principal/authorization epoch；
客户端 key 仅作 lookup hint，无法自行证明授权，不含 token/可解码 GUID。重新授权必须重新校验 binding。
rename 保持 resource identity 更新 display；move/deletion 不猜迁移，撤销旧 binding 并刷新目录。

Schema normalize 必须区分 unknown 与 false。Measure expression 在现有 DTO 默认空串，
不可填造表达式；隐藏状态/cardinality/方向/事实族无法证明时，在 adapter metadata/capability evidence
标 unknown 并禁止依赖该证据的能力。不能让默认 `is_hidden=False`、`is_active=True` 变成授权事实。
后续 M6.2 若需 DTO 最小扩展须单独 scope；M6.0 不改 Core。schema PASS 不等于 M5 全模板兼容 PASS。

完整性策略：缺 truncation flag 不等于完整。scalar 小单行可凭固定形状校验；bounded top-N 只证明
请求的有界结果；需要完整 set/trend/aggregation coverage 的查询必须有可验证 bound/count/完整资源
evidence，达到预算边界或 CSV 缺失/无法解析则 fail closed/不产出 VerifiedFacts。
不能仅凭 row_count<maxRows 任意声称所有服务端上限均未触发。M6.2 需要 fixtures 覆盖完整、未知、
截断、CSV、multi-table、text error，且不为完成 adapter 放宽 ResultInspection。

## 7. Identity Boundary / OAuth Decision

`PrincipalContext`：validated tenant_id、principal_id(oid；必要时 issuer+sub scoped fallback)、
display-safe identity、auth_source、security_scope/authority_evidence、session/authorization epoch。
email/UPN/name/组织名只用于展示，不能作为授权或 ownership key。tenant allowlist 在服务端验证。
前端 tenant/user/workspace/model ID 均不是权限凭证；authority 来自 validated Entra principal +
Microsoft response。M5 test_user / runtime_mode namespace 不能当作 multi-user identity。

Token 只在 Auth / Transport boundary：AuthService acquire/refresh，库管理 token lifecycle；
Transport 从 Auth broker 获得对应 principal/resource token 并注入 header；logout 由 Auth/session
service 失效 session、删除对应 token cache 与 transport，撤销 binding/transient cache。
不能声称 logout 会立即撤销所有 Microsoft 已签发 access tokens；必要 revoke/CA policy 遵循 Entra。
Token 不进入 UserContext、Memory、Conversation、Snapshot、report metadata、Trace、Error Ledger、
Prompt/LLM context、通用 cache payload、frontend persistence，亦不放入浏览器 session cookie。
Auth 专用 token cache 是唯一受控例外，按 tenant/principal/client/resource 隔离；本轮不实现持久化。

| Flow | Exposure / refresh / multi-user | CSRF / deployment / credential | Decision |
|---|---|---|---|
| SPA/browser code+PKCE | token 在 JS，XSS 可窃取；refresh 在浏览器；调用 backend 需独立 API token | public client 无 secret；CORS；backend downstream 通常需 OBO | 不作为当前主路线 |
| Backend authorization code | token/refresh 在 server；多用户 cache必须隔离 | confidential credential，state/nonce/PKCE、session/CSRF | 作为 BFF 基础 |
| BFF-style opaque session + backend code/PKCE | React 无 Microsoft token；Auth broker持有 refresh；下游保持 delegated | 同源 cookie、CSRF、logout cleanup；需要 confidential credential | **M6.1 推荐** |
| SPA→API OBO | validated API audience incoming token → downstream token；协议/缓存更复杂 | scopes/audience 分离；不能直接转发任意 bearer | 独立 API clients 将来有需要再评估 |
| Device code / client credentials | 前者适合 CLI probe；后者 application-only | 不适合本产品 web UX；IQ 不支持 app-only | 不选 |

推荐 React → same-origin FastAPI BFF → Fabric IQ。采用受支持 identity library，confidential code+PKCE、
OIDC state/nonce、issuer/audience/signature/exp/nbf/tenant 校验；access token audience/resource scopes
独立验证/获取，不把 ID token 发给 IQ，不通过 decode opaque downstream token 假造权限。
opaque session cookie HttpOnly/Secure/SameSite=Lax，旋转 session ID，CSRF token+Origin校验保护
mutation/logout，callback 校验 state/nonce/PKCE；不要把 token 放 cookie。CSP/XSS防御仍需验证。
并发请求不能共享全局 mutable principal/token；refresh 单 principal 协调，失败有界转 AUTH_EXPIRED。
same-origin deployment 优先；local Vite proxy `/auth/*` 与 `/api/*` 到 FastAPI，浏览器统一 localhost。
cross-origin 将增加 CORS/credential/CSRF 复杂度，需另行验收，不能临时允许 wildcard credentials。

**M6.1 开始时才配置 Portal**：已有 single-tenant `PowerBIAgent-M6-Dev`；Authentication 添加 **Web**
redirect `http://localhost:5173/auth/callback`（经 Vite proxy 到 BFF）；production 为精确 HTTPS origin
`/auth/callback`；logout 返回 allowlisted `/auth/signed-out`。最终端口/域在 M6.1 scope 确认后注册，
不要同时混用 localhost/127.0.0.1 或 SPA platform。confidential app 需要后端 credential：开发 secret
或 certificate/assertion 在 M6.1 正式选定/安全配置，production 优先 certificate/assertion；现在不创建。
现有三项 delegated scopes 保持；catalog Workspace.Read.All 的 consent 在获批 catalog scope 增加。
用户尚未 Grant admin consent 并非本轮 blocker；tenant policy 需要时才进入正常 admin workflow。

### P0 threat / implementation verification handoff

| Threat | Required mitigation / negative acceptance |
|---|---|
| OAuth mix-up / login CSRF / replay | server state/nonce/PKCE、issuer/audience/tenant校验、一次性callback；重复/错state拒绝 |
| token theft / XSS / logging | opaque HttpOnly session，React无token；Auth cache与transport redaction；CSP与输出安全；禁止rawauth日志 |
| session fixation / CSRF | 登录旋转session；SameSite配合CSRF/Origin，不单靠cookie标志；logout mutation验证 |
| IDOR / forged model key | 每次principal ownership查验，不信任frontend IDs；他人conversation/report/key负例 |
| confused deputy / wrong audience | Auth broker按resource获取delegatedtoken，禁止任意URL/Authorization header输入 |
| cross-user cache / refresh races | tenant+principal+resource+epoch cache；隔离refresh协调；并发A/B与logout晚到结果测试 |
| stale permission / resource existence oracle | Microsoft最终access检查、清旧binding；公开错误不确认他人资源存在 |
| catalog continuation / malicious deep link | server验证host/path/itemtype、无sharelink；continuation host allowlist，不携token向任意URL |

以上均为M6.1/2/3获批implementation的failure-first入口，不以本次设计表替代安全测试。

## 8. Authorization / RLS / OLS Acceptance Matrix（M6.3）

所有资源读写、Conversation/Memory/Snapshot/Report 下载与列表都要 server-side ownership。
cache key 至少 provider+tenant+principal+resource+authorization epoch+schema/query identity；
schema/member/result/catalog/negative caches 不跨 principal。原 M5 Local caches 不自动证明 Cloud安全。
access check 与 query 仍有 TOCTOU，Microsoft 最终拒绝时清理 binding，ZERO factual commit。

| Case | Required outcome / evidence | Owner / current status |
|---|---|---|
| same tenant allowed | 正确资源 schema/query；identity一致 | 两模型 smoke PASS；customapp/session 留M6.1/2 |
| same tenant denied | 无 schema/facts；不泄漏存在性；不能借他人 key | M6.3；当前无自然 denied fixture |
| cross tenant | issuer/tid allowlist拒绝；无下游调用/跨tenant history | M6.1+M6.3 |
| stale/expired token | 有界 refresh；失败转重新登录；无循环 | M6.1+M6.3 |
| revoked access | 旧 key/cache不能授权；清绑定/目录刷新；ZERO commit | M6.3 |
| RLS User A/B | 同一 deterministic query，两个 Viewer 的授权分区各自匹配独立预期；A→B无cache复用 | M6.3；本轮不创建角色/第二用户 |
| OLS User A/B | 受限表列不可成为schema/grounding/query事实；不从A cache泄漏 | M6.3 |
| deleted resource | 不查询旧映射；safe inaccessible/notfound；重新选模型 | M6.3 |
| moved/renamed model | rename更新显示；move重新resolve/access；旧映射不可猜迁移 | M6.3 |
| insufficient delegated scope | consent/forbidden 分类；无错误事实fallback | M6.1/3 |
| logout A → login B / late response | history/model/report/transient均无A数据；epoch丢弃晚到结果 | M6.1/3/4 |

RLS fixture 必须使用 Viewer/受限消费身份；Admin/Member/Contributor smoke 不能用来证明 RLS隔离。
M6.3 fixture 需用户后续明确授权，不能本轮访问他人资源制造负例。

## 9. Failure Contract（future typed extension，未改现有 enum）

当前 FailureInfo 只有既有 public code/stage/retryable/recovery_action；以下是未来扩展设计。
沿用单一 mapper，扩展 code/recovery enum 必须后续独立获批，禁止另建错误体系。
安全公开 code 和恢复动作；原始 provider message/JSON、资源存在性、scope/claim/token均不透出。

| Future code | Retryable (automatic) | User recovery / public transport semantics |
|---|---|---|
| AUTH_REQUIRED | no | login；401 |
| AUTH_EXPIRED | refresh bounded once；失败no | sign in again；401 |
| AUTH_CONSENT_REQUIRED | no | re-consent / contact admin；403 |
| AUTH_FORBIDDEN | no | contact admin / switch account；403 |
| RESOURCE_NOT_FOUND | no | refresh catalog/select model；404；仅存在性可安全披露时 |
| RESOURCE_NOT_ACCESSIBLE | no | select another/contact admin；404等安全策略避免存在性oracle |
| MODEL_RESOLUTION_FAILED | no | refresh catalog/admin修配置；422 |
| SCHEMA_UNAVAILABLE | conditional transient only | retry/select model；503或安全能力不可用状态 |
| QUERY_REJECTED | no | edit question / select supported model；422 |
| QUERY_TIMEOUT | bounded policy only | retry/narrow scope；504 |
| RATE_LIMITED | yes，Retry-After+backoff+jitter | wait/retry；429 |
| UPSTREAM_UNAVAILABLE | yes，bounded | retry；503 |
| CONTRACT_DRIFT | no | contact admin/update validated integration；503；fail closed |

HTTP status 是 future API投影建议，不是当前 MCP测得状态。上游 ambiguous404/403 不猜 NOT_FOUND。
transport timeout、JSON-RPC failure、MCP isError、structured Status/Error、text error分别识别；
unknown/text非row结果 fail closed，不通过 substring猜授权；safe QUERY_REJECTED 或 CONTRACT_DRIFT
取决于已验证 error evidence。401/403 不进行普通重试风暴，retry所有权一个边界负责，遵守既有ADR-017。
失败不得产生 VerifiedFacts/业务Memory，也不得所有错误统一500。

## 10. Contract Drift Strategy

每 startup/session：固定 endpoint+selector → initialize → tools/list → required tool/input capability校验
→ canonical schema fingerprint/version evidence → principal-bound adapter ready。
必需 ResolveFabricItem/GetSemanticModelSchema/ExecuteQuery；成员枚举可用既有 deterministic DAX，
ValueSearch、Discover、report metadata 缺失可降级其各自可选功能，不伪造必需能力。
required arg/type/response semantic drift、identity不匹配、未知结果完整性 fail closed。
允许额外工具/字段但不自动调用；fingerprint对必需 schema canonicalize，新增无关字段不必误判失败，
仍记录完整 capability hash与selector/client version；hash不可替代语义验证。
M6.2 在自有 transport 验证固定 header、raw input/output schema与脱敏fixture；本轮client view不足以
生成可信 wire fingerprint，未编造hash。不猜工具名、不改旧endpoint、不静默切Local/Mock/REST查询。

## 11. Product/Auth UX Contract — DESIGN ONLY

### CURRENT FRONTEND UI REALITY

审计来源：frontend/src/App.tsx、components/Sidebar/Composer/ConversationView/ResourceManager、
hooks/usePowerBIAgent、api/client/adapters、failure.ts 与 styles.css，及相关frontend tests。当前React+普通CSS，
**无 Tailwind / 无 CSS variables token体系**；字面值styles与现有组件视觉语言是authority。

| Surface | Current reality / reuse |
|---|---|
| shell/sidebar | flex chat shell；260px sidebar，collapsed72；background #f8f8f8 / border #e9e9e9；底部account入口 |
| header/main | header min64px、padding28；message width min(900px,100%-48px)，assistantmax820；usermax620/72% |
| history/reports | sidebar history + ResourceManager中的conversation/report/archived资源；既有ownership当前为Local语义 |
| current selectors | Composer + 菜单包含data/report，独立LLM selector；数据模型menu约290px，LLM约220px；不能混淆LLM模型与数据模型 |
| composer | min68px、max960/100%-48、radius25、border#d9d9d9、柔和shadow；40px圆形send/icon |
| account/menu | accountcard min52、avatar31、popover180/padding7/radius10/menurow38；当前静态Local身份，无auth |
| settings/modal | ResourceManager max1040、height min820/viewport-48、radius16；nav176；General/Conversations/Reports/Archived/Models/About，无Account真实后端 |
| rows/cards | compact row min40、padding8x10、radius8、hover#ececec；不使用大型dashboardcards |
| typography/colors | Inter/ui-sans/Segoe UI/Microsoft YaHei；text#171717、white主背景；secondary沿用#777等现有规则 |
| empty/loading/error | welcome+prompt、局部loading/menu状态、normalized public failure提示；模型/模板pending/disabled已有逻辑 |
| responsive | 760断点sidebar overlay，collapsed58/mainmargin58/header56；480缩小icon36/菜单clamp；reducedmotion支持；minheight600需未来小屏验证 |

未来最小token extension只在M6.1/4获批scope进行；复用surface/border/text/hover/selected/danger/success，
不引入另一套ChatGPT颜色或重做report renderer。现有About历史文案也不在本轮前端改动。

### ChatGPT Web Reference Audit

PRIMARY UI/UX REFERENCE：**Current ChatGPT Web**；VISUAL TOKEN AUTHORITY：**Existing PowerBIAgent frontend**。
2026-10-09实际尝试browser访问chatgpt.com：tab建立并返回页面标题，但加载/选tab连续timeout，
没有可靠DOM/screenshot，**REFERENCE PARTIALLY UNAVAILABLE**。没有观察到的当前像素尺寸、
登录菜单或settings细节不冒充实测，不引用旧截图。以下采用用户指定结构目标+当前PowerBIAgent
代码的保守设计；M6.1/4实施前重新做当前reference视觉spot-check，不据此重做视觉系统。
不复制OpenAI/ChatGPT logo、商标、专属品牌色或品牌文案。Microsoft按钮使用U1官方资源规范。

| ChatGPT reference area | Observation status | PowerBIAgent accepted adaptation |
|---|---|---|
| desktop/sidebar/collapse/header | 当前细节未可靠读取 | 保留260/72与64 header；chat first，不加巨大topnav/多级后台 |
| conversation/content width | 未测当前ChatGPT宽度 | 保留900内容/960composer，单主任务 |
| account/login/popover | 未测当前真实菜单 | 复用底部account、180紧凑menu；signedout同位置登录入口，welcome仅一个简洁CTA |
| settings/modal hierarchy | 未测当前dialog | 复用现有ResourceManager nav/dialog；仅有真实功能时增Account |
| compact resource/model rows | 用户指定结构目标，非实测尺寸 | 290左右现有data popover，primaryname+secondaryworkspace，row不做300高card |
| empty/loading/hover/disabled | 当前reference未测 | 复用现有局部loading/empty/hover/disabled，状态文案简短 |
| responsive | 当前reference未测 | 延续760/480 collapse/overlay与viewport clamping，单一chat产品 |

### Login / account / settings / model binding

普通用户路径：Open → 使用Microsoft登录 → 自动识别身份 → 自动加载目录 → 选择模型 → 问数/报表。
不要求Tenant/Client/Workspace/Model ID、Fabric URL、MCP endpoint、token、scope或Entra配置。
signedout保留简洁shell/welcome“使用组织Power BI数据进行问答”与一个CTA；不显示十几个disabled cards。
技术配置全部由部署/管理员路径承担，不能借bootstrap方案转嫁给用户。

底部account initials/display name；适当显示email/org安全名称；菜单只需Settings/退出/必要的切换账号。
不显示GUID/rawclaims/scopes。settings复用现有真实栏目；Account展示真实身份/退出，Data/Models展示
目录状态；没有实现的Privacy/Security不创建空页，不提供endpoint/secret等普通用户输入框。

数据selector延续Composer现有data入口与低权重current-model indicator（primaryname+workspace tooltip）；
LLM selector保持独立标签。不每条消息重复模型名。Model row状态 SELECTED/AVAILABLE/LOADING/
STALE/FORBIDDEN/ERROR：selected勾选，available可选，loading局部skeleton，stale要求revalidate，
forbidden禁选+安全提示，error可恢复CTA。普通用户只消费normalized catalog，不知道内部工具/API。

第一次即使只有一个模型也**显式选择**，避免用户不知正在访问哪个数据源；选择只需一次点击，
不增加wizard。多模型显示compact list；支持安全display-name过滤，不能把过滤无结果当全目录空。
returning有效session恢复身份后重新验证上次principal/model binding，成功才READY；撤权清模型+
template+pending，刷新目录并重新选。目录PARTIAL可以显示已验证可用rows与“部分模型暂不可用”，
不能把未验证row可选。EMPTY仅在declared catalog scope完整成功且零可用模型时成立。

切换数据模型选择 **新conversation**，复用当前selectSemanticModel的activate(null)/模板刷新方向；
新context不继承旧committed Memory/SemanticFrame/pending/reporttemplate。旧历史可按ownership查看，
恢复时仍重验模型；不无条件送旧context到新模型。请求绑定conversation/model/principal epoch，
旧响应不能覆盖新selection；cancel不代表上游一定停止，但结果必须丢弃。
Report继续domain eligibility + capability eligibility；Sales双模板不变；Logistics无模板仍可问数。

### Auth state machine / UX State Matrix

主链：SIGNED_OUT → AUTHENTICATING → AUTH_CALLBACK → SESSION_ESTABLISHING →
LOADING_CLOUD_CATALOG → READY。AUTH_CALLBACK不展示authcode/technical details。
表中R=用户retry，L=可logout/switch，A=自动恢复，Admin=是否需管理员；“条件”需真实后端证据。

| State | Visible UI / main CTA | Backend condition | Recovery (R/L/A/Admin) |
|---|---|---|---|
| SIGNED_OUT | welcome/底部“使用Microsoft登录” | 无有效session | login；R是/L否/A否/Admin否 |
| AUTHENTICATING | CTA busy“正在登录…”；防双击 | login state已创建/redirect | R取消后/L否/A等待/Admin否 |
| AUTH_CALLBACK | 简短“正在完成登录…” | 验state/nonce/code/PKCE | R失败后/L否/A成功继续/Admin否 |
| SESSION_ESTABLISHING | shell局部status | validated principal、rotate session | R失败后/L是/A成功继续/Admin否 |
| AUTH_CANCELLED | “登录已取消”/重新登录 | 用户取消 | R是/L否/A否/Admin否 |
| AUTH_ERROR | “登录未完成，请重试” | 安全normalized auth failure | R是/L是/A否/Admin持续失败 |
| CONSENT_REQUIRED | “需要批准才能访问组织数据”/继续登录或联系管理员 | interaction/consent required | R可交互/L是/A否/Admin按policy |
| TENANT_NOT_ALLOWED | “此组织账号暂不受支持”/切换账号 | validated tenant不在allowlist | R否/L是/A否/Admin是 |
| LOADING_CLOUD_CATALOG / LOADING_MODELS | selector局部skeleton，chat shell可见 | 当前principal catalog pending | R失败后/L是/A成功继续/Admin否 |
| READY_ONE_MODEL | 一个compact row/选择后composer启用 | 唯一已验证可用row | R刷新/L是/A仅重验成功/Admin否 |
| READY_MULTI_MODEL | selector/current model indicator | 多个已验证rows | R刷新/L是/A仅重验成功/Admin否 |
| READY | 选中模型、现有chat/report | session+binding+requiredcapability通过 | R按failure/L是/A有限/Admin否 |
| NO_ACCESSIBLE_MODELS | “当前账号没有发现可访问的数据模型”/刷新、切换账号、联系管理员 | declared scope完整/零可用；非IQ search empty | R是/L是/A不循环/Admin可需 |
| MODEL_REVOKED | “当前账号无法访问此模型”/换模型 | 下游拒绝/权限已撤 | R刷新/L是/A清binding+刷新一次/Admin可需 |
| CATALOG_ERROR | “暂时无法加载数据模型”/重试 | catalog未建立 | R是/L是/A有界/Admin持续失败 |
| CATALOG_DEGRADED | 保留已验证rows+轻提示/刷新 | 部分workspace失败或shared覆盖不足 | R是/L是/A有界/Admin覆盖不足 |
| FABRIC_UNAVAILABLE | “数据服务暂不可用”/稍后重试 | upstream/capability unavailable | R是/L是/A有界/Admin持续或drift |
| SESSION_EXPIRED | 保留shell，清受保护数据/重新登录 | refresh失败/session无效 | R登录/L是/A不得循环/Admin否 |
| SIGNED_OUT_AFTER_LOGOUT | signedoutwelcome，无旧history/model/report | backend session失效+frontendepoch清理 | R登录/L否/A否/Admin否 |

catalog独立状态：LOADING局部skeleton；EMPTY完整零结果；READY已验证scope；PARTIAL覆盖不全；
DEGRADED已建立目录的临时上游故障；ERROR无法建立目录。PARTIAL/DEGRADED显示安全提示与刷新，
不得误称“没有模型”。loading不使用整页blocking spinner，只有auth必要transition可短暂阻塞。

Error UX统一来自future FailureInfo：AUTH_REQUIRED/AUTH_EXPIRED→登录；AUTH_CONSENT_REQUIRED→
批准；AUTH_FORBIDDEN/RESOURCE_NOT_ACCESSIBLE→换模型/联系管理员；NO_MODEL为catalog状态；
MODEL_REVOKED清binding；CATALOG_ERROR刷新；QUERY_TIMEOUT缩小问题/重试；RATE_LIMITED等待；
UPSTREAM_UNAVAILABLE稍后重试。对用户不暴露HTTP/error JSON/技术scope，不全部变generic500。

logout顺序：用户点击退出 → backend失效session/清principal token与transient binding/cache →
frontend清identity/currentmodel/history/report/transient，增加generation、丢弃inflight晚到结果 →
SIGNED_OUT。network失败也立即清UI并冻结旧session使用，重试后端失效；不得假装服务器注销已成功。
跨标签页通知失效；User A→B不能看到A历史/cache/report，即使browser back或late response。
服务端ownership隔离是根本，不以仅清前端state代替。保留数据的存储删除policy另行设计，不本轮建DB。

### Responsive / component handoff

Desktop≥1200：保留260sidebar+中心900/960；Laptop 1024–1199保持同shell宽度clamp；
Narrow 761–1023可collapse72，不加入另一导航；≤760沿用58rail/260overlay、header56、
菜单viewportclamp；≤480保持36icon/可滚动表格、settings导航横向；keyboard可见composer/account，
未来验证100dvh/minheight600与安全区域必要最小修正。Popover Escape/outside dismiss、focus return、
keyboard row navigation、aria busy/status/alert沿用现有accessibility与reducedmotion规则。

| Existing tree | Future minimal extension / owner |
|---|---|
| App + usePowerBIAgent | M6.1 session bootstrap/AuthGate概念与epoch guard，不另建第二业务state machine |
| Sidebar account-actions | M6.1改真实AccountMenu/登录/logout，复用现有popover |
| ResourceManager | M6.1真实Account section；M6.4 Data/Models目录；不无必要另建SettingsDialog |
| Composer data menu | M6.4 CloudModelSelector/List/Row可为现有菜单内部拆分，仅复杂度需要时创建组件 |
| ConversationView / failure mapping | 复用normalizedfailure显示，M6.1/4扩展已批准codes，不直接读Microsoft错误 |
| API client / hook | 同源cookie/session，catalog DTO与epoch绑定，token不进入React |

### Text wireframes（layout contract，非当前ChatGPT实测）

```text
A Signed-out desktop
┌ Sidebar 260 ┬ Header / PowerBIAgent ─────────────────────┐
│ 新对话     │   用组织 Power BI 数据进行问答               │
│            │          [使用 Microsoft 登录]             │
│            │                                            │
│ [登录]     │       简洁 welcome，无disabled卡片阵列       │
└────────────┴────────────────────────────────────────────┘
B Authentication loading
│ 既有 shell │ 正在完成登录… (小status，无claims/code)       │
C Signed-in / single model
│ History    │ Conversation                               │
│ Reports    │                                            │
│ Account    │ [数据：唯一模型 ▾] [输入问题………] [发送]      │
│            │ 首次点选row后进入READY                     │
D Signed-in / multiple models
│ History    │ welcome / 请选择数据模型                    │
│ Reports    │ [数据模型 ▾] [输入问题………]                 │
│ Account    │ 选择后显示current model                    │
E Model selector open (约既有290px，viewport clamp)
             ┌ 数据模型 / 名称筛选 ──────────────┐
             │ ✓ 模型A                           │
             │   Workspace display               │
             │   模型B                           │
             │   Workspace display               │
             │ 部分模型暂不可用   [刷新]           │
             └───────────────────────────────────┘
F Account menu open (现有180px基础，必要时clamp扩宽)
┌ initials / display name ┐
│ 安全email / organization│
│ 设置                    │
│ 退出                    │
└─────────────────────────┘
G Settings (复用ResourceManager)
┌ 设置 ───────────────────────────────────── [×] ┐
│ 真实栏目nav │ Account: name/org + [退出]       │
│ General     │ Data/Models: normalized目录状态  │
│ …existing   │ 不显示部署配置或空Privacy页      │
└─────────────┴─────────────────────────────────┘
H No accessible models
│ shell │ 当前账号没有发现可访问的数据模型。               │
│       │ [刷新] [切换账号] [联系管理员]                    │
I Session expired
│ shell │ 登录已过期，请重新登录。 [使用Microsoft登录]       │
│       │ 清除旧history/model/report；composer不发送旧上下文 │
```

### Product UX acceptance / evidence boundary

M6.0设计验收：普通用户无技术字段；Chat-first shell；现有视觉authority；compactrows；
所有auth/catalog/model/revoked/logout状态有恢复动作；11项用户设计要求已覆盖（当前reference访问限制
明确披露）。实际“普通用户不问开发者即可使用”、无cross-user leak、响应式/键盘、人类可用性与
真实login/logout尚未实现/测试；必须由M6.1/3/4 E2E证明，不能把设计矩阵叫前端runtime PASS。

| Product requirement | M6.0 design evidence / future execution |
|---|---|
| 1. 无基础设施知识员工可登录/选模型/问数 | 首用flow与9份wireframes；实际人类可用性由M6.4验收 |
| 2. 无人工技术配置 | login→自动catalog→选择；管理员bootstrap与用户路径隔离 |
| 3. 第一视觉Chat-first | 保留Sidebar/Conversation/Composer，不建dashboard |
| 4. login/account/settings/selector参考当前ChatGPT | 已尝试实际网页；REFERENCE PARTIALLY UNAVAILABLE；保守结构mapping，不声称实测尺寸 |
| 5. 继承PowerBIAgent visualtokens | CURRENT FRONTEND UI REALITY列出CSS数值；M6.1/4视觉spot-check |
| 6. 不复制OpenAI品牌 | 无品牌资产新增；只引用结构目标 |
| 7. 登录前/中/后状态 | 主链/异常UX State Matrix；M6.1执行验收 |
| 8. model loading/empty/forbidden/revoked | catalog与row独立状态、coverage判空规则；M6.4执行验收 |
| 9. logout/user switch无泄漏 | epoch/ownership/cache/late-response合同；M6.1/3/4必须实证 |
| 10. M6.1可实施handoff | OAuth对比、Portal配置、Auth/Transport职责与基础Account UX |
| 11. M6.4可实施handoff | 明确目录authority/coverage/DTO/selector/首用返回/reporteligibility/E2E验收 |

CHATGPT UI REFERENCE MAPPING（结构目标，当前细节未实测）：

| PowerBIAgent component | ChatGPT Web reference pattern | PowerBIAgent adaptation |
|---|---|---|
| Sidebar | conversation sidebar / collapse | 复用260/72/窄屏58与当前颜色 |
| Sidebar account-actions | Account Popover / Login entry | 保留底部位置/紧凑密度，替换为真实安全identity |
| ResourceManager | Settings dialog/navigation | 现有dialog层级与真实功能栏目，仅最小Account扩展 |
| Composer data selector | compact model/context selector | 数据模型与LLM分离，primaryname+workspace，无GUID |
| ConversationView | central chat / empty / inline recovery | 保留当前宽度、VerifiedFacts展示、局部loading与安全失败 |

Power BI模型目录/报表eligibility/数据权限没有直接对应的已观察ChatGPT功能；这些是本产品合同，
只借用compact资源选择的结构模式，不能声称ChatGPT提供相同BI功能。

## 12. Implementation Handoff / Roadmap

| Milestone | Authorized future objective / entry & exit gates |
|---|---|
| M6.1 Entra Identity + Login/Session + basic Account UX | freshColdStart/官方重验；按第7/11节实现BFF、Portal Web redirect/credential、validatedprincipal、CSRF/logout/epoch；先P0 identity ownership设计和负例；不自动实施M6.2 |
| M6.2 Fabric IQ Data Plane Adapter | 新FabricIQ adapter，固定selector/rawtools schemafixture/PK-FK映射/完整性/error测试；复用ToolGateway/factual chain；证明ZERO fallback与跨principalcache；不得增加QueryShape/templates |
| M6.3 Authorization / RLS-OLS | 用户另行授权两账号/Viewer fixtures；第8节全部矩阵、ownership/IDOR、revocation/logout/caches；未通过不得试点 |
| M6.4 Cloud Catalog + Model Selector + Product E2E | FabricREST authoritative scopedcatalog +adminseeds；Workspace.Read.All正常consent；第11节全state/firstuse/returning/model-switch/reporteligibility与人类UX验收；零普通用户技术配置 |
| M6.5 Public Real Business Data Validation | 第一主数据集UCI Online Retail II；真实订单/商品/客户/国家/数量/单价/取消、约百万级；FactSales/DimDate/DimProduct/DimCustomer/DimCountry；现有Sales链验证 |
| M6.6 Enterprise Production Readiness Seal | 汇总P0安全与identity、生产部署/observability/rollback/并发隔离/生命周期证据，明确容量与真实freshness限制；是否扩展storage另立scope；不提前实现M7/M8 |

M6.5 measures建议：Total Sales、Total Quantity、Total Orders、Average Order Value、Cancelled Orders、
Cancelled Amount、Unique Customers。先定取消/signed amount/退货/缺失CustomerID/币种/日期业务口径，
再建模验证，不能LLM猜数学或新增shape。Amazon Reviews只为后续customer voice/after-sales/product
review候选。本轮未下载/导入/建模。M7 refresh、M8 pilot、Embedded与PostgreSQL/Redis/Blob均未开始。

## 13. Quality / Two-phase Closure

Phase A保持Settings.version=M5.10.9；docs/ADR candidate先跑正常requiredgates，再白名单提交pushmain。
本地backend normal suite排除既有两个51,200大节点（遵守本轮禁止大型stress）；不改测试/CI，
remote正常Full Validation仍按既有workflow实际执行全部steps。未额外运行130-turn、真实Reportmatrix、
DeepSeek/Kimi或全browserregression。Cloud证据与automatedmockCI分层。

| Local gate | Fresh result |
|---|---|
| Documentation / Version / Repository Safety / Architecture / Error Ledger | PASS；Docs含dynamic version；safety429files、architecture143productionfiles；ledger120entries/0errors |
| Artifact Governance | PASS；只读，无用户资源清理 |
| Semantic Compatibility | PASS：819 passed |
| Backend normal | PASS：2874 passed / 1 skipped / 2 deselected，579.15s；排除下列两大型节点，其余正常suite |
| Golden | PASS：11/11 runnable；既有manual_real_baseline条目1 skipped，非Cloud probe替代 |
| Frontend tests | 首轮FAIL：98passed，ResourceManager worker启动timeout；原npm test有界重跑PASS：10files/105tests，无配置/超时/validator修改 |
| Lint / Typecheck / Build | PASS；build保留PLUGIN_TIMINGS性能提示（非失败），未隐藏warning |

Local backend命令：`scripts/run_pytest_ci.py backend/tests -q`，仅deselect
`backend/tests/unit/test_business_language_stress.py::test_generator_covers_51200_safe_reproducible_cases`
与同文件`test_stress_report_has_zero_generated_failures`；remote workflow不改，正常requiredsteps照常执行。
首轮frontend workertimeout发生在并行本地gates期间，未出现断言失败；待其他frontend/semantic任务结束后
原命令重跑105/105，记录为本地runner启动失败与恢复，不冒充首轮全绿或修复production。

Phase A local required gates全部通过，candidate待自身exact-SHA CI；SHA/CI将在完成后写入Phase B。
最终seal自身SHA不写入自身提交，以currentcheckout的exactSHA
Actions completed/success（Full Validation Windows +正常steps）以及fetch后HEAD==origin/main、clean联合解析。
ADR accepted不等于提前COMPLETE：只有PhaseA全绿后才version=M6.0与COMPLETE marker；最终自身CI仍须绿。

## 14. Acceptance register

1–17合同/官方/两个模型probe/discovery/目录/adapter/identity/OAuth/RLSmatrix/failure/drift/公开数据路线：
已形成证据与设计；18 FrozenCore runtimechange=0。19 localgates、20 exactCI、21 HEAD==origin/main、
22 cleanworktree在seal时按本节记录与09基线解析。尚未验证的M6.1/2/3/4能力不冒充M6.0 blocker或已实现。
M6.0完成后立即停止；M6.1需用户下一轮授权。
