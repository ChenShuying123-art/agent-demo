"""LangGraph 版 agent loop（spec-agent §19.17，T28）。

与手写版共用同一套契约与工具：
    - 继承 `AgentRunner`，复用 skill 解析、工具执行、截断、重复检测与日志；
    - 只把"循环"换成 `StateGraph`：llm 节点 → 条件边 → tools 节点 → 回到 llm。

这样两版对比的差异只来自编排方式，而不是工具实现。
"""

from __future__ import annotations

import logging
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph

from kbqa.agent import (
    AgentRunner,
    _assistant_message,
    _build_initial_messages,
    _elapsed_ms,
    _emit,
    _filter_schemas,
    _step_event,
)
from kbqa.config import Settings
from kbqa.llm import LLMProvider
from kbqa.models import AgentRun, AgentStep, ChatResult, ToolCall
from kbqa.skills import LOAD_SKILL_NAME, Skill, SkillLoader
from kbqa.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """图的状态：消息、轨迹、轮数与当前 skill。"""

    messages: list[dict]
    steps: list[AgentStep]
    rounds: int
    tool_calls_count: int
    last_content: str | None
    stop_reason: str
    active_skill: Skill | None
    allowed_tools: set[str] | None
    load_skill_available: bool
    last_signature: tuple[str, str] | None
    repeat_count: int
    pending_calls: list[ToolCall]


