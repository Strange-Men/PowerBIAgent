# CLAUDE.md — PowerBIAgent 通用开发协议

> 本文件只保留 Cold Start、authority boundary、Git contract 与当前开发入口。当前状态和
> 路线分别以 `docs/09_context_handoff.md`、`docs/08_development_roadmap.md` 为准。

## Cold Start

修改任何文件前：

1. 执行 `git status`、`git branch --show-current`、`git rev-parse HEAD`，确认无未授权改动或
   merge/rebase/cherry-pick/revert 中间状态。
2. 按 `AGENTS.md` 的固定 Cold Start 顺序读取 P0、当前 ADR、专项计划、涉及的 production
   code 与邻近 tests。
3. 核对上一轮 commit、`origin/main`、09 handoff、`D:\Conda\envs\PBIAgent`。普通轮次没有
   Tag 不构成阻塞。
4. 用不超过 200 字复述目标/进度/允许与禁止范围，再用不超过 200 字列出命中的 Error
   Ledger、ADR、漂移风险与禁止边界。
5. 上一轮 commit 不存在、handoff 冲突、Error Ledger 不可读或 remote main 已前进时停止。

## Authority boundary

- `TurnPipeline` 是唯一控制面；`ToolGateway → PowerBIAdapter` 是唯一 Power BI 路径。
- LLM 只拥有 bounded language interpretation 与 natural wording authority，不拥有 canonical
  identity/member/date、DAX、business math、QueryResult、coverage/horizon、VerifiedFact、
  factual Memory、report fact 或 HTML authority。
- Runtime SemanticCatalog/Grounding、StateTransition/Completeness、Deterministic DAX/Layer 3、
  Result Inspection/VerifiedFactSet 分别拥有业务语义绑定、canonical state、执行与外部事实
  authority。歧义、未知或不完整必须 fail closed。
- General lane current-message-only、no-tool、无业务状态；mixed request 取最高风险并进入严格
  business pipeline。conversation false-negative 必须以 `requires_business_grounding` 升级，
  不得猜组织数据。
- Natural Answer 只能基于 VerifiedFactSet、verified user-facing scope 与真实 data availability，
  并在发送前通过 `FactOutputValidator`；validator 不得降低。
- `requested scope`、`observed coverage`、measure-aware `available data horizon` 独立。horizon
  只能由真实数据或 canonical-derived deterministic auxiliary probe 证明，不能冒充 refresh time。
- Report 只消费共享事实/availability；QueryShape 仍八种；禁止第二 Planner/Grounding/Memory、
  新 Agent/RAG/DB/migration、LLM DAX、MCP/Provider rewrite、报表视觉重构与未来 milestone 工作。

## 当前开发入口

- Baseline：`main@9dfbf2f72bad299e41a138e9072a11caf8c678a7`。
- M5.10.5 COMPLETE；exact-SHA CI Run `35088162355` success。
- 当前：`M5.10.6 — LLM 语义理解与自然事实表达重构`；专项计划：
  `docs/milestones/m5/m5_10_6_llm_semantic_interpretation_and_natural_factual_presentation_plan.md`。
- 下一步仅为 M5.10.7 模板兼容与错误 UX，随后 M5.10.8 最终收口；二者均 NOT STARTED。
- production 修改完成前 Settings.version 保持 M5.10.5；完成后更新 M5.10.6。
- Semantic Layer FINAL ACCEPTANCE 在 M5.10.6 后进行；`M5 FINAL=false`。

## Git contract

- 正式流程：Spec → RED reproducer → regression → minimal implementation → focused/cross-domain/
  full gates → Real DeepSeek + Local MCP → whitelist staging → commit → push main → exact-SHA CI
  → remote audit。
- Commit：`M5.10.6_LLM语义理解与自然事实表达重构`；不打 Tag，不自动进入 M5.10.7。
- 禁止 `git add .` / `git add -A`、force、rebase、history rewrite、reset hard、clean、branch
  deletion。Push 前再次核对 remote main；若已前进则停止。
- CI 失败只做 failure reproducer 驱动的 minimal forward-fix；同根因最多两轮。
- staging 前运行 repository safety，并检查 cached diff；不得读取/提交 `.env`、Secret、PBIX、
  DB、真实业务数据、完整真实 prompt/response、trace dump。
- Commit 前同步 README（仅当 current state 过期）、CHANGELOG、07/08/09、专项计划、Error
  Ledger 与 Settings.version；当前 commit SHA/CI 不预填。Commit 后不得追加文档回填 commit。
- Local automated、Local Real、Remote CI 证据严格分栏，禁止相互冒充。

---

*最后更新：2026-09-17 | M5.10.5 COMPLETE / CI 35088162355 success；M5.10.6 ACTIVE；M5.10.7/8 NOT STARTED；M5 FINAL=false*
