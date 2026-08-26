# 10 — 前端视觉与交互规范

> **状态：** M5.4.2 重建线规划固化（COMPLETE）；当前实现能力保持 M5.4.1
> **目标阶段：** M5.6 负责 Presentation/Localization/Resource UX truth；M5.7 独立负责 Report readability
> **视觉参考：**
> ![已有对话与组合回答参考](../assets/frontend/整体01.png)
> ![新聊天欢迎态与菜单参考](../assets/frontend/整体02.png)

---

## 一、文档目的

本文件记录 PowerBIAgent 前端的产品视觉方向与交互规范。内容基于两张前端参考图和项目负责人提供的文字化分析。

本文档是当前 React 前端的正式视觉与交互基线。两张图片是视觉方向参考，不是官方尺寸来源，也不要求逐像素复制。总体目标为简洁、清晰、参考 GPT 网页端风格。

## 二、当前阶段与实施边界

**当前阶段：** M5.4 已将请求与 UI 状态收口到 conversation scope；M5.4.1 已把依赖 Recent 第一页的轻量资源面板修复为独立分页的 Settings Hub。M0–M5 factual authority 保持不变；没有真实 presentation block 时不伪造前端表格或图表。

### 2.1 重建线后续边界

- M5.4.2 只固化规范，不修改 `frontend/src/**`。旧 `m5/frontend` 的原 M5.5/M5.5.1 视觉与 UX 代码不是新线基线。
- M5.6 才处理 Settings 有 report 但 Recent Reports 不同步、Recent conversation newest-first、failed conversation 正式可管理、toolbar 空间不足时 destructive action 可达，以及 conversation/report floating menu 不被 overflow clipping。
- toolbar 必须使用 sticky、scroll 或 responsive 策略保持关键操作可达；禁止以窄屏或容器空间不足为由隐藏 destructive action。
- M5.7 才处理 report card width/height、时间轴跨年识别、plot area、无意义空白、donut/legend 密度、accessibility 与视觉层级。
- “技术不裁切”不等于“产品可读”。M5.7 必须通过 Real Browser 人工视觉 Gate；M5.6 不修改 report renderer，M5.7 不修改 Semantic/MCP/resource lifecycle。

## 三、视觉参考图片

| 图片 | 文件名 | 内容 |
|------|--------|------|
| 已有对话与组合回答态 | `assets/frontend/整体01.png` | 已有对话中的 AI 组合回答、左侧栏、底部输入器 |
| 新聊天欢迎态与菜单展开态 | `assets/frontend/整体02.png` | 新聊天欢迎页、"+"菜单展开态、模型选择器展开态 |

## 四、视觉原则

1. **全局以纯白和极浅灰为主** — 主背景白色，分隔区域使用极浅灰
2. **正文使用黑色和深灰** — 高对比度，易阅读
3. **分隔线与边框使用浅灰** — 轻量不抢眼
4. **数据图表和可点击报表链接使用克制的蓝色** — 不作为大面积装饰色
5. **页面保持大面积留白** — 信息密度低，呼吸感强
6. **卡片圆角轻量** — 圆角小，不圆润
7. **阴影非常克制** — 仅在必要时使用微弱阴影
8. **不使用**：大面积渐变、深色背景、彩色仪表盘、大量装饰性 KPI 卡、复杂动画、多层嵌套面板

## 五、桌面端整体布局

```
┌──────────────┬─────────────────────────────────────────┐
│   左侧栏      │              主对话区                     │
│              │                                         │
│  PowerBI     │  ┌───────────────────────────────────┐  │
│  Agent       │  │  对话标题栏（已有对话态）            │  │
│  [折叠]      │  │  或欢迎态（新聊天）                 │  │
│              │  ├───────────────────────────────────┤  │
│  ✚ 新聊天    │  │                                   │  │
│  🔍 搜索     │  │  消息流区域                        │  │
│              │  │  · 用户消息（右侧浅灰气泡）         │  │
│  项目        │  │  · AI 组合回答（左侧、无气泡背景）  │  │
│              │  │  · 内容按需动态渲染                 │  │
│  最近报表    │  │                                   │  │
│  最近对话    │  │                                   │  │
│              │  ├───────────────────────────────────┤  │
│  用户信息    │  │  底部 Composer                     │  │
│              │  │  [+] [输入框] [DS▼] [●]           │  │
└──────────────┴──────────────────────────────────────┘
```

