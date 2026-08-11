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

- 当前版本：M1.8 Codex 接管准备。
- M0—M1 已由 Tag `m1.7.2-m0-m1正式封板` 正式封板。
- Mock + Mock 完整可用。
- DeepSeek + Mock Power BI Chat 完整可用。
- 真实 Power BI 尚未接入。
- M2 尚未开始业务实现。
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
6. `docs/adr/README.md`
7. 当前阶段涉及的 ADR
8. 当前轮 Prompt 指定文档
9. 当前轮涉及的生产代码

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
7. Remote MCP 必须封装在 PowerBIAdapter 边界内。
8. Real 模式失败禁止静默回退 Mock。
9. Memory / Snapshot 写入仍由既定控制面管理，不建立第二套事务链。
10. 不得为了 M2 重构已封板的 Intent → QueryPlan → DAX → Answer / ReportSpec 主链。

同时禁止：

- 使用 LangGraph
- 引入多 Agent
- 重新引入 PydanticAI
- 绕过 Harness
- 复制新的 Real Pipeline

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

具体 M2 设计以后续 M2.0 官方文档调研结果为准。

本文件不提前写死尚未验证的 MCP SDK、OAuth 实现或微软接口细节。

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

*最后更新：2026-08-11 | M1.8 Codex 接管准备与仓库上下文固化*
