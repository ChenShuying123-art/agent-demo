# 知识库问答 Agent —— 任务拆解

| 项目 | 内容 |
|------|------|
| 文档版本 | v1.0 |
| 配套文档 | [spec.md](./spec.md)（设计契约，本文档不重复其内容） |
| 任务粒度 | 模块级，共 28 个任务：MVP 15 个（T0–T14）+ Agent 化 13 个（T15–T27） |
| 状态 | 待开工 |

---

## 0. 如何使用本文档

### 0.1 核心原则

**一个任务 = 一次独立的 AI 对话。** 不要把多个任务塞进一次对话，也不要让 AI 一次生成所有代码。

**喂给 AI 的内容 = 本任务卡片 + 该任务引用的 spec 小节。** 不要把整份 spec.md 丢给 AI——1300 多行会让它在中后段"忘掉"前面的类型定义，输出不一致。每个任务卡片里的「契约」字段已经告诉你该给哪几节。

### 0.2 标准 Prompt 模板

```text
请实现任务 T3。

【项目背景】RAG 知识库问答 demo，完整设计见 docs/spec.md。本任务只涉及 §7.5，
请只阅读该节，不要通读全文。

【任务卡片】
<粘贴 tasks.md 中 T3 的完整内容>

【硬性约束】
- 严格遵守 §7.5 的接口签名，不得改名、不得改返回结构
- 只实现本任务产出文件，不要顺带实现或"预留"其他模块
- 不要修改已完成的文件；如确有必要，先说明理由并等我确认
- 不引入 requirements.txt 之外的依赖
- 遵守 spec §18.1 注释规范：关键流程逐步注释，解释「为什么」而非「是什么」
- 遵守 spec §18.2 日志规范：主流程必打点位置不得省略；用 logging，禁止 print

【完成后】
按任务卡片「验收」小节逐条自测，报告每条的实测结果（通过/失败 + 证据）。
```

### 0.3 四条纪律

1. **验收未通过，不进入下一个任务。** 上层模块建立在错误的底层之上，排查成本是复利增长的。
2. **每完成一个任务，必须停下来等作者 review。** 按 spec §18.3 的四点汇报（改了哪些文件 / 重点看哪里 / 怎么自己验 / 明确的等待），**得到确认后才开始下一个任务**。
3. **一个任务一次 commit。** 出问题时 `git diff` 就能定位，比翻 20 个文件快得多。
4. **🤖 / 👤 严格区分。** 标 👤 的任务 AI 不得代劳。

> 纪律 2 覆盖 T1–T14 **全部任务**（含标 🤖 的）。T0 骨架简单，但同样要停——它是后面所有任务的依赖。

### 0.4 验收形式约定

| 标记 | 含义 |
|------|------|
| `CMD` | 可执行命令，看输出是否匹配预期 |
| `NB` | Notebook 中肉眼观察，需要你确认"看起来对不对" |
| `LOG` | 检查日志输出：打点位置是否齐全、级别是否正确、是否脱敏（spec §18.2） |
| `CHK` | 人工检查，无自动化手段 |

> 涉及主流程的任务（T1–T11、T13），验收时必须额外执行 `LOG` 检查：对照 spec §18.2 的「主流程必须打点的位置」表，逐条确认该任务涉及的链路日志已打全。

---

## 1. 前置条件（P0）

开工前必须全部满足，否则 T3 之后会卡住。

| # | 条件 | 说明 |
|---|------|------|
| P0-1 | Python 3.11+ 环境 | `python --version` |
| P0-2 | 阿里云百炼账号 + API Key（**北京地域**） | 同一 Key 供对话/Embedding/Rerank 使用 |
| P0-3 | 已开通 3 个模型：`qwen-plus`、`text-embedding-v4`、`qwen3-rerank` | 在百炼控制台开通，未开通会报 `Model.AccessDenied` |
| P0-4 | Node.js 18+ | T11 需要，`node --version` |
| P0-5 | 准备 2–3 篇**自己的** txt/md 文档 | T1 测试用；T12 出题也用这批，选你熟悉的内容 |
| P0-6 | git 仓库已初始化 | 每个任务一次 commit |

---

## 2. 依赖关系图

