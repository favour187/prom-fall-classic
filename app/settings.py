"""Competition-specific settings (extends the shared foundation)."""

from app.core.config import Settings


class AppSettings(Settings):
    app_name: str = "Prom Fall Classic"
    app_version: str = "0.1.0"
