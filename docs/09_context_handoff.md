# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M1.0.2 密钥与仓库安全规则固化**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.0.2 密钥与仓库安全规则固化** — ✅ 已完成。

## 当前完成轮次

**M1.0.2** — 密钥与仓库安全规则固化

## 下一轮

**M1.1 DeepSeek Provider基础接入**

M1.2—M1.5：未开始

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | `3c7cc7c` | 2026-07-31 |
| M0.3.2 | 工具网关与并发闭环修正 | `ec1afcc` | 2026-07-31 |
| M0.3.3 | Mock场景并发隔离修复 | `d0d47e3` | 2026-07-31 |
| M0.4 | 项目骨架与阶段收尾 | `d5c1634` | 2026-07-31 |
| M0.4.1 | API骨架真实性修复 | `1f967b0` | 2026-07-31 |
| M1.0 | M0遗留收口与M1路线固化 | `9247322` | 2026-07-31 |
| M1.0.1 | 幂等并发与文档收尾修复 | 最终 SHA 以 git log -1 为准 | 2026-07-31 |
| M1.0.2 | 密钥与仓库安全规则固化 | 最终 SHA 以 git log -1 为准 | 2026-07-31 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 — 保留不动 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 — 保留不动 |

## M1.0.2 交付内容

### 安全规则固化

**CLAUDE.md：**
- 新增「Secret 与 API Key 绝对规则」章节（共 6 条子规则）
- Secret 永不进入仓库、Claude 不得读取 .env、API Key 仅后端使用
- 前端禁止持有 Provider Secret、日志与测试禁止泄漏
- 提交前安全检查：禁止 `git add .`/`git add -A`，必须使用文件白名单
- Commit 规则新增文件白名单和安全检查步骤

**docs/06 安全规范：**
- 新增 1.1—1.6 节：Secret 文件规则、Claude 禁止读取 .env、后端 Key 规则、前端禁止 Secret、日志安全、API Key 填写规则
- 提交前检查清单更新为 10 项（新增文件白名单和安全扫描步骤）

**.gitignore：**
- 新增 `.env.backup`、`.env.bak`、`.env.old`、`credentials/`、`private_credentials/`
- 新增 `*.har`、`http_dumps/`、`network_capture/`、`debug_responses/`、`smoke_outputs/`、`secret_scan_output/`

**安全检查脚本：**
- `scripts/check_repository_safety.py` — 检查：禁止跟踪文件名、前端 Secret、明显真实 Secret
- 排除测试和脚本目录中的安全检测样本
- 退出码：安全=0，发现风险=非0

**安全测试：**
- `backend/tests/unit/test_repository_safety.py` — 26 个测试全部通过
- 覆盖：禁止文件名、空值/占位值允许、疑似真实值拒绝、前端 Secret 拒绝、输出不含 Secret 原文、当前仓库通过

**.env 状态：**
- `.env.example` 继续受 Git 跟踪，已清理为安全默认状态（所有 Key 为空值，`LLM_MODE=mock`）
- 本地 `.env` 已创建（从 `.env.example` 复制），已被 `.gitignore` 忽略且未被 Git 跟踪
- Claude 本轮未读取 `.env` 内容
- `.env` 中所有 Key 为空，待 M1.1 前由用户本人手动填写真实 DeepSeek API Key

**README：**
- 新增 `.env` 创建和安全说明
- 新增仓库安全检查命令

## M1.1 开始前准备

- M1.1 开始前由用户本人填写本地 `.env` 中的 `DEEPSEEK_API_KEY`
- M1.1 不得读取或回显 Key
- M1.1 只实现 DeepSeekLLMProvider 基础接入，不涉及真实业务流程

## 测试结果

**pytest：** 待最终全量验证
**Golden Cases：** 待最终验证
**安全扫描：** `scripts/check_repository_safety.py` 通过

## 未完成或待观察事项

- 跨进程持久化和分布式锁延后处理
- 项目负责人 Power BI 账号状态（M2 前确认）
- DeepSeek API Key 可用性（M1.1 前用户本人填写）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）

## M1.1 允许范围

**下一轮：** M1.1 DeepSeek Provider基础接入

**允许：**
- 从 Settings 读取 API Key、Base URL、模型名
- 实现 DeepSeekLLMProvider
- 超时、鉴权、限流、网络和服务错误分类
- 最小真实连通测试
- Mock 模式保持完整可用

**M1.1 禁止：**
- 读取或回显真实 API Key
- 真实 Intent 业务流程
- 真实 QueryPlan / DAX / Answer / ReportSpec 生成
- 真实 Power BI 连接
- React 前端 / SSE / Docker / Redis / LangGraph / 多 Agent
- 修改历史 Tag

---

*最后更新：2026-07-31 | M1.0.2 密钥与仓库安全规则固化*
