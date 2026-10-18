# Agent 化 Spec（工具 / MCP / Skill）

| 项目     | 内容                                    |
| -------- | --------------------------------------- |
| 文档版本 | v0.3（对应 spec.md v0.3）               |
| 所属项目 | [知识库问答 Agent（RAG MVP）](./spec.md) |
| 章节编号 | 保持 §19.x，全文交叉引用编号不变       |
| 状态     | 待评审                                  |

> 本文档由 [spec.md](./spec.md) 第 19 章拆分而来，便于按需阅读；spec.md 只保留 MVP 部分。
> 本文中的 `§19.x` 均指本文档对应小节；其余章节（如 §7.8、§8、§18）见 [spec.md](./spec.md)。
> 任务拆解见 [tasks-agent.md](./tasks-agent.md)；文档目录见 [spec-index.md](./spec-index.md)。

---

## 19. Agent 化：工具 / MCP / Skill（第二批）

> 本节是 §16 第 5 步「Agent 化」的**可执行契约**：§16 只是路线图，验收以本节为准。
> 前提是 MVP（T0–T14）已完成。**`/api/qa` 固定链路与三风格提示词原样保留**——它是 agent 的对照基线（§19.14）。

### 19.1 目标与非目标

**目标**

1. 让模型自己决定「要不要调工具、调哪个、调几次」——即 §16 第 5 步说的"把检索变成 LLM 可调用的工具"。
2. 落地四类工具：知识库检索、日期时间、百度搜索、天气/生活服务。
3. 「生成 markdown 文件」用 **MCP** 承载：自写一个 MCP server，agent 作为 **MCP client** 消费它。
4. 一套 **skill 机制**：提示词 + 工具子集，按需加载；支持模型自动选择与用户显式指定。
5. **同一 agent loop 两版实现**：手写版（默认，理解循环本身）+ LangGraph 版（对照学习框架替你做了什么），两版共用同一契约与同一套工具（§19.17）。

**非目标（本批明确不做）**

- 不做多 agent（Router / 专家 / Handoff），留到下一批。
- **主链路不引入框架**：默认执行路径仍是手写 loop；LangGraph 只作为**可切换的对照实现**（§19.17），不得成为 `/api/agent/chat` 的默认依赖。
- 不改 `/api/qa` 的返回结构、不改 `PROMPT_STYLES` 三件套、不改已实现 8 个路由的既有行为。

### 19.2 核心概念（先对齐名词）

| 概念         | 含义                                             | 本项目里的形态                                                  |
| ------------ | ------------------------------------------------ | --------------------------------------------------------------- |
| tool（工具） | 一个可以被模型主动调用的函数                     | `kbqa/tools/` 下的 `Tool`                                   |
| tool schema  | 给模型看的"工具说明书"：名字 / 用途 / 参数       | JSON Schema，由`Tool.parameters` 提供                         |
| tool_call    | 模型输出的"我要调 X，参数是 Y"                   | OpenAI 兼容协议的`message.tool_calls[]`                       |
| tool result  | 工具执行结果，回填给模型                         | `role="tool"` 的消息                                          |
| agent loop   | 「调模型 → 执行工具 → 回填 → 再调模型」的循环 | `kbqa/agent.py` 的 `AgentRunner.run`（手写）                |
| agent engine | 执行同一条 agent loop 的具体实现                 | 手写`AgentRunner` / LangGraph `GraphAgentRunner`（§19.17） |
| MCP          | 跨进程的工具协议                                 | agent 作 client，markdown server 作 server                      |
| skill        | 一组"提示词 + 允许的工具子集"                    | `skills/<name>/SKILL.md`                                      |

> **一句话区分固定链路与 agent**：固定链路里"检索"是代码里的一个 `if`；agent 里"检索"是模型的一个**选择**。

### 19.3 分层与数据流

新增一层 `agent`，位于 `pipeline` 之上、`api` 之下：

