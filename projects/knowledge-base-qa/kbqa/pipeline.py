"""检索与问答编排模块（spec §7.10）。

职责边界：把底层能力串成链路，本模块自身**不做**具体 IO、模型调用或文本处理。
    - 索引链路：文档 → 切分 → 向量化 → 入库
    - 检索链路：问题 → 召回（vectorstore）→ 重排（rerank）
    - 问答链路：组装提示词（prompts）→ 生成答案（llm）
这样每个子能力都能单独替换（NFR-2），也便于 §13 的消融实验。

为什么把 recall / rerank / retrieve **分阶段暴露**（§7.10）：
    消融实验需要"只改一个变量"——比如固定提示词、只看 rerank 开/关的影响。
    分阶段暴露后，实验脚本可以单独观察召回结果与重排结果，而不用去猜中间发生了什么。

一个容易被忽略的公平性细节：
    `answer_all_styles` **只检索一次**，让三种风格看到完全相同的参考资料。
    否则同一问题在三版之间会有"检索差异"，评测出来的分差就分不清是风格造成的、
    还是检索运气造成的——那就违背了 §12.1 的控制变量要求。
"""

from __future__ import annotations

import logging
import re
import time

import numpy as np

from kbqa.chunking import split_text
from kbqa.config import Settings
from kbqa.embeddings import EmbeddingProvider
from kbqa.llm import LLMProvider
from kbqa.loaders import list_documents, load_document
from kbqa.models import Chunk, QAResult, RerankResult, SearchResult
from kbqa.prompts import build_messages
from kbqa.rerank import RerankProvider
from kbqa.vectorstore import VectorStore

logger = logging.getLogger(__name__)

# 答案里的引用标记，形如 [1] [2]（§12.1 硬约束 3 要求标注引用编号）
_CITATION_RE = re.compile(r"\[(\d+)\]")


