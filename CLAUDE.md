# CLAUDE.md — PowerBIAgent 项目开发协议

> **每个新的 Claude 对话开始后，修改任何文件前，必须执行冷启动协议。**

---

## 一、冷启动协议

每个新的 Claude 对话开始后，修改任何文件前必须：

### 1. 环境检查

```bash
git status
git branch
git log --oneline -5
git tag -l
```

### 2. 必须阅读的文件（按顺序）

1. `PROJECT_CHARTER.md`
2. `CLAUDE.md`（本文件）
3. `docs/00_product_requirements_document.md`
4. `docs/adr/README.md` 及当前有效 ADR
5. `docs/ai_development_error_ledger.yaml`
6. `docs/08_development_roadmap.md`
7. `docs/09_context_handoff.md`
8. 当前轮 Prompt 指定的设计文档
9. `CHANGELOG.md` 最近一轮记录

### 3. 状态核实

- 检查上一轮固定 Commit 是否存在
- 检查 `docs/09_context_handoff.md` 是否标记上一轮完成
- 检查 Git 工作区是否干净
- 检查 `D:\Conda` 和 `PBIAgent` 环境状态

### 4. 复述（不超过200字）

- 项目目标
- 当前进度
- 本轮允许范围
- 本轮禁止范围
- 当前本地开发环境

### 5. 防偏移检查（不超过200字）

开始开发前必须输出：

- 本轮命中了哪些历史错误 ID
- 哪些 ADR 限制本轮修改
- 本轮可能产生的架构偏移
- 本轮禁止触碰的边界

### 6. 阻塞条件

- 上一轮未完成、Commit 不存在或交接文档冲突 → 停止
- 无法读取错题本或格式错误 → 停止
- **注意：不得将"没有上一轮 Tag"视为阻塞，因为普通轮次本来不创建 Tag。**

---

## 二、Commit 规则

### 格式

- 正常轮次：`M0.x_中文描述`
- 专项修复（仅限用户明确批准）：`M0.x.y_中文描述`
- Claude 不得自行增加修复版本号
- 使用一个下划线连接版本号和中文描述
- 当前轮 Commit 标题必须与当前轮固定名称一致

### 提交前检查清单

1. 明确文件白名单暂存（禁止 `git add .` 和 `git add -A`）
2. 检查 `git diff --cached`，确认无 `.env` 等 Secret 文件
3. 检查 `git diff` 和新增文件
4. 执行 `python scripts/check_repository_safety.py`
5. 检查 docs 文件名全部为英文
6. 检查没有提前实现后续轮次内容
7. 更新 `CHANGELOG.md`
8. 更新 `docs/09_context_handoff.md`
9. 检查 Commit 标题准确
10. 检查本轮没有新增 Tag

---

## 三、Tag 规则

- Tag 仅用于大版本封板（M0 封板、MVP 封板、正式可发布版本等）
- Tag 名称描述部分全部使用中文
- 禁止：为小轮自动创建 Tag、创建临时/测试 Tag、删除或重写历史 Tag

---

## 四、Git 安全规则

禁止执行：
- `git push --force` / `git push -f`
- `git reset --hard`
- `git clean -fd`
- 删除或重写历史 Tag
- 未经说明的大规模重构

禁止提交：
- 真实 Secret、API Key、Token
- 真实业务数据
- `.env` 文件

---

## 五、Secret 与 API Key 绝对规则

### 1. Secret 永不进入仓库

永远禁止提交或上传：

- `.env`、`.env.local`、`.env.development`、`.env.production` 等真实环境文件
- API Key、Token、密码、Client Secret
- OAuth Refresh Token、Authorization Header、Bearer Token
- Cookie 和 Session、证书私钥、云服务凭据
- `.har` 文件、网络抓包、HTTP Dump、Debug 响应转储
- Smok 输出、Trace 日志、真实 Prompt 全文、真实模型原始响应
- 真实业务数据、Power BI 导出文件（.pbix）、数据库文件、生成报表
- 用户私人工作资料、截图包含的 Secret

`.env.example` 是唯一允许提交的环境模板，只能包含空值、公开默认值或明显占位符。

### 2. Claude 不得读取 Secret

Claude **只能**检查 `.env` 是否存在/被忽略/被跟踪；**不得**打开、读取、搜索 `.env` 文件内容或输出任何环境变量真实值。

### 3. API Key 只能后端运行时使用

DeepSeek API Key 只能由后端 `Settings` 以 `SecretStr` 类型读取，通过 HTTPS Authorization Header 发送给 DeepSeek 官方 API。不得进入 GitHub、CI 日志、前端、日志、Trace、测试 Fixture。

### 4. 前端禁止持有 Provider Secret

以下名称或同类形式禁止在前端出现：
```
VITE_DEEPSEEK_API_KEY / REACT_APP_DEEPSEEK_API_KEY / NEXT_PUBLIC_DEEPSEEK_API_KEY
PUBLIC_DEEPSEEK_API_KEY / NUXT_PUBLIC_DEEPSEEK_API_KEY
```

