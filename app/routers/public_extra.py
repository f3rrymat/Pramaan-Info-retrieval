"""Phase G additive, read-only endpoints for the public landing page and the data-provenance footer.

Everything is read from saved runs in results/ and from docs/research_notes.md. No case text, no titles, no queries run.
Public (no sign-in): the prefix /api/public/ is open in app/security.py, and these routes expose aggregates and ids only.
"""
import csv
import json
import re
import time
from typing import Dict, List

from fastapi import APIRouter

from irlegal.common.config import load_config, repo_path
from . import extras

router = APIRouter(prefix="/api/public", tags=["public-extra"])

# files whose modification time is shown as the data provenance
PROVENANCE_FILES = ["dev_eval.json", "test_eval.json", "b2_ablation_dev.json", "leakage_audit.json", "efficiency.json", "crawl_sim.json", "index_report.json"]
SYSTEMS = {"tfidf": "tf-idf lnc.ltc", "bm25": "BM25 tuned", "ours_t": "Config A + temporal filter"}


def _results_dir():
    return repo_path(load_config()["paths"]["results_dir"])


def _load(name):
    p = _results_dir() / name
    return json.loads(p.read_text()) if p.exists() else None


def provenance() -> Dict:
    files = {}
    for n in PROVENANCE_FILES:
        p = _results_dir() / n
        if p.exists():
            files[n] = p.stat().st_mtime
    newest = max(files.values()) if files else None
    return {"files": {k: time.strftime("%Y-%m-%d %H:%M", time.localtime(v)) for k, v in files.items()}, "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest)) if newest else None,
            "updated_epoch": newest, "note": "modification times of the saved run files in results/ on this machine"}


@router.get("/provenance")
def provenance_endpoint():
    return provenance()


def _per_query(run_id: str) -> Dict[str, Dict[str, Dict]]:
    p = _results_dir() / run_id / "per_query.csv"
    out: Dict[str, Dict[str, Dict]] = {}
    if not p.exists():
        return out
    with p.open() as f:
        for r in csv.DictReader(f):
            out.setdefault(r["qid"], {})[r["ranker"]] = r
    return out


def _examples(dev: Dict) -> List[Dict]:
    """Three dev queries picked by a fixed rule (spread over the sorted ids among queries with at least 3 labelled citations), never by outcome."""
    pq = _per_query(dev["run_id"])
    names = {"tfidf": next((k for k in dev["macro"] if k.startswith("tf-idf lnc.ltc") and "temporal" not in k and "REFERENCE" not in k), None),
             "bm25": next((k for k in dev["macro"] if k.startswith("BM25 tuned")), None),
             "ours_t": "Config A + temporal filter"}
    if not pq or not all(names.values()):
        return []
    ids = sorted(q for q, rows in pq.items() if all(n in rows for n in names.values()) and int(next(iter(rows.values()))["n_relevant"]) >= 3)
    if len(ids) < 3:
        return []
    picks = [ids[len(ids) // 6], ids[len(ids) // 2], ids[(5 * len(ids)) // 6]]
    try:
        meta = extras.query_meta()["items"]
    except Exception:
        meta = {}
    out = []
    for q in picks:
        rows = pq[q]
        out.append({"qid": q, "court": meta.get(q, {}).get("court"), "year": meta.get(q, {}).get("year"), "n_relevant": int(rows[names["ours_t"]]["n_relevant"]),
                    "systems": [{"key": k, "label": SYSTEMS[k], "AP": round(float(rows[n]["MAP"]), 4), "R@10": round(float(rows[n]["R@10"]), 4), "MRR": round(float(rows[n]["MRR"]), 4)} for k, n in names.items()]})
    return out


def _notes() -> Dict:
    """Papers and data credits from docs/research_notes.md (never retyped)."""
    p = repo_path("docs/research_notes.md")
    if not p.exists():
        return {"papers": []}
    text = p.read_text()
    m = re.search(r"^## Papers\n(.*?)(?=^## )", text, re.S | re.M)
    papers = []
    for block in re.split(r"^### ", m.group(1) if m else "", flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        f = {k: v.strip() for k, v in re.findall(r"^- (\w+): (.*)$", body, re.M)}
        if "short" in f:
            papers.append({"title": title.strip(), "short": f["short"], "did": f.get("did", ""), "take": f.get("take", ""), "status": f.get("status", "").split(".")[0].split(" (")[0]})
    return {"papers": papers}


@router.get("/landing")
def landing():
    """One payload for the public landing page: headline MAP rows, ablation ladder, leakage audit, three real example queries, papers."""
    dev, test = _load("dev_eval.json"), _load("test_eval.json")
    if not dev:
        return {"available": False, "provenance": provenance()}
    head = extras.headline()
    pipe = extras.pipeline_numbers()
    leak = _load("leakage_audit.json") or {}
    a = leak.get("a_no_leave_one_out_train_queries", {})
    leakage = {k: {"with": a[k]["with_LOO"]["MAP"], "without": a[k]["without_LOO"]["MAP"], "n_queries": a.get("n_queries")} for k in ("config_A", "neighbour_alone", "authority_alone") if k in a}
    scrub = leak.get("c_citation_scrubbing_off_vs_on_dev", {}).get("queries_whose_text_changed_by_scrubbing")
    notes = dev.get("notes", {})
    return {"available": True, "headline": head, "pipeline": pipe, "leakage": leakage, "scrub_changed_queries": scrub, "examples": _examples(dev),
            "example_rule": "three dev queries picked by a fixed rule (spread over the sorted ids, at least 3 labelled citations), not by outcome",
            "first_stage_recall_at_1000": notes.get("first_stage_recall_at_1000"), "n_dev": dev["n_queries"], "n_test": test["n_queries"] if test else None,
            "notes": _notes(), "provenance": provenance()}
