# 04 — Power BI MCP 与 API 契约

> **状态：** M0.1 骨架已建立
> **下一轮实质性填充：** M0.3（Power BI MCP 连接验证）
> **警告：** 本文当前仅为骨架，尚未完成的技术决策不得用于指导开发

---

## 一、Power BI MCP Adapter

### 1.1 职责

- 连接 Power BI MCP Server
- 获取可用语义模型列表
- 获取语义模型结构（表、字段、度量值、关系）
- 执行 DAX 查询
- 统一处理 MCP 返回结果
- 处理连接异常和查询错误

### 1.2 MVP 配置

- 使用项目负责人的 Microsoft 账号登录
- 访问负责人的个人 Power BI 数据
- 不处理多用户权限和 RLS

### 1.3 待设计内容 (M0.3)

- MCP Client 实现方案
- Microsoft 认证流程
- 连接健康检查
- DAX 模板和生成策略
- 查询结果标准化
- 错误处理和重试策略
- 数据量限制

## 二、API 契约概要

### 2.1 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/semantic-models` | 语义模型列表 |
| GET | `/api/report-templates` | 报表模板列表 |
| POST | `/api/chat` | 对话请求 |
| GET | `/api/reports/{report_id}` | 获取报表 |

### 2.2 待设计内容 (M0.3-M0.4)

- 完整 Request/Response Schema
- 错误码体系
- SSE 流式响应设计
- 分页和限流策略

## 三、报表生成

### 3.1 ReportSpec 概要

LLM 输出 ReportSpec，由后端校验后渲染：

| 字段 | 说明 |
|------|------|
| title | 报表标题 |
| summary | 摘要分析 |
| kpis | KPI 列表 |
| charts | 图表配置（类型、字段） |
| tables | 表格配置（列、数据） |
| conclusions | 分析结论 |

### 3.2 固定模板

- 销售周报模板
- 满意度报告模板
- 经营分析模板

### 3.3 待设计内容 (M3)

- ReportSpec 完整 Schema
- Jinja2 模板结构
- HTML 渲染管线
- 模板注册和发现机制

## 四、模块边界

### 本轮 (M0.1) 边界

- 仅建立骨架
- 不实现任何 MCP 连接
- 不定义具体 API Schema
- 不设计报表模板

### M0.3 边界

- 完成 Power BI MCP 连接和验证
- 完成 API 契约详细定义
- 不实现报表生成（M3）

---

*创建日期：2026-07-31 | M0.1 仓库初始化与文档基线*
