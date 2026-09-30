# 09 — 下一开发者 / AI Cold Start Handoff

> Settings.version=M5.10.9；M5.10.9 RELEASE CANDIDATE；M5 FINAL=false。
> 唯一开发交接 authority；当前项目状态见 [07](07_milestones_status_and_open_questions.md)，路线见 [08](08_development_roadmap.md)。

## 当前阶段 — M5.10.9 — Documentation Governance & M5 Final Seal

M5.10.8 COMPLETE；M5.10.8 FIX COMPLETE。本轮只治理/冻结，Core 无业务实现变化。
下一阶段：M6 — Cloud Consumption & Enterprise Identity；本轮结束后停止，不自动开始 M6。

## Mandatory Cold Start

1. git status、git branch --show-current、git rev-parse HEAD / origin/main、git log -8；fetch 后再次
   核对 main、clean worktree、HEAD==origin/main。remote 前进、非 main 或非本轮改动立即停止。
2. AGENTS.md → PROJECT_CHARTER.md → CLAUDE.md。
3. docs/07 → docs/08 → docs/09；README、CHANGELOG 作为导航与历史摘要。
4. Error Ledger 的 schema、有效 prevention/prohibited rules 与相关条目；ADR README 和任务相关
   accepted ADR。ADR-006 是历史 SUPERSEDED 路线，不能当成当前 endpoint/auth contract。
5. 当前用户指定文档、涉及 production code、邻近 tests、CI required checks。
6. 输出简短 reality audit 后在已授权范围内继续。不得以聊天记忆或历史 PASS 代替 fresh 证据。

冲突优先级：当前明确用户指令 → PROJECT_CHARTER → 正式 PRD → accepted ADR → 当前专项设计
→ 08 → 09 → CLAUDE → code/fresh tests → Archive。07/08/09 分别只拥有状态/路线/交接。

## 最终 baseline 解析

上一阶段最终绿色基线：`main@409fd521b4b503b6e8e56846806e099cd98e7a5b`，
[exact-SHA CI Run 36665958820](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36665958820)
completed/success，2026-09-30 fresh REST + fetch 核验。M5.10.8 发布基线
`ef5a4c8ead7c05576360d3070ecf0e286e841dc5` / Run `36661689674` 也已核验 success。
本阶段候选/最终 SHA 不预填；以当前 checkout 的 `git rev-parse HEAD`、该 exact SHA 的
PowerBIAgent Validation / Full Validation (Windows) completed/success、fetch 后 HEAD==origin/main
与 clean worktree 联合解析发布基线。文档中的 final marker 只有在最终 SHA CI 绿色后成为有效 seal。

Phase A commit：M5.10.9_文档治理与最终封板候选。保持 FINAL=false；候选 exact-SHA CI 全绿后才
做 very small marker patch。Phase B：M5.10.9_M5最终封板，最终 exact-SHA CI 再全绿后 remote audit。
可直接运行 git log -8 --oneline 查 seal 中文提交，并按该 SHA 查询 Actions；禁止假定祖先 CI 覆盖当前 SHA。

## M5 Frozen Core

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

SemanticFrame 只输出 bounded language draft；Catalog/Grounding 证明 canonical object/member，
StateTransition/Completeness 证明可执行 state。QueryShape 固定八种；无证据/歧义/残缺在 DAX 前
clarification/no-match + ZERO factual Memory commit。DeterministicDAXBuilder + DAXSafety + Independent
Layer 3、ResultInspection + VerifiedFactSet 保留执行/事实 authority；LLM 不做业务数学。
General current-message-only/no-tool，ZERO schema/member/DAX/report/business Memory/pending mutation。
Natural Presentation 只消费 verified facts/scope/真实 availability 并经 FactOutputValidator；失败 repair
或 deterministic safe fallback。Report 复用同一链，固定 Renderer authority 不变。
requested scope、observed coverage 与 measure-aware available horizon 独立；未知 freshness 明示未知。

## 当前 provider 分层与 M6 第一阶段

M5 Local MCP = Developer / Desktop Provider；M6 Cloud Provider = Production Cloud Consumption Provider。
当前实现为 MockPowerBIAdapter、LocalMCPPowerBIAdapter 与未完成的 RemoteMCP skeleton，Real 失败
不得回退 Mock。未来 Cloud PowerBI Adapter 继续服从 PowerBIAdapter 与 ToolGateway，不能复制管线。

```
SemanticFrame → Grounding → CanonicalQueryPlan → Deterministic DAX
→ Power BI data plane → QueryResult → ResultInspection → VerifiedFactSet → Answer / Report
```

任何 M6 implementation 前必须重新验证 Microsoft 官方 API / MCP / Fabric 文档，保存日期、
官方来源、endpoint、auth、tenant/identity、capability/tool schema、RLS/OLS 与 fail-closed probe
证据。Fabric IQ MCP 是需要评估的默认方向之一，尚未确认其适用性或 production contract。
ADR-006 已 SUPERSEDED；历史 Power BI Consumption MCP endpoint、SDK 版本、认证假设不得直接
当成当前稳定合同。本轮没有验证或实现 Cloud MCP / Entra。

