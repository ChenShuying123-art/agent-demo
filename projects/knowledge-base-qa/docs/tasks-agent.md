# Agent 化任务拆解（T15–T29）

| 项目 | 内容 |
|------|------|
| 文档版本 | v1.0（沿用 tasks.md） |
| 配套文档 | [spec-agent.md](./spec-agent.md)（Agent 设计契约，本文档不重复其内容） |
| 任务范围 | T15–T29，共 15 个任务（批次 A–D + 双引擎对照） |
| 前置条件 | MVP（T0–T14）已完成 |
| 状态 | 待开工 |

> 本文档由 [tasks.md](./tasks.md) 拆分而来。通用约定（一个任务一次对话、标准 Prompt 模板、四条纪律、`CMD/NB/LOG/CHK` 验收形式）见 [tasks.md](./tasks.md) §0，本文档不再重复。
> 本文中的 `§19.x` 均见 [spec-agent.md](./spec-agent.md)；其余章节（如 §7.8、§8、§18）见 [spec.md](./spec.md)。
> 依赖关系图与进度追踪见 [tasks.md](./tasks.md) §2、§4；文档目录见 [tasks-index.md](./tasks-index.md)。

---

## 1. 任务清单（T15–T29）

> 设计契约见 [spec-agent.md](./spec-agent.md) §19，本清单不重复其内容。
> **前置条件**：MVP（T0–T14）已完成。批次 B（T22/T23）额外需要百度搜索与天气 API 的 Key（见 §19.16），
> 且需要能访问外网；本机沙箱默认无外网，因此批次 B 的验收允许先"mock 跑通、再真实联调"，但**必须如实记录联调状态**。
> 批次 C（T24/T25）用 stdio 传输，不需要外网。

### T15 —— 工具基础层 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T0 |
| **产出** | `kbqa/tools/__init__.py`、`kbqa/tools/base.py` |
| **契约** | §19.2、§19.5 |
| **验收** | `CMD` 注册一个假工具 `echo(text)` → `registry.schemas()` 输出合法 JSON Schema（`json.dumps` 打印后核对结构：`type/function/name/description/parameters`）<br>`CMD` 调用该工具 → 拿到 `ToolResult.text`<br>`CMD` 注册重名工具 → 抛 `ValueError`<br>`CHK` 本层**不**吞 `handler` 抛出的异常（由 T18 的 loop 兜住）——本层只做注册与查找<br>`CHK` 未引入 `requirements.txt` 之外的新依赖 |
| **禁止** | 不实现 agent loop、不实现具体工具、不碰 `llm.py` |

### T16 —— LLM 工具调用 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T15 |
| **产出** | `kbqa/models.py`（新增 DTO）、`kbqa/llm.py`（新增方法） |
| **契约** | §19.6、§7.8 增量 |
| **验收** | `CMD` 传一个 `echo` 工具的 schema + "请调用 echo 说 hi" → `ChatResult.tool_calls` 非空且 `name="echo"`<br>`CMD` 把工具结果作为 `role="tool"` 消息回填后再调一次 → `tool_calls` 为空、有最终 `content`<br>`CMD` `tools=[]` 时的结果与 `chat()` 等价（同 prompt 各跑一次，文本均非空）<br>`LOG` 工具调用打点（参数截断、耗时）<br>`CHK` `git diff` 显示 `chat()` **只增不改** |
| **禁止** | 不改 `chat()`、不改 `pipeline.py`、不写 agent loop |

### T17 —— 本地工具：日期时间 + 知识库检索 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T15 |
| **产出** | `kbqa/tools/datetime_tool.py`、`kbqa/tools/kb_tool.py` |
| **契约** | §19.7（`get_datetime`、`search_knowledge_base`） |
| **验收** | `CMD` `get_datetime` 默认参数 → 文本含年月日与**星期**<br>`CMD` 传 `"tomorrow"` → 日期为次日<br>`CMD` `search_knowledge_base` 检索一篇已索引文档 → 返回编号 `[1]..`，每条含 `文件名#序号`、片段、分数<br>`CMD` 空库 / 无命中 → 返回"未检索到"文本而非异常<br>`CHK` 单条结果长度 ≤ `AGENT_TOOL_RESULT_MAX_CHARS`<br>`LOG` 两个工具都按 §19.13 打点 |
| **禁止** | 不重写检索（必须复用 `pipeline.retrieve`）、不改 `prompts.py` 的 `format_context` |

