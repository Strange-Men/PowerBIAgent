# PowerBIAgent 前端

## 状态

**M5.3 — 结构化结果与前端最终收口已完成；Rich PBIX Real 浏览器验收通过。**

## 技术栈

- React 19
- Vite 8
- TypeScript 6
- React hooks 轻量状态管理
- 普通 CSS + lucide-react
- Vitest + Testing Library

## 启动与验证

```powershell
cd frontend
npm install
npm run dev
```

Vite 默认监听 `http://127.0.0.1:5173`，并将 `/api`、`/health` 代理至 `http://127.0.0.1:8000`。

```powershell
npm run typecheck
npm run lint
npm test
npm run build
```

前端从后端只读语义模型发现响应取得当前 runtime namespace、模型与 compatibility 状态；浏览器不读取 `.pbix`，也不保存任何连接信息或 Provider Secret。Mock 后端联调时可显式使用 `VITE_RUNTIME_MODE=mock` 作为请求前的保守初值，后端发现结果仍是运行时权威来源。模型可连接但不符合当前 glossary/schema 时仍会显示名称与明确提示，但发送保持禁用。

连接本地 PBIX 的完整配置和启动顺序见根目录 [README 的“本地 Power BI 真实模式启动”章节](../README.md#本地-power-bi-真实模式启动)。默认配置是 Mock，仅用于开发测试。

## 页面结构

带左侧栏的 GPT 式极简白色对话网页。

### 整体布局

- **左侧栏：** PowerBIAgent 标识、折叠/展开、新聊天、搜索聊天、项目、最近报表、最近对话、底部账户展示
- **主对话区：** 新聊天欢迎态（页面居中留白、欢迎图标、主标题“今天想分析什么数据？”、副标题）、已有对话态（用户消息浅灰气泡、AI 组合回答、底部输入区）

### 左侧栏能力边界

| 条目 | 交互策略 | 后端依赖 |
|------|---------|---------|
| 新聊天 | 真实交互 | 无（前端创建新对话） |
| 搜索聊天 | 真实交互 | M4 会话搜索 API（已完成） |
| 最近对话 | 打开、搜索、重命名、归档、删除 | M4 API + M5.3 presentation metadata |
| 最近报表 | 查看、下载；按所属 conversation 管理 | M3/M4 报表历史与 conversation delete API |
| 项目 | 仅展示卡片，不新增项目管理后端 | 无 |
| 用户账户 | 仅展示，不新增用户系统 | 无 |

**原则：** 已有完善后端能力的功能提供真实交互；没有后端能力的功能只做展示，不为了 UI 扩大 M0–M4 后端范围。

### AI 回答 — 动态渲染原则

前端**不得**将 AI 回答固定为"文字 → 指标 → 表格 → 图表 → 报表附件"这类每次必现的序列。

前端根据当前轮次的用户意图和后端实际返回产物**动态渲染**：

- 普通问答：可能只有文字
- 数据查询：可能是文字 + 表格
- 简单数字追问：可能只有文字或指标
- 多轮追问：可能只更新文字或表格
- 比较/趋势且后端提供可视化数据：才显示图表
- 用户明确要求生成报表且后端真正生成 ReportArtifact：才显示 HTML 报表附件
- clarification：普通 AI 消息
- unsupported：普通 AI 消息
- error：普通 AI 消息
- empty：普通 AI 消息，不生成假表格或假图表

前端不得为了页面完整度自行创造 KPI、表格数据、图表数据、趋势、排名、HTML 报表或事实结论。

### 输入区（Composer）

结构（从左到右）：

| 组件 | 说明 |
|------|------|
| "+"按钮 | 点击弹出轻量菜单，分"数据模型"和"报表模板"两组 |
| 文本输入 | 占位文字："询问你的 Power BI 数据" |
| 模型选择器 | 圆角 pill 设计，可点击展开下拉卡片 |
| 发送按钮 | 黑色圆形，提交问题 |

#### "+"菜单

打开后显示两个分组：

1. **数据模型** — 映射为 Chat 请求的 `semantic_model_key`
2. **报表模板** — 仅在用户主动选择具体模板时映射为 Chat 请求的可选 `report_template_key` override

M5.3 使用 `GET /api/v1/semantic-models` 读取后端通过 Local MCP / 当前 Power BI Desktop 实例发现并进行最小 Agent compatibility 检查的模型。浏览器不能直接读取 `.pbix`；前端只展示后端返回的安全目录，不再内置或伪造“Power BI 销售数据”。Mock discovery 只暴露正式支持的 `mock_sales_model`。当前 Local Adapter 的稳定执行合同一次只连接一个 Desktop 模型；若模型可连接但暂不符合当前业务结构，UI 明确提示并禁用发送，不显示内部 schema/hash/DAX。

报表模板暂时没有发现 API，继续由 `src/config.ts` 集中维护 registry-owned 目录。当前只有 `sales_report`，展示名为“销售分析报告”。菜单不提供“不使用模板”：未选择模板只表示本次请求不传 override，普通问答、多轮分析或报表生成仍由后端 intent 自动识别；即使未显式选择，后端也可以按业务规则为报表意图选择默认模板。

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

## 后端能力与 UI 映射（以当前代码为准）

| 后端能力 | 当前状态 | M5 UI |
|---------|---------|-------|
| `POST /api/v1/chat` | ✅ 已实现 | 对话主交互 |
| `GET /api/reports/{report_id}` | ✅ 已实现 | 查看报表 |
| `GET /api/reports/{report_id}/download` | ✅ 已实现 | 下载 HTML |
| `GET /api/v1/conversations` | ✅ 已实现（SQLite 必填 runtime_mode） | 最近对话列表 |
| `GET /api/v1/conversations/search` | ✅ 已实现 | 搜索聊天 |
| `GET /api/v1/conversations/{id}/history` | ✅ 已实现 | 恢复对话历史 |
| `GET /api/v1/conversations/{id}/reports` | ✅ 已实现（必填 source_mode） | 最近报表列表 |
| `PATCH /api/v1/conversations/{id}` | ✅ M5.3 presentation metadata | 会话重命名 |
| `POST /api/v1/conversations/{id}/archive` | ✅ 已实现 | 归档对话 |
| `DELETE /api/v1/conversations/{id}` | ✅ 已实现 | 删除对话 |
| `GET /api/v1/semantic-models` | ✅ M5.3 最小只读 compatibility | 动态加载 Desktop 模型、runtime namespace 与兼容状态 |
| `GET /api/report-templates` | ❌ 未实现 | `sales_report` 集中白名单配置 |
| `ChatResponse.presentation` | ✅ M5.3 只读展示层 | 动态消费 dataset 引用与 text/metric/table/chart/report blocks |
| 展示型 transcript/title | ✅ M5.3 | 完整恢复新会话消息、自动标题与重命名；不作为 Memory 事实 |
| 多轮 Memory 显示 | ✅ 后端已实现 | UI 只展示保存的 transcript/result，不读取 Memory |
| 报表资源显示 | ✅ 后端已实现 | ChatResponse.report 内的结构化报表字段 |

## 前端规范文档

- `docs/01_product_scope_and_frontend_skeleton.md` — 产品范围与前端骨架
- `docs/specs/10_frontend_visual_and_interaction_spec.md` — 正式视觉与交互规范
- `docs/specs/11_structured_answer_contract.md` — 结构化组合回答契约

## 实现结构

- `src/api/`：typed fetch 客户端、namespace 查询与 Chat/History → UI adapters
- `src/components/`：Sidebar、Composer、Conversation、动态 Assistant、StructuredBlocks 与 ReportAttachment
- `src/hooks/usePowerBIAgent.ts`：当前会话、recent/search/history/reports 与发送状态
- `src/config.ts`：模板目录与发现前的保守 runtime 初值；不再配置真实 Desktop 模型
- `src/styles.css`：GPT 式桌面优先布局与基础窄屏适配

`ChatResponse.presentation` 与 History 中保存的同一 envelope 暴露一份 QueryResult dataset；metric/table/chart block 只保存 `data_reference` 与字段引用。前端不读取 DAX/Trace/Memory，也不从 `execution_audit` 或 answer 反解析事实。目前动态支持文字、单值指标、多行表格、简单柱状图/折线图和 ReportArtifact；没有真实 block 时不补假内容。

## M5 路线

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M5.0 | 前端设计与契约固化（本文档校准、页面结构、交互边界、动态回答原则、UI↔后端能力映射） | ✅ 已完成 |
| M5.1 | React + Vite 实现与核心联调（Sidebar/Welcome/Chat/Composer、菜单交互、Chat/History/Search/Reports 联调、动态渲染） | ✅ 已完成 |
| M5.2 | 真实业务链路与前端逻辑收口（Real、Desktop 模型发现、SQLite 会话、intent/template/model、Chat 多轮与报表联调、最小错误态） | ✅ 已完成 |
| M5.2.1 | 模型能力边界与真实模式说明收口 | ✅ 已完成 |
| M5.3 | 结构化结果、历史/标题/管理、ChatGPT 风格尺寸/间距、responsive、accessibility、状态与表格/图表视觉 | ✅ 已完成，Rich PBIX Real 验收通过 |

---

*最后更新：2026-08-23 | M5.3 COMPLETE — 结构化结果与前端最终收口*
