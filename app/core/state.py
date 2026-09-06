"""Process-wide application state (engine, session factory, settings).

Kept in its own module so `http` and `auth` can both import it without a
circular dependency.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .db import make_engine, make_session_factory


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: Engine = make_engine(settings.database_url, echo=settings.db_echo)
        self.session_factory: sessionmaker | None = make_session_factory(self.engine)
        self.started_at = time.time()

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self.started_at, 1)

    def info(self) -> dict[str, Any]:
        return {
            "app_name": self.settings.app_name,
            "version": self.settings.app_version,
            "environment": self.settings.environment,
            "ai_mode": self.settings.ai_mode,
            "database": "sqlite" if self.settings.database_url.startswith("sqlite") else "other",
        }


app_state: AppState | None = None  # populated by set_app_state()


def set_app_state(state: AppState) -> None:
    global app_state
    app_state = state


def get_app_state() -> AppState:
    if app_state is None:  # pragma: no cover - defensive
        raise RuntimeError("Application state is not initialised yet.")
    return app_state
