"""Efficiency vs effectiveness on DEV (D25 test is not touched). Saves results/efficiency.json|csv.

Text-stage methods (tf-idf lnc.ltc, Facts+Issues, whole text): exhaustive, index elimination, champion lists,
authority tiers. Neighbour search: exhaustive vs cluster pruning (end to end through Config A).
Latency is wall time per query on this machine (selection + scoring + top-20); candidates and postings are
machine independent. MAP and R@10 are scored on the full ranking (scored docs first, rest in tie-key order).
Usage: python scripts/run_efficiency.py
"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.efficiency.champions import ChampionSelector  # noqa: E402
from irlegal.efficiency.cluster import ClusterPruner  # noqa: E402
from irlegal.efficiency.elimination import EliminationSelector  # noqa: E402
from irlegal.efficiency.heap import top_k_heap, top_k_sort  # noqa: E402
from irlegal.efficiency.scoring import TextScorer  # noqa: E402
from irlegal.efficiency.tiers import TierSelector  # noqa: E402
from irlegal.evaluation.metrics import evaluate_ranking  # noqa: E402
from irlegal.ranking.pipeline import Context  # noqa: E402

ctx = Context()
qs = [q for q in ctx.corpus.queries("val") if ctx.relevant(q)]
own = ctx.own_idx(qs)
sc = TextScorer(ctx)
qt = [sc.query_terms(q.text) for q in qs]
authority = ctx.graph.base.astype(np.float32)


def full_ranking(s, i):
    o = np.lexsort((ctx.tie, -s))
    if own[i] >= 0:
        o = o[o != own[i]]
    return [ctx.ids[d] for d in o]


def summarize(name, family, lat, cands, posts, rankings, extra=None):
    ms = [evaluate_ranking(r, ctx.relevant(q), (10, 20)) for r, q in zip(rankings, qs)]
    return {"method": name, "family": family, "median_ms": round(float(np.median(lat)) * 1e3, 3), "p95_ms": round(float(np.percentile(lat, 95)) * 1e3, 3),
            "mean_candidates_scored": round(float(np.mean(cands)), 1), "mean_postings_processed": round(float(np.mean(posts)), 1),
            "MAP": round(float(np.mean([m["MAP"] for m in ms])), 4), "R@10": round(float(np.mean([m["R@10"] for m in ms])), 4),
            "R@20": round(float(np.mean([m["R@20"] for m in ms])), 4), **(extra or {})}


def run_text(name, family, fn):
    """fn(i, rows, w) -> (scores, postings, docs_scored); latency includes selection."""
    lat, cands, posts, rk = [], [], [], []
    for i, (rows, w) in enumerate(qt):
        t = time.perf_counter()
        s, p, c = fn(i, rows, w)
        top = np.argpartition(-s, 20)[:20]
        lat.append(time.perf_counter() - t)
        cands.append(c); posts.append(p); rk.append(full_ranking(s, i))
    return summarize(name, family, lat, cands, posts, rk)


rows_out = []
exh = run_text("exhaustive tf-idf", "baseline", lambda i, r, w: sc.score(r, w))
rows_out.append(exh)
for thr in (1.0, 1.5, 2.0):
    for m in (1, 2, 3):
        sel = EliminationSelector(sc, thr, m)

        def fn(i, r, w, sel=sel):
            r2, w2 = sel.terms_kept(r, w)
            if len(r2) == 0:
                return sc.score(r, w)
            cnt = np.zeros(sc.n, np.int32)
            for rr in r2:
                a, b = sc.T.indptr[rr], sc.T.indptr[rr + 1]
                cnt[sc.T.indices[a:b]] += 1
            return sc.score(r2, w2, cnt >= min(m, len(r2)))
        rows_out.append(run_text(f"elimination idf>={thr}, >= {m} terms", "index elimination", fn))
for r_ in (50, 100, 200, 500):
    ch = ChampionSelector(sc, r_)
    rows_out.append(run_text(f"champion lists r={r_}", "champion lists", lambda i, r, w, ch=ch: sc.score(r, w, ch.select_mask(r))))
for name, kw in (("tiers fall-through 20% -> 50% -> 100%", dict(fall_through=True)),
                 ("tier 1 only (top 20% by authority)", dict(fall_through=False, max_fraction=0.2)),
                 ("tiers 1-2 only (top 50% by authority)", dict(fall_through=False, max_fraction=0.5))):
    ts = TierSelector(sc, authority, **kw)
    rows_out.append(run_text(name, "authority tiers", lambda i, r, w, ts=ts: sc.score(r, w, ts.select_mask(r, 20)[0])))

# ---- heap vs full sort on the exhaustive score vectors
heap = []
scores_list = [sc.score(r, w)[0] for r, w in qt[:200]]
for K in (10, 100):
    for name, fn in (("full sort", top_k_sort), ("heap top-K", top_k_heap)):
        lat = []
        for s in scores_list:
            lst = s.tolist()
            t = time.perf_counter(); fn(lst, K); lat.append(time.perf_counter() - t)
        heap.append({"K": K, "method": name, "median_ms": round(float(np.median(lat)) * 1e3, 3), "p95_ms": round(float(np.percentile(lat, 95)) * 1e3, 3)})
    lat = []
    for s in scores_list:
        t = time.perf_counter(); np.argpartition(-s, K)[:K]; lat.append(time.perf_counter() - t)
    heap.append({"K": K, "method": "numpy argpartition (reference)", "median_ms": round(float(np.median(lat)) * 1e3, 3), "p95_ms": round(float(np.percentile(lat, 95)) * 1e3, 3)})
same = all(top_k_heap(s.tolist(), 20) == top_k_sort(s.tolist(), 20) for s in scores_list[:50])

# ---- cluster pruning on the neighbour search, end to end through Config A
nidx = ctx.nidx
pr = ClusterPruner(nidx, seed=ctx.seed)
texts = [q.text for q in qs]
F0 = ctx.features(qs, loo=True)
mask0 = ctx.first_stage_mask(F0["text"], own)


def config_a_rows(votes):
    F = dict(F0); F["neighbour"] = votes
    return ctx.rank_ids(qs, ctx.net(F, mask0), mask0, F0["text"]), ctx.rank_ids(qs, votes, np.ones_like(mask0), np.zeros_like(F0["text"]))


def pruned_votes(b):
    import scipy.sparse as sp
    V = np.zeros((len(qs), ctx.n), np.float32)
    lat, cand = [], []
    for i, t in enumerate(texts):
        t0 = time.perf_counter()
        q = nidx._query_matrix([t])
        rows = pr.candidate_rows(q, b)
        s = (q @ nidx.D[rows].T).toarray().ravel()
        top = np.argsort(-s, kind="stable")[:ctx.k_nb]
        w = np.power(np.maximum(s[top], 0), ctx.p_nb)
        V[i] = np.asarray((sp.csr_matrix(w[None, :]) @ nidx.C[rows[top]]).todense()).ravel()
        lat.append(time.perf_counter() - t0); cand.append(len(pr.leaders) + len(rows))
    return V, lat, cand


lat, cand = [], []
for t in texts:
    t0 = time.perf_counter(); q = nidx._query_matrix([t]); s = (q @ nidx.D.T).toarray().ravel()
    np.argpartition(-s, ctx.k_nb)[:ctx.k_nb]; lat.append(time.perf_counter() - t0); cand.append(nidx.D.shape[0])
cluster = []
ex_A, ex_N = config_a_rows(F0["neighbour"])
cluster.append(summarize("exhaustive neighbour search (Config A)", "cluster pruning", lat, cand, cand, ex_A))
cluster.append(summarize("exhaustive neighbour search (neighbour votes alone)", "cluster pruning", lat, cand, cand, ex_N))
for b in (1, 2, 3):
    V, lat, cand = pruned_votes(b)
    A, N = config_a_rows(V)
    cluster.append(summarize(f"cluster pruning b={b} (Config A)", "cluster pruning", lat, cand, cand, A, {"leaders": len(pr.leaders)}))
    cluster.append(summarize(f"cluster pruning b={b} (neighbour votes alone)", "cluster pruning", lat, cand, cand, N))

base = {"text": exh, "configA": cluster[0], "nbalone": cluster[1]}
for r in rows_out:
    r["MAP_retained"] = round(r["MAP"] / exh["MAP"], 4); r["R@10_retained"] = round(r["R@10"] / exh["R@10"], 4)
for r in cluster:
    ref = cluster[1] if "alone" in r["method"] else cluster[0]
    r["MAP_retained"] = round(r["MAP"] / ref["MAP"], 4); r["R@10_retained"] = round(r["R@10"] / ref["R@10"], 4)
out = {"split": "dev", "n_queries": len(qs), "pool_docs": ctx.n, "train_queries_in_neighbour_index": int(nidx.D.shape[0]),
       "note": "text-stage rows are retained relative to exhaustive tf-idf; cluster rows relative to exhaustive neighbour search; latency is machine dependent",
       "text_stage": rows_out, "cluster_pruning": cluster, "heap_vs_sort": heap, "heap_equals_sort_on_50_queries": bool(same)}
(Path(repo_path("results")) / "efficiency.json").write_text(json.dumps(out, indent=1))
with open(Path(repo_path("results")) / "efficiency.csv", "w", newline="") as f:
    allr = rows_out + cluster
    w = csv.DictWriter(f, fieldnames=sorted({k for r in allr for k in r}, key=lambda k: (k != "method", k)), restval="")
    w.writeheader(); w.writerows(allr)
for r in rows_out + cluster:
    print(f"{r['method'][:56]:56s} med {r['median_ms']:7.2f}ms p95 {r['p95_ms']:7.2f} cands {r['mean_candidates_scored']:8.1f} MAP {r['MAP']:.4f} ({r['MAP_retained']:.2f}) R@10 {r['R@10']:.4f} ({r['R@10_retained']:.2f})")
print(json.dumps(heap))
