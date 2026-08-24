# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-24

## 当前阶段

**M5.4 — 多会话并发、用户设置与资源管理最终收口已完成。** M0–M4 后端保持封板与 FINAL PASS；M5.0—M5.4 已完成；M5.5 继续 Deferred。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 series | 会话/报表恢复与 metadata authority 最终收口 | ✅ FINAL PASS |
| M4.3 | Conversation History / Search API | ✅ 完成 |
| **M4.4** | **Restart / Crash Acceptance & M4 Final Closure** | **✅ M4 FINAL PASS** |
| **M4.4.1** | **Memory corruption fail-closed + README/document closure** | **✅ FINAL PASS** |
| **M4.4.2** | **M0–M4 truth / persistence boundary final closure** | **✅ FINAL PASS** |
| **M5.0** | **前端设计与契约固化** | **✅ 已完成** |
| **M5.1** | **React 前端实现与核心联调** | **✅ 已完成** |
| **M5.2** | **真实业务链路与前端逻辑收口** | **✅ 已完成** |
| **M5.2.1** | **模型能力边界与真实模式说明收口** | **✅ 已完成** |
| **M5.3** | **结构化结果与前端最终收口** | **✅ 已完成** |
| **M5.3.1** | **多 PBIX 绑定与展示事实边界最终加固** | **✅ 已完成** |
| **M5.3.2** | **Local MCP 多模型选择与协议稳定性加固** | **✅ 已完成** |
| **M5.3.3** | **多轮语义、会话资源生命周期与 Artifact Governance** | **✅ 已完成** |
| **M5.4** | **多会话并发、用户设置与资源管理最终收口** | **✅ 已完成** |
| **M5.5** | **语义/中文字段/视觉/性能** | **⏸ Deferred / NOT STARTED** |

### M5.4 root-cause baseline（代码修改前）

- `usePowerBIAgent()` 仅维护一组全局 `messages / activeConversationId / sending / loadingConversation / error`，把“当前展示哪个会话”与“哪个会话正在执行”错误合并。
- 新聊天在后端返回 conversation ID 前没有稳定 local identity，因此无法立即出现于 Sidebar，也无法让 A pending 时 B/C 独立发送。
- M5.3.3 已为 history navigation 建立 abort/generation/active identity 保护，但 business chat 仍绑全局 sending/messages，不能表达不同 conversation 同时 pending。
- 当前 Sidebar 使用长 recent list，用户卡片纯展示；批量 conversation/archive/report 管理、report rename 和 deleted tombstone 尚未实现。

### M5.4 approved implementation contract

- 使用 `conversation_id → ConversationSession` 隔离 messages/pending/sending/history/error/status；active ID 只决定当前可见 session。
- 新会话首次发送由前端生成合法 UUID，同一 ID 直接传给 Chat API；Sidebar 立即合并 local pending row。
- 不同 conversation 允许并发，同 conversation 保持串行。history fetch 可取消，business chat 归属 conversation，切窗不取消也不自动回跳。
- 用户卡片打开设置/已归档/资源管理；Sidebar recent/report 独立滚动与折叠，批量 checkbox 只在资源面板。
- 批量操作最多 20 项，协调正式单资源 API 并呈现 partial failure；不增 `DELETE ALL`，不绕过 durable delete，archive ≠ delete。
- report delete 保留 presentation tombstone；report `display_title` 只是 presentation metadata，report_id/HTML/content_hash/ReportSpec/VerifiedFactSet 不变。LLM/ToolGateway 无 rename/delete 权限。
- M5.5 语言理解、Localization Registry、单指标展示、HTML 视觉与性能继续 Deferred。

### M5.4 — 最终实现与验收

