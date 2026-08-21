# Frontend — PowerBIAgent 前端

## 状态

**M5.0 — 前端设计与契约固化（已启动）。M5.0 只修改 Markdown 文档，不创建 React 项目。**

## 技术栈

- React 18+
- Vite 构建工具
- 轻量状态管理

## 页面结构

带左侧栏的 GPT 式极简白色对话网页。

### 整体布局

- **左侧栏：** PowerBIAgent 标识、折叠/展开、新聊天、搜索聊天、项目、最近报表、最近对话、底部账户展示
- **主对话区：** 新聊天欢迎态（页面居中留白、欢迎图标、主标题"今天想分析什么数据？"、副标题）、已有对话态（用户消息浅灰气泡、AI 组合回答、底部 Composer）

### 左侧栏能力边界

| 条目 | 交互策略 | 后端依赖 |
|------|---------|---------|
| 新聊天 | 真实交互 | 无（前端创建新对话） |
| 搜索聊天 | 真实交互 | M4 conversation search API（已完成） |
| 最近对话 | 真实交互 | M4 conversation history API（已完成） |
| 最近报表 | 真实交互 | M3/M4 report history API（已完成） |
| 项目 | 仅展示卡片，不新增项目管理后端 | 无 |
| 用户账户 | 仅展示，不新增用户系统 | 无 |

**原则：** 已有完善后端能力的做真实交互；没有后端能力的只做展示，不为了 UI 扩大 M0–M4 后端范围。

### AI 回答 — 动态渲染原则

前端**不得**将 AI 回答固定为"文字 → 指标 → 表格 → 图表 → 报表附件"这类每次必现的序列。

前端根据当前 Turn 的用户意图和后端实际返回产物**动态渲染**：

- 普通问答：可能只有文字
- 数据查询：可能是文字 + 表格
- 简单数字追问：可能只有文字或指标
- 多轮追问：可能只更新文字/表格
- 比较/趋势且后端提供可视化数据：才显示图表
- 用户明确要求生成报表且后端真正生成 ReportArtifact：才显示 HTML 报表附件
- clarification：普通 AI 消息
- unsupported：普通 AI 消息
- error：普通 AI 消息
- empty：普通 AI 消息，不生成假表格/假图表

前端不得为了页面完整度自行创造 KPI、表格数据、图表数据、趋势、排名、HTML 报表或事实结论。

### Composer

结构（从左到右）：

| 组件 | 说明 |
|------|------|
| "+"按钮 | 点击弹出轻量菜单，分"数据模型"和"报表模板"两组 |
| 文本输入 | 占位文字："询问你的 Power BI 数据" |
| 模型选择器 | 圆角 pill 设计，可点击展开下拉卡片 |
| 发送按钮 | 黑色圆形，提交问题 |

#### "+"菜单

打开后显示两个分组：

1. **数据模型** — 映射为 chat request 的 `semantic_model_key`
2. **报表模板** — 映射为 chat request 的 `report_template_key`

M5.0 只固化交互结构和数据映射原则。如果当前没有独立 list API（`/api/semantic-models` 和 `/api/report-templates` 当前未实现），不在本轮实现；留到 M5.1 联调时做最小适配判断。

#### 模型选择器

- 点击模型 pill 打开下拉卡片
- 卡片中只显示 **DeepSeek**
- 单选，默认选中，有选中状态
- 不展示 Mock
- 不展示 GPT-5.6 或任何未真实接入模型
- 不承诺当前多模型能力
- 保留未来增加模型的 UI 扩展空间

### 视觉原则

- 白色主界面，极浅灰左侧栏
- 大面积留白
- 极简，不做 BI Dashboard / Admin Panel
- 不在 UI 展示 Trace、DAX、Memory、Log 或内部 Agent 状态
- 总体上参考 ChatGPT Web 风格（不是必须逐像素复制的最终稿）

### 视觉参考

- `docs/assets/frontend/整体01.png` — 已有对话与组合回答态
- `docs/assets/frontend/整体02.png` — 新聊天欢迎态与菜单展开态

## 后端能力到 UI 的映射（以当前代码为准）

| 后端能力 | 当前状态 | M5 UI |
|---------|---------|-------|
| `POST /api/v1/chat` | ✅ 已实现 | 对话主交互 |
| `GET /api/reports/{report_id}` | ✅ 已实现 | 查看报表 |
| `GET /api/reports/{report_id}/download` | ✅ 已实现 | 下载 HTML |
| `GET /api/v1/conversations` | ✅ 已实现（SQLite 必填 runtime_mode） | 最近对话列表 |
| `GET /api/v1/conversations/search` | ✅ 已实现 | 搜索聊天 |
| `GET /api/v1/conversations/{id}/history` | ✅ 已实现 | 恢复对话历史 |
| `GET /api/v1/conversations/{id}/reports` | ✅ 已实现（必填 source_mode） | 最近报表列表 |
| `POST /api/v1/conversations/{id}/archive` | ✅ 已实现 | 归档对话 |
| `DELETE /api/v1/conversations/{id}` | ✅ 已实现 | 删除对话 |
| `GET /api/semantic-models` | ❌ 未实现（需 M5.1 联调适配） | "+"菜单数据模型列表 |
| `GET /api/report-templates` | ❌ 未实现（需 M5.1 联调适配） | "+"菜单报表模板列表 |
| 统一 frontend envelope | ❌ 不存在 | M5.1 确定 |
| Multi-turn Memory 显示 | ✅ 后端已实现 | 前端仅展示当前 turn 的 answer |
| 报表资源显示 | ✅ 后端已实现 | ChatResponse.report 内的结构化报表字段 |

## 前端规范文档

- `docs/01_product_scope_and_frontend_skeleton.md` — 产品范围与前端骨架
- `docs/specs/10_frontend_visual_and_interaction_spec.md` — 正式视觉与交互规范
- `docs/specs/11_structured_answer_contract.md` — 结构化组合回答契约

## 当前目录约束

- M5.0 阶段：不创建 `package.json`、`src/`、`node_modules/` 或任何 React 代码
- 不创建 CSS 或组件文件
- 完整 React 开发在 M5.1 启动

## M5 路线

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M5.0 | 前端设计与契约固化（本文档校准、页面结构、交互边界、动态回答原则、UI↔后端能力映射） | **当前阶段** |
| M5.1 | React + Vite 实现与核心联调（Sidebar/Welcome/Chat/Composer、菜单交互、Chat/History/Search/Reports 联调、动态渲染） | ⬜ 待开始 |
| M5.2 | 视觉与交互收口（真实多轮测试、loading/error/empty/disabled、响应式、accessibility、最终视觉验收） | ⬜ 待开始 |

---

*最后更新：2026-08-21 | M5.0 前端设计与契约固化*
