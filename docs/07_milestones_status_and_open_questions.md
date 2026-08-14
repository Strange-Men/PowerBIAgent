# 07 — 里程碑状态与待确认事项

> **状态：** M2.6.4 — M0—M2 ready for final seal；Final Tag 待用户授权
> 详细历史见 `CHANGELOG.md`、`docs/08_development_roadmap.md` 与 Git。

## 里程碑总览

| Milestone | 交付范围 | 状态 |
|---|---|---|
| M0 | 项目基础、契约、Harness、Mock、FastAPI | ✅ 已完成 |
| M1 | DeepSeek、统一 TurnPipeline、架构/安全/CI | ✅ 已完成并封板 |
| M2.0—M2.5 | Local MCP + Desktop Schema/DAX/Chat/Golden | ✅ 已完成 |
| M2.6 | Filter/TopN correctness、Architecture Gate、Health truth | ✅ 已完成 |
| M2.6.1 | 独立 Oracle、8 Case/2 holdout、正式 6 Conversation/16 Turn | ✅ 已完成 |
| M2.6.2 | Business Semantic Catalog、Grounding、StateTransition | ✅ 已完成 |
| M2.6.3 | Deterministic DAX、Independent Layer 3、VerifiedFactSet、Pending Clarification | ✅ 已完成 |
| M2.6.4 | 最终技术加固、文档治理、fresh offline/Real acceptance | ✅ 完成；Final Tag 待用户授权 |
| M3 | 固定模板报表正式渲染与资源契约 | ⬜ 下一阶段，未批准开发 |
| M4 | 持久化会话与历史搜索 | ⬜ 未开始 |
| M5 | React + Vite 前端与联调 | ⬜ 未开始 |

## 当前能力状态

| 能力 | 状态 |
|---|---|
| TurnPipeline / ToolGateway / Memory-Snapshot 单一控制面 | ✅ |
| Mock + DeepSeek Provider，共享执行骨架 | ✅ |
| Local MCP + Power BI Desktop | ✅ Real Demo；Remote Deferred |
| Business Semantic authority | ✅ ADR-008；Grounding/StateTransition 独占 canonical slots |
| DAX authority | ✅ Real deterministic；历史 Mock compatibility 可保留 LLM DAX |
| Independent Layer 3 | ✅ 受限 grammar fail closed |
| Fact authority | ✅ VerifiedFactSet；Answer/Report fact-bounded |
| Clarification | ✅ PendingClarificationContext 与 committed Memory 分离 |
| TopN | ✅ selection/order 分离；ties may exceed N；只声称 result position |
| Bounded selection | ✅ Catalog-owned metadata shortlist；低证据不提交 canonical truth |
| UNSUPPORTED routing | ✅ 明确 out-of-scope early-stop；data-shaped 请求进入 Grounding |
| 正式 Renderer / 持久化会话 / React | ⬜ M3 / M4 / M5 |

## 待确认事项

| 事项 | 决策时点 |
|---|---|
| M0—M2 final Tag 名称与是否创建 | 仅用户明确批准后 |
| M3 报表资源 ID、保存、查看与下载契约 | M3 开始前 |
| M4 持久化介质与会话搜索策略 | M4 开始前 |
| M5 前端状态管理与展示范围 | M5 开始前 |
| Remote MCP Tenant setting、Entra App、委托权限与模型权限 | 管理员条件具备并重新批准后 |

## 当前真实风险

- Local Modeling MCP 是 Preview；官方包、Desktop 或协议变化后需重新人工 Smoke。
- M2 grammar 有意只支持 Measure、Dimension、EQ、resolved TimeRange、single-measure Sort/TopN；comparison、非 EQ 与通用 DAX 不得宣称支持。
- Remote MCP 生产化仍受外部管理员/授权条件阻塞，但不影响 Local Demo 架构正确性。
- Memory/Snapshot 当前为单进程；分布式/持久化能力属于 M4。

## Tag 与基线

| 项目 | 值 |
|---|---|
| M0—M1 正式 Tag | `m1.7.2-m0-m1正式封板` → `23d8ddb` |
| M2 Local Demo Tag | `m2-local-powerbi-demo-release` → `c9af48a` |
| M2.6.4 远程 main 起点 | `ab9c6a6fba2e0cf9919c1366d37f8c6beb1f5e32` |
| M2.6.4 Tag | none；本轮禁止创建 |

---

*最后更新：2026-08-14 | M2.6.4 M0—M2 ready for final seal；Tag / M3 均待用户明确批准*
