# M6.4_FIX — 登录、会话、布局与 CI 定点回归

日期：2026-10-14。用户批准仅修现有 FIX 运行时回归；起始 main 为
`d01fe9149ae63dc29f53dbfd3a6e534c58515d23`，CI38498609270 FAILURE，不能继承历史 PASS。

## 实施前 P0 边界

Fresh fetch 后 main/HEAD/origin/main 相同，worktree/staging clean。读取入口、Charter、
07/08/09、Ledger、ADR-020 与相关 production/tests。只使用 Synthetic Auth/Fabric/LLM。
没有读取 .env、真实 DB/PBIX、账号日志、Token、Cookie 或企业业务内容。

重新读取 Microsoft 官方文档：

- [MSAL Python token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens)：静默刷新绑定已选择账号，失败不能猜测另一账号。
- [Authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)：state/PKCE/nonce 验证保持；select_account 不等于强制密码/MFA。
- [Conditional Access session lifetime](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-session-lifetime)：组织重新认证要求不能由应用绕过。
- [Fabric IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp) 与
  [Fabric Workspace listing](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/list-workspaces)：当前 delegated principal 的访问 authority 不变。

复验日期均为2026-10-14。未调用真实 Microsoft 登录、BI或外部LLM；runtime Real NOT_TESTED。

合同：有效 DELETE 响应才确认成功；后续列表可用性不反向改写已提交结果。Ownership、CAS、
tombstone、durable delete intent 和重试保持；迟到页不能复活删除项；迟到身份响应不能跨 epoch。
前端暂时网络故障保留账号投影，但服务端每次仍验证身份/资源。Token 获取网络故障不得销毁有效
cache/session；真正 expiry、account mismatch、撤权与认证拒绝仍 fail closed。绝不刷新应用硬 TTL、
扩大 scope、持久化凭据、关闭 test mode/Allowlist/MFA 或更改 Conditional Access。

并发 OAuth callback 不得消费另一 state 的新 flow 或清除新登录 session；未知/重放 callback
不得建立身份。只调整布局定位和唯一状态提示，不改变原视觉系统、模板或事实链。
InMemory 重启丢会话及3600秒硬 TTL仍是既有开发合同，分布式 store留待M6.6。

M6.4 FINAL NOT READY；Settings.version=M6.3。数值、完整性、隐私及真实E2E Gate不变。
本轮完成以自身 exact-SHA Full Validation、Remote Audit与clean生效，修复后停止。

## 根因与修复证据

1. CI38498609270完整job日志证明：后端、Semantic、Golden、安全/治理均成功；前端
   143PASS/1FAIL，Settings报表checkbox仍在。日志未包含该次DELETE响应时序，不能从单条
   DOM断言推断服务端删除失败。原合成真实API测试本地基线能通过；新增延迟读回用例先FAIL，
   证明CloudWorkspace将成功mutation等待后续transcript/list读取完成，才确认给ResourceManager。
   新增迟到分页用例先FAIL，证明旧页能把已删除项重新加入。修复只认有效服务端提交响应，
   后续读取独立同步；确认删除更新tombstone，取消旧分页generation。原API测试显式等待
   DELETE200后保留checkbox消失与download404断言，未延长timeout或删除负例。
2. 用户三账号现象为callback302、session401后200、已登录API403。native业务入口的
   require_execution固定拒绝未验收执行，合成测试证明403后session仍200、DB未打开；这是E类
   预期安全拒绝。未配置测试范围是C类RESOURCE_NOT_ACCESSIBLE503，有独立reason；当前principal
   权限拒绝为D类。仅靠现有汇总不能把每个账号的每条403归于E或D，也不能证明实际白名单配置。
   新提示区分test_scope_missing/cloud_execution_blocked与普通权限拒绝，403不注销有效账号。
   启动诊断仅含阶段、TTL、store类型、test mode、配置bool及批准数量，不含身份或资源内容。
3. B反复验证的实际触发尚UNCONFIRMED。确定且复现的Bug包括前端任何session请求异常清身份、
   一次失败停止后续分钟检查；服务端Token网络失败清cache/session并误报AUTH_EXPIRED；MSAL
   构造阶段网络异常误报认证拒绝；迟到callback消费新Flow/清新session。failure-first用例证明
   并最小修复上述路径。3600秒硬TTL及重启丢InMemory session仍保持原合同；没有把B的现象
   无证据归于TTL、重启、select_account或Conditional Access。成功回调仍校验PKCE/state/nonce、
   issuer/audience/tenant/principal与私有账号cache；真实expiry/错配/撤权仍拒绝。
4. 底部根因是absolute composer未占据文档流，而catalog提示与默认全宽reload按钮在chat-main
   普通流中；600px最小高度超过缩放后viewport；同一error又进入Composer selector。改为flex流
   中唯一状态区域、取消过大min-height与补偿padding、限制popover高度和换行，保留视觉变量。

## 分层验证与浏览器证据

前端全量152PASS（14文件），Typecheck/Lint/Build通过；Semantic819PASS，Golden11PASS、
1人工Real SKIP。Repository/Ledger/Architecture/Documentation/Artifact门禁通过。
后端最终全量3367PASS、1SKIP、15 warnings（493.47秒），日志为本轮仓库外backend-full.log。
warnings保留既有SQLite migration主键提示与MSAL response_mode建议，新增MSAL用例也计数；
没有隐藏或降低validator。此前未覆盖最后改动的全量运行主动中止，保留
backend-pre-final-interrupted.log，不计PASS。

浏览器为独立Edge headless Synthetic Auth/API上下文，全部外部网络请求被拒绝；未使用真实
账号profile。baseline截图来自起始exact-SHA归档。100/125/150%采用物理尺寸对应的CSS viewport
及deviceScaleFactor等效验证，另有390px窄屏；不冒充三账号真实截图或Real E2E PASS。
原150%下document高度600px超过533px viewport；修复后533/533，无水平/底部溢出，唯一提示
与输入框/selection不重叠，弹出菜单在viewport内。其他三种尺寸同样通过。

可复用脚本：`scripts/manual_smoke/cloud_runtime_browser_acceptance.mjs`；参数为本地URL、
仓库外输出目录、before/after。本机用`PBI_BROWSER_MODULES`指定Playwright依赖路径，
`PBI_BROWSER_CHANNEL=msedge`。证据目录：
`D:/AAA_Workfile/PBIAgentTest/M6.4_FIX/Acceptance/runtime-20261014/browser`，保存before/after
四组PNG及geometry JSON；没有截图或业务数据进入Git。

Remote Audit按本次实际SHA解析push/main Full Validation与remote main、local HEAD/origin/main、
clean。GitHub连接器不具备branch protection读取权限（403），不修改保护、不绕过normal push；
不以此推断保护配置。自身SHA/CI/审计回执写仓库外，避免自引用提交。
