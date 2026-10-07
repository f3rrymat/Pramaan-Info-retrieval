"""Regression: seed the demo users with the real script, then sign in with every credential through the API."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import security as sec
from app.server import app

ROOT = Path(__file__).resolve().parents[2]
H = {"X-Requested-With": "irl"}


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    db, creds = tmp_path / "app.db", tmp_path / "creds.txt"
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "IRLEGAL_APP_DB": str(db), "IRLEGAL_DEMO_CREDENTIALS": str(creds)}
    r = subprocess.run([sys.executable, "scripts/seed_demo_users.py"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("IRLEGAL_APP_DB", str(db))
    monkeypatch.setenv("IRLEGAL_APP_SECRET", str(tmp_path / "secret.key"))
    sec._failures.clear()
    users = {l.split()[0]: l.split()[1] for l in creds.read_text().splitlines() if l and not l.startswith("#")}
    return TestClient(app), users, r.stdout, creds


def signin(c, u, p):
    return c.post("/api/auth/signin", json={"username": u, "password": p}, headers=H)


def test_seed_script_prints_paths_not_secrets(seeded):
    _, users, out, creds = seeded
    assert str(creds) in out and "Database:" in out and "Verified 3/3" in out
    assert all(pw not in out for pw in users.values())
    assert oct(creds.stat().st_mode & 0o777) == "0o600" and set(users) == {"researcher", "analyst", "admin"}


def test_every_seeded_credential_signs_in_and_gets_its_role(seeded):
    c, users, *_ = seeded
    for name, pw in users.items():
        r = signin(c, name, pw)
        assert r.status_code == 200, name
        assert r.json()["user"] == {"username": name, "role": name}


def test_pasted_whitespace_and_username_case_do_not_break_sign_in(seeded):
    c, users, *_ = seeded
    pw = users["analyst"]
    for u, p in (("Analyst", pw), ("  analyst ", pw), ("analyst", pw + "\n"), ("analyst", " " + pw + " "), ("analyst", pw + "\r\n")):
        assert signin(c, u, p).status_code == 200, repr((u, p[-3:]))
    assert signin(c, "analyst", pw[:-1]).status_code == 401
    assert signin(c, "analyst", "   ").status_code == 401


def test_lockout_is_reported_distinctly_not_as_invalid(seeded):
    c, users, *_ = seeded
    for _ in range(5):
        r = signin(c, "researcher", "wrong-password")
        assert r.status_code == 401 and r.json()["code"] == "bad_credentials"
    r = signin(c, "researcher", users["researcher"])                    # even the right password is refused during a lockout
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and "Try again" in r.json()["detail"] and "Invalid" not in r.json()["detail"]
    assert int(r.headers["retry-after"]) > 0
    assert signin(c, "admin", users["admin"]).status_code == 200        # the lockout is per user name, not global