## 六、左侧栏

### 6.1 定位

- 新聊天和对话导航入口
- 展示项目入口（仅卡片展示）
- 展示最近报表和最近会话（真实交互，依赖 M3/M4 后端）
- **不展示：** Trace、日志、Memory 内部状态、系统健康状态、开发调试面板

### 6.2 内容（从上到下）

| # | 内容 | 说明 | 交互策略 |
|---|------|------|---------|
| 1 | PowerBIAgent 文字标识 | 品牌标识 | UI |
| 2 | 侧栏折叠按钮 | 折叠/展开左侧栏 | UI |
| 3 | 新聊天 | 创建新对话入口 | 真实交互 |
| 4 | 搜索聊天 | 搜索历史对话 | 真实交互，接 M4 后端 |
| 5 | "项目"分区标题 | 分区标签 | — |
| 6 | 当前 Power BI 分析项目 | 仅展示卡片，不新增后端 | 仅展示 |
| 7 | "最近报表"分区标题 | 分区标签 | — |
| 8 | 最近生成的报表列表 | 可折叠、独立滚动；不放批量 checkbox | 真实交互 |
| 9 | "最近"分区标题 | 对话分区标签 | — |
| 10 | 最近对话 | persisted + local pending；可折叠、独立滚动 | 真实交互 |
| 11 | 用户卡片 | 底部固定，展示用户名/内部用户；只打开统一“设置” | 真实交互，不新增账户后端 |

## 七、新聊天欢迎态

### 7.1 布局

- 页面中央保持大量留白
- 垂直居中排列

### 7.2 内容

- 简单数据分析图标（中置）
- 主标题："今天想分析什么数据？"
- 副标题："可以查询数据、生成报表或开始新的分析。"

### 7.3 不展示

- 仪表盘
- 推荐 KPI 卡
- 系统模块列表
- 开发说明

## 八、已有对话态

### 8.1 顶部

- 左侧：当前对话标题（可选）+ 轻量下拉箭头（可选）
- 右上角：分享或导出入口图标（可选，M5.3 决定细节）
- **不设计复杂导航栏**
- **不展示系统状态、模型 Token、Trace 等信息**

### 8.2 用户消息

- 位于主内容区右侧
- 使用浅灰圆角气泡
- 文本简洁
- **不使用**：高饱和背景、头像大卡片、复杂消息工具栏

### 8.3 AI 回答

- 位于主内容区中间偏左
- **默认不使用明显气泡背景**（与用户消息区分）
- 内容按自然阅读顺序纵向排列
- 回答最大内容宽度适中（不铺满超宽屏）

### 8.4 AI 回答动态渲染（核心）

> **绝对禁止：** 将 AI 回答固定为"文字 → 指标 → 表格 → 图表 → 报表附件"这类每次必现的序列。

**正确规则：** 前端根据当前 Turn 的用户意图和后端实际返回产物动态渲染。具体内容块类型包括：

| 内容块 | 出现条件 | 数据来源 |
|--------|---------|---------|
| text（文字） | 任何 AI 回答 | ChatResponse.answer / clarification_question / unsupported_reason |
| metric（指标摘要） | VerifiedFactSet scalar fact 可回指真实 row 时 | `presentation` dataset + field/row reference |
| table（表格） | grouped fact 且 QueryResult 包含数据行时 | `presentation` 的单一 QueryResult dataset |
| chart（图表） | grouped result 至少两行且 Y 字段为数值时 | 同一 dataset 的 X/Y field reference |
| report_attachment（报表附件） | 后端真正生成 ReportArtifact 时 | canonical `report_id` |