### T18 —— agent loop 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T15、T16、T17 |
| **产出** | `kbqa/agent.py` |
| **契约** | §19.8 |
| **验收** | `CMD` 问"今天是几号、星期几" → `AgentRun.steps` 含 `get_datetime`，`stop_reason="final_answer"`<br>`CMD` 挂一个"每次都要求再调一次"的假工具 → 停在 `AGENT_MAX_STEPS` 且**不抛异常**<br>`CMD` 挂一个必抛异常的工具 → 该步 `ok=False`、循环继续、最终仍有答案<br>`CMD` 检查 `steps[].result_text` 长度均 ≤ 上限<br>`LOG` 开始 / 每轮 / 每次工具 / 结束 四类打点齐全 |
| **禁止** | 不写 HTTP 路由、不接 MCP、不实现 skill |

### T19 —— agent API 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T18 |
| **产出** | `api/schemas.py`、`api/routes.py`（+2 路由；`chat/stream` 留 T27） |
| **契约** | §19.9、§8 |
| **验收** | `CMD` `POST /api/agent/chat {"question":"今天几号"}` → 200，响应含 `answer` / `steps` / `stop_reason`<br>`CMD` 带不存在的 `skill` → 400 `skill_not_found`<br>`CMD` 让工具全部失败 → 仍 200（工具失败是 `steps[].ok=false`）<br>`CMD` 触发 `max_steps` → 200 + `stop_reason="max_steps"`<br>`CMD` `/api/health`、`/api/qa` 回归通过 |
| **禁止** | 不改已有 8 个路由的行为、不在路由层写编排逻辑 |

### T20 —— 前端：工具调用轨迹 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T19 |
| **产出** | `web/src/components/AgentPanel.vue`、`web/src/components/ToolTrace.vue`、`web/src/api.ts`（+2 方法） |
| **契约** | §19.10 |
| **验收** | `NB` 浏览器提问 → 出现最终答案 + 轨迹列表<br>`NB` 失败步骤标红、可展开看错误文本<br>`NB` skill 下拉默认"自动"，可切换后重新提问<br>`NB` 原有上传 / 检索 / 问答面板功能未受影响 |
| **禁止** | 不在前端做编排或工具执行、不改 `AnswerCard.vue` 的既有展示 |

### T21 —— 对照实验：固定链路 vs Agent 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T9、T18、T19 |
| **产出** | `eval/agent_compare.py`（或 `notebooks/04_agent_compare.ipynb`）+ 一张对照表 |
| **契约** | §19.14 |
| **验收** | `CMD` 一条命令对同一批问题双跑 → 产出 `agent_compare.md`（含 是否调工具 / 调了哪些 / 步数 / 工具次数 / 耗时 / 引用是否仍正确）<br>`NB` 能指出至少 2 个"agent 选择与固定链路不同"的案例 |
| **禁止** | 不改 `/api/qa` 与三风格提示词 |

### T22 —— 百度搜索工具 🤖（批次 B）

| 字段 | 内容 |
|------|------|
| **依赖** | T18 |
| **产出** | `kbqa/tools/web_search.py` |
| **契约** | §19.7（`web_search`）——**开工前把该行补成定稿**（用哪个百度接口、鉴权方式、返回字段） |
| **验收** | `CMD` 直接调用工具 → 返回 ≤5 条，每条"标题 + URL + 摘要（≤200 字）"<br>`CMD` 错误 key / 断网 → 返回错误文本、**不抛异常**<br>`LOG` key 不出现在日志中<br>`CHK` 如实记录"是否真实联调"（mock 也允许，但不得写成联调通过） |
| **禁止** | 不做重试队列 / 缓存；不引入 `requirements.txt` 之外的依赖（除非用户确认） |

### T23 —— 天气 / 生活服务工具 🤖（批次 B）

| 字段 | 内容 |
|------|------|
| **依赖** | T18 |
| **产出** | `kbqa/tools/weather.py` |
| **契约** | §19.7（`get_weather`）+ 同 T22 的定稿要求 |
| **验收** | `CMD` 传城市 → 返回 城市 / 日期 / 天气 / 温度（+ 定稿字段）<br>`CMD` 传不存在的城市 → 明确错误文本、不抛异常<br>`CHK` 超时为 10s |
| **禁止** | 不做地图 / 定位联动 |

### T24 —— MCP server：markdown 写入 🧩（批次 C）

| 字段 | 内容 |
|------|------|
| **依赖** | T0 |
| **产出** | `mcp_servers/md_writer/`（server + 依赖说明） |
| **契约** | §19.12 |
| **验收** | `CMD` 用 MCP 官方 inspector（或客户端）列工具 → 出现 `write_markdown`<br>`CMD` 调一次 → `data/exports/` 下出现文件且内容一致<br>`CMD` `filename="../../evil.md"` → 被拒绝<br>`CHK` 输出目录外无法写入 |
| **禁止** | 不做 HTTP 传输、不在同一 server 里塞其它工具 |

### T25 —— MCP client：工具并入 registry 🤖（批次 C）

