"""MCP client：把 MCP server 暴露的工具并入同一个 ToolRegistry（spec-agent §19.12，T25）。

设计要点：
    - 默认关闭（MCP_ENABLED=false）；关闭时本模块不 import mcp，应用照旧启动。
    - 启动时对每个 server 做一次 tools/list，把工具包装成本地 Tool；
      名称加 `{server}.{tool}` 前缀，避免与本地工具撞名。
    - 单个 server 起不来只丢该批工具，其余工具与 `/api/agent/chat` 仍可用。
    - 工具调用每次开一个 stdio 会话（demo 取舍）：简单、隔离好；代价是握手开销。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from kbqa.config import Settings
from kbqa.tools.base import Tool, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

_CALL_TIMEOUT_SECONDS = 30.0


def register_mcp_tools(registry: ToolRegistry, settings: Settings) -> None:
    """按配置连接 MCP server 并注册工具。

    Args:
        registry: 已含本地工具的工具表。
        settings: 读取 mcp_enabled / mcp_servers / export_dir。

    Returns:
        None。任何 server 失败都只打 WARNING，不抛异常。
    """
    if not settings.mcp_enabled:
        logger.info("MCP 未启用（MCP_ENABLED=false），跳过")
        return

    specs = _server_specs(settings)
    if not specs:
        logger.warning("MCP_ENABLED=true 但 MCP_SERVERS 为空或格式非法，跳过")
        return

    for spec in specs:
        server_name = spec["name"]
        try:
            remote_tools = _list_tools_sync(settings, spec)
        except Exception as exc:  # noqa: BLE001 —— 失败隔离：只丢这一批工具
            logger.warning(
                "MCP server 启动失败 name=%s 原因=%s", server_name, _short(str(exc), 120)
            )
            continue

        registered = 0
        for remote in remote_tools:
            remote_name = getattr(remote, "name", "")
            if not remote_name:
                continue
            full_name = f"{server_name}.{remote_name}"
            parameters = (
                getattr(remote, "inputSchema", None)
                or getattr(remote, "input_schema", None)
                or {"type": "object", "properties": {}}
            )
            description = getattr(remote, "description", "") or f"MCP 工具 {remote_name}"
            try:
                registry.register(
                    Tool(
                        name=full_name,
                        description=description,
                        parameters=parameters,
                        handler=_make_handler(settings, spec, remote_name, full_name),
                    )
                )
            except ValueError:
                logger.warning("MCP 工具与已有工具撞名，跳过 name=%s", full_name)
                continue
            registered += 1

        logger.info(
            "MCP server 已接入 name=%s 工具数=%d 工具=%s",
            server_name,
            registered,
            [f"{server_name}.{getattr(t, 'name', '')}" for t in remote_tools],
        )


def _server_specs(settings: Settings) -> list[dict]:
    """解析 MCP_SERVERS JSON；非法配置只打 WARNING，不阻断应用。"""
    raw = settings.mcp_servers.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("MCP_SERVERS 不是合法 JSON：%s", _short(str(exc), 100))
        return []
    if not isinstance(data, list):
        logger.warning("MCP_SERVERS 必须是 JSON 数组")
        return []

    specs: list[dict] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("name") or not item.get("command"):
            logger.warning("MCP_SERVERS 条目缺少 name/command，已跳过：%s", item)
            continue
        args = item.get("args") or []
        specs.append(
            {
                "name": str(item["name"]),
                "command": str(item["command"]),
                "args": [str(arg) for arg in args] if isinstance(args, list) else [],
            }
        )
    return specs


def _list_tools_sync(settings: Settings, spec: dict) -> list[Any]:
    """同步入口：启动 server，initialize，然后 tools/list。"""
    return asyncio.run(_list_tools_async(settings, spec))


async def _list_tools_async(settings: Settings, spec: dict) -> list[Any]:
    ClientSession, StdioServerParameters, stdio_client = _mcp_imports()
    params = StdioServerParameters(
        command=spec["command"],
        args=spec["args"],
        env=_subprocess_env(settings),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return list(getattr(result, "tools", []) or [])


def _call_tool_sync(settings: Settings, spec: dict, tool_name: str, arguments: dict) -> str:
    """同步入口：每次调用开一个 stdio 会话，执行 tools/call，返回文本。"""
    return asyncio.run(_call_tool_async(settings, spec, tool_name, arguments))


async def _call_tool_async(
    settings: Settings, spec: dict, tool_name: str, arguments: dict
) -> str:
    ClientSession, StdioServerParameters, stdio_client = _mcp_imports()
    params = StdioServerParameters(
        command=spec["command"],
        args=spec["args"],
        env=_subprocess_env(settings),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=_CALL_TIMEOUT_SECONDS,
            )

    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) or "(MCP 工具没有返回文本)"


def _make_handler(settings: Settings, spec: dict, remote_name: str, full_name: str):
    """给每个 MCP 工具生成一个同步 handler。"""

    def handler(args: dict) -> ToolResult:
        started = time.perf_counter()
        try:
            text = _call_tool_sync(settings, spec, remote_name, args)
        except Exception as exc:  # noqa: BLE001 —— 外进程失败不能中断 loop
            logger.warning(
                "MCP 工具调用失败 name=%s 原因=%s", full_name, _short(str(exc), 120)
            )
            return ToolResult(text=f"MCP 工具调用失败：{exc}")
        logger.info(
            "工具执行 %s 成功=True 结果长度=%d 耗时=%dms",
            full_name,
            len(text),
            int((time.perf_counter() - started) * 1000),
        )
        return ToolResult(text=text)

    return handler


def _mcp_imports():
    """延迟 import：MCP_ENABLED=false 时进程内不会加载 mcp。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    return ClientSession, StdioServerParameters, stdio_client


def _subprocess_env(settings: Settings) -> dict[str, str]:
    """给子进程传环境变量；EXPORT_DIR 用绝对路径，避免工作目录不同导致写错地方。"""
    env = dict(os.environ)
    export_dir = settings.export_dir
    if not export_dir.is_absolute():
        export_dir = Path.cwd() / export_dir
    env["EXPORT_DIR"] = str(export_dir.resolve())
    return env


def _short(text: str, limit: int = 50) -> str:
    return text if len(text) <= limit else text[:limit] + "..."