典型场景渲染：

| 场景 | 展示内容 |
|------|---------|
| 普通问答 | 仅有文字 |
| 数据查询 | 文字 + 表格 |
| 简单数字追问 | 仅有文字或指标 |
| 多轮追问 | 仅更新文字/表格 |
| comparison/trend 且后端提供可视化 | 才显示图表 |
| 用户要求生成报表且后端生成 ReportArtifact | 才显示报表附件卡片 |
| clarification | 文字（clarification_question） |
| unsupported | 文字（unsupported_reason） |
| error | 文字（error_type + answer） |
| empty | 文字说明，不生成假表格/假图表 |

**安全约束：**
- 表格数据必须来自后端 QueryResult
- 图表 block 只能引用同 envelope 的 QueryResult dataset
- 指标值必须由后端 VerifiedFactSet 证明
- source_mode 必须与数据层一致
- 报表引用由后端生成
- **禁止**前端为了页面完整度创造 KPI、表格数据、图表数据、趋势、排名、HTML 报表、事实结论

## 九、表格

### 9.1 样式

- 直接嵌入 AI 回答，不独立弹出
- 白色背景
- 不使用厚重外框
- 使用浅灰横向分隔线
- 表头清晰（加粗或浅灰背景）
- 行距舒适（适当行高）
- 数字列右对齐或居中对齐

### 9.2 不设计

- 复杂筛选器
- 分页工作台
- 列排序交互（MVP）
- 列宽拖拽调整（MVP）

### 9.3 数据约束

- columns 必须与后端 QueryResult.columns 一致
- rows 必须与后端 QueryResult.rows 一致
- 没有表格数据时不生成空表格

## 十、图表

### 10.1 样式

- 直接嵌入 AI 回答
- 标题简洁（如"各区域销售额"）
- 坐标轴清晰（含刻度标签）
- 数据标签可见（在柱/点旁标注数值）
- 颜色克制，优先单一蓝色

### 10.2 允许的图表类型

- bar（柱状图，含横向/纵向）
- line（折线图）
- 仅在后端返回的可视化数据可用时渲染

### 10.3 禁止

- 3D 图表
- 花哨渐变
- 默认展示复杂交互工具栏（缩放、导出等）
- 图表数据来源虚构（必须来自后端 QueryResult）
- 无可视化数据时也显示图表

### 10.4 数据约束

- type 当前只允许 `bar` 或 `line`
- 字段必须存在于后端 QueryResult.columns
- 数据必须引用后端 QueryResult

## 十一、报表附件

### 11.1 样式

轻量横向卡片，与消息流齐宽。

### 11.2 内容

- 文件图标（左侧）
- 报表标题
- 文件类型（如"HTML 报表"）
- "查看报表"操作（链接/按钮）
- "下载 HTML"操作（链接/按钮）

### 11.3 规则

- 附件卡片属于 AI 消息的一部分
- 仅在后端真正生成 ReportArtifact 时显示
- 查看和下载能力已在 M3/M4 实现
- 不设计独立复杂报表后台

### 11.4 数据约束

- report_id 来自后端
- view_reference 和 download_reference 由后端生成
- LLM 不得生成任意外部 URL
- 最近报表提供 `… → 删除报表`，必须经用户确认；只调用显式资源管理 API，不删除所属 conversation
- 独立删除后该 report 不再从 Recent/History attachment 恢复；LLM 与自然语言 Chat 无删除路径

### 11.5 异步 conversation 隔离

- 打开 conversation 时立即记录目标 ID，并为 history 请求分配 generation/AbortController
- response 返回后再次核对 response conversation ID、当前 active ID 与 generation；任一不一致即丢弃
- open/new/delete/archive/restore/model switch 必须使旧 history 请求失效
- A conversation 的慢响应、错误或 report attachment 不得覆盖已经打开的 B conversation

