"""FastAPI 路由层（spec §8）。

职责边界：本层只做 HTTP 语义——解析请求、调用 kbqa 的编排接口、把结果转成响应模型、
    以及把内部异常统一翻译成错误信封。**不写任何算法**（检索/重排/生成都在 kbqa 里）。

统一错误约定（§8）：
    任何错误都返回 {"error": {"code", "message"}}。映射关系：
        ValueError                → 400 invalid_request（doc_id 不存在、风格非法等用户输入问题）
        ApiError                  → 自带状态码（如删除不存在的文档 → 404）
        请求体校验失败            → 422 validation_error
        LLMError / OpenAIError    → 502，并**透传百炼的 code 与 message**
                                    （便于前端直接看到 invalid_api_key / 额度 / 地域等问题）
        其他未捕获异常            → 500 internal_error

关于上游模型 URL：对话与 Embedding 走 OpenAI 兼容协议，SDK 抛的是 openai.OpenAIError；
    Rerank 走百炼自有协议且内部会自行降级（不抛到这一层），所以这里只需兜住前两者。
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time

from fastapi import APIRouter, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAIError

from kbqa import loaders
from kbqa.agent import AgentRunner
from kbqa.llm import LLMError
from kbqa.pipeline import RAGPipeline
from kbqa.prompts import PROMPT_STYLES
from kbqa.vectorstore import VectorStore

from api.schemas import (
    AgentChatRequest,
    AgentRunOut,
    CompareRequest,
    DeleteResponse,
    DocumentOut,
    HealthResponse,
    IndexItemOut,
    IndexRequest,
    QARequest,
    QAResultOut,
    RetrieveRequest,
    RetrieveResponse,
    SkillOut,
    to_agent_run_out,
    to_document_out,
    to_qa_out,
    to_rerank_out,
    to_search_out,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["kbqa"])


class ApiError(Exception):
    """带 HTTP 语义的业务异常，由 install_exception_handlers 统一翻译成错误信封。

    为什么不让各路由直接返回 JSONResponse：直接 return 会绕过 response_model 校验、
    也让"哪些地方会发生什么错误"散落各处；抛异常 + 集中处理能让错误约定只写一次。
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# --------------------------------------------------------------------- 依赖


def _pipeline(request: Request) -> RAGPipeline:
    """取出应用级单例 pipeline（在 main.create_app 中装配到 app.state）。"""
    return request.app.state.pipeline


def _store(request: Request) -> VectorStore:
    """取出应用级单例向量库（删除文档时需要直接操作它）。"""
    return request.app.state.store


def _agent(request: Request) -> AgentRunner:
    """取出应用级单例 agent（在 main.create_app 中装配到 app.state）。"""
    return request.app.state.agent


# --------------------------------------------------------------------- 路由


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """自检接口：回显当前使用的三个模型名。

    这里**不实际调用模型**：health 会被前端/探针高频调用，真打三次模型既慢又费额度；
    模型是否真的可用，由 /api/qa 等真实链路的 502 错误直接暴露（§8 的错误约定）。
    """
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        chat_model=settings.chat_model,
        embedding_model=settings.embedding_model,
        rerank_model=settings.rerank_model,
    )


@router.post("/documents", response_model=DocumentOut)
async def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentOut:
    """上传文档（FR-1）。内容相同则命中去重，返回已存在的记录。"""
    settings = request.app.state.settings
    # UploadFile 必须在 async 路由里 await 读取；读取本身很快，后续落盘是同步小操作
    content = await file.read()
    # 文件名可能为空（极端客户端），给个占位名，save_upload 会做 basename 安全化
    doc = loaders.save_upload(file.filename or "unnamed.txt", content, settings.data_dir)
    return to_document_out(doc)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(request: Request) -> list[DocumentOut]:
    """列出全部已上传文档及其索引状态。"""
    settings = request.app.state.settings
    return [to_document_out(doc) for doc in loaders.list_documents(settings.data_dir)]


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(doc_id: str, request: Request) -> DeleteResponse:
    """删除文档：同时清掉上传文件与该文档的全部 chunk 向量（§8）。

    Raises:
        ApiError(404): doc_id 不存在（避免"删了个寂寞"却返回 ok=true 误导前端）。
    """
    settings = request.app.state.settings
    documents = {doc.doc_id: doc for doc in loaders.list_documents(settings.data_dir)}
    doc = documents.get(doc_id)
    if doc is None:
        raise ApiError(404, "document_not_found", f"文档不存在：{doc_id}")

    doc.path.unlink(missing_ok=True)  # 先删文件，再删向量（两者都做才算删干净）
    _store(request).remove_document(doc_id)  # 内部会立刻落盘，避免崩溃后向量"复活"
    logger.info("删除文档完成 doc_id=%s 文件=%s", doc_id, doc.filename)
    return DeleteResponse(ok=True)


@router.post("/index", response_model=list[IndexItemOut])
def index_documents(payload: IndexRequest, request: Request) -> list[IndexItemOut]:
    """向量化指定文档（FR-3）。

    响应字段名按 §8 定为 `ms`，而 pipeline 内部返回的是 `elapsed_ms`，这里做一次映射。
    """
    report = _pipeline(request).index_documents(payload.doc_ids)
    return [
        IndexItemOut(doc_id=item["doc_id"], chunks=item["chunks"], ms=item["elapsed_ms"])
        for item in report
    ]


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    """两阶段检索观测（FR-8）：返回召回列 + 重排列 + 是否降级。"""
    candidates, used = _pipeline(request).retrieve(
        payload.question, payload.doc_ids, payload.use_rerank
    )
    return RetrieveResponse(
        candidates=[to_search_out(item) for item in candidates],
        used=[to_rerank_out(item) for item in used],
        # 只要有任意一条是降级结果，就认为本次"未真正重排"（used 为空时不算降级）
        degraded=any(item.degraded for item in used),
    )


