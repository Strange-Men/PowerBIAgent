# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答“现在是什么、下一步做什么”。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-17

## 当前阶段

**M3.0 — Report Architecture + Sales Contract Baseline**。M0—M2 已由 `m2.6.4-m0-m2-final-seal` 正式封板，Tag 与 `main` 均指向 `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。

当前分支为 `dev/m3.0-report-contract`。M3.0 已实现并 fresh 验收 `sales_report` TemplateContract、M3 PBIX schema binding、availability/compatibility validator、固定四查询 ReportDataPlan、反绕链单测与 Real contract smoke。下一步只允许 Commit/Push 后等待远程审计；不得进入 M3.1、merge main 或创建 Tag。

## 当前 M3 架构与 Truth Boundary

```text
Natural Language
→ Intent / Template Grounding
→ Semantic Grounding
→ TemplateContract + runtime schema compatibility
→ deterministic ReportDataPlan
→ Canonical QueryPlan（每个 sub-query）
→ Deterministic DAX
→ Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet（每个 sub-query）
→ deterministic Report Data Contract（M3.1）
→ deterministic ReportSpec（M3.1）
→ Fixed Renderer（M3.1）
→ static HTML
```

- ADR-005：TurnPipeline 仍是唯一确定性控制面。
- ADR-008：runtime schema/Catalog/Grounding 仍拥有 canonical business semantics。
- ADR-009：Real DAX、Layer 3 与 VerifiedFactSet authority 不变；Real failure 不回退 Mock。
- ADR-010：M3 production template 只有 `sales_report`；TemplateContract 固定 schema binding 与四查询，ReportDataPlan 不读取 LLM draft。
- LLM 对 template canonical authority、查询集合、DAX、KPI/rows、排名、趋势、因果、Report factual truth、HTML/CSS 的 authority 均为 0。

## `sales_report` 固定合同

| Requirement | Measure | Dimension | Sort / TopN |
|---|---|---|---|
| `total_sales` | Total Sales | — | — |
| `total_quantity` | Total Quantity | — | — |
| `sales_by_category` | Total Sales | Category | — |
| `top_products` | Total Sales | Product | desc / 5 |

固定 metadata：数据来源、筛选条件、时间范围、生成时间。缺任一必需 Measure/field/type 或 fingerprint mismatch 时整个 ReportDataPlan fail closed，不生成 partial/fake section。

## M3 专用 Real PBIX 基线

- 本地文件：`demo_data/PowerBIAgent_M3_Test.pbix`；gitignored，只用于 M3 acceptance，不替换 M2 封板 PBIX。
- semantic model key：`local_desktop_model`。
- bound fingerprint：`d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac`。
- 可见 `Sales` fields/types：OrderID/OrderDate/Quantity=`Int64`，Category/Product=`String`，UnitPrice/SalesAmount=`Double`。
- Measures/types：Total Sales=`Double`，Total Quantity=`Int64`；expression 非空。
- Runtime `OrderDate` 如实为 `Int64`；M3.0 不伪装为 DateTime，也不扩展 M2 time grammar。
- Real smoke：四个固定 query 均经 Deterministic DAX + Independent Layer 3 + ToolGateway + Local Adapter + QueryResult + VerifiedFactSet；local scalar oracle 匹配，source real，fallback/LLM/Renderer=0。

## 当前实现与禁止范围

已实现：

- `backend/app/report/contracts.py`：TemplateContract、schema requirements/binding、validator、ReportDataPlanBuilder。
- production Catalog 仅 `sales_report` available；legacy template keys 显式 unavailable。
- `scripts/manual_smoke/sales_report_contract_smoke.py`：CLI oracle 与 actual 分离的只读 Real smoke。
- `backend/tests/unit/test_report_contract.py`：unknown/legacy/missing object/fingerprint/LLM-input/second-pipeline/hardcoded-result gates。

未实现且本轮禁止：

- 正式 Jinja2/Fixed Renderer、HTML 文件或 HTML 样式；
- report resource repository、report_id lifecycle、`GET /api/reports/*`、download endpoint；
- satisfaction/operating overview/其他 template；
- PDF、自由 HTML、JavaScript、用户模板、动态 Power BI Report、复杂图表框架；
- M4 persistence、M5 React、Remote MCP。

## Acceptance 状态

- Targeted contract/template tests：19 passed。
- M3 Real contract smoke：PASS；query_count=4、all nonempty、schema binding/actual scalar oracle/source mode 通过，fallback/LLM/Renderer=0。
- Fresh backend：1412 passed。
- Golden：11 PASS / 1 manual Real baseline skip；0 FAIL / 0 ERROR。
- Architecture Gate：PASS（86 个受管 Python 文件）。
- Repository Safety：PASS（193 个文件）；Error Ledger：PASS（25 entries）；Documentation Governance：PASS；`git diff --check`：PASS。

## 关键命令

```powershell
# Targeted
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests\unit\test_template_catalog.py backend\tests\unit\test_report_contract.py -q

# Full offline + governance
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py

# M3 Real（oracle 只由本地命令提供）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\sales_report_contract_smoke.py `
  --expected-total-sales <local-oracle> `
  --expected-total-quantity <local-oracle>
```

## 固定基线与 Git

| 项目 | 值 |
|---|---|
| M0—M2 Final Seal | `m2.6.4-m0-m2-final-seal` → `70748da` |
| M3.0 source branch | `dev/m3.0-report-contract` |
| M3.0 commit | Commit 后仅在最终报告记录，不回填本文档 |
| 本轮 Tag | **none；禁止创建** |

## 下一步

白名单暂存、提交 `M3.0_销售报表合同与开发路线固化` 并 push `dev/m3.0-report-contract`，随后停止等待 GPT 远程审计。只有用户另行批准后才能进入 M3.1。

---

*最后更新：2026-08-17 | M3.0 sales_report contract baseline；M3.1 未开始*
