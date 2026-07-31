# 06 — 安全、Git 与开发规范

> **状态：** M1.0.2 已完成 Secret 安全规则固化
> **后续轮次细化：** 代码风格指南（M0.4）、Harness 安全规则（M0.3）、Secret 扫描（M0.4 → M1.0.2 落地）

---

## 一、Secret 与 API Key 安全规则

### 1.1 Secret 文件规则

| 文件 | 是否可提交 | 说明 |
|------|-----------|------|
| `.env.example` | ✅ 可提交 | 环境配置模板，只能包含空值或公开默认值 |
| `.env` | ❌ 禁止提交 | 用户本地 Secret 文件，已被 `.gitignore` 排除 |
| `.env.local`、`.env.development`、`.env.production` | ❌ 禁止提交 | 任何真实环境文件 |
| `*.key`、`*.pem`、`*.p12`、`*.pfx` | ❌ 禁止提交 | 证书和私钥 |
| `credentials.json`、`token.json`、`secrets.yaml` | ❌ 禁止提交 | 凭据文件 |
| `*.har` | ❌ 禁止提交 | 网络抓包文件 |

### 1.2 Claude 禁止读取 .env

Claude 只能：
- 检查 `.env` 是否存在
- 检查 `.env` 是否被 Git 忽略
- 检查 `.env` 是否被 Git 跟踪

Claude 不得：
- 打开、读取、搜索或总结 `.env` 文件内容
- 输出任何环境变量真实值
- 要求用户把 Key 发进对话
- 将 Key 复制到 Prompt、代码、测试、文档、日志或截图

### 1.3 后端专用 Key 规则

DeepSeek API Key 只能：
- 由后端 `Settings` 以 `SecretStr` 类型读取
- 在后端运行时通过 HTTPS Authorization Header 发送给 DeepSeek 官方 API

除运行时鉴权外，Key 不得进入：GitHub 仓库、Git 历史、CI 日志、前端配置、浏览器、日志、Trace、测试 Fixture。

### 1.4 前端禁止 Secret

前端禁止持有模型 Provider API Key。以下命名或同类形式禁止在前端出现：

```
VITE_DEEPSEEK_API_KEY
REACT_APP_DEEPSEEK_API_KEY
NEXT_PUBLIC_DEEPSEEK_API_KEY
PUBLIC_DEEPSEEK_API_KEY
NUXT_PUBLIC_DEEPSEEK_API_KEY
```

前端只能调用 PowerBIAgent 后端接口，禁止直接请求 DeepSeek API。

### 1.5 日志、Trace、Smoke 与 Fixture 安全

禁止写入日志/Trace/测试 Fixture/Report 的内容：
- API Key、Authorization Header、完整请求 Header
- `.env` 内容、真实 Prompt 全文、真实模型原始响应
- 真实业务数据、真实用户问题、HTTP 抓包和 HAR 文件

允许记录的脱敏元数据：
```
provider=deepseek, model=deepseek-chat, status_code=200
prompt_tokens=10, completion_tokens=5, error_type=authentication_error
```

### 1.6 API Key 填写规则

- 用户本人手动在本地 `.env` 中填写真实 Key
- Claude 不得代填真实 Key
- Claude 不得询问或回显 Key
- 真实 Smoke 最终报告只记录成功/失败和脱敏错误类型

## 二、九准备

每轮开发必须确认以下九项准备就绪：

| # | 准备项 | 检查要点 |
|---|--------|---------|
| 1 | 需求与 PRD | 本轮需求明确，正式 PRD 已更新 |
| 2 | 页面和交互骨架 | 前端交互边界清晰 |
| 3 | 产品范围与边界 | 本轮做/不做明确 |
| 4 | 技术选型 | 技术决策已通过 ADR 或 Prompt 确认 |
| 5 | 系统架构 | 模块划分清晰，接口边界明确 |
| 6 | 项目上下文 | 已阅读交接文档和开发路线 |
| 7 | 开发与编码规范 | 已明确编码标准、命名规范和文件组织 |
| 8 | Git、版本与回滚 | 已确认当前分支、Commit 历史和 Tag 状态 |
| 9 | 测试、Harness与验收 | 已明确本轮测试策略和验收标准 |

