# 07 — 当前项目状态

> **状态：** Settings.version=M6.1；M6.1 COMPLETE；M6.2 IN PROGRESS（本轮已授权，未封板）；M5.10.9 COMPLETE；M5.10.9 FIX COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一当前项目状态 authority；路线见 [08](08_development_roadmap.md)，开发交接见 [09](09_context_handoff.md)。

## 当前状态

| 项目 | 状态 |
|---|---|
| Current Version | M6.1 |
| Current Release State | M6.1 COMPLETE；最终seal以自身exact-SHA CI + remoteaudit生效；M5 FINAL=true |
| Frozen | M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN |
| Post-final | M5.10.9 FIX COMPLETE — documentation semantic consistency / CI test stability forward-fix |
| Next | M6.2 IN PROGRESS — 本轮已批准，未封板 |
| Current implementation status | M6.1 Auth/Session/Account runtime IMPLEMENTED；Cloud data plane candidate IMPLEMENTED；两模型Real PASS，Phase A/Final CI待完成 |
| Ready state | M6.1 official / Real Entra / local gates / Phase A exact-SHA CI通过；final自身CI独立验收 |

## M6.2 当前实施

2026-10-10用户明确批准Fabric IQ只读Data Plane scope。
[合同与验收](milestones/m6/m6_2_fabric_iq_cloud_adapter.md)：独立SDK transport、request/session绑定Adapter、
required capability negotiation、schema-before-bind、unknown metadata与结果完整性fail closed。
Settings.version保持M6.1；两模型Real、Phase A与Final自身CI未全部通过前不声明COMPLETE。
Cloud Catalog / multi-user persistence ownership / Product E2E未实现；ENTRA_BFF旧/api仍关闭。

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
当前待决策为微软能力/权限验证、租户/主体隔离、存储/事务/部署方案，详见 08/09。
Local Modeling MCP Preview、LLM 长尾、无权威刷新时间、本地 single-machine persistence 是已知限制，
不能作为推倒 Core 或提前实现 M6 的理由。

## 证据与历史

M5.10.x 详细变更见 [CHANGELOG](../CHANGELOG.md)、[M5.10.8](milestones/m5/m5_10_8_mvp_final_test_seal.md)、
[M5.10.8 FIX](milestones/m5/m5_10_8_fix_model_aware_report_template_catalog.md) 和
[M5.10.9 evidence](milestones/m5/m5_10_9_documentation_governance_and_final_seal.md)。
post-final 分层证据见 [M5.10.9 FIX](milestones/m5/m5_10_9_fix_document_semantic_consistency_and_m6_handoff.md)。
旧状态长记录保留于 [Historical snapshot](archive/m5_pre_final_07_milestones_status_and_open_questions.md)。
历史 milestone / ADR / archive 不另设当前状态。最终 seal 必须以最终 exact-SHA CI 为准。
