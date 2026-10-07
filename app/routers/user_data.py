"""Saved searches / cases and search history, per user. Ids, parameters and timestamps only, never case text (D36)."""
import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import security as sec

router = APIRouter(prefix="/api", tags=["user-data"])
HISTORY_KEEP = 200


class Item(BaseModel):
    kind: str = "search"          # search | case
    ref: str                      # dev query id, doc id, or the literal "pasted"
    params: dict = {}


def _uid(request: Request) -> int:
    u = getattr(request.state, "user", None)
    if u is None:
        raise HTTPException(401, "Sign in required.")
    return u["id"]


def _clean(item: Item) -> dict:
    if item.kind not in ("search", "case") or not (sec.SAFE_REF.match(item.ref) or item.ref == "pasted"):
        raise HTTPException(422, "ref must be an id (letters, digits, . _ -) or 'pasted'; kind search or case")
    try:
        return sec.clean_params(item.params)
    except ValueError as e:
        raise HTTPException(422, str(e))


def _rows(rows):
    return [{"id": r["id"], "ref": r["ref"], "params": json.loads(r["params"]), "created_at": r["created_at"], **({"kind": r["kind"]} if "kind" in r.keys() else {})} for r in rows]


@router.get("/saved")
def saved(request: Request):
    return {"items": _rows(sec.connect().execute("SELECT * FROM saved WHERE user_id=? ORDER BY id DESC", (_uid(request),)).fetchall())}


@router.post("/saved")
def save(item: Item, request: Request):
    params = _clean(item)
    con = sec.connect()
    uid = _uid(request)
    dup = con.execute("SELECT id FROM saved WHERE user_id=? AND kind=? AND ref=? AND params=?", (uid, item.kind, item.ref, json.dumps(params, sort_keys=True))).fetchone()
    if dup:
        return {"id": dup["id"], "duplicate": True}
    cur = con.execute("INSERT INTO saved (user_id, kind, ref, params, created_at) VALUES (?,?,?,?,?)", (uid, item.kind, item.ref, json.dumps(params, sort_keys=True), time.time()))
    con.commit()
    return {"id": cur.lastrowid, "duplicate": False}


@router.delete("/saved/{item_id}")
def unsave(item_id: int, request: Request):
    con = sec.connect()
    con.execute("DELETE FROM saved WHERE id=? AND user_id=?", (item_id, _uid(request)))
    con.commit()
    return {"ok": True}


@router.get("/history")
def history(request: Request, limit: int = 50):
    return {"items": _rows(sec.connect().execute("SELECT * FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?", (_uid(request), max(1, min(limit, 200)))).fetchall())}


@router.post("/history")
def add_history(item: Item, request: Request):
    params = _clean(item)
    con, uid = sec.connect(), _uid(request)
    con.execute("INSERT INTO history (user_id, ref, params, created_at) VALUES (?,?,?,?)", (uid, item.ref, json.dumps(params, sort_keys=True), time.time()))
    con.execute("DELETE FROM history WHERE user_id=? AND id NOT IN (SELECT id FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?)", (uid, uid, HISTORY_KEEP))
    con.commit()
    return {"ok": True}


@router.delete("/history")
def clear_history(request: Request):
    con = sec.connect()
    con.execute("DELETE FROM history WHERE user_id=?", (_uid(request),))
    con.commit()
    return {"ok": True}