先完成外部能力/授权/RLS-OLS验证和 threat model、resource identity、ownership、token lifecycle
设计，随后形成 accepted implementation scope。未完成这些证据前不得开发或部署 Cloud consumption。

| 未来职责 | 范围 |
|---|---|
| PowerBIDataPlane | discover、schema、member/value search、query、execute deterministic DAX |
| PowerBIControlPlane | refresh、refresh history、workspace metadata、report resource metadata、embed metadata、lifecycle |

refresh API 不得塞入 execute_dax adapter。以上为 M6 架构方向，尚无本轮代码实现。

## Production Backend — P0

Authentication / Entra identity、tenant namespace、principal namespace、Authorization、Ownership、
IDOR、OAuth token lifecycle、Secret leakage、cross-user cache isolation、RLS / OLS identity propagation、
fail-closed external authority handling 均为 P0。当前 M5 的本地 `test_user` 与 Mock/Real namespace
不是 enterprise identity 或 authorization；不得部署后仅替换显示用户名。

Token 只能存在 Auth / Transport boundary，不得进入 UserContext、Memory、Trace、Conversation
persistence。后续 persistence resource identity 必须包含 `tenant_id`、`principal_id`、
`conversation_id`。Report / Snapshot / Conversation / Memory 均需 server-side ownership validation；
客户端传来的 ID、tenant、principal 与 model key 均不能自行证明授权。跨用户 cache key 和
RLS / OLS identity 必须来自服务端验证的主体，外部 auth/schema/result authority 不完整时 fail closed。

## Production Backend — P1

multi-worker、multi-instance、restart behavior、transactions、idempotency、retry、timeout、
failure recovery、PostgreSQL migration path、Blob/Object Storage path、cache strategy、
distributed coordination when justified、schema migration、observability、audit、deployment、
upgrade compatibility。先证明资源归属、事务/重放/取消/失败恢复与隔离，再增加功能数量。
PostgreSQL / Blob / Redis 均尚未实现，不能把本地 SQLite + filesystem 的保证描述为生产云保证。

## 明确禁止事项

禁止第二 Planner/Grounding/Memory、Agent、LangGraph、RAG/vector DB、ontology server、LLM DAX、
任意代码/自由 HTML、直接生产写操作、无审批 authoring、自动 Real→Mock fallback、silent report overwrite。
本轮禁止新物流模板/分析能力/LLM判断/事实链与 eligibility 变化、RemoteMCP rewrite，以及
Entra/Fabric IQ/PostgreSQL/Blob/Redis/migration/M6 implementation。后续事项只在获批 scope 中扩展。
当前报告是 historical snapshot；M7 规划 Recipe + Artifact versions，不能用刷新覆盖历史证据。

## 测试 / CI / release 与 debugging

main 是唯一活动开发线。流程为 failure-first → minimal implementation → fresh gates →
必要且有界 Real → 白名单 staging → 中文 commit → push main → exact-SHA CI → remote audit。
不得 git add . / git add -A、force push、rebase、history rewrite、reset --hard、clean、删除分支；
push 前 fetch，remote main 已前进则停止，不覆盖用户变更。不打 Tag。

同一 root cause 的 P1 不因每次失败都停止：保留 reproducer、更新证据，在已授权边界内最多两轮
minimal forward-fix；达到上限仍失败，或出现新根因、修改边界扩大、architecture risk 时停止重新
评估。不得降低 validator、删除 negative tests、改 expected 迎合错误、Mock Real 或隐藏 warning/error。
新的额外修复轮次必须取得明确授权并记录到 Error Ledger。

Local automated、Local Real、Remote exact-SHA CI 分层记录；历史 PASS 不替代 fresh evidence。
不读取/输出/提交 .env、Secret、Token、PBIX、DB、真实业务数据、完整真实 prompt/response/trace dump。
临时资源必须标明 ownership 并 finally teardown，不自动删除用户或 ownership 不明资源。

本轮 Local normal backend required suite 只按用户授权 deselect test_business_language_stress.py 中
test_generator_covers_51200_safe_reproducible_cases、test_stress_report_has_zero_generated_failures。
测试节点与 CI full matrix 未修改；不重复大型 Real/stress/provider matrix。
检查：Documentation Governance、Version Consistency、Architecture、Repository Safety、Error Ledger、
Artifact Governance、Semantic Compatibility、Golden、backend normal suite、frontend tests/lint/typecheck/build。
CSS Browser Smoke 使用真实 Logistics 目录，核对无 Sales templates、文案、12px/1.5、可发送与零 console
warning/error；不新增 Playwright/Selenium、不重跑 Report Real E2E。

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts/check_documentation_governance.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_artifact_governance.py
D:\Conda\envs\PBIAgent\python.exe scripts/check_semantic_compatibility.py
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
```

本阶段 evidence 见 [M5.10.9](milestones/m5/m5_10_9_documentation_governance_and_final_seal.md)。旧长交接见
[Historical snapshot](archive/m5_pre_final_09_context_handoff.md)，仅作历史，不能继承旧 pending/current state。
