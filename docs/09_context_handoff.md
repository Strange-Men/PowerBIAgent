# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M0.3 数据接入与验证闭环**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M0.3 数据接入与验证闭环** — 进行中。

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |

## 当前轮 Commit

**标题：** `M0.3_数据接入与验证闭环`

**SHA：** 由下一轮通过 `git log -1` 获取。

## 最近封板 Tag

**暂无封板 Tag。**

## M0.2 审计修复（M0.3 完成）

1. AgentRuntime 从三引号字符串修复为 `runtime.py` 中的真实抽象类
2. PydanticAI API 参数名核实：`output_type`（非 `result_type`）
3. Mock Fixture 统一到 `harness/fixtures/`，移除 `backend/tests/fixtures/`
4. Mock LLM `time.sleep()` → `await asyncio.sleep()`
5. 未知 scenario_key 严格抛出 `LLMScenarioNotFoundError`
6. IntentSpec 新增 FilterSpec 结构化筛选 + 7 条跨字段一致性规则
7. DeepSeek 使用 SecretStr 封装 API Key，repr 不泄露
8. 核心依赖锁定：pydantic-ai==2.21.0, pydantic==2.13.4, pytest==9.1.1, pytest-asyncio==1.4.0, pyyaml==6.0.3
9. 状态文档修正：M0.2 Commit `d03ac6c`、自引用 SHA 规则、ADR 编号

## M0.3 新增内容

### Power BI 与数据契约
- ADR-003：Power BI MCP 认证（Remote MCP + MSAL + Entra App Registration）
- PowerBIAdapter 接口 + MockPowerBIAdapter（可运行）+ RemoteMCPPowerBIAdapter（骨架）
- 核心数据契约：QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec（含 KPISpec/ChartSpec/TableSpec）、UserContext、FilterSpec

### Harness ETCLOVG
- ADR-004：轻量控制面设计
- ToolGateway：3 工具注册、Intent 权限矩阵、async timeout、有限重试
- ContextBuilder：最近 5 轮、Secret 排除、输入截断
- TurnController：19 状态完整状态机、资源限制、MemoryCommitEvidence
- ValidationService：Intent/QueryPlan/DAX/QueryResult/Report/Memory 六类验证
- TraceRecorder：JSON Trace、Secret 脱敏、内存事件列表

### 记忆系统
- InMemoryMemoryRepository：深拷贝隔离、幂等、乐观锁、Mock/Real 空间隔离
- MemoryCommitEvidence：8 项必需要素的结构化提交证据
- MemoryCorrectionRecord：字段白名单纠正 + 审计记录
- Mock 空间规则：Mock 成功允许在 Mock 空间提交

### Application
- MockAgentRuntime：实现 AgentRuntime 接口
- MockReportRenderer：最小安全 HTML（无 JS/外部脚本）
- MockTurnService：完整确定性流程控制（非 LangGraph）

### Golden Cases
- 10 条 Golden Cases YAML（`harness/cases/golden_cases.yaml`），8 条 mock_ready
- GoldenCaseRunner：加载、校验、运行、比较

## 测试结果

**166/166 通过**（pytest 9.1.1，Python 3.11.15）

| 测试文件 | 测试数 |
|---------|--------|
| test_intent.py | 25 |
| test_llm.py | 21 |
| test_memory.py | 28 |
| test_agent_framework.py | 8 |
| test_powerbi.py | 12 |
| test_harness.py | 24 |
| test_memory_repository.py | 16 |
| test_mock_pipeline.py | 8 |
| （集成测试含 24 条 async） | |

## 目录结构

```
PowerBIAgent/
├── harness/
│   ├── README.md
│   ├── cases/golden_cases.yaml
│   ├── fixtures/
│   │   ├── mock_llm_responses.json
│   │   ├── mock_schema.json
│   │   ├── mock_query_results.json
│   │   └── mock_report_specs.json
│   └── reports/.gitkeep
├── backend/
│   ├── app/
│   │   ├── agent/        (runtime.py, mock_runtime.py)
│   │   ├── application/  (mock_turn_service.py)
│   │   ├── harness/      (ETCLOVG: runtime/, validators/, observability/, cases/)
│   │   ├── intent/       (models.py with FilterSpec)
│   │   ├── llm/          (base + mock + deepseek + registry)
│   │   ├── memory/       (models + policies + repository with InMemory)
│   │   ├── powerbi/      (base + mock + remote_mcp)
│   │   ├── report/       (base + mock)
│   │   └── schemas/      (data_contracts.py)
│   └── tests/
│       ├── fixtures/     (已清空，迁移至 harness/fixtures/)
│       ├── unit/         (7 test files)
│       └── integration/  (test_mock_pipeline.py)
└── docs/adr/
    ├── ADR-001 (Agent 框架 — 已修正 API 参数名)
    ├── ADR-002 (记忆系统 — 已修正 Mock/版本语义)
    ├── ADR-003 (Power BI MCP 认证)
    └── ADR-004 (Harness ETCLOVG)
```

## 未验证事项

- 项目负责人 Power BI 账号状态（M2 前确认）
- DeepSeek API Key 可用性（M1 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置是否启用（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）
- GoldenCases 中有 1 条为 pending_real_baseline

## 下一轮唯一允许范围

**下一轮固定 Commit：** `M0.4_项目骨架与阶段收尾`

**允许：**
- Pydantic Settings
- FastAPI 最小骨架（main.py、路由）
- `/health` 端点
- 运行模式展示
- Application Service 正式接入
- health 测试
- README 启动验证
- 全量审查
- M0 总验收
- 是否创建 M0 封板 Tag 由 M0.4 Prompt 决定

**禁止：**
- 真实 DeepSeek（M1）
- 真实 Power BI 生产连接（M2）
- React 页面（M5）
- Docker、多租户、正式报表产品
- M1-M5 开发

---

*最后更新：2026-07-31 | M0.3 数据接入与验证闭环*
