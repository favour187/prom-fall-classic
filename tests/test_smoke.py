"""Smoke tests: the scaffold's wiring works (health, auth, AI, feature router)."""

from app.core.testing import auth_headers, create_user


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "ai" in body


def test_feature_router(client):
    res = client.get("/api/event/status")
    assert res.status_code == 200
    assert res.json()["feature"] == "event"


def test_auth_flow(client):
    data = create_user(client, email="smoke@example.com")
    me = client.get("/api/auth/me", headers=auth_headers(data["token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "smoke@example.com"


def test_ai_ping(client):
    res = client.post("/api/demo/ai-ping", json={"prompt": "hello"})
    assert res.status_code == 200
    body = res.json()
    assert body["text"]
    assert body["provider"] == "local-demo"  # test env has no key
