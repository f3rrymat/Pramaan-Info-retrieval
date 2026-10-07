"""Additive endpoints for the Phase E front end: query metadata, case detail, evaluation overlay, public numbers.

Nothing here changes an existing response shape. No case text is returned (titles only with SHOW_TEXT=1, D36).
"""
import json
import math
import re
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from irlegal.common.config import load_config, repo_path
from irlegal.common.toy import toy_bundle
from . import _state, ws3_search

router = APIRouter(prefix="/api", tags=["extras"])
_cache: Dict = {}


@router.get("/query_meta")
def query_meta():
    """qid -> {court level, year} for the dev queries (the picker shows only these)."""
    if _state.mode() == "toy":
        corpus, _, _ = toy_bundle()
        return {"source": "toy", "items": {q.qid: {"court": corpus.get_case(q.case_id).court, "year": (q.date or "")[:4] or None}
                                           for s in ("train", "val", "test") for q in corpus.queries(s)}}
    if "qm" not in _cache:
        import pandas as pd
        from irlegal.data.loader import map_court, parse_date
        d = repo_path(load_config()["dataset"]["local_dir"])
        df = pd.read_parquet(d / "dev_queries.parquet", columns=["id", "jurisdiction", "date"])
        _cache["qm"] = {r.id: {"court": map_court(r.jurisdiction), "year": (parse_date(r.date) or "")[:4] or None} for r in df.itertuples(index=False)}
    return {"source": "real", "items": _cache["qm"]}


@router.get("/case_detail/{doc_id}")
def case_detail(doc_id: str):
    if _state.mode() == "toy":
        corpus, _, _ = toy_bundle()
        c = corpus.get_case(doc_id)
        if c is None:
            raise HTTPException(404, f"unknown doc_id {doc_id}")
        return {"source": "toy", "doc_id": doc_id, "court": c.court, "year": (c.date or "")[:4] or None, "train_indegree": None, "authority": None,
                "zone_sizes": {z: len(p) for z, p in c.zones.items()}, "cites_in_pool": len(c.cites_out)}
    c = _state.ctx()
    case = c.corpus.get_case(doc_id)
    if case is None:
        raise HTTPException(404, f"unknown doc_id {doc_id}")
    i = c.index.index_of(doc_id)
    train_in = int(c.train_indegree[i])
    base = float(c.graph.base[i])
    out = {"source": "real", "doc_id": doc_id, "court": case.court, "year": (case.date or "")[:4] or None, "date": case.date,
           "train_indegree": train_in, "pool_plus_train_indegree": int(base), "authority": round(math.log1p(base), 4),
           "zone_sizes": {z: len(p) for z, p in case.zones.items()}, "cites_in_pool": len(case.cites_out)}
    if _state.show_text():
        out["title"] = case.title
        out["snippet"] = _state.clip(case.text)
    return out


class OverlayRequest(BaseModel):
    query_id: str
    ranker: str = "ours"
    pruning: str = "none"
    filters: Dict = {}
    temporal_filter: bool = False
    weights: Dict[str, float] = {}


@router.post("/overlay")
def overlay(req: OverlayRequest):
    """Evaluation-only: gold relevant set of a DEV query and P@10, R@10, AP@100 for the current settings. Never used by a ranker."""
    if _state.mode() == "toy":
        corpus, _, ranker = toy_bundle()
        q = next((q for s in ("train", "val", "test") for q in corpus.queries(s) if q.qid == req.query_id), None)
        if q is None:
            raise HTTPException(404, "unknown query_id")
        ids = [r.doc_id for r in ranker.rank(q, 100)]
        gold = set(q.relevant)
    else:
        sr = ws3_search.SearchRequest(query_id=req.query_id, ranker=req.ranker, pruning=req.pruning, filters=req.filters,
                                      temporal_filter=req.temporal_filter, weights=req.weights, k=100)
        res = ws3_search._real_search(sr)
        ids = [r["doc_id"] for r in res["results"]]
        c = _state.ctx()
        gold = c.relevant(ws3_search._dev_queries()[req.query_id])
    hits, ap = 0, 0.0
    ranks = {}
    for r, d in enumerate(ids, 1):
        if d in gold:
            hits += 1
            ap += hits / r
            ranks[d] = r
    return {"evaluation_only": True, "n_relevant": len(gold), "relevant_ranks": ranks, "relevant_in_top100": hits,
            "P@10": round(sum(1 for d in ids[:10] if d in gold) / 10, 4), "R@10": round(sum(1 for d in ids[:10] if d in gold) / max(len(gold), 1), 4),
            "AP@100": round(ap / max(len(gold), 1), 4), "note": "AP is truncated at rank 100: relevant precedents below it add nothing"}


