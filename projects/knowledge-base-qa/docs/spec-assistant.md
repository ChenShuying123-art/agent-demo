# 私人助手 Spec（动态工具 / 记忆 / 沙箱 / 中断恢复 / ReAct）

| 项目     | 内容                                                |
| -------- | --------------------------------------------------- |
| 文档版本 | v0.1                                                |
| 所属项目 | [知识库问答 Agent（RAG MVP）](./spec.md)             |
| 章节编号 | §20.x                                               |
| 前置文档 | [spec-agent.md](./spec-agent.md)（§19 Agent 化）     |
| 状态     | 待评审，尚未开始实现                                |

> 本文档描述在现有 Agent 能力之上的增量改造，不改变 MVP 固定链路
> （`/api/qa`、三风格提示词）和既有 `/api/agent/*` 的行为。
>
> 任务拆解见本文 §20.12；文档目录见 [spec-index.md](./spec-index.md)。

---

## 20. 私人助手改造

### 20.1 目标与非目标

**目标**

1. 工具不再只在启动时静态注册，支持运行时新增、停用、删除。
2. 会话持久化，并引入短期记忆与长期记忆；长期记忆具备巩固和冲突消除。
3. 引入隔离执行环境，工具代码不在主进程里直接运行。
4. 任务支持主动取消、网络中断和进程重启后的恢复。
5. 对话升级为 ReAct 范式，用户可以设置最大迭代轮数（1~3，默认 2）。

**非目标（第一版明确不做）**

- 上传任意 Python 文件并直接注册为工具。
- 多用户登录、权限体系与租户隔离。
- 向量化长期记忆与复杂检索排序。
- 分布式任务队列与跨机器调度。
- gVisor / Firecracker 级别的强隔离。

### 20.2 已确认决策

| 决策点     | 选择                                                       |
| ---------- | ---------------------------------------------------------- |
| 改造范围   | 后端 API + `web/` 前端一起改                               |
| 执行引擎   | LangGraph 作为新 ReAct 引擎的主实现                        |
| 动态工具   | 第一版支持动态 MCP Server + HTTP API 工具                  |
| 沙箱       | Docker 容器隔离；不可用时明确降级，不回退到宿主机执行      |
| 用户模型   | 第一版单用户，但数据模型保留 `user_id`，便于后续扩展       |
| 迭代轮数   | 请求级参数 `max_iterations`，允许 1~3，默认 2              |
| 兼容策略   | 保留 `/api/qa` 与 `/api/agent/*`，新能力走 `/api/assistant/*` |

**环境事实（2026-10-26）**

- `langgraph` 已安装到 `projects/knowledge-base-qa/.venv`。
- 当前机器 PATH 中没有 Docker；沙箱代码可以先完成，但真实隔离测试需要
  安装并启动 Docker Desktop。

### 20.3 总体架构

```text
Vue 前端
  └─ /api/assistant/*
       ├─ SessionService       会话、消息、run 状态与事件
       ├─ MemoryService        短期上下文、长期记忆、巩固与冲突消除
       ├─ AssistantRunner      基于 LangGraph 的 ReAct 执行
       ├─ RuntimeToolRegistry  动态工具注册与 run 级快照
       ├─ SandboxRunner        Docker 隔离执行
       └─ SQLite               会话、run、事件、记忆、工具配置
```

**分层边界**

- API 层只做 HTTP 语义、参数校验和 DTO 映射。
- 编排层负责 run 生命周期、checkpoint、取消和恢复。
- 执行层只负责一次模型决策或一次工具调用。
- 存储层不包含业务判断，只提供事务化的读写。

### 20.4 动态工具

工具分三类：

| 类型       | 来源                              | 是否持久化 |
| ---------- | --------------------------------- | ---------- |
| 内置工具   | 知识库检索、日期、天气、网页搜索  | 否         |
| HTTP 工具  | 用户配置 URL / method / Schema    | 是         |
| MCP 工具   | 运行时添加的 MCP Server           | 是         |

**工具元数据**

```text
name
description
parameters            JSON Schema
enabled
version
timeout_seconds
side_effect           none / read / write
idempotent            bool
sandbox_required      bool
source                builtin / http / mcp:<server>
```

**运行规则**

- 每次 run 启动时对工具表拍快照；运行过程中的增删不影响当前 run。
- 工具名全局唯一；重复注册直接失败，不静默覆盖。
- HTTP 工具默认禁止访问 localhost 与内网地址；确需访问时显式配置放行。
- 第一版不允许把任意 Python 源码直接注册成主进程工具。

### 20.5 会话与记忆

#### 短期记忆