```
T0 骨架
├─ T1 loaders ──┐
├─ T2 chunking ─┼─ T3 embeddings ── T4 vectorstore ──┬─ T5 rerank ──┐
│               │                                     │              │
└─ T6 llm ──────┴─────────────────────────────────────┴─ T8 检索编排 ┴─ T9 问答编排 ── T10 API ── T11 Vue
                                                                              │
                                                                              └─ T12 出题(👤) ── T13 评测 ── T14 复盘
```

**关键路径**：T0 → T3 → T4 → T8 → T9 → T10 → T11
**可并行**：T5 与 T6 可以并行（但建议仍分两次对话）

Agent 化批次（T15–T27，契约 §19）：

```
批次 A（本地，无 key、无外网）
T15 工具基础层 ──┬── T17 本地工具（datetime / kb）──┐
                 │                                  ├── T18 agent loop ──┬── T19 API ──┬── T20 前端轨迹 ── T27 流式（可选）
T16 LLM 工具调用 ─┘                                  │                    │             └── T26 Skill 机制（另需 T19）
                                                     ├── T21 对照实验（另需 T9）
                                                     │
批次 B（外网，另需 key）                              ├── T22 百度搜索
                                                     └── T23 天气
批次 C（MCP）
T24 MCP server ── T25 MCP client（另需 T18）
```

**Agent 化关键路径**：T15 → T17 → T18 → T19 → T20

---

## 3. 任务清单

### T0 —— 项目骨架与配置 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | P0 |
| **产出** | `kbqa/__init__.py`、`kbqa/config.py`、`kbqa/logging_conf.py`、`kbqa/models.py`、`.env.example`、`.gitignore`、`requirements.txt`、`data/uploads/.gitkeep`、`data/index/.gitkeep` |
| **契约** | spec §7.1、§7.2、§7.12、§14 |
| **验收** | `CMD` `python -c "import kbqa; print('ok')"` → `ok`<br>`CMD` `python -c "from kbqa.config import settings; print(settings.chat_model, settings.embedding_dim, settings.rerank_model, settings.log_level)"` → `qwen-plus 1024 qwen3-rerank INFO`<br>`LOG` `logging.getLogger("kbqa").info("test")` 输出形如 `时间 \| INFO \| 模块名 \| test`<br>`LOG` `LOG_LEVEL=DEBUG` 时 DEBUG 可见；改回 `INFO` 时 DEBUG 不可见<br>`CHK` `.gitignore` 含 `.env`，且 `git status` 不出现 `.env`<br>`CHK` `requirements.txt` 含：fastapi、uvicorn、pydantic、pydantic-settings、python-multipart、openai、httpx、numpy |
| **禁止** | 本任务**不写任何业务逻辑**，`models.py` 只放 @dataclass 定义 |

> 说明：`config.py` 中的字段名会从 `.env` 读取，注意 `pydantic-settings` 默认大小写不敏感。`.env.example` 里的 key 必须是 UPPER_SNAKE，如 `CHAT_MODEL`。

---

### T1 —— 文档加载 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T0 |
| **产出** | `kbqa/loaders.py` |
| **契约** | spec §7.3 |
| **验收** | `CMD` 上传一篇自己准备的 md → 返回 `Document`，`doc_id` 为 16 位 hex<br>`CMD` **重复上传同一文件** → 返回**相同** `doc_id`，且 `data/uploads/` 下只有 1 个文件<br>`CMD` `list_documents()` 返回该文档且 `indexed=False`、`size` 与真实文件一致<br>`CHK` `.txt` 和 `.md` 都能正确读取（UTF-8） |
| **禁止** | 不要在这里做切分或向量化 |

---

### T2 —— 文本切分 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T0 |
| **产出** | `kbqa/chunking.py`、`notebooks/01_indexing.ipynb`（前半部分） |
| **契约** | spec §7.4 |
| **验收** | `CMD` 对 T1 上传的真实文档调用 `split_text`，断言：<br>　① 每个 chunk 长度 ≤ `chunk_size` + 边界冗余<br>　② 相邻 chunk 存在 `chunk_overlap` 字符重叠<br>　③ **`text[start:end] == chunk_text` 逐条成立**<br>`NB` Notebook 01 打印 chunk 总数 + 前 3 个 chunk 的完整文本 |
| **重点** | 断言 ③ 是关键，它保证 `start/end` 没有错位。错位了引用定位就会指到别处 |
| **学习点** | 跑完后在 Notebook 里对比 `chunk_size=200` vs `800` 的 chunk 数量差异，记一行结论 |

