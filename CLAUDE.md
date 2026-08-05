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

只有检查全部通过才能开始修改。

如果上一轮未完成、Commit 不存在或交接文档冲突：
- 不得直接继续开发
- 先核查 Git 和文件
- 记录阻塞
- 不猜测上一轮已完成

无法读取 `docs/ai_development_error_ledger.yaml` 或错题本格式错误时，禁止开发。

**注意：不得将"没有上一轮 Tag"视为阻塞，因为普通轮次本来不创建 Tag。**

---

## 二、Commit 规则

### 格式

每一轮有效开发至少创建一个 Commit。

正常开发轮次：
```
M0.x_中文描述
```

经用户明确批准的专项修复：
```
M0.x.y_中文描述
```

规则：
- `M0.x` 为轮次编号
- `M0.x.y` 为专项修复编号（仅限用户明确批准的修复轮次）
- Claude 不得自行增加修复版本号
- 使用一个下划线连接版本号和中文描述
- 下划线后的描述必须全部为中文
- 不使用纯英文描述或中英文混合描述
- 当前轮 Commit 标题必须与当前轮固定名称一致
- 未达到验收标准不得提交完成性 Commit
- 禁止将多轮工作混入同一个 Commit

### M0 固定 Commit 名称

- M0.1_仓库初始化与文档基线
- M0.2_智能体架构与记忆设计
- M0.3_数据接入与验证闭环
- M0.3.1_验证闭环加固修复
- M0.3.2_工具网关与并发闭环修正
- M0.4_项目骨架与阶段收尾

### 提交前检查清单

1. 使用明确文件白名单暂存（禁止 `git add .` 和 `git add -A`）
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

### 允许创建 Tag 的场景

Tag 仅用于大版本封板：
- M0 开发准备封板（由 M0.4 Prompt 决定）
- MVP 完整闭环封板
- 正式可发布版本
- 其他经用户明确确认的大阶段版本

### 禁止

- 为 M0.1、M0.2、M0.3 自动创建 Tag
- 每个 Commit 都配一个 Tag
- 创建临时 Tag
- 创建测试 Tag
- 创建未经用户确认的封板 Tag
- 删除或重写历史 Tag

### Tag 命名

Tag 名称的描述部分必须全部使用中文，禁止使用英文描述。

---

## 四、九准备

每轮开发必须确认以下九项准备就绪：

1. **需求与 PRD** — 本轮需求明确，正式 PRD 已更新
2. **页面和交互骨架** — 前端交互边界清晰（后端跑通前仅确认骨架）
3. **产品范围与边界** — 本轮做/不做明确
4. **技术选型** — 技术决策已通过 ADR 或 Prompt 确认
5. **系统架构** — 模块划分清晰，接口边界明确
6. **项目上下文** — 已阅读交接文档和开发路线
7. **开发与编码规范** — 已明确编码标准、命名规范和文件组织
8. **Git、版本与回滚** — 已确认当前分支、Commit 历史和 Tag 状态
9. **测试、Harness与验收** — 已明确本轮测试策略和验收标准

## 五、五关键

每轮开发必须坚持五项关键原则：

1. **小步迭代** — 每轮只完成一个明确目标，不跨轮开发
2. **模块拆分** — 每个文件职责单一，模块间接口清晰
3. **状态摘要** — 每轮结束更新交接文档
4. **安全底线** — 不提交 Secret、不执行危险命令、不绕过 Harness
5. **检查报错** — 不压制错误、不跳过失败测试、不掩盖异常

## 六、开发铁律

- 每个新 Claude 开始前必须执行冷启动复习
- 必须阅读固定入口文件后才能修改代码
- 当前轮未验收不得进入下一轮
- 不得根据聊天记忆替代仓库文档
- 不得静默调整开发路线
- 重大变更必须新增 ADR（`docs/adr/`）
- 每轮结束必须更新 `docs/09_context_handoff.md`
- 每轮有效开发必须有 Commit
- Tag 只在大版本封板时创建
- 不为普通小轮开发创建 Tag

## 七、Git 安全规则

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

## 八、Secret 与 API Key 绝对规则

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

Claude **只能**：
- 检查 `.env` 是否存在
- 检查 `.env` 是否被 Git 忽略
- 检查 `.env` 是否被 Git 跟踪

Claude **不得**：
- 打开、读取、搜索或总结 `.env` 文件内容
- 输出任何环境变量真实值
- 要求用户把 Key 发进对话
- 将 Key 复制到 Prompt、代码、测试、文档、日志或截图
- 使用调试命令打印 Secret（如 `echo $VAR`、`printenv`、`set`）

### 3. API Key 只能后端运行时使用

DeepSeek API Key 只能：
- 由后端 `Settings` 以 `SecretStr` 或等价 Secret 类型读取
- 在后端运行时通过 HTTPS Authorization Header 发送给 DeepSeek 官方 API

除上述运行时鉴权用途外，Key 不得进入任何：
- GitHub 仓库、Git 历史、Issue、PR
- CI 日志、Artifact、云端文档
- Vercel/Netlify 等前端配置
- 浏览器、前端 Bundle、LocalStorage、SessionStorage、Cookie
- HTML、JavaScript、Source Map
- 日志、Trace、报表、截图、测试 Fixture、Golden Case