```
api  （HTTP 层，§8）
 └─ agent      ← 新增：工具注册表 + loop + MCP client + skill 加载
     ├─ tools  （本地：datetime / kb / web_search / weather）
     ├─ mcp_client（远程：MCP server 暴露的工具）
     └─ pipeline  ← 已有：知识库检索工具内部复用它
```

**一次 agent 请求的数据流**

1. 组装 messages：system（人格 + 工具使用规则 + 当前 skill 正文）、可选历史、用户问题。
2. 带工具 schema 调 LLM。
3. 模型返回 `tool_calls` → 逐个执行 → 结果按 `role="tool"` 追加进 messages。
4. 回到第 2 步，直到模型不再请求工具、直接给答案，或达到 `max_steps`。
5. 返回 `AgentRun`：最终答案 + 全部步骤轨迹。

每一步都要进 `AgentRun.steps`：前端轨迹面板（§19.10）与对照实验（§19.14）都读它。

> 上述数据流是**契约层**的约定：手写版与 LangGraph 版必须产出同样的 `AgentRun`，差异只在 loop 的内部实现（§19.17）。

### 19.4 新增目录与配置

```
kbqa/
├─ tools/                 # 新增：工具层
│  ├─ __init__.py
│  ├─ base.py             # Tool / ToolResult / ToolRegistry（§19.5）
│  ├─ datetime_tool.py    # get_datetime（T17）
│  ├─ kb_tool.py          # search_knowledge_base（T17）
│  ├─ web_search.py       # 百度搜索（T22，批次 B）
│  └─ weather.py          # 天气/生活服务（T23，批次 B）
├─ agent.py               # 手写 agent loop + AgentEngine 协议 + 引擎工厂（§19.8、§19.17，T18）
├─ agent_graph.py         # LangGraph 版 agent loop（§19.17，T28）
├─ mcp_client.py          # MCP client（§19.12，T25）
└─ skills.py              # skill 加载（§19.11，T26）
mcp_servers/
└─ md_writer/             # 自写 MCP server（§19.12，T24）
skills/                   # skill 目录（§19.11，T26）
data/exports/             # markdown 输出（artifacts，已 gitignore）
requirements-langgraph.txt  # 可选依赖：LangGraph 版本锁定（§19.17，T28）
```

**配置增量（并入 `.env.example` / `Settings`）**

| 键                                           | 默认             | 说明                                                         |
| -------------------------------------------- | ---------------- | ------------------------------------------------------------ |
| `AGENT_MAX_STEPS`                          | `5`            | loop 上限，防死循环烧钱                                      |
| `AGENT_ENGINE`                             | `handwritten`  | loop 实现：`handwritten`（默认）/ `langgraph`（§19.17） |
| `AGENT_TOOL_RESULT_MAX_CHARS`              | `2000`         | 单个工具结果回填前的截断上限                                 |
| `AGENT_HISTORY_MAX_TURNS`                  | `6`            | 多轮对话保留的历史轮数（0 = 不带历史）                       |
| `SKILLS_DIR`                               | `skills`       | skill 目录                                                   |
| `SKILL_AUTO_SELECT`                        | `true`         | 是否允许模型自动选 skill（§19.11）                          |
| `MCP_ENABLED`                              | `false`        | 是否启用 MCP 工具（false 时一切照旧）                        |
| `MCP_SERVERS`                              | 空               | MCP server 定义（§19.12）                                   |
| `EXPORT_DIR`                               | `data/exports` | markdown 输出目录                                            |
| `WEB_SEARCH_API_KEY` / `WEATHER_API_KEY` | 空               | 批次 B，见 §19.16                                           |

### 19.5 工具层契约 `kbqa/tools/base.py`

