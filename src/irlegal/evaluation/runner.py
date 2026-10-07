"""One evaluation runner for dev and test. Owner: WS4.

Rows (Facts+Issues queries unless marked REFERENCE): random, popularity (train in-degree), tf-idf, tuned BM25,
Config A, Config A + temporal filter, plus full-judgment reference rows. Candidates for every query: the full
pool minus the query's own id. Outputs (results/<run_id>/): metrics.json (macro + micro averages, paired
bootstrap vs tf-idf and for key pairs), metrics.csv, per_query.csv, pr_curve.json, config.json. The latest run
per split is also copied to results/dev_eval.json | test_eval.json for the API.

The test split runs only with --final, and only once: a successful final run writes results/final.lock and
a second run needs --allow-rerun (DECISIONS D25).

Usage:  python -m irlegal.evaluation.runner --split dev
        python -m irlegal.evaluation.runner --split test --final
"""
import argparse
import csv
import json
import logging
import time
import zlib
from pathlib import Path
from typing import Dict, List

import numpy as np

from irlegal.common.config import load_config, repo_path
from .metrics import evaluate_ranking, interpolated_pr

log = logging.getLogger(__name__)
KEYS = ("MAP", "MRR", "nDCG@10", "R@10", "R@20")
BASE = "tf-idf lnc.ltc"
LOCK = "final.lock"


def _guard(split: str, final: bool, allow_rerun: bool):
    if split == "test":
        if not final:
            raise PermissionError("Refusing to run on the test split without --final (DECISIONS D5, D25).")
        lock = repo_path(load_config()["paths"]["results_dir"], LOCK)
        if lock.exists() and not allow_rerun:
            raise PermissionError(f"{lock.name} exists: the final test run was already done. Pass --allow-rerun to override.")


