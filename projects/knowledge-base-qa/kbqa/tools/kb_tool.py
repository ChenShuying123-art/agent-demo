"""本地工具：知识库检索（spec-agent §19.7）。

职责边界：只把模型给的 query 转成一次**已有的**两阶段检索，
不重写召回/重排逻辑（直接复用 `RAGPipeline.retrieve`），也不组装提示词。
返回文本按 `used` 的顺序编号 `[1]..[n]`——编号必须与 prompts.format_context 一致，
否则模型回答里的 [n] 会指向错误的原文。
"""

from __future__ import annotations

import logging
import time

from kbqa.pipeline import RAGPipeline
from kbqa.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)

# 单条片段最多回填多少字：完整 chunk 可能 500 字，4 条就会把上下文撑爆
_SNIPPET_CHARS = 300
# 默认返回条数；调用方可以传 top_n 覆盖（上限 10，避免一次塞太多）
_DEFAULT_TOP_N = 4
_MAX_TOP_N = 10


def build_kb_tool(pipeline: RAGPipeline, max_chars: int = 2000) -> Tool:
    """构造知识库检索工具。

    为什么用工厂而不是模块级 Tool：工具需要 `RAGPipeline` 这个依赖，
    用工厂把依赖显式传进来，避免模块级全局变量（也方便测试时注入假 pipeline）。

    Args:
        pipeline: 已完成依赖注入的检索/问答编排对象。
        max_chars: 单次工具结果的最大字符数（通常传 settings.agent_tool_result_max_chars）。

    Returns:
        名为 `search_knowledge_base` 的 Tool。
    """

    @tool(
        name="search_knowledge_base",
        description=(
            "当问题需要依据知识库中的文档内容作答时使用。"
            "参数 query 是检索问题，top_n 是返回条数（1-10，默认 4）。"
            "不要用它查实时信息（日期、天气、网页）——那些应该用对应的专门工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要检索的问题或关键词",
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回条数，1-10，默认 4",
                },
            },
            "required": ["query"],
        },
    )
    def search_knowledge_base(args: dict) -> ToolResult:
        """检索知识库并按 rerank 顺序返回带编号的片段。

        Args:
            args: 模型给的参数 dict；`query` 必填，`top_n` 可选。

        Returns:
            ToolResult；空库或无命中时返回"未检索到"文本，不抛异常。
        """
        started = time.perf_counter()
        query = str(args.get("query") or "").strip()
        top_n = _parse_top_n(args.get("top_n"))

        if not query:
            text = "查询内容不能为空。"
            logger.warning(
                "工具执行 search_knowledge_base 参数=%s 成功=False 原因=empty_query 耗时=%dms",
                _short_args(args),
                _elapsed_ms(started),
            )
            return ToolResult(text=text, data={"query": "", "results": []})

        # 复用已有检索：召回 + 重排的取舍都在 pipeline 里，工具层不重复实现
        _, used = pipeline.retrieve(query, None)
        selected = used[:top_n]

        if not selected:
            text = "未检索到相关资料。"
            logger.info(
                "工具执行 search_knowledge_base 参数=%s 成功=True 命中=0 结果长度=%d 耗时=%dms",
                _short_args(args),
                len(text),
                _elapsed_ms(started),
            )
            return ToolResult(text=text, data={"query": query, "results": []})

        blocks = []
        for number, item in enumerate(selected, start=1):
            chunk = item.chunk
            snippet = chunk.text.strip()
            if len(snippet) > _SNIPPET_CHARS:
                snippet = snippet[:_SNIPPET_CHARS] + "..."
            # 编号顺序 = used 顺序（即 rerank 顺序），与 format_context 完全一致
            blocks.append(
                f"[{number}] {chunk.filename}#{chunk.index:04d}"
                f"（分数={item.rerank_score:.4f}）\n{snippet}"
            )

        text = _truncate("\n\n".join(blocks), max_chars)
        logger.info(
            "工具执行 search_knowledge_base 参数=%s 成功=True 命中=%d 结果长度=%d 耗时=%dms",
            _short_args(args),
            len(selected),
            len(text),
            _elapsed_ms(started),
        )
        return ToolResult(
            text=text,
            data={
                "query": query,
                "results": [
                    {
                        "filename": item.chunk.filename,
                        "chunk_index": item.chunk.index,
                        "score": round(item.rerank_score, 4),
                    }
                    for item in selected
                ],
            },
        )

    return search_knowledge_base


def _parse_top_n(raw: object) -> int:
    """把模型给的 top_n 收敛到 1-10；非法值回退默认值。"""
    try:
        value = int(raw) if raw is not None else _DEFAULT_TOP_N
    except (TypeError, ValueError):
        value = _DEFAULT_TOP_N
    return max(1, min(value, _MAX_TOP_N))


def _truncate(text: str, limit: int) -> str:
    """按字符数截断最终结果，避免回填后撑爆上下文（§19.13）。

    注意省略号也算长度：否则 text[:limit] + "..." 会超出上限 3 个字符。
    """
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _short_args(args: dict) -> str:
    """日志里只保留简短参数，避免长 query 淹没日志（§18.2）。"""
    text = repr(args)
    return text if len(text) <= 80 else text[:80] + "..."


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
