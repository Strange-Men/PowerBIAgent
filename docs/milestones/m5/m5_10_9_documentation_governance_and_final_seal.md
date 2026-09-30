# M5.10.9 — Documentation Governance & M5 Final Seal

> 本文件只保存本阶段 audit / 分层 evidence / release procedure；current state 仅见 07/08/09。

## Cold Start / file-level audit

2026-09-30；initial main / HEAD / fetched origin/main 均为 409fd521b4b503b6e8e56846806e099cd98e7a5b；
worktree clean；Settings.version=M5.10.8；M5 FINAL=false。REST fresh 验证 FIX Run 36665958820 与
M5.10.8 Run 36661689674 exact-SHA completed/success，满足进入本轮前置条件。
Cold Start 读取根入口/charter/CLAUDE、README/CHANGELOG、07/08/09、Ledger schema/规则/相关项、
ADR index 与核心 accepted ADR、两份 M5.10.8 记录、Settings、Harness/Acceptance/Frontend spec、
CI/Architecture/Documentation/Repository gate 与邻近 tests。
全仓 tracked text 按 M5.10.6/7/8/9、FINAL、NOT STARTED/PENDING/READY、MVP/FROZEN/M6、Remote MCP、
历史 endpoint、Fabric IQ、test_user 与 baseline/current/next wording 审计。以下 23 项为文件级
当前状态/路线冲突；历史 pending 不计为当前冲突，不机械替换旧记录。

| 文件 | 当前声明（修改前） | 真实状态 / 是否修改 | 修改方式 |
|---|---|---|---|
| README | M5.10.8 local/pending | 前置 FIX CI green；需要治理 | 根导航与候选标记 |
| PROJECT_CHARTER | M5.10.7 pending / M5.10.8 NOT STARTED | 前置 FIX CI green；需要治理 | 长期产品边界与引用 |
| AGENTS | M5.10.8 scope / 旧 CI | 前置 FIX CI green；需要治理 | 冻结纪律与两阶段候选 |
| CLAUDE | M5.10.8 pending / 禁止治理 | 前置 FIX CI green；需要治理 | 开发协议与授权范围 |
| CHANGELOG | 缺 FIX / M5.10.8 pending | 前置 FIX CI green；需要治理 | 补齐真实发布历史 |
| docs/00 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/01 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/02 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/03 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/04 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/05 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/06 | 旧里程碑状态或 Remote 默认路线 | 前置 FIX CI green；需要治理 | 合同/历史职责；状态委托 07/08/09 |
| docs/07 | M5.10.8 pending + 历史 current | 前置 FIX CI green；需要治理 | 精简状态；原文 archive |
| docs/08 | M5 小阶段长历史 | 前置 FIX CI green；需要治理 | M5—M9 路线；原文 archive |
| docs/09 | M5.10.8 pending + 长历史 | 前置 FIX CI green；需要治理 | 唯一 handoff；原文 archive |
| docs/index | 旧 milestone / 固定7文件 | 前置 FIX CI green；需要治理 | 导航/Cold Start 校准 |
| Error Ledger header | M5.10.6 candidate | 前置 FIX CI green；需要治理 | 规则/历史职责 |
| Frontend spec | M5.10.7 current/pending | 前置 FIX CI green；需要治理 | 合同职责 + 12px |
| Acceptance spec | M5.10.6 current/pending | 前置 FIX CI green；需要治理 | 长期合同/历史 |
| ADR index | M5.10.6 / ADR-006 accepted | 前置 FIX CI green；需要治理 | 状态索引/Remote superseded |
| ADR-019 | M5.10.6 current | 前置 FIX CI green；需要治理 | report authority only |
| ADR-006 | 历史 endpoint 当默认 production | 前置 FIX CI green；需要治理 | SUPERSEDED + 原文保留 |
| ADR-007 | 回到 accepted ADR-006 | 前置 FIX CI green；需要治理 | 适用性附注，历史不改 |


