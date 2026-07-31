# ADR-002 — 记忆系统与存储方案

- **状态：** accepted
- **日期：** 2026-07-31
- **决策者：** PowerBIAgent 项目组

---

## 一、Context

记忆系统是 PowerBIAgent 的核心卖点。需要设计一套可靠的结构化记忆系统，支持：

1. **四层记忆设计** — 原始对话、结构化工作记忆、滚动摘要、查询产物
2. **可靠提交** — 只有完整成功轮次才能提交记忆
3. **幂等和乐观锁** — request_id 幂等 + memory_version 乐观锁
4. **上下文切换** — 模型切换、模板切换、重新开始
5. **Context Assembly** — 上下文只加载 committed 状态的必要信息

## 二、候选方案

### 方案 A：完整 SQLite + SQLAlchemy

- SQLite 持久化，SQLAlchemy ORM
- 支持复杂查询、索引、事务
- 适合生产环境

### 方案 B：内存字典 + JSON 文件

- 纯内存操作，JSON 文件备份
- 无外部依赖
- 适合 MVP 快速验证

### 方案 C：Pydantic 模型 + Repository 接口（延迟持久化）

- 先用 Pydantic 定义完整数据契约
- Repository 抽象接口分离持久化实现
- M0.2-M0.3 使用内存实现
- M1+ 替换为 SQLite 实现

## 三、比较

| 维度 | SQLAlchemy ORM | 内存字典 + JSON | Repository 接口 |
|------|---------------|----------------|----------------|
| 实现复杂度 | 高 | 低 | 中 |
| 数据完整性 | 高（事务） | 低 | 接口保证 |
| 测试便利性 | 中（需数据库） | 高 | 高（可 Mock） |
| 迁移成本 | 低（已持久化） | 高（需重写） | 低（换实现） |
| MVP 适配 | 过度设计 | 太简单 | ✅ 刚好 |
| 本轮工作量 | 大 | 小 | 适中 |

## 四、Decision

**选择方案 C：Pydantic 数据契约 + Repository 抽象接口，M0.2 不实现 SQLite 持久化。**

核心理由：

1. **数据契约先行** — Pydantic 模型在 M0.2 固化，后续实现不变
2. **Repository 抽象** — 接口与实现分离，可渐进升级
3. **MVP 节奏** — M0.2 聚焦设计，持久化在 M0.3/M1 按需实现
4. **测试友好** — 接口可 Mock，Golden Cases 可直接验证

## 五、四层记忆设计

### L1：原始对话记忆

- 完整消息历史（用户 + 系统）
- 不可变（append-only）
- Context Assembly 仅取最近 5 轮

### L2：结构化工作记忆 (StructuredWorkMemory)

- Pydantic 模型，包含意图、指标、维度、时间、筛选等
- 三态：pending / committed / failed
- 只有 committed 状态参与 Context Assembly

### L3：滚动摘要

- 长对话的压缩摘要
- 定期由 LLM 生成（或规则合并）
- 超出最近 5 轮的上下文通过摘要注入

### L4：查询产物记忆

- QueryPlan、DAX、QueryResult 摘要、ReportSpec
- 关联到 request_id
- 用于审计和 Trace

## 六、状态机与准入

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

准入条件（M0.2 固化，M0.3 Harness 强制执行）：

1. 意图有效（非 unsupported）
2. 请求未被拒绝
3. 查询计划有效
4. DAX 校验成功
5. 工具执行成功
6. 查询结果校验成功
7. 最终回答或 ReportSpec 成功
8. memory_version 未冲突
9. 非 Mock 结果

## 七、幂等与乐观锁

### request_id 幂等

- 每个请求生成唯一 `request_id`
- 相同 `request_id` 的重复请求返回已有结果，不重复执行

### memory_version 乐观锁（M0.3.2 固化）

- `base_memory_version`：开始本轮时读取到的 committed 版本（0 = 无历史）
- 提交时 Repository 原子检查 base 与当前会话最新 committed 版本
- 匹配成功则 `memory_version = base + 1`
- 版本检查和递增在同一临界区完成
- `version_matches` 由 Repository 原子提交时设置（调用方不可伪造）
- 冲突不得覆盖现有 committed memory
- request_id 索引使用 `(runtime_mode, request_id)` 复合键
- Mock 和 Real 相同 request_id 可以共存

## 八、一致性规则

| 场景 | 规则 |
|------|------|
| 重复请求 | request_id 幂等，返回已有结果 |
| 并发冲突 | memory_version 乐观锁拒绝 |
| 失败轮次 | 不污染 committed memory |
| 原始消息 | 不可变（append-only） |
| 结构化状态 | 版本化（bump_version） |
| 用户纠正 | 记录旧值和新值 |
| 切换语义模型 | 清理旧模型状态，递增版本 |
| 切换报表模板 | 保留分析条件，清理旧 ReportSpec |
| 重新开始 | 清空工作记忆，保留审计 |
| clarification | 不允许提交为 committed |
| unsupported | 不提交分析状态 |

## 九、Context Assembly 契约

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

## 十、Consequences

**正面：**
- 数据契约清晰，测试可验证
- 接口与实现分离，渐进升级
- 三态机制确保记忆质量
- 准入条件可逐项验证

**负面：**
- M0.2 没有持久化，重启丢失数据（MVP 阶段可接受）
- 后续需实现 SQLite 持久化

## 十一、Risks

| 风险 | 缓解措施 |
|------|---------|
| 准入条件过严导致有效记忆被拒 | 条件可配置，Golden Cases 回归验证 |
| 乐观锁冲突频繁 | 当前单用户场景预期冲突极少 |
| 摘要质量影响长对话理解 | 滚动摘要策略可迭代优化 |

---

*创建日期：2026-07-31 | M0.2 智能体架构与记忆设计*
*最后更新：2026-07-31 | M0.3.2 工具网关与并发闭环修正*
