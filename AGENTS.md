# AGENTS.md — PowerBIAgent 仓库级 Agent 入口

> Claude、Codex 与其他代码 Agent 修改任何文件前，必须先阅读本文件。
> 本文件是仓库地图，不替代 PRD、ADR、路线图或 `CLAUDE.md`。

---

## 一、项目一句话目标

PowerBIAgent 是供公司内部少量用户使用的 Power BI 数据分析 Agent MVP。

核心目标链路：

```text
自然语言
→ FastAPI
→ TurnPipeline
→ DeepSeek 结构化生成
→ ToolGateway
→ Power BI Adapter
→ Power BI MCP
→ QueryResult
→ Answer / ReportSpec
```

## 二、当前真实状态

- 当前版本：M2.6.1 Known-answer 独立数值 Oracle 与多轮 Harness/Test Set 离线固化完成。
- M0—M1 已由 Tag `m1.7.2-m0-m1正式封板` 正式封板。
- Mock + Mock 完整可用。
- DeepSeek + Mock Power BI Chat 完整可用。
- 当前 Demo Provider 为 Local MCP + Power BI Desktop，真实 stdio / 协议 / 工具发现 / Desktop 连接已验证；Remote MCP 保留为延后生产化路径。
- M2.1—M2.5 已完成 Local Demo 封板；M2.6 已加固 Filter、TopN/Sort、Architecture Gate 与 Health 真实性；M2.6.1 已完成 Oracle、Multi-turn Case/Runner 与全部离线验证。
- 下一阶段为 M2.6.2 DeepSeek + Local MCP + Desktop 最终真实数值与多轮验收；不得提前开发 M3。
- M3 报表正式渲染不得提前开发。
- M4 持久化会话不得提前开发。
- M5 React 前端不得提前开发。

## 三、权威文档顺序

不得根据聊天记忆猜测项目状态。遇到冲突时按以下顺序处理：

1. 用户当前明确要求
2. `PROJECT_CHARTER.md`
3. `docs/00_product_requirements_document.md`
4. Accepted ADR
5. 当前轮设计文档
6. `docs/08_development_roadmap.md`
7. `docs/09_context_handoff.md`
8. `CLAUDE.md` 开发规则
9. 代码真实行为
10. 历史资料

产品方向按上述文档优先级判断；当前代码是否真的实现，必须用真实代码和测试结果验证。

## 四、每轮固定冷启动

修改任何文件前，只按任务需要读取：

1. `AGENTS.md`
2. `PROJECT_CHARTER.md`
3. `CLAUDE.md`
4. `docs/09_context_handoff.md`
5. `docs/08_development_roadmap.md` 当前阶段
6. `docs/ai_development_error_ledger.yaml`：读取结构、当前有效治理规则及与当前轮相关条目；不要求完整复盘所有历史错误
7. `docs/adr/README.md`
8. 当前阶段涉及的 ADR
9. 当前轮 Prompt 指定文档
10. 当前轮涉及的生产代码

不要默认读取：

- 完整 `CHANGELOG.md`
- `docs/archive/`
- 全部测试
- 全仓源码
- 历史 Commit diff

需要时再按任务局部读取，不做无目标的全仓扫描。

## 五、不可违反的架构铁律

1. TurnPipeline 是统一确定性控制面。
2. Mock 与 Real 必须共享同一执行骨架。
3. Power BI 调用只能经 ToolGateway。
4. ToolGateway 是 Power BI / Renderer 唯一工具执行入口。
5. Service / API / LLM 不得直接调用 MCP。
6. LLM 不得自主发现、选择或执行 MCP 工具。
7. 任何真实 Power BI MCP Provider（Local / Remote）必须封装在 PowerBIAdapter 边界内；不得形成两套 Pipeline。
8. Real 模式失败禁止静默回退 Mock。
9. Memory / Snapshot 写入仍由既定控制面管理，不建立第二套事务链。
10. 不得为了 M2 重构已封板的 Intent → QueryPlan → DAX → Answer / ReportSpec 主链。
11. LLM 可生成 QueryPlan 与 DAX，但业务语义只能来自已验证的 Semantic Model metadata 或明确业务定义；DAX 语法正确不是业务正确的充分条件。

Semantic Grounding 永久规则：不得发明 Measure、字段业务含义或日期口径，不得自行决定模糊业务术语；存在明确业务 Measure 时优先使用，不以裸列聚合重复定义；无法唯一消歧时必须 clarification，不得猜测。

同时禁止：

- 使用 LangGraph
- 引入多 Agent
- 重新引入 PydanticAI
- 绕过 Harness
- 复制新的 Real Pipeline

`backend/app/powerbi/local_mcp.py` 的职责冻结为 Local Provider / protocol Adapter。M3/M4/M5 默认不得修改；只有 Microsoft MCP Preview 兼容变化、Local Provider Bug 或 Provider 协议/响应问题允许修改。Renderer、Memory 与 UI 逻辑不得进入该文件。

## 六、当前 M2 预期数据链

```text
API
→ TurnService
→ TurnPipeline
→ Intent
→ ToolGateway.get_semantic_model_schema
→ PowerBIAdapter
→ MCP Client
→ Power BI
→ QueryPlan
→ DAX
→ ToolGateway.execute_dax
→ PowerBIAdapter
→ MCP Client
→ QueryResult
→ Answer / ReportSpec
→ Memory / Snapshot
```

当前 Demo 使用 Local MCP，Remote MCP 是延后生产化路径；二者只能替换 PowerBIAdapter 后的 Provider，不能改变上层主链。具体设计以 `docs/12_m2_powerbi_mcp_integration_plan.md`、ADR-006 与 ADR-007 为准；外部细节必须经当前 Provider 实机验证后才能写成事实。

## 七、修改前必须内部回答

每轮开发前先确认：

1. 我要修改的职责现在属于哪个模块？
2. 仓库是否已有接口、Adapter 或 Provider 可以复用？
3. 是否会绕过 TurnPipeline？
4. 是否会绕过 ToolGateway？
5. 是否提前实现后续 Milestone？

任一答案存在风险时，先停止开发并核实边界。

## 八、测试原则

- 优先修改或补充现有领域测试。
- 禁止继续创建 `test_m2_xxx.py` 这类版本型测试。
- 一个 Bug 尽量对应一个最接近真实生产入口的回归测试。
- 不为了测试数量增加机械重复测试。
- Real Power BI 不能进入普通 CI。
- CI 不得持有真实 Microsoft Token 或 DeepSeek Key。
- Mock 测试和 Fake MCP 用于自动 CI。
- 真实 MCP 只允许人工验收 Smoke。

## 九、Git 与文档规则

完整开发、Secret、Git、修复次数、官方证据与 Tag 规则见 `CLAUDE.md`，不得绕过。

- 禁止 force push。
- 禁止 `git add .`。
- 禁止 `git add -A`。
- Secret 永不进入仓库。
- 文档必须在 Commit 前完成。
- Commit 后不再追加纯文档回填 Commit。
- 每轮只完成一个明确 Goal。

---

*最后更新：2026-08-12 | M2.6.1 Oracle 与多轮 Harness 离线固化完成*
