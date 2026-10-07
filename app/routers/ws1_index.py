"""Index endpoints. Owner: WS1. Real index when available, toy stubs otherwise (see _state.mode())."""
import math
from typing import Optional

from fastapi import APIRouter, HTTPException

from irlegal.common.schema import ZONES
from irlegal.common.toy import toy_bundle
from . import _state

router = APIRouter(prefix="/api", tags=["ws1-index"])
REAL_ZONES = list(ZONES) + ["fi", "all"]


@router.get("/index/stats")
def index_stats():
    if _state.mode() == "toy":
        _, index, _ = toy_bundle()
        return {"source": "toy", "n_docs": index.n_docs(), "available": False}
    rep = _state.results_file("index_report.json") or {}
    sizes = rep.get("persisted_sizes_bytes", {})
    return {"source": "real", "available": bool(rep), "n_docs": rep.get("n_docs"), "tokens_whole_text": rep.get("tokens_all_zone"),
            "build_seconds": rep.get("build_seconds"), "in_memory_mb": rep.get("in_memory_index_mb"),
            "compression": {"raw_int32_mb": rep.get("persisted_total", {}).get("raw_int32_mb"),
                            "gap_vbyte_mb": rep.get("persisted_total", {}).get("gap_vbyte_mb"),
                            "per_zone": {z: {"raw_bytes": s["raw_int32_bytes"], "compressed_bytes": s["gap_vbyte_bytes"], "terms": s["n_terms"],
                                             "postings": s["n_postings"]} for z, s in sizes.items()}},
            "skip_benchmark": rep.get("skip_benchmark_all_zone_df_ge_50")}


@router.get("/case/{doc_id}")
def get_case(doc_id: str):
    if _state.mode() == "toy":
        corpus, _, _ = toy_bundle()
        case = corpus.get_case(doc_id)
        if case is None:
            raise HTTPException(404, f"unknown doc_id {doc_id}")
        return {"doc_id": case.doc_id, "title": case.title, "court": case.court, "date": case.date,
                "pool": case.pool, "statutes": sorted(case.statutes), "zones": case.zones, "source": "toy"}
    c = _state.ctx()
    case = c.corpus.get_case(doc_id)
    if case is None:
        raise HTTPException(404, f"unknown doc_id {doc_id}")
    out = {"doc_id": doc_id, "court": case.court, "date": case.date, "source": "real",
           "paragraphs_per_zone": {z: len(p) for z, p in case.zones.items()},
           "cites_in_pool": len(case.cites_out)}
    if _state.show_text():
        out["title"] = case.title
        out["snippet"] = _state.clip(case.text)
    return out


@router.get("/inspect/index")
def inspect_index(term: str, zone: Optional[str] = None, limit: int = 20):
    """df, idf and a postings preview (doc ids and tf only) for a term as stored (already stemmed: pass the raw word and we analyse it)."""
    if _state.mode() == "toy":
        _, index, _ = toy_bundle()
        zones = [zone] if zone else list(ZONES)
        t = term.lower()
        return {"term": t, "source": "toy", "zones": {z: {"df": index.df(t, z), "postings": index.postings(t, z)[:50]} for z in zones}}
    c = _state.ctx()
    analysed = c.an.analyze(term)
    stem = analysed[0] if analysed else term.lower()
    zones = [zone] if zone else REAL_ZONES
    out = {}
    for z in zones:
        if z not in c.index.zones:
            raise HTTPException(422, f"unknown zone {z}")
        df = c.index.df(stem, z)
        out[z] = {"df": df, "idf_log10": round(math.log10(c.index.n_docs() / df), 4) if df else None,
                  "postings_preview": [{"doc_id": d, "tf": tf, "ord": c.index.index_of(d)} for d, tf in c.index.postings(stem, z)[:max(1, min(limit, 500))]],
                  "positions_kept": z in ("facts", "issues")}
    return {"term": term, "indexed_form": stem, "source": "real", "n_docs": c.index.n_docs(), "zones": out}
