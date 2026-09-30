# M5.10.7 — Schema-aware Template Eligibility + Typed Failure + Recovery UX

> **Historical — governance 2026-09-30：** 本文件保存当时设计、计划和分层 evidence，旧 current/pending/FINAL=false 不是今日状态；当前状态见 [07](../../07_milestones_status_and_open_questions.md)、[08](../../08_development_roadmap.md)、[09](../../09_context_handoff.md)。
> **Completed by：** 后续 M5.10.8 + FIX release/用户 UI Smoke；原 189edc6 的 frontend lint failure 与当时 pending 不删除。


## 状态与范围

M5.10.7 implementation 已完成，等待用户人工验收；`M5 FINAL=false`。本阶段只收口当前 Power BI 语义模型下的报表模板可用性，以及失败后的稳定恢复提示。M5.10.8、报表视觉重构、新模板、新 QueryShape、新业务数学、MCP/Provider 改写与数据库 migration 均不在范围内。

## 合同

- `GET /api/v1/report-templates?semantic_model_key=...` 只经 `ToolGateway → PowerBIAdapter` 读取当前 runtime schema，复用 `ReportTemplateRegistry`、`ReportContractValidator` 和既有 section capability 计算；不执行 DAX，不调用 LLM，不生成 ReportPlan。
- 每个已登记模板返回 `compatible | partial | incompatible | unavailable`、`selectable`、可用/总 section 数和稳定 reason code。`partial` 可选择；`incompatible` 与 `unavailable` 可见但禁用。
- 模型切换会失效旧目录请求；只在模板对新模型仍 `compatible/partial` 时保留选择。旧模型晚到响应不得覆盖当前状态，未完成兼容性确认的模板不得随消息发送。
- 后端以 `FailureInfo(code, stage, retryable, recovery_action)` 为唯一公开失败控制面；内部 exception message、trace 与 provider diagnostic 不进入用户文案。前端以 `failure.code` 映射固定安全中文提示，旧 `error_type` 只保留精确兼容映射，不再使用 `startswith/includes` 猜错。
- 报表执行或渲染失败保留当前模型与模板，允许直接重试；模板失效清空模板，stale model 清空模型。历史恢复继续使用同一 typed failure。

## 验收

- failure-first 覆盖 full / partial / none / unavailable，目录发现 ZERO DAX；覆盖 renderer、Power BI disconnect、stale model、LLM provider、timeout 与 legacy exact fallback。
- 前端覆盖模型切换、兼容模板保留、不兼容模板清空、stale response 防护、不可用 option、ARIA error/status 和历史恢复。
- Local Real 仅执行 2 模板 × DeepSeek/Kimi 的限定矩阵，并附 M5.10.6 小型 smoke；不运行完整 backend/frontend suite 或大规模 stress。
- 发布采用 main-only、白名单 staging、固定提交名、push 后只记录自动 CI Run ID/head SHA。用户人工验收与 M5.10.8 完成前不得声明 `M5 FINAL=true`。
