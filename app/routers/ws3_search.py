"""Search endpoints. Owner: WS3. Real pipeline when available (Config A), toy ranker otherwise.

POST /api/search  {text | query_id (dev only), ranker: tfidf|bm25|ours, pruning: none|champion|tier|elimination,
                   filters: {court: [SC,HC,OTHER], year_from, year_to}, temporal_filter, weights, k<=100}
Returns top-k with normalised components (so the UI can re-weight client-side), neighbour ids and explanations.
Titles and snippets (<= 200 chars) only with SHOW_TEXT=1. The test split is never reachable from here.
"""
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from irlegal.common.schema import QUERY_ZONES, SPLITS, Query
from irlegal.common.toy import toy_bundle
from . import _state

router = APIRouter(prefix="/api", tags=["ws3-search"])
FEATURES = ("text", "neighbour", "authority")
_cache: Dict = {}


class StageTimer:
    """Wall time per pipeline stage, reported in a Server-Timing header (the JSON body is unchanged). Phase F, task 8."""

    def __init__(self):
        self.rows: List[tuple] = []

    @contextmanager
    def stage(self, name: str, desc: str = ""):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.rows.append((name, (time.perf_counter() - t0) * 1000, desc))

    def note(self, name: str, desc: str, dur: Optional[float] = None):
        self.rows.append((name, dur, desc))

    def header(self) -> str:
        out = []
        for name, dur, desc in self.rows:
            part = name + (f";dur={dur:.2f}" if dur is not None else "")
            if desc:
                part += ';desc="' + desc.replace('"', "'").replace(",", ";") + '"'
            out.append(part)
        return ", ".join(out)


class SearchRequest(BaseModel):
    text: Optional[str] = None
    query_id: Optional[str] = None
    ranker: str = "ours"
    pruning: str = "none"
    filters: Dict = {}
    temporal_filter: bool = False
    weights: Dict[str, float] = {}
    k: int = 10


def _dev_queries():
    c = _state.ctx()
    if "dev" not in _cache:
        _cache["dev"] = {q.qid: q for q in c.corpus.queries("val")}
    return _cache["dev"]


@router.get("/queries")
def list_queries():
    if _state.mode() == "toy":
        corpus, _, _ = toy_bundle()
        return {"source": "toy", "queries": [
            {"qid": q.qid, "split": q.split, "title": corpus.get_case(q.case_id).title, "text": q.text}
            for s in SPLITS for q in corpus.queries(s)]}
    st = _state.show_text()
    return {"source": "real", "show_text": st, "queries": [
        {"qid": q.qid, "split": "val", "date": q.date, "n_relevant": len(q.relevant),
         "title": "", "text": q.text if st else ""} for q in _dev_queries().values()]}


def _toy_search(req: SearchRequest, timer: Optional[StageTimer] = None):
    timer = timer or StageTimer()
    corpus, index, ranker = toy_bundle()
    t_query = timer.stage("query")
    t_query.__enter__()
    if req.query_id:
        found = [q for s in SPLITS for q in corpus.queries(s) if q.qid == req.query_id]
        if not found:
            raise HTTPException(404, f"unknown query_id {req.query_id}")
        query = found[0]
    elif req.text:
        query = Query(qid="adhoc", case_id="adhoc", text=req.text, zones={z: "" for z in QUERY_ZONES} | {"facts": req.text},
                      statutes=set(), date=None, split="adhoc", relevant=set())
    else:
        t_query.__exit__(None, None, None)
        raise HTTPException(422, "give text or query_id")
    t_query.__exit__(None, None, None)
    timer.note("scrub", "toy corpus: no citation strings to remove")
    with timer.stage("rank", "toy ranker: first stage; features and net score in one step"):
        results = ranker.rank(query, req.k)
    with timer.stage("explain"):
        out = {"source": "toy", "ranker": ranker.name, "qid": query.qid, "results": [
            {"doc_id": r.doc_id, "score": r.score, "components": r.components, "explanation": r.explanation,
             "meta": index.meta(r.doc_id), "relevant": r.doc_id in query.relevant} for r in results]}
    return out


def _selectors(c):
    if "sel" not in _cache:
        from irlegal.efficiency.champions import ChampionSelector
        from irlegal.efficiency.elimination import EliminationSelector
        from irlegal.efficiency.scoring import TextScorer
        from irlegal.efficiency.tiers import TierSelector
        sc = TextScorer(c)
        _cache["sel"] = {"sc": sc, "champion": ChampionSelector(sc, 200), "tier": TierSelector(sc, c.graph.base.astype(np.float32)),
                         "elimination": EliminationSelector(sc, 1.0, 1)}
    return _cache["sel"]


