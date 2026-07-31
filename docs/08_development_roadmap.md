# 08 — 开发路线

> **状态：** M1.0 进行中
> **更新频率：** 每轮结束时更新完成状态

---

## 路线总览

```
M0 开发准备 (7轮)
  M0.1 仓库初始化与文档基线        ✅ 已完成 (eb5812d)
  M0.2 智能体架构与记忆设计         ✅ 已完成 (d03ac6c)
  M0.3 数据接入与验证闭环           ✅ 已完成 (c3510f2)
  M0.3.1 验证闭环加固修复           ✅ 已完成 (3c7cc7c)
  M0.3.2 工具网关与并发闭环修正      ✅ 已完成 (ec1afcc)
  M0.3.3 Mock场景并发隔离修复        ✅ 已完成 (d0d47e3)
  M0.4 项目骨架与阶段收尾           ✅ 已完成 (d5c1634)
  M0.4.1 API骨架真实性修复          ✅ 已完成 (1f967b0)

M1 真实 DeepSeek 接入 (6轮)
  M1.0 M0遗留收口与M1路线固化       🔄 进行中
  M1.1 DeepSeek Provider基础接入    ⬜
  M1.2 真实意图识别                 ⬜
  M1.3 真实QueryPlan与DAX生成       ⬜
  M1.4 真实Answer与ReportSpec生成   ⬜
  M1.5 全链路验收与封板              ⬜

MVP 功能阶段 (后续)
  M2 真实 Power BI MCP 与数据问答    ⬜
  M3 报表生成闭环                   ⬜
  M4 多轮记忆完善                   ⬜
  M5 React 前端与联调                ⬜

后续阶段 (延后)
  商业化权限与部署                    ⬜
```

---

## M1 轮次详细路线

> **重要：M1 必须按照 M1.0 → M1.1 → M1.2 → M1.3 → M1.4 → M1.5 顺序执行。**
> 当前轮未验收不得进入下一轮。不允许跨轮提前实现功能。
> 调整小轮顺序必须由用户明确批准，调整前必须先更新本文件。
> **本文件是小轮路线唯一权威来源。** `docs/09_context_handoff.md` 只负责记录实时进度，不重新定义路线。

---

### M1.0｜M0遗留收口与M1路线固化

**状态：** 🔄 进行中

**完成内容：**
- clarification/unsupported 保留 conversation_id
- 固定 request_id 幂等重放规则与实现
- 实际报表模板同步写入 Memory（默认 sales_weekly）
- 更新版本号为 M1.0 和开发依赖安装说明
- 固化 M1.0—M1.5 开发顺序

**本轮不接入 DeepSeek。**

---

### M1.1｜DeepSeek Provider基础接入

**状态：** ⬜ 未开始

**完成内容：**
- 从 Settings 读取 API Key、Base URL、模型名
- 实现 DeepSeekLLMProvider
- 超时、鉴权、限流、网络和服务错误分类
- 最小真实连通测试
- Mock 模式保持完整可用

**本轮不接入真实 Intent 业务流程。**

---

### M1.2｜真实意图识别

**状态：** ⬜ 未开始

**完成内容：**
- DeepSeek 输出严格 IntentSpec
- 支持 data_question / report_generation / clarification / unsupported
- JSON 或结构化格式错误自动修复一次
- 真实模式禁止调用 MockScenarioResolver

---

### M1.3｜真实QueryPlan与DAX生成

**状态：** ⬜ 未开始

**完成内容：**
- QueryPlan 结构化生成
- 根据 Semantic Model Schema 生成 DAX
- DAX 只读安全验证
- 格式失败、非法字段和超限兜底
- Power BI 查询仍使用 Mock Adapter

---

### M1.4｜真实Answer与ReportSpec生成

**状态：** ⬜ 未开始

**完成内容：**
- 根据 Mock 查询结果生成真实自然语言 Answer
- 生成结构化 ReportSpec
- Report Renderer 仍使用现有 Mock 实现
- 校验回答、证据、模型和 source_mode 一致性

---

### M1.5｜全链路验收与封板

**状态：** ⬜ 未开始

**完成内容：**
- Mock 和 DeepSeek 模式切换
- API 真实调用验证
- DeepSeek 失败不得静默回退 Mock
- 成本、Token、耗时和 Trace 记录
- Golden Cases 继续全部通过
- 新增真实 LLM 基线案例
- 文档收尾
- M1 封板 Commit 和 Tag

---

## M0 历史轮次

### M0.4.1 — API骨架真实性修复

**状态：** ✅ 已完成 | **Commit：** `1f967b0` M0.4.1_API骨架真实性修复

- 依赖可复现（fastapi/uvicorn/pydantic-settings/httpx 版本锁定）
- 公开 API 真实意图流（MockScenarioResolver）
- Answer/Report 真实返回
- Health 真实性（ready/reasons/503）
- app.state 与 lifespan

### M0.4 — 项目骨架与阶段收尾

**状态：** ✅ 已完成 | **Commit：** `d5c1634` M0.4_项目骨架与阶段收尾

- 请求级并发上下文收口
- FastAPI 最小骨架（Settings、Health、Chat 接口）
- M0 全量验收（265 测试 + Golden Cases）

### M0.3.3 — Mock场景并发隔离修复

**状态：** ✅ 已完成 | **Commit：** `d0d47e3` M0.3.3_Mock场景并发隔离修复

- 删除 MockLLMProvider._active_scenario 共享状态
- Scenario Key 仅通过 context 局部传递

### M0.3.2 — 工具网关与并发闭环修正

**状态：** ✅ 已完成 | **Commit：** `ec1afcc` M0.3.2_工具网关与并发闭环修正

- ToolGateway 完整策略检查链
- TraceRecorder 深度安全返回值 + 真实耗时
- Repository (runtime_mode, request_id) 复合键
- 205 个测试全部通过 + 11/11 Golden Cases 通过

### M0.3.1 — 验证闭环加固修复

**状态：** ✅ 已完成 | **Commit：** `3c7cc7c` M0.3.1_验证闭环加固修复

- Memory 模型重构（RuntimeDataMode 枚举）
- Repository 原子化、ToolGateway 真实接入
- MockTurnService 重构、GoldenCaseRunner 异步重构
- 191 个测试全部通过 + Golden Cases 11/11 通过

### M0.3 — 数据接入与验证闭环

**状态：** ✅ 已完成 | **Commit：** `c3510f2` M0.3_数据接入与验证闭环

- Power BI MCP ADR-003、PowerBIAdapter、核心数据契约
- Harness ETCLOVG 完整实现（ADR-004）
- Golden Cases（10 条）、166 个测试全部通过

### M0.2 — 智能体架构与记忆设计

**状态：** ✅ 已完成 | **Commit：** `d03ac6c` M0.2_智能体架构与记忆设计

### M0.1 — 仓库初始化与文档基线

**状态：** ✅ 已完成 | **Commit：** `eb5812d` M0.1_仓库初始化与文档基线

---

*最后更新：2026-07-31 | M1.0 M0遗留收口与M1路线固化*
