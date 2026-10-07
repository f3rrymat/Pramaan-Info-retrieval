"""Sign-in endpoints (local demo-grade auth, DECISIONS D37). Not dataset access control."""
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import security as sec
from . import _state

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignIn(BaseModel):
    username: str
    password: str


def _user_json(u):
    return {"username": u["username"], "role": u["role"]}


@router.post("/signin")
def signin(body: SignIn, request: Request):
    if not sec.auth_required():
        return {"user": _user_json(sec.guest_user()), "auth_required": False}
    uname = body.username.strip().lower()[:40]
    key = f"{request.client.host if request.client else '?'}|{uname}"
    wait = sec.rate_limited(key)
    if wait:
        return JSONResponse({"detail": f"Too many failed attempts. Try again in {wait} s.", "code": "rate_limited", "retry_after": wait}, status_code=429,
                            headers={"Retry-After": str(wait)})
    con = sec.connect()
    row = con.execute("SELECT * FROM users WHERE username=?", (uname,)).fetchone()
    ok = sec.check_password(body.password, row["pw_hash"] if row else sec._DUMMY) and row is not None
    if not ok:
        sec.record_failure(key)
        return JSONResponse({"detail": "Invalid username or password.", "code": "bad_credentials"}, status_code=401)
    sec.clear_failures(key)
    con.execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), row["id"]))
    con.commit()
    resp = JSONResponse({"user": _user_json(row), "auth_required": True, "expires_in": sec.SESSION_SECONDS})
    resp.set_cookie(sec.COOKIE, sec.make_token(row), max_age=sec.SESSION_SECONDS, httponly=True, samesite="lax", path="/")
    return resp


class Quick(BaseModel):
    role: str


@router.post("/quick")
def quick_signin(body: Quick, request: Request):
    """Local demo quick sign-in. 404 (as if it did not exist) unless DEMO_QUICK_LOGIN=1 AND the client is a loopback address."""
    if not sec.quick_login_allowed(request):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if request.headers.get("x-requested-with") != "irl":
        return JSONResponse({"detail": "Missing request header.", "code": "csrf"}, status_code=403)
    if body.role not in sec.ROLES:
        return JSONResponse({"detail": "Unknown role."}, status_code=422)
    sec.ensure_demo_users()
    con = sec.connect()
    row = con.execute("SELECT * FROM users WHERE username=?", (body.role,)).fetchone()
    con.execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), row["id"]))
    con.commit()
    resp = JSONResponse({"user": _user_json(row), "auth_required": True, "expires_in": sec.SESSION_SECONDS, "quick": True})
    resp.set_cookie(sec.COOKIE, sec.make_token(row), max_age=sec.SESSION_SECONDS, httponly=True, samesite="lax", path="/")
    return resp


@router.post("/signout")
def signout(response: Response):
    r = JSONResponse({"ok": True})
    r.delete_cookie(sec.COOKIE, path="/")
    return r


@router.get("/me")
def me(request: Request):
    user, reason = sec.current_user(request)
    return {"auth_required": sec.auth_required(), "user": _user_json(user) if user else None, "reason": reason,
            "mode": _state.mode(), "show_text": _state.show_text(), "quick_login": sec.quick_login_allowed(request)}