| 字段 | 内容 |
|------|------|
| **依赖** | T18、T24 |
| **产出** | `kbqa/mcp_client.py`、配置读取（`MCP_ENABLED` / `MCP_SERVERS`） |
| **契约** | §19.12 |
| **验收** | `CMD` 启动 → registry 里出现 `md_writer.write_markdown`<br>`CMD` 问"把刚才的答案存成 md" → 文件落在 `data/exports/`<br>`CMD` 故意把 server 命令改错 → 应用仍能启动、其余工具仍可用、日志有 `WARNING`<br>`LOG` 名称前缀正确、无撞名 |
| **禁止** | 不把 MCP 做成"必需依赖"（`MCP_ENABLED=false` 时一切照旧） |

### T26 —— Skill 机制 🤖（批次 D）

| 字段 | 内容 |
|------|------|
| **依赖** | T18、T19 |
| **产出** | `skills/`（≥2 个示例 skill）、`kbqa/skills.py`、`GET /api/agent/skills`、`load_skill` 工具 |
| **契约** | §19.11 |
| **验收** | `CMD` `GET /api/agent/skills` → 返回 `name` + `description` 列表<br>`CMD` 显式 `skill=xxx` → 实际可用工具被收窄到该 skill 的 `tools`<br>`CMD` 不指定 skill、提一个贴合某 skill 的问题 → 模型经 `load_skill` 命中该 skill<br>`CMD` 请求不存在的 skill → 400<br>`NB` 对照实验：全部预载 vs 按需加载（token / 选择正确率）各跑一次 |
| **禁止** | 不允许 skill 越权声明未注册工具；`SKILL.md` 内不得包含代码 |

### T27 —— 流式输出（可选 / 后续）🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T19、T20 |
| **产出** | `POST /api/agent/chat/stream`（SSE）、前端订阅逻辑 |
| **契约** | §19.10 |
| **验收** | `CMD` `curl` 能看到分片事件（`step_start` / `token` / `done`）<br>`NB` 前端逐字出现，同时轨迹面板实时刷新 |
| **禁止** | 不改非流式的 `/api/agent/chat` |

### T28 —— LangGraph 版 agent loop 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T18（T17 的工具直接复用） |
| **产出** | `kbqa/agent_graph.py`、`requirements-langgraph.txt`、`kbqa/agent.py`（新增 `AgentEngine` 协议与 `create_agent_runner` 工厂）、`kbqa/config.py`（`AGENT_ENGINE`）、`.env.example` |
| **契约** | §19.8、§19.17 |
| **验收** | `CMD` `AGENT_ENGINE=handwritten` → 与 T18 行为一致，且进程内**不导入 langgraph**<br>`CMD` `AGENT_ENGINE=langgraph` → T18 的四条验收全部通过（时间问题、`max_steps`、工具异常、结果截断）<br>`CMD` 同一问题两个引擎各跑一次 → `AgentRun` 字段齐全且结构一致，`steps` 能还原工具名 / 参数 / 结果 / 耗时 / ok<br>`CMD` `AGENT_MAX_STEPS` 触顶 → `stop_reason="max_steps"` 且不抛异常<br>`CMD` 未安装可选依赖却设 `langgraph` → 启动报明确错误（提示安装 `requirements-langgraph.txt`）<br>`LOG` §19.13 四类打点齐全 |
| **禁止** | 不改 `AgentRun` / API 响应结构；不让 langgraph 成为默认依赖；不在图内重写工具实现 |

### T29 —— 双引擎对照实验 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T18、T28 |
| **产出** | `eval/agent_engine_compare.py`（或 notebook）、`eval/agent_engine_compare.md` |
| **契约** | §19.17 |
| **验收** | `CMD` 一条命令对同一批问题双跑 → 产出对照表（结果一致性 / 步数 / 工具次数 / 耗时 / 代码量）<br>`NB` 能指出至少 2 个"两版行为不同"的案例并解释原因<br>`CHK` 结论按"框架替你做了什么 / 隐藏了什么"归因，不写空泛评价 |
| **禁止** | 不改工具实现与 `/api/agent/chat` 契约；不得为了对齐结果而给某一版特殊照顾 |

---

## 2. Agent 化里程碑

| 里程碑 | 任务 | 验收标准 |
|--------|------|----------|
| **M8 Agent loop** | T15–T18 | 命令行跑通"问时间 → 模型调 `get_datetime` → 回答"，`steps` 完整 |
| **M9 API + 前端** | T19–T21 | 浏览器看到工具轨迹与最终答案；对照表产出 |
| **M10 外网工具** | T22–T23 | 真实调通（或如实记录"未联调"） |
| **M11 MCP + Skill** | T24–T26 | md 落 `data/exports/`；skill 两种触发都生效 |
| **M12 流式**（可选） | T27 | 事件流可见，非流式接口不受影响 |
| **M13 双引擎对照** | T28–T29 | 手写版与 LangGraph 版跑同一批问题，产出对照表与学习结论 |
