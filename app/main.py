from __future__ import annotations

import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_runtime_directories()
    configure_logging(settings)

    app = FastAPI(title=settings.app_name)
    register_exception_handlers(app)

    request_logger = get_logger("globalstudy.request")
    app_logger = get_logger("globalstudy.app")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            request_logger.exception(
                "Unhandled request exception path=%s method=%s",
                request.url.path,
                request.method,
                extra={"request_id": request_id},
            )
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        request_logger.info(
            "Completed request method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response

    app.include_router(api_router)
    _mount_frontend(app, settings, app_logger)
    return app


def _mount_frontend(app: FastAPI, settings: Settings, app_logger) -> None:
    frontend_dir = settings.frontend_dir
    assets_dir = frontend_dir

    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    app_logger.info(
        "Application initialized env=%s frontend_dir=%s",
        settings.app_env,
        str(frontend_dir),
        extra={"request_id": "-"},
    )


app = create_app()
