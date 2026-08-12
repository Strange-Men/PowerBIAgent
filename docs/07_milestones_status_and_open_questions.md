# 07 — 里程碑状态与待确认事项

> **状态：** M2.6 正确性契约与架构治理加固完成
> **更新频率：** 每轮结束时更新

---

## 一、里程碑总览

| 里程碑 | 名称 | 状态 | 完成日期 | Commit |
|--------|------|------|---------|--------|
| M0.1 | 仓库初始化与文档基线 | ✅ 已完成 | 2026-07-31 | `eb5812d` |
| M0.2 | 智能体架构与记忆设计 | ✅ 已完成 | 2026-07-31 | `d03ac6c` |
| M0.3 | 数据接入与验证闭环 | ✅ 已完成 | 2026-07-31 | `c3510f2` |
| M0.3.1 | 验证闭环加固修复 | ✅ 已完成 | 2026-07-31 | `3c7cc7c` |
| M0.3.2 | 工具网关与并发闭环修正 | ✅ 已完成 | 2026-07-31 | `ec1afcc` |
| M0.3.3 | Mock场景并发隔离修复 | ✅ 已完成 | 2026-07-31 | `d0d47e3` |
| M0.4 | 项目骨架与阶段收尾 | ✅ 已完成 | 2026-07-31 | `d5c1634` |
| M0.4.1 | API骨架真实性修复 | ✅ 已完成 | 2026-07-31 | `1f967b0` |
| M1.0 | M0遗留收口与M1路线固化 | ✅ 已完成 | 2026-07-31 | `9247322` |
| M1.0.1 | 幂等并发与文档收尾修复 | ✅ 已完成 | 2026-07-31 | `c223d7b` |
| M1.0.2 | 密钥与仓库安全规则固化 | ✅ 已完成 | 2026-07-31 | `5726959` |
| M1.1 | DeepSeek Provider基础接入 | ✅ 已完成 | 2026-08-03 | `073a819` |
| M1.2 | 真实意图识别 | ✅ 已完成 | 2026-08-03 | `53cf43e` |
| M1.3 | 真实QueryPlan与DAX生成 | ✅ 已完成 | 2026-08-03 | `441ca45` / `c0e782b` |
| M1.3.1 | QueryPlan与DAX验证修复 | ✅ 已完成 | 2026-08-03 | `6647760` |
| M1.3.2 | 前端视觉与结构化回答契约固化 | ✅ 已完成 | 2026-08-03 | `db0a7e8` |
| M1.4 | 真实Answer与ReportSpec生成 | ✅ 已完成 | 2026-08-03 | `4b1f0a3` |
| M1.4.1 | 真实性验证与Smoke验收修复 | ✅ 已完成 | 2026-08-03 | `e22f9bd` |
| M1.5 | 全链路验收与M1封板 | ✅ 已完成 | 2026-08-03 | `a926b5e` |
| M2.6 | 正确性契约与架构治理加固 | ✅ 已完成 | 2026-08-12 | Filter/TopN/Sort/Gate/Health |
| M2.6.1 | Known-answer Oracle + Real Multi-turn Harness | ⬜ 未开始 | — | — |
| M2.6.2 | 最终真实数值与多轮验收 | ⬜ 未开始 | — | — |
| M3 | 报表生成闭环 | ⬜ 未开始 | — | — |
| M4 | 多轮记忆完善 | ⬜ 未开始 | — | — |
| M5 | React 前端与联调 | ⬜ 未开始 | — | — |

状态图例：⬜ 未开始 | 🔄 进行中 | ✅ 已完成 | ❌ 阻塞

## 二、当前主要交付物

