# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答”现在是什么、下一步做什么”。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-17

## 当前阶段

**M3.4 — Adaptive Report Planning + Visualization & Layout Policy 已完成。**

- M0—M2 Final Seal：`m2.6.4-m0-m2-final-seal` → `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。
- M3.0：`e4b5c6c6a759cdf22c74c4d87902482563e27cad`，main CI `31986207118` success。
- M3.1：`fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57`，main CI `31989328261` success。
- M3.2 / M3.3 直接在 `main` 完成；M3.4 在 `main` 完成 Adaptive Report Planning：schema-aware capability engine、ReportPlan、Visualization/Layout/Theme Policy、ReportSpec 图表支持、双模型 Real acceptance。M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）。

CI truth 必须分开描述：dev push 不代表 CI；当前 GitHub workflow 只覆盖 main push、PR → main 与 workflow_dispatch。本地 pytest/Golden/gates、Real Power BI smoke 与 GitHub CI 是三类独立证据。

## 当前正式报表链

```text
Natural Language
→ Intent / constrained language understanding
→ Template grounding（sales_report）
→ Bounded Report Intent weak signal（registry-owned ID only，可选 LLM）
→ deterministic ReportPlanner（NL signal ∩ runtime capability ∩ catalog）
→ Canonical ReportPlan（requested / resolved / unavailable sections）
→ query requirements（resolved sections 去重）
→ N × CanonicalQueryPlan（M2 密封链）
→ N × Deterministic DAX → N × Independent Layer 3
→ N × ToolGateway → PowerBIAdapter → Power BI
→ N × QueryResult → N × VerifiedFactSet
→ fact-level re-gate（空结果 section 丢弃，不渲染）
→ deterministic SalesReportData
→ deterministic ReportSpec（KPI + charts，VisualizationPolicy 选 visual）
→ SalesReportRenderer（Layout/Theme Policy，design system）
→ static UTF-8 HTML → ReportArtifact → ReportRepository
→ report_id / view / download
→ Memory / Snapshot
```

TurnPipeline 仍是唯一控制面；Renderer 仍经 ToolGateway；ReportRepository 只管理当前 M3 artifact，不形成 M4 persistence。

## M3.4 核心变更（ADR-011）

ADR-010 的固定事实安全边界继续有效；"一个 template 永久绑定一个 model fingerprint + 固定四 queries"的限制由 **ADR-011** supersede。固定模板 = 固定设计规则 + 允许能力目录，不是固定输出内容。

- `backend/app/report/capability.py`：真正的 schema-aware capability engine。9 个 registry-owned sections（SALES_KPI / QUANTITY_KPI / ORDERS_KPI / AOV_KPI / TIME_TREND / CATEGORY_CONTRIBUTION / REGION_COMPARISON / TOP_PRODUCTS / TOP_CUSTOMERS）；section 必须满足 TemplateContract 声明 + runtime schema 对象与类型 + 已验证非空事实，缺一即 UNAVAILABLE（不 Mock、不补数据、不生成空图）。
- `backend/app/report/contracts.py`：TemplateContract 变为允许能力目录（contract version 2.0），schema 对象检查下沉到逐需求级别（`RequirementAvailability`）；`ReportDataPlanBuilder.build(..., requirement_keys=...)` 只构建请求子集。
- `backend/app/report/intent.py` + `deepseek_report_intent_service.py`：受控 Report Intent。LLM 只输出 registry-owned ID（weak signal），未知 ID 丢弃；确定性 NL 匹配器是地板；"只看…"忽略 LLM 增量；计数 `llm_report_intent_call_count`，与事实类计数分开。
- `backend/app/report/plan.py`：deterministic ReportPlan（requested / resolved / unavailable sections、去重 query requirements、provenance）。请求为零可解析 section → fail closed。
- `backend/app/report/policy.py`：VisualizationPolicy（KPI Card / Line / Donut≤8 / Column / HBar，禁止全部 grouped→hbar）、LayoutPolicy（KPI 行 → 全宽趋势 → 2 列对比/排行对）、ThemePolicy（dataviz 验证调色板、系统字体、间距 token）。
- `backend/app/report/assembly.py`：通用多 section 装配（保留全部防篡改：FactSet 重建、mixed source、id 复用、排名伪造）；trend 只做已验证时间点显示排序，不创造数值。
- `backend/app/report/fixed.py`：`SalesReportRenderer`（原 FixedSalesReportRenderer 更名）；渲染 KPI cards、inline SVG line/donut、CSS column/hbar；无 JS/CDN/外部资源；空 section 一律不输出。
- `backend/app/schemas/data_contracts.py`：`CanonicalQueryPlan.dimension_tables` / `dimension_order`（最小通用扩展，None=M2 原行为）；ChartSpec 增加 `visual_type` / `business_role` / `series` / `layout_hint`（结构化，无 HTML/CSS/可执行配置）。`LLMTask.REPORT_INTENT` 独立计数。
- DeterministicDAXBuilder / Layer 2 validator / RestrictedDAXVerifier：支持确定性表归属 hint（star-schema 重名列消歧，如 Sales[Region] vs Region[Region]）。

## `sales_report` 能力目录与数据范围

当前报表针对整个 PBIX 全量数据，不接受动态月份、Category filter、comparison 或任意 DAX；每个查询仍复用 M2 封板链。

| Requirement | Measure | Dimension（表） | Sort / TopN | 所属 section |
|---|---|---|---|---|
| `total_sales` | Total Sales | — | — | sales_kpi |
| `total_quantity` | Total Quantity | — | — | quantity_kpi |
| `total_orders` | Total Orders | — | — | orders_kpi |
| `average_order_value` | Average Order Value | — | — | aov_kpi |
| `monthly_sales` | Total Sales | YearMonth（Date，display asc） | — | time_trend |
| `sales_by_category` | Total Sales | Category（Sales） | — | category_contribution |
| `sales_by_region` | Total Sales | Region（Sales） | — | region_comparison |
| `top_products` | Total Sales | Product（Sales） | desc / 5 | top_products |
| `top_customers` | Total Sales | Customer（Sales） | desc / 5 | top_customers |

TopN 只保留 `result_position` / QueryResult order；ties 可使结果超过 5 行，不声明严格 business rank。

## 自然语言 → section 映射（确定性）

| 用户输入 | requested sections |
|---|---|
| 只看销售额 | sales_kpi（最小单主题报表） |
| 看看销售趋势 | sales_kpi + time_trend |
| 按区域看销售表现 | sales_kpi + region_comparison |
| 看看头部客户 | sales_kpi + top_customers |
| 生成完整销售分析报表 | 全部 9 个（实际解析由 runtime schema 决定） |
| 无明确分析目标 | 默认完整请求 |

Simple PBIX（仅 Sales 表 + 两个 measure）完整请求解析为 4 sections / 4 queries，与 M3 基线行为一致；缺 Region/Customer/Date/Orders/AOV 能力 → 对应 section UNAVAILABLE，绝不 Mock。

## 当前实现

- 完整能力布局（Rich 全量时）：Header → 4 KPI → 全宽月度销售趋势 Line → 2 列 品类 Donut | 区域 Column → 2 列 Top 5 产品 HBar | Top 5 客户 HBar → Footer metadata。实际解析少时自动成为简洁单主题报表，无空 section。
- 视觉由普通代码选择：business role + data shape + cardinality（donut ≤ 8 slices，品类少）；不全是 horizontal bars。
- 无 JS / CDN / external resources；允许确定性 inline SVG（line/donut），全部 HTML escape、无可执行内容。
- LLM 唯一新增：report-intent weak signal（registry ID 列表），单独计数；DAX/ReportData/Report factual/Renderer 的 LLM authority 仍为 0。

## Fail-closed / anti-bypass

- 缺任一 resolved query/FactSet、错误 FactSet binding、mixed source、空必需结果、重复 result/fact ID、伪造 KPI/grouped/TopN order 均拒绝。
- unknown/legacy template 继续 fail closed；未知 requirement key / 不可用 requirement 拒绝。
- LLM draft 的未知/非法 section ID 丢弃；请求全不可用 → 无报表（fail closed）。
- Renderer 拒绝非 `sales_report`、结构/provenance 不完整、未注册 role/visual、重复 role、KPI role 冒充 chart 的 ReportSpec。
- 所有动态文本 HTML escape；保存前拒绝 active script、external URL、非完整 HTML，以及 `link` / `iframe` / `object` / `embed` / `@import` / `url()` / `src=`。
- report_id 只接受 repository-owned `rpt_<uuidhex>`；任意路径与 unknown ID → 404。
- render/store failure 返回失败并把 pending Memory 标记 FAILED；不提交成功 Memory。
- 生产报表代码不含本地 oracle，不构造 fake QueryResult，不从 expected 构造 actual。

## M3.4 测试矩阵

- `backend/tests/unit/test_report_contract.py`：能力目录、逐需求 availability、subset plan、未知/不可用 requirement fail closed、module authority scan。
- `backend/tests/unit/test_report_generation.py`：装配/渲染/资源全链路 anti-fake（含 forged FactSet、mixed source、重复 visual、HTML escape、hash/view/download、idempotent replay）。
- `backend/tests/unit/test_report_adaptive.py`：5 个 NL cases × Simple/Rich schema、missing capability synthetic fixtures、LLM weak-signal 边界（unknown ID 丢弃、只看→忽略增量、失败回退）、fact-gate 空结果 drop、planning modules 无 LLM/PowerBI/oracle。
- `backend/tests/unit/test_deterministic_dax.py`：`dimension_tables` 表归属 hint 的 builder/Layer2/Layer3 一致性。

## M3 PBIX Real acceptance

### Simple（PowerBIAgent_M3_Test.pbix，M3 baseline）

- semantic model：`local_desktop_model`；fingerprint `d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac`。
- 完整请求解析 4 sections / 4 真实查询，全部非空；`source_mode=real`。
- scalar oracle：Total Sales `500821`、Total Quantity `358`（只用于 CLI acceptance 比较）。
- DAX LLM=0、ReportData LLM=0、Report factual LLM=0、Renderer LLM=0、fallback=0、fake QueryResult=0、report-intent LLM=0（smoke 直接驱动确定性链）。

### Rich（PowerBIAgent_M3_Rich_Test.pbix，M3.4 新增）

- semantic model：`local_desktop_model`；fingerprint `31505f7987133c235554bc00e7ca5ce3fd42351b08e984c0c011f48410e56157`。
- 完整请求解析 9 sections / 9 真实查询（含 monthly trend 15 点、3 品类、4 区域、Top 5 产品、Top 5 客户），全部非空；`source_mode=real`。
- scalar oracle：Total Sales `6943997.509999986`、Total Quantity `3065`、Total Orders `800`、Average Order Value `8679.996887499983`。
- visual types：line / donut / column / hbar；HTML 无 table/script/link；hash 一致；view/download 200。
- 全部事实类 LLM counters = 0；report-intent LLM = 0（smoke 无 LLM provider）。
- 受管 artifact 与固定验收副本逐字节一致（Simple → `local_state/reports/m3_sales_report.html`，Rich → `local_state/reports/m3_rich_report.html`）；禁止提交。

## Acceptance 状态（M3.4 fresh）

- Backend pytest：1477 passed。
- Golden（`python -m backend.app.harness.cases`）：11 PASS / 1 manual Real baseline skip；0 FAIL / 0 ERROR。
- Architecture Gate、Repository Safety、Error Ledger、Documentation Governance、`git diff --check`：PASS。
- Real full report smoke：Simple / Rich 双模型 PASS；oracle/source/hash/API/gitignore counters 全部通过。
- 视觉：桌面 1024px 与 430px 窄屏 headless 截图已产出（`local_state/visual/`：rich_desktop.png / rich_narrow.png / simple_desktop.png），程序化 DOM/几何检查 PASS（Rich 5 sections、4 KPI、donut sum 100%、line 15 点、无 table/script、响应式 media rules 存在；Simple 2 charts donut+hbar）；**用户人工视觉验收 PASS**。

## 关键命令

```powershell
# Targeted
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests\unit\test_report_contract.py backend\tests\unit\test_report_generation.py backend\tests\unit\test_report_adaptive.py backend\tests\unit\test_deterministic_dax.py -q

# Full offline + governance
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py

# M3.4 Real smoke（Power BI Desktop 需打开对应 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\sales_report_contract_smoke.py `
  --model simple --expected-total-sales 500821 --expected-total-quantity 358
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\sales_report_contract_smoke.py `
  --model rich --expected-total-sales 6943997.509999986 --expected-total-quantity 3065 `
  --expected-total-orders 800 --expected-average-order-value 8679.996887499983
```

## 下一步

M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）。后续轮次必须从 `AGENTS.md` Cold Start，重新取得 fresh tests/Real/CI 证据。不进入 M4/M5、不开发 Remote MCP；只有用户另行明确授权后才可继续。

---

*最后更新：2026-08-18 | M0—M3 Final Seal — M3.4 Adaptive Report Planning + Visualization/Layout Policy*