### 4. 前端禁止持有 Provider Secret

以下名称或同类形式禁止在前端源码、构建产物、环境变量中出现：

```
VITE_DEEPSEEK_API_KEY
REACT_APP_DEEPSEEK_API_KEY
NEXT_PUBLIC_DEEPSEEK_API_KEY
PUBLIC_DEEPSEEK_API_KEY
NUXT_PUBLIC_DEEPSEEK_API_KEY
```

前端只能调用 PowerBIAgent 后端接口。前端禁止：直接请求 DeepSeek API、构造 DeepSeek Authorization Header、接触任何模型 Provider API Key。

### 5. 日志与测试禁止泄漏

禁止将以下内容写入日志、Trace、测试 Fixture、Snapshot 或报告：
- API Key、Authorization Header、完整请求 Header
- `.env` 内容、真实 Prompt 全文、真实模型原始响应
- 真实业务数据、真实用户问题、HTTP 抓包和 HAR 文件

允许记录的只有脱敏元数据：
```
provider=deepseek
model=deepseek-chat
status_code=200
prompt_tokens=10
completion_tokens=5
error_type=authentication_error
```

### 6. 提交前安全检查

- 禁止默认使用 `git add .` 或 `git add -A`
- 每轮必须使用明确文件白名单暂存
- 暂存后必须检查 `git diff --cached`
- Commit 前必须执行 `scripts/check_repository_safety.py`
- Push 前必须确认 `.env` 未被跟踪和暂存
- Push 成功才算本轮远端交付完成

## 九、外部证据修复门禁

任何 Bug 修复，修改代码前必须：

1. **查官方最新文档、官方源码或维护者 Issue** — 第一优先级为官方 API 文档、官方错误码说明、官方 GitHub Issue/Discussion/Release；第二优先级为框架维护者确认的解决方案。只有前两级不足时才允许参考高质量工程文章。
2. **保存本地错误证据** — 包含错误现象、本地代码或测试证据
3. **建立最小复现** — 可独立运行的失败测试或脚本
4. **说明官方方案为何适用于当前项目** — 记录资料标题、更新时间或访问日期、与本项目的适用关系
5. **只做最小修改** — 不趁修复之机扩大重构范围
6. **用回归测试验证** — 修复后新增或强化测试，防止同根因复发

**没有找到可信权威依据时：**
- 不允许猜测修改
- 不允许凭经验大改
- 立即停止该问题
- 输出缺失证据和下一步需要人工确认的内容

## 十、两次修复上限

同一错误最多两次代码修改：

- 同一根因、同一堆栈或同一失败测试不得改名为新错误以重置次数
- 第一次修改后验证失败，计为第 1 次失败
- 第二次修改后仍失败，必须立即停止

**第一次失败后，第二次修复前必须：**
1. 重新检查根因判断
2. 查找额外官方资料或维护者 Issue
3. 说明第一次方案为什么无效
4. 提出与第一次不同且有证据支持的最小方案

**第二次仍失败后禁止：**
- 第三次修复
- 继续重构
- 扩大修改范围
- 创建新错误 ID 规避限制
- Commit 和 Push

连续失败两次说明判断可能存在幻觉或根因不明确，必须停下来。

## 十一、Conda 开发环境

- 本机 Conda 安装目录：`D:\Conda`
- 项目 Conda 环境名称：`PBIAgent`
- Python 版本：3.11
- Conda 可执行文件：`D:\Conda\Scripts\conda.exe`
- 环境路径：`D:\Conda\envs\PBIAgent`
- 不在 base 环境安装项目依赖
- 不在业务代码中硬编码 Conda 路径

## 十二、项目目录结构

```
PowerBIAgent/
├── PROJECT_CHARTER.md          # 项目北极星
├── README.md                   # 项目说明
├── CLAUDE.md                   # 本文件 - 开发协议
├── CHANGELOG.md                # 变更日志
├── .gitignore
├── .env.example
├── environment.yml             # Conda 环境配置
├── pyproject.toml              # Python 项目配置
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
│   └── adr/
│       └── README.md
├── frontend/
│   └── README.md
├── backend/                    # 后端源码
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
│       └── fixtures/
```

## 十三、文档来源优先级

当文档内容存在冲突时，按以下优先级处理：

1. 用户最新明确要求
2. `PROJECT_CHARTER.md`
3. `docs/00_product_requirements_document.md`（正式 PRD）
4. 已确认 ADR
5. 正式设计文档
6. `docs/09_context_handoff.md` 中的当前状态
7. 原始 `PRD.md`（仅作历史参考，不直接指导开发）
8. Claude 的可逆默认假设

不得自行选择方便开发的版本；无法判断时记录到待确认事项；不得静默改变产品方向。

**重要：** 原始 PRD 与正式 PRD 冲突时，以正式 PRD 为准。不修改原始 PRD。

---

*最后更新：2026-08-05 | M1.6.3.2 事务边界、单写入者与证据驱动修复门禁固化*
