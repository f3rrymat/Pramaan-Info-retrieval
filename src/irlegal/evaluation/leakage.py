"""Leakage audit, DEV (and train for (a)) only. Owner: WS4.

Each audit measures how much a leaky variant would inflate the metrics, with paired bootstrap intervals:
 (a) neighbour + authority features WITHOUT leave-one-out, scoring TRAIN queries (sample of 1,500);
 (b) authority built from train + dev links vs train only, scoring dev;
 (c) query text with vs without citation scrubbing, scoring dev;
 (d) temporal filter on vs off, scoring dev.
The test split is never touched: `_split` refuses it, and a test scans this file for test-split access.
Usage: python -m irlegal.evaluation.leakage
"""
import csv
import json
import sys
from typing import Dict, List

import numpy as np

from irlegal.common.config import load_config, repo_path
from irlegal.ranking import authority as au
from .metrics import evaluate_ranking

ALLOWED_SPLITS = ("train", "val")
KEYS = ("MAP", "MRR", "nDCG@10", "R@10", "R@20")


def _split(name: str) -> str:
    if name not in ALLOWED_SPLITS:
        raise ValueError(f"leakage audit may only use {ALLOWED_SPLITS}, not {name!r}")
    return name


def _per_query(ctx, qs, rankings) -> Dict[str, np.ndarray]:
    ms = [evaluate_ranking(r, ctx.relevant(q)) for r, q in zip(rankings, qs)]
    return {k: np.array([m[k] for m in ms]) for k in KEYS}


def _delta(a, b, idx) -> Dict[str, List[float]]:
    out = {}
    for k in KEYS:
        d = a[k] - b[k]
        m = d[idx].mean(axis=1)
        out[k] = [round(float(d.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]
    return out


def _systems(ctx, qs, F, removed=None):
    """tf-idf and Config A rankings for features F."""
    own = ctx.own_idx(qs)
    allm = np.ones((len(qs), ctx.n), bool)
    zero = np.zeros((len(qs), ctx.n), np.float32)
    mask = ctx.first_stage_mask(F["text"], own)
    return {"tfidf": ctx.rank_ids(qs, F["text"], allm, zero, removed),
            "config_A": ctx.rank_ids(qs, ctx.net(F, mask), mask, F["text"], removed),
            "neighbour_alone": ctx.rank_ids(qs, F["neighbour"], allm, zero),
            "authority_alone": ctx.rank_ids(qs, F["authority"], allm, zero)}


def _mean(per):
    return {k: round(float(v.mean()), 4) for k, v in per.items()}


def run(ctx, n_train: int = 1500) -> dict:
    res = {}
    # ---- (a) leave-one-out off, TRAIN queries
    _split("train")
    tq = [q for q in ctx.train_queries if q.text and ctx.relevant(q)]
    rng = np.random.default_rng(ctx.seed)
    tq = [tq[i] for i in sorted(rng.choice(len(tq), size=min(n_train, len(tq)), replace=False))]
    clean = _systems(ctx, tq, ctx.features(tq, loo=True))
    leaky = _systems(ctx, tq, ctx.features(tq, loo=False))
    idx = rng.integers(0, len(tq), size=(1000, len(tq)))
    res["a_no_leave_one_out_train_queries"] = {
        s: {"with_LOO": _mean(_per_query(ctx, tq, clean[s])), "without_LOO": _mean(_per_query(ctx, tq, leaky[s])),
            "inflation_[mean,lo95,hi95]": _delta(_per_query(ctx, tq, leaky[s]), _per_query(ctx, tq, clean[s]), idx)}
        for s in ("config_A", "neighbour_alone", "authority_alone")}
    res["a_no_leave_one_out_train_queries"]["n_queries"] = len(tq)
    # ---- dev queries
    _split("val")
    dq = [q for q in ctx.corpus.queries("val") if ctx.relevant(q)]
    didx = np.random.default_rng(ctx.seed).integers(0, len(dq), size=(1000, len(dq)))
    F = ctx.features(dq, loo=True)
    base = _systems(ctx, dq, F)
    bper = {s: _per_query(ctx, dq, base[s]) for s in base}
    # ---- (b) authority from train+dev links, no LOO
    dev_cites = ctx.corpus.relevant_ids("val")
    g2 = au.AuthorityGraph(ctx.ids, {c.doc_id: c.cites_out for c in ctx.cases},
                           {**ctx.corpus.relevant_ids("train"), **dev_cites})
    Fb = dict(F)
    Fb["authority"] = ctx.authority_matrix(dq, loo=False, graph=g2)
    lb = _systems(ctx, dq, Fb)
    res["b_authority_train_plus_dev_links_vs_train_only_scoring_dev"] = {
        s: {"train_only": _mean(bper[s]), "train_plus_dev": _mean(_per_query(ctx, dq, lb[s])),
            "inflation_[mean,lo95,hi95]": _delta(_per_query(ctx, dq, lb[s]), bper[s], didx)} for s in ("config_A", "authority_alone")}
    # ---- (c) scrubbing off
    raw = [q for q in ctx.corpus.queries("val", scrub=False) if ctx.relevant(q)]
    Fc = ctx.features(raw, loo=True)
    lc = _systems(ctx, raw, Fc)
    res["c_citation_scrubbing_off_vs_on_dev"] = {
        s: {"scrubbed": _mean(bper[s]), "not_scrubbed": _mean(_per_query(ctx, raw, lc[s])),
            "difference_unscrubbed_minus_scrubbed_[mean,lo95,hi95]": _delta(_per_query(ctx, raw, lc[s]), bper[s], didx)}
        for s in ("tfidf", "config_A")}
    res["c_citation_scrubbing_off_vs_on_dev"]["queries_whose_text_changed_by_scrubbing"] = int(sum(a.text != b.text for a, b in zip(raw, dq)))
    # ---- (d) temporal filter
    rm = ctx.removed_by_date(dq)
    ld = _systems(ctx, dq, F, rm)
    res["d_temporal_filter_on_vs_off_dev"] = {
        s: {"off": _mean(bper[s]), "on": _mean(_per_query(ctx, dq, ld[s])),
            "difference_on_minus_off_[mean,lo95,hi95]": _delta(_per_query(ctx, dq, ld[s]), bper[s], didx)} for s in ("tfidf", "config_A")}
    res["splits_used"] = list(ALLOWED_SPLITS)
    return res


def main():
    from irlegal.ranking.pipeline import Context
    out = run(Context())
    d = repo_path(load_config()["paths"]["results_dir"])
    (d / "leakage_audit.json").write_text(json.dumps(out, indent=1))
    rows = []
    for audit, body in out.items():
        if isinstance(body, dict):
            for sys_name, v in body.items():
                if isinstance(v, dict):
                    key = next((k for k in v if "[mean" in k), None)
                    if key:
                        for m, (mean, lo, hi) in v[key].items():
                            rows.append({"audit": audit, "system": sys_name, "metric": m, "delta": mean, "lo95": lo, "hi95": hi})
    with open(d / "leakage_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["audit", "system", "metric", "delta", "lo95", "hi95"])
        w.writeheader(); w.writerows(rows)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