---

### T3 —— 向量化 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T2（需要 chunk 文本做测试）<br>**前置：P0-2、P0-3 必须已完成** |
| **产出** | `kbqa/embeddings.py` |
| **契约** | spec §7.5、§4.2（坑 2） |
| **验收** | `CMD` 传入 **15 条**带编号的文本（如 `"这是第 1 条"`…）：<br>　① 内部自动分成 2 批发出<br>　② 返回 15 个向量，**顺序与输入严格一致**（检查第 i 个向量的文本对应关系）<br>　③ `len(vec) == settings.embedding_dim == 1024`<br>`NB` 语义相近的两句（如"如何切分文档"vs"文本分块的方法"）余弦相似度 > 不相关的两句<br>`NB` Notebook 01 后半：打印向量维度、L2 范数、前 5 维数值 |
| **重点** | **分批顺序错乱是本任务最容易出的 bug**，而且不报错。必须用"带编号的文本"专门验证顺序 |
| **禁止** | 不要把 `embedding_batch_size` 调大于 10（spec §4.2 坑 2） |

---

### T4 —— 向量存储 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T3 |
| **产出** | `kbqa/vectorstore.py` |
| **契约** | spec §7.6 |
| **验收** | `CMD` `add()` 后 `stats()` 返回 `{"chunks": N, "docs": M, "dim": 1024}`，N 与 JSONL 行数一致<br>`CMD` `save()` → 新建实例 `load()` → 对同一查询返回**完全相同**的检索结果<br>`CMD` `search()` 返回结果按 score **降序**<br>`CMD` `remove_document()` 后：`stats()["chunks"]` 正确减少，且 **`vectors.npy` 行数 == `chunks.jsonl` 行数**<br>`CMD` 传 `doc_ids` 过滤时，返回结果只含指定文档的 chunk |
| **重点** | 必须显式断言 **npy 行数 == jsonl 行数**（spec §7.6 指出的最大隐患）。删除策略建议**全量重写**，逻辑最简单不易错 |
| **里程碑** | ✅ **M1 完成**（Notebook 01 全绿） |

---

### T5 —— Rerank 重排 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T4 |
| **产出** | `kbqa/rerank.py` |
| **契约** | spec §7.7、§4.2（坑 1） |
| **验收** | `CMD` 构造 5 条候选（其中 1 条明显相关）→ `rerank()` 后**相关那条排到第 1**<br>`CMD` `RerankResult.original_rank` 正确反映重排前排名<br>`CMD` `rerank_enabled=False` → `get_reranker()` 返回 `None`<br>`CMD` **故意把 endpoint 改错** → 不抛异常、正常降级，且返回结果标记 `degraded=True` |
| **重点** | endpoint 是 `api/v1/services/rerank/text-rerank/text-rerank`，**不是** `compatible-mode/v1`（spec §4.2 坑 1）。响应中 `index` 是输入数组下标，必须用它映射回 chunk |
| **注意** | `relevance_score` 与 cosine 分数不可比较，教程里不要混着排序 |

---

### T6 —— LLM 调用 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T0 |
| **产出** | `kbqa/llm.py` |
| **契约** | spec §7.8、§4.2（坑 3） |
| **验收** | `CMD` 传入 messages 返回非空字符串<br>`CMD` 使用错误 API Key → 抛出异常，异常信息中包含百炼返回的 `code`（便于排查）<br>`CHK` 请求体确实带上了 `extra_body={"enable_thinking": False}` |
| **重点** | 若改用 qwen3.x 系列必须关思考模式，否则 `content` 可能为空、答案跑到 `reasoning_content`（spec §4.2 坑 3） |

---

### T7 —— 提示词 🤖 ⚠️

