"""Local, demo-grade sign-in (DECISIONS D37). Owner: app.

SQLite (data/app.db), scrypt password hashes with a per-user salt, HMAC-signed session cookie (HttpOnly, SameSite=Lax),
a secret generated on first run into data/, a sign-in rate limit. This is NOT dataset access control: the dataset's own
terms apply regardless. No password or secret is ever logged or written outside data/.
Environment: AUTH_REQUIRED=0 disables sign-in (video, tests); DEMO_ROLE picks the role used then (default admin);
IRLEGAL_APP_DB / IRLEGAL_APP_SECRET override the file locations (tests).
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Optional

from irlegal.common.config import repo_path

ROLES = ("researcher", "analyst", "admin")
COOKIE = "irl_session"
SESSION_SECONDS = 8 * 3600
SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
RATE_MAX, RATE_WINDOW = 5, 300
_lock = threading.Lock()
_failures: Dict[str, deque] = defaultdict(deque)

# path prefix -> roles allowed; anything under /api not listed here only needs a signed-in user
PUBLIC_PREFIXES = ("/api/health", "/api/auth/", "/api/public/")
ROLE_RULES = (("/api/system", {"admin"}), ("/api/index", {"admin"}), ("/api/inspect", {"admin"}), ("/api/eval", {"analyst", "admin"}), ("/api/results", {"analyst", "admin"}))


def auth_required() -> bool:
    return os.environ.get("AUTH_REQUIRED", "1") != "0"


def quick_login_enabled() -> bool:
    """Local demo convenience (DEMO_QUICK_LOGIN=1): sign in as a role with no password, from this machine only. Never for a shared or hosted server."""
    return os.environ.get("DEMO_QUICK_LOGIN") == "1"


def is_loopback(request) -> bool:
    """True only for a direct connection from this machine. Forwarding headers are deliberately ignored."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def quick_login_allowed(request) -> bool:
    return quick_login_enabled() and is_loopback(request)


def ensure_demo_users() -> None:
    """Create the three role users if missing, with random passwords that are never printed or stored anywhere readable."""
    con = connect()
    for role in ROLES:
        if con.execute("SELECT 1 FROM users WHERE username=?", (role,)).fetchone() is None:
            con.execute("INSERT INTO users (username, role, pw_hash, created_at) VALUES (?,?,?,?)", (role, role, hash_password(secrets.token_urlsafe(18)), time.time()))
    con.commit()


def db_path() -> Path:
    return Path(os.environ.get("IRLEGAL_APP_DB") or repo_path("data", "app.db"))


def secret_path() -> Path:
    return Path(os.environ.get("IRLEGAL_APP_SECRET") or repo_path("data", "app_secret.key"))


def connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
      CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, role TEXT NOT NULL,
        pw_hash TEXT NOT NULL, created_at REAL NOT NULL, last_login REAL);
      CREATE TABLE IF NOT EXISTS saved (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL,
        params TEXT NOT NULL, created_at REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, ref TEXT NOT NULL,
        params TEXT NOT NULL, created_at REAL NOT NULL);
    """)
    return con


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(h) // 2)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


_DUMMY = hash_password("dummy-to-equalise-timing")


def check_password(password: str, stored: str) -> bool:
    """Exact match first. A password pasted from a file or a terminal often carries a trailing space or newline, and the generated
    demo passwords never contain whitespace, so the whitespace-trimmed form is accepted too (checked only after the exact form fails)."""
    if verify_password(password, stored):
        return True
    trimmed = password.strip()
    return trimmed != password and bool(trimmed) and verify_password(trimmed, stored)


def _secret() -> bytes:
    p = secret_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    return p.read_bytes()


def make_token(user: sqlite3.Row, now: Optional[float] = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"u": user["id"], "exp": (now or time.time()) + SESSION_SECONDS}).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_token(token: str, now: Optional[float] = None) -> Optional[dict]:
    """Returns the payload, or {'expired': True} for a valid signature past its expiry, or None for anything else."""
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest(), sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < (now or time.time()):
            return {"expired": True}
        return data
    except Exception:
        return None


def guest_user() -> sqlite3.Row:
    con = connect()
    role = os.environ.get("DEMO_ROLE", "admin")
    role = role if role in ROLES else "admin"
    row = con.execute("SELECT * FROM users WHERE username='guest'").fetchone()
    if row is None:
        con.execute("INSERT INTO users (username, role, pw_hash, created_at) VALUES ('guest', ?, '!', ?)", (role, time.time()))
        con.commit()
        row = con.execute("SELECT * FROM users WHERE username='guest'").fetchone()
    elif row["role"] != role:
        con.execute("UPDATE users SET role=? WHERE id=?", (role, row["id"]))
        con.commit()
        row = con.execute("SELECT * FROM users WHERE username='guest'").fetchone()
    return row


def current_user(request) -> tuple:
    """(user_row | None, reason). reason is None, 'auth_required' or 'session_expired'."""
    if not auth_required():
        return guest_user(), None
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None, "auth_required"
    data = read_token(tok)
    if data is None:
        return None, "auth_required"
    if data.get("expired"):
        return None, "session_expired"
    row = connect().execute("SELECT * FROM users WHERE id=?", (data["u"],)).fetchone()
    return (row, None) if row else (None, "auth_required")


def rate_limited(key: str, now: Optional[float] = None) -> int:
    """Seconds to wait if this key has too many recent failures, else 0."""
    now = now or time.time()
    with _lock:
        q = _failures[key]
        while q and q[0] < now - RATE_WINDOW:
            q.popleft()
        return int(q[0] + RATE_WINDOW - now) + 1 if len(q) >= RATE_MAX else 0


def record_failure(key: str, now: Optional[float] = None) -> None:
    with _lock:
        _failures[key].append(now or time.time())


def clear_failures(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def check_request(request) -> Optional[tuple]:
    """Middleware policy. Returns None to allow, else (status, body). Stores the user on request.state."""
    path = request.url.path
    request.state.user = None
    if not path.startswith("/api/"):
        return None
    user, reason = current_user(request)
    request.state.user = user
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return None
    if user is None:
        return 401, {"detail": "Your session has expired. Sign in again." if reason == "session_expired" else "Sign in required.", "code": reason}
    if auth_required() and request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "irl":
        return 403, {"detail": "Missing request header.", "code": "csrf"}
    for prefix, roles in ROLE_RULES:
        if path.startswith(prefix) and user["role"] not in roles:
            return 403, {"detail": f"The {user['role']} role cannot open this page.", "code": "forbidden"}
    return None


SAFE_REF = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
PARAM_KEYS = {"ranker", "pruning", "filters", "temporal_filter", "weights", "k", "view"}
FILTER_KEYS = {"court", "year_from", "year_to"}


def clean_params(params: dict) -> dict:
    """Whitelist: parameters only, never text. Raises ValueError on anything else."""
    if not isinstance(params, dict) or set(params) - PARAM_KEYS:
        raise ValueError("unexpected parameter keys")
    out = {}
    for k, v in params.items():
        if k == "filters":
            if not isinstance(v, dict) or set(v) - FILTER_KEYS:
                raise ValueError("unexpected filter keys")
            for fk, fv in v.items():
                if not (isinstance(fv, (int, float, bool)) or (fk == "court" and isinstance(fv, list) and all(isinstance(c, str) and len(c) <= 8 for c in fv))):
                    raise ValueError("filters hold numbers and court codes only")
            out[k] = v
        elif k == "weights":
            if not isinstance(v, dict) or not all(isinstance(x, (int, float)) and k2 in ("text", "neighbour", "authority") for k2, x in v.items()):
                raise ValueError("weights must be numbers")
            out[k] = v
        elif k in ("ranker", "pruning", "view"):
            if not (isinstance(v, str) and len(v) <= 20):
                raise ValueError(f"{k} must be a short string")
            out[k] = v
        else:
            if not isinstance(v, (int, float, bool)):
                raise ValueError(f"{k} must be a number or boolean")
            out[k] = v
    return out
