# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M0.3.1 验证闭环加固修复**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M0.3.1 验证闭环加固修复** — ✅ 已完成。

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | 由下一轮 git log -1 获取 | 2026-07-31 |

## 当前轮 Commit

**标题：** `M0.3.1_验证闭环加固修复`

**基准 Commit：** `c3510f2`（M0.3_数据接入与验证闭环）

**SHA：** 由下一轮通过 `git log -1` 获取。

**Push 状态：** 待推送

## 最近封板 Tag

**暂无封板 Tag。**

## M0.3 审计发现（16 项闭环真实性问题）

M0.3 完成后进行专项代码审计，发现以下问题并在 M0.3.1 全部修复：

1. **Memory 事务和乐观锁失真** — runtime_mode 使用任意字符串，版本语义依赖测试手工设置
2. **Mock/Real 记忆空间隔离失真** — Repository 未按 runtime_mode 过滤查询
3. **主链路绕过 ToolGateway** — MockTurnService 直接调用 `self.powerbi.*`
4. **ToolGateway 权限/模式/超时/重试未生效** — 工具未真实注册
5. **Memory 字段在 Commit 后才更新** — committed_memory 缺少分析字段
6. **多轮记忆未真实继承** — 通过 arbitrary dict 伪造 committed 状态
7. **clarification/unsupported 留下悬空 pending** — 意图识别前创建 pending
8. **失败分支没有统一标记 failed** — 部分失败路径只返回错误字典
9. **Scenario Key 没有完整进入执行链路** — 只传 intent_key
10. **GoldenCaseRunner 异步与场景注入失真** — 处理已有事件循环错误
11. **Golden Cases 预期值与描述矛盾** — gc_007 假字段标记 completed
12. **集成测试存在假通过** — 测试名称与断言矛盾
13. **ContextBuilder 未强制 committed/模式/模型边界** — 任何 Memory 都注入
14. **ValidationService 对错误结果验证不足** — error 结果返回 valid=True
15. **Trace ID/耗时/Secret 脱敏不完整** — record_completed 只更新最后事件
16. **M0.3 状态文档过期** — CHANGELOG 标记"待推送"

## M0.3.1 全部修复

### Memory 模型
- `runtime_mode` 统一为 `RuntimeDataMode` 枚举
- 版本语义：`base_memory_version` 驱动（0→1→2），Repository 原子检查
- 移除公共 `commit()`/`bump_version()`/`fail()` — 只能通过 Repository 改变状态
- `MemoryCommitEvidence.business_satisfied` vs `all_satisfied` 区分
- `version_matches` 由 Repository 原子提交时设置

### Repository
- `asyncio.Lock` 原子保护（版本检查和递增在同一临界区）
- Mock/Real 严格隔离（`get_latest_committed`/`list_by_conversation` 按 runtime_mode 过滤）
- commit() 拒绝：不完整 Evidence、非 PENDING、failed/committed、版本冲突、模式不一致
- `mark_failed()` 记录 reason 和 stage
- 保存完整 Memory 快照

### ToolGateway
- 三个工具真实注册（含 Handler、input_model、output_model）
- 所有 Adapter 调用统一经过 `gateway.execute()`
- 权限/模式/超时检查全部生效
- 新增异常类型

### MockTurnService
- 结构化 `MockScenarioSelection`（五类 Key）
- clarification/unsupported 不创建 pending
- 移除 `initial_memory` setattr
- 提交前填充完整 Memory 字段
- 失败分支统一 `mark_failed`
- `RenderedReport` 结构化结果

### ContextBuilder
- 只注入 committed（非 pending/failed）
- runtime_mode 匹配才注入
- semantic_model_key 匹配才注入
- Secret 值模式匹配（sk-/Bearer/JWT）

### TraceRecorder
- 唯一 trace_id
- 精确事件索引更新
- Secret 脱敏全覆盖

### ValidationService
- QueryResult error → valid=False
- Report 字段绑定当前 QueryResult
- 新增 Answer 验证

### GoldenCaseRunner
- Async-first
- 全部 Scenario Key
- Pydantic 强校验
- Runtime 配置生效
- Repository 验证
- 稳定命令行入口

### Golden Cases
- 12 条（11 mock_ready + 1 pending_real_baseline）
- gc_007 虚假字段 → response_failed
- gc_002 多轮 → setup_turns
- 新增：permission_denied、dax_error、oversized、幂等

## 测试结果

**191/191 pytest 通过**（pytest 9.1.1，Python 3.11.15）

**Golden Cases：11/11 mock_ready 通过，1 skipped (pending_real_baseline)**

**compileall 通过**

## 目录结构（更新）

```
PowerBIAgent/
├── harness/
│   ├── README.md
│   ├── cases/golden_cases.yaml (12 条)
│   ├── fixtures/ (新增 fake_field_report)
│   └── reports/.gitkeep
├── backend/
│   ├── app/
│   │   ├── application/mock_turn_service.py (重构)
│   │   ├── harness/
│   │   │   ├── cases/__main__.py (新增)
│   │   │   ├── cases/case_runner.py (重构)
│   │   │   ├── runtime/tool_gateway.py
│   │   │   ├── runtime/turn_controller.py
│   │   │   ├── runtime/context_builder.py (加固)
│   │   │   ├── validators/validation_service.py (加固)
│   │   │   └── observability/trace_recorder.py (加固)
│   │   ├── memory/
│   │   │   ├── models.py (重构)
│   │   │   ├── repository.py (重构)
│   │   │   └── policies.py (更新)
│   │   └── schemas/data_contracts.py (新增 RenderedReport)
│   └── tests/
│       ├── unit/test_memory_repository.py (重写)
│       ├── unit/test_memory.py (重写)
│       ├── unit/test_harness.py (部分更新)
│       └── integration/test_mock_pipeline.py (重写)
└── docs/ (全部更新)
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
- 再把 M0.3.1 核心修复推迟到 M0.4
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

*最后更新：2026-07-31 | M0.3.1 验证闭环加固修复*
