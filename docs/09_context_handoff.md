# 09 — 跨对话上下文交接

> **这是所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时必须更新本文件，不得只追加已失效的信息。**
> **最后更新：2026-07-31 | M0.2 智能体架构与记忆设计**

---

## 当前项目目标摘要

开发一套供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

核心技术约束：单 Agent（不用 LangGraph）、PydanticAI 框架、DeepSeek LLM、Power BI MCP、固定模板报表、结构化记忆。

## 当前阶段

**M0.2 智能体架构与记忆设计** — 已完成。

下一轮：**M0.3 数据接入与验证闭环**。

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | 待提交 | 2026-07-31 |

## 最新 Commit SHA

待提交（M0.2 完成性 Commit 尚未创建）

## 最近封板 Tag

**暂无封板 Tag。** M0.1、M0.2、M0.3 不创建 Tag。

## M0.1 一致性修复（M0.2 本轮完成）

- ✅ 修复 CHANGELOG、docs/07、docs/09 中的错误 Commit SHA（`fd9e57a` → `eb5812d`）
- ✅ 修复 "待提交"/"待推送" 状态为已完成
- ✅ 统一文档来源优先级（原始 PRD 降级为历史参考）
- ✅ 更新 PROJECT_CHARTER.md、CLAUDE.md、docs/06 中的优先级
- ✅ 修复 M0.3 职责（包含完整 Harness、Golden Cases、Mock 闭环）
- ✅ 修复 M0.4 职责（收敛为 FastAPI 骨架与收尾）
- ✅ 明确真实 Power BI 账号不是 M0.3 硬性前置条件
- ✅ 统一后端目录为 `backend/app` 和 `backend/tests`
- ✅ 修复 pyproject.toml 包发现和测试路径
- ✅ 修复 README Conda 命令
- ✅ 修复 docs/03 记忆提交机制表述
- ✅ 修复 environment.yml（移除未验证的 `-e .`）

## M0.2 完成内容

1. ✅ Agent 框架调研 → 选择 PydanticAI（ADR-001）
2. ✅ 单 Agent 架构边界明确（AgentRuntime Adapter 隔离）
3. ✅ 完整意图体系：四类 Intent + IntentSpec Pydantic 模型
4. ✅ LLM Provider 抽象（base.py）：统一 generate 接口
5. ✅ DeepSeek Provider 骨架（M1 实现真实调用）
6. ✅ 可运行的 Mock LLM（data_question/clarification/unsupported/report_generation/timeout/invalid_structure/missing_fields）
7. ✅ Provider Registry（统一选择，业务层不散落 if/else）
8. ✅ 四层记忆设计 (L1-L4)
9. ✅ 记忆数据契约（StructuredWorkMemory）
10. ✅ pending/committed/failed 三态机制
11. ✅ memory_version 乐观锁
12. ✅ request_id 幂等
13. ✅ Memory Commit 准入（MemoryPolicies.check_commit_eligibility）
14. ✅ Context Assembly 契约
15. ✅ 模型切换、模板切换、重新开始、纠正口径策略
16. ✅ MemoryRepository 抽象接口
17. ✅ ADR-002 记忆系统与存储
18. ✅ 65 个单元测试全部通过
19. ✅ docs/03 实质完成
20. ✅ 全部文档更新

## 选定的 Agent 框架

**PydanticAI 2.21.0**（MIT 许可证）

| 属性 | 值 |
|------|-----|
| 框架 | PydanticAI |
| 版本 | 2.21.0 |
| 安装 | `pydantic-ai>=2.21.0` |
| 隔离方式 | AgentRuntime Adapter（`backend/app/agent/`），核心业务不直接依赖框架 |
| DeepSeek 接入 | OpenAI-compatible Provider（`OpenAIChatModel` + `OpenAIProvider`） |

## LLM Provider 结构

```
backend/app/llm/
├── base.py        # LLMProvider 抽象 + LLMRequest/LLMResponse
├── registry.py    # LLMProviderRegistry
├── mock.py        # MockLLMProvider（可运行，7 种预设场景）
└── deepseek.py    # DeepSeekProvider 骨架（M1 实现）
```

## Mock 场景

| scenario_key | 返回 |
|-------------|------|
| `data_question` | 正常数据问答 IntentSpec |
| `report_generation` | 报表生成 IntentSpec |
| `clarification` | 澄清 IntentSpec |
| `unsupported` | 拒绝 IntentSpec |
| `timeout` | LLMTimeoutError |
| `invalid_structure` | LLMValidationError |
| `missing_fields` | 缺字段（按默认处理） |

## IntentSpec 字段摘要

```
intent, confidence, normalized_question, needs_clarification,
clarification_question, inherited_context, detected_measures,
detected_dimensions, detected_filters, detected_time_range,
requested_template, unsupported_reason
```

## Memory 模型摘要

- **StructuredWorkMemory** — 完整工作记忆 Pydantic 模型（30+ 字段）
- **MemoryStatus** — pending / committed / failed
- **MemoryPolicies** — 提交准入、幂等、版本检查、上下文切换
- **MemoryRepository** — CRUD 抽象接口

## 测试结果

**65/65 通过**（pytest 9.1.1，Python 3.11.15）

