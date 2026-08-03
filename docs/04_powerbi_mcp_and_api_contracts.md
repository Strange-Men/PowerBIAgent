# 04 — Power BI MCP 与 API 契约

> **状态：** M0.3 实质性完成
> **关联 ADR：** ADR-003

---

## 一、PowerBIAdapter 设计

### 1.1 接口（`backend/app/powerbi/base.py`）

| 方法 | 说明 |
|------|------|
| `health_check()` | 连接健康检查 |
| `get_semantic_model_schema(key)` | 获取语义模型结构 |
| `execute_dax(DAXRequest)` | 执行 DAX 查询 |
| `normalize_result(raw)` | 标准化原始响应 |
| `normalize_error(raw)` | 标准化原始错误 |

### 1.2 MockPowerBIAdapter（`backend/app/powerbi/mock.py`）

- 从 `harness/fixtures/` 加载 Mock Schema 和 QueryResult
- 不依赖网络和 Microsoft 账号
- 严格匹配 scenario_key，未知场景明确失败
- 支持模拟：正常数据、空数据、超时、无权限、DAX 错误、超大结果

### 1.3 RemoteMCPPowerBIAdapter（`backend/app/powerbi/remote_mcp.py`）

- M0.3 仅骨架，所有真实调用标记 `NotImplementedError("TODO: M2")`
- 配置边界完整：Server URL、Tenant ID、Client ID、超时、重试

## 二、OAuth 认证风险（ADR-003）

### 关键发现

1. **VS Code 能访问 ≠ 自定义客户端能访问** — VS Code 有微软预注册的 Client ID
2. **必须手动注册 Entra Application** — 需要 Azure 管理员权限
3. **需要 Power BI 管理员启用 Tenant 设置**
4. **早期 2026 年有 Remote MCP 端点中断报告**

### 授权流程

- M2: MSAL device code flow + 本地 token 缓存
- Token 获取、刷新和存储由 Adapter 内部管理
- 不暴露 Token 到 Agent 或业务层

## 三、核心数据契约（`backend/app/schemas/data_contracts.py`）

### QueryPlan
normalized_question, semantic_model_key, measures, dimensions, filters (StructuredFilter), time_range, sort, top_n, comparison_mode, requested_template, inherited_context, is_mock

### DAXRequest
semantic_model_key, dax, max_rows, timeout_seconds, request_id, is_mock

### QueryResult
semantic_model_key, columns, rows, row_count, execution_time_ms, source_mode, request_id, error (PowerBIError), truncated

内置一致性校验：row_count vs rows 长度、每行字段 vs columns 数量

### AnswerSpec
answer, summary, metrics, evidence, filters, semantic_model_key, source_mode, generated_at

### ReportSpec
title, template_key, summary, kpis (KPISpec), charts (ChartSpec), tables (TableSpec), insights, data_source, filters, generated_at, source_mode

禁止任意 HTML、JavaScript、外部脚本、未登记模板、不存在字段

### UserContext
user_id, roles, allowed_semantic_models, allowed_templates, allowed_tools

## 四、只读 DAX 安全

- 仅允许：EVALUATE、DEFINE + EVALUATE
- 禁止：SQL、写操作、跨模型引用、Python/Shell/PowerShell/JavaScript
- 安全边界来自：ToolGateway、ValidationService、semantic_model_key 白名单、Schema 字段验证、最大行数、超时、最大重试

## 五、M0.3/M2/M3 边界

| 项目 | M0.3 | M2 | M3 |
|------|------|----|----|
| PowerBIAdapter 接口 | ✅ | — | — |
| MockPowerBIAdapter | ✅ 可运行 | — | — |
| Remote Adapter | ✅ 骨架 | ✅ 真实连接 | — |
| API 数据契约 | ✅ 全部 Pydantic | — | — |
| OAuth/Token | ✅ 设计文档 | ✅ 实现 | — |
| 真实 DAX 查询 | ❌ | ✅ | — |
| ReportSpec Schema | ✅ 完整 | — | — |
| 生产报表模板/HTML | ❌ | ❌ | ✅ |

---

*最后更新：2026-08-03 | M1.3 真实QueryPlan与DAX生成*