## 三、五关键

每轮开发必须坚持五项关键原则：

1. **小步迭代** — 每轮只完成一个明确目标，不跨轮开发
2. **模块拆分** — 每个文件职责单一，模块间接口清晰
3. **状态摘要** — 每轮结束更新交接文档
4. **安全底线** — 不提交 Secret、不执行危险命令、不绕过 Harness
5. **检查报错** — 不压制错误、不跳过失败测试、不掩盖异常

## 四、开发铁律

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

## 五、Git 安全规则

### 禁止执行的命令

- `git push --force` / `git push -f`
- `git reset --hard`
- `git clean -fd`
- 删除或重写历史 Tag
- 未经说明的大规模重构

### 禁止提交的内容

- 真实 Secret、API Key、Token
- 真实业务数据
- `.env` 文件
- Conda 环境目录
- `node_modules`
- 生成报表
- 原始 Power BI 导出数据
- 敏感 Trace 和日志

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

## 六、Commit 规则

### 格式

```
M0.x_中文描述
```

- `M0.x` 为轮次编号
- 使用一个下划线连接版本号和中文描述
- 下划线后的描述必须全部为中文
- 不使用纯英文描述或中英文混合描述
- 当前轮 Commit 标题必须与当前轮固定名称一致

### M0 固定 Commit 名称

| 轮次 | Commit 标题 |
|------|------------|
| M0.1 | M0.1_仓库初始化与文档基线 |
| M0.2 | M0.2_智能体架构与记忆设计 |
| M0.3 | M0.3_数据接入与验证闭环 |
| M0.4 | M0.4_项目骨架与阶段收尾 |

## 七、Tag 规则

### 允许创建 Tag 的场景

- M0 开发准备封板（由 M0.4 Prompt 决定）
- MVP 完整闭环封板
- 正式可发布版本
- 其他经用户明确确认的大阶段版本

### 禁止

- 为 M0.1、M0.2、M0.3 创建 Tag
- 每个 Commit 都配一个 Tag
- 创建临时 Tag、测试 Tag
- 创建未经用户确认的封板 Tag
- 删除或重写历史 Tag

### Tag 命名要求

Tag 名称的描述部分必须全部使用中文，禁止使用英文描述。

## 八、代码安全原则

1. **最小权限** — Agent 只能使用白名单中的工具
2. **输入校验** — 所有外部输入必须经过 Pydantic 校验
3. **输出约束** — LLM 输出必须符合固定 Schema
4. **无代码执行** — 禁止 LLM 生成和执行任意代码
5. **Secret 分离** — 所有密钥通过环境变量注入

## 九、文档来源优先级

当文档内容存在冲突时，按以下优先级处理：

1. 用户最新明确要求
2. PROJECT_CHARTER.md
3. docs/00_product_requirements_document.md（正式 PRD）
4. 已确认 ADR
5. 正式设计文档
6. docs/09_context_handoff.md 中的当前状态
7. 原始 PRD.md（仅作历史参考，不直接指导开发）
8. Claude 的可逆默认假设

**重要：** 原始 PRD 与正式 PRD 冲突时，以正式 PRD 为准。不修改原始 PRD。

## 十、文档命名规范

| 位置 | 规范 |
|------|------|
| `docs/` 文件名 | 英文，小写，下划线分隔 |
| `docs/adr/` 文件名 | `NNNN-slug.md`，英文 |
| 文档正文 | 中文 |
| 代码注释 | 中文或英文，项目内统一 |

---

*创建日期：2026-07-31 | M1.0.2 密钥与仓库安全规则固化*
