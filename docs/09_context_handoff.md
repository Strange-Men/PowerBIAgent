# 09 — 跨对话上下文交接

> **当前状态交接入口；Claude / Codex / 其他代码 Agent 必须先从仓库根目录 `AGENTS.md` 进入。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-11 | M1.8 Codex 接管准备与仓库上下文固化**

---

## 当前项目目标

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言查询 Power BI 语义模型数据，以固定模板生成静态 HTML 报表。前端为 GPT 式极简对话网页（M5 React 开发）。

## 当前阶段

**M1.8 Codex 接管准备与仓库上下文固化** — ✅ 已完成候选。

> 本轮只建立 Codex 接管基础设施并固化仓库上下文，不新增功能、不修改生产业务逻辑、不进入 M2。

## 上一轮

**M1.7.2** — M0—M1 最终文档收口与封板（Commit `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`）。

## 固定封板 Tag

`m1.7.2-m0-m1正式封板` — 已真实存在，指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`。

## 下一动作

进入 M2.0 官方证据复核、真实 Power BI MCP 接入设计与开发路线固化。**M2 尚未开始业务实现。**

以后 Claude / Codex / 其他代码 Agent 均以根目录 `AGENTS.md` 为仓库级入口。

## 当前真实能力

- **LLM:** DeepSeek（真实 API）+ Mock（确定性测试）
- **Power BI:** Mock（M2 接入真实 Remote MCP）
- **管线:** 确定性 TurnPipeline（ADR-005），Mock/DeepSeek 共享执行骨架
- **能力:** 意图识别 → QueryPlan → DAX → Answer/ReportSpec，幂等重放，请求指纹冲突检测
- **API:** Health 200/503、Chat 可用/不可用，Mock/DeepSeek 模式切换
- **源模式:** source_mode=mock（Power BI 使用 Mock 适配器）

## 当前技术边界

- M1.8 不接入真实 Power BI、不进行 OAuth/Entra、不修改 Remote MCP；M2 仅在方案确认后实施
- Remote MCP 属 M2，会话持久化属 M4，报表资源属 M3
- PydanticAI 已从生产依赖移除（pyproject.toml 不再声明），ADR-001 已被 ADR-005 替代，M2 继续沿用确定性 TurnPipeline、ToolGateway 和 PowerBIAdapter 边界

## 运行命令

```
# 全量测试（Mock 模式，无网络）
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q

# Golden Cases
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# 人工验收 Smoke（需 .env 中 DEEPSEEK_API_KEY）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_chat_smoke.py

# 安全扫描
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py

# CI（本地模拟）
LLM_MODE=mock POWERBI_MODE=mock D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
```

## 未完成事项

- M2: 真实 Power BI MCP 连接、OAuth、DAX 真实验证
- M3: 报表正式渲染管线、报表资源 ID
- M4: 会话持久化、搜索、最近对话
- M5: React 前端
- 公司 Power BI 账号/Entra App/Tenant 设置（M2 前确认）

## 重要 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m1.7.2-m0-m1正式封板` | `23d8ddb` | M0—M1 正式封板基线 |
| `m1-deepseek-pipeline-release` | `a926b5e` | M1 DeepSeek 全链路封板 |
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## 近期变更摘要

- M1.8: Codex 接管准备与仓库上下文固化；M2 尚未开始
- M1.7.2: M0—M1 正式封板（`23d8ddb`，Tag `m1.7.2-m0-m1正式封板`）
- M1.7.1: 最终状态收口与封板候选修复（`1dd20de`，CI Run #30991136311 success）
- M1.7: MVP轻量化与通用CI固化（`e5d1740`）
- M1.6.6: CI建立、最终架构审计、文档收尾（`084aa76`）
- M1.6.5: 真实测试、机器错题本、架构防偏移治理（`e850f14`）
- M1.6.4: AI真实性门禁、异常处理与对抗测试加固（`4217b66`）
- M1.6.3: 统一TurnPipeline与旧Agent抽象清理（`d6665bd`→`d99d243`→`d57e38c`）
- M1.6.1-2: 架构定案、Harness与配置收口

---

*最后更新：2026-08-11 | M1.8 Codex 接管准备与仓库上下文固化*
