# 07 — 当前项目状态

> **状态：** Settings.version=M6.3；M6.1 COMPLETE；M6.2 COMPLETE（以自身exact-SHA CI与remote audit生效）；M6.3 Security COMPLETE（以Final exact-SHA CI与remote audit生效）；Fabric IQ数值兼容P1 BLOCKED；M6.4 NOT READY；M5.10.9 COMPLETE；M5.10.9 FIX COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一当前项目状态 authority；路线见 [08](08_development_roadmap.md)，开发交接见 [09](09_context_handoff.md)。

## 当前状态

| 项目 | 状态 |
|---|---|
| Current Version | M6.3 |
| Current Release State | M6.3 Security COMPLETE；以Final自身exact-SHA CI + remote audit生效；数值兼容P1 BLOCKED；M5 FINAL=true |
| Frozen | M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN |
| Post-final | M5.10.9 FIX COMPLETE — documentation semantic consistency / CI test stability forward-fix |
| Next | M6.4已获用户批准，正在本地开发/验证；数值P1必须在Product E2E前解决，当前未发布 |
| Current implementation status | M6.4正式Cloud控制面、模型选择及Settings已接线；服务组合与UX PARTIAL；业务API仍关闭，数值/完整性及完整Real链BLOCKED |
| Ready state | Real安全74/74、Late-Response41/41、完整本地回归及候选CI通过；Final自身CI与remote audit解析 |

## M6.4 当前开发（2026-10-13，阶段候选；非 Final Seal）

用户最新明确授权一次M6.4阶段候选提交、正常Push main、该exact SHA Full Validation CI及Remote Audit；范围冻结，不新增功能。
本轮fresh fetch成功，main/HEAD/origin/main一致，暂存区为空；48项既有源码/测试/文档修改与上一轮最终清单一致。
候选基线以提交标题`M6.4_云端产品阶段候选与安全边界`对应的当前checkout exact SHA及远端回执解析；不继承历史CI。
Settings.version继续M6.3；M6.4保持PARTIAL/BLOCKED、Final NOT READY。后文历史“不Commit/Push”限制已由本次候选授权替代；Final仍须全部原定验收。
未验证业务HTTP、测试History/Report回放与外部LLM准备继续fail closed；Real NOT_TESTED/BLOCKED不妨碍安全候选提交，不计Real PASS。
fresh本地质量门槛、候选CI与远端审计结果见[专项候选收口记录](milestones/m6/m6_4_cloud_product_e2e.md)。

最新测试隔离轮本地后端3275 PASS/1 SKIP/12 warnings，隔离31项；前端132 PASS与Typecheck/Lint/Build，Semantic819、Golden11/1 manual Real SKIP；必要Real及完整Chat→Facts→Answer/Report未通过，未提交发布。

测试Workspace强制隔离已本地实现，定向逐项REST及Adapter/Transport allowlist默认拒绝；原始回执/seed身份本机匹配。企业隐私P0仍PARTIAL，History/Report/外部LLM链保持拒绝；Real未运行，M6.4未发布。详见专项最新测试隔离章节。

