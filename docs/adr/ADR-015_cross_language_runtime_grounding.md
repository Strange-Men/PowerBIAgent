# ADR-015 — Cross-language Runtime Grounding

- **状态：** accepted
- **日期：** 2026-08-31
- **决策者：** 用户明确批准 M5.8.4
- **适用阶段：** M5.8.4；不启动 M5.9/M5.10

## 背景与复核

正式链已具有 runtime schema、immutable ModelSemanticContext、SemanticCatalog 和 bounded selector，却在调用 selector 前要求最长公共子串及唯一最高字面分数。中文与英文对象无重叠时候选为空；维度弱草稿翻译成 canonical name 后又被 current-input substring 过滤，可能错误继承旧维度。selector 没有消费已有 table/type/display/format/relationship/hierarchy evidence。Intent prompt 和 service 多处把选择模板等同于本轮生成报表。

## 决策

1. Power BI Semantic Model = structural/factual object authority。QueryResult/VerifiedFactSet 继续是结果事实 authority。
2. ModelSemanticContext = per-model immutable normalized semantic evidence；不建立第二份项目侧模型。只消费 MCP 已提供且经 Adapter 验证的 metadata；AI Instructions、AI Data Schema、synonyms、linguistic schema 缺 wire evidence 时继续为空。
3. SemanticCatalog/Grounding = canonical binding authority。exact canonical/qualified/display/description/validated alias 与确定性冲突仍优先；跨语言选择使用同一个 Catalog 的角色约束候选，不能以语言字符串无 overlap 提前排除。候选必须有数量/大小上界，超出预算 fail closed，不截取第一页假装唯一。
4. LLM = bounded linguistic interpretation only。复用 LLMTask.SEMANTIC_SELECTION，只能输出已有 candidate ID、AMBIGUOUS 或 UNRESOLVED。当前用户语言和 runtime metadata 决定语义；不得强制选择、凭唯一候选猜测、生成对象/成员/日期/事实。代码校验返回 ID 的当前 catalog membership、角色和 canonical ownership。QueryPlan LLM 仍为 weak draft；其翻译后的对象名不直接取得 binding 权限。
5. Current explicit > compatible committed canonical bindings。跨语言维度/筛选先解析当前要求，不能先借用旧维度覆盖新要求。member 仍必须通过当前 model/field runtime lookup；unknown/ambiguous ZERO DAX，失败不提交 Memory。
6. 模板选择不是意图。Router/当前报表语言确定 report request；只有 report intent 执行既有 Template Required Gate。Data turn 不携带旧/当前选择模板进入 canonical data plan。Report renderer、registry、数据计划及事实边界不改。
7. Presentation localization = display only，不回流到输入 Grounding。optional override 仅补企业专有词，保留 exact identity/fingerprint/stale fail-closed。
8. 不增加缓存，不修改 M5.8.1 session reuse/cache/singleflight，不改变 Provider、DAX、QueryResult、VerifiedFactSet 或 Memory factual authority。
9. QueryPlan 语言提取失败不等于用户省略筛选/时间，禁止构造空草稿后执行部分 Intent。QueryPlanError 在 Grounding/DAX 前 validation_failed；Intent 恢复仍必须获得有效 QueryPlan 草稿。该安全收紧替代旧“空草稿仍执行”的测试假设，不赋予草稿 canonical authority。
10. 关系证据明确标注当前字段端点的 active/cardinality/related ID；不能仅凭关系把外键替换为维表键或剪掉合法候选。并列成员只验证出子集时停止，不能用已知部分代表完整要求。

本 ADR 部分 supersede ADR-008 中“每个真实模型必须维护 glossary”及“字面分数必须预先唯一”的实现限制；ADR-008 的 runtime/member/slot authority 与 fail-closed 保持有效。legacy build_from_data 仅为已有离线 fixture 兼容入口，不成为正式生产 fallback。复用/扩展现有实现，删除冗余 description exact 和字面候选评分，不增加 planner、catalog 或平行 Grounding。

## 证据与适用性

- [Microsoft semantic model preparation](https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-semantic-models)：名称、description 和模型设计是语言解释的重要 metadata；不意味着本项目获得 Copilot 的隐藏能力。
- [Microsoft Power BI Modeling MCP](https://github.com/microsoft/powerbi-modeling-mcp)：工具实际 wire contract 才是本地能力依据；不能由 TOM/产品文档推定已暴露 AI 专用属性。
- 本地 source reproducer 与正式 Chat API/Real PBIX 形成验收依据，语言理解有不确定性，不能声称仅凭 ID 白名单即可数学证明自然语言含义。

## 验收与后果

中英双向、同义表达、八 shapes、KEEP/REPLACE、unknown/ambiguity、mutation/stale、A→B→A、Report→Data→Report 和双 Provider canonical 一致性必须覆盖。fixture 证明控制面合同，Real 证明真实语言解释；二者不能互相冒充。记录 cold/warm/4-way 与增加的 selector 调用，不能缓存结果伪造性能。metadata 不足或候选预算超限仍澄清，不承诺所有 PBIX/所有语言绝对自动理解。