def bootstrap(a: np.ndarray, b: np.ndarray, idx: np.ndarray) -> List[float]:
    d = np.asarray(a) - np.asarray(b)
    m = d[idx].mean(axis=1)
    return [round(float(d.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def build_rankings(ctx, qs, qs_full, popularity: bool = True) -> Dict[str, List[List[str]]]:
    """name -> best-first id lists for each query."""
    F = ctx.features(qs, loo=True, bm25=True)
    own = ctx.own_idx(qs)
    all_mask = np.ones((len(qs), ctx.n), bool)
    zero = np.zeros((len(qs), ctx.n), np.float32)
    mask = ctx.first_stage_mask(F["text"], own)
    cfg_net = ctx.net(F, mask)
    removed = ctx.removed_by_date(qs)
    rnd = np.stack([np.random.default_rng([ctx.seed, zlib.crc32(q.qid.encode())]).random(ctx.n) for q in qs])
    pop = np.broadcast_to(ctx.train_indegree, (len(qs), ctx.n))
    Ff = dict(F)
    Ff["text"] = ctx.text_matrix([q.text for q in qs_full])
    maskf = ctx.first_stage_mask(F["text"], own)
    rows = {
        "random": ctx.rank_ids(qs, rnd, all_mask, zero),
        "popularity (train in-degree)": ctx.rank_ids(qs, pop, all_mask, zero),
        BASE: ctx.rank_ids(qs, F["text"], all_mask, zero),
        f"BM25 tuned (k1={ctx.bm25_params['k1']}, b={ctx.bm25_params['b']})": ctx.rank_ids(qs, F["bm25"], all_mask, zero),
        "Config A (text + neighbour + authority)": ctx.rank_ids(qs, cfg_net, mask, F["text"]),
        "Config A + temporal filter": ctx.rank_ids(qs, cfg_net, mask, F["text"], removed),
        BASE + " + temporal filter": ctx.rank_ids(qs, F["text"], all_mask, zero, removed),
        "REFERENCE full-judgment query: tf-idf": ctx.rank_ids(qs, Ff["text"], all_mask, zero),
        "REFERENCE full-judgment text feature: Config A": ctx.rank_ids(qs, ctx.net(Ff, maskf), maskf, Ff["text"]),
    }
    extra = {"share_pairs_both_dates_known": round(float(ctx.both_dates_known(qs).mean()), 4)}
    rel_pairs = [(i, ctx.index.index_of(d)) for i, q in enumerate(qs) for d in ctx.relevant(q)]
    known = ctx.both_dates_known(qs)
    kn = [(i, j) for i, j in rel_pairs if known[i, j]]
    extra["share_relevant_pairs_removed_by_filter"] = round(float(np.mean([removed[i, j] for i, j in kn])), 4) if kn else None
    extra["first_stage_recall_at_1000"] = round(float(np.mean([mask[i, j] for i, j in rel_pairs])), 4)
    return rows, extra


def evaluate(ctx, split: str):
    qs = [q for q in ctx.corpus.queries(split) if ctx.relevant(q)]
    full = {q.qid: q for q in ctx.corpus.queries(split, view="full")}
    qs_full = [full[q.qid] for q in qs]
    rankings, extra = build_rankings(ctx, qs, qs_full)
    ks = tuple(ctx.cfg["ws4"]["ks"])
    macro, micro, per_rows, pr, arrays = {}, {}, [], {}, {}
    for name, rk in rankings.items():
        ms = [evaluate_ranking(r, ctx.relevant(q), ks) for r, q in zip(rk, qs)]
        macro[name] = {k: round(float(np.mean([m[k] for m in ms])), 4) for k in ms[0]}
        total_rel = sum(len(ctx.relevant(q)) for q in qs)
        mic = {}
        for k in ks:
            hits = sum(len(set(r[:k]) & ctx.relevant(q)) for r, q in zip(rk, qs))
            p, rc = hits / (k * len(qs)), hits / total_rel
            mic.update({f"micro_P@{k}": round(p, 4), f"micro_R@{k}": round(rc, 4),
                        f"micro_F1@{k}": round(2 * p * rc / (p + rc), 4) if p + rc else 0.0})
        micro[name] = mic
        pr[name] = np.round(np.mean([interpolated_pr(r, ctx.relevant(q)) for r, q in zip(rk, qs)], axis=0), 4).tolist()
        arrays[name] = {k: np.array([m[k] for m in ms]) for k in KEYS}
        per_rows += [{"ranker": name, "qid": q.qid, "n_relevant": len(ctx.relevant(q)), **m} for q, m in zip(qs, ms)]
    idx = np.random.default_rng(ctx.seed).integers(0, len(qs), size=(1000, len(qs)))
    pairs = {"vs_tfidf": {n: {k: bootstrap(arrays[n][k], arrays[BASE][k], idx) for k in KEYS} for n in rankings if n != BASE}}
    bm = next(n for n in rankings if n.startswith("BM25"))
    A, At = "Config A (text + neighbour + authority)", "Config A + temporal filter"
    pairs["ConfigA_vs_BM25_tuned"] = {k: bootstrap(arrays[A][k], arrays[bm][k], idx) for k in KEYS}
    pairs["ConfigA_temporal_vs_ConfigA"] = {k: bootstrap(arrays[At][k], arrays[A][k], idx) for k in KEYS}
    return qs, {"macro": macro, "micro": micro, "bootstrap_diff_[mean,lo95,hi95]": pairs, "pr_curve_11pt": pr, "notes": extra}, per_rows


def run(split: str, final: bool = False, allow_rerun: bool = False, out_root=None) -> Path:
    _guard(split, final, allow_rerun)
    from irlegal.ranking.pipeline import Context           # heavy import after the guard
    t0 = time.time()
    ctx = Context()
    qs, res, per_rows = evaluate(ctx, split)
    cfgd = ctx.cfg["paths"]["results_dir"]
    run_id = f"eval_{split}_{time.strftime('%Y%m%d_%H%M%S')}"
    out = Path(out_root) if out_root else repo_path(cfgd, run_id)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"run_id": run_id, "split": split, "final": final, "n_queries": len(qs), "candidates": f"pool ({ctx.n}) minus own id",
            "query": "Facts+Issues (scrubbed); REFERENCE rows use the full judgment", "seed": ctx.seed, "config_a": ctx.config_a(),
            "bm25": ctx.bm25_params, "neighbour": {"k": ctx.k_nb, "p": ctx.p_nb}, "bootstrap_resamples": 1000,
            "seconds": round(time.time() - t0, 1)}
    (out / "metrics.json").write_text(json.dumps({**meta, **res}, indent=1))
    (out / "config.json").write_text(json.dumps(meta, indent=1))
    (out / "pr_curve.json").write_text(json.dumps({"recall_levels": [i / 10 for i in range(11)], "precision": res["pr_curve_11pt"]}, indent=1))
    with open(out / "metrics.csv", "w", newline="") as f:
        cols = ["ranker"] + list(next(iter(res["macro"].values()))) + list(next(iter(res["micro"].values())))
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for n in res["macro"]:
            w.writerow({"ranker": n, **res["macro"][n], **res["micro"][n]})
    with open(out / "per_query.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_rows[0]))
        w.writeheader(); w.writerows(per_rows)
    if out_root is None:
        (repo_path(cfgd) / f"{'test' if split == 'test' else 'dev'}_eval.json").write_text(json.dumps({**meta, **res}, indent=1))
        if split == "test":
            (repo_path(cfgd) / LOCK).write_text(json.dumps({"run_id": run_id, "time": time.strftime("%Y-%m-%d %H:%M:%S")}))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "val", "test"], default="dev")
    ap.add_argument("--final", action="store_true", help="required to touch the test split")
    ap.add_argument("--allow-rerun", action="store_true", help="override results/final.lock after a final run")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        out = run("val" if a.split == "dev" else a.split, final=a.final, allow_rerun=a.allow_rerun)
    except PermissionError as e:
        raise SystemExit(str(e))
    print(f"saved to {out}")


if __name__ == "__main__":
    main()