[本轮合同与分层证据](milestones/m6/m6_4_cloud_product_e2e.md)。Charter旧状态与08的M9规划已先行修正。
Catalog增加current-principal只读REST与逐模型Resolve/Schema验证，复用ToolGateway和现有Adapter。
恢复开发已接正式Cloud控制面接口、显式模型选择、Settings/Data与既有Composer；业务执行入口仍关闭。
用户另行明确批准model_semantic_context.py六处类型兼容声明，None仍为未知、fabric_iq来源保留；其他Frozen Core不改。
Viewer A已完成真实登录；本轮Real Catalog PASS（6个可访问模型），目录仍诚实标为PARTIAL。
首轮三条固定查询在ToolGateway前置策略处被临时harness遗漏的模型授权上下文阻断，尚未到达ExecuteQuery；
仓库外最小接线修复经12项OFFLINE测试通过；Viewer A重新登录后，三条查询均已真实到达ExecuteQuery。
COUNTROWS严格数值与独立预期匹配（但truncated=true）；销售额标量/分组在HTTP wire和SDK中均为Int64列配字符串，FAIL CONTRACT_DRIFT。
三条响应均无完整性信号，官方合同重验仍不足，严格CONTRACT_DRIFT与truncated=true保留；不是登录或consent停点。
Viewer B正式首页已发现15个已验证模型（含获准共享synthetic fixture）；REST的18工作区目录完成，123候选的IQ授权串行耗尽预算。
已复用有界并发和同一deadline返回scoped PARTIAL；后续Real选择遭遇RATE_LIMITED，模板资格本轮未通过。
新负例定位未知授权失败误计不可访问并继续扇出；最小修复停止当前批次、drain任务并保留unverified范围，Real复验待新native会话。
CloudProductServiceFactory复用既有TurnPipeline/owner repositories；新增History和Report owner只读组合，身份在await前后重验。
正式业务API、Cloud Chat/History/Report前端完整链和会话恢复尚未完成；最新前端131项/Lint/Build通过，后端全量3244 PASS、1 SKIP、12 warnings。
八类Shape已逐项研究，SCALAR与标量FILTERED_AGGREGATION在既有合同内存在候选证明路径，但尚未取得可信Real证明；不要求所有问题无条件等待Microsoft。
Settings.version=M6.3，M6.4发布仍NOT READY。
本轮按用户明确许可，在fetch失败后以GitHub连接器核对相同main SHA，仅继续本地开发/测试。
成功fetch且远端基线未变化前禁止Commit/Push/Final Seal；该临时例外不改变长期Git规则。
本轮有界fetch曾失败并用连接器核验；最新HTTP/1.1 fetch已成功，main/HEAD/origin/main仍为原基线，staging为空。
产品Adapter新增完整性保护，正式API继续关闭。

用户补充企业数据P0并确认公司及账号所有者完整授权尚未确认；受影响Real操作暂停，本人创建的原生Real服务已停止。
暂停前最后一次目录返回6个已验证模型、明确115个尚未验证，获准synthetic fixture模型选择成功；模板资格及业务Real链未通过。
合成开发继续：模型名称本地筛选、隐私边界审计、LOCAL_DEV合成问答/新聊天/历史恢复已验；结果不计Cloud Real PASS。
DeepSeek/Kimi通用Provider实际可接收上层columns/rows；两个profile仅经in-process合成wire验证，未向外部发送企业数据。
现有Secret scrubber不是业务数据DLP；History/Report当前模型RLS/OLS重验与跨登录绑定未完成，P0保持PARTIAL/BLOCKED。
仓库外六目录仅脱敏风险扫描，十个历史DB及二进制/归档等内容未读；风险候选不能冒充已确认泄漏或“安全PASS”。
P0证据在PBIAgentTest/M6.4/Acceptance/p0_privacy_audit.md；同样约束用户提及的M6.4.1 PREP边界，不新增版本或实施范围。
当前可运行服务仅LOCAL_DEV合成实例；公司/账号授权明确前不恢复企业Real，也不向外部LLM发送真实BI或敏感Schema。

## M6.3 安全里程碑

