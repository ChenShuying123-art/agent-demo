# 教学笔记（供后续会话参考）

## 关于学习者
- 起点（2026-10-05 修正，见 learning-records/0002）：**只掌握 Python 基础语法**；高级语法（类型注解 / 类与继承 / 装饰器）与工程化概念（包结构 / 环境变量 / 日志 / 依赖管理）都不熟悉。
- 因此：**任何超出基础语法的东西都要先解释**，不能用"这个你应该知道"跳过。
- 讲解顺序：先拆掉用到的语法 / 工程概念 → 再讲顺序与方法。两者都要讲。
- 偏好"一次讲透一个点"，不要铺开成一门大课。

## 交流与产出
- 用中文。
- 教学材料放 `learning/`，不回写进项目代码目录。
- 提供官方文档链接时，**优先中文官方文档**；无官方中文时才用英文，并在正文/资源清单里注明"英文，无官方中文"。
- 课程形式：跟着 RAG 项目的任务走，一个任务 = 一课（当前只做 T0）。

## 教学节奏（用户明确要求）
- **每完成 tasks.md 里的一个任务，必须产出一课**：`lessons/NNNN-*.html`，并同步更新术语表 / 资源清单。
- 每课必须回答两个问题：① 如果我自己从零写这个任务，步骤是什么？② 我能带走什么可复用的东西？
- 课程编号按创建顺序自增；逻辑上是前置课的在正文标注建议阅读顺序。
- 完成后主动打开课程 html 给用户看。

## 进行中的范围
- 已完成：T0–T10（各产出一课）。
- **T3 真实验收已通过**：15 条 → 2 批（10+5）→ 顺序一致（逆序校验余弦 1.000000）→ 1024 维；`dimensions` 参数被接口接受；L2 范数 = 1.0（接口本就返回单位向量）；语义相近 0.9301 > 完全无关 0.8952（差距不大，属该模型分数尺度偏高）。

## ⚠️ 2026-10-05 凭据事故（已处理）
- 用户把真实 `DASHSCOPE_API_KEY` 填进了 **`.env.example`**（git 跟踪的模板文件），并被提交进本地提交 `32bb37f`（**未推送到远程**）。
- 已做：把 Key 挪进 `.env`（gitignore 已忽略）、把 `.env.example` 还原为占位符 `sk-xxxxxxxx`。
- **待用户执行**：改写 `32bb37f` 以清除历史中的 Key（沙箱禁止 AI 写 `.git`，AI 无法代劳）：
  `git add .env.example` → `git commit --amend --no-edit` → 确认 `git grep -c "sk-xxxxxxxx" HEAD -- .env.example` 返回 1。
- 建议：轮换 Key；在改写完成前**不要 push**。
- 教学要点：`.env.example` 是模板（要提交）、`.env` 是真配置（不提交）——已写进课程 0005。

## 概念补课（2026-10-05 · 第二次）：依赖注入

- T9 完成后，用户追问 `RAGPipeline.__init__` 里"依赖注入"是什么意思（课程 0011 提到过，但当时只给了结论）。
- **已扩成独立课程：`lessons/0013-dependency-injection.html`**
  （含"自己 new vs 注入"代码对比、控制反转、三个替换场景、打印机墨盒类比、"别过度"的判断标准、三件套装配图、4 道练习 + 5 道自测）
- 用户易混点：把 "new" 当成 Python 关键字（其实对应"构造函数调用"）；以及以为依赖注入必须靠框架。
- 术语表新增：**控制反转（IoC）**、**自己 new**。
- 教法结论：讲这类抽象概念时，**"反面写法 + 具体失败场景"比正面定义有效得多**（例：自己 new 会让测试真的去调外部接口、要花钱）。
- 后续若再出现类似追问，可沿用 0013 的结构：先澄清术语 → 两版代码并排 → 场景对比 → 类比 → 反例（别过度）。

## 下一步
- T11（Vue 3 + TS + Vite 前端 `web/`）——M6 里程碑；契约 §9。
  ⚠️ 前置提醒：`GET /api/documents` 的 `indexed` / `chunk_count` 目前恒为 `False` / `0`（见下方"T1 遗留"待办），
  前端要做"状态徽标 / chunk 数"就得先补上这一处跨模块修改（需用户确认后再动 `loaders.py`）。

## T10 已完成（2026-10-06）—— FastAPI 接口层

## Agent 化规划已定（2026-10-13）—— 新任务 T15–T27

- 目标：在现有 RAG MVP 之上"加工具 + 加 MCP + 加 skill"，用于**学习 agent 开发**。已确认的边界：
  - 保留固定链路 `/api/qa` 作对照；agent 走新路由 `/api/agent/chat`。
  - 四类工具：知识库检索、日期/时间（**本地计算**，不接第三方）、百度搜索、天气/生活服务。
  - "生成 markdown 文件"用**自写 MCP server + agent 作 MCP client**，md 落 `data/exports/`。
  - skill 面向**本 agent**（提示词 + 工具子集，按需加载）；触发方式**模型自动 + 用户显式都要**。
  - 前端：工具轨迹面板（T20）与流式（T27）都要，作为后续任务。
- 设计契约：`docs/spec.md` §19；任务卡：`docs/tasks.md` §6（T15–T27）。
- 待外网确认（批次 B 开工前）：百度搜索用哪个 API、天气用哪家、各自 Key；本机沙箱默认无外网，需"先 mock 再真实"。
- 教学安排（沿用"一任务一课"）：从 `lessons/0018-*.html` 起，建议主题序列：
  工具 schema → agent loop → 工具结果裁剪与错误处理 → 轨迹可观测 → MCP（client/server / stdio）→ skill 渐进披露 → 流式。
  每课照旧回答两问：① 我自己从零写会怎么做 ② 能带走什么。
