"""Application entry point for Prom Fall Classic.

Run locally:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.core.config import Settings
from app.core.http import create_app
from app.features.event.routers import router as feature_router
from app.settings import AppSettings


def build_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; pass test settings in tests, otherwise use the env."""
    settings = settings or AppSettings.from_env()
    return create_app(settings, extra_routers=[feature_router])


app = build_app()
