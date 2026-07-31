# CHANGELOG

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

**Commit SHA：** `fd9e57a`
**本轮 Tag：** 无（本轮不创建 Tag）

---

## 图例

- `[Mx.y]` — M0 开发准备轮次
- `[Mx]` — MVP 功能轮次