```python
@dataclass
class ToolResult:
    text: str                 # 给模型看的文本（必须已截断，见 §19.13）
    data: dict | None = None   # 给前端看的结构化数据（可空）

@dataclass
class Tool:
    name: str                  # 全局唯一，snake_case
    description: str           # 给模型看的用途说明（撰写规范见 §19.7）
    parameters: dict           # JSON Schema（手写，理由见下）
    handler: Callable[[dict], ToolResult]

class ToolRegistry:
    def register(self, tool: Tool) -> None      # 重名直接抛 ValueError（尽早暴露冲突）
    def get(self, name: str) -> Tool
    def names(self) -> list[str]
    def schemas(self) -> list[dict]             # OpenAI tools 格式，直接交给 chat_with_tools

def tool(name: str, description: str, parameters: dict) -> Callable[[Callable], Tool]
    """装饰器：把一个函数登记成 Tool（handler 只接收一个参数 dict）。"""
```

**硬约束**

- `handler` **允许抛异常**，由 agent loop 统一兜住（§19.8）；**不允许**把异常冒到 API 层。
- `parameters` 手写 JSON Schema，不用类型注解自动生成。理由：① 模型看到的就是这份 `dict`，学习者能逐字对照"模型到底看见了什么"；② 不引入额外的 schema 生成依赖与隐式行为（与 §4.3 少依赖取向一致）。
- 工具一律**同步**。本批 loop 顺序执行，先不引入并发——可观测性优先。

### 19.6 LLM 工具调用契约（`kbqa/llm.py` 扩展）

```python
@dataclass
class ToolCall:                 # kbqa/models.py
    id: str
    name: str
    arguments: str              # 模型给的原始 JSON 字符串，解析失败要在工具层兜住

@dataclass
class ChatResult:               # kbqa/models.py
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str

class LLMProvider(Protocol):
    def chat(self, messages: list[dict], temperature: float | None = None) -> str: ...   # 不变
    def chat_with_tools(self, messages: list[dict], tools: list[dict],
                        temperature: float | None = None) -> ChatResult: ...
```

- `chat()` **不得改动**：固定链路依赖它（T16 验收要求 `git diff` 只增不改）。
- `enable_thinking` 仍显式关闭：工具调用叠加思考模式时，`tool_calls` 更易解析失败（§4.2 坑 3 的延伸）。
- `tools=[]` 时 `chat_with_tools` 的行为必须与 `chat()` 等价。
- 错误仍走 `LLMError` + `_error_code`（§8）。DTO 放 `kbqa/models.py`（与 §7.2 "只放 DTO" 的定位一致）。

### 19.7 工具清单与契约

| 工具名                    | 文件                 | 参数                                                      | 返回 text                                        | 依赖                  | 批次 |
| ------------------------- | -------------------- | --------------------------------------------------------- | ------------------------------------------------ | --------------------- | ---- |
| `get_datetime`          | `datetime_tool.py` | `date?`（ISO 或 `today`/`tomorrow`）、`timezone?` | 日期 / 星期 / 时间 / 相对天数                    | 无（标准库）          | A    |
| `search_knowledge_base` | `kb_tool.py`       | `query`、`top_n?`                                     | 编号`[1]..[n]` + `文件名#序号` + 片段 + 分数 | `pipeline.retrieve` | A    |
| `web_search`            | `web_search.py`    | `query`、`count?`（默认 5）                           | 标题 + URL + 摘要                                | 百度 API + key        | B    |
| `get_weather`           | `weather.py`       | `city`、`days?`（默认 1）                             | 城市 / 日期 / 天气 / 温度（+ 定稿字段）          | 天气 API + key        | B    |
| `write_markdown`        | MCP server           | `filename`、`content`                                 | 落盘路径                                         | MCP +`EXPORT_DIR`   | C    |

**各工具的关键设计（不只是"能调通"）**

