# 08 — 开发路线

> **状态：** M2.6.4 Final Hardened Acceptance + Documentation Governance 验收候选
> **用途：** 只记录当前路线、阶段边界和已封板摘要；逐版本历史见 `CHANGELOG.md`、Git 与 `docs/archive/m0-m2.6.3_roadmap_history.md`。

## 路线总览

| Milestone | 目标 | 状态 |
|---|---|---|
| M0 | 仓库、契约、Harness、FastAPI 与 Mock 基础 | ✅ 已封板 |
| M1 | DeepSeek 接入、统一 TurnPipeline、架构/安全/CI 收口 | ✅ 已封板 |
| M2 | Local MCP + Power BI Desktop 真实数据问答与 Truth Boundary | ✅ M2.6.4 本地验收完成，待远程审计 |
| M3 | 固定模板报表正式渲染与资源契约 | ⬜ 下一功能阶段 |
| M4 | 持久化会话、搜索与最近对话 | ⬜ 未开始 |
| M5 | React + Vite 极简对话前端与联调 | ⬜ 未开始 |

M0—M1 正式 Tag 为 `m1.7.2-m0-m1正式封板`。M2 Local Demo Tag `m2-local-powerbi-demo-release` 保持不变；M2.6.4 不创建 Tag、不合并 `main`，先等待远程审计。

## 已封板阶段摘要

### M0 — Foundation

完成 Pydantic 数据契约、结构化 Memory、ToolGateway、ETCLOVG Harness、Mock LLM/Power BI、FastAPI `/health` 与 `/api/v1/chat`、幂等与并发控制。M0 详细轮次已归档。

### M1 — DeepSeek 与统一控制面

完成 DeepSeek Provider、Intent/QueryPlan/历史 Mock DAX/Answer/ReportSpec 兼容链，以及 ADR-005 确定性 TurnPipeline。PydanticAI 与旧 AgentRuntime 已删除；Mock/DeepSeek 共用控制面，ToolGateway 成为唯一工具入口。安全扫描、Error Ledger、Architecture Gate、通用 CI 与 M0—M1 封板完成。

### M2.0—M2.5 — Local Power BI Demo

按 ADR-006/007 将 Remote 生产化 Deferred，使用 Local MCP + Power BI Desktop 逐步验证 stdio/协议/工具发现、Schema、DAX、QueryResult、现有 TurnPipeline 与 Business Golden。Local/Remote 差异始终隔离在 PowerBIAdapter 后，Real 失败不回退 Mock。

### M2.6—M2.6.1 — Correctness Contract

- Real Filter 仅 `eq=SUPPORTED`；其他 operator fail closed。
- TopN selection 与 final ORDER BY 分离验证；ties 可合法超过 N。
- 建立独立 scalar/grouped/ordered Known-answer Oracle、8 Case（2 holdout）与正式 6 Conversation / 16 Turn 多轮契约。

### M2.6.2 — Business Semantic Grounding

ADR-008 固化 runtime schema + model-scoped glossary + runtime member + deterministic time authority。Intent/QueryPlan LLM 降为 weak signal；Grounding + StateTransition 独占 Canonical QueryPlan slots。PendingClarificationContext 与 committed Memory 分离，partial clarification 不可执行或提交。

### M2.6.3 — Deterministic Execution & Verified Facts

ADR-009 固化：

```text
Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ Power BI
→ QueryResult
→ VerifiedFactSet
→ fact-bounded Answer / ReportSpec
```

Real DAX LLM call count 为 0。VerifiedFactSet 是外部数字、结果顺序、极值、筛选、时间与 provenance 的唯一 authority；无法证明的因果、趋势或严格排名不输出。

## 当前阶段：M2.6.4

目标是 M0—M2 最终技术收口、文档真实性恢复、文档治理与 fresh hardened acceptance，不新增 M2 大架构。

### 技术收口

- TopN ties：只把 QueryResult order 表达为 `result_position`，不把 row index 宣称为严格 business rank；保持 ties may exceed N。
- Bounded semantic selection：exact canonical/approved alias/runtime metadata 继续 deterministic；LLM 只能在 metadata-backed Catalog shortlist 内选 ID，证据不唯一即 clarification，非法 ID 即 UNRESOLVED。
- Intent `UNSUPPORTED`：明确破坏性/非数据请求保持廉价早停；data/report/metric/filter/time/ranking-shaped 请求必须进入现有 Grounding/capability check，失败不得污染 Memory。

### 文档治理

- 保留 `docs/00`—`09` 原路径；08 只做 Roadmap，09 只做当前交接。
- 新增 `docs/index.md` 文档地图。
- 原始 PRD 归档到 `docs/archive/original/PRD.md`；正式 PRD 唯一 SOT 为 `docs/00_product_requirements_document.md`。
- 10/11 移入 `docs/specs/`；12 移入 `docs/milestones/m2/`。
- 新增 deterministic Documentation Governance Gate，并纳入 CI。

### Acceptance

必须 fresh 通过 full backend pytest、Golden、Architecture、Repository Safety、Error Ledger、Documentation Governance、`git diff --check`，以及 Semantic Grounding、Clarification、Deterministic DAX、Independent Layer 3、VerifiedFactSet、fact-bounded output、ties、bounded selector、unsupported routing 的专项回归。

本轮 fresh 验收已完成：全量 backend `1397 passed`；Golden 11/11（Real 专用 case 1 个按设计跳过）；Real Semantic 34/34，production E2E Known-answer 8/8、Holdout 2/2、6 Conversation/16 Turn、`a1→a2→a3` 10/10、3/3 TopN，fallback/pollution/DAX LLM/Answer LLM 均为 0。当前 PBIX 的三个 TopN 边界未出现并列；ties truth safety 由固定 deterministic regression 覆盖，不把数据分布当作架构前提。

若 M2.6.4 暴露重大架构缺陷，停止并报告 architecture failure，不创建 M2.6.5/M2.6.6。

## 后续路线

### M3 — 报表生成闭环

在用户明确批准后，固化报表资源 ID、查看/下载契约与固定模板渲染。Renderer 仍只能经 ToolGateway；不得改变 VerifiedFactSet 事实边界，不得把渲染逻辑放入 `local_mcp.py`。

### M4 — 持久化会话

在用户明确批准后，实现持久化会话、历史搜索与最近对话；沿用 TurnPipeline 单写入者与 Pending/Committed 分离，不建立第二事务链。

### M5 — React 前端

在用户明确批准后，按 `docs/specs/10_frontend_visual_and_interaction_spec.md` 使用 React + Vite 实现极简对话 UI；Provider Secret 永不进入前端。

## 永久阶段边界

- 不使用 LangGraph、多 Agent 或 PydanticAI。
- 不复制 Pipeline/Service，不绕过 TurnPipeline、ToolGateway、PowerBIAdapter、Harness 或 Memory/Snapshot 控制面。
- Remote MCP 只有管理员条件具备且用户另行批准后，才按 ADR-006 恢复。
- M3/M4/M5 必须逐阶段获得用户批准；当前阶段未验收不得提前实现。
- 普通小轮不创建 Tag；禁止 force push。

---

*最后更新：2026-08-14 | M2.6.4 final hardened candidate*
