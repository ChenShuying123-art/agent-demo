"""配置加载模块。

职责边界：只负责从 .env / 环境变量读取配置，并暴露全局唯一的 `settings` 实例。
本模块不含任何业务逻辑，也不依赖上层业务模块（loaders / llm 等），
以保证任何模块都可以安全 import 它来拿配置。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全项目配置。

    字段名与 .env 中的 UPPER_SNAKE key 一一对应（pydantic-settings 默认大小写不敏感），
    例如 `.env` 里的 `CHAT_MODEL` 会映射到这里的 `chat_model`。
    """

    # 显式声明读取 .env：PROJECT 要求所有 key/模型名/参数都外置（§NFR-3），
    # 不硬编码在代码里；extra="ignore" 允许 .env 中存在本类未声明的键而不报错。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 阿里云百炼 ----
    dashscope_api_key: str  # 对话/Embedding/Rerank 共用，必填，缺失即报错暴露问题

    # 对话
    chat_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen-plus"
    chat_temperature: float = 0.0
    chat_enable_thinking: bool = False

    # Embedding
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1024
    embedding_batch_size: int = 10  # 百炼硬限制，单次最多 10 条，勿调大（§4.2 坑 2）

    # Rerank
    rerank_enabled: bool = True
    rerank_endpoint: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
    rerank_model: str = "qwen3-rerank"

    # 切分
    chunk_size: int = 500  # 字符数
    chunk_overlap: int = 80
    # 两阶段检索
    retrieve_top_k: int = 20  # 召回候选数（追求"不漏"）
    rerank_top_n: int = 4  # 重排后送入 LLM 的数量

    # Agent 工具
    agent_max_steps: int = 5  # loop 上限，防死循环烧钱（§19.4）
    agent_tool_result_max_chars: int = 2000  # 单个工具结果回填前的截断上限（§19.13）
    agent_engine: str = "handwritten"  # handwritten | langgraph（§19.17）

    # Agent 外网工具（批次 B）：endpoint/key 留空时工具返回明确标注的 mock 结果
    web_search_api_key: str = ""
    web_search_endpoint: str = ""
    weather_api_key: str = ""
    weather_endpoint: str = ""

    # MCP（批次 C）：默认关闭；关闭时进程内不 import mcp（§19.12）
    mcp_enabled: bool = False
    mcp_servers: str = ""  # JSON 数组，见 .env.example
    export_dir: Path = Path("data/exports")

    # Skill（批次 D）：skill 目录与是否允许模型自动选择（§19.11）
    skills_dir: Path = Path("skills")
    skill_auto_select: bool = True

    # 日志
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR（§18.2）

    # 存储
    data_dir: Path = Path("data")


# 模块级单例：全项目共用一份配置，避免各模块重复实例化导致配置漂移。
settings = Settings()  # 从 .env 读取
