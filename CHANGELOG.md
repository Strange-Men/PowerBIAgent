# CHANGELOG

## [M0.2] — 2026-07-31

### 智能体架构与记忆设计

**新增：**

**Agent 框架：**
- ADR-001：Agent 框架选择 — PydanticAI 2.21.0
- AgentRuntime Adapter 骨架（`backend/app/agent/`），隔离框架依赖

**意图识别：**
- IntentType 四类意图枚举：data_question、report_generation、clarification、unsupported
- IntentSpec 完整 Pydantic 模型（12 个字段）
- IntentService 抽象接口
- unsupported 意图（非法/越权要求），禁止进入后续流程

**LLM Provider：**
- LLMProvider 抽象基类（支持意图识别、QueryPlan、DAX、AnswerSpec、ReportSpec）
- LLMProviderRegistry：统一 Provider 选择，业务层不散落 if/else
- DeepSeekProvider 骨架（API Key、Base URL、Model、超时、重试），M1 实现真实调用
- MockLLMProvider 可运行：7 种预设场景（data_question/report_generation/clarification/unsupported/timeout/invalid_structure/missing_fields）

**记忆系统：**
- ADR-002：记忆系统与存储方案
- 四层记忆设计：原始对话、结构化工作记忆、滚动摘要、查询产物
- StructuredWorkMemory 完整 Pydantic 模型（30+ 字段）
- 三态机制：pending、committed、failed
- 记忆提交准入条件（MemoryPolicies.check_commit_eligibility）
- request_id 幂等 + memory_version 乐观锁
- 上下文切换策略：模型切换、模板切换、重新开始、纠正口径
- Context Assembly 契约（允许/禁止的上下文类型）
- MemoryRepository 抽象接口

**测试：**
- 65 个单元测试全部通过
- 覆盖：IntentSpec 合法/非法、Mock LLM 全部场景、Provider Registry、Memory 状态/版本/幂等/准入/切换/Context Assembly
- PydanticAI 框架 Smoke Test

**M0.1 一致性修复 (M0.2 本轮完成)：**
- 修复 CHANGELOG、docs/07、docs/09 中的错误 Commit SHA（`fd9e57a` → `eb5812d`）
- 修复 "待提交"/"待推送" 状态为已完成
- 统一文档来源优先级（原始 PRD 降级为历史参考，正式 PRD 为需求基线）
- 更新 PROJECT_CHARTER.md、CLAUDE.md、docs/06 中的文档优先级
- 修复 M0.3 职责（包含完整 Harness、Golden Cases、Mock 闭环）
- 修复 M0.4 职责（收敛为 FastAPI 骨架与收尾）
- 明确真实 Power BI 账号不是 M0.3 硬性前置条件
- 统一后端目录为 `backend/app` 和 `backend/tests`
- 修复 pyproject.toml 包发现和测试路径
- 修复 README Conda 命令（标注未验证命令）
- 修复 docs/03 记忆提交机制表述（每轮结束提交 → only-committed）
- 修复 environment.yml（移除未验证的 `-e .`）

**已安装依赖：**
- pydantic-ai 2.21.0
- pydantic 2.13.4
- pydantic-ai-slim 2.21.0
- pytest 9.1.1
- pytest-asyncio 1.4.0

**Commit SHA：** 待提交
**Push 状态：** 待推送
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M0.1] — 2026-07-31

### 仓库初始化与文档基线

**新增：**
- 识别并保留原始 PRD（`PRD.md`）
- 创建 `PROJECT_CHARTER.md` — 项目北极星文件
- 创建 `CLAUDE.md` — 开发协议、冷启动协议、Commit/Tag 规则
- 创建 `README.md` — 项目说明和环境准备指南
- 创建 `CHANGELOG.md` — 本文件
- 创建 `.gitignore` — 覆盖敏感文件和本地产物
- 创建 `.env.example` — 环境配置模板
- 创建 `environment.yml` — Conda 环境配置（PBIAgent, Python 3.11）
- 创建 `pyproject.toml` — Python 项目配置
- 创建 `docs/00_product_requirements_document.md` — 正式 PRD
- 创建 `docs/01_product_scope_and_frontend_skeleton.md` — 产品范围与前端骨架
- 创建 `docs/02_technology_selection_and_system_architecture.md` — 技术选型骨架
- 创建 `docs/03_intent_recognition_and_memory_system.md` — 意图识别与记忆骨架
- 创建 `docs/04_powerbi_mcp_and_api_contracts.md` — Power BI MCP 骨架
- 创建 `docs/05_harness_test_and_acceptance.md` — Harness 骨架
- 创建 `docs/06_security_git_and_development_standards.md` — 安全与开发规范
- 创建 `docs/07_milestones_status_and_open_questions.md` — 里程碑状态
- 创建 `docs/08_development_roadmap.md` — 开发路线
- 创建 `docs/09_context_handoff.md` — 跨对话交接
- 创建 `docs/adr/README.md` — ADR 目录说明
- 创建 `frontend/README.md` — 前端占位说明
- 初始化 Git 仓库，配置远程 `origin`
- 创建 `PBIAgent` Conda 环境（Python 3.11.15）

**Conda 环境：**
- Conda 版本：26.5.3
- Conda 路径：`D:\Conda\Scripts\conda.exe`
- 环境名称：`PBIAgent`
- 环境路径：`D:\Conda\envs\PBIAgent`
- Python 版本：3.11.15

**Commit SHA：** `eb5812d`（完整：`eb5812dfa9a76bcbb8505c31e1b8f24b67afadf0`）
**Push 状态：** ✅ 已推送至 origin/main
**本轮 Tag：** 无（本轮不创建 Tag）

---

## 图例

- `[Mx.y]` — M0 开发准备轮次
- `[Mx]` — MVP 功能轮次
