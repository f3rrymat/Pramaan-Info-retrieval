"""Admin-only system status and user list (the middleware enforces the role). Aggregates and file metadata only."""
import platform
import time
from pathlib import Path

from fastapi import APIRouter

from irlegal.common.config import load_config, repo_path
from app import security as sec
from . import _state

router = APIRouter(prefix="/api/system", tags=["system"])
_START = time.time()


@router.get("/status")
def status():
    cfg = load_config()["paths"]
    res = repo_path(cfg["results_dir"])
    idx = repo_path(cfg["index_dir"])
    files = []
    if res.exists():
        files = sorted(({"name": p.name, "bytes": p.stat().st_size, "modified": p.stat().st_mtime} for p in res.glob("*.json")), key=lambda x: x["name"])
    con = sec.connect()
    return {"mode": _state.mode(), "show_text": _state.show_text(), "auth_required": sec.auth_required(), "python": platform.python_version(),
            "uptime_seconds": round(time.time() - _START), "index_present": (idx / "meta.json").exists(),
            "index_files": len(list(idx.glob("*"))) if idx.exists() else 0, "config_a_frozen": (res / "config_a_frozen.json").exists(),
            "final_test_run_done": (res / "final.lock").exists(), "result_files": files,
            "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "saved_items": con.execute("SELECT COUNT(*) FROM saved").fetchone()[0], "history_items": con.execute("SELECT COUNT(*) FROM history").fetchone()[0]}


@router.get("/users")
def users():
    rows = sec.connect().execute("SELECT username, role, created_at, last_login FROM users ORDER BY id").fetchall()
    return {"users": [dict(r) for r in rows]}