| 交付物 | 状态 |
|--------|------|
| Agent 控制面 (确定性 TurnPipeline + Pydantic 契约) | ✅ |
| 意图识别 (IntentSpec + DeepSeekIntentService) | ✅ |
| LLM Provider (Mock + DeepSeek) | ✅ |
| QueryPlan 生成 (DeepSeekQueryPlanService) | ✅ |
| DAX 生成 + 只读安全验证 (DeepSeekDAXService) | ✅ |
| 四层记忆 + 三态机制 + 提交准入 | ✅ |
| Harness ETCLOVG 完整实现 | ✅ |
| FastAPI 最小骨架 (/health + /api/v1/chat) | ✅ |
| Golden Cases (11 个 Mock/Fake 通过 + 1 个人工真实基线) | ✅ |
| 前端视觉与组合回答契约 | ✅ M1.3.2 完成 |
| Answer 真实生成 | ✅ M1.4 |
| ReportSpec 真实生成 | ✅ M1.4 |
| 真实性验证加固（KPI/Metrics/Table/模板） | ✅ M1.4.1 |
| QueryPlan 模板 Key 契约 | ✅ M1.4.1 |
| 真实 Power BI MCP 连接 | ✅ Local Desktop Demo；Remote Deferred |
| 报表正式渲染与资源 | ⬜ M3 |
| 会话历史与持久化 | ⬜ M4 |
| React 前端 | ⬜ M5 |

## 三、待确认事项

| # | 事项 | 优先级 | 预计解决轮次 |
|---|------|--------|------------|
| 1 | Agent 控制面 | ✅ 确定性 TurnPipeline + Pydantic 契约 | M1.6.3 |
| 2 | 意图识别方案 | ✅ Prompt + Pydantic | M1.2 |
| 3 | Mock LLM 策略 | ✅ scenario_key 驱动 | M0.2 |
| 4 | Power BI MCP 连接方式 | ✅ Local Demo；Remote 生产化 Deferred | ADR-006 / ADR-007 |
| 5 | 筛选组合策略 | ✅ Real 仅 eq=SUPPORTED；其余 NOT_VERIFIED 并受控拒绝 | M2.6 |
| 6 | DAX 生成策略 | ✅ DeepSeek + 只读安全验证 | M1.3 |
| 7 | DeepSeek API Key | ✅ M1.1 前已确认 | M1.1 |
| 8 | 公司真实 Power BI 语义模型（有哪些、结构如何） | 高 | Remote 生产化前 |
| 9 | 可用报表模板（哪些模板、谁维护） | 中 | M3 前 |
| 10 | Power BI 管理员 Tenant 设置 | 高 | Remote 生产化前 |
| 11 | Entra App Registration 权限 | 高 | Remote 生产化前 |
| 12 | 报表资源保存位置（本地文件/对象存储/数据库） | 中 | M3 前 |
| 13 | 报表查看与下载方式（浏览器打开/后端下载/前端嵌入） | 中 | M3 前 |
| 14 | 会话和报表持久化方案（SQLite/PostgreSQL/文件） | 中 | M4 前 |
| 15 | 前端是否展示其他模型（GPT-5.6 等未接入模型） | 低 | M5 前 |
| 16 | 当前正式模型仅 DeepSeek（Mock 仅测试、未来模型未接入前不展示为可用） | 中 | 已确定 |
| 17 | 前端状态管理方案 | 低 | M5 |

## 四、已知风险

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|---------|
| 1 | Local MCP / Desktop Preview 版本变化 | 影响 Local Demo | Adapter 隔离 + 固定版本 + 变更后重新 Smoke |
| 2 | DeepSeek DAX 业务语义不确定 | 影响受控问答 | Schema Grounding + Layer 2/3 + Business Golden |
| 3 | Issue #124 缺失 rows | 影响真实查询 | 保持 Open 风险；missing rows 受控失败，当前实机未复现 |
| 4 | Remote MCP 管理员与授权条件不足 | 阻塞 Remote 生产化 | Remote Deferred，按 ADR-006 恢复 |
| 5 | 当前 Business Golden 未提供独立数值 Oracle / Real Multi-turn 证据 | 不足以完成 hardened 最终封板 | M2.6.1/2 按独立 Oracle 与全会话成功契约验收 |

## 五、当前 Tag 状态

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |
| `m1-deepseek-pipeline-release` | `a926b5e` | M1 DeepSeek 主链封板 |
| `m1.7.2-m0-m1正式封板` | `23d8ddb` | M0—M1 正式封板 |
| `m2-local-powerbi-demo-release` | `c9af48a` | M2.5 Local Demo 正式封板；本轮保持不变 |

---

*最后更新：2026-08-12 | M2.6 正确性契约与架构治理加固完成*
