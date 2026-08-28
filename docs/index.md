# Documentation Map

> 本文件只映射文档路径、owner、purpose 与阅读优先级，不新增产品或架构 Source of Truth。发生冲突时遵守 `AGENTS.md` 的权威顺序。

## P0 — Cold Start

每轮开发固定读取以下 7 个入口，再按任务追加当前相关 ADR：

| 路径 | Owner / purpose |
|---|---|
| `AGENTS.md` | 仓库地图、架构铁律、Cold Start |
| `PROJECT_CHARTER.md` | 项目使命、范围与不可静默改变的北极星 |
| `CLAUDE.md` | 通用开发、修复、Secret、Git、Commit/Tag 规则 |
| `docs/09_context_handoff.md` | 当前代码状态、限制、下一步与关键命令 |
| `docs/08_development_roadmap.md` | M0—M5 路线、当前 Milestone 与阶段边界 |
| `docs/ai_development_error_ledger.yaml` | 机器可校验错误治理规则与当前相关条目 |
| `docs/adr/README.md` | ADR 状态索引；继续读取本轮相关 accepted ADR |

`docs/index.md` 是导航入口，不要求在已知固定 Cold Start 路径时重复读取。P0 固定文件数为 7；实际总数为 7 + 当前相关 ADR 数量。

## P1 — 长期产品与工程基线

只在当前任务涉及相应领域时读取：

| 路径 | Owner / purpose |
|---|---|
| `docs/00_product_requirements_document.md` | 正式唯一 PRD |
| `docs/01_product_scope_and_frontend_skeleton.md` | 产品范围与前端骨架 |
| `docs/02_technology_selection_and_system_architecture.md` | 长期技术与系统架构；被 accepted ADR supersede 的部分以 ADR 为准 |
| `docs/03_intent_recognition_and_memory_system.md` | Intent、Memory 与状态契约 |
| `docs/04_powerbi_mcp_and_api_contracts.md` | Power BI Adapter/MCP 与 API 契约 |
| `docs/05_harness_test_and_acceptance.md` | Harness、Golden、Oracle 与验收规则 |
| `docs/06_security_git_and_development_standards.md` | 安全、Secret、Git 与开发规范 |
| `docs/07_milestones_status_and_open_questions.md` | 里程碑状态与仍需决策的事项 |
| `README.md` | 开发者快速运行与当前能力入口 |
| `CHANGELOG.md` | 精简版本变更摘要 |

## P2 — 专项规范与 Milestone 文档

| 路径 | Owner / purpose | 何时读取 |
|---|---|---|
| `docs/specs/10_frontend_visual_and_interaction_spec.md` | 前端视觉与交互专项规范 | M5 或相关契约任务 |
| `docs/specs/11_structured_answer_contract.md` | Answer/Report 组合输出专项契约 | 输出契约、M3/M5 任务 |
| `docs/specs/12_conversation_memory_and_resource_lifecycle_contract.md` | 多轮继承、archive/restore/delete、report ownership 与 artifact lifecycle | M5.3.3 多轮、会话或资源生命周期任务 |
| `docs/specs/13_m5_generalization_and_acceptance_contract.md` | M5 重建历史、M5.5—M5.10 scope isolation、Generalization 与人工验收 Gate | M5.4.2 及所有后续 M5 任务 |
| `docs/milestones/m5/m5_8_1_local_mcp_performance_plan.md` | M5.8.1 profiling、session reuse、cache、singleflight、并发与验收边界 | M5.8.1 |
| `docs/milestones/m2/12_m2_powerbi_mcp_integration_plan.md` | M2 Local Demo / Remote Production 专项计划 | M2 Provider、Smoke、Remote 证据任务 |
| `docs/adr/ADR-005_deterministic_turn_pipeline_and_controlled_llm_architecture.md` | TurnPipeline / ToolGateway 总体决策 | 控制面与工具边界 |
| `docs/adr/ADR-006_remote_powerbi_mcp_production_integration.md` | Remote MCP 生产化决策 | 仅重新获批 Remote 时 |
| `docs/adr/ADR-007_local_mcp_demo_validation_path.md` | Local MCP Demo Provider 决策 | Local Provider/Smoke |
| `docs/adr/ADR-008_business_semantic_catalog_and_grounding_authority.md` | Business Semantic authority | Grounding、Catalog、Member、Time、State |
| `docs/adr/ADR-009_deterministic_query_execution_and_verified_fact_authority.md` | DAX/Layer3/Fact authority | 执行与外部事实边界 |
| `docs/adr/ADR-010_deterministic_report_template_and_data_plan_authority.md` | M3 TemplateContract / ReportDataPlan authority | M3 报表合同、渲染与资源任务 |

未来阶段文档放在：

- `docs/milestones/m3/`
- `docs/milestones/m4/`
- `docs/milestones/m5/`

同一小版本若确有多份阶段文档，可使用 `docs/milestones/m3/m3.2/` 等简洁子目录。不要为每个 Bug 新建 Markdown；长期架构决策达到 ADR 门槛时才在 `docs/adr/` 新增 ADR。

## P3 — 历史资料

`docs/archive/` 保存已封板路线、历史审计和原始输入，默认不读，不参与当前状态决策。

- 原始 PRD：`docs/archive/original/PRD.md`
- M0—M2.6.3 路线历史：`docs/archive/m0-m2.6.3_roadmap_history.md`
- 正式 PRD 始终是 `docs/00_product_requirements_document.md`

## 按任务读取

| 任务 | P0 后按需追加 |
|---|---|
| 产品范围或需求 | 00/01 + 相关 accepted ADR |
| Intent、Grounding、Clarification、Memory | 03 + ADR-008/009 + 相关 Error Ledger |
| DAX、Layer 3、VerifiedFactSet、Answer/Report factual boundary | 04/05 + ADR-009 |
| Local MCP / Adapter / Smoke | 04/05 + M2 plan + ADR-006/007 |
| 安全、Git、CI、治理脚本 | 06 + CLAUDE + 相关 gate/test |
| M3 报表 | specs/11 + ADR-010 + M3 milestone 文档（如后续需要） |
| M5 前端 | 01 + specs/10/11/12/13（获批后） |

## 新增文档规则

`docs/` 根层只允许：

- `00`—`09`
- `index.md`
- `ai_development_error_ledger.yaml`
- `adr/`、`specs/`、`milestones/`、`archive/`、`assets/`

禁止继续新增 `docs/13_xxx.md`、`14_xxx.md` 等编号文档，除非用户明确扩充 00—09 主体系。08 与 09 路径固定，不移入 milestone 目录。Documentation Governance Gate 由 `scripts/check_documentation_governance.py` 执行。

---

*最后更新：2026-08-28 | M5.8.1 前置性能加速与本地 MCP 会话复用 COMPLETE*
