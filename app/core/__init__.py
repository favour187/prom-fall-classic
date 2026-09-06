"""Hackathon foundation — reusable, competition-agnostic Python backend library.

This package intentionally contains NO competition-specific logic. It provides
configuration, logging, error handling, HTTP middleware, database, auth, AI
integration and testing utilities that each competition repository shares and
extends with its own `app/features/<name>/` modules.
"""

__version__ = "0.1.0"
