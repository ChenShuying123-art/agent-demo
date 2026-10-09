"""数据模型定义（§7.2）。

职责边界：只定义贯穿各模块的数据结构（DTO），不含任何业务逻辑，
也不依赖 config / 网络，保证任何模块都能安全 import。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Document:
    """一篇已上传文档的元数据。"""

    doc_id: str  # 内容 sha256 前 16 位，用于去重
    filename: str
    path: Path
    size: int
    uploaded_at: datetime
    indexed: bool = False
    chunk_count: int = 0


@dataclass
class Chunk:
    """文档切分后的一个片段，携带位置元数据以便引用定位。"""

    chunk_id: str  # f"{doc_id}-{index:04d}"
    doc_id: str
    filename: str
    index: int
    text: str
    start: int  # 在原文中的字符起始位置（可观测用）
    end: int


@dataclass
class SearchResult:
    """召回阶段的产物。"""

    chunk: Chunk
    score: float  # cosine similarity, [-1, 1]
    rank: int  # 召回排名，从 0 开始


@dataclass
class RerankResult:
    """重排阶段的产物。"""

    chunk: Chunk
    rerank_score: float  # 与 cosine 尺度不同，不可混用
    original_rank: int  # 重排前在召回列表中的位置（★ 看排序变化）
    new_rank: int
    degraded: bool = False  # 是否走了降级路径（未真正重排）；降级时 rerank_score 其实是 cosine 分数


@dataclass
class QAResult:
    """一次问答的完整结果。"""

    answer: str
    style: str
    citations: list[str]  # 形如 ["report.md#0003", ...]
    candidates: list[SearchResult]  # 召回 20 条，供前端展示
    used: list[RerankResult]  # 重排后实际送进 LLM 的 4 条
    latency_ms: int
