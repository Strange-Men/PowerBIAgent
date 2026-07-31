项目名称：Power BI 数据分析 Agent MVP

一、项目背景

公司内部 Power BI 已沉淀部分语义模型，但普通业务人员仍需要通过 Power BI 页面、固定报表或数据人员获取数据。

本项目希望通过 LLM、Power BI MCP 和 Web 对话页面，让用户直接使用自然语言查询 Power BI 数据，并生成固定模板的静态 HTML 报表。

二、项目目标

完成一套可运行、可验证的 MVP，证明以下链路可行：

用户自然语言提问  
→ DeepSeek 理解需求  
→ Agent 调用 Power BI MCP  
→ 查询 Power BI 语义模型  
→ 返回可信的数据答案  
→ 根据固定模板生成静态 HTML 报表

MVP 主要供公司内部少量人员使用，暂不处理复杂客户权限和多租户问题。

三、目标用户

公司内部需要查看业务数据，但不熟悉 Power BI、DAX 或数据模型的业务人员。

四、核心使用场景

1. 数据问答

用户选择 Power BI 语义模型后，输入：

“本月销售额是多少？”  
“各区域销售额排名如何？”  
“最近六个月销售趋势怎么样？”

Agent 查询真实数据，并返回文字结论和数据表格。

1. 多轮追问

用户可以继续输入：

“只看华南。”  
“改成今年的数据。”  
“哪个区域下降最多？”

系统继承当前会话中的语义模型、指标、时间范围和筛选条件。

1. 报表生成

用户选择报表模板，例如：

满意度报告模板  
销售周报模板  
经营分析模板

然后输入自然语言要求，系统查询数据，并通过固定模板生成静态 HTML 报表。

五、前端设计

技术栈：React。

前端只做一个极简的白色对话页面，整体交互参考 GPT 网页版。

未开始对话时：

输入框显示在页面中间。

开始对话后：

消息内容在页面中展示，输入框固定在页面底部。

输入框包含：

1. “+”按钮

点击后弹出选择菜单，用于选择：

Power BI 数据模型  
固定报表模板

1. LLM 模型选择框

位于“+”按钮右侧，采用圆角框设计。

MVP 阶段只有 DeepSeek，但保留模型选择组件和扩展能力。

1. 文本输入区域

用户输入自然语言问题。

1. 发送按钮

用于提交问题。

回答展示形式包括：

文字回答  
简单数据表格  
报表结果卡片  
HTML 报表预览入口  
HTML 下载入口

前期只确认页面骨架，不进行完整前端开发。后端链路跑通后再进行正式联调。

六、后端设计

技术栈：FastAPI。

后端采用单 Agent 架构，不使用 LangGraph，不使用多 Agent。

主要模块包括：

1. API 层

负责接收前端请求和返回结果。

1. Agent 编排层

负责控制完整业务流程，包括：

读取会话状态  
识别用户意图  
选择工具  
生成查询  
处理查询结果  
生成最终回答或报表

1. LLM Provider 层

MVP 只接入 DeepSeek。

通过统一接口封装模型调用，后期可以增加其他 LLM，不影响 Agent 业务逻辑。

1. Power BI MCP Adapter

负责：

连接 Power BI MCP  
获取语义模型结构  
执行 DAX 查询  
统一处理 MCP 返回结果  
处理连接异常和查询错误

MVP 使用项目负责人的 Microsoft 账号登录和访问自己的 Power BI 数据。

1. Memory 模块

保存当前会话中的：

已选择语义模型  
最近一次用户意图  
指标  
维度  
时间范围  
筛选条件  
最近一次 DAX  
最近一次查询结果摘要

切换语义模型时，需要清空旧模型相关上下文。

1. 报表生成模块

LLM 不直接生成和执行任意 HTML、JavaScript 或 Python 代码。

LLM 只生成结构化 ReportSpec，包括：

报表标题  
摘要  
KPI  
图表类型  
图表字段  
表格字段  
分析结论

后端校验 ReportSpec 后，使用固定模板生成静态 HTML。

七、单 Agent 执行流程

