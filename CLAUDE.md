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
4. `docs/08_development_roadmap.md`
5. `docs/09_context_handoff.md`
6. 当前轮 Prompt 指定的设计文档和 ADR
7. `CHANGELOG.md` 最近一轮记录

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

### 5. 阻塞条件

只有检查全部通过才能开始修改。

如果上一轮未完成、Commit 不存在或交接文档冲突：
- 不得直接继续开发
- 先核查 Git 和文件
- 记录阻塞
- 不猜测上一轮已完成

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

1. 检查 `git diff`
2. 检查新增文件
3. 执行 Secret 检查
4. 检查 docs 文件名全部为英文
5. 检查没有提前实现后续轮次内容
6. 更新 `CHANGELOG.md`
7. 更新 `docs/09_context_handoff.md`
8. 检查 Commit 标题准确
9. 检查本轮没有新增 Tag

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

## 八、Conda 开发环境

- 本机 Conda 安装目录：`D:\Conda`
- 项目 Conda 环境名称：`PBIAgent`
- Python 版本：3.11
- Conda 可执行文件：`D:\Conda\Scripts\conda.exe`
- 环境路径：`D:\Conda\envs\PBIAgent`
- 不在 base 环境安装项目依赖
- 不在业务代码中硬编码 Conda 路径

## 九、项目目录结构

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

## 十、文档来源优先级

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

*最后更新：2026-07-31 | M0.4 项目骨架与阶段收尾*
