# Harness — PowerBIAgent 轻量控制面

## 目录结构

```
harness/
├── README.md                       # 本文件
├── cases/
│   └── golden_cases.yaml           # Golden Cases 定义
├── fixtures/
│   ├── mock_llm_responses.json     # Mock LLM 预设响应
│   ├── mock_schema.json            # Mock Power BI 语义模型结构
│   ├── mock_query_results.json     # Mock Power BI 查询结果
│   └── mock_report_specs.json      # Mock 报表规格
└── reports/
    └── .gitkeep                    # Golden Case 运行报告（不提交 Git）
```

## Fixtures

`harness/fixtures/` 是 Mock 数据的唯一事实来源。

所有 Mock LLM Provider、Mock Power BI Adapter 必须从此目录加载。
Fixture 不存在时明确失败，不静默使用隐藏默认数据。

## Golden Cases

### 运行

```powershell
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases
```

或通过 GoldenCaseRunner 编程调用。

### 状态

| 状态 | 说明 |
|------|------|
| mock_ready | Mock 场景可运行 |
| pending_real_baseline | 等待真实 Power BI 基线 |

### 比较策略

Golden Cases 不逐字比较自然语言答案。
重点比较：Intent、Tool 序列、状态流转、字段继承、Memory 提交、最终版本、Terminal State、Error Type、Response Type、Mock/Real 标记。

## M0.3.1 范围

- ✅ 11/11 可运行 Mock Golden Cases 通过
- ✅ Memory 事务和版本语义加固
- ✅ ToolGateway 真实接入（三个工具全链路）
- ✅ ContextBuilder/TraceRecorder/ValidationService 加固
- ✅ 完整 Harness 核心组件（ETCLOVG）
- ✅ JSON Trace 含唯一 trace_id
- ✅ Mock 问答链路
- ✅ Mock 报表链路（含 render_report）
- ✅ 失败保护链路（失败不提交，pending 标记 failed）

---

*最后更新：2026-07-31 | M0.3.1 验证闭环加固修复*
