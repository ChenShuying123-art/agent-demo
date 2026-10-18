"""外网工具：天气 / 生活服务（spec-agent §19.7，批次 B，T23）。

职责边界：只回答"某城市未来几天的天气"，不做地图/定位联动。
失败返回错误文本，不抛异常；超时固定 10s。

真实接口尚未定稿（§19.16）：采用可配置 endpoint 的最小约定——
    GET {WEATHER_ENDPOINT}?city=...&days=...
    Header: Authorization: Bearer {WEATHER_API_KEY}
    响应：{"city": "...", "days": [{"date","weather","temp"}]} 或 {"data": [...]}
未配置 endpoint/key 时返回明确标注的 [mock] 结果。
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import httpx

from kbqa.config import Settings
from kbqa.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
_MAX_DAYS = 7

# mock 模式认识的城市；其它城市按"不存在"处理，便于验证错误路径
_MOCK_CITIES = {
    "北京": ("晴", "18~25°C"),
    "上海": ("多云", "20~27°C"),
    "广州": ("阵雨", "24~31°C"),
    "深圳": ("多云", "25~31°C"),
    "杭州": ("小雨", "19~24°C"),
    "成都": ("阴", "17~23°C"),
    "武汉": ("晴", "21~28°C"),
    "西安": ("晴", "15~24°C"),
    "南京": ("多云", "19~26°C"),
    "重庆": ("阴", "22~29°C"),
}


def build_weather_tool(settings: Settings) -> Tool:
    """构造天气工具。

    Args:
        settings: 读取 weather_endpoint / weather_api_key；留空则返回 mock。

    Returns:
        名为 `get_weather` 的 Tool。
    """

    @tool(
        name="get_weather",
        description=(
            "当用户询问某个城市当前或未来几天的天气时使用。"
            "参数 city 是城市名（如 北京、上海），days 是预报天数（1-7，默认 1）。"
            "不要用它查历史天气或气候统计——那些应说明资料不足。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名，如 北京"},
                "days": {"type": "integer", "description": "预报天数，1-7，默认 1"},
            },
            "required": ["city"],
        },
    )
    def get_weather(args: dict) -> ToolResult:
        started = time.perf_counter()
        city = str(args.get("city") or "").strip()
        days = _parse_days(args.get("days"))

        if not city:
            text = "城市不能为空。"
            _log("", days, "mock", False, text, started)
            return ToolResult(text=text, data={"city": "", "days": []})

        endpoint = settings.weather_endpoint.strip()
        api_key = settings.weather_api_key.strip()

        if not endpoint or not api_key:
            if city not in _MOCK_CITIES:
                text = f"未找到城市：{city} 的天气信息。"
                _log(city, days, "mock", False, text, started)
                return ToolResult(text=text, data={"city": city, "days": []})
            forecast = _mock_forecast(city, days)
            text = _format(city, forecast, source="mock")
            logger.warning("get_weather 未配置 endpoint/key，返回 mock 结果（真实联调状态：未联调）")
            _log(city, days, "mock", True, text, started)
            return ToolResult(text=text, data={"city": city, "days": forecast})

        try:
            resp = httpx.get(
                endpoint,
                params={"city": city, "days": days},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            forecast = _parse_response(resp.json(), days)
        except Exception as exc:  # noqa: BLE001 —— 外网失败降级为文本
            text = f"get_weather 调用失败：{exc}"
            logger.warning(
                "get_weather 调用失败 city=%s 原因=%s", _short(city), _short(str(exc), 120)
            )
            _log(city, days, "real", False, text, started)
            return ToolResult(text=text, data={"city": city, "days": []})

        if not forecast:
            text = f"未找到城市：{city} 的天气信息。"
            _log(city, days, "real", False, text, started)
            return ToolResult(text=text, data={"city": city, "days": []})

        text = _format(city, forecast, source="real")
        _log(city, days, "real", True, text, started)
        return ToolResult(text=text, data={"city": city, "days": forecast})

    return get_weather


def _parse_days(raw: object) -> int:
    try:
        value = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        value = 1
    return max(1, min(value, _MAX_DAYS))


def _mock_forecast(city: str, days: int) -> list[dict]:
    weather, temp = _MOCK_CITIES[city]
    today = date.today()
    return [
        {
            "date": (today + timedelta(days=offset)).isoformat(),
            "weather": weather,
            "temp": temp,
        }
        for offset in range(days)
    ]


def _parse_response(payload: object, days: int) -> list[dict]:
    """从可配置接口响应里抽出日期/天气/温度，最多 days 条。"""
    if not isinstance(payload, dict):
        return []
    items = payload.get("days") or payload.get("forecast") or payload.get("data") or []
    if isinstance(payload, dict) and not items and payload.get("weather"):
        items = [payload]
    if not isinstance(items, list):
        return []

    forecast: list[dict] = []
    for item in items[:days]:
        if not isinstance(item, dict):
            continue
        forecast.append(
            {
                "date": str(item.get("date") or item.get("day") or ""),
                "weather": str(item.get("weather") or item.get("text") or item.get("condition") or ""),
                "temp": str(
                    item.get("temp")
                    or item.get("temperature")
                    or f"{item.get('temp_min', '')}~{item.get('temp_max', '')}"
                ),
            }
        )
    return forecast


def _format(city: str, forecast: list[dict], source: str) -> str:
    """输出：城市 + 每一天的日期/天气/温度；mock 时明确标注。"""
    suffix = "（mock）" if source == "mock" else ""
    lines = [f"城市：{city}{suffix}"]
    for item in forecast:
        lines.append(
            f"日期：{item.get('date') or '未知'}\n"
            f"天气：{item.get('weather') or '未知'}\n"
            f"温度：{item.get('temp') or '未知'}"
        )
    return "\n\n".join(lines)


def _short(text: str, limit: int = 50) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _log(city: str, days: int, source: str, ok: bool, text: str, started: float) -> None:
    """统一打点；绝不打印 api_key（§19.13）。"""
    logger.info(
        "工具执行 get_weather 参数=%s days=%d 来源=%s 成功=%s 结果长度=%d 耗时=%dms",
        _short(city),
        days,
        source,
        ok,
        len(text),
        int((time.perf_counter() - started) * 1000),
    )
