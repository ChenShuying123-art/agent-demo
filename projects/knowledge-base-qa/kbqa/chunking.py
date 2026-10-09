"""文本切分模块（spec §7.4）。

职责边界：只把一段纯文本切成带位置信息的片段。
不做向量化，也不构造 Chunk 对象——那需要 doc_id / filename，属于编排层 pipeline 的职责。

切分策略（MVP 自实现）：
  1. 先找出所有"候选切点"：
     强边界 = md 标题行首、空行后的段落起点；
     弱边界 = 换行处、句末标点之后。
  2. 以 chunk_size 为上限，优先在强边界切，其次弱边界，实在没有就硬切。
  3. 相邻 chunk 之间回退 chunk_overlap 个字符，避免答案正好跨在边界上被截断。
  4. 每个 chunk 记录 (start, end)，并保证 text[start:end] == chunk_text，供引用定位。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# md 标题行：行首最多 3 个空格，1~6 个 #，后接一个空白字符
_HEADING_RE = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]")
# 空行：段落之间的分隔
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
# 句末标点（中英文）
_SENTENCE_END = "。！？!?."


def _candidate_cuts(text: str) -> tuple[list[int], list[int]]:
    """算出两组候选切点位置：(强边界, 弱边界)，均已排序。

    强边界 = 标题行首、空行后的段落起点：语义上最该断开的地方。
    弱边界 = 换行后、句末标点后：次优，但至少不会把句子拦腰截断。

    为什么把 md 标题当强边界：标题代表新章节，chunk 跨章节会让检索到的片段语义混杂。
    """
    strong: set[int] = set()
    for match in _HEADING_RE.finditer(text):
        strong.add(match.start())
    for match in _BLANK_LINE_RE.finditer(text):
        strong.add(match.end())

    weak: set[int] = set()
    for i, ch in enumerate(text):
        if ch == "\n" or ch in _SENTENCE_END:
            weak.add(i + 1)

    # 0 与 len(text) 不是有效切点；强边界已覆盖的位置也不必再留在弱边界里
    for pos in (0, len(text)):
        strong.discard(pos)
        weak.discard(pos)
    weak -= strong

    return sorted(strong), sorted(weak)


def _pick_largest(cuts: list[int], lo: int, hi: int) -> int | None:
    """在区间 (lo, hi] 内取最大的切点；没有则返回 None。

    为什么要取"最大"而不是"第一个"：让当前 chunk 尽量装满，减少 chunk 总数。
    """
    best: int | None = None
    for pos in cuts:
        if pos > hi:
            break  # cuts 升序，后面只会更大
        if pos > lo:
            best = pos
    return best


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[int, int, str]]:
    """把文本切分为若干 chunk。

    Args:
        text: 原文（完整字符串）。
        chunk_size: 单个 chunk 的最大字符数。
        chunk_overlap: 相邻 chunk 的重叠字符数。

    Returns:
        [(start, end, chunk_text), ...]，满足：
          - text[start:end] == chunk_text（位置不错位，引用定位才准）；
          - 每个 chunk 长度 <= chunk_size；
          - 相邻两项的重叠恰为 chunk_overlap 个字符。

    Raises:
        无。空文本返回空列表。
    """
    n = len(text)
    if n == 0:
        return []

    # overlap 必须严格小于 chunk_size：否则每切一刀位置都推不动，会死循环
    if chunk_overlap >= chunk_size:
        logger.warning(
            "chunk_overlap(%d) >= chunk_size(%d)，已收窄为 %d",
            chunk_overlap,
            chunk_size,
            chunk_size - 1,
        )
        chunk_overlap = max(0, chunk_size - 1)

    strong, weak = _candidate_cuts(text)

    chunks: list[tuple[int, int, str]] = []
    start = 0
    while True:
        limit = start + chunk_size
        if limit >= n:
            end = n  # 剩余内容不足一块：直接收尾
        else:
            # 下界取 start + chunk_overlap：保证本块比 overlap 长，
            # 这样下一块回退 overlap 后仍能前进，且重叠是完整的 chunk_overlap
            end = _pick_largest(strong, start + chunk_overlap, limit)
            if end is None:
                end = _pick_largest(weak, start + chunk_overlap, limit)
            if end is None:
                end = limit  # 附近没有任何边界：只能硬切

        chunks.append((start, end, text[start:end]))
        if end >= n:
            break
        start = end - chunk_overlap  # 回退 overlap 个字符，形成相邻重叠

    logger.info(
        "文本切分完成 字符数=%d chunk数=%d chunk_size=%d overlap=%d",
        n,
        len(chunks),
        chunk_size,
        chunk_overlap,
    )
    for i, (s, e, _) in enumerate(chunks):
        logger.debug("chunk[%d] start=%d end=%d 长度=%d", i, s, e, e - s)

    return chunks
