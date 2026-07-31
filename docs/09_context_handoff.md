# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M0.3.2 工具网关与并发闭环修正**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M0.3.2 工具网关与并发闭环修正** — ✅ 已完成。

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | `3c7cc7c` | 2026-07-31 |
| M0.3.2 | 工具网关与并发闭环修正 | 由下一轮 git log -1 获取 | 2026-07-31 |

## 当前轮 Commit

**标题：** `M0.3.2_工具网关与并发闭环修正`

**基准 Commit：** `3c7cc7c`（M0.3.1_验证闭环加固修复）

**SHA：** 由下一轮通过 `git log -1` 获取。

**Push 状态：** 已推送至 origin/main

## 最近封板 Tag

**暂无封板 Tag。**

## M0.3.2 修复内容

来源：M0.3.1 专项审计后剩余的小范围真实性问题。

### ToolGateway 策略
- 取消全局 `TOOL_INTENT_POLICY`，以 `ToolSpec.allowed_intents` 为 Intent 权限唯一来源
- `supported_modes` 统一使用 `RuntimeDataMode` 枚举
- 完整策略检查链：read_only / Intent / runtime_mode / 用户工具权限 / 用户模型权限 / 用户模板权限 / 输入类型 / Handler / 输出类型
- 正确异常分类：ToolTimeoutError、ToolOutputValidationError
- 不重试异常（未注册、权限、类型错误）vs 有限重试（TimeoutError、retryable PowerBI 错误）
- Gateway 真实产生 tool_call_started/completed/failed Trace 事件
- 工具序列唯一来源：`TraceRecorder.get_tool_sequence()`，Application 不手工拼装

### TraceRecorder
- 深度超限返回 `[MAX_DEPTH_REACHED]` 而非原始对象
- 事件耗时在 record() 时自动计算写入 duration_ms

### 状态机失败流
- `PLAN_READY` 新增合法转换：`TOOL_EXECUTED`、`TOOL_FAILED`
- 统一 `_fail_turn()` 处理所有失败分支
- Memory 冲突时 pending 标记 failed

### Scenario 并发模型
- MockAgentRuntime 移除共享 `_scenario_key` 实例字段
- scenario_key 通过 MockLLMProvider._active_scenario 临时传递

### request_id 模式复合键
- Repository 索引使用 `(runtime_mode, request_id)` 复合键
- 全部接口显式传入 runtime_mode
- Mock 和 Real 相同 request_id 各自存在、互不可见

### MemoryPolicies 事务规则
- 提交前只检查 `business_satisfied`，不要求 `version_matches`（仅 Repository 可设置）
- Repository 成功后 version_matches=True、all_satisfied=True

### QueryResult 和 Report 唯一 ID
- QueryResult.result_id 使用 UUID（非 scenario key）
- RenderedReport.report_id 使用 UUID
- Memory 成功提交前写入 last_query_result_id 和 last_report_id

### Golden Runtime 配置
- 全部 Pydantic Case 模型 `extra="forbid"`
- 五类 Scenario Key 全部强制存在
- 每个 Case 使用独立 MockTurnService 和 Repository
- 幂等 Case 真实执行两次（repeat_target_turn），验证版本不变
- 多轮 Case 验证 base_memory_version > 0 证明 context 真实继承
- 失败 Case 验证 failed record、reason、stage、committed 不存在

## 测试结果

**205/205 pytest 通过**（pytest 9.1.1，Python 3.11.15）

**Golden Cases：11/11 mock_ready 通过，1 skipped (pending_real_baseline)**

**compileall 通过**

## 目录结构（更新）

```
PowerBIAgent/
├── harness/
│   ├── README.md
│   ├── cases/golden_cases.yaml（12 条，五类 Key 全部必填）
│   ├── fixtures/（4 个 JSON fixture）
│   └── reports/.gitkeep
├── backend/
│   ├── app/
│   │   ├── application/mock_turn_service.py（_fail_turn 统一失败处理）
│   │   ├── agent/mock_runtime.py（移除共享 _scenario_key）
│   │   ├── harness/
│   │   │   ├── cases/__main__.py
│   │   │   ├── cases/case_runner.py（M0.3.2 严格化）
│   │   │   ├── errors.py
│   │   │   ├── models.py
│   │   │   ├── runtime/tool_gateway.py（M0.3.2 完整改写）
│   │   │   ├── runtime/turn_controller.py（PLAN_READY 新增合法转换）
│   │   │   ├── runtime/context_builder.py
│   │   │   ├── validators/validation_service.py（source_mode error）
│   │   │   └── observability/trace_recorder.py（深度安全返回值）
│   │   ├── memory/
│   │   │   ├── models.py
│   │   │   ├── repository.py（runtime_mode 复合键）
│   │   │   └── policies.py（business_satisfied 检查）
│   │   └── schemas/data_contracts.py（QueryResult.result_id）
│   └── tests/
│       ├── unit/test_memory_repository.py（复合键 + 跨模式共存）
│       ├── unit/test_harness.py
│       └── integration/test_mock_pipeline.py（并发/产物ID/Answer校验）
└── docs/（全部更新）
```

## 未验证事项

- 项目负责人 Power BI 账号状态（M2 前确认）
- DeepSeek API Key 可用性（M1 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）

## 下一轮唯一允许范围

**下一轮固定 Commit：** `M0.4_项目骨架与阶段收尾`

**允许：**
- Pydantic Settings（环境变量读取）
- FastAPI 最小骨架（main.py）
- `/health` 端点
- 运行模式展示
- 将已加固的 Application Service 接入 FastAPI
- health 测试
- README 启动验证
- M0 全量验收
- 是否创建 M0 封板 Tag 由 M0.4 Prompt 决定

**禁止：**
- 再修复本轮已经要求完成的 ToolGateway 和并发问题
- 真实 DeepSeek（M1）
- 真实 Power BI 生产连接（M2）
- React 页面（M5）
- Docker、多租户、正式报表产品
- M1-M5 功能开发

## M0.4 必读文件

1. PROJECT_CHARTER.md
2. CLAUDE.md
3. docs/00_product_requirements_document.md
4. docs/09_context_handoff.md（本文件）
5. docs/08_development_roadmap.md
6. 本轮 Prompt 指定的设计文档和 ADR

---

*最后更新：2026-07-31 | M0.3.2 工具网关与并发闭环修正*
