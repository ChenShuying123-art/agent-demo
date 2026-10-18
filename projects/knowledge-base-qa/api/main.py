"""FastAPI 应用入口（spec §8 / §6）。

职责边界：只负责**装配**——把 kbqa 的各组件组装成应用级单例、注册路由与异常处理、
    托管接口文档资源（/docs 本地自托管，不依赖 CDN）、并在构建产物存在时托管前端静态文件。
    **不包含任何业务逻辑**。

为什么把 pipeline / store 放在 app.state（而不是模块级全局变量）：
    它们是"每个应用实例一份"的状态，挂在 app.state 上最自然，也让测试可以替换
    （TestClient 建应用时能看到同一套装配逻辑），避免模块级全局变量在多进程/多测试下互相污染。
    注意 pipeline 与 store 必须共享同一个 store 实例——pipeline 索引写入的内存索引，
    删除接口要能立刻看到，否则会出现"索引了却删不掉向量"的不一致。

启动方式：uvicorn api.main:app --reload
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from kbqa.agent import create_agent_runner
from kbqa.config import settings
from kbqa.embeddings import get_embedding_provider
from kbqa.llm import get_llm
from kbqa.mcp_client import register_mcp_tools
from kbqa.pipeline import RAGPipeline
from kbqa.rerank import get_reranker
from kbqa.skills import SkillLoader
from kbqa.tools import ToolRegistry
from kbqa.tools.datetime_tool import get_datetime
from kbqa.tools.kb_tool import build_kb_tool
from kbqa.tools.weather import build_weather_tool
from kbqa.tools.web_search import build_web_search_tool
from kbqa.vectorstore import VectorStore

from api.routes import install_exception_handlers, router

logger = logging.getLogger(__name__)

# 前端构建产物目录（§9.1 生产模式：npm run build 产出 web/dist，由本服务托管）
_WEB_DIST = Path("web") / "dist"

# 本地托管的接口文档资源：FastAPI 默认的 /docs 会从 jsdelivr CDN 加载 Swagger UI，
# 在访问不到该 CDN 的网络里页面会白屏，所以把资源放进仓库、由本服务自己发。
_STATIC_DIR = Path("api") / "static"
_SWAGGER_DIR = _STATIC_DIR / "swagger_ui"
_CDN_JS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
_CDN_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"


def create_app() -> FastAPI:
    """装配并返回 FastAPI 应用。"""
    # 1) 向量库：从 data/index 恢复已有索引（文件不存在时得到空索引，不报错）
    store = VectorStore.load(settings.data_dir / "index")

    # 2) 各能力实现：embedding / rerank / llm 都走工厂函数，便于按配置切换（NFR-2）
    #    rerank_enabled=False 时 get_reranker 返回 None，pipeline 会自动降级为"直接截断"
    llm = get_llm(settings)
    pipeline = RAGPipeline(
        settings=settings,
        store=store,
        embedder=get_embedding_provider(settings),
        reranker=get_reranker(settings),
        llm=llm,
    )

    # Agent：工具注册表 + 手写 loop（T18）；知识库工具复用同一个 pipeline 实例
    registry = ToolRegistry()
    registry.register(get_datetime)
    registry.register(build_kb_tool(pipeline, settings.agent_tool_result_max_chars))
    registry.register(build_web_search_tool(settings))
    registry.register(build_weather_tool(settings))
    # MCP 工具：默认关闭；失败只丢该批工具，不影响本地工具
    register_mcp_tools(registry, settings)
    # Skill：启动时只读 front-matter；正文在 load_skill / 显式指定时才注入
    skills = SkillLoader(settings.skills_dir)
    skills.load_all()
    agent = create_agent_runner(settings, registry, llm, skills)
    logger.info("Agent 引擎=%s 工具=%s", settings.agent_engine, registry.names())

    # docs_url=None：关掉 FastAPI 自带的（依赖 CDN 的）/docs，改由下面注册的本地版接管
    app = FastAPI(title="知识库问答 Agent", version="1.0.0", docs_url=None)

    # 3) 挂应用级单例：路由通过 request.app.state 取用（见 routes._pipeline / _store / _agent）
    app.state.settings = settings
    app.state.store = store
    app.state.pipeline = pipeline
    app.state.agent = agent
    app.state.skills = skills

    # 4) 注册统一异常处理与业务路由
    install_exception_handlers(app)
    app.include_router(router)

    # 5) 接口文档页：自己注册 /docs，指向本地托管的 Swagger UI 资源（缺失时回退 CDN）
    if _SWAGGER_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
        js_url = "/static/swagger_ui/swagger-ui-bundle.js"
        css_url = "/static/swagger_ui/swagger-ui.css"
        icon_url = "/static/swagger_ui/favicon-32x32.png"
        logger.info("已启用本地 Swagger UI 资源 目录=%s", _SWAGGER_DIR)
    else:
        js_url, css_url = _CDN_JS, _CDN_CSS
        icon_url = "https://fastapi.tiangolo.com/img/favicon.png"
        logger.warning("未找到本地 Swagger UI 资源，/docs 将回退到 CDN")

    @app.get("/docs", include_in_schema=False)
    async def swagger_docs():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} · 接口文档",
            swagger_js_url=js_url,
            swagger_css_url=css_url,
            swagger_favicon_url=icon_url,
        )

    # 6) 托管前端静态资源（可选）：web/dist 存在才挂载，避免 T11 未构建时启动报错。
    #    必须放在 include_router 与 /docs、/static 之后——mount("/") 会兜住所有未匹配路径，
    #    先注册具体路由才能保证 /api/* 与文档页不被静态目录抢走。
    if _WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
        logger.info("已挂载前端静态目录 %s", _WEB_DIST)
    else:
        logger.info("未找到 %s，跳过前端静态托管（开发模式请用 Vite dev server）", _WEB_DIST)

    logger.info("Agent 已装配 工具=%s max_steps=%d", registry.names(), settings.agent_max_steps)
    logger.info("Skill 已加载 数量=%d 名称=%s", len(skills.names()), skills.names())
    logger.info(
        "API 服务已装配 chat_model=%s embedding_model=%s rerank_model=%s rerank_enabled=%s",
        settings.chat_model,
        settings.embedding_model,
        settings.rerank_model,
        settings.rerank_enabled,
    )
    return app


app = create_app()
