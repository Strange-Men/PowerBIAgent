# AGENTS.md — PowerBIAgent 仓库入口

> Claude、Codex 与其他代码 Agent 修改文件前必须先读本文件。当前状态见
> `docs/09_context_handoff.md`，路线见 `docs/08_development_roadmap.md`。

## 当前开发入口

- 当前版本：**M5.10.6**（implementation 已进入 fresh full-gate / Real 验证阶段）。
- 正式基线：`main@9dfbf2f72bad299e41a138e9072a11caf8c678a7`。
- `M5.10.5 — 时间语义、事实防火墙与安全基线` 已 COMPLETE；exact-SHA CI
  Run `35088162355` success。人工测试确认事实安全主体有效，同时暴露自然回答、
  default-open conversation、capability wording 与 available data horizon 缺口。
- 当前阶段：`M5.10.6 — LLM 语义理解与自然事实表达重构`。production implementation
  已落地，完整 fresh gates、Real 与 exact-SHA 发布证据尚未完成。
- `M5.10.7 — 模板兼容与错误 UX 收口`、`M5.10.8 — MVP 最终 Real E2E / stress /
  mutation / historical / exact-SHA 收口` 均未启动。
- Semantic Layer 最终人工验收在 M5.10.6 完成后进行；`M5 FINAL=false`。

## Authority boundary

1. `TurnPipeline` 是唯一确定性控制面；Mock 与 Real 共用执行骨架。
2. Power BI 只能经 `ToolGateway → PowerBIAdapter`；Local/Remote 只替换 Adapter 后的
   Provider。Real 失败不得静默回退 Mock。
3. M5.10.6 的原则是 **LLM understands. Runtime proves.** LLM 可解释开放语言并输出
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
    migration、MCP runtime/Provider rewrite、LLM DAX、任意代码、写/删/更新、Forecast/Target/
    Budget、新 YoY/MoM capability、报表视觉重构及 M5.10.7/8 工作。

## 固定 Cold Start

按顺序读取：

1. `AGENTS.md`
2. `PROJECT_CHARTER.md`
3. `CLAUDE.md`
4. `docs/09_context_handoff.md`
5. `docs/08_development_roadmap.md`
6. `docs/ai_development_error_ledger.yaml` 的结构、有效规则与当前相关项
7. `docs/adr/README.md` 与当前相关 accepted ADR
8. 当前 Prompt 指定文档、涉及的 production code 与邻近 tests

不得用聊天记忆或历史 PASS 数字代替 fresh 仓库证据。文档冲突顺序：用户当前明确要求
→ `PROJECT_CHARTER.md` → 正式 PRD → accepted ADR → 当前专项设计 → 08 → 09 →
`CLAUDE.md` → 代码与 fresh 测试 → Archive。

## Git contract

- `main` 是唯一活动开发线；流程固定为 failure-first → minimal implementation → fresh gates
  → Real → 白名单 staging → commit → push main → exact-SHA CI → remote audit。
- 当前提交名固定为：`M5.10.6_LLM语义理解与自然事实表达重构`；不打 Tag。
- 禁止 `git add .`、`git add -A`、force push、rebase、history rewrite、`reset --hard`、
  `clean`、branch deletion。remote main 已前进则停止。
- CI 失败只允许 forward-fix；同一 root cause 最多两轮。禁止降低 validator、删除 negative
  tests、修改 expected 迎合错误、Mock Real 或隐藏 warning/error。
- 不读取、输出或提交 `.env`/Secret、真实业务数据、PBIX、DB、真实 prompt/response dump。
- Local automated、Local Real DeepSeek + MCP、Remote exact-SHA CI 必须分层记录。

---

*最后更新：2026-09-17 | M5.10.5 COMPLETE / CI 35088162355 success；M5.10.6 ACTIVE；M5.10.7/8 NOT STARTED；Semantic Layer FINAL ACCEPTANCE PENDING；M5 FINAL=false*