- 当前会话最近 N 条消息，默认 8 条。
- 当前 run 的 ReAct 轨迹。
- 超出窗口的早期消息生成会话摘要。

#### 长期记忆

结构化存储，不直接存自由文本：

```text
user_id
subject
key
value
confidence
source_session_id
source_run_id
status              active / superseded / uncertain
created_at
updated_at
superseded_by
```

**记忆巩固**

- run 完成后，由 LLM 抽取稳定信息，例如偏好、长期目标、身份背景、
  项目约束和明确的纠正。
- 一次性寒暄、临时任务和工具原始输出不进入长期记忆。

**冲突消除**

- 同一 `subject + key` 出现新值时，不直接覆盖旧记录。
- 旧记录标记为 `superseded`，并记录 `superseded_by`，保留审计轨迹。
- 用户明确纠正时，新值优先。
- 低置信度的推断冲突存为 `uncertain`，不覆盖当前有效值。

**检索**

- 第一版使用 key / 关键词匹配加简单相关性排序，取 top-k 注入上下文。
- 只注入 `status=active` 且置信度达到阈值的记忆。

### 20.6 沙箱

新增沙箱工具（例如 `run_python`），每次执行启动一个临时 Docker 容器。

**默认限制**

- 禁网：`--network none`
- 根文件系统只读
- 独立临时工作目录
- 非 root 用户
- CPU、内存、进程数上限
- 执行超时
- 输出长度上限
- 容器退出后自动删除

**降级策略**

- Docker 不可用时，服务正常启动。
- 沙箱工具返回明确的“沙箱不可用”提示。
- 不允许自动回退到宿主机执行。
- 本地子进程后端只作为显式开启的开发选项，并标注“不是安全边界”。

### 20.7 中断与恢复

**run 状态**

```text
queued → running → completed
                 → cancelled
                 → interrupted
                 → failed
                 → needs_confirmation
```

**checkpoint 时机**

- 初始状态建立后
- 每次模型决策后
- 每次工具调用前、后
- 生成最终答案前

**用户主动打断**

- 设置 run 的取消标记。
- 当前工具如果可中断就停止；不可中断则等它返回。
- 已保存的 checkpoint 保留，允许之后恢复。

**网络中断**

- 前端 SSE 断开：后台 run 继续执行，前端按事件序号重连回放。
- LLM 调用失败：run 标记为 `interrupted`，从最后一个安全 checkpoint 恢复。
- 工具网络失败：工具步骤记为 `ok=false`，模型可以根据错误换策略。

**恢复规则**

- 已成功的工具调用复用结果，不重复执行。
- 幂等工具允许自动重试。
- 非幂等工具在中断时状态不确定，run 进入 `needs_confirmation`，
  用户确认后才重新执行。

### 20.8 ReAct 与迭代轮数

请求级参数：

```json
{
  "message": "帮我整理今天的待办",
  "max_iterations": 2
}
```

一次迭代：

```text
模型决定 Action → 执行工具 → 得到 Observation
```

**终止条件**

- 模型不再请求工具：`stop_reason=final_answer`
- 达到最大迭代轮数：停止工具调用，强制模型基于已有 Observation 给出答案
- 用户取消：`stop_reason=cancelled`
- 不可恢复错误：`stop_reason=error`

**轨迹展示**

每一步展示：

- `thought_summary`：简短思路摘要
- `action`：工具名与参数
- `observation`：工具结果摘要
- `final_answer`：最终答案

完整思维链不展示，避免泄露内部推理和不稳定输出。

### 20.9 API 草案

```text
POST   /api/assistant/sessions
GET    /api/assistant/sessions
GET    /api/assistant/sessions/{session_id}
DELETE /api/assistant/sessions/{session_id}

POST   /api/assistant/sessions/{session_id}/runs
GET    /api/assistant/runs/{run_id}
GET    /api/assistant/runs/{run_id}/events?after=
POST   /api/assistant/runs/{run_id}/cancel
POST   /api/assistant/runs/{run_id}/resume

GET    /api/assistant/tools
POST   /api/assistant/tools/http
POST   /api/assistant/tools/mcp
PATCH  /api/assistant/tools/{tool_id}
DELETE /api/assistant/tools/{tool_id}

GET    /api/assistant/memories
PATCH  /api/assistant/memories/{memory_id}
DELETE /api/assistant/memories/{memory_id}
```

**错误约定**：沿用现有 `{ "error": { "code", "message" } }` 信封。

### 20.10 数据模型

**新增表**

