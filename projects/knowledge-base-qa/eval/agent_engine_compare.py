"""手写 loop vs LangGraph 版对照实验（spec-agent §19.17，T29）。

同一批问题分别跑两个引擎，记录：
    - 答案 / 工具序列 / 步数 / 轮数 / 耗时 / 引用
    - 代码量（LOC）与依赖差异
    - 一个确定性的 max_steps 边界场景（两版应一致）

运行：python eval/agent_engine_compare.py
输出：eval/agent_engine_compare.md
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kbqa.agent import AgentRunner
from kbqa.agent_graph import GraphAgentRunner
from kbqa.config import settings
from kbqa.embeddings import get_embedding_provider
from kbqa.llm import get_llm
from kbqa.models import ChatResult, ToolCall
from kbqa.pipeline import RAGPipeline
from kbqa.rerank import get_reranker
from kbqa.tools import ToolRegistry
from kbqa.tools.datetime_tool import get_datetime
from kbqa.tools.kb_tool import build_kb_tool
from kbqa.vectorstore import VectorStore

QUESTIONS = [
    "豆豆的疫苗本编号是什么？",
    "今天几号，星期几？",
    "2025 年旅行去了哪些地方？",
]

_CITATION_RE = re.compile(r"\[(\d+)\]")


class ScriptedLLM:
    """确定性脚本 LLM：每次都想调工具，用于 max_steps 边界对照。"""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, temperature=None):
        return "unused"

    def chat_with_tools(self, messages, tools, temperature=None):
        self.calls += 1
        return ChatResult(
            content=None,
            tool_calls=[ToolCall(id=f"c{self.calls}", name="get_datetime", arguments="{}")],
            finish_reason="tool_calls",
        )


def build_components():
    store = VectorStore.load(settings.data_dir / "index")
    llm = get_llm(settings)
    pipeline = RAGPipeline(
        settings=settings,
        store=store,
        embedder=get_embedding_provider(settings),
        reranker=get_reranker(settings),
        llm=llm,
    )
    registry = ToolRegistry()
    registry.register(get_datetime)
    registry.register(build_kb_tool(pipeline, settings.agent_tool_result_max_chars))
    return llm, registry


def _cell(text: str, limit: int = 50) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _citations(answer: str) -> list[int]:
    return sorted({int(n) for n in _CITATION_RE.findall(answer)})


def run_real(questions: list[str]) -> list[dict]:
    llm, registry = build_components()
    hand = AgentRunner(settings, registry, llm)
    graph = GraphAgentRunner(settings, registry, llm)
    rows: list[dict] = []

    for index, question in enumerate(questions, start=1):
        print(f"[{index}/{len(questions)}] 手写版：{question}")
        h = hand.run(question)
        print(f"    tools={[s.tool for s in h.steps]} latency={h.latency_ms}ms")

        print(f"[{index}/{len(questions)}] LangGraph：{question}")
        g = graph.run(question)
        print(f"    tools={[s.tool for s in g.steps]} latency={g.latency_ms}ms")

        rows.append(
            {
                "index": index,
                "question": question,
                "hand": h,
                "graph": g,
                "same_tools": [s.tool for s in h.steps] == [s.tool for s in g.steps],
                "same_answer": h.answer == g.answer,
            }
        )
    return rows


def run_max_steps() -> dict:
    """确定性边界场景：两版在 max_steps=3 时都应停止且行为一致。"""
    _, registry = build_components()
    short = settings.model_copy(update={"agent_max_steps": 3})
    h = AgentRunner(short, registry, ScriptedLLM()).run("一直调工具")
    g = GraphAgentRunner(short, registry, ScriptedLLM()).run("一直调工具")
    return {
        "hand": (h.stop_reason, h.rounds, len(h.steps), h.tool_calls_count),
        "graph": (g.stop_reason, g.rounds, len(g.steps), g.tool_calls_count),
    }


def loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def render(rows: list[dict], boundary: dict) -> str:
    hand_loc = loc(_ROOT / "kbqa" / "agent.py")
    graph_loc = loc(_ROOT / "kbqa" / "agent_graph.py")
    avg_hand = int(sum(r["hand"].latency_ms for r in rows) / len(rows))
    avg_graph = int(sum(r["graph"].latency_ms for r in rows) / len(rows))

    lines = [
        "# 手写 loop vs LangGraph：双引擎对照",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 问题数：{len(rows)}",
        f"- 手写版：`kbqa/agent.py`（{hand_loc} 行）",
        f"- LangGraph 版：`kbqa/agent_graph.py`（{graph_loc} 行）",
        "- 共用：同一个 store / llm / ToolRegistry，差异只在编排层",
        "",
        "## 逐题对照",
        "",
        "| # | 问题 | 引擎 | 工具序列 | 步数 | 轮数 | 耗时(ms) | 引用 | 答案摘要 |",
        "|---|------|------|----------|------|------|----------|------|----------|",
    ]

    for row in rows:
        for label, run in (("手写", row["hand"]), ("LangGraph", row["graph"])):
            tools = ", ".join(s.tool for s in run.steps) or "未调用"
            lines.append(
                f"| {row['index']} | {_cell(row['question'])} | {label} | {tools} | "
                f"{len(run.steps)} | {run.rounds} | {run.latency_ms} | "
                f"{len(_citations(run.answer))} | {_cell(run.answer)} |"
            )

    differences: list[str] = []
    for row in rows:
        h, g = row["hand"], row["graph"]
        if not row["same_tools"]:
            differences.append(
                f"- **工具序列不同**「{row['question']}」：手写 "
                f"{[s.tool for s in h.steps]} vs LangGraph {[s.tool for s in g.steps]}；"
                "两版把选择权都交给模型，差异来自模型采样，不是编排逻辑。"
            )
        if not row["same_answer"]:
            differences.append(
                f"- **答案不同**「{row['question']}」：手写「{_cell(h.answer)}」 vs "
                f"LangGraph「{_cell(g.answer)}」；同样是模型采样差异。"
            )

    differences.append(
        "- **依赖与启动差异**：`agent.py` 不依赖 langgraph；只有选择 `langgraph` 引擎时才延迟导入 "
        "`agent_graph.py` 与 langgraph。手写版的启动路径更轻。"
    )
    differences.append(
        f"- **代码量与抽象**：手写版 {hand_loc} 行（显式 while/for）；LangGraph 版 {graph_loc} 行"
        "（StateGraph + 条件边 + 节点）。图版把循环结构声明化，但多了一层框架概念。"
    )
    differences.append(
        f"- **平均耗时**：手写 {avg_hand} ms vs LangGraph {avg_graph} ms；"
        "本次差异主要来自模型调用与工具耗时，不能单独归因于框架开销。"
    )

    hb, gb = boundary["hand"], boundary["graph"]
    lines += [
        "",
        "## 确定性边界场景（max_steps=3，脚本化 LLM 每轮都请求工具）",
        "",
        f"- 手写版：stop_reason={hb[0]}，rounds={hb[1]}，steps={hb[2]}，tool_calls={hb[3]}",
        f"- LangGraph：stop_reason={gb[0]}，rounds={gb[1]}，steps={gb[2]}，tool_calls={gb[3]}",
        f"- 一致性：{'✅ 两版完全一致' if hb == gb else '⚠️ 存在差异'}",
        "",
        "## 差异与结论",
        "",
        *differences,
        "",
        "## 学习结论",
        "",
        "1. **框架替你做了什么**：LangGraph 把\"循环 + 条件判断\"变成节点与边，"
        "状态更新由框架合并；读图就能看懂控制流，但需要理解 State/Node/Edge 这组概念。",
        "2. **框架藏起了什么**：节点的执行顺序、状态合并、递归上限由框架管理；"
        "出错时的调用栈更深，排查要先理解框架。",
        "3. **什么时候选手写**：想逐行看懂 loop、依赖越少越好、需要精细控制事件与日志时。",
        "4. **什么时候选 LangGraph**：流程会继续变复杂（分支、并行、人工介入、持久化）时，"
        "图的声明式结构更容易扩展。",
        "",
        "> 两版被刻意设计为控制流等价；对话层的差异主要来自模型采样。"
        "不要为了\"看起来不同\"而改其中一版的行为。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    rows = run_real(QUESTIONS)
    boundary = run_max_steps()
    report = render(rows, boundary)
    out = Path(__file__).with_name("agent_engine_compare.md")
    out.write_text(report, encoding="utf-8")
    print(f"\n报告已写入：{out}")


if __name__ == "__main__":
    main()
