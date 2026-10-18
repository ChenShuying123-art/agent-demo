"""本地工具：日期时间（spec-agent §19.7）。

职责边界：只用标准库计算日期、星期与相对天数，不访问网络、不检索知识库。
为什么值得单独做成工具：模型最容易算错的就是"今天几号、星期几"，
这类事实在语料里查不到，必须由代码给出确定答案。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from kbqa.tools.base import ToolResult, tool

logger = logging.getLogger(__name__)

# Python 的 weekday() 从 0=星期一 开始，直接映射成中文可读文本
_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@tool(
    name="get_datetime",
    description=(
        "需要知道今天的日期、星期几或相对日期时使用。"
        "参数 date 支持 today、tomorrow 或 YYYY-MM-DD，默认 today；"
        "timezone 用 IANA 时区名（如 Asia/Shanghai），默认本机时区。"
        "不要用它回答知识库里已有的日期——那应该用 search_knowledge_base。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "目标日期：today、tomorrow 或 YYYY-MM-DD；默认 today",
            },
            "timezone": {
                "type": "string",
                "description": "IANA 时区名，如 Asia/Shanghai；默认使用本机时区",
            },
        },
        "required": [],
    },
)
def get_datetime(args: dict) -> ToolResult:
    """返回指定日期的日期、星期、查询时刻与相对天数。

    Args:
        args: 模型给的参数 dict，支持 date / timezone，均可省略。

    Returns:
        ToolResult；参数非法时返回说明文本（而不是抛异常），方便模型自行纠正。
    """
    started = time.perf_counter()
    raw_date = str(args.get("date") or "today").strip()
    timezone_name = str(args.get("timezone") or "").strip()

    now = _now(timezone_name)
    if now is None:
        text = f"无法识别的时区：{timezone_name}。请使用 IANA 时区名，如 Asia/Shanghai。"
        logger.warning(
            "工具执行 get_datetime 参数=%s 成功=False 原因=bad_timezone 耗时=%dms",
            _short_args(args),
            _elapsed_ms(started),
        )
        return ToolResult(text=text)

    today = now.date()
    target = _parse_date(raw_date, today)
    if target is None:
        text = f"无法识别的日期：{raw_date}。请使用 today、tomorrow 或 YYYY-MM-DD。"
        logger.warning(
            "工具执行 get_datetime 参数=%s 成功=False 原因=bad_date 耗时=%dms",
            _short_args(args),
            _elapsed_ms(started),
        )
        return ToolResult(text=text)

    delta_days = (target - today).days
    text = "\n".join(
        [
            f"日期：{target.isoformat()}",
            f"星期：{_WEEKDAYS[target.weekday()]}",
            f"时间：{now.strftime('%H:%M:%S')}（查询时刻）",
            f"相对今天：{_relative_label(delta_days)}",
        ]
    )

    logger.info(
        "工具执行 get_datetime 参数=%s 成功=True 结果长度=%d 耗时=%dms",
        _short_args(args),
        len(text),
        _elapsed_ms(started),
    )
    return ToolResult(
        text=text,
        data={
            "date": target.isoformat(),
            "weekday": _WEEKDAYS[target.weekday()],
            "time": now.strftime("%H:%M:%S"),
            "delta_days": delta_days,
        },
    )


def _now(timezone_name: str) -> datetime | None:
    """按 IANA 时区取当前时间；未指定时用本机时区。

    Args:
        timezone_name: IANA 时区名，空字符串表示本机时区。

    Returns:
        带时区的 datetime；时区名非法时返回 None。
    """
    if not timezone_name:
        return datetime.now().astimezone()
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        # 模型可能给出 "北京时间" 这类非 IANA 名称，直接告知它正确格式
        return None


def _parse_date(raw: str, today: date) -> date | None:
    """把模型给的 date 参数解析成 date；非法时返回 None。"""
    lowered = raw.lower()
    if lowered in {"", "today"}:
        return today
    if lowered == "tomorrow":
        return today + timedelta(days=1)
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _relative_label(delta_days: int) -> str:
    """把相对天数转成中文标签，保留正负号方便模型直接引用。"""
    if delta_days == 0:
        return "今天（+0 天）"
    if delta_days == 1:
        return "明天（+1 天）"
    if delta_days == -1:
        return "昨天（-1 天）"
    return f"{delta_days:+d} 天"


def _short_args(args: dict) -> str:
    """日志里只保留简短参数，避免长文本淹没日志（§18.2）。"""
    text = repr(args)
    return text if len(text) <= 80 else text[:80] + "..."


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
