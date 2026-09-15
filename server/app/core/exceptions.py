import traceback

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ApiResponse
from app.utils.logger import logger


class BizException(HTTPException):
    def __init__(self, code: int = 400, message: str = "Bad Request", status_code: int = 200):
        self.code = code
        self.message = message
        super().__init__(status_code=status_code, detail=message)


async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
    client = request.client.host if request.client else "unknown"
    logger.warning(
        "[BizException] path=%s method=%s client=%s code=%s message=%s",
        request.url.path, request.method, client, exc.code, exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(code=exc.code, message=exc.message, data=None).model_dump(),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    client = request.client.host if request.client else "unknown"
    logger.warning(
        "[HTTPException] path=%s method=%s client=%s status_code=%s detail=%s",
        request.url.path, request.method, client, exc.status_code, str(exc.detail),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            code=exc.status_code,
            message=str(exc.detail),
            data=None,
        ).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    client = request.client.host if request.client else "unknown"
    errors = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        errors.append(f"{field}: {err.get('msg', '')}")
    logger.warning(
        "[ValidationError] path=%s method=%s client=%s errors=%s",
        request.url.path, request.method, client, " | ".join(errors),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ApiResponse(
            code=422,
            message=" | ".join(errors) if errors else "Validation Error",
            data=None,
        ).model_dump(),
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    client = request.client.host if request.client else "unknown"
    logger.error(
        "[UnhandledException] path=%s method=%s client=%s error_type=%s error=%s\n%s",
        request.url.path, request.method, client, type(exc).__name__, str(exc), traceback.format_exc(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ApiResponse(
            code=500,
            message=f"Internal Server Error: {str(exc)}",
            data=None,
        ).model_dump(),
    )