- 状态备注：T11 已完成（见 git log），旧条目"进行中的范围：已完成 T0–T10"已过期；T12–T14（出题 / 评测 / 复盘）与本次 Agent 化并行、不冲突。
- 新增 `api/schemas.py` / `api/routes.py` / `api/main.py`，**未改动 `kbqa/` 任何文件**（薄接口层）。
- ⚠️ **路由数 8 而非 tasks.md 写的 9**：spec §8 表实为 10 条，其中 `/api/eval/prompt`、`/api/eval/ablation` 依赖 T13 才写的 `kbqa/evaluate.py`，
  经用户确认**留到 T13 完成后补挂**。本轮实现：health / documents(GET,POST,DELETE) / index / retrieve / qa / qa.compare。
- 关键实现（教学要点，课程 0014）：
  - 对外 schema（pydantic `BaseModel`）与内部 dataclass **分两套**，用 `to_xxx_out()` 转换（`Path → str`、pipeline 的 `elapsed_ms` → 对外的 `ms`）。
  - 统一错误信封 `{error:{code,message}}`，由 `install_exception_handlers` 集中翻译：ValueError→400、ApiError→404、校验→422、LLMError/OpenAIError→**502 透传百炼 code**、兜底→500。
  - `app.state` 挂 `pipeline` + `store`（**共用同一 store 实例**，否则"索引了却删不掉向量"）；`create_app()` 只在启动跑一次。
  - `mount("/")` 必须放在 `include_router` 之后；`web/dist` 不存在则跳过（T11 未构建时也能启动）。
  - `health` **不真实调用模型**（避免高频探针烧额度），模型可用性由 `/api/qa` 的 502 暴露。
- 实测（`uvicorn api.main:app --port 8010`，启动无报错；`/docs` 200）：
  - `/api/health` → `{"status":"ok","chat_model":"qwen-plus","embedding_model":"text-embedding-v4","rerank_model":"qwen3-rerank"}`
  - 端到端：上传 `tasks.md`（命中去重）→ 索引 40 chunk / 4 批 / 2096ms → `/api/retrieve` `candidates=20,used=4,degraded=false` → `/api/qa` 194 字 / 3 引用 / latency 4232ms
  - 错误路径：假 doc_id → `400 invalid_request`；DELETE 不存在 → `404 document_not_found`；漏 question → `422 validation_error`；风格非法 → `400 invalid_request`
- ⚠️ **发现的上游缺口（非接口层问题）**：`GET /api/documents` 的 `indexed`/`chunk_count` 恒为 `False`/`0`，根因是 T1 的 `loaders.list_documents()` 还没读 `data/index/docs.json`（见文末"T1 遗留"待办）→ 已列入 T11 前置提醒。
- 教学要点：接口层是"翻译官"不是"干活的人"（判断标准：删掉框架，核心库仍完整）；对外 schema 与内部 DTO 为什么分两套；错误信封与 502 透传；Web 版依赖注入 = `app.state`；"先离线后联网"的自测顺序。
- 追加产出（用户要求，2026-10-06）：`reference/fastapi-usage.html` —— 面向"不熟 FastAPI 语法"的**用法手册**，所有例子对照 `api/` 真实代码：
  最小应用 → APIRouter/装饰器 → **参数来源表（本手册核心）** → BaseModel 校验 → response_model → async/def → `Request`+`app.state`（并顺带澄清 `Depends`）→ 异常处理三种写法 → UploadFile → `/docs` → StaticFiles 挂载顺序 → TestClient → 坑清单 → 一页速查。已从课程 0014 的"配套"链接过去。


## 概念补课（2026-10-06）：自定义异常与 @app.exception_handler
- 用户对 FastAPI 速查表里"raise 自定义异常，配合 @app.exception_handler"不懂 → 扩成独立课程 **`lessons/0015-exception-handler.html`**。
- 结构：先补 Python 异常语法（raise / try-except / 冒泡）→ 反面写法（每个地方自己拼响应）→ 逐行拆 `ApiError` → 讲清 `@app.exception_handler` = 登记"异常类型 → 处理函数"的表（与路由表同构）→ 就近匹配 + `Exception` 兜底（必须 `logger.exception`）→ 对比 `HTTPException` → 实测 → 反例（别造一堆异常类）→ 4 练习 + 4 自测。
- 实测（最小应用复现，未烧模型额度）：未处理 `RuntimeError` → `500 {"error":{"code":"internal_error",...}}`（终端同时打印完整堆栈）；`ApiError(409, "conflict_demo", ...)` → `409` 同一信封。
- 教学要点：异常是对象、可挂字段；自定义异常让"错误从一句话变成有结构的数据"；抛的人只管"什么错"、长什么样由顶层一张表决定（关注点分离）；深层代码抛 `ValueError` → 顶层翻译成 400，核心库因此**不认识 HTTP**。
- 术语表新增：`raise`/异常、`try/except`（语法）；异常冒泡/调用栈、自定义异常、异常处理器、关注点分离（工程）。FastAPI 手册第八节也加了指向 0015 的链接。


## 概念补课（2026-10-06）：应用装配 —— main.py / app = create_app() / 静态托管
- 用户读 `api/main.py` 问了三点：为什么要有 main.py、最后一行 `app = create_app()` 为什么这么写、"托管前端静态资源"是什么意思 → 扩成 **`lessons/0016-app-assembly.html`**。
- 结构：main.py 职责（入口 / 装配清单五步 / "零件 vs 装车"类比）→ 逐层拆 `app = create_app()`（uvicorn 找的是模块里的**变量** / 工厂能重复装配供测试 / **import 只执行一次 = 模块级单例** / `--factory` 另一种写法）→ 静态托管（静态 vs 动态 / 开发 vs 生产模式 / `StaticFiles` + `mount` / `is_dir()` 判断 / 顺序坑）→ 三问速答表 → 3 练习 + 4 自测。
- 实测：`import api.main as m1, m2` → `m1 is m2` = True、`m1.app is m2.app` = True；`create_app() is not app` = True；日志里"索引已加载"出现两次 → 证明装配确实在 import 时执行。
- 术语表新增：入口文件、import 缓存/模块只执行一次、副作用、静态资源、挂载（mount）。
- 教学要点：`app = create_app()` = 工厂（可重复造）+ 模块级单例（只造一份）两件事合一；`import` 是有副作用的（fail fast 的手段）；`mount` 是"一整片 URL 区域"，不同于路由的"精确匹配"。