| 测试文件 | 测试数 | 结果 |
|---------|--------|------|
| test_intent.py | 16 | ✅ |
| test_llm.py | 15 | ✅ |
| test_memory.py | 28 | ✅ |
| test_agent_framework.py | 6 | ✅ |

## 已验证内容

- ✅ `D:\Conda` 目录存在
- ✅ PBIAgent Conda 环境：Python 3.11.15
- ✅ PydanticAI 2.21.0 可导入
- ✅ pytest 9.1.1 可运行
- ✅ 65 个单元测试全部通过
- ✅ Git 远程地址：https://github.com/Strange-Men/PowerBIAgent.git
- ✅ 当前分支：main
- ✅ 当前无 Tag

## 未验证事项

- 项目负责人 Power BI 账号状态（M0.3 前验证）
- DeepSeek API Key 可用性（M1 前验证）
- PydanticAI 在真实 DeepSeek 调用中的表现（M1 验证）
- Power BI MCP 可用性和连接方式（M0.3 早期验证）

## 当前目录结构

```
PowerBIAgent/
├── PRD.md                              # 原始 PRD（只读，不修改）
├── PROJECT_CHARTER.md                   # 项目北极星
├── README.md
├── CLAUDE.md
├── CHANGELOG.md
├── .gitignore
├── .env.example
├── environment.yml
├── pyproject.toml
├── docs/
│   ├── 00_product_requirements_document.md
│   ├── 01_product_scope_and_frontend_skeleton.md
│   ├── 02_technology_selection_and_system_architecture.md
│   ├── 03_intent_recognition_and_memory_system.md
│   ├── 04_powerbi_mcp_and_api_contracts.md
│   ├── 05_harness_test_and_acceptance.md
│   ├── 06_security_git_and_development_standards.md
│   ├── 07_milestones_status_and_open_questions.md
│   ├── 08_development_roadmap.md
│   ├── 09_context_handoff.md
│   └── adr/
│       ├── README.md
│       ├── ADR-001_agent_framework_selection.md
│       └── ADR-002_memory_system_and_storage.md
├── frontend/
│   └── README.md
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── agent/
│   │   │   └── __init__.py
│   │   ├── intent/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── service.py
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── mock.py
│   │   │   └── deepseek.py
│   │   └── memory/
│   │       ├── __init__.py
│   │       ├── models.py
│   │       ├── repository.py
│   │       └── policies.py
│   └── tests/
│       ├── __init__.py
│       ├── fixtures/
│       │   └── mock_llm_responses.json
│       └── unit/
│           ├── __init__.py
│           ├── test_intent.py
│           ├── test_llm.py
│           ├── test_memory.py
│           └── test_agent_framework.py
└── .git/
```

## 已知风险

- PydanticAI API Breaking Changes（通过 Adapter 隔离缓解）
- Power BI MCP 连接可能受 Microsoft 账号配置影响
- DeepSeek 对 DAX 生成质量不确定

---

## 下一轮唯一允许范围

**下一轮固定 Commit：**

```
M0.3_数据接入与验证闭环
```

**下一轮允许：**
- Power BI MCP 与 OAuth 风险调研
- PowerBIAdapter 接口定义
- MockPowerBIAdapter 实现
- Remote MCP Adapter 骨架
- API 数据契约：QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec
- 轻量 ETCLOVG Harness
- ToolGateway、ContextBuilder、TurnController
- ValidationService、TraceRecorder
- GoldenCaseRunner、Golden Cases
- Mock 问答、报表和失败保护链路
- MemoryRepository 内存实现

**下一轮禁止：**
- 真实 DeepSeek 正式接入（M1）
- 正式 Power BI 生产连接
- FastAPI main.py、`/health`（M0.4）
- React 页面（M5）
- Docker
- 多租户
- M0.4 收尾内容
- 创建 Tag

**说明：** 真实 Power BI 账号和远程 MCP 连接不是 M0.3 的硬性前置条件。缺少真实账号时，M0.3 仍应通过 Mock 和接口骨架完成。

---

## 下一轮必须阅读的文件

1. `PROJECT_CHARTER.md`
2. `CLAUDE.md`
3. `docs/00_product_requirements_document.md`
4. `docs/02_technology_selection_and_system_architecture.md`
5. `docs/03_intent_recognition_and_memory_system.md`
6. `docs/04_powerbi_mcp_and_api_contracts.md`
7. `docs/05_harness_test_and_acceptance.md`
8. `docs/07_milestones_status_and_open_questions.md`
9. `docs/08_development_roadmap.md`
10. `docs/09_context_handoff.md`（本文件）
11. `docs/adr/ADR-001_agent_framework_selection.md`
12. `docs/adr/ADR-002_memory_system_and_storage.md`
13. `CHANGELOG.md`

## 下一轮进入门槛

下一轮开始前必须检查：
1. `D:\Conda` 存在且可访问
2. `PBIAgent` Conda 环境存在，Python 版本为 3.11
3. 最新 Commit 为 `M0.2_智能体架构与记忆设计`
4. Git 工作区干净
5. 当前不存在封板 Tag（不存在是正常状态）
6. `.env.example` 存在

---

*最后更新：2026-07-31 | M0.2 智能体架构与记忆设计*