- `usePowerBIAgent()` 以 `conversation_id → ConversationSession` 保存 messages、pending request、sending、history、error 和 status；active ID 仅选择可见会话。首次发送使用前端 UUID 作为正式 Chat identity，pending row 无需等待后端。
- business chat 不携带 navigation Abort signal，按 owning conversation 回写；不同 conversation 可同时运行，同 conversation 由 running guard 串行。history 继续使用 AbortController/generation/active identity，后台完成不切换当前窗口。
- 用户卡片提供设置/已归档/资源管理入口；最近对话与报表可折叠，recent 独立滚动。资源面板最多选择 20 项，通过单资源 API 协调批量删除/恢复，并逐项保留 partial failure。
- `report_presentations` 与 migration `a4f6b8c2d190` 保存 `display_title`/availability。PATCH 只改 presentation title；delete 仍清理 HTML/factual metadata 并保留 transcript tombstone。conversation delete 会清理同 namespace presentation row；接口不注册 ToolGateway。
- Rich PBIX Real A/B/C 并发结果分别为总销售额 `6,943,997.51`、四区域销售表、总销量 `3,065`；pending/loading/result 均隔离且无自动跳窗。归档恢复、report rename、delete 后 reload/history tombstone 无 view/download 均通过。
- 本轮 9 个 Real acceptance conversation 与关联 report 通过正式单资源 API 精确清理。一个此前无 DB ownership 的 `test01.html` 未删除，已可恢复归档到 `local_state/archive/m54_preexisting_orphan_20260824/`，Artifact Governance PASS。
- Fresh evidence：backend `1790 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `61 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `117`、Repository Safety `290`、Error Ledger `25`、Documentation Governance、Artifact Governance、`git diff --check` PASS。
- M0–M5 factual/Memory/VerifiedFactSet/Report authority 未改变；M5.5 未开始；不合并 main，不创建 Tag。

### M5.3.3 root-cause baseline（代码修改前）

- 真实浏览器 conversation `2704941c-…` 的五轮证据显示：前五轮全部 `completed` 且 `memory_commit=true`。第 2 轮 `2025年5月销售额多少` 的 committed `time_range` 仍为 2026-08 current_month；第 3 轮虽正确解析 Region/Top3/desc，仍 KEEP 该时间；预测与 PBIX Measure 修改又分别把同一旧 plan 提交为 Memory v4/v5。
- `TimeGrounder` 仅识别本月/今年/去年/最近数字月/两个 ISO date，无法消费 LLM 的结构化当前时间语义；未识别的当前表达被当成 NOT_MENTIONED。
- `StateTransitionService` 对同 conversation 的所有未指定 slot 默认 KEEP，没有 fresh/follow-up/replace 决策，因此自包含新问题机械继承旧 time/filter/dimension/sort/top_n。
- Intent 与 QueryPlan Prompt 都注入全部 committed slot，LLM 可能重复旧槽；Grounding 已有部分 current-literal 防腐，但无法纠正“当前时间未识别 + 默认全量继承”的组合。
- `should_defer_unsupported_to_grounding()` 明确以 `committed is not None` / pending 为放行条件，导致 LLM 已识别 unsupported 的预测/写请求仍进入 data pipeline。
- 前端 `openConversation()` 在 history 完成后才设置 active ID，且无 AbortController/generation/identity re-check；慢 A response 可在用户已切 B/new/archive/delete 后覆盖 messages/title/report attachment。
- 后端 report history 已按 `(source_mode, conversation_id)` 查询，未发现跨 namespace predicate；A/B 串窗当前证据指向前端 stale response/state lifecycle。

正式实现契约见 `docs/specs/12_conversation_memory_and_resource_lifecycle_contract.md`。

### M5.3.3 — 最终实现与验收

- Intent 新增 bounded `turn_relation` 与 `TimeIntentDraft`；deterministic resolver 处理绝对月、去年五月、上个月、季度、最近月/半年与受限范围。runtime schema/glossary/members 和 validators 继续拥有 canonical authority。
- `TurnInheritancePolicy` 将 fresh/follow-up/replace 分离：自包含新问题清除旧 time/filter/dimension/sort/top_n；明确追问或替换只继承兼容省略项；证据不足 clarification；semantic model 切换清空旧模型语义上下文。
- readonly unsupported preflight 在 LLM/Memory/Grounding/DAX 前拒绝预测、PBIX/Measure 写操作、删除数据和任意代码；terminal Snapshot 保留审计，Memory 不提交。
- archive 从 recent 隐藏但保留 conversation/history/report/HTML，并通过 archived/restore API 恢复；独立 `DELETE /api/reports/{report_id}` 使用 durable report delete intent 精确清理 metadata/cache/HTML，conversation 保留，且不注册 ToolGateway。
- history 只恢复 exact `(source_mode, conversation_id, request_id, report_id)` ownership；前端使用 AbortController + generation + active ID + response ID 四重检查，open/new/delete/archive/model switch 使旧 history 失效。
- local_state 固定四目录；Artifact Governance 检查 ownership residual、cleanup failure/pending、orphan/mismatch、unauthorized entry 与 source-tree runtime artifact。pytest 默认 report root 改为 per-test 临时 ownership，teardown 后验证清理。
- Rich PBIX Real 八轮：本月、2025-05、Top3 Region、华南 follow-up、去年 replace、预测 unsupported、PBIX 修改 unsupported、report generation 全部符合契约；archive/restore、独立 report delete（对话保留）、再生成后 conversation cascade delete、A/B 快速切换均通过。
- Fresh 验证：backend full `1789 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `49 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `117`、Repository Safety `287`、Error Ledger `25`、Documentation Governance、Artifact Governance 与 `git diff --check` PASS。

