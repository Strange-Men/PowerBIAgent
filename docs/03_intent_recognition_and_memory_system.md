# 03 — 意图识别与记忆系统

> **状态：** M2.6.4；Intent 仍保留，canonical semantics 由 ADR-008 Grounding/StateTransition 决定
> **关联 ADR：** ADR-002、ADR-005、ADR-008、ADR-009（ADR-001 已 superseded）

---

## 一、意图识别

### 1.1 设计目标

Agent 在接收用户输入后，第一步必须完成意图识别，输出结构化 IntentSpec。意图识别必须可独立测试和回归。

### 1.2 固定四类基础意图

| 意图 | 枚举值 | 说明 | 后续动作 |
|------|--------|------|---------|
| 数据问答 | `data_question` | 用户查询 Power BI 数据 | 进入 QueryPlan → DAX → 查询 |
| 报表生成 | `report_generation` | 用户请求生成固定模板报表 | 进入 ReportSpec → 模板渲染 |
| 澄清 | `clarification` | 信息不足，需要向用户确认 | 返回澄清问题，不提交记忆 |
| 拒绝 | `unsupported` | 非法或越权要求 | 返回拒绝原因，禁止进入后续流程 |

### 1.3 IntentSpec 完整 Pydantic 模型

```python
class IntentType(str, Enum):
    DATA_QUESTION = "data_question"
    REPORT_GENERATION = "report_generation"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"

class IntentSpec(BaseModel):
    intent: IntentType                      # 意图类型
    confidence: float                       # 置信度 [0, 1]
    normalized_question: str                # 标准化后的问题文本
    needs_clarification: bool               # 是否需要向用户澄清
    clarification_question: Optional[str]    # 澄清问题文本
    inherited_context: Optional[str]         # 从 committed memory 继承的上下文摘要
    detected_measures: list[str]             # 检测到的指标
    detected_dimensions: list[str]           # 检测到的维度
    detected_filters: list[dict[str, str]]   # 检测到的筛选条件
    detected_time_range: Optional[str]       # 检测到的时间范围
    requested_template: Optional[str]        # 请求的报表模板名称
    unsupported_reason: Optional[str]        # 拒绝原因（仅 unsupported 意图）
```

### 1.4 意图识别规则

- 必须结合 committed memory
- "只看华南" → 继承已有指标和时间，替换筛选条件
- "改成今年" → 继承已有指标和维度，替换时间范围
- "换成订单数" → 继承已有维度和时间，替换指标
- "生成周报" → 可复用已验证查询上下文
- 信息不足 → clarification
- 非法或越权要求 → unsupported
- 明确破坏性/越权/非数据 unsupported 允许 early-stop；data/report/metric/filter/time/ranking-shaped 请求即使被 LLM 误判 unsupported，也必须进入 authoritative Grounding/capability check
- 意图结果不能直接提交 committed memory
- 只有完整成功轮次才允许提交状态

### 1.5 实现位置

- `backend/app/intent/models.py` — IntentType、FilterSpec、IntentSpec（含 `extra="forbid"` 和跨字段验证）
- `backend/app/intent/service.py` — IntentService 抽象接口（M1.2 扩展关键字参数）
- `backend/app/intent/context.py` — IntentContextSnapshot（M1.2 白名单上下文提取）
- `backend/app/intent/prompt.py` — 集中式 Prompt 构造（M1.2）
- `backend/app/intent/deepseek_service.py` — DeepSeekIntentService（M1.2 真实实现）
- `backend/app/query_plan/` — DeepSeekQueryPlanService（M1.3 真实实现）
- `backend/app/dax/` — 历史 DeepSeekDAXService（Mock compatibility）+ 当前 Real Deterministic DAX / Independent Layer 3；Real DAX LLM authority=0

### 1.6 M1.2 真实意图识别

