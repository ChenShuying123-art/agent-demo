"""工具层（spec-agent §19.5）。

对外只暴露基础类型与注册表；具体工具在后续任务中分别实现
（datetime_tool / kb_tool / web_search / weather），本文件不做任何工具注册。
"""

from kbqa.tools.base import Tool, ToolRegistry, ToolResult, tool

__all__ = ["Tool", "ToolRegistry", "ToolResult", "tool"]