### 5. 日志与测试禁止泄漏

禁止将 API Key、Authorization Header、完整 Prompt、真实模型原始响应写入日志/Trace/测试。只允许脱敏元数据（provider、model、status_code、token 计数、error_type）。

### 6. 提交前安全检查

- 禁止 `git add .` 或 `git add -A`
- 必须使用明确文件白名单暂存
- Commit 前必须执行 `scripts/check_repository_safety.py`

---

## 六、外部证据修复门禁

任何 Bug 修复，修改代码前必须：

1. **查官方最新文档、官方源码或维护者 Issue** — 第一优先级为官方 API 文档/错误码说明/GitHub Issue；第二优先级为框架维护者确认的解决方案
2. **保存本地错误证据**
3. **建立最小复现**
4. **说明官方方案为何适用于当前项目**
5. **只做最小修改** — 不趁修复之机扩大重构范围
6. **用回归测试验证**

**没有找到可信权威依据时：** 立即停止，不猜测修改。

---

## 七、两次修复上限

同一错误最多两次代码修改：

- 同一根因/堆栈/失败测试不得改名为新错误以重置次数
- 第一次修改后验证失败，计为第 1 次失败
- 第二次修改后仍失败，必须立即停止
- **第一次失败后，第二次修复前必须：** 重新检查根因、查找额外官方资料、说明第一次方案为何无效、提出有证据支持的不同方案
- **第二次仍失败后禁止：** 第三次修复、继续重构、扩大修改范围、创建新错误 ID 规避限制、Commit 和 Push

---

## 八、开发核心原则

- 每个新 Claude 开始前必须执行冷启动复习
- 必须阅读固定入口文件后才能修改代码
- 当前轮未验收不得进入下一轮
- **小步迭代** — 每轮只完成一个明确目标
- **模块拆分** — 每个文件职责单一
- **状态摘要** — 每轮结束更新交接文档
- **安全底线** — 不提交 Secret、不执行危险命令、不绕过 Harness
- **检查报错** — 不压制错误、不跳过失败测试、不掩盖异常
- 不得根据聊天记忆替代仓库文档
- 重大变更必须新增 ADR（`docs/adr/`）
- 每轮结束必须更新 `docs/09_context_handoff.md`
- 每轮有效开发必须有 Commit
- Tag 只在大版本封板时创建

---

## 九、文档来源优先级

当文档内容存在冲突时：

1. 用户最新明确要求
2. `PROJECT_CHARTER.md`
3. `docs/00_product_requirements_document.md`（正式 PRD）
4. 已确认 ADR
5. 正式设计文档
6. `docs/09_context_handoff.md` 中的当前状态
7. 原始 `PRD.md`（仅作历史参考）
8. Claude 的可逆默认假设

不得自行选择方便开发的版本；无法判断时记录到待确认事项；不得静默改变产品方向。原始 PRD 与正式 PRD 冲突时以正式 PRD 为准。

---

## 十、Conda 开发环境

- Conda 安装目录：`D:\Conda`
- 项目环境名称：`PBIAgent`（Python 3.11）
- 不在 base 环境安装项目依赖
- 不在业务代码中硬编码 Conda 路径

---

## 十一、项目目录结构

```
PowerBIAgent/
├── PROJECT_CHARTER.md
├── README.md
├── CLAUDE.md
├── CHANGELOG.md
├── .gitignore
├── .env.example
├── environment.yml
├── pyproject.toml
├── docs/                       # 英文文件名，中文正文
│   ├── 00_product_requirements_document.md
│   ├── 01_product_scope_and_frontend_skeleton.md
│   ├── 02_technology_selection_and_system_architecture.md
│   ├── 03_intent_recognition_and_memory_system.md
│   ├── 04_powerbi_mcp_and_api_contracts.md
│   ├── 05_harness_test_and_acceptance.md
│   ├── 06_security_git_and_development_standards.md
│   ├── 07_milestones_status_and_open_questions.md
│   ├── 08_development_roadmap.md
│   ├── 09_context_handoff.md
│   ├── adr/
│   └── archive/
├── frontend/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   ├── intent/
│   │   ├── llm/
│   │   ├── memory/
│   │   ├── powerbi/
│   │   ├── report/
│   │   ├── harness/
│   │   ├── schemas/
│   │   ├── core/
│   │   └── application/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── api/
│       └── fixtures/
└── scripts/
    └── manual_smoke/
```

---

## 十二、M2前禁止事项

- 新增业务功能
- 修改 Intent、QueryPlan、DAX、Answer、ReportSpec 行为
- 接入真实 Power BI
- 开发 OAuth 或 Entra
- 开发 React 前端
- 修改 API 公开契约
- 修改 Memory/Snapshot 数据模型
- 重构 TurnPipeline
- 拆分大型生产模块
- 新增生产依赖
- 创建 Tag 或 Release
- force push

---

*最后更新：2026-08-05 | M1.7 轻量化候选*