## 小问答（2026-10-07）：`Path()` 是什么语法
- 用户问 `kbqa/config.py` 里 `data_dir: Path = Path("data")` 的 `Path()` 是什么语法。
- 结论：**不是特殊语法**，就是"调用 `pathlib.Path` 这个类造对象"（和 `Settings()` 同理）；`data_dir: Path` 只是类型注解。重点澄清两件事：① 用 Path 而非字符串是为了跨平台 + 方法随对象带；② `Path("a") / "b"` 里的 `/` 是**运算符重载**，不是除法。
- 术语表新增：`Path（pathlib）`（工程）、`运算符重载`（语法）。概念较小，**未单独开课**。


## 课程 0009 扩充（2026-10-07）：三套适配器 + "什么时候不该抽"
- 用户追问"把外部依赖都收进适配器 + 工厂"没完全懂 → 结合本项目代码讲通后，**补进课程 0009**（不另开课，避免与既有内容重复）。
- 新增**第十一节「纵深：把三套适配器放在一起看」**：① 三套对称结构表（协议/适配器/工厂 × 对话/向量/重排）② **`pipeline.py` 不 import openai/httpx 的证据** ③ 适配器"五种翻译"清单（接口形状 / 厂商私有参数 / 返回值归一 / 异常形状 / **吸收不可靠性=降级**）④ "换实现只改一处"的改动范围表。
- ⚠️ **重要修正**：本项目**文件系统并没有抽适配器**（`loaders` / `vectorstore` 直接用 `pathlib` + `np.save`）。补上"要不要抽"的**三问判断**：会不会变 / 有没有第二个实现（含测试替身）/ 有没有外部怪癖；三问皆否就别抽——反例是 `chunking.py`（纯函数，套协议只多一层跳转）。并说明文件系统**何时**该抽（多后端 / 需要假实现时才定义 `StorageProvider`）。
- 练习 A–D → 追加**练习 E**（用 `FakeLLM` 替身跑通 `RAGPipeline`，省掉最贵的一步生成调用）；自测 6 题 → **7 题**（新增"要不要抽"的判断题）。
- ⚠️ 编辑过程中该文件被 IDE 旧缓冲覆盖多次（编号改动丢失/重号），已逐项重新核对修复；提醒用户：改 `learning/` 下的文件时若 IDE 开着，注意不要让旧缓冲保存覆盖。

## 收官课（2026-10-07）：全栈 + Agent 地图 —— 课程 0017
- 用户自述"RAG 基本功能都实现了，想梳理前后端开发流程、总结全栈与 Agent 开发" → 产出 **`lessons/0017-fullstack-agent-map.html`**（覆盖 T0–T11 的收束课）。
- 结构：① 全景图（一次提问的完整旅程 + spec §10 九步表）② 三层架构与"删掉框架还能跑"判断标准 ③ 为什么开发顺序是"由内而外" ④ 每层用什么工具验证（Notebook / TestClient / 浏览器）⑤ **七条贯穿全程的工程原则**（配置外置、依赖注入、薄层、统一错误、可观测、控制变量、不变量）⑥ Agent/RAG 心智模型（检索=找证据、两阶段分工、提示词即契约、幻觉与拒答、没评测就没工程）⑦ 前端 dev/prod 两形态 ⑧ 任务→概念→课程 索引表 ⑨ "从零做类似项目"9 步 ⑩ 4 道自测 quiz ⑪ 后续 T12–T14 与 Agent 化路线。
- 术语表新增：**分层架构 / 薄层、可观测性、消融实验、LLM-as-judge**。
- 定位：不教新语法，是"把前 16 课拼成一张地图"；用户若能对着它自己讲一遍，即视为达到 MISSION 的 "success looks like"。


## T9 已完成（2026-10-05）—— 里程碑 M3 + M4 ✅
- `kbqa/pipeline.py` 补齐：`index_documents` / `answer` / `answer_all_styles` / `_generate` / `_extract_citations`。
  （`index_documents` 在 tasks.md 里没明确归属，我按 §7.10 的类契约补在 T9——T8 只做了检索三段。）
- `notebooks/03_qa_prompt_compare.ipynb` 新增并跑通（本环境无 jupyter，仍用「json 读 cell + 顺序 exec」）。
- 实测（问题："召回和重排有什么区别？各自的取舍是什么？"）：
  - 三版风格差异肉眼可辨：strict = 4 条分点 +「依据来源」行（8242ms，引用 2）；concise = 一句话（3276ms，引用 1）；
    socratic = 结论/依据/延伸思考三段 + 追问（8671ms，引用 3）
  - 引用编号全部 ≤ 参考资料条数 4：strict `[1,1,2,2,1,2]` / concise `[1]` / socratic `[1,1,2,3]`
  - 拒答题（"珠穆朗玛峰的海拔是多少米？"）三版都明确拒答，且**没有编造任何具体数值**
  - `candidates` 长度 20 == `retrieve_top_k`；`used` 长度 4 == `rerank_top_n`；`latency_ms` 均为正
  - 本轮 rerank 排名变化 4/4（20 条候选 → 4 条，全部位置有变动）
- ⚠️ **一个真实观察**：切分把 markdown 表格从中间截断，参考资料里出现残缺表行（如 `| 召回率… |`）。
  不是 bug，是 `chunk_size=500` 硬切的固有代价。→ T12 出题尽量避开表格密集段落；T13 复盘若发现某些题效果差，先回头看切分。
- 教学要点（课程 0012）：`answer_all_styles` 只检索一次 = §12.1 控制变量在**编排层**的落地；
  引用反查用 `used[n-1]`；越界引用「忽略 + 告警」；latency 共用同一份检索耗时而不叠加。


