# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-05 | M1.6.6 进行中 — CI、最终架构审计与二审候选版**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

前端最终方向为带左侧栏的 GPT 式极简对话网页（React + Vite，M5 开发）。左侧栏内容、报表位置、导航层级和工作台结构尚未确定，M5 重新完成整体信息架构。

## 当前阶段

**M1.6.6 CI、最终架构审计与二审候选版** — 🔄 进行中。

> **说明：**
> - 本轮不是M2功能开发轮，也不是正式封板动作
> - M1.6.5遗留收口、错题本与校验器强化
> - Prompt注入行为测试补强、TurnController限制路径验证
> - GitHub Actions CI建立
> - 最终候选版架构审计
> - 本轮不创建Tag、不执行真实DeepSeek Smoke
> - 二审通过前不宣布M1.6正式封板
> - 真实 LLM 调用次数：0

## 上一轮

**M1.6.5** — 真实测试、机器错题本与架构防偏移治理（Commit `e850f14`、`cb2826e`、`762f4cf`）

## 下一动作

**仓库二审** — M1.6.6 候选Commit Push后等待用户连接仓库二审。二审通过前不创建Tag、不进入M2、不宣布M1.6正式封板。

- M1.6.6 职责：遗留收口、CI、最终审计、Push候选Commit
- 二审后：由用户决定正式封板或补充修复

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | `3c7cc7c` | 2026-07-31 |
| M0.3.2 | 工具网关与并发闭环修正 | `ec1afcc` | 2026-07-31 |
| M0.3.3 | Mock场景并发隔离修复 | `d0d47e3` | 2026-07-31 |
| M0.4 | 项目骨架与阶段收尾 | `d5c1634` | 2026-07-31 |
| M0.4.1 | API骨架真实性修复 | `1f967b0` | 2026-07-31 |
| M1.0 | M0遗留收口与M1路线固化 | `9247322` | 2026-07-31 |
| M1.0.1 | 幂等并发与文档收尾修复 | `c223d7b` | 2026-07-31 |
| M1.0.2 | 密钥与仓库安全规则固化 | `5726959` | 2026-07-31 |
| M1.1 | DeepSeek Provider基础接入 | `073a819` | 2026-08-03 |
| M1.2 | 真实意图识别 | `53cf43e` | 2026-08-03 |
| M1.3 | 真实QueryPlan与DAX生成 | `441ca45` / `c0e782b` | 2026-08-03 |
| M1.3.1 | QueryPlan与DAX验证修复 | `6647760` | 2026-08-03 |
| M1.3.2 | 前端视觉与结构化回答契约固化 | `db0a7e8` | 2026-08-03 |
| M1.4 | 真实Answer与ReportSpec生成 | `4b1f0a3` | 2026-08-03 |
| M1.4.1 | 真实性验证与Smoke验收修复 | `e22f9bd` | 2026-08-03 |
| M1.5 | 全链路验收与M1封板 | `a926b5e` | 2026-08-03 |
| M1.6.1 | 审计复验与架构定案 | `0f6424f` | 2026-08-04 |
| M1.6.2 | Harness与配置收口 | `208bca4` | 2026-08-04 |
| M1.6.3 | 统一TurnPipeline与旧Agent抽象清理 | `d6665bd` | 2026-08-04 |
| M1.6.3.1 | 统一管线复验与彻底收口 | `d99d243` | 2026-08-04 |
| M1.6.3.2 | 事务边界与单写入者彻底收口 | `d57e38c` | 2026-08-05 |
| M1.6.4 | AI真实性、异常处理与对抗测试加固 | `4217b66` | 2026-08-05 |
| M1.6.5 | 真实测试、机器错题本与架构防偏移治理 | `e850f14` / `cb2826e` / `762f4cf` | 2026-08-05 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m1-deepseek-pipeline-release` | `a926b5e` | M1 DeepSeek 全链路封板 |
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## M1.5 交付内容

### P0 修复
- **Token/repair 统计修复**：建立请求级 LLMCallCollector + ObservedLLMProvider 观察层
- **LLMValidationError 安全携带 usage**：validation 失败仍计入 attempt 和 Token
- **ValidationService 空权限语义修复**：[] 拒绝全部，None 使用默认
- **前端文档边界修正**：移除"确定最终布局"等绝对表述，明确 M2-M4 不绑定 UI

### DeepSeek Chat 全链路
- **TurnServiceProtocol** 通用协议 + MockTurnService 适配
- **DeepSeekTurnService**：Intent → Schema → QueryPlan → DAX → Mock QueryResult → Answer/ReportSpec → Memory Commit
- 使用 RuntimeDataMode.REAL 空间，与 Mock 隔离
- Memory: is_mock=False, llm_provider=deepseek, powerbi_provider=mock_powerbi
- 每个请求独立 LLMCallCollector + ObservedLLMProvider
- DeepSeek 失败不回退 Mock LLM

### API 模式
- Mock+Mock: Health 200, Chat Mock 链路
- DeepSeek+Mock (有 Key): Health 200, Chat 真实 DeepSeek
- DeepSeek+Mock (无 Key): Health 503, Chat 503
- Remote MCP: Health 503, Chat 503

### ChatResponse 扩展
- 新增: llm_mode, powerbi_mode, source_mode, usage
- usage: call_count, repair_count, prompt_tokens, completion_tokens, total_tokens, duration_ms, estimated_cost_usd, pricing_configured
- is_mock: Mock LLM=True, DeepSeek LLM=False
- 不新增 UI 布局字段

### QueryResult
- source_mode 始终为 mock（使用 MockPowerBIAdapter）

### 错误映射
- deepseek_api_key_missing → 503
- deepseek_authentication_failed → 502
- deepseek_rate_limited → 503
- deepseek_timeout → 504
- deepseek_connection_failed → 502
- deepseek_service_unavailable → 502/503
- request_id_conflict → 409
- idempotency_coordination_unavailable → 503
- powerbi_remote_mcp_not_implemented → 503

### 测试结果
- pytest：937 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（138 文件）

### 运行边界
- Settings.version=M1.5
- Chat DeepSeek+Mock 已可用（需配置 DEEPSEEK_API_KEY）
- QueryResult 仍为 Mock
- Renderer 仍为 Mock
- 真实 Power BI 属 M2
- Remote MCP 属 M2
- 前端属 M5

## M1.6.3.2 真实 DeepSeek Chat Smoke 记录

- **执行时间：** 2026-08-05（M1.6.3.2 轮次内）
- **结果：** overall_success=true
- **案例数：** 6 个通过
- **source_mode=mock：** 属于当前设计（Power BI 仍使用 Mock 适配器）
- **estimated_cost_usd=null：** 属于未配置价格（Settings 中成本参数为 None）

## 未完成或待观察事项

- M2: 真实 Power BI MCP 连接、OAuth、DAX 真实验证
- M3: 报表正式渲染管线、报表资源 ID
- M4: 会话持久化、搜索、最近对话
- M5: React 前端
- 跨进程持久化和分布式锁延后处理
- 项目负责人 Power BI 账号状态（M2 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）
- 公司真实 Power BI 语义模型（M2 前确认）
- 可用报表模板（M3 前确认）
- 报表资源保存位置（M3 前确认）
- 会话和报表持久化方案（M4 前确认）
- 前端整体信息架构和交互设计（M5 前确认）

---

*最后更新：2026-08-05 | M1.6.6 CI、最终架构审计与二审候选版*
