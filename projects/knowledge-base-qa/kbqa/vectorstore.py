"""本地向量存储与余弦召回（spec §7.6）。

职责边界：只负责"存向量 + 按相似度召回"。
**不负责重排**——重排是 rerank.py 的事，这个边界要守住（§7.6 明确强调）。

存储方案（纯本地，无外部依赖）：
    data/index/vectors.npy   float32 的 (N, D) 矩阵，L2 归一化后存储
    data/index/chunks.jsonl  每行一个 Chunk 的 JSON，行序与 vectors 行序严格一致
    data/index/docs.json     文档索引状态：{doc_id: {filename, chunks, indexed_at}}

三者必须始终保持"行序同步"：第 i 行向量 ↔ 第 i 行 chunk。
任何增删都要同时动两边，否则检索拿到的会是"别的文档的向量 + 这篇文档的文字"。

关于日志：本模块只拿到"查询向量"，拿不到查询文本，
所以"召回 query=..."那条日志由编排层 pipeline 负责（§18.2），这里只打命中数与 top1 分数。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

from kbqa.models import Chunk, SearchResult

logger = logging.getLogger(__name__)

_VECTORS_FILE = "vectors.npy"
_CHUNKS_FILE = "chunks.jsonl"
_DOCS_FILE = "docs.json"


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """按行做 L2 归一化。

    为什么必须归一化：归一化之后向量的模长都是 1，
    此时"点积"恰好等于"余弦相似度"，一次矩阵乘法就能算完全部相似度，
    比逐条算余弦快得多，也不用在打分时反复算模长。
    """
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # 零向量（理论上不该出现）会导致除零，兜底成 1，避免 NaN 污染整个矩阵
    norms[norms == 0] = 1.0
    return matrix / norms


def read_indexed_docs(index_dir: Path) -> dict[str, int]:
    """读取 docs.json，返回已索引文档的 {doc_id: chunk 数}。

    为什么放在本模块：docs.json 的"文件名叫什么、里面长什么样"是向量库的私有知识，
    统一收在这里，别的模块需要时来问，避免文件格式散落多处（单一事实来源）。
    loaders.list_documents（§7.3）就是靠它把"是否已索引 / chunk 数"合并进 Document 的。

    Args:
        index_dir: 索引目录（data/index）。

    Returns:
        {doc_id: chunk 数}；文件不存在或内容损坏时返回空 dict（等价于"什么都没索引"）。
    """
    path = index_dir / _DOCS_FILE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # 读不出来不应该让"列文档"整个失败——降级成"未索引"，并留下告警便于排查
        logger.warning("读取索引元数据失败，按未索引处理 文件=%s 原因=%s", path, exc)
        return {}
    return {doc_id: int(info.get("chunks", 0)) for doc_id, info in raw.items()}


class VectorStore:
    """内存中的向量索引 + 落盘能力。"""

    def __init__(self, index_dir: Path) -> None:
        self._index_dir = index_dir
        self._chunks: list[Chunk] = []
        # 空索引用 (0, 0) 表示；首次 add() 时直接替换，避免和 (N, D) 拼接时维度对不上
        self._vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._docs: dict[str, dict] = {}

    # ------------------------------------------------------------------ 写入

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        """把一批 chunk 及其向量追加进索引。

        Args:
            chunks: 与 vectors 行数一致的 Chunk 列表。
            vectors: (N, D) 的向量矩阵。

        Returns:
            None

        Raises:
            ValueError: 行数与向量数不一致，或维度与已有索引不一致。
        """
        started = time.perf_counter()
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError(f"vectors 必须是二维矩阵，当前 ndim={matrix.ndim}")
        if len(chunks) != matrix.shape[0]:
            raise ValueError(f"chunk 数({len(chunks)}) != 向量行数({matrix.shape[0]})")

        # 维度必须一致：索引与查询用同一个模型，维度对不上说明混用了不同模型
        if self._vectors.size and self._vectors.shape[1] != matrix.shape[1]:
            raise ValueError(
                f"向量维度不一致：已有 {self._vectors.shape[1]}，新来 {matrix.shape[1]}"
            )

        matrix = _normalize(matrix)
        self._chunks.extend(chunks)
        self._vectors = matrix if self._vectors.size == 0 else np.vstack([self._vectors, matrix])

        # 更新文档索引状态：出现在这里即视为"已索引"
        now = datetime.now().isoformat(timespec="seconds")
        per_doc: dict[str, int] = {}
        for chunk in chunks:
            per_doc[chunk.doc_id] = per_doc.get(chunk.doc_id, 0) + 1
        for doc_id, count in per_doc.items():
            entry = self._docs.setdefault(doc_id, {"filename": "", "chunks": 0, "indexed_at": now})
            entry["filename"] = next(c.filename for c in chunks if c.doc_id == doc_id)
            entry["chunks"] = entry.get("chunks", 0) + count
            entry["indexed_at"] = now

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "入库完成 新增=%d 总chunk数=%d 文档数=%d 维度=%d 耗时=%dms",
            len(chunks),
            len(self._chunks),
            len(self._docs),
            self.stats()["dim"],
            elapsed_ms,
        )
        self._assert_rows_aligned()

    def remove_document(self, doc_id: str) -> None:
        """删除某个文档的全部 chunk 与向量，并立刻落盘。

        为什么这里立刻保存、而 add() 不保存：删除必须马上生效，
        否则进程崩溃后"已经删掉的向量"会从文件里复活；
        新增是批量行为，交给调用方最后统一 save() 一次，避免反复重写大文件。

        Args:
            doc_id: 要删除的文档 id。

        Returns:
            None
        """
        keep = [i for i, chunk in enumerate(self._chunks) if chunk.doc_id != doc_id]
        removed = len(self._chunks) - len(keep)

        # 用"保留哪些行"的方式同时重建两边，天然保证行序一致
        self._chunks = [self._chunks[i] for i in keep]
        self._vectors = (
            self._vectors[keep]
            if keep
            else np.zeros((0, self._vectors.shape[1]), dtype=np.float32)
        )
        self._docs.pop(doc_id, None)

        logger.info(
            "删除文档完成 doc_id=%s 移除chunk数=%d 剩余chunk数=%d",
            doc_id,
            removed,
            len(self._chunks),
        )
        self._assert_rows_aligned()
        self.save()

    # ------------------------------------------------------------------ 读取

    def search(
        self,
        query_vector: np.ndarray,
        top: int,
        doc_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        """按余弦相似度召回 Top-N。

        Args:
            query_vector: 查询向量，(D,) 或 (1, D)。内部会做 L2 归一化。
            top: 返回条数上限。
            doc_ids: 只在这些文档范围内召回；None 表示全库。

        Returns:
            按 score 降序排列的 SearchResult 列表；rank 从 0 开始。
            索引为空、top<=0、或过滤后无候选时返回空列表。

        Raises:
            ValueError: 查询向量维度与索引维度不一致（通常意味着索引与查询用了不同的 embedding 模型）。
        """
        started = time.perf_counter()
        if not self._chunks or top <= 0:
            return []

        query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query.shape[0] != self._vectors.shape[1]:
            raise ValueError(
                f"查询向量维度({query.shape[0]}) 与索引维度({self._vectors.shape[1]}) 不一致"
            )
        query = _normalize(query.reshape(1, -1)).reshape(-1)

        # 向量已归一化，点积即余弦相似度
        scores = self._vectors @ query

        # doc_ids 过滤：先把候选范围缩小到指定文档，再做 Top-N
        if doc_ids is None:
            candidate_idx = np.arange(len(self._chunks))
        else:
            allowed = set(doc_ids)
            candidate_idx = np.array(
                [i for i, chunk in enumerate(self._chunks) if chunk.doc_id in allowed],
                dtype=np.int64,
            )
            if candidate_idx.size == 0:
                logger.info("召回完成 命中=0（doc_ids 过滤后无候选）")
                return []

        candidate_scores = scores[candidate_idx]
        k = min(top, candidate_idx.size)

        # 为什么用 argpartition 而不是全排序：全排序是 O(N log N)，而我们只要前 k 个。
        # argpartition 是 O(N)，万级 chunk 下差别明显。
        # 它只保证"含最大的 k 个"，不保证这 k 个内部有序，所以拿到后再对它们排一次。
        if k < candidate_idx.size:
            part = np.argpartition(-candidate_scores, k - 1)[:k]
        else:
            part = np.arange(candidate_idx.size)
        order = np.argsort(-candidate_scores[part], kind="stable")
        picked = candidate_idx[part[order]]

        results = [
            SearchResult(chunk=self._chunks[i], score=float(scores[i]), rank=rank)
            for rank, i in enumerate(picked)
        ]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "召回完成 命中=%d top1=%.4f 耗时=%dms",
            len(results),
            results[0].score if results else 0.0,
            elapsed_ms,
        )
        logger.debug("召回细节 doc_ids=%s top=%d", doc_ids, top)
        return results

    def stats(self) -> dict:
        """返回索引概况：{"chunks": N, "docs": M, "dim": D}。"""
        return {
            "chunks": len(self._chunks),
            "docs": len(self._docs),
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
        }

    # ------------------------------------------------------------------ 落盘

    def save(self) -> None:
        """全量落盘（三个文件一起写，保证行序同步）。

        Args:
            无。

        Returns:
            None
        """
        self._index_dir.mkdir(parents=True, exist_ok=True)
        np.save(self._index_dir / _VECTORS_FILE, self._vectors)

        with (self._index_dir / _CHUNKS_FILE).open("w", encoding="utf-8") as fh:
            for chunk in self._chunks:
                fh.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

        with (self._index_dir / _DOCS_FILE).open("w", encoding="utf-8") as fh:
            json.dump(self._docs, fh, ensure_ascii=False, indent=2)

        logger.info(
            "索引已落盘 目录=%s chunks=%d 维度=%d",
            self._index_dir,
            len(self._chunks),
            self.stats()["dim"],
        )

    @classmethod
    def load(cls, index_dir: Path) -> "VectorStore":
        """从磁盘恢复索引；文件不存在时返回空索引。

        Args:
            index_dir: 索引目录（data/index）。

        Returns:
            VectorStore 实例。
        """
        store = cls(index_dir)
        vectors_path = index_dir / _VECTORS_FILE
        chunks_path = index_dir / _CHUNKS_FILE
        docs_path = index_dir / _DOCS_FILE

        if not vectors_path.exists() or not chunks_path.exists():
            logger.info("索引文件不存在，返回空索引 目录=%s", index_dir)
            return store

        store._vectors = np.load(vectors_path).astype(np.float32)
        store._chunks = [
            Chunk(**json.loads(line))
            for line in chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if docs_path.exists():
            store._docs = json.loads(docs_path.read_text(encoding="utf-8"))

        # 这是本模块最大的隐患：npy 行数与 jsonl 行数一旦不同步，
        # 检索就会拿到"错位的向量 + 文字"，且不会抛异常。这里主动查出来并报警。
        if store._vectors.shape[0] != len(store._chunks):
            logger.error(
                "npy 行数(%d) != jsonl 行数(%d)，索引已损坏",
                store._vectors.shape[0],
                len(store._chunks),
            )
        store._assert_rows_aligned()
        logger.info(
            "索引已加载 目录=%s chunks=%d 文档数=%d",
            index_dir,
            len(store._chunks),
            len(store._docs),
        )
        return store

    # ------------------------------------------------------------------ 内部

    def _assert_rows_aligned(self) -> None:
        """不变量检查：向量行数必须等于 chunk 数。

        Raises:
            AssertionError: 两者不一致（行序已失步）。
        """
        if self._vectors.shape[0] != len(self._chunks):
            logger.error(
                "npy 行数(%d) != jsonl 行数(%d)，行序已失步",
                self._vectors.shape[0],
                len(self._chunks),
            )
            raise AssertionError("向量行数与 chunk 数不一致，索引行序失步")