旧 07/08/09 以 409fd521 的内容保存到 archive，仅调整 Markdown 相对链接；milestone 添加 Historical /
Completed by 说明。历史数字、设计、失败、pending 不篡改。Core production 仅 Settings.version 字符串变化。

## Local automated — fresh PASS

Failure-first governance tests：4 failed / 4 passed，拒绝 stale current marker、mixed candidate/final、
missing frozen boundary 与历史误判。治理实现曾暴露 anchor 指认错误，按 07 current status 修复；未改 expected 迎合错误。

- 正常 Backend required suite：2853 passed / 1 manual-real skipped / 2 authorized deselected，exit 0。
- Semantic Compatibility：819 passed / 126 production files，exit 0。
- Governance + Settings/version suite：57 passed（含 49 项 Settings tests）；Ledger regression：53 passed。
- Frontend 完整 suite：105/105 passed；typecheck、lint（0 errors / 0 warnings）、production build PASS。
  首轮 frontend 98 passed / 1 forks worker startup timeout，exit 1；当时主机可用内存约 350MB且
  两个 pytest 同时运行。待 backend/semantic 完成后独占资源，以同一 npm test 原配置 fresh
  重跑 105/105，未改 tests、worker config、timeout 或依赖。
- Build 成功保留 Rolldown PLUGIN_TIMINGS advisory：plugin hooks 8% / 1.6s，不隐藏、不改阈值。
- Golden：11 passed / 1 manual-real skipped；Architecture 143、Repository Safety 426（staging 前）、
  AI Error Ledger 118 entries / 0 errors、Documentation/Artifact Governance、compileall、diff-check PASS。
  新 Ledger 记录 root current-state drift 与防复发规则；不将历史 Real 压力数字冒充本轮 fresh evidence。
- 全 tracked-text keyword audit：396 files / 219 matched files / 2362 matches，覆盖用户列出的
  current/next/baseline、版本/状态/Remote endpoint/Fabric IQ/test_user 关键词。23项是文件级
  当前状态/路线冲突，历史匹配通过 Historical/applicability 注释保留。三份 archive 已逐一
  对比 409fd521 内容，3/3 fidelity PASS，只重定位 Markdown 相对链接。
Backend normal suite 仅排除原 test_business_language_stress.py 两个 51,200-case 节点；CI matrix 不改。
不做大型 Real/stress/provider matrix，不新增 Playwright/Selenium，不重跑 Report Real E2E。

## Browser / Local Real — scoped CSS smoke PASS

复用 cross_language_real_acceptance.py 的既有 browser phase、owned temp/SQLite、正式 Real
backend + freshly built frontend，独立端口 8019；未改验收脚本、未新增 Browser framework。
真实 Logistics 显式选择后，Sales templates visible=0，指定空文案完全一致。computed font-size=12px、
line-height=18px（1.5）、color=rgb(119,119,119)；模型 title=13px、local catalog note=10px，
截图目检层级 PASS。输入物流问题后 sendEnabled=true，前端 105 项含 send/model-key/stale-selection
回归；本轮 Browser 不发送额外 chat、无新增 Real Report E2E。console warning/error=0。
截图保存工作区外，不提交真实业务或页面输出；tab关闭、finish marker触发 owned teardown，
process exit 0 / temporary_residual=0，无用户资源变更。

## Two-phase remote closure

Phase A：M5.10.9_文档治理与最终封板候选；current documents 保持 candidate / FINAL=false。
候选 exact-SHA CI success 后 Phase B 只改八 current 入口 marker；M5.10.9_M5最终封板。
Final marker 仅在最终 exact-SHA CI completed/success、HEAD==fetched origin/main、worktree clean
联合成立后作为有效 M5 FINAL seal。自身 SHA 不能写入自身提交，不追加回填 commit；准确 SHA/Run
在最终交付记录，下一开发者按 09 的 Git+exact-SHA Actions procedure 解析同一 baseline。
最终条件成立立即停止，不进入 M6。