## T8 已完成（2026-10-05）—— 里程碑 M2 ✅
- `kbqa/pipeline.py` 完成检索三段：`recall` / `rerank` / `retrieve`（+ 内部 `_degrade`）。
  ⚠️ 按 tasks.md「先实现 recall / rerank / retrieve」，**`index_documents` 未实现**，留到 T9（连同 answer / answer_all_styles）。
- `notebooks/02_retrieval.ipynb` 新增并跑通：① 召回 20 条 → ② 重排 4 条 → ③ 排名变化 3/4。
- 实测（语料 = 项目自己的 `docs/spec.md` + `docs/tasks.md`，共 172 个 chunk）：
  - 召回 20 条，cosine 0.6508 ~ 0.7256（挤在一起），top1 = 0.7256
  - 重排后 4 条：original 0/11/4/14 → new 0/1/2/3，rerank 0.9677 / 0.9664 / 0.8387 / 0.8181（拉得开）
  - `use_rerank=False` → `used == candidates[:4]` 且全部 `degraded=True`
  - `doc_ids` 过滤在召回阶段生效
  - 耗时：召回 ~0.2s，重排 ~1.0s，完整检索 1.1s（不重排仅 0.2s）
- ⚠️ **环境问题**：本项目当前 Python 环境**没有 jupyter 栈**——`jupyter nbconvert` 静默失败（退出码 0 但什么都不写），`pip install` 也无网络（输出被吞、日志为空）。
  02 的验证改用「标准库 json 读出每个 code cell + 顺序 exec」，语义等价于从上到下跑一遍 Notebook，全部断言通过。
  → **用户若要交互式运行 Notebook，需在自己的环境里装 jupyter**（`pip install notebook ipykernel`）。
- ⚠️ **演示语料**：为让 02 有数据可查，已把 `docs/spec.md`、`docs/tasks.md` 经 `save_upload` 写入 `data/uploads/`。
  用户若要换成自己的文档（P0-5），删掉这两个文件、并在索引里 `remove_document` 对应 doc_id 后重新入库即可。
- 教学要点（课程 0011）：编排层要薄（顺序/边界/可观测）；分阶段暴露是为了消融实验；
  `original_rank → new_rank` 是重排成绩单；cosine 区分度窄 vs rerank 区分度宽 = 两阶段检索的实证依据。


## T7 已完成（2026-10-05）
- `kbqa/prompts.py` 完成：`PROMPT_STYLES` / `SHARED_CONSTRAINTS` / `STYLE_BODIES` / `build_messages` / `format_context`。
- ⚠️ 提示词正文**逐字来自 spec §12.3**，未做任何改写。已用程序从 `docs/spec.md` 抽出原文与代码常量做 SHA-256 比对：
  SHARED_CONSTRAINTS len=311、strict 303、concise 202、socratic 324，四段全部一致。
- 实测：三版 system prompt 前 311 字逐字相同且等于 `SHARED_CONSTRAINTS`；user 消息 = 【参考资料】+ format_context + 【问题】+ question；
  `format_context` 编号与传入顺序一致（含空列表、倒序边界）；未知 style 抛 `ValueError`。
- ⚠️ **改提示词必须先改 spec §12.3**，再同步代码（§12.4 清单亦如此要求）；否则评测结论无法对应到设计。
- 教学要点（课程 0010）：两段式拼接 = 控制变量法的代码实现；"编号 → 引用 → 溯源"因果链；逐字照抄要用程序比对而非肉眼。


## T6 已完成（2026-10-05）
- `kbqa/llm.py` 完成：`LLMProvider` / `DashScopeChat` / `get_llm`；验收三条全部通过。
- 实测：正常调用返回非空答案（qwen-plus，100 字，耗时 1.6s）；`extra_body={"enable_thinking": False}` 确认带到请求上；
  错误 Key → 抛 `LLMError`，`code=invalid_api_key`，且异常信息里含该 code。
- 两处小扩展（已做，需知悉）：
  ① 新增 `LLMError(RuntimeError)`，带 `.code` 属性，便于 T10 按 §8 透传 code；
  ② `chat(..., temperature=None)` 中的 None 解释为"用配置里的 `chat_temperature`"
     （否则 `.env` 里那个配置项改了不会有任何反应）。

## 概念补课（2026-10-05）：协议 / 工厂 / 适配器 / OpenAI 兼容协议
- T6 完成后，用户自述"不理解什么是协议、工厂函数、适配器"，随后又提出"不理解 OpenAI 兼容协议"。
- 一句话：三者解决同一件事——把"变化"收进一个地方。协议定形状 → 适配器把外部实现改造成这个形状 → 工厂决定用哪个。
  "OpenAI 兼容协议"是这套思想在现实世界的现成例子。
- **已扩成独立课程：`lessons/0009-protocol-factory-adapter.html`**（含图 1/图 2、4 道练习、6 道自测）。
- 为此在 `assets/style.css` 里新增了一组图组件样式（`.diagram` / `.dbox` / `.darrow` / `.dcap`），后续课程可直接复用。
- 用户易混点（0009 第二节专门澄清）：`typing.Protocol`（代码内部形状约定）≠ "OpenAI 兼容协议"（网络接口约定）。



## T5 已完成（2026-10-05）
- `kbqa/rerank.py` 实现完成，四条验收全部通过：相关项排第 1 / `original_rank` 映射正确 /
  `rerank_enabled=False` → `get_reranker()` 返回 None / endpoint 改错 → 404 后降级且全部 `degraded=True`。
- 实测：相关项 relevance_score = 0.9039，其余 0.3718 / 0.2895 / 0.2173（区分度很好）；单次耗时 1.3~1.6s。
- ⚠️ **spec §7.7 / §4.2 的请求体写法有误**：实测必须**嵌套**
  `{"model", "input": {"query", "documents"}, "parameters": {"top_n"}}`；
  扁平结构返回 400 `Field required: input.query & input.documents`。endpoint 本身按 spec 是对的。
  （官方另给 qwen3-rerank 一个兼容端点 `compatible-api/v1/reranks` 支持扁平写法，两者返回分数一致。）