def _real_search(req: SearchRequest, timer: Optional[StageTimer] = None):
    """Unchanged ranking; only the order of independent steps differs so each stage can be timed (Phase F): the tf-idf
    text matrix is computed first and handed to Context.features via text_override, which gives the same matrices."""
    from irlegal.ranking import netscore as ns
    from irlegal.ranking.explain import explain_result
    timer = timer or StageTimer()
    c = _state.ctx()
    k = max(1, min(req.k, 100))
    with timer.stage("query"):
        if req.query_id:
            q = _dev_queries().get(req.query_id)
            if q is None:
                raise HTTPException(404, f"unknown dev query_id {req.query_id} (only the dev split is served)")
        elif req.text and req.text.strip():
            q = Query(qid="adhoc", case_id="adhoc", text=req.text, zones={}, statutes=set(), date=None, split="adhoc", relevant=set())
        else:
            raise HTTPException(422, "give text or query_id")
    if req.ranker not in ("tfidf", "bm25", "ours"):
        raise HTTPException(422, "ranker must be tfidf, bm25 or ours")
    if req.query_id:
        timer.note("scrub", "done when the corpus was read (dev queries are scrubbed at load)", 0.0)
    else:
        timer.note("scrub", "not applied to pasted text by this endpoint")
    with timer.stage("first_stage", "tf-idf over the pool; pruning; filters; top 1000"):
        text_full = c.text_matrix([q.text])
        own = c.own_idx([q])
        n = c.n
        allowed = np.ones((1, n), bool)
        if own[0] >= 0:
            allowed[0, own[0]] = False
        scored = n
        if req.pruning != "none":
            if req.pruning not in ("champion", "tier", "elimination"):
                raise HTTPException(422, "pruning must be none, champion, tier or elimination")
            s = _selectors(c)
            rows, w = s["sc"].query_terms(q.text)
            if req.pruning == "champion":
                pm = s["champion"].select_mask(rows)
            elif req.pruning == "tier":
                pm = s["tier"].select_mask(rows, 20)[0]
            else:
                ids = s["elimination"].select(q, 20)
                pm = s["sc"].doc_mask(ids) if ids else np.ones(n, bool)
            allowed[0] &= pm
            scored = int(allowed.sum())
        f = req.filters or {}
        if f.get("court"):
            allowed[0] &= np.array([ct in f["court"] for ct in [x.court for x in c.cases]])
        years = np.array([int(d[:4]) if d and d[:4].isdigit() else -1 for d in c.doc_dates])
        if f.get("year_from") is not None:
            allowed[0] &= (years >= int(f["year_from"])) | (years < 0)
        if f.get("year_to") is not None:
            allowed[0] &= (years <= int(f["year_to"])) | (years < 0)
        temporal = bool(req.temporal_filter and q.date)
        if temporal:
            allowed &= ~c.removed_by_date([q])
        mask = ns.union_candidates([(np.where(allowed, text_full, -1.0), 1000)], c.tie, own) & allowed if req.ranker == "ours" else None
    with timer.stage("features", "neighbour vote and authority with leave-one-out" + ("; BM25" if req.ranker == "bm25" else "")):
        F = c.features([q], loo=True, bm25=req.ranker == "bm25", text_override=text_full)
    with timer.stage("net", "min-max per feature; weighted sum" if req.ranker == "ours" else "single text score"):
        text = np.where(allowed, F["text"], 0.0)
        weights = {k_: float(v) for k_, v in (req.weights or c.config_a()).items() if k_ in FEATURES}
        tot = sum(weights.values()) or 1.0
        weights = {k_: v / tot for k_, v in weights.items()}
        comps_full = None
        if req.ranker == "ours":
            Fm = dict(F); Fm["text"] = text
            net = c.net(Fm, mask, weights)[0]
            comps_full = {f_: ns.minmax_masked(Fm[f_], mask)[0] for f_ in FEATURES}
            key = np.where(mask[0], net, -np.inf)
        elif req.ranker == "bm25":
            key = np.where(allowed[0], F["bm25"][0], -np.inf)
        else:
            key = np.where(allowed[0], text[0], -np.inf)
        order = np.lexsort((c.tie, -F["text"][0], -key))
        order = [d for d in order if np.isfinite(key[d]) or True][:k]
    with timer.stage("explain", "ids, components and citing neighbours"):
        top_nb = [{"neighbour_id": c.nidx.qids[i], "similarity": round(float(s), 4)} for i, s in zip(F["nb_idx"][0][:5], F["nb_sim"][0][:5])]
        out = []
        for r, d in enumerate(order, 1):
            comps = ({f_: float(comps_full[f_][d]) for f_ in FEATURES} if comps_full else {"text": float(key[d]) if np.isfinite(key[d]) else 0.0})
            nbs = c.nidx.explain(F["nb_idx"][0], F["nb_sim"][0], int(d), c.k_nb)
            item = {"rank": r, "doc_id": c.ids[d], "score": float(key[d]) if np.isfinite(key[d]) else 0.0, "components": comps,
                    "explanation": explain_result(c.ids[d], comps, weights if comps_full else {"text": 1.0}, neighbours=nbs),
                    "meta": {"court": c.cases[d].court, "date": c.cases[d].date, "cited_by": int(c.train_indegree[d])}}
            if req.query_id:
                item["relevant"] = c.ids[d] in c.relevant(q)
            if _state.show_text():
                item["title"] = c.cases[d].title
                item["snippet"] = _state.clip(c.cases[d].text)
            out.append(item)
    return {"source": "real", "ranker": req.ranker, "qid": q.qid, "k": k, "weights": weights if comps_full else None,
            "pruning": req.pruning, "candidates_scored": scored, "temporal_applied": temporal,
            "query_has_date": bool(q.date), "top_neighbours": top_nb, "results": out}


@router.post("/search")
def search(req: SearchRequest, response: Response):
    timer = StageTimer()
    t0 = time.perf_counter()
    out = _toy_search(req, timer) if _state.mode() == "toy" else _real_search(req, timer)
    timer.note("total", "server time for this search", (time.perf_counter() - t0) * 1000)
    response.headers["Server-Timing"] = timer.header()
    return out