- `get_datetime`：宁可让模型用工具拿日期，也不要让它猜"今天几号"。返回文本必须含**星期**——"星期几"是语料里查不到、模型又最容易算错的信息。
- `search_knowledge_base`：内部**直接复用 `pipeline.retrieve`**（§7.10），不重写检索。返回按 `RerankResult` 顺序编号 `[1]..[n]`，编号必须与 `prompts.format_context`（§7.9）一致，否则引用会错位。
- `web_search`（批次 B）：搜索结果原始形态是网页片段，**必须裁成"标题 + URL + 摘要（每条 ≤ 200 字）"**再回填；超时 10s；失败返回错误文本、**不抛异常**。
- `get_weather`（批次 B）：参数是**城市名**不是经纬度（模型更会给城市名）；"生活服务"字段以开工前定稿为准（§19.16）。
- `write_markdown`（批次 C）：见 §19.12；只给 `filename` 与 `content`，**目录由服务端固定**，模型无权指定路径。

**`description` 撰写规范**（工具描述就是提示词工程，写不好模型就乱调或不调）

1. 一句话说清"**什么时候该用我**"，而不是"我是什么"。
2. 参数说明写清单位与格式（如"`count`：返回条数，1–10，默认 5"）。
3. 明确写出**不该用的场景**（如"不要用于知识库内已有内容——那用 `search_knowledge_base`"）。

### 19.8 agent loop 契约 `kbqa/agent.py`

```python
@dataclass
class AgentStep:                # kbqa/models.py
    index: int
    tool: str
    arguments: dict             # 已解析；解析失败记 {"_raw": "<原始字符串>"}
    result_text: str            # 已截断
    ok: bool
    elapsed_ms: int

@dataclass
class AgentRun:                 # kbqa/models.py
    answer: str
    skill: str | None           # 本次实际使用的 skill（无则 None）
    steps: list[AgentStep]
    stop_reason: str            # "final_answer" | "max_steps"
    tool_calls_count: int
    rounds: int                 # 循环轮数（每次调模型算一轮）
    latency_ms: int

class AgentRunner:
    def __init__(self, settings: Settings, registry: ToolRegistry,
                 llm: LLMProvider, skills: SkillLoader): ...
    def run(self, question: str, skill: str | None = None,
            history: list[dict] | None = None) -> AgentRun: ...
```

**循环硬约束**

1. 达到 `AGENT_MAX_STEPS` 仍未收敛 → 停止，`stop_reason="max_steps"`，把模型最后的文本（若有）当答案返回，**不抛异常**。
2. 工具抛异常 → 转成 `ToolResult(text="工具执行失败：<摘要>")`，该步 `ok=False`，循环继续（模型可换工具或如实回答）。
3. 同一工具 + 同参数**连续重复 ≥ 2 次** → 打 `WARNING`，并在回填文本里提示模型换策略。
4. 回填前按 `AGENT_TOOL_RESULT_MAX_CHARS` 截断。
5. 每步、每轮都必须进 `steps` 与日志（§19.13）。

**两版实现（§19.17）**

- 本节契约对两版**完全一致**：`AgentRun` / `AgentStep`、循环硬约束、日志打点都不得因引擎不同而改变；本节代码是手写版参考实现。
- 新增统一引擎接口与工厂：

```python
class AgentEngine(Protocol):
    def run(self, question: str, skill: str | None = None,
            history: list[dict] | None = None) -> AgentRun: ...

def create_agent_runner(settings: Settings, registry: ToolRegistry,
                        llm: LLMProvider, skills: SkillLoader) -> AgentEngine:
    """按 settings.agent_engine 返回手写版或 LangGraph 版。"""
```

- `AGENT_ENGINE=handwritten`（默认）→ `AgentRunner`；`AGENT_ENGINE=langgraph` → `GraphAgentRunner`（§19.17）。
- 工厂是 API 层唯一入口：`api/routes.py` 不得直接 import 具体实现。

### 19.9 API 契约（增量）