@router.get("/public/headline")
def headline():
    """Aggregates from saved runs, for the sign-in page and the pipeline page (no queries, no text)."""
    def load(n):
        p = repo_path(load_config()["paths"]["results_dir"], n)
        return json.loads(p.read_text()) if p.exists() else None
    dev, test = load("dev_eval.json"), load("test_eval.json")
    if not dev:
        return {"available": False}
    names = {"tfidf": "tf-idf lnc.ltc", "bm25": "BM25 tuned", "config_a": "Config A (text + neighbour + authority)", "config_a_tf": "Config A + temporal filter"}

    def pick(run, label):
        if not run:
            return None
        m = next((v for k, v in run["macro"].items() if k == label or k.startswith(label)), None)
        return {k: m[k] for k in ("MAP", "MRR", "nDCG@10", "R@10", "R@20")} if m else None
    rows = [{"key": k, "label": label, "dev": pick(dev, label), "test": pick(test, label)} for k, label in names.items()]
    return {"available": True, "dev_queries": dev["n_queries"], "test_queries": test["n_queries"] if test else None, "pool_docs": int(re.search(r"\d+", dev["candidates"]).group(0)),
            "rows": rows, "test_run_once": bool(test)}


@router.get("/public/about")
def about():
    """Limitations, data credits, AI-use pointer: sections copied from README.md (which scripts/make_readme.py generates)."""
    p = repo_path("README.md")
    if not p.exists():
        return {"available": False}
    text = p.read_text()
    out = {}
    # Phase F moved "Limitations" under "## Limitations and negative results" and "Related work" to "### References"; same keys either way.
    aliases = {"Limitations": ("## Limitations", "### Limitations"), "Related work": ("## Related work", "### References")}
    for title in ("Limitations", "Data credits and licences", "AI use", "Related work"):
        body = ""
        for head in aliases.get(title, (f"## {title}",)):
            m = re.search(rf"^{re.escape(head)}\n(.*?)(?=^##+ |\Z)", text, re.S | re.M)
            if m:
                body = m.group(1).strip()
                break
        out[title] = body
    gated = re.search(r"^### Data \(gated.*?\n(.*?)(?=^### |^## |\Z)", text, re.S | re.M)
    out["Gated data notice"] = gated.group(1).strip() if gated else ""
    return {"available": True, "sections": out}


RESULT_FILES = {"w_variant", "decompose_dev", "crawl_sim", "and_benchmark", "bm25_tuning", "statute_bridge", "config_a_frozen", "index_report", "role_profile"}


@router.get("/results/{name}")
def result_file(name: str):
    """Whitelisted saved-run JSON for the analyst dashboards (aggregates only; the role gate is in app/security.py)."""
    if name not in RESULT_FILES:
        raise HTTPException(404, "unknown result file")
    p = repo_path(load_config()["paths"]["results_dir"], f"{name}.json")
    if not p.exists():
        return {"available": False, "status": f"PLACEHOLDER: results/{name}.json has not been produced on this machine."}
    return {"available": True, "name": name, "data": json.loads(p.read_text())}


@router.get("/public/pipeline")
def pipeline_numbers():
    """Aggregates for the How it works page: frozen weights, first-stage recall, ablation ladder, no-leave-one-out inflation."""
    def load(n):
        p = repo_path(load_config()["paths"]["results_dir"], n)
        return json.loads(p.read_text()) if p.exists() else None
    dev, cfg, abl, leak, idx = load("dev_eval.json"), load("config_a_frozen.json"), load("b2_ablation_dev.json"), load("leakage_audit.json"), load("index_report.json")
    out = {"available": bool(dev)}
    if cfg:
        out["config_a"] = {"weights": cfg["weights"], "neighbour": cfg["neighbour"], "first_stage": cfg["first_stage"], "train_queries": cfg["train_queries"]}
    if dev:
        out["dev"] = {"n_queries": dev["n_queries"], "first_stage_recall_at_1000": dev["notes"]["first_stage_recall_at_1000"], "share_pairs_both_dates_known": dev["notes"]["share_pairs_both_dates_known"],
                      "scrubber_note": "citation strings are removed from the query before it is used"}
    if abl:
        out["ablation"] = [{"row": k, "MAP": v["MAP"]} for k, v in abl["rows"].items() if not k.startswith(("ref:", "REFERENCE"))]
    if leak:
        a = leak["a_no_leave_one_out_train_queries"]["config_A"]
        out["leave_one_out"] = {"with": a["with_LOO"]["MAP"], "without": a["without_LOO"]["MAP"]}
    if idx:
        out["index"] = {"n_docs": idx["n_docs"], "tokens": idx["tokens_all_zone"], "raw_mb": idx["persisted_total"]["raw_int32_mb"], "compressed_mb": idx["persisted_total"]["gap_vbyte_mb"]}
    return out