- ⚠️⚠️ **重大教训：终端管道会真正损坏中文编码，不只是显示问题**。
  之前用 PowerShell here-string 管道喂 `python -`，含中文的脚本在传输中被损坏，模型收到乱码，
  于是 qwen3-rerank 返回"分数挤在 0.56~0.67 + 排序错乱 + 两条无关项分数完全相同"的**假象**；
  我据此误判为"模型未开通/模型不可用"，并让用户去控制台确认（结果是已开通）。
  改用真 `.py` 文件（UTF-8）运行后，结果完全正常。
  **规则：凡含中文（非 ASCII）的验证脚本，一律写成 .py 文件再运行，不要用管道喂 stdin。**
- 连带修正：T3 的语义 sanity check 之前的数值（0.9301 / 0.8952）是被污染的；
  用真文件复验后为 **0.7246 / 0.2138**，区分度比之前好得多。T3 的结构性验收（分批/顺序/1024 维）不受影响。
- 排查方法论已写进课程 0007（"结果不可思议时先怀疑工具"）。

## 待办：T1 遗留的一处跨模块修改（需用户确认后做）
- `loaders.list_documents()` 目前 `indexed` 恒为 `False`、`chunk_count` 恒为 `0`（T1 时刻意留的）。
  现在 T4 已定义 `data/index/docs.json` 格式（`{doc_id: {filename, chunks, indexed_at}}`），
  按 spec §7.3 应由 `list_documents` 读取它并合并出 `indexed` / `chunk_count`。
  因 tasks.md 纪律要求"改已完成文件前先说明并等确认"，此处**尚未改**。

## T15 已完成（2026-10-17）—— 工具基础层（Agent 化第一批）
- 新增 `kbqa/tools/base.py`、`kbqa/tools/__init__.py`：`ToolResult` / `Tool` / `ToolRegistry` / `@tool`。
- 边界：不实现 agent loop、不实现具体工具、不碰 `llm.py`；handler 异常本层不捕获（留给 T18）。
- 实测：`schemas()` 结构正确（type/function/name/description/parameters）；`echo` 调用返回 `hi`；重名抛 `ValueError`；handler 异常原样上抛；无新增依赖。
- 设计要点：参数统一为一个 `dict`（registry 才能统一调度）；`parameters` 手写 JSON Schema（模型看的就是这份）；重名 fail fast。
- 教学：新增课程 `lessons/0018-how-to-write-t15.html`；术语表新增 `Callable` / JSON Schema / 注册表 / tool & tool_call；资源清单补 Callable、JSON Schema、Function calling。
- 下一步：T16（LLM 工具调用，§19.6）。

## T16 已完成（2026-10-18）—— LLM 工具调用
- `kbqa/models.py` 新增 `ToolCall` / `ChatResult`；`kbqa/llm.py` 的 `LLMProvider` 新增 `chat_with_tools`，`DashScopeChat` 实现。
- **`chat()` 一行未改**：`git diff` 只有新增行，固定链路无回归风险。
- 实测：
  - 传 echo schema +「请调用 echo 说 hi」→ `tool_calls=[("echo", '{"text": "hi"}')]`，`finish_reason=tool_calls`（1336ms）
  - 回填 `role="tool"` 后再调 → `tool_calls=0`，`content="hi"`，`finish_reason=stop`（459ms）
  - `tools=[]` 与 `chat()` 同题各跑一次 → 均 77 字、均非空
- 设计要点：`tools=[]` 时**不传该字段**（空数组部分实现会拒绝，且不传才与 chat() 等价）；`content` 可为 None（只请求工具）；既无 content 又无 tool_calls 才报 `empty_content`；工具参数日志截断至 50 字符。
- 教学：新增课程 `lessons/0019-how-to-write-t16.html`；术语表新增 `finish_reason`；资源清单改用中文 Function Calling 文档（Microsoft Learn / 阿里云百炼）。
- 下一步：T17（本地工具 datetime / kb，§19.7）。

## T17 已完成（2026-10-18）—— 本地工具 datetime + kb
- 新增 `kbqa/tools/datetime_tool.py`（`get_datetime` 模块级 Tool）与 `kbqa/tools/kb_tool.py`（`build_kb_tool(pipeline, max_chars)` 工厂）。
- `kbqa/config.py` / `.env.example` 新增 `AGENT_TOOL_RESULT_MAX_CHARS=2000`（§19.4 配置增量，T17 截断需要）。
- 实测：
  - `get_datetime` 默认 → 2026-10-18 / 星期日 / 11:05:02 / 今天（+0 天）；tomorrow → 2026-10-19 / 星期一 / 明天（+1 天）
  - 临时索引 1 篇文档（6 chunk）→ `search_knowledge_base` top_n=2 → `[1] 文件#0000（0.9765）`、`[2] #0001（0.3678）`，结果 674 字 ≤ 2000
  - 空库 → `未检索到相关资料。`（9 字），无异常
  - 两工具日志均含参数、成功/失败、命中数/结果长度、耗时
- 设计要点：
  - `get_datetime` 参数非法（日期/时区）返回**解释文本**而非异常，让模型自己纠正；真正运行时异常仍交给 T18 loop。
  - 时间用 `zoneinfo.ZoneInfo`（IANA），默认本机时区；未引入新依赖（Windows 若无 tzdata，则命名时区不可用，本机时区可用）。
  - `build_kb_tool` 用工厂做依赖注入；内部只调 `pipeline.retrieve`，不重写检索。
  - 返回编号顺序 = `used` 顺序（与 `format_context` 一致）；单条片段截 300 字，总结果截 `AGENT_TOOL_RESULT_MAX_CHARS`。
  - 空库/无命中返回文本，不抛异常。
