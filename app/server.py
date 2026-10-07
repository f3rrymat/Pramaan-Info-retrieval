"""FastAPI shell. Owner: WS2 (created in Phase 0; Phase D added the data-mode report in /api/health).

Auto-discovery means no workstream ever edits this file to add features:
  * every module in app/routers/ that defines `router` is included;
  * the web app is static files under app/web (index.html, ui/, styles/, fonts/); there is no panel registry.

Run:  PYTHONPATH=src uvicorn app.server:app --reload     (or: make demo)
"""
import importlib
from contextlib import asynccontextmanager
import logging
import pkgutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.routers as routers_pkg
from app import security
from irlegal import __version__

log = logging.getLogger("irlegal.server")
WEB_DIR = Path(__file__).resolve().parent / "web"

def _seed_quick_login_users():
    """Startup hook: with DEMO_QUICK_LOGIN=1 make sure the three role users exist (random passwords, never printed)."""
    if security.quick_login_enabled():
        security.ensure_demo_users()


@asynccontextmanager
async def lifespan(_app):
    _seed_quick_login_users()
    yield


app = FastAPI(title="Pramaan API", version=__version__, lifespan=lifespan)
_loaded, _failed = [], {}


def _discover_routers() -> None:
    for info in sorted(pkgutil.iter_modules(routers_pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        name = f"{routers_pkg.__name__}.{info.name}"
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # one broken router must not take the app down
            log.exception("router %s failed to import", name)
            _failed[info.name] = repr(exc)
            continue
        router = getattr(module, "router", None)
        if router is None:
            _failed[info.name] = "no `router` attribute"
            continue
        app.include_router(router)
        _loaded.append(info.name)


# D40: the browser loads nothing remote and talks only to this server (the assistant calls Sarvam server-side).
# Styles allow inline attributes (the UI sets style properties on nodes); scripts are files only. Audio plays from blob: URLs.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; "
       "connect-src 'self'; media-src 'self' blob:; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {"Content-Security-Policy": CSP, "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
                    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Sign-in and role gate for /api (DECISIONS D37). AUTH_REQUIRED=0 turns the gate into a pass-through."""
    denied = security.check_request(request)
    if denied:
        resp = JSONResponse(denied[1], status_code=denied[0])
    else:
        resp = await call_next(request)
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


@app.get("/api/health")
def health():
    mode, show_text = "unknown", False
    try:
        from app.routers import _state
        mode, show_text = _state.mode(), _state.show_text()
    except Exception:  # health must answer even if the data layer is broken
        log.exception("could not read data mode")
    return {"status": "ok", "version": __version__, "routers": _loaded, "router_errors": _failed,
            "mode": mode, "show_text": show_text}


_discover_routers()
# Mounted last so /api/* routes win.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