### 11.6 report tombstone 与重命名（M5.4）

- report 独立删除后，所属 assistant message 保留“曾生成过报表”的 presentation tombstone；标题使用删除前最后一个 `display_title`。
- tombstone 显示“报表已删除 / 此文件已不可查看或下载”，隐藏 view/download，不重建 ReportArtifact。
- history restore 必须复原 tombstone，不得将整个 attachment block 静默丢弃。
- rename 只更新 presentation-only `display_title`，Sidebar 与 report card 共用该标题；`report_id`/HTML/`content_hash`/ReportSpec/VerifiedFactSet 不变。
- rename/delete 只能由明确 UI 用户操作触发，不进 ToolGateway 或 LLM allowed tools。

## 十二、底部输入器（Composer）

### 12.1 样式

- 位于主内容区底部
- 宽大的圆角胶囊形容器
- 整体保持简洁和低干扰

### 12.2 组件（从左到右）

| 组件 | 说明 |
|------|------|
| "+"按钮 | 点击弹出"+"菜单，分"数据模型"和"报表模板"两组 |
| 文本输入区域 | 占位文字："询问你的 Power BI 数据" |
| 模型选择器 pill | 圆角 pill 设计，显示当前模型名称 |
| 发送按钮 | 黑色圆形，提交问题 |

### 12.3 行为

- 开始对话后输入器固定或稳定停留在页面底部
- 支持 Enter 发送，Shift+Enter 换行
- 只在 active conversation 自己 sending 时禁用其输入框；其他 idle conversation 仍可发送

### 12.4 conversation-scoped 请求状态（M5.4）

- 状态容器固定为 `conversation_id → ConversationSession`，每个 session 独立保存 messages/pendingRequests/sending/loadingHistory/error/status。
- 新会话首次发送前生成 UUID，立即写入本地 session/Sidebar，同一 ID 传给 Chat API。
- 不同 session 的 chat promise 独立运行；任一完成只更新它的 session，不读写 active session 的 messages/error，不改 active ID。
- 同一 session `sending=true` 时禁止第二次发送。切窗只能 Abort history/navigation，不 Abort business chat。

## 十三、"+"菜单

点击输入器左侧"+"按钮后，在输入器上方弹出轻量菜单。

### 13.1 数据模型分组

- 映射为 chat request 的 `semantic_model_key`
- 实际内容只来自 `GET /api/v1/semantic-models` 返回的 safe catalog
- 浏览器不读取 `.pbix`；后端通过 Local MCP / Power BI Desktop 实例发现并验证连接
- catalog 至少包含 backend-owned stable key、display name、source/type、available/connected；不得返回端口、connection string、path 或 MCP raw payload
- catalog 同时返回最小 `agent_compatible` / `compatibility_status`；不可返回 schema、fingerprint 或 DAX
- 无模型时显示明确 empty state 并禁用发送，不伪造默认 PBIX
- Desktop 可连接但 Agent 不兼容时显示“当前模型已连接，但暂不符合 PowerBIAgent 当前支持的数据结构”，并禁用发送
- 当前只能稳定连接一个 Desktop 模型时显示“当前已连接模型”；不得用静态“Power BI 销售数据”冒充真实模型
- 当前选中项应有清晰视觉状态
- 前端不得自行生成不存在的模型

### 13.2 报表模板分组

- 映射为 chat request 的 `report_template_key`
- 实际内容来自已登记模板白名单
- 当前无独立 `/api/report-templates` 端点；前端集中 catalog 只登记 `sales_report`（“销售分析报告”）
- 不显示“不使用模板”；默认未选择表示本次请求不传 override，不代表“仅问答”或“禁止报表”
- 普通问答、多轮和 report intent 由后端自动识别；未传 override 时后端仍可选择默认模板
- 用户主动选择的 template override 是单次请求意图，发送后回到未选择状态，避免变成粘性的“报表模式”
- 当前选中项应有清晰视觉状态
- 未实现或不适用于当前模型的模板必须禁用或隐藏

