"""外网工具：网页搜索（spec-agent §19.7，批次 B，T22）。

职责边界：只把 query 变成"标题 + URL + 摘要"的短文本给模型。
不做重试队列、不做缓存；失败返回错误文本，不抛异常。

真实接口尚未定稿（§19.16）：这里采用可配置 endpoint 的最小约定——
    GET {WEB_SEARCH_ENDPOINT}?q=...&count=...
    Header: Authorization: Bearer {WEB_SEARCH_API_KEY}
    响应：{"references"|"results"|"data": [{"title","url","snippet"}]}
未配置 endpoint/key 时返回明确标注的 [mock] 结果，便于先跑通链路。
"""

from __future__ import annotations

import logging
import time

import httpx

from kbqa.config import Settings
from kbqa.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
_MAX_RESULTS = 5
_SNIPPET_CHARS = 200


def build_web_search_tool(settings: Settings) -> Tool:
    """构造网页搜索工具。

    Args:
        settings: 读取 web_search_endpoint / web_search_api_key；留空则返回 mock。

    Returns:
        名为 `web_search` 的 Tool。
    """

    @tool(
        name="web_search",
        description=(
            "当需要知识库之外的最新网页信息时使用。"
            "参数 query 是搜索词，count 是返回条数（1-5，默认 3）。"
            "不要用它查知识库已有内容——那用 search_knowledge_base；"
            "也不要用它查日期时间——那用 get_datetime。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索词"},
                "count": {"type": "integer", "description": "返回条数，1-5，默认 3"},
            },
            "required": ["query"],
        },
    )
    def web_search(args: dict) -> ToolResult:
        started = time.perf_counter()
        query = str(args.get("query") or "").strip()
        count = _parse_count(args.get("count"))

        if not query:
            text = "搜索词不能为空。"
            _log(query, count, "mock", False, text, started)
            return ToolResult(text=text, data={"query": "", "results": []})

        endpoint = settings.web_search_endpoint.strip()
        api_key = settings.web_search_api_key.strip()

        if not endpoint or not api_key:
            # 批次 B 允许 mock-first：明确标注，避免把假数据当成真实联调结果
            results = _mock_results(query, count)
            text = _format_results(results)
            logger.warning(
                "web_search 未配置 endpoint/key，返回 mock 结果（真实联调状态：未联调）"
            )
            _log(query, count, "mock", True, text, started)
            return ToolResult(text=text, data={"query": query, "results": results})

        try:
            resp = httpx.get(
                endpoint,
                params={"q": query, "count": count},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            results = _parse_response(resp.json(), count)
        except Exception as exc:  # noqa: BLE001 —— 外网失败降级为文本结果
            text = f"web_search 调用失败：{exc}"
            logger.warning("web_search 调用失败 query=%s 原因=%s", _short(query), _short(str(exc), 120))
            _log(query, count, "real", False, text, started)
            return ToolResult(text=text, data={"query": query, "results": []})

        if not results:
            text = "web_search 未检索到结果。"
            _log(query, count, "real", True, text, started)
            return ToolResult(text=text, data={"query": query, "results": []})

        text = _format_results(results)
        _log(query, count, "real", True, text, started)
        return ToolResult(text=text, data={"query": query, "results": results})

    return web_search


def _parse_count(raw: object) -> int:
    """把 count 收敛到 1-5；非法值回退 3。"""
    try:
        value = int(raw) if raw is not None else 3
    except (TypeError, ValueError):
        value = 3
    return max(1, min(value, _MAX_RESULTS))


def _parse_response(payload: object, count: int) -> list[dict]:
    """从可配置接口的响应里抽出前 count 条，统一成 title/url/snippet。"""
    if not isinstance(payload, dict):
        return []
    items = payload.get("references") or payload.get("results") or payload.get("data") or []
    if not isinstance(items, list):
        return []

    results: list[dict] = []
    for item in items[:count]:
        if not isinstance(item, dict):
            continue
        snippet = (
            item.get("snippet")
            or item.get("summary")
            or item.get("abstract")
            or item.get("content")
            or ""
        )
        results.append(
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or item.get("link") or ""),
                "snippet": _clip(str(snippet), _SNIPPET_CHARS),
            }
        )
    return results


def _mock_results(query: str, count: int) -> list[dict]:
    """未配置真实接口时的确定性 mock，输出里明确标注 [mock]。"""
    return [
        {
            "title": f"[mock] {query} 的搜索结果 {index}",
            "url": f"https://example.com/mock/web_search/{index}?q={query}",
            "snippet": (
                f"[mock] 这是未配置百度搜索 API 时返回的示例摘要（第 {index} 条）。"
                "接入真实 endpoint 后，这里会替换为网页标题、URL 与不超过 200 字的摘要。"
            )[:_SNIPPET_CHARS],
        }
        for index in range(1, count + 1)
    ]


def _format_results(results: list[dict]) -> str:
    """把结果压成模型易读的编号文本。"""
    blocks = [
        f"[{index}] {item['title']}\nURL: {item['url']}\n摘要: {item['snippet']}"
        for index, item in enumerate(results, start=1)
    ]
    return "\n\n".join(blocks)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _short(text: str, limit: int = 50) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _log(
    query: str,
    count: int,
    source: str,
    ok: bool,
    text: str,
    started: float,
) -> None:
    """统一打点：query、条数、来源（mock/real）、成功失败、结果长度、耗时。

    注意：绝不打印 api_key（§19.13）。
    """
    logger.info(
        "工具执行 web_search 参数=%s count=%d 来源=%s 成功=%s 结果长度=%d 耗时=%dms",
        _short(query),
        count,
        source,
        ok,
        len(text),
        int((time.perf_counter() - started) * 1000),
    )