- 教学：新增课程 `lessons/0020-how-to-write-t17.html`；术语表新增 `IANA 时区 / ZoneInfo`；资源清单补 Python zoneinfo。
- 下一步：T18（agent loop，§19.8）。

## T18 已完成（2026-10-18）—— agent loop
- 新增 `kbqa/agent.py`（`AgentRunner` 手写 loop）；`kbqa/models.py` 新增 `AgentStep` / `AgentRun`；`kbqa/config.py` / `.env.example` 新增 `AGENT_MAX_STEPS=5`。
- 实测：
  - 「今天是几号、星期几？」→ 2 轮 / 1 步 / 调 `get_datetime` / `final_answer`；答案「2026年10月18日，星期日」，总耗时 1927ms
  - 模型每轮都要求再调一次 → 停在 `max_steps=5`，执行 4 步后停止，不抛异常，返回兜底文本
  - 工具必抛异常 → 该步 `ok=False`，`result_text=工具执行失败：故意失败`，循环继续并给答案
  - 3000 字工具结果 → 截到 2000 字，严格 ≤ `AGENT_TOOL_RESULT_MAX_CHARS`
  - 日志四类打点齐全（开始 / 每轮 / 每次工具 / 结束）
- 设计要点：
  - 外层 `while` 管轮数，内层 `for` 管一轮多个 tool_calls，工具选择走 `registry.get`（不用 if-else）。
  - 最后一轮不再执行工具（没有下一轮消费结果），直接 `stop_reason="max_steps"`。
  - 参数 JSON 解析失败：不执行 handler，记 `{"_raw": ...}` + `ok=False`，仍回填 tool 消息。
  - 工具异常：转成错误文本，`ok=False`，循环继续。
  - 同一工具+同参数连续 ≥2 次：追加提示文本 + `WARNING`；真正兜底仍是 max_steps。
  - 截断严格：`text[:limit-3] + "..."`；顺带修复了 T17 `kb_tool._truncate` 的同类边界（可能超 3 字符）。
  - skill 尚未实现：`run(skill=...)` 非 None 时直接 `ValueError`，T26 再替换。
- 教学：新增课程 `lessons/0021-how-to-write-t18.html`；术语表新增 `agent loop` / `stop_reason`。
- 下一步：T19（agent API，§19.9）。

## T19 已完成（2026-10-18）—— agent API
- `api/schemas.py` 新增 `AgentChatRequest` / `AgentStepOut` / `AgentRunOut` / `SkillOut` 与 `to_agent_run_out`。
- `api/routes.py` 新增 `GET /api/agent/skills`（T26 前返回 `[]`）与 `POST /api/agent/chat`；skill 不存在映射为 400 `skill_not_found`。
- `api/main.py` 装配 `ToolRegistry`（`get_datetime` + `search_knowledge_base`）与 `AgentRunner`，挂到 `app.state.agent`；`llm` 实例同时注入 pipeline 与 agent。
- 实测（TestClient）：
  - `POST /api/agent/chat {"question":"今天几号？"}` → 200，字段齐全，`final_answer`，调用 `get_datetime`
  - `skill="not-exist"` → 400 `skill_not_found`
  - 工具全部失败 → 200，`steps[0].ok=false`，最终仍有答案
  - `max_steps=2` → 200，`stop_reason=max_steps`，`rounds=2`
  - 回归：`/api/health` 200；`/api/qa` 200（真实检索 + 生成）
- 设计要点：工具失败 / max_steps 都**不是 HTTP 错误**；对外 schema 与内部 DTO 分两层；路由层只解析请求、调 `AgentRunner.run`、转换响应，不写编排。
- 教学：新增课程 `lessons/0022-how-to-write-t19.html`；术语表新增 `TestClient`；资源清单补 FastAPI 测试文档。
- 下一步：T20（前端工具调用轨迹，§19.10）。

## T20 已完成（2026-10-18）—— 前端工具调用轨迹
- `web/src/api.ts` 新增 `AgentStep` / `AgentRun` / `SkillInfo`、`agentSkills()`、`agentChat()`。
- 新增 `AgentPanel.vue`、`ToolTrace.vue`；`App.vue` 持有 `agentResult` / `skills`，统一发请求。
- 实测（浏览器 http://localhost:8010）：
  - 「5. Agent 对话」出现，Skill 下拉默认「自动」，原有上传/文档列表/提问面板未受影响
  - 提问「今天几号？」→ 2 轮 · 1 次工具 · 2035 ms；答案「2026年10月18日，星期日」
  - 工具轨迹 `#1 get_datetime 成功 0 ms`，绿色徽章，展开可见参数与结果
  - `npm run type-check` / `npm run build` 均通过
- 设计要点：网络调用只在 `App.vue`；`AgentPanel` / `ToolTrace` 只发事件/渲染 props；失败步骤默认展开并标红；skill 下拉空列表时只剩「自动」。
- 教学：新增课程 `lessons/0023-how-to-write-t20.html`；资源清单补 Vue 组件基础。
- 下一步：T21（对照实验：固定链路 vs Agent）。

## T21 已完成（2026-10-18）—— 固定链路 vs Agent 对照
- 新增 `eval/agent_compare.py`，一条命令对同一批问题双跑，输出 `eval/agent_compare.md`（逐题对照 + 本次案例 + 自动统计）。
- 实测（3 题）：
  - 实时题「今天几号，星期几？」：固定链路检索后拒答；Agent 调 `get_datetime`，正确回答 2026-10-18 星期日
  - 事实题「豆豆的疫苗本编号」：固定链路正确回答 `VX-2021-0314-77 [1]`；Agent **未调工具**，以隐私为由拒答（真实反例）
  - 事实题「2025 年旅行」：两版都正确；Agent 调 `search_knowledge_base`，但答案未带 [n] 引用
  - Agent 调用工具 2/3；平均耗时 固定 2744ms / Agent 4219ms