class GraphAgentRunner(AgentRunner):
    """LangGraph 版：同一契约，图编排。"""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        llm: LLMProvider,
        skills: SkillLoader | None = None,
    ) -> None:
        super().__init__(settings, registry, llm, skills)

    def run(
        self,
        question: str,
        skill: str | None = None,
        history: list[dict] | None = None,
        on_event=None,
    ) -> AgentRun:
        active_skill = self._resolve_skill(skill)
        auto_skills = self._auto_skills(active_skill)

        started = time.perf_counter()
        max_steps = self._settings.agent_max_steps
        max_chars = self._settings.agent_tool_result_max_chars
        base_schemas = self._registry.schemas()

        allowed_tools = set(active_skill.tools) if active_skill and active_skill.tools else None
        load_skill_available = bool(auto_skills) and active_skill is None
        messages = _build_initial_messages(
            question, history, self._system_prompt(active_skill, auto_skills)
        )

        initial: AgentState = {
            "messages": messages,
            "steps": [],
            "rounds": 0,
            "tool_calls_count": 0,
            "last_content": None,
            "stop_reason": "max_steps",
            "active_skill": active_skill,
            "allowed_tools": allowed_tools,
            "load_skill_available": load_skill_available,
            "last_signature": None,
            "repeat_count": 0,
            "pending_calls": [],
        }

        logger.info(
            "agent(langgraph) 开始 question=%s skill=%s 工具数=%d max_steps=%d",
            _short(question),
            active_skill.name if active_skill else "自动",
            len(_filter_schemas(base_schemas, allowed_tools, load_skill_available)),
            max_steps,
        )

        graph = self._build_graph(base_schemas, max_steps, max_chars, on_event)
        final = graph.invoke(initial, config={"recursion_limit": max_steps * 2 + 4})

        last_content = final.get("last_content")
        stop_reason = final.get("stop_reason") or "max_steps"
        if last_content:
            answer = last_content
        elif stop_reason == "max_steps":
            answer = f"已达到最大步数（{max_steps}），未能得到最终答案。"
        else:
            answer = ""

        active = final.get("active_skill")
        latency_ms = _elapsed_ms(started)
        logger.info(
            "agent(langgraph) 结束 stop_reason=%s 轮数=%d 步数=%d 工具调用次数=%d 答案长度=%d 耗时=%dms",
            stop_reason,
            final.get("rounds", 0),
            len(final.get("steps", [])),
            final.get("tool_calls_count", 0),
            len(answer),
            latency_ms,
        )
        return AgentRun(
            answer=answer,
            skill=active.name if active else None,
            steps=list(final.get("steps", [])),
            stop_reason=stop_reason,
            tool_calls_count=final.get("tool_calls_count", 0),
            rounds=final.get("rounds", 0),
            latency_ms=latency_ms,
        )

    def _build_graph(self, base_schemas, max_steps, max_chars, on_event):
        """构建 StateGraph：llm →（tools → llm）→ END。"""
        graph = StateGraph(AgentState)

        def llm_node(state: AgentState) -> dict:
            rounds = state["rounds"] + 1
            _emit(on_event, {"event": "step_start", "round": rounds})
            schemas = _filter_schemas(
                base_schemas, state["allowed_tools"], state["load_skill_available"]
            )
            round_started = time.perf_counter()
            result = self._llm.chat_with_tools(state["messages"], schemas)
            logger.info(
                "agent(langgraph) 第 %d 轮 messages=%d 带工具=%s finish_reason=%s 耗时=%dms",
                rounds,
                len(state["messages"]),
                bool(schemas),
                result.finish_reason,
                _elapsed_ms(round_started),
            )

            if not result.tool_calls:
                return {
                    "rounds": rounds,
                    "last_content": result.content,
                    "pending_calls": [],
                    "stop_reason": "final_answer",
                }
            if rounds >= max_steps:
                logger.warning(
                    "agent(langgraph) 达到最大步数 %d，模型仍在请求工具，停止", max_steps
                )
                return {
                    "rounds": rounds,
                    "last_content": result.content,
                    "pending_calls": [],
                    "stop_reason": "max_steps",
                }

            messages = list(state["messages"])
            messages.append(_assistant_message(result))
            return {
                "rounds": rounds,
                "last_content": result.content,
                "messages": messages,
                "pending_calls": result.tool_calls,
            }

        def tools_node(state: AgentState) -> dict:
            messages = list(state["messages"])
            steps = list(state["steps"])
            count = state["tool_calls_count"]
            active = state["active_skill"]
            allowed = state["allowed_tools"]
            load_available = state["load_skill_available"]
            last_signature = state["last_signature"]
            repeat_count = state["repeat_count"]

            for call in state["pending_calls"]:
                count += 1
                _emit(
                    on_event,
                    {
                        "event": "tool_call",
                        "index": len(steps),
                        "tool": call.name,
                        "arguments": call.arguments,
                    },
                )

                if call.name == LOAD_SKILL_NAME:
                    step, loaded, last_signature, repeat_count = self._run_load_skill(
                        call, len(steps), max_chars, last_signature, repeat_count
                    )
                    steps.append(step)
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": step.result_text}
                    )
                    _emit(on_event, _step_event(step))
                    if loaded is not None:
                        active = loaded
                        allowed = set(loaded.tools) if loaded.tools else None
                        load_available = False
                        messages[0] = {
                            "role": "system",
                            "content": self._system_prompt(active, []),
                        }
                    continue

                step, last_signature, repeat_count = self._run_tool(
                    call, len(steps), max_chars, last_signature, repeat_count
                )
                steps.append(step)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": step.result_text}
                )
                _emit(on_event, _step_event(step))

            return {
                "messages": messages,
                "steps": steps,
                "tool_calls_count": count,
                "active_skill": active,
                "allowed_tools": allowed,
                "load_skill_available": load_available,
                "last_signature": last_signature,
                "repeat_count": repeat_count,
                "pending_calls": [],
            }

        def route(state: AgentState) -> str:
            return "tools" if state["pending_calls"] else "end"

        graph.add_node("llm", llm_node)
        graph.add_node("tools", tools_node)
        graph.set_entry_point("llm")
        graph.add_conditional_edges("llm", route, {"tools": "tools", "end": END})
        graph.add_edge("tools", "llm")
        return graph.compile()


def _short(text: str, limit: int = 50) -> str:
    return text if len(text) <= limit else text[:limit] + "..."