| 字段 | 内容 |
|------|------|
| **依赖** | T6 |
| **产出** | `kbqa/prompts.py` |
| **契约** | spec §7.9、**§12.3（逐字照抄）** |
| **验收** | `CMD` `PROMPT_STYLES` 长度 == 3 且内容与 spec §12.3 一致<br>`CMD` **对同一问题生成三个 system prompt，前 N 字符（即 `SHARED_CONSTRAINTS` 部分）完全相同**，差异只在后半段<br>`CMD` `format_context()` 输出带 `[1]`、`[2]` 编号，编号与传入顺序一致 |
| **⚠️ 强约束** | **这是全项目唯一一个"照抄"任务。** 四段提示词正文必须逐字来自 spec §12.3，**禁止 AI 自由发挥、改写、优化措辞**。理由：提示词内容是要被评测的对象，必须与 spec 冻结的版本一致，否则评测结论无法与设计对应 |
| **实现要求** | 必须用 `SHARED_CONSTRAINTS + STYLE_BODIES[style]` 拼接，**不得把硬约束复制三遍** |

---

### T8 —— 检索编排（召回 + 重排） 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T4、T5 |
| **产出** | `kbqa/pipeline.py`（先实现 `recall` / `rerank` / `retrieve`） |
| **契约** | spec §7.10 |
| **验收** | `NB` Notebook 02 完整跑通，打印：<br>　① 召回 20 条（含 chunk_id、cosine 分数、rank）<br>　② 重排后 4 条（含 rerank 分数、`original_rank` → `new_rank`）<br>　③ **能肉眼看出至少一条内容的排名发生了变化**<br>`CMD` `use_rerank=False` 时，`used == candidates[:rerank_top_n]`<br>`CMD` `doc_ids` 过滤在召回阶段生效 |
| **里程碑** | ✅ **M2 完成** |

---

### T9 —— 问答编排 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T6、T7、T8 |
| **产出** | `kbqa/pipeline.py`（补 `answer` / `answer_all_styles`）、`notebooks/03_qa_prompt_compare.ipynb` |
| **契约** | spec §7.10、§7.2 `QAResult` |
| **验收** | `NB` Notebook 03 对同一问题**三版并排输出**，肉眼可辨风格差异<br>`CMD` 答案中出现 `[n]` 引用，且所有 n 都 ≤ 参考资料条数<br>`CMD` **问一个文档完全没提过的问题 → 三版都能拒答**（这是 §12.1 硬约束 2 的验证）<br>`CMD` `QAResult.candidates` 长度为 `retrieve_top_k`，`used` 长度为 `rerank_top_n`<br>`CMD` `latency_ms` 为合理正数 |
| **里程碑** | ✅ **M3 + M4 完成** |

> **学习时刻**：务必在 Notebook 03 里把"最终发给 LLM 的 messages 全文"打印出来看一眼（spec §10 第 8 步）。

---

### T10 —— FastAPI 接口层 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T9 |
| **产出** | `api/main.py`、`api/routes.py`、`api/schemas.py` |
| **契约** | spec §8 |
| **验收** | `CMD` `uvicorn api.main:app --reload` 启动无报错<br>`CMD` 浏览器访问 `/docs` 能看到全部 9 个路由<br>`CMD` `curl /api/health` → 返回三个模型名<br>`CMD` **端到端 curl 跑通**：上传 → 索引 → `/api/qa` 拿到答案<br>`CMD` `/api/retrieve` 返回 `{candidates, used, degraded}` 三个字段<br>`CMD` 传入不存在的 doc_id → 返回结构化错误 `{error:{code,message}}` |
| **注意** | 上游模型报错时返回 502，并**透传百炼的 code 与 message**（spec §8 约定） |

---

### T11 —— Vue 前端 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T10 |
| **产出** | `web/` 完整工程：`package.json`、`vite.config.ts`、`index.html`、`src/main.ts`、`src/App.vue`、`src/api.ts`、`src/components/*.vue`（4 个） |
| **契约** | spec §9 |
| **验收** | `CMD` `npm run dev` 后，`vite.config.ts` 的 proxy 生效（前端 5173 调后端 8000 无跨域）<br>`NB` 浏览器完成全流程：上传 → 勾选 → 向量化 → 提问 → 看答案与引用<br>`NB` **「召回 → 重排」面板正确显示排名变化**（左列 cosine 顺序，右列 rerank 顺序 + 升降箭头）<br>`NB` 切换 `use_rerank` 开关时，右列显示"未重排"提示<br>`NB` "全部对比"模式下三列并排展示三种风格<br>`CMD` `npm run build` 成功，FastAPI 挂载 `web/dist` 后单端口可访问 |
| **里程碑** | ✅ **M6 完成** |
| **禁止** | 不引入 UI 组件库，样式手写（spec §17.2） |

