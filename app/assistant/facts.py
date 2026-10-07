"""Facts sheet for the assistant (D42, D43): the only numbers the model may state come from here.

Built on the server from (1) whitelisted JSON files in results/ (numbers only), (2) selected sections of README.md,
docs/STATUS.md and docs/research_notes.md (our own prose; no case text), and (3) the structured context of the current
search: ids, courts, years, scores and score components. Case text, titles, snippets and pasted query text are never
read here. The whole sheet is cut to config.FACTS_MAX_CHARS.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from irlegal.common.config import load_config, repo_path

from . import config

SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
SAFE_LABEL = re.compile(r"^[\w\s@.+\-()/:·,%=&\[\]]{1,80}$")
COURTS = {"SC", "HC", "OTHER"}
FEATURES = ("text", "neighbour", "authority", "recency", "court", "statute")
PAGES = {"/search", "/compare", "/querylab", "/saved", "/history", "/evaluation", "/efficiency", "/index", "/status", "/users",
         "/how", "/about", "/settings", "/styleguide", "/assistant"}
EVAL_METRICS = ("MAP", "MRR", "nDCG@10", "R@10", "R@20", "P@10")
RESULT_FILES = ("dev_eval.json", "test_eval.json", "leakage_audit.json", "config_a_frozen.json", "b2_ablation_dev.json", "efficiency.json",
                "index_report.json", "w_variant.json", "decompose_dev.json", "crawl_sim.json", "bm25_tuning.json", "statute_bridge.json",
                "and_benchmark.json")
DOC_SECTIONS = (
    ("README.md", ("Headline results", "Leakage audit", "Negative and marginal results", "Limitations and negative results", "Efficiency", "Index",
                   "Our contributions", "Limitations", "How the assistant works")),
    ("docs/STATUS.md", ("Known issues and caveats",)),
    ("docs/research_notes.md", ("Our contributions", "Caveats")),
)
_cache: Dict[str, Any] = {}


# ------------------------------------------------------------------ results/ (numbers only)
def _num(v):
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:.0f}"
    return None


def _flatten(obj, prefix: str, out: List[str], depth: int = 0, max_lines: int = 60) -> None:
    """Numeric leaves only, as 'a.b.c = 0.1234'. Strings are dropped except short labels used as list keys."""
    if len(out) >= max_lines or depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "per_query" in str(k) or str(k) in ("qids", "rankings", "queries"):
                continue
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out, depth + 1, max_lines)
    elif isinstance(obj, list):
        if obj and len(obj) <= 12 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in obj):
            out.append(f"{prefix} = [{', '.join(_num(x) for x in obj)}]")
        elif obj and len(obj) <= 16 and all(isinstance(x, dict) for x in obj):
            for i, x in enumerate(obj):
                label = next((str(x[k]) for k in ("method", "name", "row", "family", "K") if k in x and len(str(x[k])) <= 60), str(i))
                _flatten({k: v for k, v in x.items() if k not in ("method", "name", "row")}, f"{prefix}[{label}]", out, depth + 1, max_lines)
    else:
        s = _num(obj)
        if s is not None:
            out.append(f"{prefix} = {s}")


def _eval_lines(name: str, d: dict) -> List[str]:
    out = [f"{name}: {d.get('n_queries')} queries; candidates: {d.get('candidates', '?')}"[:200]]
    for sys_name, m in (d.get("macro") or {}).items():
        out.append(f"{name} {sys_name}: " + ", ".join(f"{k} {_num(m[k])}" for k in EVAL_METRICS if isinstance(m.get(k), (int, float))))
    for sys_name, m in ((d.get("bootstrap_diff_[mean,lo95,hi95]") or {}).get("vs_tfidf") or {}).items():
        if "MAP" in m:
            out.append(f"{name} MAP difference to tf-idf, {sys_name}: mean {_num(m['MAP'][0])}, 95% interval [{_num(m['MAP'][1])}, {_num(m['MAP'][2])}]")
    for k, v in (d.get("notes") or {}).items():
        if _num(v) is not None:
            out.append(f"{name} note {k} = {_num(v)}")
    return out


def _results_block(budget: int) -> str:
    res = repo_path(load_config()["paths"]["results_dir"])
    if not res.exists():
        return "results/: not present on this server (no saved runs here). Use only the numbers quoted from the README below."
    lines: List[str] = []
    for fn in RESULT_FILES:
        p = res / fn
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
            part = _eval_lines(fn[:-5], d) if fn in ("dev_eval.json", "test_eval.json") else []
            if not part:
                flat: List[str] = []
                _flatten(d, fn[:-5], flat, max_lines=40)
                part = flat
        except Exception:
            continue
        lines += part
    text = "\n".join(lines)
    return text[:budget]


# ------------------------------------------------------------------ docs (our own prose)
def _sections(text: str, wanted) -> List[str]:
    out = []
    parts = re.split(r"(?m)^(#{2,3} .+)$", text)
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].lstrip("#").strip()
        if any(title.startswith(w) for w in wanted):
            body = re.sub(r"\n{3,}", "\n\n", parts[i + 1]).strip()
            body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)           # no image links
            out.append(f"[{title}]\n{body}")
    return out


def _docs_block(budget: int) -> str:
    chunks = []
    for rel, wanted in DOC_SECTIONS:
        p = repo_path(rel)
        if p.exists():
            chunks += [f"({rel}) {s}" for s in _sections(p.read_text(encoding="utf-8"), wanted)]
    return "\n\n".join(chunks)[:budget]


def static_sheet() -> str:
    """results/ + docs, cached on file modification times."""
    paths = [repo_path(load_config()["paths"]["results_dir"], f) for f in RESULT_FILES] + [repo_path(r) for r, _ in DOC_SECTIONS]
    key = tuple((str(p), p.stat().st_mtime if p.exists() else 0) for p in paths)
    if _cache.get("key") != key:
        res = _results_block(7000)
        docs = _docs_block(config.FACTS_MAX_CHARS - len(res) - 2500)
        _cache.update(key=key, text=f"SAVED RUNS (results/, numbers only)\n{res}\n\nPROJECT DOCS (README, STATUS, research notes)\n{docs}")
    return _cache["text"]


# ------------------------------------------------------------------ current search context (ids and numbers only)
def _f(x) -> Optional[float]:
    return round(float(x), 4) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def clean_context(ctx: Any) -> Dict[str, Any]:
    """Whitelist the structured context the browser may send. Everything else (titles, snippets, text) is dropped."""
    if not isinstance(ctx, dict):
        return {}
    out: Dict[str, Any] = {}
    if ctx.get("kind") in ("result", "search", "metric", "page"):
        out["kind"] = ctx["kind"]
    q = ctx.get("query_id")
    if isinstance(q, str) and (SAFE_ID.match(q) or q == "pasted"):
        out["query_id"] = q
    if isinstance(ctx.get("ranker"), str) and ctx["ranker"] in ("tfidf", "bm25", "ours"):
        out["ranker"] = ctx["ranker"]
    if isinstance(ctx.get("temporal_filter"), bool):
        out["temporal_filter"] = ctx["temporal_filter"]
    if isinstance(ctx.get("weights"), dict):
        out["weights"] = {k: _f(v) for k, v in ctx["weights"].items() if k in FEATURES and _f(v) is not None}
    rs = []
    for r in (ctx.get("results") or [])[: config.CONTEXT_MAX_RESULTS] if isinstance(ctx.get("results"), list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("doc_id"), str) or not SAFE_ID.match(r["doc_id"]):
            continue
        item = {"doc_id": r["doc_id"]}
        if isinstance(r.get("rank"), int) and 0 < r["rank"] < 10000:
            item["rank"] = r["rank"]
        if r.get("court") in COURTS:
            item["court"] = r["court"]
        y = str(r.get("year") or "")[:4]
        if y.isdigit():
            item["year"] = int(y)
        if _f(r.get("score")) is not None:
            item["score"] = _f(r["score"])
        if isinstance(r.get("components"), dict):
            item["components"] = {k: _f(v) for k, v in r["components"].items() if k in FEATURES and _f(v) is not None}
        if isinstance(r.get("relevant"), bool):
            item["labelled_citation"] = r["relevant"]
        nbs = [{"id": n["neighbour_id"], "similarity": _f(n.get("similarity"))} for n in (r.get("neighbours") or [])[:5]
               if isinstance(n, dict) and isinstance(n.get("neighbour_id"), str) and SAFE_ID.match(n["neighbour_id"]) and _f(n.get("similarity")) is not None]
        if nbs:
            item["citing_train_neighbours"] = nbs
        rs.append(item)
    if rs:
        out["results"] = rs
    m = ctx.get("metric")
    if isinstance(m, dict) and isinstance(m.get("name"), str) and SAFE_LABEL.match(m["name"]):
        out["metric"] = {"name": m["name"], **({"value": _f(m["value"])} if _f(m.get("value")) is not None else {})}
    return out


def context_block(ctx: Dict[str, Any], page: Optional[str]) -> str:
    lines = []
    if page in PAGES:
        lines.append(f"The user is on the {page.strip('/')} page.")
    if ctx.get("query_id"):
        lines.append(f"Current search: {'pasted text (no id, no date, no labels)' if ctx['query_id'] == 'pasted' else 'dev query ' + ctx['query_id']}"
                     f"; ranker {ctx.get('ranker', '?')}; temporal filter {'on' if ctx.get('temporal_filter') else 'off'}.")
    if ctx.get("weights"):
        lines.append("Net-score weights in use: " + ", ".join(f"{k} {v}" for k, v in ctx["weights"].items()) + ".")
    for r in ctx.get("results", []):
        bits = [f"rank {r['rank']}" if "rank" in r else None, f"court {r['court']}" if "court" in r else None, f"year {r['year']}" if "year" in r else None,
                f"score {r['score']}" if "score" in r else None]
        comp = ", ".join(f"{k} {v}" for k, v in r.get("components", {}).items())
        nb = "; ".join(f"{n['id']} (similarity {n['similarity']})" for n in r.get("citing_train_neighbours", []))
        lab = "" if "labelled_citation" not in r else ("; it IS in the dataset's labelled citations for this query (evaluation overlay)" if r["labelled_citation"] else "; not a labelled citation")
        lines.append(f"Result {r['doc_id']}: " + ", ".join(b for b in bits if b) + (f"; normalised components: {comp}" if comp else "") + (f"; similar train cases citing it: {nb}" if nb else "") + lab + ".")
    if ctx.get("metric"):
        m = ctx["metric"]
        lines.append(f"The user asks about the dashboard metric '{m['name']}'" + (f" shown as {m['value']}" if "value" in m else "") + ".")
    return "\n".join(lines)


def build(ctx: Optional[Dict[str, Any]] = None, page: Optional[str] = None) -> str:
    """The full facts sheet: current context first (small), then saved runs and docs. Hard cap FACTS_MAX_CHARS."""
    cur = context_block(ctx or {}, page)
    sheet = (f"CURRENT VIEW (ids and numbers only; case text is never available)\n{cur}\n\n" if cur else "") + static_sheet()
    return sheet[: config.FACTS_MAX_CHARS]
