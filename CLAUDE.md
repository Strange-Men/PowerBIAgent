# CLAUDE.md — PowerBIAgent 通用开发协议

> 当前状态仅见 docs/07，路线仅见 docs/08，Cold Start Handoff 仅见 docs/09；本文件不另设 current-state authority。

## 当前开发入口

Settings.version=M6.0；M6.0 COMPLETE；M6.1 READY；M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。M5.10.8 与 FIX COMPLETE。
下一正式milestone为M6.1 Entra Identity / Login / Session，需下一轮用户授权；M6 production runtime尚未实现。
Cloud消费/目录/Product Auth UX设计见ADR-020与M6.0 evidence，官方重验与适用P0验收仍是implementation前提。
发布 baseline 按 09 的当前 exact-SHA CI + remote audit 解析，不继承已完成阶段的施工流程。

## Cold Start

先 Git status/branch/HEAD/origin/log/fetch，核对 main、clean 与 exact baseline；remote main 前进即停止。
按 AGENTS 与 docs/09 顺序读取 charter、07/08/09、Error Ledger、ADR index/相关 accepted ADR、
当前任务及 production/邻近 tests。不得以历史 PASS、旧 endpoint 或聊天记忆替代 fresh 证据。
简短 reality audit 后自动在授权范围继续；文档治理任务中的既有状态漂移由本轮修复，不因漂移重复求确认。

## Frozen Core / authority boundary

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

TurnPipeline 是唯一控制面，ToolGateway → PowerBIAdapter 是唯一 Power BI 路径。
LLM understands. Runtime proves. LLM 不拥有 canonical identity/member/date、DAX、business math、
QueryResult、coverage/horizon、VerifiedFact、factual Memory、report fact 或 HTML authority。
General current-message-only/no-tool/ZERO business state；歧义/残缺 fail closed；Natural Answer
基于 VerifiedFactSet/verified scope/真实 availability 并通过 FactOutputValidator，validator 不降低。
requested scope/observed coverage/measure-aware horizon 独立，未知 refresh 明示 UNKNOWN。
Report 只消费共享事实；八种 QueryShape 和 fixed Renderer authority 保持。

## M6 交接

生产级后端风险优先于功能数量。Auth/Entra、tenant/principal、ownership/IDOR、Token lifecycle、
RLS/OLS、cross-user cache、fail-closed 为 P0；生产 persistence/恢复/部署为 P1。详见 09。
Token 只留 Auth / Transport，不进入 UserContext/Memory/Trace/Conversation persistence。
可进入 M6 研究/设计；每个 implementation patch 必须单独取得用户批准的具体 scope。
先 fresh Cold Start、重查 Microsoft 官方能力、完成 P0 边界设计/验证并形成 accepted contract，
再实施 production path。ADR-006 SUPERSEDED；RemoteMCP legacy skeleton 不证明 endpoint/auth 合同。

## Git / debugging contract

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

提交名称与收口阶段按当前任务授权；current release markers 必须一致。
staging 前运行 Repository Safety、cached diff 与 documentation gate。自身 SHA 不写入自身提交；
最终 exact-SHA CI + remote audit 成立后完成该获批任务，下一 patch 另按 scope 授权。
