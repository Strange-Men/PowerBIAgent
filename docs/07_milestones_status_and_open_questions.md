# 07 — 里程碑状态与待确认事项

> **状态：** M0.4 已完成
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
| M0.4 | 项目骨架与阶段收尾 | ✅ 已完成 | 2026-07-31 | 待提交 |
| M1 | 真实 DeepSeek 接入 | ⬜ 计划中 | — | — |
| M2 | 真实 Power BI MCP 与数据问答 | ⬜ 计划中 | — | — |
| M3 | 报表生成闭环 | ⬜ 计划中 | — | — |
| M4 | 多轮记忆完善 | ⬜ 计划中 | — | — |
| M5 | React 前端与联调 | ⬜ 计划中 | — | — |

状态图例：⬜ 计划中 | ⏳ 待开始 | 🔄 进行中 | ✅ 已完成 | ❌ 阻塞

## 二、M0.2 完成状态（已修正）

| 交付物 | 状态 |
|--------|------|
| Agent 框架 ADR (ADR-001) | ✅ |
| ADR-002 记忆系统与存储 | ✅ |
| IntentSpec + IntentService | ✅ |
| LLM Provider（Mock + DeepSeek 骨架） | ✅ |
| 四层记忆 + 三态机制 + 提交准入 | ✅ |
| 65 个单元测试通过 | ✅ |
| Commit `d03ac6c` 已推送 | ✅ |

## 三、M0.2 审计修复（M0.3 完成）

| 修复项 | 状态 |
|--------|------|
| AgentRuntime 从字符串修复为真实类 | ✅ |
| PydanticAI API 准确性（output_type 非 result_type） | ✅ |
| Mock LLM Fixture 路径修复（harness/fixtures/） | ✅ |
| Mock LLM time.sleep → asyncio.sleep | ✅ |
| 未知 scenario 严格失败 | ✅ |
| IntentSpec 跨字段规则 + FilterSpec | ✅ |
| DeepSeek SecretStr 安全 | ✅ |
| 核心依赖版本锁定 | ✅ |
| 记忆系统 Mock 空间规则 | ✅ |
| MemoryCommitEvidence + Correction 审计 | ✅ |
| memory_version 语义修正 | ✅ |
| InMemoryMemoryRepository | ✅ |

## 四、待确认事项

| # | 事项 | 优先级 | 预计解决轮次 |
|---|------|--------|------------|
| 1 | Agent 框架选择 | ✅ PydanticAI | M0.2 |
| 2 | 意图识别方案 | ✅ Prompt + Pydantic | M0.2 |
| 3 | Mock LLM 策略 | ✅ scenario_key 驱动 | M0.2 |
| 4 | 筛选 AND/OR 策略 | ⏳ 待确认 | M2 |
| 5 | Power BI MCP 连接方式 | ✅ Remote MCP | ADR-003 |
| 6 | DAX 生成策略 | ⏳ 待确认 | M2 |
| 7 | 报表模板注册机制 | 中 | M3 |
| 8 | 前端状态管理方案 | 低 | M5 |
| 9 | 是否有现有 Power BI 语义模型 | 高 | M2 前 |
| 10 | DeepSeek API Key | 中 | M1 前 |
| 11 | Power BI 管理员 Tenant 设置 | 高 | M2 前 |
| 12 | Entra App Registration 权限 | 高 | M2 前 |

## 五、已知风险

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|---------|
| 1 | Power BI MCP 连接可能受账号影响 | 阻塞 M2 | M0.3 已完成 ADR-003 设计 |
| 2 | DeepSeek DAX 生成质量不确定 | 影响 M2 | DAX 校验层 + Golden Cases |
| 3 | PydanticAI Breaking Changes | 影响长期 | Adapter 隔离 + 版本锁定 |
| 4 | Remote MCP 端点不稳定 | 影响 M2 | ADR-003 Fallback 方案 |
| 5 | Entra App Registration 权限不足 | 影响 M2 | M2 早期验证 |

## 六、当前 Tag 状态

**`m0.4-foundation-release`** — M0 开发准备封板 Tag（M0.4 验收通过后创建）。

## 七、M0.4 交付总结

- 请求级并发上下文收口（删除共享 Trace/Controller 状态）
- Pydantic Settings（环境变量覆盖，Mock 无需 API Key）
- FastAPI 最小骨架（`/health` + `/api/v1/chat`）
- 265 个测试全部通过，11/11 Golden Cases 通过
- Uvicorn 启动验证通过

---

*最后更新：2026-07-31 | M0.4 项目骨架与阶段收尾*
