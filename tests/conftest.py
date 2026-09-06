import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.testing import make_settings  # noqa: E402
from app.main import build_app  # noqa: E402


@pytest.fixture()
def client():
    """Test client wired exactly like production (incl. feature routers)."""
    with TestClient(build_app(make_settings())) as c:
        yield c
