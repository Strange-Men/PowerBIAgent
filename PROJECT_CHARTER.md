# PROJECT_CHARTER — PowerBIAgent 项目北极星

> **重要：后续每轮 Claude 开始前必须阅读此文件。**
> 未经用户明确确认，不得静默修改北极星内容。
> 重大方向变化必须新增 ADR 并在项目状态文档中记录。
> 开发时间变长不能成为偏离项目初衷的理由。

---

## 一、项目使命

让公司内部不熟悉 Power BI、DAX 或数据模型的业务人员，通过自然语言对话直接获取 Power BI 语义模型中的数据答案，并以固定模板生成静态 HTML 报表。

## 二、目标用户

公司内部需要查看业务数据但不具备 Power BI 技术能力的业务人员。

## 三、核心业务链路

```
用户自然语言提问
→ React 极简对话页面
→ FastAPI 后端
→ 确定性 TurnPipeline（Intent → Grounding → Canonical QueryPlan → Deterministic DAX → VerifiedFactSet）
→ DeepSeek（受控语言理解与结构化草稿；不拥有 Real DAX/Fact authority）
→ Power BI MCP
→ Power BI 语义模型
→ 数据问答或固定模板静态 HTML 报表
```

## 四、核心卖点

- 自然语言对话式数据查询
- 确定性 TurnPipeline 生命周期控制（非自主 Agent 循环）
- 受控 LLM 语言理解与结构化草稿；Real 执行与外部事实由普通代码确定性控制
- 结构化工作记忆与可靠提交机制
- 固定模板安全报表生成
- Power BI MCP 后端统一接入

## 五、前端固定方向

- 仅使用 React + Vite
- 类似 GPT 网页版的极简白色对话页面
- 正式前端开发等待后端核心链路跑通后启动

## 六、后端固定方向

- 使用 FastAPI
- 采用确定性 TurnPipeline 控制对话生命周期（非自主 Agent 循环）
- LLM 仅负责受约束的 Intent、语言草稿与 Catalog-owned bounded selection；Real DAX 与 factual Answer/Report 由 Deterministic Builder + VerifiedFactSet 控制
- 通过统一 Provider 接口封装 LLM 调用，Mock 与 DeepSeek 共享同一执行骨架
- ToolGateway 是 Power BI 和 Renderer 的唯一调用入口
- **不使用 LangGraph**
- **不使用多 Agent**
- **不从零手写复杂 Agent Runtime**
- 意图识别必须明确、独立、可测试

## 七、确定性管线原则

- 整个对话生命周期由确定性 TurnPipeline 控制（非 LLM 自主决策）
- TurnPipeline 按固定阶段顺序执行：Intent → Grounding → Canonical QueryPlan → Deterministic DAX → QueryResult → VerifiedFactSet → Answer/ReportSpec
- 管线拥有明确工具白名单
- 管线不执行任意 Python、Shell、PowerShell、SQL、JavaScript 或自由 HTML
- LLM 在管线中不控制流程分支、工具调用、Real DAX 或外部事实

## 八、意图识别要求

- Agent 必须首先完成意图识别，输出结构化 IntentSpec
- 意图识别结果可独立测试和回归

## 九、LLM 策略

- 真实 LLM 前期只有 DeepSeek
- 必须提供 Mock LLM，用于无 Key、无网络、流程调试和 Harness 回归
- 通过统一 Provider 接口封装，后期可扩展其他模型

## 十、Power BI MCP

- 后端统一连接 Power BI MCP，网页用户不配置 MCP
- 前期使用项目负责人的 Microsoft 账号和个人数据

## 十一、记忆系统

- 记忆系统是核心卖点
- 必须包含结构化工作记忆和可靠的提交机制
- 切换语义模型时清空旧模型相关上下文

## 十二、固定模板报表

- 报表只能使用固定模板
- LLM 输出结构化 ReportSpec，由程序渲染 HTML
- 禁止 LLM 执行任意代码或生成自由 HTML

## 十三、Harness

- MVP 采用轻量控制面
- 必须约束：工具白名单、上下文边界、生命周期、结构化输出验证、记忆提交、Trace

## 十四、MVP 不做事项

- 不使用 LangGraph
- 不使用多 Agent
- 不处理多租户
- 不处理复杂用户权限
- 不处理 Power BI RLS
- 不支持跨语义模型查询
- 不支持用户自定义 HTML 模板
- 不支持动态 Power BI 报表发布
- 不执行任意代码
- 不开发复杂后台管理页面
- 不使用 Docker（延后到真实后端链路跑通后）

## 十五、项目成功标准

1. 后端可以稳定连接 Power BI MCP
2. 可以读取指定语义模型的结构
3. 用户可以通过自然语言查询真实 Power BI 数据
4. 返回的核心数值与 Power BI 中的数据一致
5. 支持基本多轮追问和筛选条件继承
6. 可以使用固定模板生成静态 HTML 报表
7. LLM 无法执行任意代码或绕过工具白名单
8. 关键请求具备完整 Trace
9. Golden Cases 可以重复执行并输出测试结果
10. React 页面可以完成模型选择、模板选择、提问和结果展示

## 十六、开发环境约束

- 本地开发使用 `D:\Conda` 中的 Conda
- Conda 环境名称固定为 `PBIAgent`
- Python 版本固定为 3.11
- 不在业务代码中硬编码 `D:\Conda`、环境绝对路径、用户目录或项目绝对路径
- 不在 base 环境安装项目依赖

## 十七、文档来源优先级

1. 用户最新明确要求
2. PROJECT_CHARTER.md（本文件）
3. docs/00_product_requirements_document.md（正式 PRD）
4. 已确认 ADR
5. 正式设计文档
6. docs/09_context_handoff.md 中的当前状态
7. `docs/archive/original/PRD.md`（仅作历史参考，不直接指导开发）
8. Claude 的可逆默认假设

文件之间出现冲突时，按优先级处理；无法判断时记录到待确认事项；不得静默改变产品方向。

**重要：** 原始 PRD（`docs/archive/original/PRD.md`）已降级为历史参考。正式 PRD（`docs/00_product_requirements_document.md`）是当前唯一需求基线。原始 PRD 与正式 PRD 冲突时，以正式 PRD 为准。不修改原始 PRD。

---

*最后更新：2026-08-14 | M2.6.4 Truth Boundary 与 PRD 路径同步*