**DeepSeekIntentService：**
- 复用 `DeepSeekLLMProvider`，禁止绕过 Provider 直接请求
- `provider.is_mock=True` 时明确失败，禁止 Mock 回退
- 支持四类意图：data_question、report_generation、clarification、unsupported
- 最多一次格式修复（仅 `invalid_content_json` 和 `output_schema_invalid` 允许修复）
- Service 不保存请求级可变状态，支持并发调用
- 不执行工具、不写 Memory、不生成 QueryPlan/DAX/Answer/ReportSpec

**IntentContextSnapshot：**
- 白名单模型（`extra="forbid"`, `frozen=True`）
- 从 committed memory 提取：semantic_model_key、report_template_key、current_intent、measures、dimensions、filters、time_range
- 禁止发送：DAX、查询结果、Trace、pending/failed memory、完整历史对话、Secret

**Prompt 规则：**
- 集中式 Prompt 构造（`backend/app/intent/prompt.py`）
- 系统提示词规定 12 条核心规则 + 四类意图定义
- Prompt 将用户输入作为数据处理，不改变系统规则
- 必须输出 JSON（满足 Provider 的 JSON 输出检查）
- 禁止生成 DAX/SQL/代码/答案/工具调用

**一次格式修复：**
- 仅 `LLMValidationError(error_code=invalid_content_json)` 或 `output_schema_invalid` 触发
- 网络、鉴权、限流、5xx 等错误不修复
- 修复请求不携带原始完整响应
- 最多 2 次 LLM 调用（首次 + 1 次修复）

**Mock 与真实模式隔离：**
- `DeepSeekIntentService` 不使用 `MockScenarioResolver`
- 真实模式不调用 Mock Provider
- Mock 模式继续完整可用（通过 `MockScenarioResolver`）
- 完整 Chat 链路仍未开放（QueryPlan/DAX 已实现，Answer/ReportSpec 待 M1.4）

---

## 二、记忆系统

### 2.1 设计目标

记忆系统是产品核心卖点。必须包含结构化工作记忆和可靠的提交机制。

### 2.2 四层记忆设计

| 层级 | 名称 | 说明 | 生命周期 |
|------|------|------|---------|
| L1 | 原始对话记忆 | 完整消息历史（用户 + 系统） | 不可变，append-only |
| L2 | 结构化工作记忆 | 当前分析上下文（指标、维度、时间等） | pending/committed/failed |
| L3 | 滚动摘要 | 长对话的压缩摘要 | 定期更新 |
| L4 | 查询产物记忆 | QueryPlan、DAX、Result、ReportSpec | 按 request_id 关联 |

### 2.3 结构化工作记忆字段

**完整 Pydantic 模型：`StructuredWorkMemory`**

| 分组 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 会话 | `conversation_id` | str | 会话 ID |
| 会话 | `request_id` | str | 请求唯一标识（幂等键） |
| 模型 | `semantic_model_key` | Optional[str] | 语义模型 Key |
| 模型 | `report_template_key` | Optional[str] | 报表模板 Key |
| 意图 | `current_intent` | Optional[str] | 当前意图类型 |
| 意图 | `analysis_goal` | Optional[str] | 分析目标 |
| 分析 | `measures` | list[str] | 指标列表 |
| 分析 | `dimensions` | list[str] | 维度列表 |
| 分析 | `filters` | list[dict] | 筛选条件 |
| 分析 | `time_range` | Optional[str] | 时间范围 |
| 分析 | `sort` | Optional[str] | 排序方式 |
| 分析 | `top_n` | Optional[int] | Top N 限制 |
| 分析 | `comparison_mode` | Optional[str] | 对比模式 |
| 查询 | `last_query_plan` | Optional[dict] | 最近一次 QueryPlan |
| 查询 | `last_dax` | Optional[str] | 最近一次 DAX |
| 查询 | `last_query_result_id` | Optional[str] | 最近一次结果 ID |
| 查询 | `last_result_summary` | Optional[str] | 最近一次结果摘要 |
| 查询 | `last_report_id` | Optional[str] | 最近一次报表 ID |
| 澄清 | `clarification_pending` | bool | 是否待澄清 |
| 澄清 | `clarification_question` | Optional[str] | 待澄清问题 |
| 版本 | `memory_version` | int | 乐观锁版本号 |
| 版本 | `state_status` | MemoryStatus | pending/committed/failed |
| 时间 | `created_at` | datetime | 创建时间 |
| 时间 | `updated_at` | datetime | 更新时间 |
| 标记 | `is_mock` | bool | Mock 标记（不可作为真实结果） |

