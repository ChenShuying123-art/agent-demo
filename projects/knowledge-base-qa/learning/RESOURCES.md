# 从零写代码 —— 资源清单

> 原则一：只收一手、高可信来源。讲课时引用这里的内容，不凭记忆瞎说。
> 原则二：**有官方中文文档的，优先给中文**；没有官方中文的才用英文，并在下方「语言说明」里标注。

## 语言说明

- **有官方中文**（优先使用）：Python 官方文档、FastAPI、12-Factor App
- **暂无官方中文**（只能用英文）：Pydantic、mypy、OWASP

## Knowledge

- [Python 官方教程 · 6. 模块](https://docs.python.org/zh-cn/3/tutorial/modules.html)（官方中文）
  权威解释"什么是模块/包、`__init__.py`、import 从哪找文件"。用在哪：理解 T0 的包结构为什么长这样。
- [Python 官方教程 · 9. 类](https://docs.python.org/zh-cn/3/tutorial/classes.html)（官方中文）
  类、继承、属性的权威入门。用在哪：前置课第 1、2 站（`class Document`、`class Settings(BaseSettings)`）。
- [Python 官方文档 · dataclasses](https://docs.python.org/zh-cn/3/library/dataclasses.html)（官方中文）
  `@dataclass` 到底自动生成了什么。用在哪：前置课第 1 站。
- [Python 官方 HOWTO · 日志指南](https://docs.python.org/zh-cn/3/howto/logging.html)（官方中文，部分页可能回落英文）
  日志级别、logger、handler 的权威入门。用在哪：前置课第 3 站、`logging_conf.py`。
- [Python 官方文档 · pathlib](https://docs.python.org/zh-cn/3/library/pathlib.html)（官方中文）
  `Path.name` / `.suffix` / `read_text` / `glob` 的权威说明。用在哪：课程 0003、`loaders.py`。
- [Python 官方文档 · re 正则表达式](https://docs.python.org/zh-cn/3/library/re.html)（官方中文）
  正则语法与 `re.finditer` 等 API。用在哪：课程 0004、`chunking.py`（识别空行与 md 标题行）。
- [Python 官方文档 · hashlib](https://docs.python.org/zh-cn/3/library/hashlib.html)（官方中文）
  sha256 等哈希算法；说明"哈希用于完整性校验与内容寻址"。用在哪：课程 0003 的内容寻址、`doc_id`。
- [Python 官方 HOWTO · Unicode 指南](https://docs.python.org/zh-cn/3/howto/unicode.html)（官方中文，部分页可能回落英文）
  解释编码/解码为何会出错、为什么必须显式指定 UTF-8。用在哪：课程 0003 的"编码坑"。
- [Python 官方文档 · typing（类型注解）](https://docs.python.org/zh-cn/3/library/typing.html)（官方中文）
  说明"类型注解在运行时不被强制，但为人和工具服务"。用在哪：理解为什么写 `dashscope_api_key: str`。
- [Pydantic Settings 官方文档](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)（英文，无官方中文）
  `BaseSettings` / `SettingsConfigDict` / `.env` 读取与优先级的权威说明。用在哪：T0 的 `config.py`。
- [FastAPI 教程 · 设置和环境变量](https://fastapi.tiangolo.com/zh/advanced/settings/)（官方中文）
  把 pydantic-settings 用在真实 Web 项目的完整范例（含"只实例化一次"的写法）。用在哪：`config.py` 的工程惯例。
- [FastAPI 教程 · 第一步](https://fastapi.tiangolo.com/zh/tutorial/first-steps/)（官方中文）
  路由与装饰器（`@app.get` 这类）的最小可运行例子。用在哪：课程 0014、`api/routes.py` 的"把函数挂到 URL 上"。
- [FastAPI 教程 · 响应模型](https://fastapi.tiangolo.com/zh/tutorial/response-model/)（官方中文）
  `response_model` 与"内部对象 vs 对外模型"的官方说明。用在哪：课程 0014、`api/schemas.py` 的 `to_xxx_out()`。
- [MDN · HTTP 响应状态码](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Status)（官方中文）
  200 / 400 / 404 / 422 / 502 等状态码的权威定义。用在哪：课程 0014 的状态码表与错误信封。
- [Pydantic 官方文档 · Models](https://docs.pydantic.dev/latest/concepts/models/)（英文，无官方中文）
  `BaseModel` 的字段声明与校验行为（请求校验、自动生成文档都靠它）。用在哪：课程 0014、`api/schemas.py`。
- [The Twelve-Factor App · III. 配置](https://12factor.net/zh_cn/config)（官方中文）
  配置外置这一工程原则的原始出处：为什么密钥不能写进代码。用在哪：理解 `.env` / `.gitignore` 的存在意义。
- [阿里云百炼 · 向量化（Embedding）](https://help.aliyun.com/zh/model-studio/embedding)（官方中文）
  文本向量化总览：模型列表、维度可选值、**单次最多 10 条**等硬事实。用在哪：课程 0005、`embeddings.py`。
- [阿里云百炼 · OpenAI 兼容 Embedding 接口](https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai)（官方中文）
  OpenAI 兼容协议的调用方式与参数（含 `dimensions`）。用在哪：课程 0005、`embeddings.py`。
- [阿里云百炼 · 文本排序（Rerank）](https://help.aliyun.com/zh/model-studio/rerank)（官方中文）
  重排序总览、endpoint、调用示例。用在哪：课程 0007、`rerank.py`。⚠️ 示例里的请求体格式与实测不一致，以实测为准。
- [阿里云百炼 · 文本排序 API 使用详情](https://help.aliyun.com/zh/model-studio/text-rerank-api)（官方中文）
  模型列表、参数（`top_n` / `return_documents`）、响应结构。用在哪：课程 0007、`rerank.py`。
- [阿里云百炼 · 深度思考（enable_thinking）](https://help.aliyun.com/zh/model-studio/deep-thinking)（官方中文）
  哪些模型默认开启思考模式、`reasoning_content` 与 `content` 分别放什么、如何关闭。用在哪：课程 0008、`llm.py`。
- [阿里云百炼 · OpenAI 兼容 Chat](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)（官方中文）
  chat/completions 的请求参数与调用示例。用在哪：课程 0008、`llm.py`。
- [阿里云百炼 · 文生文 Prompt 指南](https://help.aliyun.com/zh/model-studio/use-cases/prompt-engineering-guide)（官方中文）
  Prompt 框架（背景 / 目的 / 风格 / 语气 / 受众 / 输出）与"模糊 → 清晰"的改造方法。用在哪：课程 0010、`prompts.py`。
- [NumPy 官方文档 · Linear algebra（含 norm 与 @ 运算符）](https://numpy.org/doc/stable/reference/routines.linalg.html)（英文，无官方中文）
  矩阵乘法 `@` 与 `linalg.norm`。用在哪：课程 0006、`vectorstore.py` 的 L2 归一化与相似度计算。
- [NumPy 官方文档 · numpy.argpartition](https://numpy.org/doc/stable/reference/generated/numpy.argpartition.html)（英文，无官方中文）
  O(N) 选出前 k 大/小的下标。用在哪：课程 0006、`vectorstore.py` 的 Top-N 召回。
- [mypy 类型注解速查表](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)（英文，无官方中文）
  一页看完常见注解写法。用在哪：需要查某个注解怎么写时的第一站。
- [OWASP · File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)（英文，无官方中文）
  文件上传的安全清单（文件名消毒、路径穿越、类型校验）。用在哪：课程 0003 的"外部输入不可信"。

## Wisdom (Communities)

- [r/learnpython](https://www.reddit.com/r/learnpython/)
  对新手友好、有人认真答题的社区。用在哪：卡在"为什么这么写"时贴最小可复现代码去问。
- [Python Discourse（官方论坛）](https://discuss.python.org/)
  质量更高、更偏"语言设计/工程实践"的讨论。用在哪：想深入理解某个标准库行为时。

> 用户暂未表达加入社区的意愿；如明确拒绝，请在此记录。

## Gaps

- Pydantic、mypy、OWASP 目前**没有官方中文**；如需中文，只能找社区翻译，可信度不稳定，暂不收录。
- 缺"如何阅读 traceback 报错"的专门材料——这是新手从"卡住"到"自己解决"的关键一环，后续补。
- 缺"密钥/凭据管理"的专门一手材料（`.env` vs `.env.example`、误提交后如何补救）。课程 0005 里已按当前认知写了一段，后续找到权威来源再补。