---

### T12 —— 评测集出题 👤 **（人工，AI 不得代劳）**

| 字段 | 内容 |
|------|------|
| **依赖** | T9（需先在 Notebook 里能跑问答） |
| **产出** | `eval/eval_set.jsonl`（12–20 条） |
| **契约** | spec §13.1 |
| **验收** | `CHK` 四类题型覆盖：`factual` ≥ 5、`synthesis` ≥ 3、`boundary` ≥ 3、`distractor` ≥ 2<br>`CHK` 每条的 `doc_ids` 真实存在<br>`CHK` **每道 factual/synthesis 题先在 Notebook 02 手工跑一次召回，确认正确 chunk 在 Top-20 内**<br>`CHK` `should_refuse=true` 的题，确实文档里查不到<br>`CHK` `expected_points` 写的是关键信息点，不是整段答案 |
| **AI 可做的部分** | 只允许 AI 写一个**格式校验脚本**（校验 JSON 合法性、字段完整性、doc_ids 存在性、题型数量分布）。**题目内容必须你自己写** |
| **理由** | 出题人已知答案，才能判断后续裁判打分是否靠谱。AI 编的题你无法验证，整份评测会失去意义 |

> 重要提醒：如果某道题的正确 chunk 不在 Top-20 内，**说明问题出在切分/Embedding，不是提示词**。这类题要么调整切分参数，要么剔除，不要留着拉低所有风格的分数。

---

### T13 —— 评测与消融实验 🤖

| 字段 | 内容 |
|------|------|
| **依赖** | T12 |
| **产出** | `kbqa/evaluate.py`、`eval/judge_prompt.md`、`eval/report.md`、`eval/report.csv`、`notebooks/04_evaluation.ipynb` |
| **契约** | spec §7.11、§13.2 ~ §13.6 |
| **验收** | `CMD` **实验一**（提示词对比）：固定全部检索参数，产出「三种风格 × 各维度平均分」表<br>`CMD` **实验二**（Rerank 消融）：固定 `strict_citation`，产出 rerank on/off 的检索层 + 生成层对比表<br>`CMD` 报告含逐题明细与裁判理由<br>`CMD` 裁判 JSON 解析失败率 < 5%，且失败记录被打印出来<br>`CHK` 结论区按 §13.2 归因链路给出判断（是切分/召回/重排/提示词哪一环的问题） |
| **里程碑** | ✅ **M5 完成** |

> 预期参考（spec §13.5）：文档小时 rerank 增益可能不明显，这**本身就是有价值的结论**，如实写进报告，不要为了"好看"而美化。

---

### T14 —— README 复盘 🤖 + 👤

| 字段 | 内容 |
|------|------|
| **依赖** | 全部 |
| **产出** | `README.md` |
| **契约** | spec §15 M7 |
| **验收** | `CHK` 含架构图（可复用 spec §5.1）<br>`CHK` 含从零到跑的完整步骤（含 P0 前置条件）<br>`CHK` 含**三张表**：提示词对比、Rerank 消融、模型/参数对比<br>`CHK` 含踩坑记录（对照 spec §11 逐条确认哪些真踩到了）<br>`📖` **能对着 README 把 RAG 全链路讲清楚，并解释 Rerank 的实测收益** |
| **归属** | 🤖 AI 写初稿 + 👤 你补充实测结论与踩坑记录 |

---

## 4. 进度追踪