[完整合同、证据与遗留问题](milestones/m6/m6_3_multi_user_ownership_authorization_rls_ols.md)。
真实同tenant双Viewer安全矩阵74/74 PASS（A17、B31、A返回26；0 FAIL/0 NOT_TESTED）。
COUNTROWS标量/分组为严格数字，Region为A/B/A；A可读RestrictedTable，B实际schema隐藏且固定查询被拒绝。
真实Late-Response 41/41 PASS：7类A在途操作在native logout及B登录后全部AUTH_REQUIRED；
Memory/Snapshot/Report/History零过期提交、A binding清除且不可复用，B资源/会话/Idempotency不受影响；A返回身份与原A一致。
Late测试使用真实Entra/MSAL/BFF、IQ Transport/Adapter及原生Repository；延迟注入仅在仓库外，synthetic DB/HTML。
完整Cloud Product UI/E2E、外部角色撤销通知NOT_TESTED，不以该测试冒充上述产品能力。
临时服务已关闭，正式native app已恢复；临时/auth/m63-*及/m63-test路径原生后端404；未登录正式API401、合成登录产品gate403。
Vite对未代理未知路径仍返回SPA shell，不能把该200当作后端路由存在；/auth代理路径404已实测。
按用户2026-10-10最终封板指令显式调整验收范围：M6.3 Security独立封板，销售额标量/分组仍FAIL CONTRACT_DRIFT。
Fabric IQ数值兼容为M6.4 Product E2E前P1 BLOCKER；不得强转、改expected、降低M5 ResultInspection/VerifiedFactSet或伪造PASS。
旧401首次拒绝层、旧第三轮A指纹差异UNRESOLVED；本轮principal比较来自validated tenant+principal稳定hash，不依赖session/epoch或邮箱。
Cloud完整性仍保守truncated=true；M6.4 Catalog、完整Chat/Report/History UI与Product E2E未实施，须独立批准。

Phase A exact-SHA CI已全步骤success；Final采用管理员同受保护的PR路径。最终基线按09解析，禁止继承候选或M6.2 CI代替Final证据。

## M6.2 已发布基线

2026-10-10用户明确批准Fabric IQ只读Data Plane scope。
[合同与验收](milestones/m6/m6_2_fabric_iq_cloud_adapter.md)：独立SDK transport、request/session绑定Adapter、
required capability negotiation、schema-before-bind、unknown metadata与结果完整性fail closed。
Settings.version=M6.2；两模型Real与Phase A全步骤CI通过；最终自身CI38012437829与remote audit已重验。
M6.2封板时ownership尚未实施；当前M6.3进度见上节。Cloud Catalog / Product E2E未实施；ENTRA_BFF旧/api仍关闭。

## M6.1 历史封板

用户2026-10-09已批准身份/登录/Session/Account scope。实现与安全合同见
[M6.1 evidence](milestones/m6/m6_1_entra_identity_login_session.md)。Settings.version=M6.1；
LOCAL_DEV保留M5，ENTRA_BFF只开放Auth/Account/安全diagnostics。
ENTRA_BFF multi-user persistence: NOT ENABLED BY DESIGN UNTIL M6.3 OWNERSHIP。
首次Real OAuth前人工Portal配置停点已完成；真实login/callback/account/reload/logout与跨标签退出PASS。Phase A exact-SHA CI全绿；COMPLETE marker以最终封板自身CI全绿、fetch后HEAD==origin/main、worktree clean生效。M6.1封板时M6.2未实施；当前实施见上节。

## M6.0 历史审计

[M6.0 evidence](milestones/m6/m6_0_fabric_iq_cloud_contract_audit.md) 与
[ADR-020 ACCEPTED](adr/ADR-020_fabric_iq_cloud_consumption_and_catalog_authority.md)：Fabric IQ GA、
delegated-only、两模型resolve/schema/query PASS；DiscoverArtifacts名称搜索仍empty，属于已知限制。
Fabric REST current-principal workspace/model/report listing作为M6.4 scoped catalog authority，
管理员seed补共享资源，明确partial coverage；BFF delegated code/PKCE为M6.1推荐。
Product/Auth UX为设计合同；当前ChatGPT reference可靠访问受限，现有前端视觉authority保持。
Phase A exact-SHA CI37904870868全绿后进入最终seal，Settings.version=M6.0。
final自身SHA不写入自身提交；以09的exact-SHA CI / remoteaudit联合解析最终成立状态。
M6.0封板时M5 factual Core与所有production behavior保持，M6.1/2/3/4当时尚未实施；当前M6.1状态见上节。

