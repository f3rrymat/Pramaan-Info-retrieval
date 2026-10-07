"""API smoke tests on the toy corpus (conftest forces IRLEGAL_MODE=toy). SHOW_TEXT stays off."""
import json

import pytest
from fastapi.testclient import TestClient

from app.server import app

client = TestClient(app)


def test_routers_load_and_the_web_app_is_served():
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and not h["router_errors"]
    for path in ("/", "/ui/main.js", "/ui/router.js", "/styles/tokens.css", "/fonts/inter-latin-wght-normal.woff2"):
        assert client.get(path).status_code == 200, path
    for gone in ("/api/panels", "/panels/results.js", "/app.js", "/styles.css", "/vendor/viz.js"):
        assert client.get(gone).status_code == 404, gone


def test_search_toy_and_errors():
    r = client.post("/api/search", json={"query_id": "Q-TE2", "k": 3}).json()
    assert r["source"] == "toy" and r["results"]
    assert client.post("/api/search", json={"text": "dowry death harassment", "k": 3}).json()["results"]
    assert client.post("/api/search", json={}).status_code == 422
    assert client.post("/api/search", json={"query_id": "nope"}).status_code == 404


def test_index_endpoints_toy():
    assert client.get("/api/index/stats").json()["source"] == "toy"
    r = client.get("/api/inspect/index", params={"term": "dowry"}).json()
    assert "zones" in r and r["source"] == "toy"


def test_eval_endpoints_never_fabricate():
    for name in ("summary", "ablation", "leakage", "efficiency", "zone_matrix"):
        r = client.get(f"/api/eval/{name}").json()
        assert "available" in r
        if not r["available"]:
            assert "PLACEHOLDER" in (r.get("status") or "")
    s = client.get("/api/eval/summary").json()
    assert "dev" in s and "test" in s


def test_text_hidden_unless_show_text(monkeypatch):
    monkeypatch.delenv("SHOW_TEXT", raising=False)
    from app.routers import _state
    assert _state.show_text() is False
    monkeypatch.setenv("SHOW_TEXT", "1")
    assert _state.show_text() is True
    assert len(_state.clip("x " * 500)) <= _state.SNIPPET_CHARS + 1
