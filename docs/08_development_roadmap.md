# 08 — 开发路线

> **状态：** M0.1 已固化完整路线
> **更新频率：** 每轮结束时更新完成状态

---

## 路线总览

```
M0 开发准备 (4轮)
  M0.1 仓库初始化与文档基线        ✅ 已完成
  M0.2 智能体架构与记忆设计         ⏳ 下一轮
  M0.3 数据接入与验证闭环           ⬜
  M0.4 项目骨架与阶段收尾           ⬜

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

## M0.1 — 仓库初始化与文档基线

**状态：** ✅ 已完成 | **Commit：** M0.1_仓库初始化与文档基线

### 目标

建立仓库、需求、文档、开发环境和长期规则基线。

### 前置条件

- 无

### 核心交付物

- 原始 PRD 保留
- 正式 PRD
- PROJECT_CHARTER.md
- CLAUDE.md（冷启动协议、Commit/Tag 规则）
- 完整 docs 文档体系（00-09）
- .gitignore、.env.example、environment.yml、pyproject.toml
- README.md、CHANGELOG.md
- Git 仓库初始化
- PBIAgent Conda 环境（Python 3.11）

### 不允许提前做

- 选择 Agent 框架
- 编写业务代码
- 创建 React 项目或 FastAPI 应用
- 实现任何 M0.2-M0.4 的代码

### 完成标准

- 30 项验收标准全部通过
- Commit 已推送
- 工作区干净
- 无 Tag 创建

### Tag：否

---

## M0.2 — 智能体架构与记忆设计

**状态：** ✅ 已完成 | **Commit：** M0.2_智能体架构与记忆设计

### 目标

确定 Agent 框架、LLM Provider 接口、意图识别方案和记忆系统设计。

### 前置条件

- M0.1 完成

### 核心交付物

- Agent 框架 ADR
- LLM Provider 接口设计
- DeepSeek 接入骨架
- Mock LLM 实现
- 意图识别方案（IntentSpec 完整定义）
- 记忆系统设计文档和接口

### 不允许提前做

- Power BI MCP 实现
- Harness 完整闭环
- FastAPI 正式骨架
- React 页面
- M0.3 和 M0.4 内容

### 完成标准

- ✅ ADR-001 Agent 框架选择 (PydanticAI)
- ✅ ADR-002 记忆系统与存储
- ✅ IntentSpec 完整 Pydantic 模型
- ✅ LLM Provider 抽象 + DeepSeek 骨架 + Mock LLM
- ✅ 四层记忆设计 + 三态机制 + 提交准入
- ✅ 65 个单元测试全部通过

### Tag：否

---

## M0.3 — 数据接入与验证闭环

**状态：** ⬜ 计划中 | **Commit：** M0.3_数据接入与验证闭环

### 目标

验证 Power BI MCP 连接可行性，建立从意图识别到数据查询的完整 Mock 验证闭环，实现轻量 Harness。

### 前置条件

- M0.2 完成

### 核心交付物

- Power BI MCP 与 OAuth 风险调研
- PowerBIAdapter 接口定义
- MockPowerBIAdapter 实现
- Remote MCP Adapter 骨架
- API 数据契约：QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec
- 轻量 ETCLOVG Harness
- ToolGateway、ContextBuilder、TurnController
- ValidationService、TraceRecorder
- GoldenCaseRunner 和 Golden Cases
- Mock 数据问答链路
- Mock 报表链路
- 失败不提交 Memory 的完整保护

### 允许提前做

- Power BI MCP 接口调研和文档
- Mock 适配器完整实现
- 所有数据契约的 Pydantic 模型

### 不允许提前做

- M0.4 的 FastAPI 骨架和 `/health`
- M1 真实 DeepSeek 调用
- React 前端项目
- 真实 Power BI 账号连接（如账号不可用，仍应通过 Mock 完成）

### 完成标准

- Mock LLM + Mock Power BI MCP 数据流可跑通
- Golden Cases 可重复执行
- 失败轮次不污染 committed memory
- 所有数据契约已定义并文档化

### Tag：否

### 说明

真实 Power BI 账号和远程 MCP 连接不是 M0.3 的硬性前置条件。缺少真实账号时，M0.3 仍应通过 Mock 和接口骨架完成。

---

## M0.4 — 项目骨架与阶段收尾

**状态：** ⬜ 计划中 | **Commit：** M0.4_项目骨架与阶段收尾

### 目标

搭建 FastAPI 最小骨架，完成全量测试和 M0 总验收。

### 前置条件

- M0.3 完成

### 核心交付物

- FastAPI 最小骨架
- `/health` 端点
- 运行模式展示（Mock/真实）
- health 测试
- 全量测试运行
- README 启动验证
- 文档与代码一致性检查
- CHANGELOG 更新
- M0 总验收
- 是否创建 M0 封板 Tag 由 M0.4 Prompt 决定

### 不允许提前做

- M1 真实 DeepSeek 调用
- React 前端项目
- 报表生成（如 M3 未完成）

### 完成标准

- `/health` 返回 200
- 全量测试通过
- 文档与代码一致
- M0 验收标准全部满足

### Tag：由 M0.4 Prompt 决定是否创建 M0 封板 Tag

---

## M1 — 真实 DeepSeek 接入

### 目标

接入真实 DeepSeek LLM，替代 Mock LLM 完成基本的自然语言理解。

### 前置条件

- M0 全部完成
- DeepSeek API Key 可用

### 核心交付物

- DeepSeek Provider 实现
- 真实意图识别验证
- Prompt 模板

### 完成标准

- DeepSeek 意图识别准确率达到可接受水平

### Tag：否（MVP 未完成）

---

## M2 — 真实 Power BI MCP 与数据问答

### 目标

连接真实 Power BI MCP，实现自然语言到 DAX 到数据答案的完整链路。

### 前置条件

- M1 完成
- Power BI 语义模型可用

### 核心交付物

- Power BI MCP 真实连接
- DAX 生成和校验
- 数据问答完整闭环

### 完成标准

- 自然语言问题返回正确的 Power BI 数据

### Tag：否

---

## M3 — 报表生成闭环

### 目标

实现 ReportSpec 生成、固定模板渲染和 HTML 输出。

### 前置条件

- M2 完成

### 核心交付物

- ReportSpec Schema
- 固定模板（至少 2 个）
- HTML 渲染管线
- 报表预览和下载

### 完成标准

- 可使用固定模板生成可读的 HTML 报表

### Tag：否

---

## M4 — 多轮记忆完善

### 目标

完善会话记忆系统，支持流畅的多轮追问。

### 前置条件

- M3 完成

### 核心交付物

- 记忆合并逻辑
- 模型切换上下文清理
- 多轮对话测试

### 完成标准

- 5+ 轮连续追问场景通过测试

### Tag：否

---

## M5 — React 前端与联调

### 目标

完成极简 React 对话页面，实现前后端联调。

### 前置条件

- M4 完成

### 核心交付物

- React + Vite 项目
- 完整对话页面
- 前后端联调通过
- 报表预览和下载

### 完成标准

- 10 项 MVP 验收标准全部通过

### Tag：创建 MVP 封板 Tag

---

## 后续阶段（延后）

当 MVP 验证成功后：

- Microsoft 用户登录
- Power BI 用户权限和 RLS
- 多租户隔离
- 更多语义模型和报表模板
- 报表分享和定时发送
- Docker 容器化部署
- 更完整的 Harness 和评测平台

---

## Tag 创建规则总结

| 阶段 | Tag | 条件 |
|------|-----|------|
| M0.1 | 不创建 | — |
| M0.2 | 不创建 | — |
| M0.3 | 不创建 | — |
| M0.4 | 待定 | 由 M0.4 Prompt 决定 |
| M1-M4 | 不创建 | MVP 未完成 |
| M5 | 创建 MVP 封板 Tag | MVP 验收通过 |
| 后续 | 按需创建 | 用户确认 |

---

*创建日期：2026-07-31 | M0.1 仓库初始化与文档基线*
