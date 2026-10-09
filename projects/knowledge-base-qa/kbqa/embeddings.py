"""向量化模块（spec §7.5）。

职责边界：只把文本批量转成向量。不负责存储与检索（属于 vectorstore），
也不负责切分（属于 chunking）。

两个必须守住的点：
  1. 百炼 text-embedding-v4 单次请求最多 10 条（§4.2 坑 2），超限直接报错，
     所以必须内部分批，且默认 embedding_batch_size=10 不得调大。
  2. 分批后必须保证返回顺序与输入顺序严格一致。这是本模块最容易出的 bug：
     顺序错乱不会抛异常，但会让"第 i 个向量对应第 i 条文本"的假设悄悄失效，
     导致检索结果整体错位。做法是：按顺序同步发送每一批，再按顺序拼接结果
     ——不并发、不重排、不排序。
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from openai import OpenAI

from kbqa.config import Settings

logger = logging.getLogger(__name__)

_MAX_RETRY = 2  # §7.5 要求"失败重试 2 次"，即最多尝试 1 + 2 = 3 次
_BAILIAN_BATCH_LIMIT = 10  # 百炼硬限制：单次最多 10 条（§4.2 坑 2）


@runtime_checkable
class EmbeddingProvider(Protocol):
    """向量化提供方接口（§7.5）。换实现只改这里，业务代码不动（NFR-2）。"""

    @property
    def dim(self) -> int:
        """向量维度。索引与查询必须用同一模型，否则向量空间不一致。"""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """把文本列表转成向量列表，长度与顺序均与输入一致。"""
        ...


class DashScopeEmbedding:
    """百炼（DashScope）实现，走 OpenAI 兼容协议 compatible-mode/v1。"""

    def __init__(self, settings: Settings) -> None:
        # base_url 只到版本号，路径由 SDK 自己拼（§11：带了 /chat/completions 会 404）
        self._client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.embedding_base_url,
        )
        self._model = settings.embedding_model
        self._dim = settings.embedding_dim

        # 防呆：配置里若把批次调大，这里强制拉回上限，避免调用时才报 batch 超限
        self._batch_size = settings.embedding_batch_size
        if self._batch_size > _BAILIAN_BATCH_LIMIT:
            logger.warning(
                "embedding_batch_size=%d 超过百炼上限 %d，已强制改为 %d",
                self._batch_size,
                _BAILIAN_BATCH_LIMIT,
                _BAILIAN_BATCH_LIMIT,
            )
            self._batch_size = _BAILIAN_BATCH_LIMIT

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（内部自动分批）。

        Args:
            texts: 待向量化的文本列表。允许为空。

        Returns:
            与 texts 等长、顺序一一对应的向量列表；texts 为空时返回空列表。

        Raises:
            Exception: 某一批重试 _MAX_RETRY 次后仍失败时，抛出最后一次的异常。
        """
        if not texts:
            return []

        n_batches = (len(texts) + self._batch_size - 1) // self._batch_size
        logger.info(
            "开始向量化 文本数=%d 批次数=%d batch_size=%d 模型=%s",
            len(texts),
            n_batches,
            self._batch_size,
            self._model,
        )

        vectors: list[list[float]] = []
        # 顺序、同步地发送每一批：返回结果按批顺序 extend 回去，
        # 全量顺序自然等于输入顺序（若改成并发，就必须额外记住批次下标再排序）
        for batch_no, start in enumerate(range(0, len(texts), self._batch_size), start=1):
            batch = texts[start : start + self._batch_size]
            batch_vectors = self._embed_one_batch(batch_no, batch)
            vectors.extend(batch_vectors)
            logger.debug(
                "第 %d/%d 批完成 本批=%d 累计=%d",
                batch_no,
                n_batches,
                len(batch),
                len(vectors),
            )

        # 不变量：返回条数必须与输入条数一致，否则说明分批拼接处有 bug
        assert len(vectors) == len(texts), f"向量数({len(vectors)}) != 文本数({len(texts)})"
        logger.info("向量化完成 文本数=%d 维度=%d", len(vectors), len(vectors[0]) if vectors else 0)
        return vectors

    def _embed_one_batch(self, batch_no: int, batch: list[str]) -> list[list[float]]:
        """发送单批请求，失败重试 _MAX_RETRY 次。

        Args:
            batch_no: 批次序号（从 1 开始），仅用于日志定位。
            batch: 本批文本。

        Returns:
            本批向量，顺序与 batch 一致。

        Raises:
            Exception: 重试耗尽后，抛出最后一次的异常（保留原始信息便于排查）。
        """
        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRY + 2):
            try:
                resp = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                    dimensions=self._dim,  # 让维度跟配置一致（text-embedding-v4 支持该参数）
                )
                # 按 index 显式排序：百炼本身就按下标有序返回，
                # 这里排一次是防止将来换实现时"乱序返回"导致静默错位
                items = sorted(resp.data, key=lambda item: item.index)
                return [item.embedding for item in items]
            except Exception as exc:  # noqa: BLE001 —— 重试策略：任何失败都重试，耗尽后原样抛出
                last_error = exc
                logger.warning(
                    "向量化第 %d 批第 %d 次尝试失败：%s",
                    batch_no,
                    attempt,
                    exc,
                )

        raise last_error  # type: ignore[misc]


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """工厂函数：按配置返回向量化实现（§7.5）。

    索引与查询都要通过它取实例，确保用的是同一个模型 / 同一维度。
    """
    return DashScopeEmbedding(settings)