### M5.3.2 — Local MCP 多模型选择与协议稳定性加固

- `PowerBILocalMCPClient` 将 beta.12 `ListLocalInstances` raw payload 严格转换为内部 typed identity；后端使用 PID、local data source 与 start time 的 canonical identity 经进程内密钥 HMAC-SHA-256 生成 `local_desktop:<opaque-id>`。display name 不参与 identity；API/前端不暴露 PID、端口、connection string、raw fingerprint 或 MCP payload。
- discovery 返回所有当前 Desktop option。每个 option 的 compatibility 都执行精确绑定 probe；schema/member/DAX 的每个新 stdio session 都重新 `ListLocalInstances → opaque key 唯一匹配 → Connect → session connectionName`，不存在 `instances[0]`、display-name guess 或其他 PBIX fallback。
- Desktop 重启/关闭、后端进程重启或 identity 变化使旧 key stale；schema/member/DAX deterministic fail closed。前端刷新目录、清空失效选择并要求重选，不持久化 instance registry，不自动切换剩余模型；重复 display name 只显示“实例 1/2”。
- 固定 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`。只读 capability probe 覆盖 server startup、protocol、required tools、ListLocalInstances、Connect、schema List/Get，以及 `EVALUATE ROW("__pbiagent_probe", 1)` 的列、一行和值；结果不进入 Memory、Snapshot 或业务 Trace。
- DAX wire 请求使用 `request.max_rows + 1` sentinel，并验证实际 columns/rows/rowCount 与 wire limit。显式 truncation/limit metadata 映射到 `QueryResult.truncated`；无完整性证明且触及上限时保守 truncated，不做任意 DAX 分页，VerifiedFactSet 既有 truncated 语义不变。
- `sales_report` 的 registry 逻辑 binding 与 opaque instance resource identity 显式分离；TemplateContract、deterministic queries、VerifiedFactSet、renderer 与 M0–M4 factual/Memory/Report authority 未改变。无 migration，Remote MCP 继续 Deferred。
- Real Smoke：同时打开 `PowerBIAgent_M3_Rich_Test.pbix` 与 `PowerBIAgent_M3_Test.pbix`，safe API 同时返回两个 unique/selectable option；两者 probe/schema/DAX 均成功，模型专属查询证明不串实例；浏览器可分别单选，Rich 问答、表格/柱状图与 HTML 报表成功。关闭 Rich 时 Desktop 显示未保存更改确认且检测到用户输入，因此未强制丢弃本地状态；live stale-shaped key 与 fake disappearance 回归均验证下一请求 fail closed。
- Fresh 验证：backend full `1760 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `39 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `116`、Repository Safety `280`、Error Ledger `25` PASS。Settings.version 为 M5.3.2；frontend version 为 5.3.2。

### M5.3.1 — 多 PBIX 绑定与展示事实边界最终加固

- 根因：Local MCP discovery、schema、member lookup 与 DAX 分别建立 stdio session，每次都重新执行 `ListLocalInstances → instances[0] → Connect`。多个 Desktop 同时打开时，不同阶段可能连接不同 PBIX，形成“数据真实但来源模型错误”的 P0 风险。
- Local MVP 采用最小唯一实例 contract：每个 session 的 `ListLocalInstances` 必须恰好返回一个 Desktop 实例；0 个保持 `powerbi_desktop_not_connected`，多个在 `Connect` 前 fail closed 为 `powerbi_multiple_desktop_instances`。不按顺序或 display name 猜测，不新增 instance registry。
- discovery/schema/member/DAX 共用同一检查；单实例 Rich 路径不变。前端对多实例显示自然语言提示并禁止发送，不暴露连接 identity 或 MCP raw payload。
- stdio 关闭可将受控 Desktop 错误与 cleanup 错误组合为 `ExceptionGroup`；分类器现会保留 `DESKTOP_NOT_FOUND` / `DESKTOP_CONNECTION` 中的安全错误码，避免多实例被上层归一为通用 discovery unavailable。
- `PresentationDataset` 不再复制完整 QueryResult；只按 scalar/grouped/ranking/min/max VerifiedFact `source_fields` 保持 QueryResult 原顺序投影 columns/rows。metric/table/chart 全部引用该 verified dataset，额外列不进入 presentation，row/column shape mismatch 继续 fail closed。
- 正式 PRD 已同步 M5.3 presentation、transcript/title/rename/delete、metric/table/bar/line/report attachment 与 Rich PBIX acceptance；comparison/YoY/arbitrary trend、Remote MCP、多租户/RLS 等仍 unsupported/deferred。
- Settings.version 为 M5.3.1；frontend version 为 5.3.1。无 migration，无 M0–M4 authority 变化，无后续里程碑扩展。
- Fresh 验证：backend focused `98 passed`，backend full `1743 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `34 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `116`、Repository Safety `280`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。
- Real Smoke：Rich 单实例 discovery 为 compatible/selectable，简单问答、表格、报表均成功；同时打开第二个 PBIX 后明确返回 `powerbi_multiple_desktop_instances`，关闭后 Rich 立即恢复。未修改或保存 PBIX。

### M5.3 — 结构化结果与前端最终收口

- 新增安全启动诊断：严格 `.env` 行格式只允许 `KEY=value`、注释和空行；CLI 与 `/health` 只输出模式、readonly、工具预算及 DeepSeek“是否配置”，不输出值或 Secret。
- discovery 在 ToolGateway 只读 schema 路径上执行当前 Semantic Catalog/glossary 最小兼容性构建；完整 fingerprint 仅标记 `schema_drift`，不单独阻断模型。只有缺少必需业务对象或对象类型冲突才返回 `incompatible` 并由 UI 禁用发送，不暴露 schema/hash/DAX。
- 新增 presentation-only transcript/title：terminal Snapshot 保存本轮 `user_message` 与 `presentation`；conversation 首个有效问题生成默认标题，支持 namespace-scoped PATCH 重命名。两者不进入 WorkMemory、Grounding、QueryPlan 或 VerifiedFactSet。
- 新增 `PresentationEnvelope`：每个 QueryResult 只保存一份 dataset，包含 verified fact linkage；动态 block 支持 text、metric、table、bar/line chart 与 report attachment，所有数据块只通过 `data_reference` 和字段名引用 dataset。
- Sidebar 支持搜索、完整历史恢复、重命名、归档、删除；报表按 conversation 管理，DELETE 继续复用 M4 durable delete intent 清理关联 managed HTML，没有独立 report delete API。
- 前端完成白色主区/浅灰 Sidebar、内容宽度、固定 Composer、折叠、菜单定位、表格横向滚动、图表尺寸、报表附件、hover/focus/loading/disabled/error/empty，以及 desktop/medium/small responsive 和 ESC/focus-visible/aria/keyboard 基础 accessibility。
- 已在浏览器验证 Rich PBIX Real `local_desktop` discovery；fingerprint drift 下保持 connected/compatible/selectable。六轮问答完成时间与区域筛选继承，真实表格与 HTML 报表生成、查看/下载、recent/history/search 均通过；测试 conversation 与关联 managed HTML 已经正式 DELETE API 精确清理。
- Alembic head 更新为 `d3b7f9a1c524`，仅增加 nullable conversation `title`；无 M0–M4 factual schema/authority 变化。
- Fresh affected backend regression：`335 passed`；frontend typecheck/lint/build PASS，Vitest `31 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `116`、Repository Safety `279`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。

