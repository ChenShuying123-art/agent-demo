"""工具基础层（spec-agent §19.5）。

职责边界：只定义工具的数据结构、注册表与装饰器。
不调用模型（llm）、不编排循环（agent / api）、不实现任何具体工具。

异常策略：本层**不捕获** handler 抛出的异常——工具失败是运行时行为，
由 agent loop 统一兜底并记录为该步 `ok=False`（§19.8）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# OpenAI tools 格式里固定的 type 值（§19.5 的 schemas 结构）
_TOOL_TYPE = "function"


@dataclass
class ToolResult:
    """一次工具执行的结果。

    Attributes:
        text: 给模型看的文本，回填前必须已按上限截断（§19.13）。
        data: 给前端看的结构化数据，可为空。
    """

    text: str
    data: dict | None = None


@dataclass
class Tool:
    """一个可被模型调用的工具。

    Attributes:
        name: 全局唯一名称，snake_case。
        description: 给模型看的用途说明（撰写规范见 §19.7）。
        parameters: 手写的 JSON Schema；不做自动生成，保证模型看到的就是这份 dict。
        handler: 执行函数，接收一个已解析的参数 dict，返回 ToolResult。
    """

    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], ToolResult]


class ToolRegistry:
    """工具注册表：按名称查找工具，并生成 OpenAI tools 格式的 schema。"""

    def __init__(self) -> None:
        # dict 保持插入顺序，schemas() 的输出顺序因此稳定、可逐字核对
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具。

        Args:
            tool: 待注册的工具。

        Raises:
            ValueError: 名称已存在。重名会让模型调用到错误的实现，
                因此直接失败，而不是覆盖或静默忽略。
        """
        if tool.name in self._tools:
            raise ValueError(f"工具名重复：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """按名称取工具。

        Args:
            name: 工具名。

        Returns:
            对应的 Tool。

        Raises:
            KeyError: 工具不存在。
        """
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"工具不存在：{name}") from None

    def names(self) -> list[str]:
        """返回全部工具名（按注册顺序）。"""
        return list(self._tools)

    def schemas(self) -> list[dict]:
        """生成 OpenAI tools 格式的 schema 列表，可直接交给 chat_with_tools。

        Returns:
            形如
            `{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}`
            的列表。不对 parameters 做裁剪或改写，保证模型看到的 schema
            与注册时手写的内容完全一致。
        """
        return [
            {
                "type": _TOOL_TYPE,
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]


def tool(
    name: str, description: str, parameters: dict
) -> Callable[[Callable[[dict], ToolResult]], Tool]:
    """装饰器：把一个函数登记成 Tool。

    被装饰的函数只接收一个参数 dict（模型给的 JSON 参数已由上层解析），
    这样不同工具的执行逻辑可以共用同一种调用方式：`tool.handler(args)`。

    Args:
        name: 全局唯一名称。
        description: 给模型看的用途说明。
        parameters: 手写的 JSON Schema。

    Returns:
        装饰器；作用后原函数名绑定到 Tool 实例。
    """

    def decorator(handler: Callable[[dict], ToolResult]) -> Tool:
        return Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    return decorator