- 结论：Agent 的价值是"选择"（实时题），风险也是"选择"（事实题不检索）；耗时不是公平指标，要结合轮数与工具次数看。
- 教学：新增课程 `lessons/0024-how-to-write-t21.html`。
- 下一步：T22（百度搜索工具，批次 B，mock-first）。

## T22 已完成（2026-10-18）—— 百度搜索工具（mock-first）
- 新增 `kbqa/tools/web_search.py`（工厂 `build_web_search_tool(settings)`）；`config.py` / `.env.example` 新增 `WEB_SEARCH_API_KEY` / `WEB_SEARCH_ENDPOINT`。
- 契约：query 必填、count 1–5、每条标题+URL+摘要（≤200 字）、最多 5 条、超时 10s、失败返回文本不抛异常。
- 实测：mock 3 条（514 字，带 `[mock]`）；错误 endpoint → `web_search 调用失败：…`（2750ms）；日志无 Key。
- ⚠️ **真实联调：未联调**（无 Key / endpoint）。接口尚未定稿，采用可配置 GET + Bearer 的最小约定。
- 教学：新增课程 `lessons/0025-how-to-write-t22.html`。

## T23 已完成（2026-10-18）—— 天气工具（mock-first）
- 新增 `kbqa/tools/weather.py`（工厂 `build_weather_tool(settings)`）；`config.py` / `.env.example` 新增 `WEATHER_API_KEY` / `WEATHER_ENDPOINT`。
- 契约：city 必填（城市名）、days 1–7、返回城市/日期/天气/温度、超时 10s、错误返回文本。
- 实测：北京 2 天 → 城市/日期/天气/温度齐全（带 mock 标记）；不存在的城市 → `未找到城市：…`；错误 endpoint → `get_weather 调用失败：…`（2566ms）。
- ⚠️ **真实联调：未联调**（无 Key / endpoint）。
- 教学：新增课程 `lessons/0026-how-to-write-t23.html`。
- 下一步：T24（MCP server：markdown 写入）。

## T24 已完成（2026-10-18）—— MCP server：markdown 写入
- 新增 `mcp_servers/md_writer/server.py`（官方 SDK `MCPServer`，stdio 传输）、`requirements-mcp.txt`（`mcp>=2,<3`）、`data/exports/.gitkeep`；`.gitignore` 忽略导出内容。
- 安全边界：目录由服务端固定；拒绝绝对路径 / 盘符 / `..` / 目录成分；写入前 `resolve().relative_to(EXPORT_DIR)` 双保险；content 上限 200,000 字符。
- 实测：`tools/list` → `["write_markdown"]`；写入 `hello.md` 内容一致；`../../evil.md` 被拒绝且目录外无文件。
- ⚠️ 环境安装：`mcp 2.3.0`（`FastMCP` 在 2.x 改名为 `MCPServer`，API 基本一致）。
- 教学：新增课程 `lessons/0027-how-to-write-t24.html`。

## T25 已完成（2026-10-18）—— MCP client：工具并入 registry
- 新增 `kbqa/mcp_client.py`：`MCP_ENABLED=false` 时直接返回且**不 import mcp**；启用时 `tools/list` → 包装成 `Tool`（名称前缀 `server.tool`）→ 注册进同一个 registry。
- `config.py` / `.env.example` 新增 `MCP_ENABLED` / `MCP_SERVERS` / `EXPORT_DIR`；`main.py` 装配时调用 `register_mcp_tools`。
- 失败隔离：server 命令写错只记 WARNING，其余工具仍可用；每次 `tools/call` 开一个 stdio 会话（实测 3–5s，demo 取舍）。
- 实测：
  - `MCP_ENABLED=false` → 只有本地工具，`mcp` 未被 import
  - 启用 → registry 出现 `md_writer.write_markdown`，写文件成功
  - 错误 server → 只剩本地工具，应用不崩
  - Agent 脚本化调用 MCP 工具 → 1 步成功，`trace.md` 落盘
- 教学：新增课程 `lessons/0028-how-to-write-t25.html`。
- 下一步：T26（Skill 机制）。

## T26 已完成（2026-10-18）—— Skill 机制
- 新增 `kbqa/skills.py`（`Skill` / `SkillLoader` / `LOAD_SKILL_SCHEMA`）、`skills/daily-brief/SKILL.md`、`skills/kb-research/SKILL.md`。
- `agent.py` 支持两种触发：显式 `skill=name` 启动即收窄工具；自动模式注入 skill 清单 + `load_skill`，加载后正文进 system prompt、工具集收窄。
- `config.py` / `.env.example` 新增 `SKILLS_DIR` / `SKILL_AUTO_SELECT`；`main.py` 装配 `SkillLoader`；`GET /api/agent/skills` 返回真实清单。
- 实测：
  - 加载 2 个 skill：`daily-brief` / `kb-research`
  - 显式 `daily-brief`：首轮工具 = `get_datetime / search_knowledge_base / get_weather`，无 `load_skill`
  - 自动：首轮含 `load_skill`；第二轮工具收窄为 3 个；`run.skill=daily-brief`
  - `SKILL_AUTO_SELECT=false`：无 `load_skill`、system 无 skill 清单
  - 未知 skill：runner `ValueError`；API 400 `skill_not_found`
  - `GET /api/agent/skills` → 200，返回两个 name + description
- 教学：新增课程 `lessons/0029-how-to-write-t26.html`；术语表新增 `skill / 渐进披露`。
- 下一步：T27（流式输出）。

