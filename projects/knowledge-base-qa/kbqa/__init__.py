"""kbqa 核心包：与框架无关的 RAG 实现，供 Notebook 与 FastAPI 复用。

本文件只做一件事——统一日志初始化，不导出任何业务对象，
避免 `import kbqa` 时意外触发昂贵或依赖网络的模块加载。
"""

from kbqa.logging_conf import setup_logging

# 全项目只在此处初始化一次日志（§7.12）
setup_logging()
