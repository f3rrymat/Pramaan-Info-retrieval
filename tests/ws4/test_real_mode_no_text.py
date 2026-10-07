"""In real mode, with SHOW_TEXT unset, no API response may carry case text or titles. Skipped without the real index."""
import os

import pytest

from irlegal.common.config import load_config, repo_path

CFG = load_config()["paths"]
HAVE = repo_path(CFG["index_dir"], "meta.json").exists() and repo_path(CFG["results_dir"], "config_a_frozen.json").exists()
pytestmark = pytest.mark.skipif(not HAVE, reason="real index not built on this machine")


def _texts(obj, path=""):
    """Yield (path, value) for any non-empty value under a text-like key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("title", "snippet", "text") and isinstance(v, str) and v.strip():
                yield f"{path}/{k}", v
            yield from _texts(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _texts(v, f"{path}[{i}]")


def test_real_mode_returns_no_text(monkeypatch):
    monkeypatch.delenv("SHOW_TEXT", raising=False)
    monkeypatch.setenv("IRLEGAL_MODE", "real")
    from fastapi.testclient import TestClient
    from app.server import app
    c = TestClient(app)
    h = c.get("/api/health").json()
    assert h["mode"] == "real" and h["show_text"] is False
    qs = c.get("/api/queries").json()
    assert qs["source"] == "real" and not list(_texts(qs))
    qid = qs["queries"][0]["qid"]
    for body in ({"query_id": qid, "ranker": "ours", "temporal_filter": True, "k": 5}, {"query_id": qid, "ranker": "bm25", "pruning": "champion", "k": 5},
                 {"text": "murder trial dowry death witness hostile", "ranker": "tfidf", "k": 5}):
        r = c.post("/api/search", json=body).json()
        assert r["source"] == "real" and r["results"] and not list(_texts(r)), body
    assert c.post("/api/search", json={"query_id": "123456789"}).status_code == 404
    q = c.post("/api/query/run", json={"q": "murder /3 knife court:SC", "k": 5}).json()
    assert q["ok"] and q["mode"] == "real" and not list(_texts(q))
    assert not list(_texts(c.get("/api/case/" + q["results"][0]["doc_id"]).json()))
    assert not list(_texts(c.post("/api/parse", json={"q": "murdr*"}).json()))
