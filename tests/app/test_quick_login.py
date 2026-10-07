"""Local demo quick sign-in: only with DEMO_QUICK_LOGIN=1 AND a loopback client; roles stay enforced; password sign-in unaffected."""
import time

import pytest
from fastapi.testclient import TestClient

from app import security as sec
from app.server import app

H = {"X-Requested-With": "irl"}
LOCAL = ("127.0.0.1", 50000)


class _AsClient:
    """ASGI wrapper that sets the peer address the app sees (this Starlette TestClient has no client= argument)."""

    def __init__(self, ip, port=50000):
        self.addr = (ip, port)

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope = {**scope, "client": self.addr}
        await app(scope, receive, send)


def TC(addr):
    return TestClient(_AsClient(*addr))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("IRLEGAL_APP_DB", str(tmp_path / "q.db"))
    monkeypatch.setenv("IRLEGAL_APP_SECRET", str(tmp_path / "q.key"))
    monkeypatch.delenv("DEMO_QUICK_LOGIN", raising=False)
    sec._failures.clear()
    return monkeypatch


def quick(client, role, headers=H):
    return client.post("/api/auth/quick", json={"role": role}, headers=headers)


@pytest.mark.parametrize("role", ["researcher", "analyst", "admin"])
def test_quick_sign_in_works_for_each_role_from_loopback(env, role):
    env.setenv("DEMO_QUICK_LOGIN", "1")
    c = TC(LOCAL)
    r = quick(c, role)
    assert r.status_code == 200 and r.json()["user"] == {"username": role, "role": role}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and sec.COOKIE in cookie
    me = c.get("/api/auth/me").json()
    assert me["user"]["role"] == role and me["quick_login"] is True
    assert c.post("/api/search", json={"query_id": "Q-TE2", "k": 2}, headers=H).status_code == 200


def test_ipv6_loopback_is_allowed(env):
    env.setenv("DEMO_QUICK_LOGIN", "1")
    assert quick(TC(("::1", 1)), "researcher").status_code == 200


def test_404_when_the_flag_is_off_even_from_loopback(env):
    c = TC(LOCAL)
    for role in ("researcher", "analyst", "admin"):
        assert quick(c, role).status_code == 404
    env.setenv("DEMO_QUICK_LOGIN", "0")
    assert quick(c, "admin").status_code == 404
    assert c.get("/api/auth/me").json()["quick_login"] is False
    assert c.get("/api/auth/me").json()["user"] is None


def test_404_when_the_client_is_not_loopback(env):
    env.setenv("DEMO_QUICK_LOGIN", "1")
    for ip in ("203.0.113.9", "192.168.1.20", "10.0.0.5", "testclient"):
        c = TC((ip, 4000))
        assert quick(c, "admin").status_code == 404, ip
        assert c.get("/api/auth/me").json()["quick_login"] is False
        assert c.get("/api/system/status").status_code == 401           # and no session was issued
    spoof = TC(("203.0.113.9", 4000))
    assert quick(spoof, "admin", {**H, "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"}).status_code == 404      # forwarding headers are ignored


def test_quick_sign_in_still_enforces_roles(env):
    env.setenv("DEMO_QUICK_LOGIN", "1")
    c = TC(LOCAL)
    quick(c, "researcher")
    for path in ("/api/eval/summary", "/api/results/crawl_sim", "/api/system/status", "/api/index/stats", "/api/inspect/index?term=x"):
        assert c.get(path).status_code == 403, path
    quick(c, "analyst")
    assert c.get("/api/eval/summary").status_code == 200 and c.get("/api/system/status").status_code == 403 and c.get("/api/index/stats").status_code == 403
    quick(c, "admin")
    assert c.get("/api/system/status").status_code == 200 and c.get("/api/index/stats").status_code == 200


def test_quick_endpoint_checks_header_and_role_value(env):
    env.setenv("DEMO_QUICK_LOGIN", "1")
    c = TC(LOCAL)
    assert quick(c, "admin", {}).status_code == 403
    assert quick(c, "superuser").status_code == 422


def test_users_are_created_on_demand_with_unknown_random_passwords(env, capsys):
    env.setenv("DEMO_QUICK_LOGIN", "1")
    assert sec.connect().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    c = TC(LOCAL)
    quick(c, "analyst")
    names = {r["username"] for r in sec.connect().execute("SELECT username FROM users")}
    assert names == {"researcher", "analyst", "admin"}
    for r in sec.connect().execute("SELECT username, pw_hash FROM users"):
        assert not sec.verify_password(r["username"], r["pw_hash"]) and not sec.verify_password("demo", r["pw_hash"])
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""                              # nothing printed, least of all a password
    ensure_before = {r["username"]: r["pw_hash"] for r in sec.connect().execute("SELECT username, pw_hash FROM users")}
    sec.ensure_demo_users()
    assert ensure_before == {r["username"]: r["pw_hash"] for r in sec.connect().execute("SELECT username, pw_hash FROM users")}      # existing users are left alone


def test_password_sign_in_still_works_with_the_flag_unset(env):
    con = sec.connect()
    con.execute("INSERT INTO users (username, role, pw_hash, created_at) VALUES (?,?,?,?)", ("analyst", "analyst", sec.hash_password("pw-analyst-1234"), time.time()))
    con.commit()
    c = TC(LOCAL)
    assert c.post("/api/auth/signin", json={"username": "analyst", "password": "pw-analyst-1234"}, headers=H).status_code == 200
    assert c.post("/api/auth/signin", json={"username": "analyst", "password": "nope"}, headers=H).status_code == 401
    assert c.get("/api/eval/summary").status_code == 200


def test_startup_creates_users_only_when_the_flag_is_on(env):
    from app.server import _seed_quick_login_users
    _seed_quick_login_users()
    assert sec.connect().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    env.setenv("DEMO_QUICK_LOGIN", "1")
    _seed_quick_login_users()
    assert sec.connect().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
