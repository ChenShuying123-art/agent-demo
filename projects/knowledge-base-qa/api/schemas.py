"""HTTP 层请求 / 响应模型（spec §8）。

职责边界：只定义对外的数据结构与「kbqa DTO → 响应模型」的转换函数，
    **不含任何业务逻辑，也不做网络调用**。HTTP 语义（状态码、错误信封）在 routes.py。

请求模型（*Request）：字段与 §8 表格的「请求」列一一对应。
响应模型（*Out / *Response）：字段与 §8 表格的「响应」列一一对应，
    字段名严格照抄（如 /api/index 的耗时字段就叫 `ms`，而不是内部 pipeline 用的 `elapsed_ms`）。

为什么不让 kbqa 的 @dataclass 直接当 response_model，而要显式转一层：
    kbqa 的 DTO 是"内部契约"，字段会随实现演进（例如 Document.path 是本地 Path、
    pipeline.index_documents 返回的是 dict）。显式转换把"对外 API 形状"与"内部结构"解耦：
    内部字段变动不会悄悄改变 API 输出，API 的兼容性改动也集中在本文件，便于 review。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from kbqa.models import AgentRun, Chunk, Document, QAResult, RerankResult, SearchResult

# --------------------------------------------------------------------- 请求


class IndexRequest(BaseModel):
    """/api/index 请求体：要向量化的文档 id 列表。"""

    doc_ids: list[str] = Field(min_length=1, description="要索引的 doc_id 列表")


class RetrieveRequest(BaseModel):
    """/api/retrieve 请求体：观测两阶段检索。"""

    question: str
    doc_ids: list[str] | None = Field(default=None, description="只在这些文档内检索；缺省为全库")
    use_rerank: bool | None = Field(default=None, description="是否重排；缺省跟随服务端配置")


class QARequest(BaseModel):
    """/api/qa 请求体。"""

    question: str
    style: str | None = Field(default=None, description="提示词风格；缺省用第一个风格")
    doc_ids: list[str] | None = None
    use_rerank: bool | None = None


class CompareRequest(BaseModel):
    """/api/qa/compare 请求体：一次生成三种风格。"""

    question: str
    doc_ids: list[str] | None = None


class AgentChatRequest(BaseModel):
    """/api/agent/chat 请求体（spec-agent §19.9）。"""

    question: str
    skill: str | None = Field(default=None, description="指定 skill；缺省为自动选择")
    history: list[dict] = Field(default_factory=list, description="可选的历史消息")


# --------------------------------------------------------------------- 响应


class ChunkOut(BaseModel):
    """切分片段。text 一并返回，前端「召回 → 重排」面板展开时可看到原文。"""

    chunk_id: str
    doc_id: str
    filename: str
    index: int
    text: str
    start: int
    end: int


class SearchResultOut(BaseModel):
    """召回阶段的单条结果。"""

    chunk: ChunkOut
    score: float  # cosine 相似度
    rank: int


class RerankResultOut(BaseModel):
    """重排阶段的单条结果。rerank_score 与 cosine 不同尺度，故单独成字段（§7.7）。"""

    chunk: ChunkOut
    rerank_score: float
    original_rank: int
    new_rank: int
    degraded: bool


class DocumentOut(BaseModel):
    """文档元数据。字段与 §7.2 的 Document 一致（含 path，遵守"返回字段不得改变"）。"""

    doc_id: str
    filename: str
    path: str
    size: int
    uploaded_at: datetime
    indexed: bool
    chunk_count: int


class IndexItemOut(BaseModel):
    """单篇文档的索引结果，字段名严格按 §8：`ms`。"""

    doc_id: str
    chunks: int
    ms: int


class DeleteResponse(BaseModel):
    """删除接口响应。"""

    ok: bool


class RetrieveResponse(BaseModel):
    """两阶段检索的完整观测结果（§8）。"""

    candidates: list[SearchResultOut]  # 召回列
    used: list[RerankResultOut]  # 重排列
    degraded: bool  # 是否走了降级（未真正重排）


class QAResultOut(BaseModel):
    """一次问答的完整结果，字段与 §7.2 的 QAResult 一致。"""

    answer: str
    style: str
    citations: list[str]
    candidates: list[SearchResultOut]
    used: list[RerankResultOut]
    latency_ms: int


class AgentStepOut(BaseModel):
    """一次工具调用的轨迹（spec-agent §19.9）。"""

    index: int
    tool: str
    arguments: dict
    result_text: str
    ok: bool
    elapsed_ms: int


class AgentRunOut(BaseModel):
    """一次 agent 对话的响应（spec-agent §19.9）。"""

    answer: str
    skill: str | None
    steps: list[AgentStepOut]
    stop_reason: str
    tool_calls_count: int
    rounds: int
    latency_ms: int


class SkillOut(BaseModel):
    """可用 skill 的简要信息，供前端下拉展示。"""

    name: str
    description: str


class HealthResponse(BaseModel):
    """健康检查响应：回显三个模型名（§8）。"""

    status: str
    chat_model: str
    embedding_model: str
    rerank_model: str


class ErrorDetail(BaseModel):
    """错误明细：所有错误统一用 {error: {code, message}} 信封（§8）。"""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """错误响应信封。仅用于文档展示，实际以 JSONResponse 返回。"""

    error: ErrorDetail


# ----------------------------------------------------------------- 转换函数


def to_chunk_out(chunk: Chunk) -> ChunkOut:
    """Chunk（dataclass）→ ChunkOut。"""
    return ChunkOut(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        filename=chunk.filename,
        index=chunk.index,
        text=chunk.text,
        start=chunk.start,
        end=chunk.end,
    )


def to_search_out(item: SearchResult) -> SearchResultOut:
    """SearchResult → SearchResultOut。"""
    return SearchResultOut(chunk=to_chunk_out(item.chunk), score=item.score, rank=item.rank)


def to_rerank_out(item: RerankResult) -> RerankResultOut:
    """RerankResult → RerankResultOut，保留 original_rank 供前端画升降箭头。"""
    return RerankResultOut(
        chunk=to_chunk_out(item.chunk),
        rerank_score=item.rerank_score,
        original_rank=item.original_rank,
        new_rank=item.new_rank,
        degraded=item.degraded,
    )


def to_document_out(doc: Document) -> DocumentOut:
    """Document → DocumentOut。path 是本地 Path，转成字符串再出网。"""
    return DocumentOut(
        doc_id=doc.doc_id,
        filename=doc.filename,
        path=str(doc.path),
        size=doc.size,
        uploaded_at=doc.uploaded_at,
        indexed=doc.indexed,
        chunk_count=doc.chunk_count,
    )


def to_qa_out(result: QAResult) -> QAResultOut:
    """QAResult → QAResultOut，两阶段检索结果一并透出供前端展示。"""
    return QAResultOut(
        answer=result.answer,
        style=result.style,
        citations=result.citations,
        candidates=[to_search_out(c) for c in result.candidates],
        used=[to_rerank_out(u) for u in result.used],
        latency_ms=result.latency_ms,
    )


def to_agent_run_out(run: AgentRun) -> AgentRunOut:
    """AgentRun → AgentRunOut，逐条转换工具轨迹（供前端轨迹面板与对照实验）。"""
    return AgentRunOut(
        answer=run.answer,
        skill=run.skill,
        steps=[
            AgentStepOut(
                index=step.index,
                tool=step.tool,
                arguments=step.arguments,
                result_text=step.result_text,
                ok=step.ok,
                elapsed_ms=step.elapsed_ms,
            )
            for step in run.steps
        ],
        stop_reason=run.stop_reason,
        tool_calls_count=run.tool_calls_count,
        rounds=run.rounds,
        latency_ms=run.latency_ms,
    )
