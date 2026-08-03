# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-03 | M1.4.1 真实性验证与Smoke验收修复**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

前端最终为带左侧栏的 GPT 式极简对话网页（React + Vite，M5 开发）。

## 当前阶段

**M1.4.1 真实性验证与Smoke验收修复** — ✅ 已完成。

## 上一轮

**M1.4** — 真实 Answer 与 ReportSpec 生成（Commit `4b1f0a3`）

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
| M1.3.2 | 前端视觉与结构化回答契约固化 | `db0a7e8` | 2026-08-03 |
| M1.4 | 真实Answer与ReportSpec生成 | `4b1f0a3` | 2026-08-03 |
| M1.4.1 | 真实性验证与Smoke验收修复 | 本轮提交 | 2026-08-03 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## M1.4.1 交付内容

### P0 修复
- **KPI 列顺序**：`_validate_kpis_strict` 从 set 枚举改为有序列映射 + column_name→index 字典
- **Answer 强制绑定**：`semantic_model_key` 必须非空且匹配 QueryResult
- **Report 强制绑定**：`data_source` 必须非空且匹配 QueryResult
- **KPI None/bool**：None 和 bool 被明确拒绝，不允许作为合法 KPI 数值
- **Metrics provenance**：metrics 非空时 evidence 必须包含 `metric_provenance`（direct/sum/avg/count/min/max），旧自由文本不再放行
- **QueryPlan 模板 Key 契约**：`requested_template` 只能输出 sales_weekly/satisfaction/operating_overview 或 null，中文名称在 Prompt 中映射到内部 Key
- **模板非法修复**：非法 template_key 触发 QueryPlan 一次修复，Provider 最多调用 2 次
- **模板冲突**：显式 template_key 与 QueryPlan.requested_template 不一致时零次 ReportSpec 调用
- **空权限**：allowed_templates 为空集合时拒绝所有模板（不错误回退默认）
- **Table 类型严格**：`_safe_repr` 返回 type_tag 元组区分 None/bool/int/float/str/other
- **Smoke 加固**：所有关键条件参与 success 判定，dax_safe/renderer_ok 失败时 success=false
- **Token 统计**：Intent 纳入 Token 和 repair_count 统计，各阶段独立追踪

### 真实 Smoke 结果
- 总体 success=true，model=deepseek-chat，total_tokens=8570
- Case A（数据问答）：answer_repairs=0，evidence_bound=true，metrics_provenance_valid=true
- Case B（报表生成）：spec_repairs=0，qp_requested_template=sales_weekly，template_consistent=true

### 测试结果
- pytest：936 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（134 文件）

### 运行边界
- Settings.version=M1.4.1
- QueryResult 仍为 Mock
- Renderer 仍为 Mock
- DeepSeek Chat 仍 503
- 真实 Power BI 属 M2

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
- 安全扫描：PASS

### 运行边界
- Settings.version=M1.4
- QueryResult 仍为 Mock
- Renderer 仍为 Mock
- DeepSeek Chat 仍 503
- 真实 Power BI 属 M2

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

*最后更新：2026-08-03 | M1.4.1 真实性验证与Smoke验收修复*