M5.10.8 与 FIX、M5.10.9 已完成。原 Final baseline：
`86aaaec7d2172c041e97392c3de03adcca77ca1b` /
[CI 36678384015](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36678384015)
completed/success，2026-09-30 fresh REST + fetch 核验。
post-final FIX 只校准文档与治理回归，M5 FINAL=true 持续有效。
最新 FIX 发布基线按 09 的当前 exact-SHA CI / remote audit 解析，不用祖先 CI 代替。
FIX 候选 `9196bb7e52fbc8869daff7233518ac896bc813ca` /
[CI 36686978579](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36686978579)
completed/success；最终 FIX marker 以最终 exact-SHA CI + remote audit 成立为准。

2026-10-09 重新核验：Phase B `953be2683d539fbf4b43d59cca086a3fd598928c` /
[CI 36688714620](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36688714620)
completed/failure；跨 lifespan 的整数 id 断言产生测试假失败，该提交的 FIX COMPLETE 尚未生效。
Phase C `f8641f4d588e1823f521a6d1e9e4e459e6c920f3` /
[CI 37871771667](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37871771667)
completed/success；required check 与全部正常 steps success，fresh fetch 后 HEAD==origin/main、clean。
最终 FIX marker 仍以其自身 exact-SHA CI 与 remote audit 成立为准，不用 Phase C CI 覆盖最终 SHA。

## M5 Core Analysis Kernel 冻结边界

M5 是后续 enterprise productionization 复用的 Core Analysis Kernel。

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

LLM understands. Runtime proves. LLM 仅解释语言并组织 verified wording；runtime Catalog/Grounding
拥有对象/成员绑定，StateTransition/Completeness 拥有可执行 state，Deterministic DAX/Independent
Layer 3 拥有执行校验，ResultInspection/VerifiedFactSet 拥有结果事实。Report 复用同一事实链。
requested_query_scope、observed_data_coverage、available_data_horizon 独立；horizon 只由真实
measure/fact-family + temporal-dimension-aware 数据证明，不能冒充 refresh time。

## Local MVP baseline 与限制

- React + Vite、FastAPI、SQLite/Repository、readonly Local MCP + Desktop、DeepSeek/Kimi Registry。
- 模型感知目录由 backend runtime metadata 确定；Sales 两模板为简易销售分析模板与专业销售经营分析模板。
  Logistics 没有适配模板仍可正常数据问答；未新增物流模板、未放宽 eligibility。
- 当前生成的 HTML Report 是 historical snapshot；真实 refresh metadata 缺失时明确 UNKNOWN。
- 本地 identity、SQLite/filesystem、Preview MCP 与进程内 coordination 尚不具备 enterprise backend 保证。

## 下一阶段与非阻塞风险

下一阶段：M6 — Cloud Consumption & Enterprise Identity；必须另行获批 implementation。
下一实施阶段为M6.4，须独立批准；数值合同P1必须在Product E2E前解决，存储/部署风险见08/09。
Local Modeling MCP Preview、LLM 长尾、无权威刷新时间、本地 single-machine persistence 是已知限制，
不能作为推倒 Core 或提前实现 M6 的理由。

## 证据与历史

M5.10.x 详细变更见 [CHANGELOG](../CHANGELOG.md)、[M5.10.8](milestones/m5/m5_10_8_mvp_final_test_seal.md)、
[M5.10.8 FIX](milestones/m5/m5_10_8_fix_model_aware_report_template_catalog.md) 和
[M5.10.9 evidence](milestones/m5/m5_10_9_documentation_governance_and_final_seal.md)。
post-final 分层证据见 [M5.10.9 FIX](milestones/m5/m5_10_9_fix_document_semantic_consistency_and_m6_handoff.md)。
旧状态长记录保留于 [Historical snapshot](archive/m5_pre_final_07_milestones_status_and_open_questions.md)。
历史 milestone / ADR / archive 不另设当前状态。最终 seal 必须以最终 exact-SHA CI 为准。
