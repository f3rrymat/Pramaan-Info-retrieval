"""Query-understanding endpoints. Owner: WS2.

POST /api/parse        parse tree, statute tokens and suggestions for a query string (syntax errors are returned, not raised)
POST /api/query/run    evaluate a Boolean / phrase / proximity query; ids and tf-idf scores only (text only with SHOW_TEXT=1)
GET  /api/suggest      wildcard expansions, spelling suggestions and Soundex variants for one word
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from irlegal.query.parser import QuerySyntaxError, parse, pretty, to_tree, words_of
from irlegal.query.statutes import RegexStatuteNormalizer
from . import _state

router = APIRouter(prefix="/api", tags=["ws2-query"])
_NORM = RegexStatuteNormalizer()


class ParseRequest(BaseModel):
    q: str


class RunRequest(BaseModel):
    q: str
    k: int = 20
    strategy: str = "df_order"


def suggestions_for(word: str, n: int = 8) -> dict:
    L = _state.light()
    w = word.lower().strip()
    if "*" in w:
        return {"word": word, "kind": "wildcard", "items": L.kg.wildcard(w)[:n]}
    stems = L.an.analyze(w)
    stem = stems[0] if stems else None
    out = {"word": word, "kind": "none", "items": []}
    if stem and stem not in L.df:
        sug = L.spell.suggest(stem, n=n)
        out.update(kind="spelling", items=sug)
    if stem:
        ph = [t for t in L.soundex.similar(w) if t != stem][:n]
        if ph:
            out["soundex"] = ph
    return out


@router.post("/parse")
def parse_query(req: ParseRequest):
    try:
        node = parse(req.q)
    except QuerySyntaxError as e:
        return {"input": req.q, "ok": False, "error": str(e), "parsed": None, "statutes": sorted(_NORM.extract(req.q)), "suggestions": []}
    words = []
    for w in words_of(node):
        if w not in words:
            words.append(w)
    return {"input": req.q, "ok": True, "parsed": to_tree(node), "pretty": pretty(node), "statutes": sorted(_NORM.extract(req.q)),
            "suggestions": [s for s in (suggestions_for(w) for w in words[:12]) if s["items"] or s.get("soundex")], "mode": _state.mode()}


@router.post("/query/run")
def run_query(req: RunRequest):
    L = _state.light()
    strategy = req.strategy if req.strategy in L.searchers else "df_order"
    try:
        res = L.searchers[strategy].search(req.q)
    except QuerySyntaxError as e:
        return {"ok": False, "error": str(e)}
    k = max(1, min(req.k, 100))
    ranked = L.searchers[strategy].rank(res, req.q, k)
    items = []
    for d, s in ranked:
        meta = L.index.meta(d)
        item = {"doc_id": d, "score": s, "court": meta.get("court"), "date": meta.get("date")}
        if _state.show_text():
            c = L.case(d)
            if c is not None:
                item["title"], item["snippet"] = c.title, _state.clip(c.text)
        items.append(item)
    return {"ok": True, "mode": L.mode, "strategy": strategy, "n_matches": int(len(res.docs)), "tree": res.tree, "trace": res.trace,
            "and_comparisons": res.stats.comparisons, "results": items,
            "note": "positions exist only for the facts and issues zones: phrase and proximity search those two"}


@router.get("/suggest")
def suggest(term: str):
    return suggestions_for(term)
