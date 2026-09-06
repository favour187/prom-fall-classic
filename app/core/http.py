"""Application factory: wires config, logging, middleware, error handling,
database, auth and the health endpoint into a FastAPI app.

Each competition repository has a thin `app/main.py` that calls
`create_app(settings, extra_routers=[...])` with its own feature routers.
"""

from __future__ import annotations

import time
from typing import Any, Sequence

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from . import ai as ai_core
from .auth import bootstrap_demo_user, build_auth_router
from .config import Settings
from .db import init_db, make_engine
from .errors import error_envelope, install_error_handlers
from .logging import get_logger, setup_logging
from .ratelimit import RateLimitMiddleware
from .state import AppState, get_app_state, set_app_state

logger = get_logger("app.http")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", "")
        if not request_id:
            import uuid

            request_id = uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def create_app(
    settings: Settings,
    *,
    extra_routers: Sequence[APIRouter] | None = None,
    enable_rate_limit: bool = True,
    disable_auth: bool = False,
) -> FastAPI:
    """Build the FastAPI application for a competition repo."""
    setup_logging(debug=settings.debug, json_logs=settings.is_production)
    state = AppState(settings)
    set_app_state(state)
    if settings.auto_create_tables:
        init_db(state.engine)
    ai_core.install_gateway(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=f"{settings.api_prefix}/docs" if not settings.is_production else None,
        openapi_url=f"{settings.api_prefix}/openapi.json" if not settings.is_production else None,
    )

    # --- middleware ----------------------------------------------------
    app.add_middleware(RequestIDMiddleware)
    if enable_rate_limit:
        app.add_middleware(
            RateLimitMiddleware,
            limit_per_minute=settings.rate_limit_per_minute,
            trusted_proxy_headers=settings.trusted_proxy_headers,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- error handling ------------------------------------------------
    install_error_handlers(app, debug=settings.debug)

    # --- routes --------------------------------------------------------
    api = APIRouter(prefix=settings.api_prefix)

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "ai": ai_core.get_gateway().status(),
            "database": "sqlite" if settings.database_url.startswith("sqlite") else "other",
            "uptime_seconds": get_app_state().uptime_seconds,
        }

    @api.get("/meta/ai-status", tags=["meta"])
    def ai_status() -> dict[str, Any]:
        return ai_core.get_gateway().status()

    if not settings.is_production:

        @api.post("/demo/ai-ping", tags=["demo"])
        def demo_ai_ping(payload: dict[str, Any]) -> dict[str, Any]:
            """Small smoke-test endpoint proving the AI layer works."""
            prompt = str(payload.get("prompt", "Say hello."))
            result = ai_core.get_gateway().chat(
                system="You are a helpful assistant. Be concise.",
                user=prompt,
                max_tokens=200,
            )
            return result.to_dict()

    api.include_router(build_auth_router())
    if extra_routers:
        for router in extra_routers:
            api.include_router(router)
    app.include_router(api)

    @app.exception_handler(404)
    async def _api_404(request: Request, _exc: Exception) -> JSONResponse:
        # Only interfere with unknown /api paths; the SPA catch-all below
        # handles everything else.
        if request.url.path.startswith(settings.api_prefix):
            return JSONResponse(
                status_code=404,
                content=error_envelope("not_found", "Resource not found.", request_id=getattr(request.state, "request_id", None)),
            )
        raise _exc  # pragma: no cover

    # --- static web app (SPA), optional ---------------------------------
    if settings.static_dir:
        from pathlib import Path

        static_dir = Path(settings.static_dir)
        if static_dir.is_dir():
            index_file = static_dir / "index.html"
            if index_file.is_file():
                app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

                @app.get("/{path:path}", include_in_schema=False)
                async def spa_fallback(path: str):  # pragma: no cover - simple passthrough
                    if path.startswith(settings.api_prefix.lstrip("/")) or path == "api":
                        return JSONResponse(status_code=404, content=error_envelope("not_found", "Resource not found."))
                    candidate = static_dir / path
                    if candidate.is_file():
                        return FileResponse(candidate)
                    return FileResponse(index_file)

    # --- development conveniences ---------------------------------------
    if settings.environment == "development":
        bootstrap_demo_user()

    logger.info(
        "App '%s' v%s ready (env=%s, ai_mode=%s, db=sqlite)",
        settings.app_name,
        settings.app_version,
        settings.environment,
        settings.ai_mode,
    )
    return app
