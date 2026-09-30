# M5.10.8 — MVP Final Test Seal

## 范围与状态

LOCAL TEST SEAL PASS / REMOTE CI PENDING；M5 FINAL=false。用户 2026-09-30 当前指令覆盖旧路线的大型压力计划及“不得进入 M5.10.8”限制。仅完成小修、关键 focused regression、极少量 Real、既有 required checks 和 exact-SHA CI。M5.10.9 与 M6 未实施。

起始 clean main：`189edc6a37966955eb5f0069af6be6835c6a358e`，remote main 一致。Run `36654396932` 在 frontend lint 失败，之前 backend/semantic/frontend test/typecheck 均 success；不能把父提交绿色冒充本轮证据。

## 修复

- RED：`npm run lint` 可复现 `usePowerBIAgent.ts` 中 effect 同步 setState；目录清理回到模型失效事件，effect 使用既有可取消异步启动形式并失效晚到响应。规则、ignore、依赖与业务 authority 均未修改。
- 既有 Real 验收脚本增加三请求 m5108 phase。首轮生产 Data 与 Report 成功；报告核验脚本误把单个结果尝试配对所有 plans，触发 `fact_source_field_missing`。修正为 actual DAX fingerprint → unique CanonicalQueryPlan → rebuilt VerifiedFactSet，不修改生产事实链；仅补跑 report 与尚未执行的 Kimi smoke。

## Local automated（本轮 fresh）

- Backend focused：195 passed，覆盖 Understanding continuity/fresh、failure corpus、typed failure、schema compatibility、两模板 generation、provider registry 与安全 exception API。
- Frontend focused：69 passed；新增模型缺失与晚到模板响应两项 lifecycle 回归后 hook suite 17/17 PASS。
- Frontend lint：PASS（1 error → 0 errors / 0 warnings）。
- Semantic Compatibility：819 passed / 125 production files；最终 frontend full suite 102 passed（包括新增两项 lifecycle regression），typecheck/build PASS。
- Golden：11 passed / 1 manual-real skipped；Repository Safety 420、Architecture 142、Error Ledger 117、Documentation Governance、compileall、version consistency 49 与 diff-check PASS；最终 staging 安全检查与 cached diff 必须在 commit 前通过。
- 首轮 backend：2838 passed / 2 version-consistency failures / 1 manual-real skip / 2 deselected。测试进程启动后同步版本文档，造成进程内 M5.10.7 与磁盘 M5.10.8 不一致；无业务 failure。fresh version suite 49/49 PASS；已冻结版本并以新进程重跑 required backend suite：2840 passed / 1 manual-real skipped / 2 deselected，exit 0；没有降低检查或修改 expected。
- 本地 backend 正常 suite 仅 deselect 两个 51,200-case 节点：`test_generator_covers_51200_safe_reproducible_cases`、`test_stress_report_has_zero_generated_failures`。用户明确禁止重跑；测试文件与 CI matrix 原样保留。

## Local Real（与 automated 分层）

- DeepSeek Data E2E：首轮 PASS；单轮 Total Sales scalar，no inherited filter/time，actual Local MCP result → rebuilt VerifiedFactSet → validated natural answer。
- DeepSeek executive Report E2E：PASS。生产首轮 completed；修正验收脚本后 9/9 actual DAX fingerprint → unique canonical plan → rebuilt VerifiedFactSet 配对成功。ReportSpec 包含非空 KPI/charts/table、ReadingContext/DataSnapshot，固定 Renderer 输出含 SVG/table 且无 script；HTTP view/download 字节相同、content hash 一致，presentation report block 有效。
- Kimi structured provider smoke：PASS；单个 general turn、1 LLM call、ZERO tool/ZERO factual Memory commit。DeepSeek data/report 也证明 profile/structured-output 正常；fallback contract 由 provider focused regression 单独验证。
- 实际业务行、数值、DAX、最终回答与 provider prompt/response 仅在验收进程内核验，不写入本文件或 Git。
- 实际运行合计 4 个 Real chat requests：data 1、report 2（首轮仅 observer pairing 失败）、Kimi 1；未重跑 data 或大型 matrix。最终 scoped run 2/2 PASS、9 execution witnesses、business residual=0；两次 temporary teardown residual=0。

## Remote exact-SHA CI

本轮 commit/push 后自动 workflow 待执行。当前 SHA/Run 不预填；不以 local gates 替代 remote CI。无需新 matrix 或手工重跑至绿。最终 exact-SHA/Run/remote-main/worktree audit 在最终交付消息中记录，不追加文档回填 commit。

## 人工 UI smoke（用户执行）

1. 打开主页并选择真实模型与 DeepSeek。
2. 正常问数一次。
3. follow-up 一次，确认 scope 延续。
4. 触发一次 typed failure，检查安全提示与恢复动作。
5. 选择模板生成 report。
6. 打开 artifact，检查图表/表格、metadata 与浏览器 console。

已启动本地 backend `127.0.0.1:8000` 与 frontend `127.0.0.1:5173`；health=ok/version=M5.10.8/DeepSeek+local_mcp，主页 HTTP 200，仅就绪检查，不冒充浏览器验收。

本轮不新增 Playwright/Selenium；HTTP artifact 与 frontend tests 不能冒充人工视觉/console 验收。M5.10.7 人工验收尚无新确认；M5 FINAL=false。

## 结论

Local automated + Local Real 全部 PASS，无已知本轮代码 blocker。发布最终判定待本提交自动 exact-SHA CI 与 remote-main/worktree audit；准确 SHA/Run 在最终交付消息中记录，不预填或追加回填 commit。通过后 M5.10.8 COMPLETE / READY FOR M5.10.9；人工 UI smoke 保持独立，M5 FINAL=false，不开始后续治理或功能优化。
