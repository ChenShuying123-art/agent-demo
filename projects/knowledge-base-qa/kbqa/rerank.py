"""Rerank 重排模块（spec §7.7）。

职责边界：只对"召回候选"做精排（Cross-encoder 打分重排）。
不负责召回（属于 vectorstore），也不负责生成（属于 llm）。

坑 1（§4.2）：Rerank 的地址与协议跟对话、Embedding 都不同。
    对话 / Embedding 走 OpenAI 兼容的 `compatible-mode/v1`；
    Rerank 走百炼自有协议 `api/v1/services/rerank/text-rerank/text-rerank`。
    把它当成 OpenAI 接口去拼路径，必然 404——这是本项目最容易踩的一个坑。

⚠️ 实测与文档不一致（重要，T10/T14 需同步）：
    spec §7.7 / §4.2 把请求体写成扁平结构 `{model, query, documents[], top_n}`，
    但真实接口要求**嵌套**结构：
        {"model": ..., "input": {"query": ..., "documents": [...]}, "parameters": {"top_n": N}}
    用扁平结构调用会返回 400 `InvalidParameter: Field required: input.query & input.documents`。
    本实现按真实接口为准（已实测通过）。

三个关键实现细节：
  1. 请求里的 `documents` 是**纯文本数组**（不是 chunk 对象，也不是 {text} 包装）；
     响应里的 `index` 是"输入 documents 数组的下标"，必须用它映射回原来的 SearchResult，
     才能拿回 chunk 元数据（doc_id / filename / 原文位置）。
  2. `relevance_score` 与召回阶段的 cosine 分数**尺度不同、不可比较**，
     所以 RerankResult 单独用一个字段存，绝不混着排序。
  3. 必须记录 `original_rank`——这是本项目最重要的可观测数据之一，
     能直观看到"重排到底把哪些内容捞上来了"。
"""

from __future__ import annotations

import logging
import time
from typing import Protocol, runtime_checkable

import httpx

from kbqa.config import Settings
from kbqa.models import RerankResult, SearchResult

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30.0


@runtime_checkable
class RerankProvider(Protocol):
    """重排提供方接口（§7.7）。换实现只改这里，业务代码不动（NFR-2）。"""

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        top_n: int,
    ) -> list[RerankResult]:
        """对召回候选重新打分排序，返回前 top_n 条。"""
        ...


class DashScopeRerank:
    """百炼（DashScope）实现：自有协议，用 httpx 直接 POST。"""

    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.rerank_endpoint
        self._model = settings.rerank_model
        self._api_key = settings.dashscope_api_key

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        top_n: int,
    ) -> list[RerankResult]:
        """对候选做重排。

        Args:
            query: 用户问题原文。
            candidates: 召回阶段的候选（已按 cosine 降序）。
            top_n: 重排后保留的条数。

        Returns:
            重排后的 RerankResult 列表（按新排名排列）。
            调用失败或参数为空时不抛异常，返回降级结果（每条 degraded=True）。

        Raises:
            无。任何外部调用失败都会被降级吸收，保证问答链路不中断（§7.7 关键细节 5）。
        """
        if not candidates or top_n <= 0:
            return []

        body = {
            "model": self._model,
            # 真实接口要求 query / documents 嵌在 input 下（见模块顶部说明）
            "input": {
                "query": query,
                # documents 是纯文本数组（§7.7 关键细节 1）
                "documents": [c.chunk.text for c in candidates],
            },
            "parameters": {"top_n": min(top_n, len(candidates))},
        }
        started = time.perf_counter()

        try:
            resp = httpx.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            raw_results = resp.json()["output"]["results"]
        except Exception as exc:  # noqa: BLE001 —— 网络/协议/鉴权任何问题都走降级
            logger.warning("rerank 调用失败，已降级为直接截断前 %d 条：%s", top_n, exc)
            return self._fallback(candidates, top_n)

        results: list[RerankResult] = []
        for new_rank, item in enumerate(raw_results):
            # index 是"输入数组的下标"，用它映射回原候选（§7.7 关键细节 2）
            original_rank = int(item["index"])
            results.append(
                RerankResult(
                    chunk=candidates[original_rank].chunk,
                    rerank_score=float(item["relevance_score"]),
                    original_rank=original_rank,
                    new_rank=new_rank,
                    degraded=False,
                )
            )

        changed = sum(1 for r in results if r.original_rank != r.new_rank)
        logger.info(
            "重排完成 输入=%d 输出=%d 排名变化=%d 耗时=%dms",
            len(candidates),
            len(results),
            changed,
            int((time.perf_counter() - started) * 1000),
        )
        logger.debug("重排细节 query=%s top_n=%d", _short(query), top_n)
        return results

    @staticmethod
    def _fallback(candidates: list[SearchResult], top_n: int) -> list[RerankResult]:
        """降级：直接取召回结果的前 top_n 条。

        注意此时 `rerank_score` 里装的是**召回阶段的 cosine 分数**，
        与真正的 relevance_score 不同尺度——所以每一条都标了 `degraded=True`；
        调用方看到这个标记，就不该把它跟正常重排的分数放在一起比较或排序。
        """
        return [
            RerankResult(
                chunk=c.chunk,
                rerank_score=c.score,
                original_rank=c.rank,
                new_rank=i,
                degraded=True,
            )
            for i, c in enumerate(candidates[:top_n])
        ]


def _short(text: str, limit: int = 50) -> str:
    """query 截断到 50 字符再进日志（§18.2：长文本会淹没日志）。"""
    return text if len(text) <= limit else text[:limit] + "..."


def get_reranker(settings: Settings) -> RerankProvider | None:
    """工厂函数：按配置返回重排实现；`rerank_enabled=False` 时返回 None（§7.7）。

    返回 None 表示"本次不做重排"，调用方据此跳过重排、直接使用召回结果。
    """
    if not settings.rerank_enabled:
        logger.info("rerank_enabled=False，本次不启用重排")
        return None
    return DashScopeRerank(settings)
