# 任务文档目录索引

> 本项目任务拆解的总入口。一个任务 = 一次独立的 AI 对话，通用约定见 [tasks.md](./tasks.md) §0。

## 1. 文档清单

| 文件 | 任务范围 | 内容 | 何时读 |
|------|----------|------|--------|
| [tasks.md](./tasks.md) | P0、T0–T14（并含全项目总览） | 通用约定（核心原则 / Prompt 模板 / 四条纪律 / 验收形式）、前置条件、依赖关系图、MVP 任务卡片、进度追踪、任务与 spec 映射速查 | 开工前通读；实现 MVP 任务时逐卡使用 |
| [tasks-agent.md](./tasks-agent.md) | T15–T29 | Agent 化任务卡片（批次 A–D + 双引擎对照）、M8–M13 里程碑 | MVP 完成后使用 |

> 拆分原则：`tasks.md` 只放 MVP 任务卡片；Agent 化任务卡片独立成 `tasks-agent.md`。两者共用 `tasks.md` §0 的通用约定与 §4 的进度总览。

## 2. tasks.md 目录

| 章节 | 主题 |
|------|------|
| §0 | 如何使用本文档（核心原则 / 标准 Prompt 模板 / 四条纪律 / 验收形式约定） |
| §1 | 前置条件（P0） |
| §2 | 依赖关系图（MVP 与 Agent 化批次） |
| §3 | 任务清单（T0–T14） |
| §4 | 进度追踪（项目整体总览，含 T15–T29） |
| §5 | 任务与 spec 的映射速查 |
| §6 | Agent 化任务清单（已拆分至 [tasks-agent.md](./tasks-agent.md)） |

## 3. tasks-agent.md 目录

| 章节 | 主题 |
|------|------|
| §1 | 任务清单（T15–T29，批次 A–D + 双引擎对照） |
| §2 | Agent 化里程碑（M8–M13） |

## 4. 任务顺序速览

| 批次 | 任务 | 说明 |
|------|------|------|
| MVP | T0–T14 | 参见 [tasks.md](./tasks.md) §3 |
| 批次 A（本地，无 key、无外网） | T15–T21、T26、T27 | 工具层 → agent loop → API → 前端 → 对照实验 / Skill / 流式 |
| 批次 B（外网，需 key） | T22–T23 | 百度搜索、天气 |
| 批次 C（MCP，stdio） | T24–T25 | MCP server → client |
| 批次 D（引擎对照，本地） | T28–T29 | 手写 loop vs LangGraph，产出对照报告 |

> Agent 化关键路径：T15 → T17 → T18 → T19 → T20。

## 5. 相关文档

- Spec 文档索引：[spec-index.md](./spec-index.md)
- MVP 设计契约：[spec.md](./spec.md)
- Agent 化设计契约：[spec-agent.md](./spec-agent.md)
