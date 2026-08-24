from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings, reset_settings
from app.db import reset_engine, session_scope
from app.kb import ensure_default_knowledge_base
from app.routers.chat import router as chat_router
from app.routers.documents import router as documents_router
from app.routers.knowledge_bases import router as kb_router
from app.routers.me import router as me_router
from app.routers.p1 import router as p1_router
from app.routers.search import router as search_router
from app.routers.tags import router as tags_router
from app.user import ensure_default_user


def create_app(*, load_file: bool = True, ensure_default: bool = True) -> FastAPI:
    get_settings(load_file=load_file)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if ensure_default:
            session = session_scope()
            try:
                ensure_default_knowledge_base(session)
                ensure_default_user(session)
            finally:
                session.close()
        yield

    app = FastAPI(title="知域", lifespan=lifespan)
    app.include_router(me_router)
    app.include_router(kb_router)
    app.include_router(documents_router)
    app.include_router(tags_router)
    app.include_router(search_router)
    app.include_router(chat_router)
    app.include_router(p1_router)

    @app.get("/health")
    def health():
        s = get_settings()
        return {
            "status": "ok",
            "ai_configured": s.ai_configured,
            "host": s.host,
        }

    return app


app = create_app()


def reset_app_state() -> None:
    reset_settings()
    reset_engine()
