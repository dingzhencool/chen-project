from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import Base, engine
from app.core.exceptions import (
    BizException,
    biz_exception_handler,
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.api.v1 import api_router


def create_tables() -> None:
    from app.models import user  # noqa: F401
    from app.models import knowledge_base  # noqa: F401
    from app.models import document  # noqa: F401
    from app.models import conversation  # noqa: F401
    Base.metadata.create_all(bind=engine)


def replay_ready_documents() -> None:
    from app.core.database import SessionLocal
    from app.rag.pipeline import replay_all_ready_documents
    try:
        replay_all_ready_documents(SessionLocal)
    except Exception as e:
        from app.utils.logger import get_logger
        get_logger("app.startup").error("启动向量重放失败 err=%s", str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    replay_ready_documents()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    openapi_url="/openapi.json" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(BizException, biz_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