class RAGPipeline:
    """把各子模块编排成"索引 → 召回 → 重排 → 生成"的完整链路。"""

    def __init__(
        self,
        settings: Settings,
        store: VectorStore,
        embedder: EmbeddingProvider,
        reranker: RerankProvider | None,
        llm: LLMProvider,
    ) -> None:
        self._settings = settings
        self._store = store
        self._embedder = embedder
        self._reranker = reranker  # 可能是 None：rerank_enabled=False 时不做重排
        self._llm = llm

    # ------------------------------------------------------------------ 索引

    def index_documents(self, doc_ids: list[str]) -> list[dict]:
        """把指定文档切分、向量化并写入索引，最后统一落盘（§7.10）。

        采"先删后加"实现幂等：重复索引同一篇文档不会累积重复 chunk。

        Args:
            doc_ids: 要索引的文档 id（来自 loaders.list_documents）。

        Returns:
            [{"doc_id", "filename", "chunks", "elapsed_ms"}, ...]，便于前端展示索引进度。

        Raises:
            ValueError: 有 doc_id 在 data/uploads 下不存在（尽早暴露拼写错误）。
        """
        available = {doc.doc_id: doc for doc in list_documents(self._settings.data_dir)}
        missing = [doc_id for doc_id in doc_ids if doc_id not in available]
        if missing:
            raise ValueError(f"以下 doc_id 在上传目录中不存在：{missing}")

        report: list[dict] = []
        for doc_id in doc_ids:
            doc = available[doc_id]
            started = time.perf_counter()

            # 幂等：先清掉旧 chunk，避免重复运行时同一篇文档被索引两遍
            self._store.remove_document(doc_id)

            text = load_document(doc.path)
            pieces = split_text(text, self._settings.chunk_size, self._settings.chunk_overlap)
            chunks = [
                Chunk(
                    chunk_id=f"{doc_id}-{index:04d}",
                    doc_id=doc_id,
                    filename=doc.filename,
                    index=index,
                    text=piece,
                    start=start,
                    end=end,
                )
                for index, (start, end, piece) in enumerate(pieces)
            ]

            if chunks:
                vectors = np.asarray(
                    self._embedder.embed([c.text for c in chunks]), dtype=np.float32
                )
                self._store.add(chunks, vectors)
            else:
                logger.warning("文档内容为空，未入库 doc_id=%s 文件=%s", doc_id, doc.filename)

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            report.append(
                {
                    "doc_id": doc_id,
                    "filename": doc.filename,
                    "chunks": len(chunks),
                    "elapsed_ms": elapsed_ms,
                }
            )
            logger.info(
                "索引文档完成 doc_id=%s 文件=%s chunk数=%d 耗时=%dms",
                doc_id,
                doc.filename,
                len(chunks),
                elapsed_ms,
            )

        # add() 不落盘，这里统一写一次，避免逐篇反复重写大文件
        self._store.save()
        return report

    # ------------------------------------------------------------------ 检索

    def recall(self, question: str, doc_ids: list[str] | None) -> list[SearchResult]:
        """召回：把问题向量化，按余弦相似度取 Top-K 候选（§7.10）。

        Args:
            question: 用户问题原文。
            doc_ids: 只在这些文档内召回；None 表示全库。

        Returns:
            按 cosine 降序排列的 SearchResult 列表，最多 retrieve_top_k 条。

        Raises:
            无。空问题直接返回空候选（由上层决定如何提示用户）。
        """
        if not question.strip():
            logger.warning("recall 收到空问题，返回空候选")
            return []

        started = time.perf_counter()
        # 查询与索引必须用同一个 embedding 模型，否则向量空间不一致，检索必然失效（§11）
        query_vector = np.asarray(self._embedder.embed([question])[0], dtype=np.float32)

        candidates = self._store.search(
            query_vector,
            top=self._settings.retrieve_top_k,
            doc_ids=doc_ids,
        )

        # vectorstore 只拿到向量、拿不到问题文本，所以"召回 query=..."这条日志由这里补上（§18.2）
        logger.info(
            "召回完成 query=%s 命中=%d top_k=%d 范围=%s top1=%s 耗时=%dms",
            _short(question),
            len(candidates),
            self._settings.retrieve_top_k,
            f"{len(doc_ids)} 篇文档" if doc_ids else "全库",
            f"{candidates[0].score:.4f}" if candidates else "无",
            int((time.perf_counter() - started) * 1000),
        )
        return candidates

    def rerank(
        self,
        question: str,
        candidates: list[SearchResult],
    ) -> list[RerankResult]:
        """重排：对召回候选精排，返回前 rerank_top_n 条（§7.10）。

        重排器为 None（未启用）时退化为"直接截断"，并标记 degraded=True——
        保证无论重排可用与否，链路都不会中断（§7.7 关键细节 5）。

        Args:
            question: 用户问题原文。
            candidates: 召回结果（已按 cosine 降序）。

        Returns:
            重排后的 RerankResult 列表；无候选时返回空列表。
        """
        if not candidates:
            return []

        top_n = self._settings.rerank_top_n
        if self._reranker is None:
            logger.info("未启用重排，直接取召回前 %d 条", top_n)
            return self._degrade(candidates, top_n)
        return self._reranker.rerank(question, candidates, top_n)

    def retrieve(
        self,
        question: str,
        doc_ids: list[str] | None,
        use_rerank: bool | None = None,
    ) -> tuple[list[SearchResult], list[RerankResult]]:
        """召回 +（可选）重排，一次拿到两阶段结果（§7.10）。

        `use_rerank` 是给**消融实验**用的显式开关（§7.10）：
            None → 跟随 settings.rerank_enabled；
            True / False → 强制开或关，用于对比"有重排 vs 无重排"。

        Args:
            question: 用户问题原文。
            doc_ids: 只在这些文档内检索；None 表示全库。
            use_rerank: 是否启用重排；None 表示跟随配置。

        Returns:
            (candidates, used)：
              candidates —— 召回的全部候选，供前端展示"召回列"；
              used       —— 实际送入 LLM 的若干条，供前端展示"重排列"。
        """
        enabled = self._settings.rerank_enabled if use_rerank is None else use_rerank
        started = time.perf_counter()

        candidates = self.recall(question, doc_ids)
        if enabled:
            used = self.rerank(question, candidates)
        else:
            # 显式关掉重排（消融用）：绕过 self.rerank，避免重排器仍被调用
            used = self._degrade(candidates, self._settings.rerank_top_n)

        logger.info(
            "检索完成 use_rerank=%s 候选=%d 采用=%d 耗时=%dms",
            enabled,
            len(candidates),
            len(used),
            int((time.perf_counter() - started) * 1000),
        )
        return candidates, used

    # ------------------------------------------------------------------ 问答

    def answer(
        self,
        question: str,
        style: str,
        doc_ids: list[str] | None,
        use_rerank: bool | None = None,
    ) -> QAResult:
        """单风格问答：检索 → 组装提示词 → 生成 → 抽取引用（§7.10）。

        Args:
            question: 用户问题原文。
            style: 提示词风格，须在 PROMPT_STYLES 中。
            doc_ids: 只在这些文档内检索；None 表示全库。
            use_rerank: 是否启用重排；None 表示跟随配置。

        Returns:
            QAResult，含答案、引用、两阶段检索结果与总耗时。

        Raises:
            ValueError: style 非法（由 prompts.build_messages 抛出）。
            LLMError: 生成失败。
        """
        retrieve_started = time.perf_counter()
        candidates, used = self.retrieve(question, doc_ids, use_rerank)
        retrieve_ms = int((time.perf_counter() - retrieve_started) * 1000)
        return self._generate(question, style, candidates, used, retrieve_ms)

    def answer_all_styles(
        self,
        question: str,
        styles: list[str],
        doc_ids: list[str] | None,
    ) -> list[QAResult]:
        """同一问题并排生成多种风格的回答（§7.10）。

        关键设计：**只检索一次**，三版共用同一份参考资料（candidates / used）。
        这样三版之间的差异只可能来自提示词风格，而不是"这版恰好检索到了更好的资料"——
        这是 §12.1 控制变量要求在编排层的落地。

        Args:
            question: 用户问题原文。
            styles: 要生成的风格列表（通常直接传 PROMPT_STYLES）。
            doc_ids: 只在这些文档内检索；None 表示全库。

        Returns:
            与 styles 顺序一致的 QAResult 列表。
        """
        retrieve_started = time.perf_counter()
        candidates, used = self.retrieve(question, doc_ids)
        retrieve_ms = int((time.perf_counter() - retrieve_started) * 1000)

        logger.info("并排生成 风格数=%d 参考资料=%d 条", len(styles), len(used))
        return [
            self._generate(question, style, candidates, used, retrieve_ms) for style in styles
        ]

    # ------------------------------------------------------------------ 内部

    def _generate(
        self,
        question: str,
        style: str,
        candidates: list[SearchResult],
        used: list[RerankResult],
        retrieve_ms: int,
    ) -> QAResult:
        """组装 messages 并调用 LLM，最后装配成 QAResult。

        `latency_ms` = 本次检索耗时 + 本次生成耗时。检索耗时由调用方传入，
        这样 answer_all_styles 里三版都能算上同一份检索时间，而不会互相叠加。
        """
        started = time.perf_counter()
        messages = build_messages(style, question, used)
        answer_text = self._llm.chat(messages)
        generate_ms = int((time.perf_counter() - started) * 1000)

        citations = _extract_citations(answer_text, used)
        logger.info(
            "问答完成 风格=%s 候选=%d 采用=%d 引用=%d 答案长度=%d 生成=%dms 检索=%dms",
            style,
            len(candidates),
            len(used),
            len(citations),
            len(answer_text),
            generate_ms,
            retrieve_ms,
        )
        return QAResult(
            answer=answer_text,
            style=style,
            citations=citations,
            candidates=candidates,
            used=used,
            latency_ms=retrieve_ms + generate_ms,
        )

    @staticmethod
    def _degrade(candidates: list[SearchResult], top_n: int) -> list[RerankResult]:
        """降级：直接取召回前 top_n 条，并标记 degraded=True。

        这里的 `rerank_score` 装的是**召回阶段的 cosine 分数**，与真正的
        relevance_score 不同尺度；`degraded` 标记就是给调用方的提示——
        看到它就不该把这里的分数跟正常重排的结果放在一起比较（§7.7 注意）。
        """
        return [
            RerankResult(
                chunk=item.chunk,
                rerank_score=item.score,
                original_rank=item.rank,
                new_rank=position,
                degraded=True,
            )
            for position, item in enumerate(candidates[:top_n])
        ]


def _extract_citations(answer: str, used: list[RerankResult]) -> list[str]:
    """从答案里抽取引用，映射成 "文件名#chunk序号" 列表（§7.2 QAResult.citations）。

    引用编号 n 对应 format_context 里的第 n 条参考资料（即 used[n-1]），
    所以这里必须用 used 的顺序去映射——顺序错了，前端点开看到的就不是同一段原文。

    越界的编号（例如只给了 4 条资料却标了 [7]）属于编造引用（§12.1 硬约束 4），
    这里忽略它并打 WARNING，交给评测环节去统计"幻觉引用率"。
    """
    citations: list[str] = []
    for match in _CITATION_RE.finditer(answer):
        number = int(match.group(1))
        if not 1 <= number <= len(used):
            logger.warning("答案出现越界引用 [%d]，参考资料只有 %d 条（疑似编造）", number, len(used))
            continue
        chunk = used[number - 1].chunk
        reference = f"{chunk.filename}#{chunk.index:04d}"
        if reference not in citations:  # 去重但保持出现顺序
            citations.append(reference)
    return citations


def _short(text: str, limit: int = 40) -> str:
    """把问题截断后再进日志（§18.2：长文本会淹没日志）。"""
    return text if len(text) <= limit else text[:limit] + "..."
