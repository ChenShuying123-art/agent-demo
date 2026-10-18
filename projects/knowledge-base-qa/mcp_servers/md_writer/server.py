"""MCP server：把 markdown 写入受限目录（spec-agent §19.12，T24）。

依赖：官方 MCP Python SDK（本项目验证版本 mcp 2.3.0）。
    pip install -r requirements-mcp.txt

启动（stdio）：python mcp_servers/md_writer/server.py
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

# 写入目录由服务端固定：模型只能给文件名，不能指定路径（§19.12）
_ROOT = Path(__file__).resolve().parents[2]
_EXPORT_DIR = Path(os.getenv("EXPORT_DIR", "data/exports"))
if not _EXPORT_DIR.is_absolute():
    _EXPORT_DIR = _ROOT / _EXPORT_DIR

_MAX_CONTENT_CHARS = 200_000

server = MCPServer("md_writer")


@server.tool(
    name="write_markdown",
    description=(
        "把一段 markdown 内容写入服务器指定目录。"
        "filename 只能是文件名（如 notes.md），不能包含路径；content 是文件正文。"
        "用于保存答案、报告或笔记。"
    ),
)
def write_markdown(filename: str, content: str) -> str:
    """安全地写入一个 markdown 文件。

    Args:
        filename: 纯文件名（basename），如 `answer.md`。
        content: 文件正文。

    Returns:
        成功时返回落盘绝对路径；失败时返回以"写入失败："开头的说明文本。
    """
    name = (filename or "").strip()
    if not name:
        return "写入失败：filename 不能为空。"

    # 拒绝绝对路径、盘符、.. 与任何目录成分：目录由服务端固定
    candidate = Path(name)
    if candidate.is_absolute() or candidate.name != name or ".." in candidate.parts:
        return "写入失败：filename 只能是纯文件名，不能包含路径或 ..。"

    if len(content or "") > _MAX_CONTENT_CHARS:
        return f"写入失败：content 超过上限 {_MAX_CONTENT_CHARS} 字符。"

    try:
        _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        target = _EXPORT_DIR / name
        # 双保险：解析后仍必须落在导出目录内
        target.resolve().relative_to(_EXPORT_DIR.resolve())
        target.write_text(content or "", encoding="utf-8")
    except (OSError, ValueError) as exc:
        return f"写入失败：{exc}"

    return f"已写入：{target.resolve()}"


if __name__ == "__main__":
    server.run()
