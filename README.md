# PowerBIAgent — Power BI 数据分析 Agent MVP

## 项目简介

PowerBIAgent 是供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。

核心链路：用户自然语言提问 → React 极简对话页面 → FastAPI 后端 → 单 Agent 意图识别 → DeepSeek → Power BI MCP → Power BI 语义模型 → 数据问答或固定模板静态 HTML 报表。

## 当前状态

**M0.1 仓库初始化与文档基线** — 仓库、需求、文档、开发环境和长期规则基线已建立。

## 开发环境准备

### Conda 环境

本机 Conda 安装目录：`D:\Conda`

#### 检查 Conda

```powershell
D:\Conda\Scripts\conda.exe --version
```

#### 创建 PBIAgent 环境

```powershell
D:\Conda\Scripts\conda.exe create -n PBIAgent python=3.11 -y
```

#### 激活 PBIAgent 环境

```powershell
D:\Conda\Scripts\conda.exe activate PBIAgent
```

#### 检查 Python 版本

```powershell
D:\Conda\envs\PBIAgent\python.exe --version
# 预期输出: Python 3.11.x
```

#### 安装项目依赖

当前 M0.1 阶段尚未定义具体 Python 依赖。后续轮次将逐步填充 `pyproject.toml` 和 `environment.yml`。

```powershell
# 后续阶段使用:
pip install -e .
# 或:
conda env update -f environment.yml
```

### 注意事项

- 当前 M0.1 尚未提供正式服务启动入口
- 不要求在 base 环境安装项目依赖
- 所有项目依赖仅安装到 `PBIAgent` 环境
- 不在业务代码中硬编码 `D:\Conda` 或环境绝对路径

## 技术栈

| 层级 | 技术 | 状态 |
|------|------|------|
| 前端 | React + Vite | 骨架已确认，开发延后 |
| 后端 | FastAPI | 已选定，后续实现 |
| Agent | 成熟框架单 Agent | M0.2 确定框架 |
| LLM | DeepSeek + Mock LLM | M0.2 接入 |
| 数据 | Power BI MCP | M0.3 接入 |
| 记忆 | 结构化工作记忆 | M0.2 设计 |
| 报表 | 固定模板 HTML | M3 实现 |
| Harness | MVP 轻量控制面 | M0.3/M0.4 实现 |

## 文档导航

| 文档 | 说明 |
|------|------|
| `PROJECT_CHARTER.md` | 项目北极星，不可静默修改的核心约束 |
| `CLAUDE.md` | 开发协议、Commit/Tag 规则、冷启动协议 |
| `docs/00_product_requirements_document.md` | 正式 PRD |
| `docs/08_development_roadmap.md` | 完整开发路线 |
| `docs/09_context_handoff.md` | 最新交接入口 |
| `docs/adr/` | 架构决策记录 |

## 许可证

专有软件，公司内部使用。

---

*最后更新：2026-07-31*
