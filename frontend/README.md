# Frontend — PowerBIAgent 前端

## 状态

**前端正式开发延后至后端核心链路跑通后（M5）。**

当前 M1.3.2 已固化前端视觉方向和交互骨架，不创建 React 项目。

## 技术栈

- React 18+
- Vite 构建工具
- 轻量状态管理

## 页面方向

带左侧栏的 GPT 式极简白色对话网页。

### 整体布局

- **左侧栏（约15%宽）：** PowerBIAgent 标识、新聊天、搜索聊天（M4 后端/M5 界面）、项目、最近报表（M3 后端/M5 界面）、最近对话（M4 后端/M5 界面）、用户信息。左侧栏 React UI 整体属于 M5，M3/M4 只准备后端能力
- **主对话区：** 新聊天欢迎态、已有对话态（用户消息 + AI 组合回答 + 底部输入器）

### AI 回答

未来支持文字、表格、图表和报表附件组合展示，数据必须来自后端 QueryResult。

### 输入器

胶囊形容器，包含"+"按钮（数据模型 + 报表模板两分组）、文本输入、模型菜单（当前仅 DeepSeek 正式可用）、发送按钮。

## 视觉参考

- `docs/assets/frontend/整体01.png` — 已有对话与组合回答态
- `docs/assets/frontend/整体02.png` — 新聊天欢迎态与菜单展开态

## 前端规范文档

- `docs/01_product_scope_and_frontend_skeleton.md` — 产品范围与前端骨架
- `docs/10_frontend_visual_and_interaction_spec.md` — 正式视觉与交互规范
- `docs/11_structured_answer_contract.md` — 结构化组合回答契约

## 当前目录约束

- 不创建 `package.json`、`src/`、`node_modules/` 或任何 React 代码
- 不创建 CSS 或组件文件
- 完整前端开发在 M5 启动

---

*最后更新：2026-08-03 | M1.3.2 前端视觉与结构化回答契约固化*
