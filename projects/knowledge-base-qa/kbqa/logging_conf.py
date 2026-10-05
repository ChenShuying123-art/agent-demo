"""统一日志配置模块（§7.12）。

职责边界：只负责初始化标准库 `logging` 的格式与级别。
各业务模块统一 `logger = logging.getLogger(__name__)` 使用，
不得自行添加 handler 或调用 basicConfig，避免日志重复输出/格式不一致。
"""

import logging

from kbqa.config import settings

# 全项目统一格式：时间 | 级别 | 模块名 | 消息（§18.2）
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """统一日志初始化。在 kbqa/__init__.py 中调用一次。

    Args:
        level: 日志级别字符串，如 "INFO" / "DEBUG"。为 None 时取 settings.log_level。

    Returns:
        None
    """
    resolved = (level or settings.log_level).upper()
    logging.basicConfig(
        level=resolved,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        # force=True：Notebook 中可能已存在默认 handler，强制重建以保证格式统一
        force=True,
    )