## T27 已完成（2026-10-18）—— 流式输出（SSE）
- `AgentRunner.run` 新增可选 `on_event` 回调，发出 step_start / tool_call / tool_result；`api/routes.py` 新增 `POST /api/agent/chat/stream`（线程 + 队列 + StreamingResponse）。
- 前端 `api.ts` 新增 `agentChatStream`（ReadableStream 解析 SSE）；`AgentPanel` 加「流式输出」开关；`App.vue` 按事件增量更新答案与轨迹。
- 事件序列实测：step_start → tool_call → tool_result → step_start → token ×3 → done。
- ⚠️ **诚实边界**：`token` 是把最终答案按 8 字分片发出，不是模型原生 token 流；真正的原生流需要改 LLM 层。
- 浏览器实测：流式默认勾选；答案与 get_datetime 轨迹正常。
- 教学：新增课程 `lessons/0030-how-to-write-t27.html`。
- 下一步：T28（LangGraph 版 loop）。

## T28 已完成（2026-10-18）—— LangGraph 版 agent loop
- 新增 `kbqa/agent_graph.py`（`GraphAgentRunner` 继承 `AgentRunner`，复用 skill / 工具执行 / 截断 / 日志）；`agent.py` 新增 `AgentEngine` 协议与 `create_agent_runner`；`config.py` / `.env.example` 新增 `AGENT_ENGINE`；`requirements-langgraph.txt`。
- 图结构：llm 节点 → 条件边（pending_calls 是否为空）→ tools 节点 → 回 llm；`recursion_limit = max_steps*2+4`。
- 实测：
  - 真实问日期：2 轮 / 1 步 / `get_datetime` / final_answer
  - max_steps=3：停在 3 轮 / 2 步，不抛异常
  - 工具异常：ok=False，继续到最终答案
  - 3000 字 → 2000 字
  - 两版同脚本：stop_reason / 步数 / 轮数 / 工具名一致
  - skill 收窄在 LangGraph 版同样生效
  - handwritten 模式 `langgraph` 未被 import（实测 False）
- 教学：新增课程 `lessons/0031-how-to-write-t28.html`。
- 下一步：T29（双引擎对照）。

## T29 已完成（2026-10-18）—— 双引擎对照实验
- 新增 `eval/agent_engine_compare.py`，双跑手写 vs LangGraph，输出 `eval/agent_engine_compare.md`。
- 实测（3 题）：
  - 疫苗题：手写未调工具（回答缺背景）；LangGraph 调 `search_knowledge_base` 并答出 `VX-2021-0314-77`（模型采样差异）
  - 日期题：两版都调 `get_datetime`，答案一致
  - 旅行题：两版都调检索，答案措辞不同；耗时 6466ms vs 17297ms
  - 确定性边界 max_steps=3：两版完全一致（rounds=3 / steps=2 / tool_calls=2）
  - 代码量：agent.py 538 行 vs agent_graph.py 264 行；LangGraph 为可选依赖
- 结论：两版控制流被刻意设计为等价；对话差异主要来自模型采样；框架把循环声明化，也引入依赖与排查成本。学习阶段选手写，复杂流程选图。
- 教学：新增课程 `lessons/0032-how-to-write-t29.html`；术语表新增 `StateGraph / 节点 / 条件边`；资源清单补 LangGraph。
- 🎉 T15–T29 全部完成（T22/T23 真实联调仍为「未联调」，已如实记录）。

## 概念补课（2026-10-18）：工厂参数注入怎么举一反三
- 触发：用户追问 `build_kb_tool(pipeline, max_chars)` 的"工厂注入参数"是什么意思、怎么迁移。
- 已扩成独立课程 **`lessons/0033-factory-injection-pattern.html`**，不重复 0013 的基础 DI，重点在"迁移方法"：
  - 通用模板：`build_X(dep_a, dep_b, config) -> X`，参数是注入点、闭包固定依赖、返回统一接口成品。
  - 四步迁移法：① 识别依赖 → ② 选注入点（函数工厂 / 构造函数 / app.state / 环境变量 / 适配器工厂）→ ③ 在组合根装配 → ④ 用假实现验证。
  - 判断表：外部 IO / 测试替换 / 共享实例 / 有第二实现 → 该注入；纯函数、标准库小工具、无变化点 → 不该注入。
  - 项目里的五种同构形态：闭包工厂、类构造注入、适配器工厂、应用级单例、前端 props/emits。
  - 三种反面写法：模块级全局、handler 内部 new、工厂参数膨胀（应收敛成 Settings / 上下文）。
  - 练习 A–D：翻译工具、订单通知、测试 max_steps、判断该不该抽。
- 术语表新增：**组合根（composition root）**、**闭包工厂**。
- 教学要点：讲模式时用"四步 + 判断表 + 同构形态"比只给定义更可迁移；同时强调"别过度注入"。

## 学习材料增强（2026-10-18）：每个任务补齐"代码全流程拆解"
- 背景：一次性完成 T15–T29 后，单个文件叠加了多轮修改，缺少"一次只加一层"的中间参照。
- 已在 **0018–0032 全部 15 篇任务课**中新增 `附：代码全流程拆解`，每篇统一包含：
  1. **阶段表**：输入 → 关键步骤 → 输出；
  2. **代码地图**：哪个文件/函数负责哪一段；
  3. **核心代码逐段讲解**：完整代码或关键核心代码，每段说明"在做什么 / 为什么这么写 / 删掉会怎样"；
  4. **失败路径**：异常、超时、空结果、权限边界；
  5. **前后衔接**：这一任务与上一/下一任务的分界线。
- 覆盖范围：
  - 0018 T15 工具层 → 0019 T16 工具调用 → 0020 T17 两个本地工具 → 0021 T18 手写 loop → 0022 T19 API
  - 0023 T20 前端轨迹 → 0024 T21 固定链路对照 → 0025 T22 web_search → 0026 T23 weather
  - 0027 T24 MCP server → 0028 T25 MCP client → 0029 T26 Skill
  - 0030 T27 SSE → 0031 T28 LangGraph → 0032 T29 双引擎对照
- 校验：15 篇均恰好 1 个新章节，`<pre><code>` 开闭标签数量一致。
- 建议阅读顺序：先读 0021（loop 主线），再按 T15→T19 补前置/后置；T20 之后按任务号推进。大文件只读"骨架"，helper 第二遍再看。