### 2.4 记忆状态机制

**固定三态：`pending`、`committed`、`failed`**

```
      ┌─────────┐
      │ pending  │  ← 每轮开始
      └────┬─────┘
           │
     ┌─────┴──────┐
     │ 完整成功？   │
     └──┬──────┬───┘
   yes  │      │  no
        ▼      ▼
  ┌─────────┐ ┌─────────┐
  │committed│ │ failed   │
  └─────────┘ └─────────┘
```

### 2.5 记忆提交机制

**只有满足完整成功边界时，才能提交 committed memory。**

完整成功边界至少要求：
1. 意图有效（非 unsupported）
2. 请求未被拒绝
3. 查询计划有效
4. DAX 校验成功
5. 工具执行成功
6. 查询结果校验成功
7. 最终回答或 ReportSpec 成功
8. memory_version 未冲突
9. 非 Mock 结果

M0.2 已将这些准入条件固化为 `MemoryPolicies.check_commit_eligibility()`。

**提交前校验：**
- 通过 `MemoryPolicies.check_commit_eligibility()` 检查
- 检查 `request_id` 幂等
- 检查 `memory_version` 乐观锁

### 2.6 一致性规则

| 场景 | 规则 |
|------|------|
| 重复请求 | `request_id` 幂等，返回已有结果 |
| 并发冲突 | `memory_version` 乐观锁拒绝写入 |
| 失败轮次 | 不污染 committed memory |
| 原始消息 | 不可变（append-only，L1） |
| 结构化状态 | 版本化（`bump_version()`） |
| 用户纠正 | 记录旧值和新值 |
| 切换语义模型 | 清理旧模型状态（措施、维度、筛选、时间、DAX、查询结果） |
| 切换报表模板 | 保留分析条件，清理旧 ReportSpec |
| "重新开始" | 清空工作记忆，保留审计（conversation_id 和历史记录不丢） |
| clarification | 不允许提交为 committed |
| unsupported | 不提交分析状态 |
| Mock 结果 | 不可标记为真实业务结果 |
| failed → committed | 禁止 |

### 2.7 Context Assembly 契约

**上下文只允许包含：**
- 系统规则
- 当前用户输入
- committed structured memory
- 最近 5 轮消息
- 滚动摘要
- 相关 Schema 子集
- 当前模型与模板
- Mock/真实标识

**上下文禁止包含：**
- 全部历史对话
- 完整 Schema
- 大量原始查询结果
- Secret（API Key 等）
- failed/pending 状态
- 与当前模型无关的数据

### 2.8 实现位置

- `backend/app/memory/models.py` — StructuredWorkMemory、MemoryStatus
- `backend/app/memory/repository.py` — MemoryRepository 抽象接口
- `backend/app/memory/policies.py` — MemoryPolicies 策略集合

---

## 三、模块边界

### M0.2 完成内容

- IntentSpec 完整 Pydantic 模型（含四类意图）
- IntentService 抽象接口
- 四层记忆设计文档
- StructuredWorkMemory 完整数据契约
- 三态机制（pending/committed/failed）
- 记忆提交准入条件（MemoryPolicies）
- request_id 幂等 + memory_version 乐观锁
- 上下文切换策略（模型切换、模板切换、重新开始）
- Context Assembly 契约
- MemoryRepository 抽象接口
- 65 个单元测试全部通过

### M0.3 边界

- 在 Harness 和 TurnController 中强制执行记忆提交准入
- Context Builder 基于契约实现
- 实现内存 MemoryRepository

### 后续轮次边界

- M1+：SQLite 持久化实现
- M3-M4：滚动摘要生成、长对话管理

---

*最后更新：2026-08-14 | M2.6.4 Intent/Grounding/Memory 权威边界同步*
