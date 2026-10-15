# AGENTS.md — PowerBIAgent 仓库入口

> Claude、Codex 与其他代码 Agent 修改文件前必须先读本文件。
> 当前状态见 `docs/07_milestones_status_and_open_questions.md`；路线见
> `docs/08_development_roadmap.md`；下一开发者交接见 `docs/09_context_handoff.md`。

## 当前开发入口

- 当前版本：**M6.4.1**（治理维护发布）；M6.4 FINAL COMPLETE 是已验证稳定基线。
- M5.10.9 COMPLETE；M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN；M6 PRODUCTIONIZATION READY。M6.0–M6.3 各自按自身 CI/Audit COMPLETE；IQ_ACCEPTED。
- M6.4.1 仅处理仓库外测试资产治理、README 信息架构、current-state 一致性、IQ 保守结果边界明确化及 Test B OLS 证据状态；不实施 Schema cache、connection reuse、Favorites/Preferences，不进入 M6.5。
- 本轮治理与 fresh gates 已 PASS，Settings.version=M6.4.1；维护发布只按自身 exact-SHA CI/Remote Audit/clean 生效。
- 07 是当前状态，08 是路线，09 是唯一交接；根入口不重复保存浮动 SHA/CI。
- 每个后续 implementation 仍须明确 scope、fresh Cold Start、Microsoft 官方能力重新验证与适用 P0 前置设计/验证。

## Authority boundary

1. `TurnPipeline` 是唯一确定性控制面；Mock 与 Real 共用执行骨架。
2. Power BI 只能经 `ToolGateway → PowerBIAdapter`；Local/Remote 只替换 Adapter 后的
   Provider。Real 失败不得静默回退 Mock。
3. M5.10.6+ 的原则是 **LLM understands. Runtime proves.** LLM 可解释开放语言并输出
   bounded candidate/draft，但不拥有 canonical object/member/date、DAX、QueryResult、
   coverage、available horizon、numeric fact、business Memory 或 report fact authority。
4. Runtime `SemanticCatalog` 与 `Grounding` 证明业务对象、成员和 canonical identity；
   `StateTransition` 与 `Completeness` 证明可执行 canonical state。歧义/未知/残缺必须在
   DAX 前 clarification/no-match，且 ZERO factual Memory commit。
5. QueryShape 固定为八种：`SCALAR`、`ENTITY_LIST`、`GROUPED`、`RANKING`、
   `MEMBER_SET`、`FILTERED_AGGREGATION`、`TREND`、`BOUNDED_TREND`。
6. Real 只执行受限 Deterministic DAX；Independent Layer 3、Result Inspection 与
   `VerifiedFactSet` 分别保留执行/结果/外部事实 authority。业务数学不得由 LLM 计算。
7. General conversation 默认开放，但必须 current-message-only、no-tool、ZERO schema/
   member/DAX/report/business Memory/pending mutation；若需要组织业务事实必须升级到正式链。
8. Natural presentation 可由 LLM 组织措辞，但只能消费 Verified Facts、verified user-facing
   scope 与真实 data availability context，且必须经过 `FactOutputValidator`；失败只能 repair
   或 deterministic safe fallback。
9. `requested_query_scope`、`observed_data_coverage`、`available_data_horizon` 三者独立。
   horizon 必须 measure/fact-family + temporal-dimension aware，来自真实数据；不得用 Date 表
   最大值、当前日期、requested end、provenance 时间或 LLM 猜测，也不得冒充 refresh time。
10. Report 复用同一 Verified Facts 与 availability context，不得新增 parser、planner、
    availability 逻辑或事实解释。固定模板与 Renderer authority 保持不变。
11. PendingClarification 与 committed Memory 分离；general turn 不消费、不改写业务 pending 或
    Memory。模型切换不得继承旧模型业务上下文。
12. 禁止第二 Planner/Grounding/Memory、Agent、LangGraph、RAG/vector DB、ontology server、
    LLM DAX、LLM 任意代码、未经审批的生产写/删/更新。migration、MCP runtime/Provider 扩展、
    Forecast/Target/Budget、新 YoY/MoM capability 与报表视觉变更只能按独立获批 scope 和正式合同实施，
    不得由 M6 READY 自动授权或绕过 Frozen Core。

## 固定 Cold Start

先 git fetch origin，再核对 branch、HEAD、origin/main、worktree、staging 与 log；初始要求 main、
HEAD==origin/main、clean worktree/staging。开发中允许本轮已授权白名单改动；未知用户修改或远端基线前进立即停止。

按顺序读取：