| 方法     | 路径                       | 说明                                                     |
| -------- | -------------------------- | -------------------------------------------------------- |
| `GET`  | `/api/agent/skills`      | 列出可用 skill（`name` + `description`），供前端下拉 |
| `POST` | `/api/agent/chat`        | 一次 agent 对话                                          |
| `POST` | `/api/agent/chat/stream` | 流式（后续任务 T27，SSE，见 §19.10）                    |

```jsonc
// POST /api/agent/chat 请求
{ "question": "今天几号？顺便看看知识库里有没有相关约定", "skill": null, "history": [] }

// 响应（200）
{
  "answer": "...",
  "skill": null,
  "stop_reason": "final_answer",
  "steps": [
    { "index": 0, "tool": "get_datetime", "arguments": {},
      "result_text": "...", "ok": true, "elapsed_ms": 3 }
  ],
  "tool_calls_count": 1,
  "rounds": 2,
  "latency_ms": 1840
}
```

- 错误沿用 §8 信封，新增 `skill_not_found` → `400`。
- **工具失败不是 HTTP 错误**：它是 `steps[].ok=false` + 200。
- **`max_steps` 也不是错误**：200 + `stop_reason="max_steps"`。

### 19.10 前端（轨迹 / skill 选择 / 流式）

- 新增 `web/src/components/AgentPanel.vue`、`ToolTrace.vue`，与现有 `AnswerCard.vue` **并列**展示（不改原有交互）。
- `ToolTrace`：逐 step 显示 序号 / 工具名 / 参数 / 结果摘要 / 耗时 / 成功失败（失败标红），默认折叠。
- skill 选择：下拉框，首项"自动"，其余来自 `GET /api/agent/skills`。
- 流式（后续任务 T27）：SSE 事件类型 `step_start` / `tool_call` / `tool_result` / `token` / `done`。
- 前端**只渲染** `steps`，不做任何编排（与 §9 前端定位一致）。

### 19.11 Skill 机制

```
skills/
└─ daily-brief/
   └─ SKILL.md      # YAML front-matter: name / description / tools
```

```markdown
---
name: daily-brief
description: 当用户想了解"今天该知道什么"时使用：日期 + 天气 + 知识库里的相关约定
tools: [get_datetime, get_weather, search_knowledge_base]
---

（正文：这个技能下的回答流程、语气、输出格式要求。只写"做什么 / 怎么回答"，不放代码。）
```

**加载策略（渐进披露）**

1. 启动只读 front-matter → 把 `name + description` 清单注入 system prompt。**正文不进**。
2. 需要时通过**工具** `load_skill(name)` 加载——选 skill 与选工具同构（§19.2）。
3. 加载后：正文进 system prompt，且把工具集**收窄**为该 skill 的 `tools`。

**硬约束**

- `tools` 只能**收窄**已注册工具，不能新增或越权使用；留空表示继承全部工具。
- `SKILL.md` 只写"做什么 + 怎么回答"，**不放代码**。
- skill 不存在 → `400 skill_not_found`。
- 触发方式**两种都要**：模型自动（经 `load_skill`）+ 请求显式指定（`skill=name`，跳过选择）。

### 19.12 MCP 集成

- **server**：`mcp_servers/md_writer/`，用官方 Python SDK（FastMCP），**stdio 传输**，暴露 `write_markdown`。
- **写盘边界**：只允许写入 `EXPORT_DIR` 之内；拒绝绝对路径与 `..`；文件名 basename 化；`content` 设长度上限。
- **client**：`kbqa/mcp_client.py` 启动时 `tools/list` → 把每个 MCP 工具包装成本地 `Tool` → 注册进同一个 registry；调用时转发 `tools/call`。
- **名称前缀**：`{server}.{tool}`（如 `md_writer.write_markdown`），避免与本地工具撞名。
- **失败隔离（硬要求）**：某个 MCP server 起不来或崩溃 → 只丢该批工具，**其余工具与 `/api/agent/chat` 仍可用**；启动失败打 `WARNING`，不阻断应用启动。
- **为什么用 stdio**：不需要网络（本机沙箱也能跑），且能直观看到"工具跑在另一个进程里"。