### M5.2.1 — 模型能力边界与真实模式说明收口

- 根因：Mock discovery 直接遍历 `mock_schema.json` 的全部 fixture，并统一标记 `available=true/connected=true`；`SemanticModelOption` 与前端消费语义实际是可选择模型，因此 `mock_satisfaction_model` 被错误提升为正式业务能力。
- 修复：`MockPowerBIAdapter` 使用最小显式白名单，只向 discovery 返回 `mock_sales_model`。`mock_satisfaction_model` fixture 与直接 schema 读取能力保留，继续服务聚焦测试，但不进入前端目录。
- Real Local MCP discovery 未改，仍返回单一 `local_desktop_model` 安全选项；未新增 `selectable/supported` 字段，未扩大 API 或前端类型复杂度。
- 根 README 在快速开始顶部增加“本地 Power BI 真实模式启动”，明确默认 Mock、Real `.env` 键、启动顺序、SQLite 前提与 `/health`、`/api/v1/semantic-models` 检查；根 README 和 `frontend/README.md` 的普通标题与叙述统一为中文。
- Fresh 验证：discovery 聚焦 `5 passed`；PowerBI/semantic-models/health 受影响回归 `86 passed`；Mock pipeline `41 passed`；前端 Vitest `21 passed`，lint/typecheck/build 全部通过；Architecture Gate `111`、Repository Safety `270`、Error Ledger `25` 与 Documentation Governance 通过。
- 无 M5.3 视觉 polish，无 DB schema/migration，无 M0–M4 核心链重构；未创建 Tag。