1. `AGENTS.md`
2. `PROJECT_CHARTER.md`
3. `CLAUDE.md`
4. `docs/07_milestones_status_and_open_questions.md` → `docs/08_development_roadmap.md` → `docs/09_context_handoff.md`
5. `README.md`、`CHANGELOG.md`（导航与历史摘要）
6. `docs/ai_development_error_ledger.yaml` 的结构、有效规则与当前相关项
7. `docs/adr/README.md` 与当前相关 accepted ADR
8. 当前 Prompt 指定文档、涉及的 production code 与邻近 tests

不得用聊天记忆或历史 PASS 数字代替 fresh 仓库证据。文档冲突顺序：用户当前明确要求
→ `PROJECT_CHARTER.md` → 正式 PRD → accepted ADR → 当前专项设计 → 08 → 09 →
`CLAUDE.md` → 代码与 fresh 测试 → Archive。

## 测试资产长期规则

所有本地 test/cache/acceptance/evidence/screenshot/diagnostic/synthetic DB/report/benchmark/runner
output 均进入独立仓库外根 `PBIAGENT_TEST_ROOT`（目录名 PBIAgentTest），按 milestone/purpose/run
分层；禁止写入工作区父目录或正式仓库。正式测试源码、fixtures 定义与配置继续属于 Git。
本地验证使用 `scripts/run_local_validation.py --milestone <版本> [--frontend] -- <命令>`；显式
cache_dir/TMP/TEMP/basetemp，参数使用正斜杠和正确引用，owned temp 在结束/异常时自动清理。
执行后核对 Git status 无新临时目录；真实产品持久化不是测试资产，不移动、读取或删除用户 DB。
CI 保持既有可移植命令，不写本机路径。DB 只有 synthetic 来源明确时可 byte copy/hash；
未分类 DB 保留并报告。迁移必须 Inventory → Copy → SHA/数量/字节 Verify → Reference Migration
→ Regression → 清理 → fresh inventory/receipt，禁止 move-first。历史证据不可冒充当前 PASS。

## Git contract

- main 是唯一正式活动开发线，默认在 main 开发、提交、推送。流程固定为：
  Cold Start → Main 开发 → Failure-first → Minimal Implementation → Local Validation → 必要 Real → 白名单 Staging → 中文 Commit → Push main → 一次 Main Exact-SHA CI → Remote Audit。
  不强制临时开发分支、PR 或 Phase A / Final 双 CI；仅当用户明确要求或 GitHub 权限客观要求时才使用 PR。
  不自动修改 GitHub 分支保护；普通 push 被拒绝即停止报告，不以 force push、关闭更多保护或另建 PR 绕过。
  管理员豁免是既有工作流的权限条件，不允许忽视失败的 CI；每个最终实际 main 提交必须通过自身完整 CI，不能继承旧 SHA 或 PR CI。
- 禁止 `git add .`、`git add -A`、force push、rebase、history rewrite、`reset --hard`、
  `clean`、未经授权删除分支。不覆盖用户修改，不自动打 Tag；push 前 fetch，remote main 相对本轮基线前进即停止。
- CI 失败只允许 forward-fix；同一 root cause 最多两轮，P1 不因每次失败都停止；上限仍失败、新根因、边界扩大或 architecture risk 才停止重新评估。禁止降低 validator、删除 negative
  tests、修改 expected 迎合错误、Mock Real 或隐藏 warning/error。
- 不读取、输出或提交 `.env`/Secret、真实业务数据、PBIX、DB、真实 prompt/response dump。
- Local automated、Local Real DeepSeek + MCP、Remote exact-SHA CI 必须分层记录。

---


## Frozen Core / M6 扩展纪律

TurnPipeline、QuestionRouter、SemanticFrame、Grounding、StateTransition、CanonicalQueryPlan、
DeterministicDAXBuilder、DAXSafety、ResultInspection、VerifiedFactSet、ReportPlanner、ReportSpec、
Renderer、Presentation、TypedFailure、LLM Provider Registry、Harness、ToolGateway。

Frozen 表示已有 authority / contract / architecture boundary 不再随意重构，允许
failure-first minimal forward-fix 修复 correctness bug。禁止第二 Planner / Grounding / Memory，
禁止重设计 deterministic factual chain；M6 优先经 Adapter / Repository / Service 扩展，能扩展就不重构 Core。

生产级后端风险优先于功能数量；每个M6 implementation按09重新验证Microsoft官方能力与适用P0边界。ADR-020接受Cloud消费/目录设计，ADR-006已SUPERSEDED。Token只允许Auth/Transport；tenant/principal/ownership与RLS/OLS必须先证明。

*最后更新：2026-10-15 | M6.4 FINAL COMPLETE；M6.4.1 维护发布按自身 CI/Audit/clean 生效；M5 FINAL/FROZEN；当前状态以07/08/09为准*
