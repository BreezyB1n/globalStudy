from __future__ import annotations

from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    code: Final[str] = "APP_ERROR"
    status_code: Final[int] = 500

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = code or self.code
        self.http_status = status_code or self.status_code


class ConfigError(AppError):
    code = "CONFIG_ERROR"


class InvalidRequestError(AppError):
    code = "INVALID_REQUEST"
    status_code = 400


class ThirdPartyServiceError(AppError):
    code = "THIRD_PARTY_SERVICE_ERROR"
    status_code = 502


class FileMissingError(AppError):
    code = "FILE_NOT_FOUND"
    status_code = 404


class DatabaseOperationError(AppError):
    code = "DATABASE_OPERATION_ERROR"
    status_code = 500


class KnowledgeBaseNotReadyError(AppError):
    code = "KNOWLEDGE_BASE_NOT_READY"
    status_code = 503


def build_error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "request_id": request_id,
        },
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return build_error_response(
            request,
            code=exc.error_code,
            message=exc.message,
            status_code=exc.http_status,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return build_error_response(
            request,
            code="INVALID_REQUEST",
            message=str(exc),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse | PlainTextResponse:
        if request.url.path.startswith("/api"):
            if exc.status_code == 404:
                return build_error_response(
                    request,
                    code="NOT_FOUND",
                    message="API route not found",
                    status_code=404,
                )
            return build_error_response(
                request,
                code="HTTP_ERROR",
                message=str(exc.detail),
                status_code=exc.status_code,
            )
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return build_error_response(
            request,
            code="INTERNAL_SERVER_ERROR",
            message="Internal server error",
            status_code=500,
        )