@router.post("/qa", response_model=QAResultOut)
def qa(payload: QARequest, request: Request) -> QAResultOut:
    """单风格问答（FR-5 / FR-6）。

    style 缺省用 PROMPT_STYLES 的第一个（strict_citation），与前端默认选项一致。
    style 非法时 prompts.build_messages 会抛 ValueError → 由全局处理器返回 400。
    """
    style = payload.style or PROMPT_STYLES[0]
    result = _pipeline(request).answer(
        payload.question, style, payload.doc_ids, payload.use_rerank
    )
    return to_qa_out(result)


@router.post("/qa/compare", response_model=list[QAResultOut])
def qa_compare(payload: CompareRequest, request: Request) -> list[QAResultOut]:
    """一次性返回三种风格的回答，便于并排对比（§8）。

    共用同一份检索结果（answer_all_styles 内部只检索一次），保证风格间的差异不是检索运气造成的。
    """
    results = _pipeline(request).answer_all_styles(
        payload.question, PROMPT_STYLES, payload.doc_ids
    )
    return [to_qa_out(result) for result in results]


# ------------------------------------------------------------------ agent


@router.get("/agent/skills", response_model=list[SkillOut])
def agent_skills(request: Request) -> list[SkillOut]:
    """列出可用 skill（spec-agent §19.9）。"""
    loader = getattr(request.app.state, "skills", None)
    if loader is None:
        return []
    return [
        SkillOut(name=skill.name, description=skill.description)
        for skill in loader.summaries()
    ]


@router.post("/agent/chat", response_model=AgentRunOut)
def agent_chat(payload: AgentChatRequest, request: Request) -> AgentRunOut:
    """一次 agent 对话（spec-agent §19.9）。

    工具失败与 max_steps 都不是 HTTP 错误：
        工具失败 → 200 + steps[].ok=false；
        max_steps → 200 + stop_reason="max_steps"。

    Raises:
        ApiError(400): 指定的 skill 不存在。
    """
    try:
        run = _agent(request).run(payload.question, payload.skill, payload.history)
    except ValueError as exc:
        # skill 不存在是用户输入错误；其他 ValueError 仍交给全局处理器（invalid_request）
        if payload.skill is not None:
            raise ApiError(400, "skill_not_found", f"skill 不存在：{payload.skill}") from exc
        raise
    return to_agent_run_out(run)


@router.post("/agent/chat/stream")
def agent_chat_stream(payload: AgentChatRequest, request: Request) -> StreamingResponse:
    """SSE 流式对话（spec-agent §19.10，T27）。

    事件类型：step_start / tool_call / tool_result / token / done（失败时 error）。
    说明：`token` 是把最终答案按 8 字分片发出，用于前端逐字渲染；
    模型本身仍是一次性返回，真正的原生 token 流不在本批范围内。
    """
    runner = _agent(request)
    events: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            run = runner.run(
                payload.question,
                payload.skill,
                payload.history,
                on_event=events.put,
            )
        except Exception as exc:  # noqa: BLE001 —— 错误也要以事件形式发出
            events.put({"event": "error", "message": str(exc)})
            events.put(None)
            return

        for offset in range(0, len(run.answer), 8):
            events.put({"event": "token", "text": run.answer[offset : offset + 8]})
            time.sleep(0.02)
        events.put(
            {
                "event": "done",
                "answer": run.answer,
                "skill": run.skill,
                "stop_reason": run.stop_reason,
                "tool_calls_count": run.tool_calls_count,
                "rounds": run.rounds,
                "latency_ms": run.latency_ms,
            }
        )
        events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generator():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ----------------------------------------------------------------- 异常处理


def install_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，保证所有错误都是 {error: {code, message}} 信封（§8）。

    在 main.create_app 中调用一次。
    """

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error_json(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 缺字段 / 类型错等：把 pydantic 的报错压成一行，避免把整个 detail 数组丢给前端
        message = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'][1:]) or 'body'}: {err['msg']}"
            for err in exc.errors()
        )
        return _error_json(422, "validation_error", message)

    @app.exception_handler(LLMError)
    async def _handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
        # 透传百炼的 code（如 invalid_api_key），方便前端直接定位 key/额度/地域问题
        logger.error("LLM 调用失败透传前端 code=%s", exc.code)
        return _error_json(502, exc.code, str(exc))

    @app.exception_handler(OpenAIError)
    async def _handle_openai_error(request: Request, exc: OpenAIError) -> JSONResponse:
        # Embedding 走 OpenAI 兼容协议，失败时是 OpenAIError，同样按上游失败处理
        code = _upstream_code(exc)
        logger.error("上游模型调用失败 code=%s", code)
        return _error_json(502, code, str(exc))

    @app.exception_handler(ValueError)
    async def _handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        # 代码里主动抛的 ValueError 都代表用户输入非法（doc_id 不存在、风格非法等）
        logger.warning("请求参数非法：%s", exc)
        return _error_json(400, "invalid_request", str(exc))

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常：%s", exc)
        return _error_json(500, "internal_error", str(exc))


def _error_json(status_code: int, code: str, message: str) -> JSONResponse:
    """构造统一错误信封 {error: {code, message}}。"""
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _upstream_code(exc: Exception) -> str:
    """从 OpenAI 兼容异常里挖出百炼的错误码，挖不到就退回 HTTP 状态码。

    百炼的报错体形状不固定（{"error": {"code": ...}} 或 {"code": ...}），
    这里逐一兜底，保证返回给前端的 code 总有排查价值。
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"])
        if body.get("code"):
            return str(body["code"])

    status = getattr(exc, "status_code", None)
    return str(status) if status is not None else "upstream_error"