### 19.13 安全与日志（增量，并入 §18）

**日志新增打点（对应 §18.2）**

| 链路         | 必打日志                                               |
| ------------ | ------------------------------------------------------ |
| agent 开始   | question（截断）、skill、工具数、`max_steps`         |
| 每轮模型调用 | 轮次、messages 数、是否带工具、`finish_reason`、耗时 |
| 工具调用     | 工具名、参数（截断 / 脱敏）、耗时、成功失败、结果长度  |
| 工具失败     | `WARNING` + 错误摘要（完整堆栈不进 `INFO`）        |
| agent 结束   | `stop_reason`、步数、工具调用次数、总耗时、答案长度  |

**安全清单**

- 不打印 API Key（沿用 §18.2）；百度 / 天气的 key 只从 `.env` 读。
- 写文件工具限定目录：拒绝 `..`、绝对路径、目录穿越。
- 工具结果一律截断，防上下文爆炸。
- 外部 API 调用设超时（默认 10s），失败降级为文本结果。

### 19.14 对照实验（固定链路 vs Agent 自主）

同一批问题双跑 `/api/qa` 与 `/api/agent/chat`，记录：是否调工具 / 调了哪些 / 步数 / 工具调用次数 / 耗时 / 答案差异 / **引用是否仍正确**。产出与 §13 同风格的表。它既是学习材料，也是 M7 复盘的加分项。

> 本节对照的是"固定链路 vs Agent"；"手写 loop vs LangGraph"的引擎对照见 §19.17（T29）。

### 19.15 里程碑与验收（M8–M13）

| 里程碑                     | 内容     | 验收标准                                                             |
| -------------------------- | -------- | -------------------------------------------------------------------- |
| **M8 Agent loop**    | T15–T18 | 命令行跑通"问时间 → 模型调`get_datetime` → 回答"，`steps` 完整 |
| **M9 API + 前端**    | T19–T21 | 浏览器提一个问题，看到工具轨迹与最终答案；对照表产出                 |
| **M10 外网工具**     | T22–T23 | 真实调通百度搜索与天气（或明确记录"未联调"）                         |
| **M11 MCP + Skill**  | T24–T26 | md 落`data/exports/`；skill 自动 / 显式两种触发都生效              |
| **M12 流式**（可选） | T27      | 事件流可见，非流式接口不受影响                                       |
| **M13 双引擎对照**   | T28–T29 | 手写版与 LangGraph 版跑同一批问题，产出对照表与学习结论              |

### 19.16 待定项

| # | 问题                                                                   | 建议                                                                                             |
| - | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 1 | 百度搜索用哪个 API（千帆 AppBuilder 组件 / 百度智能云搜索 API / 其他） | 批次 B 开工前定，届时把 §19.7 的该行补成定稿                                                    |
| 2 | 天气 / 生活服务用哪家，含哪些字段                                      | 同上                                                                                             |
| 3 | 流式协议细节                                                           | 先在 T19 用非流式跑通，流式单列 T27                                                              |
| 4 | token 统计是否纳入对照                                                 | 拿得到就记；拿不到只记步数与耗时                                                                 |
| 5 | LangGraph 的版本与图写法                                               | T28 开工前在`requirements-langgraph.txt` 锁定版本；图形态按 §19.17 的最小实现，不追求复杂能力 |

### 19.17 Agent loop 双实现：手写 vs LangGraph

> 本节是 §19.8 的补充契约，目标是**对比学习**：同一份需求、同一套工具，分别用手写循环和 LangGraph 编排，观察框架到底替你做了什么、又藏起了什么。

**共同约束（两版都必须满足）**

