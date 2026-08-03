# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-03 | M1.4 真实Answer与ReportSpec生成**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

前端最终为带左侧栏的 GPT 式极简对话网页（React + Vite，M5 开发）。

## 当前阶段

**M1.4 真实 Answer 与 ReportSpec 生成** — ✅ 已完成。

## 上一轮

**M1.3.2** — 前端视觉与结构化回答契约固化（Commit `db0a7e8`）

## 下一轮

**M1.5 全链路验收与封板**

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
| M1.0.1 | 幂等并发与文档收尾修复 | `c223d7b` | 2026-07-31 |
| M1.0.2 | 密钥与仓库安全规则固化 | `5726959` | 2026-07-31 |
| M1.1 | DeepSeek Provider基础接入 | `073a819` | 2026-08-03 |
| M1.2 | 真实意图识别 | `53cf43e` | 2026-08-03 |
| M1.3 | 真实QueryPlan与DAX生成 | `441ca45` / `c0e782b` | 2026-08-03 |
| M1.3.1 | QueryPlan与DAX验证修复 | `6647760` | 2026-08-03 |
| M1.3.2 | 前端视觉与结构化回答契约固化 | 本轮提交 | 2026-08-03 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## M1.4 交付内容

### Answer 生成
- `DeepSeekAnswerService`：安全上下文、集中式 Prompt、最多一次修复
- Evidence 四大字段强制绑定（result_id/semantic_model_key/row_count/source_mode）
- Metrics 可追溯验证
- Truncated/input_truncated 强制披露

### ReportSpec 生成
- `DeepSeekReportSpecService`：安全上下文、集中式 Prompt
- KPI/Chart/Table 真实性验证
- Table 整行投影验证（防跨行拼接 + 重复行限制 + 类型严格比较）
- Mock Renderer 兼容

### 真实 Smoke
- 双案例（data_question + report_generation）均通过
- Answer repairs=1（一次修复后严格验证通过）
- ReportSpec repairs=0
- 使用真实 DeepSeek + Mock QueryResult，未调用真实 Power BI

### 测试结果
- pytest：858 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（133 文件）

### 运行边界
- Settings.version=M1.4
- QueryResult 仍为 Mock
- Renderer 仍为 Mock
- DeepSeek Chat 仍 503
- 真实 Power BI 属 M2

## M1.3.2 交付内容

### 视觉资产归档

- 两张前端参考图归档至 `docs/assets/frontend/`：
  - `整体01.png` — 已有对话与组合回答态
  - `整体02.png` — 新聊天欢迎态与菜单展开态
- 图片为未来 M5 React 前端开发的视觉参考
- 当前不根据图片创建 React 页面

### 前端最终产品方向

- 最终为带左侧栏的 GPT 式极简对话网页（React + Vite，M5 开发）
- 全局视觉：纯白/极浅灰为主，黑色/深灰正文，克制蓝色图表，大面积留白
- 左侧栏（约15%宽）：标识、新聊天、搜索聊天、项目、最近报表、最近对话、用户信息。左侧栏 React UI 整体属 M5；M3/M4 只准备对应后端能力（报表资源、会话持久化、搜索）
- 主对话区：新聊天欢迎态、已有对话态（用户消息+AI组合回答+底部输入器）
- 输入器：胶囊形容器、"+"按钮（数据模型+报表模板两分组）、文本输入、模型菜单、发送按钮
- 模型菜单：当前仅 DeepSeek 为正式用户模型，Mock 仅测试，GPT-5.6 未接入

### 结构化组合回答契约

- 目标：一条 AI 回答由多个内容块组成（text、metrics、table、chart、report_attachment）
- 表格和图表数据必须来自 QueryResult，LLM 不得虚构
- 图表使用结构化字段（bar/line/pie/scatter），禁止 HTML/JS/外部脚本
- 报表附件引用由后端生成，禁止 LLM 生成任意外部 URL
- 当前不创建新的 Python 消息 Envelope 或 API 代码

### 关键边界

- **当前正式用户模型只有 DeepSeek**；Mock 仅测试；GPT-5.6 未接入
- **当前 QueryResult 仍为 Mock**；真实 Power BI 属于 M2
- **M3 只实现后端能力**：报表渲染、report_id、查看/下载资源、最近报表所需后端数据
- **M4 只实现后端能力**：会话历史、搜索、持久化、最近对话所需后端数据
- **最近报表列表、最近对话列表、搜索聊天界面和完整左侧栏统一在 M5 React 前端实现**
- **M3、M4 不开发 React 左侧栏或任何前端 UI**
- **前端正式开发延后至 M5**
- **M1.4 继续使用现有 AnswerSpec、QueryResult 和 ReportSpec**
- **完整组合消息编排在 M1.5/M5 继续确定**

### 文档修改

- `CHANGELOG.md` — 新增 M1.3.2 记录
- `docs/00` — 补充组合回答和左侧栏布局
- `docs/01` — 替换为带左侧栏的完整页面骨架
- `docs/04` — 核对 API 路径，补充契约职责和组合回答目标
- `docs/05` — 同步 706 passed 基线 + 未来验收项
- `docs/07` — 重写里程碑状态 + 待确认项
- `docs/08` — 插入 M1.3.2 + 阶段前固化内容
- `docs/09` — 本文件 — 覆盖更新
- `frontend/README.md` — 更新前端方向
- `docs/10` — 新增：正式视觉与交互规范
- `docs/11` — 新增：结构化组合回答契约

### 测试结果

- pytest：706 passed（无变化，本轮无代码修改）
- Golden Cases：11 passed，1 skipped（无变化）
- 安全扫描：PASS（无变化）

### M1.3.2 允许和禁止范围

**允许：**
- 归档两张前端参考图
- 创建/修改文档（CHANGELOG + 9 docs + frontend/README）
- 创建视觉规范与组合回答契约文档

**禁止：**
- 修改后端业务代码（Python）
- 修改前端业务代码
- 创建 React 项目 / package.json / src / CSS / 组件
- 创建新 API / 数据库 / 会话持久化 / 报表下载
- 修改 AnswerSpec / ReportSpec / RenderedReport
- 修改 Settings.version
- 开发 M1.4 功能
- 创建 Tag
- 声称 GPT-5.6 已接入、Mock 是正式模型、前端已完成

## 未完成或待观察事项

- 跨进程持久化和分布式锁延后处理
- 项目负责人 Power BI 账号状态（M2 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）
- 完整 Chat 仍未开放（待 M1.5）
- Answer/ReportSpec 真实生成已完成 → 仍使用 Mock QueryResult
- 公司真实 Power BI 语义模型（M2 前确认）
- 可用报表模板（M3 前确认）
- 报表资源保存位置（M3 前确认）
- 会话和报表持久化方案（M4 前确认）
- 前端是否展示其他模型（M5 前确认）

---

*最后更新：2026-08-03 | M1.4 真实Answer与ReportSpec生成*