### 13.3 规则

- 数据模型和报表模板不能混成一个无分类列表
- 当前选中项应有清晰视觉状态
- 未实现或无权限选项必须禁用或隐藏
- 前端不得自行生成不存在的模型和模板
- M5.1 已实现交互结构和 request 字段映射

## 十四、模型选择器

### 14.1 样式

输入器右侧的圆角 pill。

### 14.2 交互

- 点击 pill 打开下拉卡片
- 卡片中只显示 **DeepSeek**
- 单选，默认选中，有选中状态

### 14.3 真实产品边界

> **当前 MVP 正式用户模型只有 DeepSeek。**
> **不展示 Mock**（仅用于开发和测试）。
> **不展示 GPT-5.6** 或任何未真实接入模型。
> 不承诺当前多模型能力。
> 保留未来增加模型的 UI 扩展空间（如卡片结构支持滚动列表）。

## 十五、状态规范

### 15.1 加载状态

- 消息流中显示简洁等待反馈（如三点加载动画）
- 不创建独立 Loading 面板或全屏遮罩
- 发送期间输入框保持禁用但不隐藏

### 15.2 空数据状态

- AI 消息说明"暂无符合条件的数据"或类似信息
- 不生成空图表和假指标
- 不显示空白表格

### 15.3 错误状态

- 作为普通对话反馈显示（非弹窗）
- 给出简洁错误描述
- 提供可重试提示（如适用）
- **不展示**：完整异常堆栈、Trace 详情、内部错误代码

### 15.4 禁用状态

以下情况必须明确禁用，不得制造可点击但无效果的按钮：

- 未接入的 LLM 模型
- 未配置的数据模型
- 未登记的报表模板
- 未实现的查看报表功能（当前已实现，不应禁用）
- 未实现的下载功能（当前已实现，不应禁用）

## 十六、响应式原则

桌面端优先。M5.3 已实现以下窄屏行为：

- 小屏默认折叠 Sidebar，仅保留可访问的展开、新聊天与搜索入口
- 主对话区占满可用宽度
- 输入器保持可操作（不溢出）
- 表格允许横向滚动
- 图表适配容器宽度
- 报表卡片操作不溢出

Sidebar 在桌面端固定可用高度；“最近对话”与“最近报表”各自 `overflow-y:auto` 并可折叠。已归档默认不常驻 Sidebar，通过用户卡片进入资源面板。

## 十六 A、用户卡片与 Settings Hub（M5.4.1）

- 用户卡片只提供“设置”入口；Settings 左导航固定为“常规 / 对话管理 / 报表管理 / 已归档 / 数据模型 / 关于”，不恢复三个重复一级入口，也不增加套餐、支付、账户安全等无后端能力。
- “对话管理”独立分页查询全部 active conversations；“报表管理”独立分页查询全部 active reports；“已归档”分为已归档对话与已归档报表。Settings 不读取 Sidebar `recentConversations` 作为数据源。
- 每个列表使用固定高度 scroll container，首屏只渲染一页；提供 loading more、empty state、`共 N 项`、`已加载 N 项`、`已选择 N / 共 N 项` 和明确的 has-more/load-more control。
- checkbox 与批量操作只在 Settings。按钮文案固定为“全选当前已加载”；只有完整后端查询条件与全部匹配 ID 均已取得时才允许“选择全部匹配项”，并显示完整数量。
- 用户可持续分页后多选任意历史项，选择数量不受 20 限制。一次确认的大批量操作由前端按最多 20 项一组执行，每组继续调用正式单资源 API；成功项移除，失败项保留并逐项显示原因。
- conversation 支持 rename/archive/delete；report 支持 rename/archive/delete；归档页支持 restore/delete。删除必须确认，archive/restore 不重建事实资源，delete 不得绕过 durable delete intent。
- report 行与 Sidebar Recent Reports 的 `…` 菜单统一提供“重命名 / 归档 / 删除”。rename 只改 `display_title`；archive 隐藏 recent、保留 HTML/metadata/conversation；delete 清理 managed HTML/factual metadata 并保留最后 title 的 history tombstone。

