from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings, reset_settings
from app.db import reset_engine, session_scope
from app.rag.es_bm25 import EsNotConfiguredError
from app.kb import ensure_default_knowledge_base
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.chunk_settings import router as chunk_settings_router
from app.routers.documents import router as documents_router
from app.routers.knowledge_bases import router as kb_router
from app.routers.master import router as master_router
from app.routers.plans import router as plans_router
from app.routers.recommendations import router as recommendations_router
from app.routers.insights import router as insights_router
from app.routers.retrieval_debug import router as retrieval_debug_router
from app.routers.search import router as search_router
from app.routers.tags import router as tags_router
from app.routers.task import router as task_router
from app.routers.news import router as news_router
from app.scheduler.scheduler import shutdown_scheduler, start_scheduler
from app.user import ensure_default_user


def create_app(*, load_file: bool = True, ensure_default: bool = True) -> FastAPI:
    settings = get_settings(load_file=load_file)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if ensure_default:
            session = session_scope()
            try:
                user = ensure_default_user(session)
                ensure_default_knowledge_base(session, user.id)
            finally:
                session.close()
        start_scheduler()
        try:
            yield
        finally:
            shutdown_scheduler()

    app = FastAPI(title="知域", lifespan=lifespan)

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        path = request.url.path
        if (
            path == "/health"
            or path.startswith("/api/auth/login")
            or path.startswith("/api/auth/logout")
            or path.startswith("/docs")
            or path.startswith("/openapi")
            or path.startswith("/redoc")
        ):
            return await call_next(request)
        if path.startswith("/api/") and not request.session.get("user_id"):
            return JSONResponse(status_code=401, content={"detail": "未登录"})
        return await call_next(request)

    app.include_router(auth_router)
    app.include_router(kb_router)
    app.include_router(documents_router)
    app.include_router(tags_router)
    app.include_router(search_router)
    app.include_router(retrieval_debug_router)
    app.include_router(chunk_settings_router)
    app.include_router(chat_router)
    app.include_router(master_router)
    app.include_router(insights_router)
    app.include_router(recommendations_router)
    app.include_router(plans_router)
    app.include_router(task_router)
    app.include_router(news_router)

    @app.exception_handler(EsNotConfiguredError)
    def _es_not_configured(_request, exc: EsNotConfiguredError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        s = get_settings()
        return {
            "status": "ok",
            "ai_configured": s.ai_configured,
            "host": s.host,
        }

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="zhiyu_session",
        https_only=False,
        same_site="lax",
    )
    return app


app = create_app()


def reset_app_state() -> None:
    from app.agent.graph import reset_graph
    from app.agent.master import reset_master_graph

    reset_settings()
    reset_engine()
    reset_graph()
    reset_master_graph()
