"""Query Lab API on the toy corpus (conftest sets IRLEGAL_MODE=toy)."""
from fastapi.testclient import TestClient

from app.server import app

c = TestClient(app)


def test_parse_ok_and_error():
    r = c.post("/api/parse", json={"q": 'facts:murd* /3 "dowry death" court:SC'}).json()
    assert r["ok"] and r["parsed"]["op"] == "AND" and r["pretty"]
    bad = c.post("/api/parse", json={"q": "(murder"}).json()
    assert bad["ok"] is False and "')'" in bad["error"]
    st = c.post("/api/parse", json={"q": "Section 302 of the Indian Penal Code murder"}).json()
    assert "IPC_302" in st["statutes"]


def test_run_returns_ids_and_scores_only():
    r = c.post("/api/query/run", json={"q": "dowry", "k": 5}).json()
    assert r["ok"] and r["results"] and r["mode"] == "toy"
    for x in r["results"]:
        assert set(x) <= {"doc_id", "score", "court", "date"}          # no text fields without SHOW_TEXT
    assert [x["score"] for x in r["results"]] == sorted((x["score"] for x in r["results"]), reverse=True)
    assert c.post("/api/query/run", json={"q": "a OR"}).json()["ok"] is False


def test_suggestions():
    s = c.get("/api/suggest", params={"term": "dowr*"}).json()
    assert s["kind"] == "wildcard" and s["items"]
    sp = c.get("/api/suggest", params={"term": "dowrry"}).json()
    assert sp["kind"] == "spelling" and sp["items"][0]["term"] == "dowri"