接收用户请求  
→ 读取会话状态  
→ 判断数据问答或报表生成  
→ 获取 Power BI 语义模型结构  
→ 生成查询计划  
→ 生成并校验 DAX  
→ 通过 Power BI MCP 执行查询  
→ 校验查询结果  
→ 生成文字答案或 ReportSpec  
→ 固定模板渲染 HTML  
→ 保存会话和 Trace  
→ 返回前端

八、Agent 工具

MVP 只开放以下工具：

get_semantic_model_schema

获取当前 Power BI 语义模型中的表、字段、度量值和关系。

execute_dax

执行经过校验的 DAX 查询。

render_report

根据经过校验的 ReportSpec 和真实查询数据生成静态 HTML 报表。

Agent 不允许调用系统命令，不允许执行任意 Python、Shell、SQL 或 JavaScript。

九、Harness 设计

MVP Harness 用于限制 Agent 行为、防止开发偏移，并持续验证数据结果。

1. 结构化输出约束

LLM 的关键输出必须符合固定结构：

IntentSpec  
QueryPlan  
DAX  
AnswerSpec  
ReportSpec

所有结构使用 Pydantic 校验。

1. 工具白名单

Agent 只能调用预先登记的 Power BI 和报表工具。

1. 查询限制

限制：

查询超时时间  
最大返回行数  
最大重试次数  
禁止危险或无关查询  
禁止访问未选择的语义模型

1. Golden Cases

建立约20至30个固定测试问题，覆盖：

单指标查询  
区域排名  
时间趋势  
多条件筛选  
连续追问  
空数据  
错误字段  
DAX 执行失败  
销售周报生成  
满意度报告生成

每次修改 Prompt、Agent、MCP Adapter 或报表模块后执行回归测试。

1. Trace

每次请求记录：

用户问题  
所选语义模型  
所选模板  
意图识别结果  
查询计划  
生成的 DAX  
MCP 返回数据摘要  
最终答案  
ReportSpec  
错误信息  
各阶段耗时

十、MVP 接口

GET /api/health

检查后端、DeepSeek 和 Power BI MCP 的连接状态。

GET /api/semantic-models

返回可选择的 Power BI 语义模型。

GET /api/report-templates

返回可选择的固定报表模板。

POST /api/chat

接收用户问题并返回文字答案、表格或报表结果。

GET /api/reports/{report_id}

预览或下载已生成的静态 HTML 报表。

十一、MVP 开发顺序

第一阶段：Power BI MCP 连通

完成账号登录、读取语义模型和执行固定 DAX。

第二阶段：数据问答

完成自然语言理解、DAX 生成、查询执行和文字回答。

第三阶段：Harness

完成结构化输出、工具白名单、Trace、Golden Cases 和回归测试。

第四阶段：报表生成

完成 ReportSpec、固定模板和静态 HTML 输出。

第五阶段：会话记忆

完成多轮追问、筛选条件继承和模型切换处理。

第六阶段：React 页面

完成 GPT 式极简对话页面，并与后端接口联调。

十二、MVP 暂不包含

多 Agent  
LangGraph  
多租户  
复杂用户权限  
不同客户的数据隔离  
Power BI RLS 打通  
跨语义模型查询  
用户自定义 HTML 模板  
动态 Power BI 报表发布  
任意代码执行  
复杂后台管理页面

十三、验收标准

MVP 达到以下条件即可视为成功：

1. 后端可以稳定连接 Power BI MCP。
2. 可以读取指定语义模型的结构。
3. 用户可以通过自然语言查询真实 Power BI 数据。
4. 返回的核心数值与 Power BI 中的数据一致。
5. 支持基本多轮追问和筛选条件继承。
6. 可以使用固定模板生成静态 HTML 报表。
7. LLM 无法执行任意代码或绕过工具白名单。
8. 关键请求具备完整 Trace。
9. Golden Cases 可以重复执行并输出测试结果。
10. React 页面可以完成模型选择、模板选择、提问和结果展示。

十四、后续扩展方向

当 MVP 验证成功并出现正式客户需求后，再考虑：

多个 LLM 模型切换  
Microsoft 用户登录  
Power BI 用户权限和 RLS  
多租户隔离  
更多语义模型  
更多报表模板  
报表分享和定时发送  
更完整的 Harness 和评测平台  
更复杂的 Agent 编排