"""固定链路 vs Agent 自主 对照实验（spec-agent §19.14，T21）。

同一批问题分别跑：
    - 固定链路：RAGPipeline.answer（永远召回 + 重排 + 三风格之一）
    - Agent：AgentRunner.run（模型自主决定调不调工具、调哪个）

输出：eval/agent_compare.md

运行：python eval/agent_compare.py
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

# 允许直接 `python eval/agent_compare.py`：把项目根目录加入 sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kbqa.agent import AgentRunner
from kbqa.config import settings
from kbqa.embeddings import get_embedding_provider
from kbqa.llm import get_llm
from kbqa.pipeline import RAGPipeline
from kbqa.rerank import get_reranker
from kbqa.tools import ToolRegistry
from kbqa.tools.datetime_tool import get_datetime
from kbqa.tools.kb_tool import build_kb_tool
from kbqa.vectorstore import VectorStore

# 默认问题覆盖两类：知识库事实题（应走检索）与实时题（应走日期工具）
DEFAULT_QUESTIONS = [
    "豆豆的疫苗本编号是什么？",
    "今天几号，星期几？",
    "2025 年旅行去了哪些地方？",
]

_CITATION_RE = re.compile(r"\[(\d+)\]")


def build_components():
    """装配固定链路与 agent，共用同一个 store / llm。"""
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
    agent = AgentRunner(settings, registry, llm)
    return pipeline, agent


def _cell(text: str, limit: int = 60) -> str:
    """表格单元格：压成一行并截断，避免 Markdown 表格被换行破坏。"""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def run(questions: list[str]) -> str:
    pipeline, agent = build_components()
    rows: list[dict] = []

    for index, question in enumerate(questions, start=1):
        print(f"[{index}/{len(questions)}] 固定链路：{question}")
        fixed = pipeline.answer(question, "strict_citation", None)
        print(f"    answer={_cell(fixed.answer)} latency={fixed.latency_ms}ms")

        print(f"[{index}/{len(questions)}] Agent：{question}")
        act = agent.run(question)
        tools = [step.tool for step in act.steps]
        print(
            f"    answer={_cell(act.answer)} tools={tools} "
            f"steps={len(act.steps)} latency={act.latency_ms}ms"
        )

        rows.append(
            {
                "index": index,
                "question": question,
                "fixed_answer": fixed.answer,
                "fixed_citations": len(fixed.citations),
                "fixed_latency": fixed.latency_ms,
                "agent_answer": act.answer,
                "agent_tools": tools,
                "agent_steps": len(act.steps),
                "agent_calls": act.tool_calls_count,
                "agent_latency": act.latency_ms,
                "agent_stop": act.stop_reason,
                "agent_citations": sorted({int(n) for n in _CITATION_RE.findall(act.answer)}),
            }
        )

    return render(rows)


def render(rows: list[dict]) -> str:
    """把结果渲染成 Markdown 对照表 + 自动统计。"""
    lines = [
        "# 固定链路 vs Agent 自主：对照实验",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 问题数：{len(rows)}",
        "- 固定链路：`/api/qa` 同源的 `pipeline.answer(style=strict_citation)`",
        "- Agent：`AgentRunner.run`，工具 = `get_datetime` + `search_knowledge_base`",
        "",
        "## 逐题对照",
        "",
        "| # | 问题 | 方案 | 是否调工具 | 工具 / 步数 | 耗时(ms) | 引用数 | 答案摘要 |",
        "|---|------|------|------------|-------------|----------|--------|----------|",
    ]

    for row in rows:
        lines.append(
            f"| {row['index']} | {_cell(row['question'])} | 固定链路 | 否 | — | "
            f"{row['fixed_latency']} | {row['fixed_citations']} | {_cell(row['fixed_answer'])} |"
        )
        tools = ", ".join(row["agent_tools"]) or "未调用"
        lines.append(
            f"| {row['index']} | {_cell(row['question'])} | Agent | "
            f"{'是' if row['agent_tools'] else '否'} | {tools} / {row['agent_steps']} 步 | "
            f"{row['agent_latency']} | {len(row['agent_citations'])} | {_cell(row['agent_answer'])} |"
        )

    used_tools = sum(1 for row in rows if row["agent_tools"])
    use_datetime = sum(1 for row in rows if "get_datetime" in row["agent_tools"])
    use_kb = sum(1 for row in rows if "search_knowledge_base" in row["agent_tools"])
    avg_fixed = int(sum(row["fixed_latency"] for row in rows) / len(rows))
    avg_agent = int(sum(row["agent_latency"] for row in rows) / len(rows))

    # 具体案例：从数据里自动挑出"两版选择/结果不同"的题，避免只写空泛结论
    cases: list[str] = []
    for row in rows:
        if "get_datetime" in row["agent_tools"]:
            cases.append(
                f"- **{row['index']}. 实时题**「{row['question']}」：固定链路仍检索知识库，"
                f"回答「{_cell(row['fixed_answer'], 50)}」；Agent 调用 `get_datetime`，"
                f"回答「{_cell(row['agent_answer'], 50)}」。"
            )
        if not row["agent_tools"]:
            cases.append(
                f"- **{row['index']}. Agent 未调用工具**「{row['question']}」：固定链路检索并回答"
                f"「{_cell(row['fixed_answer'], 50)}」；Agent 在一轮内直接回答"
                f"「{_cell(row['agent_answer'], 50)}」，没有使用工具。"
            )
        fixed_refs = sorted({int(n) for n in _CITATION_RE.findall(row["fixed_answer"])})
        if fixed_refs and row["fixed_citations"] == 0:
            cases.append(
                f"- **{row['index']}. 引用异常**「{row['question']}」：固定链路答案出现 {fixed_refs}，"
                f"但有效引用数为 0（越界编号被忽略）；Agent 调用 "
                f"{row['agent_tools'] or '未调用工具'}，回答「{_cell(row['agent_answer'], 50)}」。"
            )
    if not cases:
        cases.append("- 本次未发现明显差异，建议增加问题样本后再观察。")

    lines += [
        "",
        "## 本次案例",
        "",
        *cases,
        "",
        "## 自动统计",
        "",
        f"- Agent 调用工具的问题数：{used_tools} / {len(rows)}",
        f"- 其中 `get_datetime`：{use_datetime} 次；`search_knowledge_base`：{use_kb} 次",
        f"- 平均耗时：固定链路 {avg_fixed} ms；Agent {avg_agent} ms",
        "",
        "## 通用观察",
        "",
        "1. **实时题**：固定链路仍会去检索知识库，而 Agent 会改用 `get_datetime`——最直观的「选择不同」。",
        "2. **知识库事实题**：固定链路必然召回；Agent 可能调用一次 `search_knowledge_base`，也可能直接回答。",
        "3. **引用**：固定链路有结构化 `citations` 且会过滤越界编号；Agent 的引用需要从答案里的 `[n]` 反推。",
        "4. 耗时不是公平比较：固定链路固定一次检索 + 一次生成；Agent 的轮数与工具次数由模型决定。",
        "",
        "> 本报告由 `eval/agent_compare.py` 生成；结论以实际输出为准，不为了「好看」调整数据。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    report = run(questions)
    out = Path(__file__).with_name("agent_compare.md")
    out.write_text(report, encoding="utf-8")
    print(f"\n报告已写入：{out}")


if __name__ == "__main__":
    main()
