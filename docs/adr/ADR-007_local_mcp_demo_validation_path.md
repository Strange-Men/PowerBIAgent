# ADR-007 — Demo 阶段使用 Local Power BI MCP 验证真实流程

- **状态：** accepted
- **日期：** 2026-08-11
- **决策者：** 用户明确批准
- **统一计划：** `docs/milestones/m2/12_m2_powerbi_mcp_integration_plan.md`

---

## 背景

M2 Demo 的目标是先证明 PowerBIAgent 经既有控制面访问真实 Power BI，并为后续 Schema、DAX、QueryResult 与 DeepSeek 问答建立可运行路径。Remote MCP 当前受公司 Tenant setting、Entra App 与管理员权限前置条件阻塞；这些是外部治理条件，不是 ADR-006 架构失败。

## 决策

1. Demo 阶段使用 Microsoft Power BI Local Modeling MCP Server，通过 stdio 连接本机 Power BI Desktop。
2. Local MCP 只作为 `LocalMCPPowerBIAdapter` 后的 Provider；上层仍是 TurnPipeline → ToolGateway → PowerBIAdapter，不建立 Local Service 或 Local Pipeline。
3. M2.1 只验证 Server 启动、协议协商、`list_tools`、Desktop 实例发现与连接；不读取完整 Schema、不执行 DAX、不调用 DeepSeek。
4. Local Server 使用官方 Preview npm 包的明确版本并启用 `--readonly`；M2.1 只允许 Adapter 内部调用连接发现能力，不向业务层或 LLM 暴露建模写工具。
5. M2.2—M2.5 先沿 Local Adapter 完成真实 Schema、DAX、现有 TurnPipeline 与 Golden 验收。
6. 公司管理员条件具备且用户批准生产化阶段后，只替换 `LocalMCPPowerBIAdapter → RemoteMCPPowerBIAdapter`；上层 TurnPipeline、ToolGateway、Harness 与语义正确性契约不重写。

## 与其他 ADR 的关系

- ADR-005 继续负责 TurnPipeline、ToolGateway 与受控 LLM 总体架构，完全不变。
- ADR-006 继续负责 Remote Power BI MCP 生产化接入，保持 accepted；ADR-007 不 supersede ADR-006。
- ADR-007 只决定当前 Demo 的真实 Power BI Provider 验证顺序，不允许 Local / Remote 形成两套 Pipeline，也不允许 Real 失败回退 Mock。

## 后果

- 正面：在不等待公司 Tenant 治理前置条件的情况下，先验证真实产品链路；Local/Remote 差异仍被 Adapter 隔离。
- 负面：Local Modeling MCP 是 Public Preview，依赖 Windows、Node.js 与已打开的 Power BI Desktop；其工具包含写能力，因此必须使用只读模式并保持业务入口白名单。

## M2.2 实机补充

固定 beta.12 已在 `--readonly` 下通过五类 Schema 工具的 `List` / `Get` 真实读取并标准化 Desktop 模型；原始工具名与响应仍封装在 LocalMCPPowerBIAdapter 后，ToolGateway 继续只暴露项目 Schema 抽象。该观察不改变 ADR-005、ADR-006 或本 ADR 的决策关系。

## M2.3 实机补充

固定 beta.12 已在同一只读边界内通过 `dax_query_operations Execute` 返回可验证 row data；固定 ROW 值 1 与两个 Demo Measure 的实际数值均成功标准化为 `source_mode=real` 的 QueryResult。Microsoft Issue #124 仍为 Open，当前实机仅能证明该组合未复现，不能证明官方已修复。ToolGateway 继续只暴露项目 `execute_dax` 抽象，DeepSeek + Local Chat 仍延后 M2.4。

---

*最后更新：2026-08-11 | accepted；M2.3 实机 DAX / QueryResult 观察补充*
