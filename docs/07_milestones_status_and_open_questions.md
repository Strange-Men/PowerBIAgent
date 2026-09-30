# 07 — 当前项目状态

> **状态：** Settings.version=M5.10.9；M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。
> 唯一当前项目状态 authority；路线见 [08](08_development_roadmap.md)，开发交接见 [09](09_context_handoff.md)。

## 当前阶段

M5.10.8 COMPLETE；M5.10.8 FIX COMPLETE。用户已完成前阶段人工 UI Smoke，并指出唯一遗留
empty-state 字体过大。本轮只改文档、version、12px CSS 与最小治理回归，不做业务功能。
M5 Core Analysis Kernel 与 Local MVP baseline 已冻结；下一阶段为 M6 productionization。

上一阶段最终绿色基线：`main@409fd521b4b503b6e8e56846806e099cd98e7a5b`，
[exact-SHA CI Run 36665958820](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36665958820)
completed/success，2026-09-30 fresh REST + fetch 核验。M5.10.8 发布基线
`ef5a4c8ead7c05576360d3070ecf0e286e841dc5` / Run `36661689674` 也已核验 success。
Phase A 已验证绿色候选：`main@a98f0fcaa8935aa3f371b6b2d6bdf0057b582d6d`，
[exact-SHA CI Run 36677238767](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36677238767)
completed/success。最终 seal 的自身 SHA 不写入自身提交；
以当前 checkout 的 `git rev-parse HEAD`、该 exact SHA 的
PowerBIAgent Validation / Full Validation (Windows) completed/success、fetch 后 HEAD==origin/main
与 clean worktree 联合解析发布基线。文档中的 final marker 只有在最终 SHA CI 绿色后成为有效 seal。

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
旧状态长记录保留于 [Historical snapshot](archive/m5_pre_final_07_milestones_status_and_open_questions.md)。
历史 milestone / ADR / archive 不另设当前状态。最终 seal 必须以最终 exact-SHA CI 为准。
