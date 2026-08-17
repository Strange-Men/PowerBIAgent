# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答“现在是什么、下一步做什么”。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-17

## 当前阶段

**M3.2 — Hardened Sales Report Visual Acceptance 已完成；M3 final closure。**

- M0—M2 Final Seal：`m2.6.4-m0-m2-final-seal` → `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。
- M3.0：`e4b5c6c6a759cdf22c74c4d87902482563e27cad`，GPT remote audit PASS；已从 M2 seal 纯 fast-forward 合入 main。
- M3.0 main CI：`PowerBIAgent Validation` run `31986207118`，head SHA 与 M3.0 commit 一致，`success`。
- M3.1：`fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57`，GPT remote audit PASS；已从 M3.0 纯 fast-forward 合入 main。
- M3.1 main CI：`PowerBIAgent Validation` run `31989328261`，head SHA 与 M3.1 commit 一致，`success`；本地与远程开发分支已删除。
- M3.2 直接在 `main` 完成 hardened acceptance；不创建新分支或 Tag，不进入 M4/M5/Remote MCP。

CI truth 必须分开描述：dev push 不代表 CI；当前 GitHub workflow 只覆盖 main push、PR → main 与 workflow_dispatch。本地 pytest/Golden/gates、Real Power BI smoke 与 GitHub CI 是三类独立证据。

## 当前正式报表链

```text
Natural Language / Template Grounding
→ TemplateContract
→ runtime schema validation
→ deterministic ReportDataPlan
→ 4 × CanonicalQueryPlan
→ 4 × Deterministic DAX
→ 4 × Independent Layer 3
→ 4 × ToolGateway → PowerBIAdapter → Power BI
→ 4 × QueryResult
→ 4 × VerifiedFactSet
→ deterministic SalesReportData
→ deterministic ReportSpec
→ FixedSalesReportRenderer
→ static UTF-8 HTML
→ ReportArtifact → ReportRepository
→ report_id / view / download
→ Memory / Snapshot
```

TurnPipeline 仍是唯一控制面；Renderer 仍经 ToolGateway；ReportRepository 只管理当前 M3 artifact，不形成 M4 persistence。

## `sales_report` 固定合同与数据范围

当前报表针对整个 M3 PBIX 全量数据，不接受动态月份、Category filter、comparison、趋势、用户自由 ReportDataPlan 或任意 DAX。

| Requirement | Measure | Dimension | Sort / TopN |
|---|---|---|---|
| `total_sales` | Total Sales | — | — |
| `total_quantity` | Total Quantity | — | — |
| `sales_by_category` | Total Sales | Category | — |
| `top_products` | Total Sales | Product | desc / 5 |

TopN 只保留 `result_position` / QueryResult order；ties 可使结果超过 5 行，不声明严格 business rank。

## 当前实现

- `backend/app/report/contracts.py`：TemplateContract、schema binding、validator、ReportDataPlan。
- `backend/app/report/assembly.py`：`SalesReportDataAssembler` 与 `SalesReportSpecBuilder`；四组 FactSet 必须与 QueryResult/plan 重建结果完全一致。
- `backend/app/report/fixed.py` + `templates/sales_report.html`：唯一 production Renderer；Category / Top Product 横条宽度由同组已验证值确定性归一化，保留实际值与同源表格；固定 HTML/CSS、UTF-8、无 JS/CDN/外部资源/自由 HTML，动态值 escape。
- `backend/app/report/resources.py`：`ReportArtifact`、内存/本地 Repository、SHA-256 与原子写入；本地根目录固定 `local_state/reports/`。
- `backend/app/application/deepseek_turn_service.py`：在同一 active TurnPipeline 内执行固定四查询；ReportData/Report factual/Renderer 不调用 LLM。
- `backend/app/harness/tool_registry.py`：Renderer + repository store 仍封装在 `render_report` 白名单工具内。
- `backend/app/api/routes.py`：`GET /api/reports/{report_id}` 与 `/download`；只访问 app-scoped ReportRepository。
- Snapshot 保存 report reference/hash；同 request_id replay 返回同一 report_id，工具序列为空。

## Fail-closed / anti-bypass

- 缺任一 query/FactSet、错误 FactSet binding、mixed source、空必需结果、重复 result/fact ID、伪造 KPI/Category/Top Product order 均拒绝。
- unknown/legacy template、model/schema/fingerprint mismatch 继续由 M3.0 contract gate 拒绝。
- Renderer 拒绝非 `sales_report` 与结构/provenance 不完整的 ReportSpec。
- 所有动态文本 HTML escape；保存前拒绝 active script、external URL、非完整 HTML，以及 `link` / `iframe` / `object` / `embed` / `@import` / `url()` / `src=`。
- report_id 只接受 repository-owned `rpt_<uuidhex>`；任意路径与 unknown ID → 404。
- render/store failure 返回失败并把 pending Memory 标记 FAILED；不提交成功 Memory。
- 生产报表代码不含本地 oracle，不构造 fake QueryResult，不从 expected 构造 actual。

## M3 PBIX Real acceptance

- 文件：`demo_data/PowerBIAgent_M3_Test.pbix`；gitignored，未跟踪。
- semantic model：`local_desktop_model`。
- fingerprint：`d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac`。
- 四个真实 query 全部非空；`source_mode=real`。
- scalar oracle：Total Sales `500821`、Total Quantity `358`，只用于 CLI acceptance 比较。
- DAX LLM=0、ReportData LLM=0、Report factual LLM=0、Renderer LLM=0、fallback=0、fake QueryResult=0。
- 正式 artifact 与固定 acceptance copy 字节相同，content hash 验证通过；view/download 均为 200。
- 固定验收路径：`D:\AAA_Workfile\PowerBIAgent\local_state\reports\m3_sales_report.html`；禁止提交。
- M3.2 最终 smoke：report_id `rpt_f5b96ac8ec384d5580b47e9a6851981e`，HTML 10,230 bytes，SHA-256 `7144438843fae9a626e6122f4b936a2ff3fe2d973dc85c6e20c644f2ede6578d`；目录只保留该受管 artifact 与逐字节相同的验收副本。
- 同一 HTML 经禁止网络/脚本的静态 Renderer 实际渲染；桌面与 430px 窄屏视觉检查均 PASS，图表/表格值逐项对应，无重叠、截断或空组件。

## Acceptance 状态

- Prompt/report targeted：112 passed；report/contract/API targeted：96 passed。
- Fresh backend pytest：1435 passed。
- Golden：11 PASS / 1 manual Real baseline skip；0 FAIL / 0 ERROR。
- Architecture Gate、Repository Safety、Error Ledger、Documentation Governance、`git diff --check`：PASS。
- Real full report smoke：PASS；query_count=4、oracle/source/hash/API/gitignore counters 全部通过。

## 关键命令

```powershell
# Targeted
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests\unit\test_report_contract.py backend\tests\unit\test_report_generation.py backend\tests\api\test_chat.py -q

# Full offline + governance
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py

# M3.2 final Real；oracle 只作为 CLI 比较输入
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\sales_report_contract_smoke.py `
  --expected-total-sales <local-oracle> `
  --expected-total-quantity <local-oracle>
```

## 下一步

M3 已最终收口。停止开发，不继续扩展 M3，不创建 Tag；只有用户另行明确授权后才可规划 M4/M5 或重新评估 Remote MCP。后续轮次必须从 `AGENTS.md` Cold Start，并重新取得 fresh tests/Real/CI 证据，不能沿用本轮 PASS 数字。

---

*最后更新：2026-08-17 | M3.2 hardened visual acceptance；M3 final closure，无 Tag*
