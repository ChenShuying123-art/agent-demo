"""手写 agent loop（spec-agent §19.8）。

职责边界：只负责"调模型 → 执行工具 → 回填 → 判断是否继续"这个循环。
HTTP 路由在 api/routes.py，MCP 在 mcp_client.py；本模块只通过 ToolRegistry 调度工具，
并在 T26 之后支持 skill（显式指定 + load_skill 自动加载）。

两个层次不要混淆：
    - 外层 while：还要不要再问模型一轮（轮数未知，且必须有上限）；
    - 内层 for：这一轮模型一次点了几把工具（并行 tool_calls）。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Protocol

from kbqa.config import Settings
from kbqa.llm import LLMProvider
from kbqa.models import AgentRun, AgentStep, ChatResult, ToolCall
from kbqa.skills import LOAD_SKILL_NAME, LOAD_SKILL_SCHEMA, Skill, SkillLoader
from kbqa.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# 通用人格 + 工具使用规则。skill 正文要到 T26 才会拼进来。
_SYSTEM_PROMPT = """你是一个可以使用工具的问答助手。

- 需要日期、时间或知识库内容时，优先调用合适的工具，不要凭记忆猜测。
- 工具结果是你的依据；最终回答不要编造工具没有返回的信息。
- 如果工具报错或没有结果，如实说明，并尝试换一种方式（换工具或直接回答）。
"""


class AgentRunner:
    """手写 agent loop：模型自主决定何时调用哪个工具。"""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        llm: LLMProvider,
        skills: SkillLoader | None = None,
    ) -> None:
        """注入 loop 所需的依赖。

        Args:
            settings: 全局配置（agent_max_steps / agent_tool_result_max_chars /
                skill_auto_select）。
            registry: 已注册好工具的工具表。
            llm: 支持 chat_with_tools 的模型实现。
            skills: skill 加载器；None 表示不启用 skill。
        """
        self._settings = settings
        self._registry = registry
        self._llm = llm
        self._skills = skills

    def run(
        self,
        question: str,
        skill: str | None = None,
        history: list[dict] | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> AgentRun:
        """执行一次完整的 agent 对话。

        Args:
            question: 用户问题。
            skill: 显式指定 skill；None 表示自动（由模型经 load_skill 选择）。
            history: 可选的历史消息（按 OpenAI messages 格式），插在 system 之后。
            on_event: 可选的流式事件回调（T27）；收到 step_start / tool_call / tool_result。
                回调抛异常不会影响主循环。

        Returns:
            AgentRun：最终答案、全部工具轨迹、停止原因与耗时。

        Raises:
            ValueError: 指定的 skill 不存在。
            LLMError: 模型调用失败（工具失败不会抛出，会记成 ok=False 的步骤）。
        """
        active_skill = self._resolve_skill(skill)
        auto_skills = self._auto_skills(active_skill)

        started = time.perf_counter()
        max_steps = self._settings.agent_max_steps
        max_chars = self._settings.agent_tool_result_max_chars
        base_schemas = self._registry.schemas()
        messages = _build_initial_messages(
            question, history, self._system_prompt(active_skill, auto_skills)
        )

        # 显式 skill 直接收窄工具；自动模式先开放全部工具 + load_skill
        allowed_tools = set(active_skill.tools) if active_skill and active_skill.tools else None
        load_skill_available = bool(auto_skills) and active_skill is None
        schemas = _filter_schemas(base_schemas, allowed_tools, load_skill_available)

        steps: list[AgentStep] = []
        rounds = 0
        tool_calls_count = 0
        last_content: str | None = None
        stop_reason = "max_steps"
        # 重复调用检测：同一工具 + 同一参数连续出现时提醒模型换策略
        last_signature: tuple[str, str] | None = None
        repeat_count = 0

        logger.info(
            "agent 开始 question=%s skill=%s 工具数=%d max_steps=%d",
            _short(question),
            active_skill.name if active_skill else "自动",
            len(schemas),
            max_steps,
        )

        while rounds < max_steps:
            rounds += 1
            _emit(on_event, {"event": "step_start", "round": rounds})
            # 每轮都按当前 skill 重新计算工具集：load_skill 可能刚刚收窄了它
            schemas = _filter_schemas(base_schemas, allowed_tools, load_skill_available)
            round_started = time.perf_counter()
            result = self._llm.chat_with_tools(messages, schemas)
            last_content = result.content

            logger.info(
                "agent 第 %d 轮 messages=%d 带工具=%s finish_reason=%s 耗时=%dms",
                rounds,
                len(messages),
                bool(schemas),
                result.finish_reason,
                _elapsed_ms(round_started),
            )

            if not result.tool_calls:
                stop_reason = "final_answer"
                break

            # 已经用完最后一轮：再执行工具也没有下一轮来消费结果，直接停止
            if rounds >= max_steps:
                stop_reason = "max_steps"
                logger.warning("agent 达到最大步数 %d，模型仍在请求工具，停止", max_steps)
                break

            # 先回填 assistant 的 tool_calls，再逐条回填工具结果：
            # 每条工具结果都必须用 tool_call_id 与申请单配对
            messages.append(_assistant_message(result))
            for call in result.tool_calls:
                tool_calls_count += 1
                _emit(
                    on_event,
                    {
                        "event": "tool_call",
                        "index": len(steps),
                        "tool": call.name,
                        "arguments": call.arguments,
                    },
                )

                # load_skill 不是普通工具：它会把正文写进 system prompt，并收窄后续工具集
                if call.name == LOAD_SKILL_NAME:
                    step, loaded, last_signature, repeat_count = self._run_load_skill(
                        call=call,
                        index=len(steps),
                        max_chars=max_chars,
                        last_signature=last_signature,
                        repeat_count=repeat_count,
                    )
                    steps.append(step)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": step.result_text,
                        }
                    )
                    _emit(on_event, _step_event(step))
                    if loaded is not None:
                        active_skill = loaded
                        allowed_tools = set(loaded.tools) if loaded.tools else None
                        load_skill_available = False
                        # 正文进 system prompt：后续每一轮都能看到
                        messages[0]["content"] = self._system_prompt(active_skill, [])
                    continue

                step, last_signature, repeat_count = self._run_tool(
                    call=call,
                    index=len(steps),
                    max_chars=max_chars,
                    last_signature=last_signature,
                    repeat_count=repeat_count,
                )
                steps.append(step)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": step.result_text,
                    }
                )
                _emit(on_event, _step_event(step))

        if last_content:
            answer = last_content
        elif stop_reason == "max_steps":
            # 模型到最后也没给文本：给一个可读的兜底，而不是返回空字符串
            answer = f"已达到最大步数（{max_steps}），未能得到最终答案。"
        else:
            answer = ""

        latency_ms = _elapsed_ms(started)
        logger.info(
            "agent 结束 stop_reason=%s 轮数=%d 步数=%d 工具调用次数=%d 答案长度=%d 耗时=%dms",
            stop_reason,
            rounds,
            len(steps),
            tool_calls_count,
            len(answer),
            latency_ms,
        )
        return AgentRun(
            answer=answer,
            skill=active_skill.name if active_skill else None,
            steps=steps,
            stop_reason=stop_reason,
            tool_calls_count=tool_calls_count,
            rounds=rounds,
            latency_ms=latency_ms,
        )

    def _resolve_skill(self, name: str | None) -> Skill | None:
        """解析显式 skill；不存在时抛 ValueError（由 API 映射成 400）。"""
        if name is None:
            return None
        if self._skills is None:
            raise ValueError(f"未知的 skill：{name}")
        return self._skills.get(name)

    def _auto_skills(self, active: Skill | None) -> list[Skill]:
        """自动模式下列出可用 skill；显式指定或关闭自动选择时返回空列表。"""
        if active is not None or self._skills is None:
            return []
        if not self._settings.skill_auto_select:
            return []
        return self._skills.summaries()

    def _system_prompt(self, active: Skill | None, auto_skills: list[Skill]) -> str:
        """拼 system prompt：通用规则 + 可用 skill 清单 + 当前 skill 正文。"""
        content = _SYSTEM_PROMPT
        if auto_skills:
            lines = "\n".join(f"- {s.name}: {s.description}" for s in auto_skills)
            content += f"\n\n可用 skill（符合场景时调用 load_skill 加载）：\n{lines}"
        if active is not None:
            content += f"\n\n【当前技能：{active.name}】\n{active.body}"
        return content

    def _run_load_skill(
        self,
        call: ToolCall,
        index: int,
        max_chars: int,
        last_signature: tuple[str, str] | None,
        repeat_count: int,
    ) -> tuple[AgentStep, Skill | None, tuple[str, str], int]:
        """处理 load_skill：加载成功时返回 Skill，供调用方收窄工具集。"""
        started = time.perf_counter()
        args, parse_error = _parse_arguments(call.arguments)
        signature = (call.name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        repeat_count = repeat_count + 1 if signature == last_signature else 1

        loaded: Skill | None = None
        ok = False
        if parse_error is not None:
            text = f"工具参数解析失败：{parse_error}"
            logger.warning("agent 加载 skill 失败 原因=参数不是合法 JSON")
        else:
            name = str(args.get("name") or "").strip()
            if self._skills is None:
                text = "skill 机制未启用。"
            else:
                try:
                    loaded = self._skills.get(name)
                    ok = True
                    text = f"已加载 skill：{name}。请按该 skill 的流程继续。"
                    logger.info("agent 加载 skill name=%s 工具=%s", name, loaded.tools or "全部")
                except ValueError:
                    text = f"skill 不存在：{name}"
                    logger.warning("agent 加载 skill 失败 name=%s 原因=不存在", _short(name))

        if repeat_count >= 2:
            text += "\n\n[提示] 你已连续重复调用同一工具与相同参数，请换一种策略。"
            logger.warning("agent 工具重复调用 name=%s 连续=%d 次", call.name, repeat_count)

        text = _clip(text, max_chars)
        elapsed_ms = _elapsed_ms(started)
        step = AgentStep(
            index=index,
            tool=call.name,
            arguments=args,
            result_text=text,
            ok=ok,
            elapsed_ms=elapsed_ms,
        )
        logger.info(
            "agent 工具调用 index=%d name=%s 参数=%s 成功=%s 结果长度=%d 耗时=%dms",
            index,
            call.name,
            _short(repr(args), 80),
            ok,
            len(text),
            elapsed_ms,
        )
        return step, loaded, signature, repeat_count

    def _run_tool(
        self,
        call: ToolCall,
        index: int,
        max_chars: int,
        last_signature: tuple[str, str] | None,
        repeat_count: int,
    ) -> tuple[AgentStep, tuple[str, str], int]:
        """执行一次 tool_call，并把任何失败都转成可回填的文本。

        Args:
            call: 模型发出的工具调用申请。
            index: 该步骤在整次运行中的全局序号。
            max_chars: 结果文本的截断上限。
            last_signature: 上一次的 (工具名, 参数) 签名，用于重复检测。
            repeat_count: 当前连续重复次数。

        Returns:
            (AgentStep, 本次签名, 更新后的连续重复次数)。
        """
        started = time.perf_counter()
        args, parse_error = _parse_arguments(call.arguments)

        # 重复检测放在执行前：即使工具失败，也说明模型在原地打转
        signature = (call.name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        repeat_count = repeat_count + 1 if signature == last_signature else 1

        if parse_error is not None:
            ok = False
            text = f"工具参数解析失败：{parse_error}"
            logger.warning(
                "agent 工具调用失败 name=%s 原因=参数不是合法 JSON 错误=%s",
                call.name,
                _short(parse_error, 100),
            )
        else:
            try:
                tool = self._registry.get(call.name)
                text = tool.handler(args).text
                ok = True
            except KeyError:
                ok = False
                text = f"工具不存在：{call.name}"
                logger.warning("agent 工具调用失败 name=%s 原因=未注册", call.name)
            except Exception as exc:  # noqa: BLE001 —— 工具失败不能中断整个循环
                ok = False
                text = f"工具执行失败：{exc}"
                logger.warning(
                    "agent 工具调用失败 name=%s 原因=%s",
                    call.name,
                    _short(str(exc), 100),
                )
                logger.debug("agent 工具异常堆栈 name=%s", call.name, exc_info=True)

        if repeat_count >= 2:
            # 模型可能陷入"调同一个工具、同样参数"的死循环；提示它换策略
            text += "\n\n[提示] 你已连续重复调用同一工具与相同参数，请换一种策略。"
            logger.warning(
                "agent 工具重复调用 name=%s 连续=%d 次", call.name, repeat_count
            )

        text = _clip(text, max_chars)
        elapsed_ms = _elapsed_ms(started)
        step = AgentStep(
            index=index,
            tool=call.name,
            arguments=args,
            result_text=text,
            ok=ok,
            elapsed_ms=elapsed_ms,
        )
        logger.info(
            "agent 工具调用 index=%d name=%s 参数=%s 成功=%s 结果长度=%d 耗时=%dms",
            index,
            call.name,
            _short(repr(args), 80),
            ok,
            len(text),
            elapsed_ms,
        )
        return step, signature, repeat_count


def _emit(callback: Callable[[dict], None] | None, event: dict) -> None:
    """安全地发一个流式事件；回调异常不影响主循环。"""
    if callback is None:
        return
    try:
        callback(event)
    except Exception:  # noqa: BLE001 —— 前端断开时不能拖垮 agent
        logger.debug("agent 事件回调失败", exc_info=True)


def _step_event(step: AgentStep) -> dict:
    """把 AgentStep 转成 tool_result 事件。"""
    return {
        "event": "tool_result",
        "index": step.index,
        "tool": step.tool,
        "arguments": step.arguments,
        "result_text": step.result_text,
        "ok": step.ok,
        "elapsed_ms": step.elapsed_ms,
    }


def _filter_schemas(
    base_schemas: list[dict],
    allowed_tools: set[str] | None,
    load_skill_available: bool,
) -> list[dict]:
    """按当前 skill 收窄工具集；自动模式且尚未加载时追加 load_skill。"""
    schemas = [
        schema
        for schema in base_schemas
        if allowed_tools is None or schema["function"]["name"] in allowed_tools
    ]
    if load_skill_available:
        schemas.append(LOAD_SKILL_SCHEMA)
    return schemas


def _build_initial_messages(
    question: str, history: list[dict] | None, system_prompt: str
) -> list[dict]:
    """组装首轮 messages：system → 历史 → 当前问题。"""
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})
    return messages


def _assistant_message(result: ChatResult) -> dict:
    """把模型返回的 tool_calls 转成可回填的 assistant 消息。"""
    return {
        "role": "assistant",
        "content": result.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in result.tool_calls
        ],
    }


def _parse_arguments(raw: str) -> tuple[dict, str | None]:
    """解析模型给的 JSON 参数。

    Returns:
        (参数 dict, 错误信息)；解析失败时返回 ({"_raw": 原文}, 错误信息)，
        这样轨迹里仍能看到模型到底发了什么。
    """
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        return {"_raw": raw}, str(exc)
    if not isinstance(parsed, dict):
        return {"_raw": raw}, "参数必须是 JSON 对象"
    return parsed, None


def _clip(text: str, limit: int) -> str:
    """严格按上限截断（省略号也计入长度），保证结果长度 ≤ limit。"""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    suffix = "..."
    if limit <= len(suffix):
        return text[:limit]
    return text[: limit - len(suffix)] + suffix


def _short(text: str, limit: int = 50) -> str:
    """日志用截断：长问题/长参数只在日志里保留开头。"""
    return text if len(text) <= limit else text[:limit] + "..."


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class AgentEngine(Protocol):
    """两版 loop 的共同接口（§19.17）。"""

    def run(
        self,
        question: str,
        skill: str | None = None,
        history: list[dict] | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> AgentRun:
        ...


def create_agent_runner(
    settings: Settings,
    registry: ToolRegistry,
    llm: LLMProvider,
    skills: SkillLoader | None = None,
) -> AgentEngine:
    """按 AGENT_ENGINE 返回手写版或 LangGraph 版（§19.17）。

    LangGraph 采用延迟导入：handwritten 模式下进程内不会加载 langgraph。
    """
    engine = (settings.agent_engine or "handwritten").strip().lower()
    if engine == "handwritten":
        return AgentRunner(settings, registry, llm, skills)
    if engine == "langgraph":
        try:
            from kbqa.agent_graph import GraphAgentRunner
        except ImportError as exc:  # 缺可选依赖时给出明确安装指引
            raise RuntimeError(
                "AGENT_ENGINE=langgraph 需要安装 langgraph："
                "pip install -r requirements-langgraph.txt"
            ) from exc
        return GraphAgentRunner(settings, registry, llm, skills)
    raise ValueError(
        f"未知的 AGENT_ENGINE：{settings.agent_engine!r}（可选 handwritten / langgraph）"
    )