| 任务 | 归属 | 状态 | 完成日期 | 备注 |
|------|------|------|----------|------|
| P0 前置条件 | 👤 | ⬜ | | API Key / 文档准备 |
| T0 骨架配置 | 🤖 | ⬜ | | |
| T1 文档加载 | 🤖 | ⬜ | | |
| T2 文本切分 | 🤖 | ⬜ | | |
| T3 向量化 | 🤖 | ⬜ | | 前置 P0-2/P0-3 |
| T4 向量存储 | 🤖 | ⬜ | | ✅ M1 |
| T5 Rerank | 🤖 | ⬜ | | |
| T6 LLM 调用 | 🤖 | ⬜ | | |
| T7 提示词 | 🤖 | ⬜ | | ⚠️ 逐字照抄 |
| T8 检索编排 | 🤖 | ⬜ | | ✅ M2 |
| T9 问答编排 | 🤖 | ⬜ | | ✅ M3+M4 |
| T10 API 层 | 🤖 | ⬜ | | |
| T11 Vue 前端 | 🤖 | ⬜ | | ✅ M6 |
| T12 出题 | 👤 | ⬜ | | 必须人工 |
| T13 评测消融 | 🤖 | ⬜ | | ✅ M5 |
| T14 README | 🤖+👤 | ⬜ | | ✅ M7 |
| T15 工具基础层 | 🤖 | ⬜ | | ✅ M8 |
| T16 LLM 工具调用 | 🤖 | ⬜ | | |
| T17 本地工具 | 🤖 | ⬜ | | datetime / kb |
| T18 agent loop | 🤖 | ⬜ | | ✅ M8 |
| T19 agent API | 🤖 | ⬜ | | ✅ M9 |
| T20 前端轨迹面板 | 🤖 | ⬜ | | ✅ M9 |
| T21 对照实验 | 🤖 | ⬜ | | 固定链路 vs Agent |
| T22 百度搜索工具 | 🤖 | ⬜ | | 批次 B，需 key |
| T23 天气工具 | 🤖 | ⬜ | | 批次 B，需 key |
| T24 MCP server | 🧩 | ⬜ | | 批次 C |
| T25 MCP client | 🤖 | ⬜ | | 批次 C |
| T26 Skill 机制 | 🤖 | ⬜ | | 批次 D |
| T27 流式输出 | 🤖 | ⬜ | | 可选 / 后续 |

---

## 5. 任务与 spec 的映射速查

| spec 章节 | 对应任务 |
|-----------|----------|
| §7.1 配置 / §7.2 模型 / §14 环境变量 | T0 |
| §7.3 loaders | T1 |
| §7.4 chunking | T2 |
| §7.5 embeddings | T3 |
| §7.6 vectorstore | T4 |
| §7.7 rerank | T5 |
| §7.8 llm | T6 |
| §7.9 prompts / §12.3 提示词正文 | T7 |
| §7.10 pipeline | T8、T9 |
| §8 API | T10 |
| §9 前端 | T11 |
| §13.1 评测集 | T12 |
| §7.11 evaluate / §13.2–13.6 评测 | T13 |
| §15 M7 | T14 |
| §11 FAQ 常见坑 | 贯穿 T3/T5/T6/T7，T14 汇总 |
| **§18 代码规范（注释 / 日志 / Review）** | **贯穿全部任务**，每个任务都必须遵守 |
| §7.12 logging_conf | T0 |
| §19.2 / §19.5 工具概念与工具层 | T15 |
| §19.6 LLM 工具调用 | T16 |
| §19.7 工具清单（datetime / kb） | T17 |
| §19.8 agent loop | T18 |
| §19.9 API 契约 / §8 错误信封 | T19 |
| §19.10 前端轨迹 | T20 |
| §19.14 对照实验 | T21 |
| §19.7 工具清单（web_search） | T22 |
| §19.7 工具清单（get_weather） | T23 |
| §19.12 MCP（server 侧） | T24 |
| §19.12 MCP（client 侧） | T25 |
| §19.11 Skill 机制 | T26 |
| §19.10 流式 | T27 |
| **§19.13 安全与日志增量** | **贯穿 T15–T27**，每个任务都必须遵守 |

---

## 6. Agent 化任务清单（T15–T27）

> 设计契约见 spec §19，本清单不重复其内容。
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

---

## 7. Agent 化里程碑

| 里程碑 | 任务 | 验收标准 |
|--------|------|----------|
| **M8 Agent loop** | T15–T18 | 命令行跑通"问时间 → 模型调 `get_datetime` → 回答"，`steps` 完整 |
| **M9 API + 前端** | T19–T21 | 浏览器看到工具轨迹与最终答案；对照表产出 |
| **M10 外网工具** | T22–T23 | 真实调通（或如实记录"未联调"） |
| **M11 MCP + Skill** | T24–T26 | md 落 `data/exports/`；skill 两种触发都生效 |
| **M12 流式**（可选） | T27 | 事件流可见，非流式接口不受影响 |