### M5.2 — 完成状态与固化边界

- 数据模型不是前端固定“Power BI 销售数据”别名。浏览器不能读取 `.pbix`；后端通过 Local MCP / 当前 Desktop 实例发现和连接，前端只展示只读 discovery endpoint 返回的 safe catalog。
- `local_desktop_model` 仅保留为 M2 封板兼容的后端内部执行 identity，不再作为前端静态产品目录；当前 Local Adapter 一次只稳定连接一个模型时，UI 明确标记“当前已连接模型”。
- `report_template_key` 是 request-level 可选 override。删除“不使用模板”产品模式；未选择时不传字段，问答/多轮/报表由后端 intent 判断，report intent 仍可自动选择默认 `sales_report`。
- M5.2 负责 Real、Desktop discovery、SQLite conversation 配置、runtime/source namespace、真实多轮与 report、最小错误分类和结构化表格/图表契约审计。
- M5.3 才负责尺寸/间距、responsive、accessibility、loading/error/empty polish、表格/图表视觉和最终浏览器视觉收口。

### M5.2 实现与 Real acceptance

- 新增 `GET /api/v1/semantic-models`：API → `SemanticModelDiscoveryService` → read-only `ToolGateway` → `PowerBIAdapter` → Local MCP。响应只有 stable key、display name、source/type、availability/connected 与 runtime namespace，不返回端口、process ID、connection string、MCP raw payload、DAX 或 schema。
- 当前 Local execution contract 一次只选择并验证一个打开中的 Desktop 模型；前端动态加载 safe catalog，无模型时禁止发送并显示 Desktop/模型 empty state，不再伪造销售模型。
- `TemplateCatalog` 显式配置 registry-owned 默认 `sales_report`：只有后端已识别为 `report_generation` 且用户没有 override/明确模板时才使用；普通 Chat 不受影响，disabled/unknown template 继续 fail closed。
- Real 启动使用 `LLM_MODE=deepseek`、`POWERBI_MODE=local_mcp`、`PERSISTENCE_BACKEND=sqlite`、`MAX_TOOL_CALLS=8`。本地旧值 `MAX_TOOL_CALLS=3` 会在 full report 的第三个 DAX 前被 TurnController 拒绝；独立四查询均成功，改回正式预算后 generic report 执行 schema + 4 DAX + render 并 completed。
- 当前 Desktop schema 与 model-scoped glossary 的旧 fingerprint 不一致；只读兼容性检查确认所有 glossary object/type/visibility 仍匹配后，仅更新 fingerprint，未放宽 Semantic Catalog authority。
- Fresh Real 7-turn conversation 使用同一 conversation_id、不同 request_id，类别/筛选/指标切换/产品维度/Top2/未指定模板的 generic report 全部 `completed`、`memory_commit=true`、`source_mode=real`；report 自动选择 `sales_report`。recent/search/history(7 turns)/conversation report/view/download 均通过，report view/download 同源；dispose/restart 后 history/report/view 可恢复。
- 实际浏览器确认 Desktop display name、模板 catalog（无“不使用模板”）、recent/search/history、用户可理解错误消息与 ReportArtifact 附件。未强制关闭用户正在运行的 Desktop；Desktop absent 采用 Adapter/API/frontend safe fault-injection 回归，避免丢失未保存 PBIX。
- Chat/History 仍没有 QueryResult columns/rows、独立 metrics 或 ChartSpec。本轮不新增高风险事实 response adapter，不从 answer/audit 反解析；结构化表格/图表契约明确 defer 至 M5.3 前。
- Fresh gates：frontend typecheck/lint/build PASS、Vitest `21 passed`；backend `1708 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture Gate `111`、Repository Safety `270`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。

### M5.2 启动故障基线

- 以仓库当前默认启动配置复现：`/health` 为 Mock+Mock ready；conversation/search 因 `persistence_backend=memory` 返回 `503 conversation_history_requires_sqlite`。数据库文件存在不等于 SQLite provider 已启用。
- 同一配置下 Chat HTTP 200 但业务 `terminal_state=tool_failed`、`error_type=ToolPolicyDeniedError`、`memory_commit=false`；根因是前端默认 Real/`local_desktop_model` 与后端 Mock/`mock_sales_model` 不一致。HTTP 200 不是业务成功。
- M5.2 已让前端 runtime/model 来自后端 discovery，并完成 SQLite + DeepSeek + Local MCP 的显式 Real acceptance。

### M5.1 — React 前端实现与核心联调

- `frontend/` 已创建 React 19 + Vite 8 + TypeScript 6 工程，使用 hooks、普通 CSS、lucide-react、Vitest 与 Testing Library；无重型 Dashboard 框架、路由器或全局状态库。
- 已实现 AppShell、真实折叠 Sidebar、新聊天欢迎态、已有对话态、稳定底部 Composer、"+"数据模型/报表模板菜单与 DeepSeek-only 单选卡片。
- Chat adapter 发送 `conversation_id` / `request_id` / `semantic_model_key` / `report_template_key`，动态渲染 answer、clarification、unsupported、error、empty 与真实 ReportArtifact；不展示 trace/tool/audit/Memory/DAX/usage。
- recent/search/history/reports 已接现有 SQLite API。Conversation 请求显式 `runtime_mode`，report 请求显式 `source_mode`；History 只恢复 persisted structured result，并在 UI 明示不是逐字 transcript。
- 项目卡片与用户账户保持纯展示。M5.1 当时没有 discovery endpoint；该限制已由 M5.2 的只读 semantic-model discovery supersede，模板仍在 `src/config.ts` 集中登记。
- 报表查看/下载只使用与 `report_id` 严格一致的后端 canonical reference；无 report resource 时不显示附件。
- 最小契约缺口：Chat/History 不暴露 QueryResult `columns/rows`、独立 metrics 或 ChartSpec，`execution_audit` 也没有可消费 rows。M5.1 不修改 M4 Snapshot/Persistence，不从 answer/audit 推导事实，因此不渲染假表格/图表。
- Fresh gates：frontend typecheck/lint/build PASS，Vitest `13 passed`；Chrome 1600×1000 实际欢迎态检查 PASS；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture/Repository Safety/Error Ledger PASS。

### M5.0 — 前端设计与契约固化

- M5.0 已完成以下文档固化：
  - `frontend/README.md` — 从 M1.3.2 状态升级为 M5.0 文档，新增动态回答原则、左侧栏能力边界、"+"菜单映射原则、模型选择器 DeepSeek 唯一交互、后端能力到 UI 映射表、M5 路线三段、项目/账户仅展示
  - `docs/01_product_scope_and_frontend_skeleton.md` — 全面重构为 M5.0 骨架规范，AI 回答动态渲染原则代替固定内容序列，Composer 结构、模型选择器交互、"+"菜单映射、项目/账户仅展示，后端能力映射表
  - `docs/specs/10_frontend_visual_and_interaction_spec.md` — 更新动态渲染规范（8.4 节完全重写代替固定顺序）、模型选择器只显示 DeepSeek、后端能力到 UI 映射表、"+"菜单映射原则、禁止固定内容序列
  - `docs/specs/11_structured_answer_contract.md` — 重写为动态渲染框架，删除固定内容顺序，新增 frontend rendering flow concept、ChatResponse 映射表、场景-展示对应表、删除 M1.4/M3 历史边界（已由 ADR-009 supersede）
  - `docs/04_powerbi_mcp_and_api_contracts.md` — 同步 ChatResponse 已实现的 report 字段和前端组合回答状态
  - `docs/07_milestones_status_and_open_questions.md` — 补充 M5.0 状态行，待确认事项标记 M5 阶段
  - `docs/08_development_roadmap.md` — M5 拆分为 M5.0/M5.1/M5.2 三段路线
  - `docs/09_context_handoff.md` — 标记 M5.0 已完成，下一步为 M5.1
  - `README.md` — 同步 M5.0 状态
  - `CHANGELOG.md` — 新增 M5.0 条目

### M4.4.2 final boundary closure

- 根因：SQLite `_model_to_work_memory()` 在 `payload_json` 缺失时用 dedicated columns 构造 partial `StructuredWorkMemory`；columns 不含 filters/time/sort/top_n/last_query_plan 等完整 canonical state，可能把损坏 committed state 解释为更宽查询。
- 最终语义：modern committed WorkMemory 的完整 domain reconstruction authority 仅为 `payload_json`。NULL/empty、malformed JSON、字段不完整、domain validation failure 或 row/payload integrity mismatch 全部 fail closed；dedicated columns 仅为 query/index/integrity/support fields，不再替代 executable semantic state。无 legacy partial reconstruction contract。
- `MemoryRepository.get_latest_committed()` / `list_by_conversation()` 的 runtime namespace 在 ABC、InMemory、SQLite 与 production callers 中 mandatory；删除跨模式 aggregate 默认行为。InMemory exact conversation/request ID 跨 Mock/Real overwrite 已由 composite conversation-store key 修复。
- 最终 audit 发现并最小修复两个额外 P1：非 legacy committed time corruption 不再在 StateTransition 静默清空；terminal Snapshot row/payload request/conversation/fingerprint/terminal mismatch 不再通过 replay。未发现 P0；未做大重构或未来功能。
- M0—M4 semantic/DAX/fact/report/memory/snapshot/namespace/filesystem authority 保持封板模型；Real failure 不回退 Mock，history/persistence 不成为 factual authority，report HTML 继续只从 filesystem 恢复。

### M4.4.1 corruption boundary

- 根因：`StructuredWorkMemory.filters` 接受任意 `dict`，SQLite `model_validate()` 无法识别 semantic corruption；`StateTransitionService._previous_filters()` 又捕获 canonical parse failure 后 `continue`，导致损坏 filter 被解释为空并可能扩大下一轮查询范围。
- 修复：保持 `list[dict]` storage/legacy shape，但 domain validation 逐项调用 `StructuredFilter.model_validate()`；持久化损坏在 fresh repository load 时以 `committed_memory_filter_invalid:<index>` fail closed。StateTransition 对绕过初始 validation 的进程内损坏抛出 `CommittedMemoryCorruptionError`，禁止 skip/clear/default-empty。
- TurnPipeline 的 committed/pending load、context build 与 controller setup 现在复用 Owner abort-on-exception 语义；同一 request_id 在 corruption 后可重复得到确定性失败，不遗留永远等待的 process-local claim。
- 合法 committed filter 继续跨轮继承；已有 legacy time string contract 保持不变。无 persistence schema change、无 Alembic migration。
- 新真实临时 SQLite restart regression 使用 dispose + fresh engine/repository/service，参数化覆盖 Mock/Real。同 namespace 在 LLM、schema、DAX、Power BI 与下一 memory commit 前失败，version 保持 1；另一 namespace 的合法 filter 正常恢复。
- README 现固定为 value-first Landing Page；`AGENTS.md` 新增 README Maintenance Contract。正式 PRD 只同步实现状态，07/08/09 与 CHANGELOG 同步为 M4.4.1。

### M4.4 restart / crash authority

- terminal `result_snapshots` 是 request replay authority；durable Snapshot 已保存但 process-local tracker 尚未 complete 时，fresh runtime 直接 replay，不重复工具执行。
- process-local in-flight claim 不持久化；crash 后若无 Snapshot，不产生 fake completed。若同 request 已有 Memory 但缺 terminal Snapshot，表示结果/外部副作用无法安全确认，TurnPipeline 以 `IdempotencyCoordinationError` fail closed，不自动重执行，也不生成 terminal duplicate。
- committed Memory 按 `(runtime_mode, conversation_id)` 恢复并保持 version；Pending/Failed 不冒充 Committed。Mock/Real 同 conversation ID 持续隔离。
- SQLite/History/Snapshot 仍不是 business/result/report factual authority；M0—M3 truth chain 未改。

### Report recovery

- `report_artifacts` SQLite row/payload 继续只提供 strict metadata；HTML filesystem 是唯一内容 authority。
- 新 persistent `ReportResultSnapshot` 的 `html` 兼容字段为空；restart replay 通过 `ReportRepository.read_html()` 读取文件，并核对 report identity、template/contract/reference/content hash、conversation/request linkage 与 source mode。
- Adaptive Real report 路径现将实际带 `conversation_id/request_id` 的 `ReportSpec` 传给 ToolGateway；此前构造 context copy 后误传原对象的生产 bug 已由严格 replay 验收发现并修复。
- missing/tampered HTML、corrupt metadata 或 snapshot/artifact mismatch 均 fail closed。配置了 report repository 时，旧 snapshot 内可能存在的 HTML 也不参与重放 authority。

### History / Archive / Delete restart

- recent/history/search/reports 在 dispose + fresh engine/service 后与重启前一致；archive 状态保留，recent/search 默认隐藏，direct history/reports 继续遵守 M4.3 contract。
- Migration `c8d4e6f2a109` 新增 `conversation_delete_intents`：DB 删除 transaction 同时持久化 exact `(runtime_mode, conversation_id)` 的 report IDs/counts；HTML cleanup 成功后 service 才清除 intent。
- DB commit 后 unlink/finalize 失败或进程退出时，fresh service 的相同 delete 可从 intent 重试；pending intent 阻止 Memory/Snapshot/Report 在该 namespace 复活。成功 delete 后再 restart，DB state、intent 与关联 HTML 均已清理；另一 namespace 不受影响。
- 这是应用级 durable intent + idempotent cleanup，不声称 SQLite transaction 可原子覆盖 filesystem，也不声称硬件/文件系统违反自身 durability contract 时仍可恢复。
- Report create 仍是 atomic HTML write → metadata save，并在可观察的 metadata-save failure 上 best-effort unlink；M4.4 没有为进程恰在 HTML rename 后、metadata commit 前退出的窗口增加 durable create journal，因此不承诺自动回收该无引用文件。该窗口不会形成成功 metadata 或 terminal Snapshot，也不会被当作可恢复报表。

### Fresh acceptance

- 新增 7 个 restart/crash integration tests；每个 restart 路径都使用真实临时 DB/files、dispose、全新 engine/session/repository/service。
- 新增 1 个 M4.3 → M4.4 migration test；fresh DB → head 与 `f4c3a2b1907d` → head 均通过。
- Backend fresh regression：`1681 passed, 1 skipped`。
- Golden `11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- `backend/app/config/settings.py`：version → M4.4。
- M4 FINAL PASS；不新增 Tag。

