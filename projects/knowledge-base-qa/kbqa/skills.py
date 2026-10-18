"""Skill 加载（spec-agent §19.11，T26）。

一个 skill = 一段提示词正文 + 一组允许使用的工具名。
加载策略是渐进披露：
    1. 启动只读 front-matter，把 name + description 注入 system prompt；
    2. 需要时由模型调用 load_skill（或用户显式指定）；
    3. 加载后正文进 system prompt，并把工具集收窄到该 skill 的 tools。

硬约束：tools 只能收窄已注册工具，不能新增；SKILL.md 只写"做什么/怎么回答"，不放代码。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

LOAD_SKILL_NAME = "load_skill"

# 给模型看的 load_skill 工具 schema；agent loop 会特殊处理这个调用
LOAD_SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": LOAD_SKILL_NAME,
        "description": (
            "当用户的问题符合某个可用 skill 时，加载该 skill 的正文与工具集。"
            "参数 name 必须是可用 skill 列表中的名称。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "skill 名称"},
            },
            "required": ["name"],
        },
    },
}


@dataclass
class Skill:
    """一个已加载的 skill。"""

    name: str
    description: str
    tools: list[str]  # 空列表表示继承全部工具
    body: str
    path: Path


class SkillLoader:
    """从目录读取 SKILL.md，提供按名查找与清单。"""

    def __init__(self, skills_dir: Path) -> None:
        self._dir = skills_dir
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> None:
        """扫描 `{skills_dir}/*/SKILL.md`；非法文件只打 WARNING 并跳过。"""
        self._skills = {}
        if not self._dir.is_dir():
            logger.warning("skill 目录不存在，跳过 skills_dir=%s", self._dir)
            return

        for path in sorted(self._dir.glob("*/SKILL.md")):
            try:
                skill = _parse_skill(path)
            except ValueError as exc:
                logger.warning("skill 解析失败 path=%s 原因=%s", path, exc)
                continue
            if skill.name in self._skills:
                logger.warning("skill 名称重复，跳过 name=%s path=%s", skill.name, path)
                continue
            self._skills[skill.name] = skill

        logger.info("skill 加载完成 数量=%d 名称=%s", len(self._skills), list(self._skills))

    def get(self, name: str) -> Skill:
        """按名称取 skill。

        Raises:
            ValueError: skill 不存在。
        """
        skill = self._skills.get(name)
        if skill is None:
            raise ValueError(f"未知的 skill：{name}")
        return skill

    def names(self) -> list[str]:
        """返回全部 skill 名（按加载顺序）。"""
        return list(self._skills)

    def summaries(self) -> list[Skill]:
        """返回全部 skill，供 API 列 name + description。"""
        return list(self._skills.values())


def _parse_skill(path: Path) -> Skill:
    """解析 `---` 包裹的 front-matter 与正文。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("缺少 front-matter（文件必须以 --- 开头）")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("front-matter 未闭合")

    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip()

    name = meta.get("name") or path.parent.name
    description = meta.get("description", "").strip()
    body = parts[2].strip()
    if not description:
        raise ValueError("缺少 description")
    if not body:
        raise ValueError("正文为空")

    return Skill(
        name=name,
        description=description,
        tools=_parse_tools(meta.get("tools", "")),
        body=body,
        path=path,
    )


def _parse_tools(raw: str) -> list[str]:
    """解析 `[a, b]` 形式的工具列表；空表示继承全部。"""
    value = raw.strip()
    if not value or value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip().strip("'\"") for item in value.split(",") if item.strip()]
