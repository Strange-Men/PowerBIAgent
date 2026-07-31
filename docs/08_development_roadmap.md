# 08 — 开发路线

> **状态：** M0.4 已完成
> **更新频率：** 每轮结束时更新完成状态

---

## 路线总览

```
M0 开发准备 (6轮)
  M0.1 仓库初始化与文档基线        ✅ 已完成 (eb5812d)
  M0.2 智能体架构与记忆设计         ✅ 已完成 (d03ac6c)
  M0.3 数据接入与验证闭环           ✅ 已完成 (c3510f2)
  M0.3.1 验证闭环加固修复           ✅ 已完成 (3c7cc7c)
  M0.3.2 工具网关与并发闭环修正      ✅ 已完成 (ec1afcc)
  M0.3.3 Mock场景并发隔离修复        ✅ 已完成 (d0d47e3)
  M0.4 项目骨架与阶段收尾           ✅ 已完成 (当前轮)

MVP 功能阶段 (5轮)
  M1 真实 DeepSeek 接入             ⬜
  M2 真实 Power BI MCP 与数据问答    ⬜
  M3 报表生成闭环                   ⬜
  M4 多轮记忆完善                   ⬜
  M5 React 前端与联调                ⬜

后续阶段 (延后)
  商业化权限与部署                    ⬜
```

---

## M0.3.2 — 工具网关与并发闭环修正

**状态：** ✅ 已完成 | **Commit：** M0.3.2_工具网关与并发闭环修正

### 来源
- M0.3.1 专项审计后剩余的小范围真实性问题
- 重点：ToolGateway 策略真正生效、Trace 真实关联、状态机失败路径、并发安全、模式隔离、Golden Cases 严格化
- 不属于新功能阶段
- 不创建 Tag
- 完成后才能进入 M0.4

### 核心交付物
- ToolGateway 完整策略检查链（read_only/Intent/模式/用户权限）+ 正确异常分类
- TraceRecorder 深度安全返回值 + 真实耗时
- 状态机 PLAN_READY 新增合法失败转换 + 统一 _fail_turn
- MockAgentRuntime 移除共享 scenario 状态 + 并发测试
- Repository (runtime_mode, request_id) 复合键
- MemoryPolicies 只检查 business_satisfied
- QueryResult.result_id / RenderedReport.report_id 唯一 UUID
- Answer source_mode 不一致 → error
- Golden Case extra="forbid" + 五类 Key 强校验 + 幂等真实重放 + 多轮 context 验证
- 205 个测试全部通过 + 11/11 Golden Cases 通过

---

## M0.3.1 — 验证闭环加固修复

**状态：** ✅ 已完成 | **Commit：** `3c7cc7c` M0.3.1_验证闭环加固修复

### 来源
- M0.3 专项代码审计发现 16 项闭环真实性问题
- 目的：修复 Mock 闭环真实性
- 不属于新功能阶段
- 完成后才能进入 M0.4
- 不创建 Tag

### 核心交付物
- Memory 模型重构（RuntimeDataMode 枚举、base_memory_version、移除公共 commit/fail）
- Repository 原子化（asyncio.Lock、Mock/Real 隔离、证据验证）
- ToolGateway 真实接入（三个工具注册、主链路经 Gateway）
- MockTurnService 重构（Scenario Key、提交前填充、失败统一标记）
- ContextBuilder/TraceRecorder/ValidationService 加固
- GoldenCaseRunner 异步重构 + 12 条 Golden Cases
- 191 个测试全部通过 + Golden Cases 11/11 通过

---

## M0.3 — 数据接入与验证闭环

**状态：** ✅ 已完成 | **Commit：** `c3510f2` M0.3_数据接入与验证闭环

### 核心交付物

- M0.2 审计修复（AgentRuntime、PydanticAI API、Fixture、Mock LLM、IntentSpec、记忆规则）
- Power BI MCP 与 OAuth ADR-003
- PowerBIAdapter（Mock + Remote 骨架）
- 核心数据契约（QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec、UserContext）
- Harness ETCLOVG 完整实现（ADR-004）
- ToolGateway、ContextBuilder、TurnController、ValidationService、TraceRecorder
- InMemoryMemoryRepository
- MockAgentRuntime、MockReportRenderer、MockTurnService
- Golden Cases（10 条）+ GoldenCaseRunner
- 166 个测试全部通过

### Tag：否

---

## M0.4 — 项目骨架与阶段收尾

**Commit：** M0.4_项目骨架与阶段收尾

### 允许

- Pydantic Settings
- FastAPI 最小骨架
- `/health`
- 运行模式展示
- Application Service 正式接入
- health 测试
- README 启动验证
- 全量审查
- M0 总验收
- 是否创建 M0 封板 Tag 由 M0.4 Prompt 决定

### 禁止

- 真实 DeepSeek
- 真实 Power BI 生产连接
- React 页面
- Docker
- 多租户
- 正式报表产品
- M1 开发

---

*最后更新：2026-07-31 | M0.4 项目骨架与阶段收尾*