### M4.4.1 fresh acceptance

- Targeted corruption regression：5 passed（StateTransition 3；真实 SQLite restart 2）。
- 邻近 Memory/StateTransition/persistence/restart：190 passed；backend full regression：1686 passed、1 skipped。
- Golden：11 passed、1 manual-real skipped；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- Alembic head 保持 `c8d4e6f2a109`；fresh DB → head 与 head → head 幂等 upgrade PASS，确认无新增 migration。
- `backend/app/config/settings.py`：version → M4.4.1。
- M4.4.1 无 migration；M5 NOT STARTED；不新增 Tag。

### M4.4.2 fresh acceptance

- Payload/namespace/audit targeted + adjacent suites：`607 passed`。
- Backend full regression：`1700 passed, 1 skipped`。
- Golden：`11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- Alembic head 保持 `c8d4e6f2a109`；fresh DB → head 与 head → head 幂等 upgrade PASS，确认无新增 migration。
- `backend/app/config/settings.py`：version → M4.4.2。
- M4.4.2 FINAL PASS；M5 NOT STARTED；不新增 Tag。

## 下一步

M5.4 已完成。下一步必须等待用户明确批准 M5.5；不得自行进入语言理解、中文字段、单指标、HTML 视觉或性能范围。

## 关键命令

```powershell
# Full test suite
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q --asyncio-mode=auto

# Persistence-focused
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests\unit\persistence -v --asyncio-mode=auto

# Golden
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# Alembic smoke（从空 DB）
D:\Conda\envs\PBIAgent\python.exe -m alembic upgrade head

# Gates
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_artifact_governance.py
```

## 本地启动（PowerShell 标准流程）

先执行一次 `conda init powershell`（首次使用），然后关闭并重新打开 PowerShell：

```powershell
conda activate PBIAgent
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

验证 Python 路径：`python -c "import sys; print(sys.executable)"` 应输出 `D:\Conda\envs\PBIAgent\python.exe`。

常见问题见 `README.md` 的"常见启动问题"。

---

*最后更新：2026-08-24 | M5.4 COMPLETE — 多会话并发与用户资源管理最终收口*
