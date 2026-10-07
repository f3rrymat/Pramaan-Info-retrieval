"""Sign-in, roles, saved/history, rate limit and the additive endpoints (toy mode, temp database)."""
import os
import stat
import time

import pytest
from fastapi.testclient import TestClient

from app import security as sec
from app.server import app

H = {"X-Requested-With": "irl"}


@pytest.fixture
def auth_on(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("IRLEGAL_APP_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("IRLEGAL_APP_SECRET", str(tmp_path / "secret.key"))
    sec._failures.clear()
    con = sec.connect()
    for name, role in (("researcher", "researcher"), ("analyst", "analyst"), ("admin", "admin")):
        con.execute("INSERT INTO users (username, role, pw_hash, created_at) VALUES (?,?,?,?)", (name, role, sec.hash_password(f"pw-{name}-1234"), time.time()))
    con.commit()
    return TestClient(app)


def signin(c, name, pw=None):
    return c.post("/api/auth/signin", json={"username": name, "password": pw or f"pw-{name}-1234"}, headers=H)


def test_scrypt_hash_is_salted_and_verifies():
    a, b = sec.hash_password("same"), sec.hash_password("same")
    assert a != b and a.startswith("scrypt$") and sec.verify_password("same", a) and not sec.verify_password("other", a)
    assert not sec.verify_password("x", "garbage")


def test_gate_blocks_anonymous_but_not_public(auth_on):
    c = auth_on
    assert c.get("/api/health").status_code == 200 and c.get("/api/public/headline").status_code == 200
    assert c.get("/api/public/headline").status_code == 200
    r = c.post("/api/search", json={"query_id": "Q-TE2"}, headers=H)
    assert r.status_code == 401 and r.json()["code"] == "auth_required"
    assert c.get("/api/auth/me").json()["user"] is None
    assert c.get("/api/eval/summary").status_code == 401


def test_signin_cookie_flags_and_me(auth_on):
    c = auth_on
    r = signin(c, "researcher")
    assert r.status_code == 200 and r.json()["user"] == {"username": "researcher", "role": "researcher"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "irl_session" in cookie
    assert "pw-researcher" not in r.text
    assert c.get("/api/auth/me").json()["user"]["role"] == "researcher"
    assert c.post("/api/search", json={"query_id": "Q-TE2", "k": 2}, headers=H).status_code == 200
    mode = stat.S_IMODE(os.stat(sec.secret_path()).st_mode)
    assert mode == 0o600


def test_bad_credentials_are_generic_and_rate_limited(auth_on):
    c = auth_on
    for _ in range(5):
        r = signin(c, "researcher", "wrong")
        assert r.status_code == 401 and r.json()["detail"] == "Invalid username or password."
    assert signin(c, "nobody", "x").json()["detail"] == "Invalid username or password."           # same message for unknown users
    r = signin(c, "researcher", "pw-researcher-1234")
    assert r.status_code == 429 and r.json()["retry_after"] > 0 and r.headers["retry-after"]


def test_roles_gate_dashboards(auth_on):
    c = auth_on
    signin(c, "researcher")
    assert c.get("/api/eval/summary").status_code == 403 and c.get("/api/system/status").status_code == 403 and c.get("/api/index/stats").status_code == 403
    assert signin(c, "analyst").status_code == 200
    assert c.get("/api/eval/summary").status_code == 200 and c.get("/api/system/status").status_code == 403 and c.get("/api/inspect/index", params={"term": "x"}).status_code == 403
    assert signin(c, "admin").status_code == 200
    assert c.get("/api/system/status").status_code == 200 and c.get("/api/index/stats").status_code == 200
    users = c.get("/api/system/users").json()["users"]
    assert {u["username"] for u in users} == {"researcher", "analyst", "admin"} and all("pw_hash" not in u for u in users)


def test_signout_and_expiry(auth_on, monkeypatch):
    c = auth_on
    signin(c, "researcher")
    c.post("/api/auth/signout", headers=H)
    assert c.get("/api/auth/me").json()["user"] is None
    row = sec.connect().execute("SELECT * FROM users WHERE username='researcher'").fetchone()
    old = sec.make_token(row, now=time.time() - sec.SESSION_SECONDS - 10)
    c.cookies.set(sec.COOKIE, old)
    r = c.get("/api/saved")
    assert r.status_code == 401 and r.json()["code"] == "session_expired"
    c.cookies.set(sec.COOKIE, old[:-3] + "abc")                                        # tampered signature
    assert c.get("/api/saved").json()["code"] == "auth_required"


def test_csrf_header_required_for_writes(auth_on):
    c = auth_on
    signin(c, "researcher")
    r = c.post("/api/saved", json={"kind": "search", "ref": "Q-TE2", "params": {}})
    assert r.status_code == 403 and r.json()["code"] == "csrf"


def test_saved_and_history_store_ids_and_parameters_only(auth_on):
    c = auth_on
    signin(c, "researcher")
    ok = c.post("/api/saved", json={"kind": "search", "ref": "Q-TE2", "params": {"ranker": "ours", "k": 10, "filters": {"court": ["SC"], "year_from": 1990}, "temporal_filter": True,
                                                                              "weights": {"text": 0.4, "neighbour": 0.5}}}, headers=H)
    assert ok.status_code == 200 and ok.json()["duplicate"] is False
    assert c.post("/api/saved", json={"kind": "search", "ref": "Q-TE2", "params": {"ranker": "ours", "k": 10, "filters": {"court": ["SC"], "year_from": 1990}, "temporal_filter": True,
                                                                                "weights": {"text": 0.4, "neighbour": 0.5}}}, headers=H).json()["duplicate"] is True
    for bad in ({"text": "the accused was charged with murder"}, {"filters": {"note": "x"}}, {"ranker": "x" * 50}, {"weights": {"text": "abc"}}):
        assert c.post("/api/history", json={"kind": "search", "ref": "Q-TE2", "params": bad}, headers=H).status_code == 422
    assert c.post("/api/history", json={"kind": "search", "ref": "a long sentence of case text", "params": {}}, headers=H).status_code == 422
    assert c.post("/api/history", json={"kind": "search", "ref": "pasted", "params": {"ranker": "ours"}}, headers=H).status_code == 200
    items = c.get("/api/saved").json()["items"]
    assert len(items) == 1 and items[0]["ref"] == "Q-TE2" and set(items[0]) >= {"id", "params", "created_at"}
    assert len(c.get("/api/history").json()["items"]) == 1
    # another user cannot see or delete it
    signin(c, "analyst")
    assert c.get("/api/saved").json()["items"] == []
    c.delete(f"/api/saved/{items[0]['id']}", headers=H)
    signin(c, "researcher")
    assert len(c.get("/api/saved").json()["items"]) == 1
    c.delete(f"/api/saved/{items[0]['id']}", headers=H)
    assert c.get("/api/saved").json()["items"] == []


def test_auth_off_runs_as_guest_with_demo_role(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    monkeypatch.setenv("IRLEGAL_APP_DB", str(tmp_path / "g.db"))
    monkeypatch.setenv("DEMO_ROLE", "analyst")
    c = TestClient(app)
    me = c.get("/api/auth/me").json()
    assert me["auth_required"] is False and me["user"] == {"username": "guest", "role": "analyst"}
    assert c.post("/api/search", json={"query_id": "Q-TE2", "k": 2}).status_code == 200


def test_additive_endpoints_toy_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    monkeypatch.setenv("IRLEGAL_APP_DB", str(tmp_path / "x.db"))
    c = TestClient(app)
    qm = c.get("/api/query_meta").json()
    assert qm["source"] == "toy" and "Q-TE2" in qm["items"] and set(qm["items"]["Q-TE2"]) == {"court", "year"}
    d = c.get("/api/case_detail/S04").json()
    assert d["doc_id"] == "S04" and "zone_sizes" in d and "title" not in d
    assert c.get("/api/case_detail/nope").status_code == 404
    o = c.post("/api/overlay", json={"query_id": "Q-TE2"}).json()
    assert o["evaluation_only"] is True and {"P@10", "R@10", "AP@100", "n_relevant"} <= set(o)
    h = c.get("/api/public/headline").json()
    assert "available" in h
    ab = c.get("/api/public/about").json()
    assert "available" in ab
    if ab["available"]:
        assert "Limitations" in ab["sections"]


def test_results_endpoint_is_whitelisted_and_role_gated(auth_on):
    c = auth_on
    signin(c, "researcher")
    assert c.get("/api/results/crawl_sim").status_code == 403
    signin(c, "analyst")
    assert c.get("/api/results/crawl_sim").status_code == 200
    assert c.get("/api/results/data_inspect").status_code == 404
    assert c.get("/api/results/..%2Fsecret").status_code in (404, 422)
    r = c.get("/api/public/pipeline").json()
    assert "available" in r
