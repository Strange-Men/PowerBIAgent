# 03 — 意图识别与记忆系统

> **状态：** M2.6.4；Intent 仍保留，canonical semantics 由 ADR-008 Grounding/StateTransition 决定
> **关联 ADR：** ADR-002、ADR-005、ADR-008、ADR-009（ADR-001 已 superseded）

---

## 一、意图识别

### 1.1 设计目标

Agent 在接收用户输入后，先完成可独立测试的 IntentSpec。Intent 只负责分类与语言 weak signal，不拥有 Measure、Dimension、Filter Field、runtime Member、TimeRange 或其他 canonical business semantics；这些槽位只能由 ADR-008 的 Grounding/StateTransition 确定。

### 1.2 固定四类基础意图

| 意图 | 枚举值 | 说明 | 后续动作 |
|------|--------|------|---------|
| 数据问答 | `data_question` | 用户查询 Power BI 数据 | 进入 authoritative Grounding → Canonical QueryPlan → deterministic execution |
| 报表生成 | `report_generation` | 用户请求报表输出 | 先经过同一 Grounding/Fact boundary；正式模板渲染属于 M3 |
| 澄清 | `clarification` | 信息不足，需要向用户确认 | authoritative incomplete grounding 可更新非提交 PendingClarificationContext；不执行查询、不提交正式 Memory |
| 拒绝 | `unsupported` | 明确破坏性、越权或产品范围外请求 | 确定性 early-stop；data-shaped 请求不得仅凭 LLM 判定绕过 Grounding |

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
- `detected_*` 只作为当前输入的 weak signal / diagnostic，不能覆盖 Catalog、runtime metadata、runtime member lookup 或确定性时间规则
- deterministic exact canonical / approved alias / runtime metadata match 优先；bounded LLM selector 只能返回 Catalog-owned candidate ID、`AMBIGUOUS` 或 `UNRESOLVED`
- 候选无足够唯一区分证据、未知业务术语或非法 candidate ID 必须 fail closed / clarification，不得把“最像”提交为 canonical truth
- 意图结果不能直接提交 committed memory
- 只有完整成功轮次才允许提交状态

### 1.5 实现位置

- `backend/app/intent/models.py` — IntentType、FilterSpec、IntentSpec（含 `extra="forbid"` 和跨字段验证）
- `backend/app/intent/service.py` — IntentService 抽象接口（M1.2 扩展关键字参数）
- `backend/app/intent/context.py` — IntentContextSnapshot（M1.2 白名单上下文提取）
- `backend/app/intent/prompt.py` — 集中式 Prompt 构造（M1.2）
- `backend/app/intent/deepseek_service.py` — DeepSeekIntentService（M1.2 真实实现）
- `backend/app/query_plan/` — 历史 DeepSeek QueryPlan 草稿兼容 + 当前 Business Semantic Catalog、Grounding、StateTransition 与 Canonical QueryPlan authority
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

**Mock 与真实模式隔离及当前 Chat 状态：**
- `DeepSeekIntentService` 不使用 `MockScenarioResolver`
- 真实模式不调用 Mock Provider
- Mock 模式继续完整可用（通过 `MockScenarioResolver`）
- `/api/v1/chat` 已支持 Mock+Mock、DeepSeek+Mock 与 DeepSeek+Local MCP + Power BI Desktop；三种模式共用正式 TurnPipeline，Remote MCP 仍 Deferred
- Real 路径在 Intent 后进入 runtime schema / Catalog Grounding；Real DAX 与 factual Answer/ReportSpec 不由 Intent LLM 或 QueryPlan LLM 决定

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

#### PendingClarificationContext（独立于三态正式 Memory）

多轮澄清链保存在 Repository 管理的 `PendingClarificationContext` 中，只包含 chain identity、已权威解析/仍缺失的 slots、固定意图、model/fingerprint 与 provenance。它没有 `MemoryStatus`、DAX、QueryResult 或 commit evidence，不进入 committed version chain，也不能形成可执行 QueryPlan。只有 missing slots 全部补齐后，当前明确语义才可进入正常 Grounding/StateTransition；其后仍须完整执行成功才能提交正式 Memory。

### 2.5 记忆提交机制

**只有满足完整成功边界时，才能提交 committed memory。**

完整成功边界至少要求：
1. 意图有效（非 unsupported / clarification）
2. 请求未被拒绝
3. Grounding/StateTransition 已形成受支持的 Canonical QueryPlan
4. Deterministic DAX 与 Independent Layer 3 成功
5. ToolGateway / Power BI 执行成功
6. QueryResult 与 VerifiedFactSet 构建成功
7. fact-bounded Answer 或 ReportSpec 成功
8. memory_version 未冲突
9. Mock/Real runtime space 与 `source_mode` 一致；Real 不得读取或提交 Mock 结果

`MemoryPolicies.check_commit_eligibility()` 固化基础提交准入；当前 TurnPipeline / MemoryCommitEvidence 进一步要求上述 Grounding、执行与事实链全部成功。

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
- `backend/app/memory/models.py` — PendingClarificationContext（非 committed Memory）
- `backend/app/memory/repository.py` — MemoryRepository 抽象接口、committed/pending 隔离存取
- `backend/app/memory/policies.py` — MemoryPolicies 策略集合

---

## 三、当前模块边界

- IntentSpec、IntentService、StructuredWorkMemory、MemoryPolicies、Repository、幂等与乐观锁已经实现；TurnPipeline 是唯一写入控制面。
- ADR-008 的 Grounding/StateTransition 是 canonical semantic slot authority；Intent 和历史 QueryPlan LLM 不能直接写入正式状态。
- PendingClarificationContext 与 committed Memory 分离；歧义、未解析、unsupported capability 或任一下游失败均不得污染 last successful state。
- ADR-009 要求 DAX、Layer 3、QueryResult、VerifiedFactSet 与 factual output 全部成功后才允许 commit。
- 当前 Repository / Snapshot 为单进程实现；SQLite 或其他持久化介质、滚动摘要与长对话管理属于 M4，不在 M2 内扩展。

---

*最后更新：2026-08-14 | M2.6.4 Intent weak signal、Pending/Committed 与 successful commit 边界校准*