| 表名            | 用途                                   |
| --------------- | -------------------------------------- |
| `sessions`      | 会话元数据、摘要、更新时间             |
| `messages`      | 用户消息与最终答案                     |
| `runs`          | 一次任务的状态、轮数、停止原因         |
| `run_checkpoints` | run 的可恢复状态（JSON）             |
| `run_events`    | 可回放的执行事件                       |
| `memories`      | 长期记忆与冲突关系                     |
| `tool_configs`  | 动态 HTTP / MCP 工具配置               |

**兼容性**

- 现有向量索引与文档数据不迁移。
- 现有 `/api/agent/chat` 继续使用内存中的 `ToolRegistry`。
- 新 assistant 服务使用独立 SQLite 文件，默认 `data/assistant.db`。

### 20.11 前端

新增私人助手工作区：

- 会话列表与新建会话
- 最大迭代轮数选择（1 / 2 / 3，默认 2）
- 发送、停止、恢复
- ReAct 轨迹时间线
- 工具管理面板（新增 HTTP / MCP、启停、删除）
- 记忆管理面板（查看、修改、删除）
- 沙箱状态提示（可用 / 不可用及原因）

保留现有文档上传、索引、固定链路问答和旧 Agent 面板。

### 20.12 任务拆分

#### 阶段 1：持久化基础

- 新增 SQLite 存储层与建表语句
- 实现会话、消息、run、事件、checkpoint 的读写
- 实现进程重启后的 run 恢复标记
- 验收：重启后会话和消息仍然存在

#### 阶段 2：ReAct Runner

- 基于 LangGraph 新建 `AssistantRunner`
- 支持 `max_iterations=1~3`
- 输出结构化 ReAct 轨迹
- 验收：用 mock LLM 验证 1、2、3 轮上限与最终答案兜底

#### 阶段 3：中断恢复

- run 改为后台执行
- 实现 checkpoint、cancel、resume
- 实现事件回放
- 验收：模拟用户取消、LLM 网络失败、服务重启后的恢复

#### 阶段 4：动态工具

- 实现 `RuntimeToolRegistry`
- 支持 HTTP 工具注册
- 支持动态 MCP Server 注册与刷新
- run 级工具快照
- 验收：不重启服务即可新增工具，并被下一次 run 使用

#### 阶段 5：沙箱

- 实现 `DockerSandboxRunner`
- 新增 `run_python` 工具
- Docker 不可用时明确降级
- 验收：超时、禁网、输出截断、容器清理
- 注意：需要本机 Docker 才能完成真实测试

#### 阶段 6：记忆系统

- 实现短期上下文拼装与摘要
- 实现长期记忆抽取
- 实现冲突消除与记忆检索
- 验收：用户偏好变化后，旧记忆标记为 `superseded`，新记忆生效

#### 阶段 7：前端

- 会话列表与切换
- 迭代轮数选择
- ReAct 轨迹展示
- 停止 / 恢复
- 工具与记忆管理
- 验收：TypeScript 类型检查与构建通过；有条件时做浏览器验证

#### 阶段 8：测试与文档

- 补单元测试与 API 测试
- 更新 `.env.example`
- 更新使用说明
- 明确记录已验证范围与未验证项

### 20.13 验收标准

- 新增工具后无需重启服务，下一次 run 即可调用。
- 同一会话多轮对话能引用之前的上下文。
- 用户偏好变化后，旧记忆被标记为 `superseded`，新记忆生效。
- 沙箱执行具备禁网、超时和资源限制；Docker 缺失时给出明确提示。
- 用户能取消运行中的 run，并从 checkpoint 恢复。
- 服务重启后，运行中的 run 标记为 `interrupted`，可手动恢复。
- `max_iterations=1/2/3` 行为符合定义，达到上限后仍给出最终答案。
- 原有 `/api/qa`、`/api/agent/chat` 行为不回归。

### 20.14 风险与待确认项

| 风险                         | 应对                                             |
| ---------------------------- | ------------------------------------------------ |
| Docker 在当前机器不可用      | 先完成代码与单元测试，真实隔离测试待 Docker 就绪 |
| LLM 记忆抽取不稳定           | 严格 JSON 输出 + 解析失败跳过 + 置信度门槛       |
| 动态 HTTP 工具 SSRF          | 默认禁止内网地址，需显式放行                     |
| 非幂等工具重复执行           | 中断时进入 `needs_confirmation`，用户确认后重试  |
| SQLite 并发写压力            | 单机单用户场景可接受；后续可替换为 PostgreSQL    |

### 20.15 第一版不做的事

- 上传任意 Python 插件代码
- 多用户登录和权限系统
- 向量化长期记忆
- 分布式任务队列
- gVisor / Firecracker 级别的强隔离
