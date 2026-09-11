# M5.10 — Complex Report Contract & Professional Sales Foundation

## 目标与边界

M5.10 固化复杂报表通用 Reading Context、第二个销售模板身份、共享 query requirements、freshness/metric/exception/source contracts。它不是专业视觉实现轮次，不实现 `sales_executive_report.html`、Executive Renderer、Remote MCP、YoY/MoM、Forecast、Target、Budget、Map、AI insight、PDF、JS dashboard 或交互筛选。

起始基线：`main@e6ac2ae8409d6cb83c605f089bc1a62a1aeaea4e`，与 `origin/main` 一致且工作树干净。

## 分阶段

1. 审计三张参考图和现有 Report Contract/Registry/Assembly/Renderer。
2. 先建立失败测试：tier、ReadingContext、freshness、metric、exception、shared authority、no fallback。
3. 最小实现 immutable contracts 与 dispatcher pre-render gate。
4. 注册 `sales_executive_report`，保持 `UNAVAILABLE` 且不注册 Renderer。
5. 抽取 `SALES_QUERY_REQUIREMENTS`，两个合同引用同一 requirement objects。
6. 运行 simple report focused regressions 与三个 mutation sanity。
7. 同步 ADR-019、Spec 14、资产说明、全局治理状态和 Settings.version。
8. 执行 Semantic、backend、Golden、frontend、治理、compileall、diff gates。
9. 白名单提交并 push main；以最终 SHA 的 Windows CI success 作为正式完成证据。

## 阶段关系

- **M5.10 = foundation：** 复杂报表合同和专业模板基础。
- **M5.10.1 = Professional Renderer + Real Visual Acceptance：** 当前未开始。
- **M5.10.2 = Report Hardening / Cloud-ready Final Closure：** 当前未开始。

## 完成语义

M5.10 的实现范围完成不等于专业模板已可用。只有 M5.10.1 完成 deterministic Renderer 和真实视觉验收后，才可将专业模板切为 AVAILABLE。只有后续全部 M5 门禁完成后才可声明 M5 FINAL。

## Fresh Evidence

- failure-first 新专项从缺失 imports/contracts 开始失败；最终 complex/report focused 172 PASS。
- mutation sanity：generated_at→data_updated_at、跳过 COMPLEX pre-render gate、executive requirement 漂移三项均使对应测试 FAIL；恢复后专项 24 PASS。
- Semantic Compatibility 774 PASS，扫描 120 个 production backend files。
- backend full 2620 PASS / 1 manual-real SKIP；Golden 11 PASS / 1 manual-real SKIP。
- frontend 90 PASS，typecheck/lint/production build PASS；本轮无 frontend source change。
- Repository Safety、AI Error Ledger、Architecture、Documentation/Artifact Governance、compileall 与 `git diff --check` PASS。
- Scope audit 仅包含 report/schema/template registry/contract、简易 footer 时间标签、测试、reference assets 与治理文档；无 Grounding/DAX/VerifiedFactSet/Local MCP worker/retry/cancellation/Remote MCP/Executive Renderer 改动。