## 十七、当前 MVP 后端能力到 UI 映射

| 能力 | 后端状态 | M5 UI |
|------|---------|-------|
| 左侧栏（完整） | — | ✅ M5.1 |
| 新聊天欢迎态 | — | ✅ M5.1 |
| AI 组合回答 | ChatResponse 含 answer/report/clarification/unsupported 字段 | ✅ M5.1 动态渲染 |
| 最近报表列表 | ✅ M3/M4 report history API 已完成 | ✅ M5.1 |
| 最近对话列表 | ✅ M4 conversation history API 已完成 | ✅ M5.1 |
| 搜索聊天 | ✅ M4 search API 已完成 | ✅ M5.1 |
| "查看报表"操作 | ✅ M3 resource API 已完成 | ✅ M5.1 |
| "下载 HTML"操作 | ✅ M3 resource API 已完成 | ✅ M5.1 |
| 多模型切换 | DeepSeek 唯一启用 | ✅ M5.1 单选交互 |
| 响应式布局 | — | ✅ M5.3 desktop/medium/small |
| semantic_model_key 列表 | ✅ M5.3 最小只读 compatibility | +"菜单展示 Desktop model safe catalog 与兼容状态 |
| report_template_key 列表 | ❌ 无独立 API | +"菜单只登记 `sales_report` |
| `presentation` 展示层 | ✅ Chat/History typed envelope | M5.3 动态 text/metric/table/bar/line/report |
| History transcript/title | ✅ presentation metadata | M5.3 完整恢复、默认标题、重命名 |
| Conversation 管理 | ✅ archive/delete + M5.3 rename；M5.3.3 restore | Sidebar 区分最近/已归档；archive 可恢复，delete 永久清理 |
| 独立 report delete | M5.3.3 显式资源 API | 最近报表 `…` 菜单 + 确认；conversation 保留，LLM 无权限 |
| 多 conversation state | M5.4 前端合同 | local UUID pending、异会话并发、同会话串行、loading/error/result 隔离 |
| 用户资源管理 | M5.4.1 独立分页 + 前端协调单资源 API | Settings Hub、完整 active/archived conversation/report、selection 不限、最多 20 项/执行组、partial failure |
| report rename/tombstone | M5.4 presentation metadata | `display_title` 同步；deleted 历史卡保留且无 view/download |

## 十八、明确禁止的设计

### 禁止的页面形态

- 传统 BI 后台/数据治理平台
- 多面板企业工作台
- 管理驾驶舱
- Tab 式多页面后台

### 禁止的视觉风格

- 大面积渐变
- 深色背景
- 彩色仪表盘
- 大量装饰性 KPI 卡
- 复杂动画
- 多层嵌套面板

### 禁止的功能展示

- Trace / 日志 / Memory 内部状态（左侧栏）
- 系统健康状态（主对话区顶部）
- 模型 Token 用量（主对话区顶部）
- 开发调试面板

### 禁止的数据展示

- 把 Mock 数据描述为真实 Power BI 数据
- 把未接入模型展示为可用
- 把 Mock 展示为用户正式模型
- 展示未经验证的数据结论
- 为了页面完整度自行创造 KPI/表格/图表/报表

### 禁止的内容固定

- 固定"文字 → 指标 → 表格 → 图表 → 报表附件"的必现序列
- 每次 AI 回答都生成相同结构的内容块
- 在后端无报表时仍显示报表附件卡片
- 在后端无可视化数据时仍显示图表

---

*创建日期：2026-08-03 | M1.3.2 前端视觉与结构化回答契约固化*
*最后更新：2026-08-26 | M5.4.2 COMPLETE — M5.6/M5.7 视觉与交互职责隔离*