1. **对外契约不变**：构造函数参数、`run()` 签名、`AgentRun` / `AgentStep` 字段、API 响应结构完全一致；`/api/agent/*` 不得感知引擎差异。
2. **工具来源不变**：两版都从同一个 `ToolRegistry` 取工具；本地工具、MCP 工具、skill 收窄逻辑完全复用。
3. **行为约束不变**：`AGENT_MAX_STEPS`、工具异常兜底、结果截断、重复调用告警、四类日志打点（§19.13）逐条生效。
4. **默认路径不变**：`AGENT_ENGINE` 默认 `handwritten`；框架版失败不得影响手写版与固定链路。

**引擎选择**

| 键               | 默认            | 取值                            | 说明                                           |
| ---------------- | --------------- | ------------------------------- | ---------------------------------------------- |
| `AGENT_ENGINE` | `handwritten` | `handwritten` / `langgraph` | 选择 loop 实现；`langgraph` 需先安装可选依赖 |

**目录与依赖**

```
kbqa/
├─ agent.py          # 手写 AgentRunner + AgentEngine 协议 + create_agent_runner 工厂
└─ agent_graph.py    # GraphAgentRunner（LangGraph 实现）
requirements-langgraph.txt   # 可选依赖：langgraph（版本在此锁定）
```

- LangGraph 必须**延迟导入**：`AGENT_ENGINE=handwritten` 时进程内不得出现 `import langgraph`。
- 未安装可选依赖却选了 `langgraph` → 启动时给出明确错误（缺哪个包、安装哪个文件），**不回退、不静默**。
- 对照版只依赖 LangGraph 的图编排能力，不引入 LangChain AgentExecutor / LlamaIndex。

**手写版要点（基线）**

- `while` 循环 + 显式状态；每一步自己写：调模型 → 解析 `tool_calls` → 执行 → 回填 → 判停。
- 停止条件、重复调用检测、异常兜底、截断、日志全部显式可见，便于逐行理解。
- 它是"框架替你做了什么"的对照组。

**LangGraph 版要点**

- 用 `StateGraph` 表达循环：`llm` 节点 → 条件边（有 `tool_calls` 去 `tools`，否则结束）→ `tools` 节点 → 回到 `llm`。
- 工具用 `ToolNode` 承载；`ToolRegistry` 中的每个 `Tool` 包装成 LangGraph 可识别的工具，`handler` 保持不变（异常仍按 §19.8 转成错误文本）。
- 循环上限用图的 `recursion_limit` 对齐 `AGENT_MAX_STEPS`；触顶时把最后文本作为答案并置 `stop_reason="max_steps"`，不抛异常。
- 历史消息、skill system prompt、工具收窄在**进入图之前**完成；图内只负责"模型 ↔ 工具"循环。
- 必须把 LangGraph 的消息轨迹**映射回 `AgentRun.steps`**（工具名、参数、结果、耗时、ok），否则前端与对照实验无法复用。
- 重复调用检测、结果截断、日志打点由包装层补齐，不得依赖框架的默认行为。

**对照实验（T29）**

同一批问题分别用两个引擎跑，记录：

| 维度       | 说明                                                                                               |
| ---------- | -------------------------------------------------------------------------------------------------- |
| 结果一致性 | 最终答案与引用是否等价；不一致的案例逐条列出                                                       |
| 轨迹       | 步数、工具调用次数、调用了哪些工具                                                                 |
| 性能       | 总耗时、每轮耗时（token 统计若拿得到则记录）                                                       |
| 代码量     | 两个实现的 LOC 与文件数                                                                            |
| 学习结论   | 框架替你做了什么（状态管理、条件边、工具节点、消息裁剪）；哪些行为被隐藏了（重试、异常、停止条件） |

产出 `eval/agent_engine_compare.md`。结论按"手写版 / LangGraph 版各自适合什么场景"来写，不写"谁更好"的空话。
