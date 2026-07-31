# 07 — 里程碑状态与待确认事项

> **状态：** M0.2 已完成
> **更新频率：** 每轮结束时更新

---

## 一、里程碑总览

| 里程碑 | 名称 | 状态 | 完成日期 | Commit |
|--------|------|------|---------|--------|
| M0.1 | 仓库初始化与文档基线 | ✅ 已完成 | 2026-07-31 | `eb5812d` |
| M0.2 | 智能体架构与记忆设计 | ✅ 已完成 | 2026-07-31 | 待提交 |
| M0.3 | 数据接入与验证闭环 | ⏳ 待开始 | — | — |
| M0.4 | 项目骨架与阶段收尾 | ⏳ 待开始 | — | — |
| M1 | 真实 DeepSeek 接入 | ⬜ 计划中 | — | — |
| M2 | 真实 Power BI MCP 与数据问答 | ⬜ 计划中 | — | — |
| M3 | 报表生成闭环 | ⬜ 计划中 | — | — |
| M4 | 多轮记忆完善 | ⬜ 计划中 | — | — |
| M5 | React 前端与联调 | ⬜ 计划中 | — | — |

状态图例：⬜ 计划中 | ⏳ 待开始 | 🔄 进行中 | ✅ 已完成 | ❌ 阻塞

## 二、M0.1 完成状态

| 交付物 | 状态 |
|--------|------|
| 原始 PRD 识别与保留 | ✅ |
| 正式 PRD (docs/00) | ✅ |
| PROJECT_CHARTER.md | ✅ |
| docs/08_development_roadmap.md | ✅ |
| docs/09_context_handoff.md | ✅ |
| CLAUDE.md (冷启动协议) | ✅ |
| .gitignore | ✅ |
| .env.example | ✅ |
| environment.yml | ✅ |
| pyproject.toml | ✅ |
| README.md | ✅ |
| CHANGELOG.md | ✅ |
| Docs 02-05 骨架 | ✅ |
| Docs 01, 06, 07 实质内容 | ✅ |
| Git 初始化与远程配置 | ✅ |
| PBIAgent Conda 环境 | ✅ |
| Git Commit | ✅ `eb5812d` |
| Git Push | ✅ 已推送至 origin/main |
| M0.1 一致性修复 (M0.2) | ✅ |

## 三、M0.2 完成状态

| 交付物 | 状态 |
|--------|------|
| Agent 框架 ADR (ADR-001) | ✅ |
| ADR-002 记忆系统与存储 | ✅ |
| IntentSpec 完整 Pydantic 模型 | ✅ |
| 四类 Intent (data_question/report_generation/clarification/unsupported) | ✅ |
| LLM Provider 抽象 (base.py) | ✅ |
| DeepSeek Provider 骨架 | ✅ |
| Mock LLM Provider（可运行） | ✅ |
| Provider Registry | ✅ |
| 四层记忆设计 | ✅ |
| 三态机制 (pending/committed/failed) | ✅ |
| 记忆提交准入条件 | ✅ |
| request_id 幂等 | ✅ |
| memory_version 乐观锁 | ✅ |
| 上下文切换策略 | ✅ |
| Context Assembly 契约 | ✅ |
| MemoryRepository 接口 | ✅ |
| MemoryPolicies 策略 | ✅ |
| M0.2 单元测试 (65/65 通过) | ✅ |
| docs/03 实质完成 | ✅ |
| docs/07 更新 | ✅ |
| docs/08 更新 | ✅ |
| docs/09 更新 | ✅ |
| docs/adr/ 更新 | ✅ |
| CHANGELOG 更新 | ✅ |
| pyproject.toml 实际依赖 | ✅ |
| 后端目录统一为 backend/app + backend/tests | ✅ |

## 四、当前 Tag 状态

**暂无封板 Tag。**

M0.1、M0.2、M0.3 不创建 Tag。是否在 M0.4 完成后创建 M0 封板 Tag，由 M0.4 Prompt 明确决定。

## 五、待确认事项

| # | 事项 | 优先级 | 预计解决轮次 |
|---|------|--------|------------|
| 1 | Agent 框架具体选择 | ✅ 已解决 | M0.2 → PydanticAI |
| 2 | 意图识别实现方案（Prompt vs 分类器 vs 混合） | ✅ 已解决 | M0.2 → Prompt + Pydantic 校验 |
| 3 | Mock LLM 策略（固定响应 vs 可配置 vs 录制回放） | ✅ 已解决 | M0.2 → scenario_key 驱动 |
| 4 | 记忆合并策略细节（筛选条件的 AND/OR 逻辑） | ✅ 已解决 | M0.2 → MemoryPolicies |
| 5 | Power BI MCP 连接方式（本地 vs 远程） | 高 | M0.3 |
| 6 | DAX 生成策略（模板 vs LLM 直接生成） | 高 | M0.3 |
| 7 | 报表模板注册和管理机制 | 中 | M3 |
| 8 | 前端状态管理方案 | 低 | M5 |
| 9 | 是否有现有 Power BI 语义模型可直接测试 | 高 | M0.3 前需确认 |
| 10 | DeepSeek API Key 获取方式 | 中 | M1 前需确认 |

## 六、已知风险

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|---------|
| 1 | Power BI MCP 连接可能受 Microsoft 账号配置影响 | 阻塞 M2 | M0.3 早期验证 |
| 2 | DeepSeek 对 DAX 生成质量不确定 | 影响 M2 | 建立 DAX 校验层和 Golden Cases |
| 3 | 单 Agent 架构可能不如预期灵活 | 影响长期 | 通过 ADR 记录决策，必要时重新评估 |
| 4 | 个人账号和数据的限流风险 | 影响 M2-M3 | 设置合理的查询限制和缓存 |
| 5 | LLM 输出格式不稳定 | 影响全链路 | Pydantic 强制校验 + 重试机制 |
| 6 | PydanticAI API Breaking Changes | 影响长期 | Adapter 隔离 + 锁定版本 |

## 七、阻塞项

**当前无阻塞项。**

---

*最后更新：2026-07-31 | M0.2 智能体架构与记忆设计*
