# M5.10.1 — Professional Sales Renderer & Real Visual Acceptance

## 状态与基线

- 状态：LOCAL ACCEPTANCE COMPLETE；exact-SHA CI pending
- 起始基线：`main@a47b74c4e211c431cd3bbaa98bef204d03aec517`
- M5.10：foundation COMPLETE
- M5.10.2：NOT STARTED
- M5 FINAL：false

## 唯一目标

把 `sales_executive_report` 从已登记但不可用的 COMPLEX identity，收口为第二个可生产使用的固定模板。它与 `sales_report` 共用 `SALES_QUERY_REQUIREMENTS`、CanonicalQueryPlan、deterministic DAX、QueryResult 与 VerifiedFactSet；差异只允许位于固定信息架构、布局、可视化和样式。

## Authority 与禁止项

- P0/P1/P2 参考图优先级固定为 Reading Context hard contract、主布局、视觉灵感；图片不拥有事实或功能 authority。
- COMPLEX Renderer 前必须具备完整且一致的 `ReportReadingContext` 与 `ReportDataSnapshot`。
- LLM 对 query、DAX、事实、指标口径、异常、刷新时间、HTML、CSS、SVG 的 authority 为 0。
- 不实现 YoY、MoM、Forecast、Budget、Target、Map、AI Insight、统计异常、PDF、JS、CDN、Remote MCP、Entra、PostgreSQL 或 Deployment。
- 不修改 QuestionRouter、Grounding/member、Deterministic DAX、VerifiedFactSet、Local MCP worker/retry/cancellation 或 persistence architecture。

## 顺序

1. 治理 P2 图片双扩展名并验证 blob 不变、旧引用为零。
2. 建立 Executive Renderer、Reading Context HTML、parity、template identity、frontend explicit-selection failure tests。
3. 实现独立 deterministic `ExecutiveSalesReportRenderer` 与自包含 UTF-8 HTML 模板。
4. 以现有 verified report data 构建 professional ReportSpec；scope/snapshot/Reading Context 只从 canonical + verified evidence 投影。
5. 建立 18 个 TEST_FIXTURE visual scenarios 与浏览器 geometry acceptance。
6. 执行 Simple/Executive deterministic 与 Real PBIX factual parity。
7. 执行四项 mutation sanity；恢复全部 mutation。
8. 无 unresolved P0/P1/P2 后才将 executive descriptor 切为 AVAILABLE、注册 renderer，并让后端 catalog/前端公开第二模板。
9. 记录 planning/query/assembly/render/HTML size；完成 fresh gates、Real Browser、Real PBIX 与 residual=0。
10. 同步文档与 Settings.version，白名单提交、push main，并等待 exact-SHA CI success。

## 完成证据

完成必须同时具备：focused/report/frontend/full/golden/semantic/governance gates；1440/1024/768/430 真实浏览器 geometry；长产品/客户、60 点趋势、多筛选、unknown freshness 与 missing-section 自适应；Simple/Executive exact factual parity；Simple/Rich PBIX 正式链；mutation sanity；clean worktree、local main=origin/main、`.env` untouched、residual=0 与 exact-SHA Windows CI success。

提交前 fresh local evidence：

- report/template/API focused `96 passed`；backend full `2650 passed, 1 skipped`；Semantic Compatibility `775 passed` / 121 production backend files；Golden `11 passed, 1 manual-real skipped`。
- frontend Vitest `91 passed`，typecheck、lint、production build 全部 PASS；compileall PASS。
- 18 个 fixture 全部为静态 HTML；renderer p50 `1.447ms`、max `4.483ms`、最大 HTML `30,801 bytes`，低于 `500ms / 500KB` 门槛。
- 18 × 4 viewport = `72/72` 真实 Chrome geometry PASS；overflow mutation 为 `72/72` expected FAIL，恢复后重新 `72/72` PASS。
- Rich PBIX 9/9 与 Simple PBIX 4 个 runtime-available requirements 均经 Local MCP → deterministic DAX → Layer 3 → QueryResult → VerifiedFactSet；Simple/Executive parity=true，关闭后 `session_residual=0`、`active_workers=0`。
- P0 Reading Context、overflow、Renderer miswire、TopCustomer fact mapping 四项 mutation 均先红后恢复；破坏代码未保留。
- Repository Safety `390`、Architecture `138`、AI Error Ledger `82`、Documentation/Artifact Governance、compileall 与 staged diff-check 全部 PASS。

## 开头治理记录

`docs/assets/reports/03_sales_executive_visual_style.png.png` 已纯重命名为 `03_sales_executive_visual_style.png`。重命名前后 Git blob 均为 `cbe51680d2d85239f59a19ee130c6d4143ec9411`；图片内容未修改，旧文件名仓库引用为零，Documentation Governance PASS。
