# M6.1 — Entra Identity / Login / Session & Basic Account UX

状态：M6.1 COMPLETE / M6.2 READY（最终marker仅按自身exact-SHA CI与remote audit生效）；Settings.version=M6.1。用户2026-10-09明确批准本轮scope。
首次Real OAuth前必须完成代码、fake tests与本地gates，然后停在人工Portal配置。
Real Entra login/callback/session/account/reload/logout已通过；Phase A提交/自身CI全绿。最终封板只更新版本与文档，仍必须独立核验封板自身CI；不实施M6.2。

## Official Contract（fresh revalidation 2026-10-09）

- [MSAL Python token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens)：confidential web app使用initiate_auth_code_flow/acquire_token_by_auth_code_flow；silent acquisition由库处理cache/refresh。
- [Authorization code / PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)：code+OIDC+PKCE，S256，Web redirect与server credential。
- [Client applications](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/client-applications)、[client credentials](https://learn.microsoft.com/en-us/entra/msal/python/advanced/client-credentials)：开发使用独立Entra SecretStr，生产certificate/assertion属于M6.6。
- [Redirect URI](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url)：精确Web registration，localhost开发例外。
- [OIDC logout](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc)：本地session清除与Microsoft SSO/已发token撤销不同。
- [Token cache](https://learn.microsoft.com/en-us/entra/msal/python/advanced/msal-python-token-cache-serialization)：web app按用户隔离，不使用磁盘business persistence。
- [Fabric IQ](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)：delegated Item.Read.All / Item.Execute.All / Dataset.Read.All，application-only/service principal unsupported。
- [Microsoft resource scope convention](https://learn.microsoft.com/en-us/entra/architecture/authorize-applications-resources-workloads)：Power BI resource URI `https://analysis.windows.net/powerbi/api`；与IQ三permission组合为本项目scope配置。未来scope增量另行授权。

实际依赖固定MSAL Python 1.39.0。fresh installed source审计发现1.38+不再自行验证ID token签名/lifetime；本项目因此使用标准PyJWT[crypto] 2.13.0验证Microsoft tenant JWKS、RS256签名、issuer/audience和必需时间claims，MSAL负责state/nonce/PKCE与token exchange/refresh。没有自行实现crypto或refresh协议。离线真实MSAL + synthetic signed ID token tests验证篡改签名、nonce、audience、issuer、expiry与state拒绝。

用户指定GET callback，故使用query response mode。MSAL明确发出推荐form_post的UserWarning；保留warning，未过滤或降低校验。当前控制为one-use短期flow、即时302至干净`/`、no-store/no-referrer及callback access-log query redaction。form_post合同变更需后续独立批准。

## Threat Model / accepted implementation boundary

本轮接受ADR-020 BFF设计，并按用户明确的M6.1 stage correction实施：
LOCAL_DEV保留M5；ENTRA_BFF只开放Auth/Account/安全health，所有旧product API在路由dependency前拒绝，且不初始化business persistence/provider。
**ENTRA_BFF multi-user persistence: NOT ENABLED BY DESIGN UNTIL M6.3 OWNERSHIP**。

| Threat | P0 control / verification |
|---|---|
| Unscoped history/report/chat IDOR | default-deny product middleware + frontend never mounts business hook；全route matrix tests |
| Login CSRF / callback replay / fixation | random correlation cookie；server-only state/nonce/PKCE；atomic consume once；successful login rotates session |
| Wrong tenant/issuer/audience/expiry | MSAL flow + standard PyJWT signature/claims verification + server single-tenant policy；no client-declared principal |
| Shared user/token singleton | immutable request-scoped PrincipalContext；flow/session独占MSAL client/cache；A/B parallel tests |
| Cookie CSRF | all unsafe methods要求exact Origin + server CSRF secret；callback只允许GET、依赖OAuth flow |
| Token/credential/log leak | Auth-exclusive memory；safe DTO allowlist；禁raw logging；no-store/referrer-policy；callback query不进入access logs |
| Production misuse | insecure cookie / HTTP or localhost redirect / in-memory store fail startup；M6.1 store不支持production |
| Late UI result / tab logout | generation guard + abort；BroadcastChannel仅无identity事件；logout冻结旧UI直到server失效 |

## Auth Flow / PrincipalContext / Session Contract

GET /auth/login → MSAL confidential code+S256 flow → opaque correlation cookie → Entra → GET /auth/callback → consume flow → MSAL completion → tenant/issuer/audience/expiry policy → rotate opaque session → redirect `/`。
PrincipalContext位于Auth边界：tenant_id/principal_id/sub/issuer evidence、display fields、auth_source、session/authorization epochs。展示字段不作授权或cache key。
AuthSessionStore接口与InMemoryAuthSessionStore只用于single-process开发；NOT MULTI-WORKER PRODUCTION READY。过期/登出清MSAL context；process restart全部session失效。
Cookie HttpOnly/SameSite=Lax/Path=/；生产Secure必需；HTTP只允许APP_ENV=development与显式dev cookie policy。

## Token Boundary / SessionStore / CSRF

每flow独占MSAL cache，成功后仅该session拥有；tenant/principal/account/client/resource固定匹配。silent acquire仅Auth broker允许固定Power BI scopes，不向浏览器暴露。refresh由MSAL处理，无自建协议。
所有POST/PATCH/PUT/DELETE在ENTRA_BFF统一要求exact configured Origin与该session签发CSRF值。拒绝后不进入业务依赖；无wildcard credentials CORS。
本地logout失效session、token cache、flow并增加epoch；不宣称Microsoft已发token立即撤销。

## Route Matrix

| Surface | LOCAL_DEV | ENTRA_BFF |
|---|---|---|
| GET /auth/session | local mode safe DTO | valid session→safe account DTO；missing/invalid/expired→401 single FailureInfo |
| GET /auth/login | deny | server flow +302 Entra |
| GET /auth/callback | deny | one-use correlation+MSAL+server policy，302 clean local path |
| POST /auth/logout | deny | Origin+CSRF；server invalidate |
| GET /health | existing M5 diagnostics | safe identity readiness only |
| all product routes /api/* | existing M5 behavior | fail closed irrespective of login |

## Frontend Auth State / Account UX

Bootstrap只读取/auth/session；LOCAL_DEV才挂载usePowerBIAgent，ENTRA_BFF signed-in/out均不加载旧product resources。
SIGNED_OUT/AUTHENTICATING/SESSION_ESTABLISHING/SIGNED_IN/AUTH_ERROR/CONSENT_REQUIRED/SESSION_EXPIRED；没有Cloud catalog/model ready伪状态。
沿用现有sidebar底部Account菜单与ResourceManager设置容器，只显示name/safe username/login状态/退出；无GUID/raw claims/scopes。
2026-10-09 ChatGPT reference浏览器加载超时，先沿用M6.0 conservative contract。随后用户提供登录后ChatGPT截图，按其底部avatar/name、compact popover层级参考；用户特别说明截图侧栏宽度已自行调整，因此保留PowerBIAgent现有宽度/配色。未扩展多账户、订阅、个性化或帮助功能。

## Manual Entra Setup / Real E2E

待本地代码/gates通过后，按用户要求输出ACTION REQUIRED并停在第一次Real OAuth前。
App registrations → PowerBIAgent-M6-Dev → Authentication → Web：`http://localhost:5173/auth/callback`。
创建最短合理期限development secret；repo外secure-input helper隐藏输入并写gitignored .env，secret不进入聊天。
确认Power BI Service Delegated三permissions；不新增Workspace.Read.All，不自行Grant admin consent。
用户回复“M6.1 Entra 配置完成”后才启动Real login/callback/account/reload/logout验收；不查询Fabric。

2026-10-09用户明确确认三项Delegated permission、Redirect URI、tenant/client与credential已配置，并授权继续Real OAuth。以原生uvicorn/Vite启动真实ENTRA_BFF（无fake identity注入），safe `/health`返回ready。浏览器从SIGNED_OUT真实跳转Microsoft，S256 challenge与三个固定Power BI scopes成立。首次user-consent由用户亲自接受；随后重新发起正常登录并选择真实组织工作账号，成功callback至干净`/`。

Real Entra验收PASS：真实账号登录；页面刷新恢复同一账号；底部菜单与账户设置显示正确姓名、用户名、已登录状态；第二标签自动恢复同一Session；点击账户页退出后两个标签均SIGNED_OUT；退出后刷新仍SIGNED_OUT。整个验收没有访问Fabric或旧product API。截图保留repo外，不提交真实姓名、邮箱、tenant/client ID。初次callback建立Session必需实际MSAL返回access token、验证ID token并匹配该cache内账号；silent acquisition/cache命中与清理另由actual MSAL离线测试证明，不将其描述为Real refresh网络验收。浏览器Token不暴露由safe DTO/代码与自动化negative tests证明，未读取真实Cookie/Token，也未额外审计浏览器存储快照。

## Known Limitations / M6.2 Handoff / M6.3 Ownership Gate

In-memory store仅开发；production distributed store留M6.6/独立patch。M6.1无Cloud Adapter/Catalog/DB ownership。
未来validated Principal + server-owned model binding + authorization evidence → server trusted authorization projection → legacy UserContext/ToolExecutionContext；不得client self-declare。
M6.2 Transport仅通过Auth broker acquire delegated token，不能再次实现OAuth；M6.3必须先完成tenant/principal resource ownership才能开放旧product APIs。

## Evidence / Closure

Cold Start main/clean，HEAD==origin/main==`fabee6b46ea2f72574cdaa5d39dc3a5e73771a2f`。
Failure-first：Auth security初始因Auth module缺失失败；frontend初始因useAuth缺失失败，随后最小实现。

Local automated（2026-10-09，本轮fresh运行，不继承M6.0历史PASS）：

- Backend full normal：2908 passed、1 skipped、2 deselected；明确排除两个51,200 stress生成/报告测试。保留8个MSAL query/form_post建议warning。
- Semantic Compatibility：819 passed，gate PASS；Golden：11 passed、1 manual Real baseline skipped、0 failed。
- Auth focused：41 passed（含actual MSAL offline protocol/signature tests）；Auth frontend：7 passed。
- Frontend full：11 files、112 tests PASS。Account共享容器/布局最后调整后，相关Auth/Sidebar/ResourceManager再次26 passed；typecheck/lint/build均PASS。
- Documentation Governance / Repository Safety / Architecture Gate / Error Ledger / Artifact Governance：PASS；Error Ledger 120 entries / 0 errors；strict diff whitespace check PASS。未提交worktree为本轮候选的预期状态，尚不能声称CI strict clean成立。
- Synthetic浏览器：SIGNED_OUT CTA、simulated callback clean URL、safe Account/menu/settings、signed-in reload恢复、logout后SIGNED_OUT及刷新PASS。仅本地FakeIdentity，绝不等同Real Entra。截图预览和启动辅助脚本保留repo外。
- repo外secure-input helper：synthetic tempfile round-trip PASS，隐藏输入、保留无关配置、去除重复Auth键、直接写受限ACL文件；验证没有访问真实repo `.env`。

Real Entra：PASS（login/callback/account/reload/logout及跨标签退出，详见上节）。Phase A commit：`5549d0973473eed7849f48465ccbd13af96a5015`，`M6.1_Entra身份登录与会话候选`，当时Settings.version=M6.0。
[exact-SHA CI37954913373](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37954913373)：completed/success，Full Validation (Windows)与全部required steps实际success，无skipped step，push事件与head_sha已独立核对。

2026-10-10最终seal：Settings.version=M6.1，当前文档M6.1 COMPLETE / M6.2 READY。封板自身SHA不写入自身提交；必须查询当前checkout exact-SHA CI completed/success、全部required steps实际success，fresh fetch后HEAD==origin/main、worktree clean，marker才生效。不能继承Phase A CI。M6.2未实施；完成后立即停止。

手工交接前remote refresh两次遭GitHub连接reset/timeout；没有push。当前HEAD与本地origin/main仍为Cold Start SHA，但不将缓存ref冒充fresh remote audit。恢复后Phase A提交前必须重新fetch确认remote未前进。模拟backend/Vite仅本轮拥有的进程已停止，避免被误当作Real runtime。

恢复Real E2E本轮：原生uvicorn真实ENTRA_BFF、Vite已启动；Auth focused再次41 passed/8个保留warning，Documentation Governance PASS。git fetch遭300s网络timeout；GitHub connector compare(baseline SHA...main) fresh返回identical、ahead_by=0、behind_by=0，remote main没有前进。该只读证据不替代Phase A/Final所需fetch/push/自身CI。临时证据观察器启动命令遭automatic approval rejection（仅blocked by policy），未执行；改用未注入identity_client的项目原生启动，不读取Cookie/Token作为替代。

Real E2E完成后git fetch成功；HEAD与origin/main仍等于Cold Start SHA，remote main未前进。按白名单进入Phase A候选提交。
