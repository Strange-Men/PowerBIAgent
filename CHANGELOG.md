# CHANGELOG

> 完整历史变更记录见 `docs/archive/m0-m1.6_detailed_changelog.md`

---

## [M1.7] — 2026-08-05

### MVP轻量化与通用CI固化

**目标：** M0—M1 正式封板前最后一次整理 — 测试收敛、CI通用化、文档轻量化、Smoke移出生产包。

**主要变更：**
- 测试收敛：删除4个旧集成测试文件（已被更强领域测试覆盖），版本化测试文件重命名为领域名称
- CI通用化：`.github/workflows/ci.yml`（PowerBIAgent Validation），动态版本一致性由pytest保护
- Smoke轻量化：删除4个阶段性Smoke，只保留一个人工验收入口（`scripts/manual_smoke/deepseek_chat_smoke.py`）
- 文档轻量化：归档M1.6审计文档、压缩docs/09和活跃CHANGELOG
- 版本同步至M1.7

**最终测试结果：**
- pytest：1120 passed
- Golden Cases：11 passed，1 skipped
- 真实 LLM 调用次数：0
- 生产依赖变化：0
- 生产业务逻辑变化：0
- 未创建 Tag

**Commit：** 本轮提交

---

## [M1.6] — 2026-08-04 ~ 2026-08-05

### 架构收口与加固（M1.6.1—M1.6.6）

**目标：** 审计复验、架构定案、Harness收口、统一TurnPipeline、旧Agent清理、AI真实性加固、错题本治理、CI建立。

**关键架构决定：**
- ADR-005：确定性TurnPipeline与受控LLM调用架构（废弃PydanticAI）
- Memory单写入者：TurnPipeline为唯一事务入口
- ToolGateway为Power BI/Renderer唯一调用入口
- AST架构门禁替代grep检查

**最终验收（M1.6.6）：**
- pytest：1253 passed | Golden Cases：11 passed，1 skipped
- 安全扫描：PASS | 远程CI（Run #30983637121）：全部通过
- Commits：`0f6424f` → `208bca4` → `d6665bd` → `d99d243` → `d57e38c` → `4217b66` → `e850f14`/`cb2826e`/`762f4cf` → `084aa76`

---

## [M1.5] — 2026-08-03

### 全链路验收与M1封板

**Tag：** `m1-deepseek-pipeline-release` | **Commit：** `a926b5e`

**主要能力：**
- DeepSeek Chat全链路：Intent → QueryPlan → DAX → Mock QueryResult → Answer/ReportSpec → Memory
- TurnServiceProtocol通用协议 + Mock/DeepSeek双Service
- API模式切换：Mock/DeepSeek Health 200/503
- ChatResponse扩展 + Token/repair统计

**测试结果：** pytest 937 passed | Golden Cases 11/1 | 安全扫描 PASS

---

## [M1.4] — 2026-08-03

### 真实Answer与ReportSpec生成（含M1.4.1修复）

**主要能力：** DeepSeekAnswerService/ReportSpecService、Evidence强制绑定、KPI/Table/Chart严格验证、模板冲突拒绝

**测试结果：** pytest 936 passed | Golden Cases 11/1

---

## [M1.3] — 2026-08-03

### 真实QueryPlan与DAX生成（含M1.3.1修复、M1.3.2前端文档）

**主要能力：** DeepSeekQueryPlanService/DAXService、DAX只读安全验证器、QP真实验证、结构化回答契约

**测试结果：** pytest 706 passed | Golden Cases 11/1

---

## [M1.2] — 2026-08-03

### 真实意图识别

**Commit：** `53cf43e`

**主要能力：** DeepSeekIntentService、IntentContextSnapshot、意图严格化、集中式Prompt

**测试结果：** pytest 604 passed | Golden Cases 11/1

---

## [M1.1] — 2026-08-03

### DeepSeek Provider基础接入

**Commit：** `073a819`

**主要能力：** DeepSeekLLMProvider、10种异常类型、Provider Factory、真实连通测试

**测试结果：** pytest 506 passed | Golden Cases 11/1

---

## [M1.0 — M1.0.2] — 2026-07-31

### M0遗留收口、幂等并发、密钥安全

**Commits：** `9247322`、`c223d7b`、`5726959`

**主要能力：** 请求指纹与冲突检测、并发Owner/Waiter防重、Report快照结构化、密钥安全规则固化

**测试结果：** pytest 415 passed | Golden Cases 11/1

---

## [M0.4 — M0.4.1] — 2026-07-31

### 项目骨架与阶段收尾

**Tags：** `m0.4.1-foundation-release`、`m0.4-foundation-release`

**主要能力：** FastAPI最小骨架、API骨架真实性修复、请求级并发上下文收口

**测试结果：** pytest 285 passed | Golden Cases 11/1

---

## [M0.1 — M0.3] — 2026-07-31

### 仓库初始化、架构设计与验证闭环

**主要能力：** 项目文档基线、四层记忆系统、Power BI MCP设计（ADR-003）、ETCLOVG Harness（ADR-004）、ToolGateway、Golden Cases

---

*最后更新：2026-08-05 | M1.7 轻量化候选*
