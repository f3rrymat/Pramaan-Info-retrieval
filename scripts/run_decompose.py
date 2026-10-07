"""N6 issue decomposition on DEV: sub-queries from the Issues zone, tf-idf each, fuse with RRF; compare with the single
Facts+Issues query. Honest report even if negative. Saves results/decompose_dev.json."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.evaluation.metrics import evaluate_ranking  # noqa: E402
from irlegal.query.decompose import decompose, rrf  # noqa: E402
from irlegal.ranking.pipeline import Context  # noqa: E402

ctx = Context()
qs = [q for q in ctx.corpus.queries("val") if ctx.relevant(q)]
own = ctx.own_idx(qs)
single = ctx.text_matrix([q.text for q in qs])
subs = [decompose(q.zones.get("issues", "")) for q in qs]
flat = [t for s in subs for t in s]
M = ctx.text_matrix(flat) if flat else np.zeros((0, ctx.n), np.float32)
off = np.concatenate(([0], np.cumsum([len(s) for s in subs])))


def order(scores, i):
    s = scores.astype(np.float64).copy()
    if own[i] >= 0:
        s[own[i]] = -np.inf
    o = np.lexsort((ctx.tie, -s))
    return [ctx.ids[d] for d in o if np.isfinite(s[d])]


def fused(i, include_single, top=1000):
    lists = [order(M[j], i)[:top] for j in range(off[i], off[i + 1])]
    base = order(single[i], i)
    if include_single or not lists:
        lists = lists + [base[:top]]
    ranked = [d for d, _ in rrf(lists)]
    seen = set(ranked)
    return ranked + [d for d in base if d not in seen]


variants = {"single query (tf-idf, Facts+Issues)": lambda i: order(single[i], i),
            "RRF of issue sub-queries only": lambda i: fused(i, False),
            "RRF of issue sub-queries + the single query": lambda i: fused(i, True)}
per = {n: [evaluate_ranking(f(i), ctx.relevant(q)) for i, q in enumerate(qs)] for n, f in variants.items()}
multi = np.array([len(s) >= 2 for s in subs])
rng = np.random.default_rng(ctx.seed)
BI = rng.integers(0, len(qs), size=(1000, len(qs)))
out = {"split": "dev", "n_queries": len(qs), "queries_with_two_or_more_issue_sub_queries": int(multi.sum()),
       "mean_sub_queries_per_query": round(float(np.mean([len(s) for s in subs])), 2), "queries_without_issue_text": int(sum(1 for s in subs if not s)), "rows": {}}
base = per["single query (tf-idf, Facts+Issues)"]
for n, ms in per.items():
    row = {"all_queries": {k: round(float(np.mean([m[k] for m in ms])), 4) for k in ("MAP", "MRR", "nDCG@10", "R@10", "R@20")},
           "queries_with_2plus_sub_queries": {k: round(float(np.mean([m[k] for m, f in zip(ms, multi) if f])), 4) for k in ("MAP", "R@10")}}
    if n != "single query (tf-idf, Facts+Issues)":
        d = np.array([a["MAP"] - b["MAP"] for a, b in zip(ms, base)])
        m = d[BI].mean(axis=1)
        row["MAP_diff_vs_single_[mean,lo95,hi95]"] = [round(float(d.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]
        d10 = np.array([a["R@10"] - b["R@10"] for a, b in zip(ms, base)]); m10 = d10[BI].mean(axis=1)
        row["R@10_diff_vs_single_[mean,lo95,hi95]"] = [round(float(d10.mean()), 4), round(float(np.percentile(m10, 2.5)), 4), round(float(np.percentile(m10, 97.5)), 4)]
    out["rows"][n] = row
(Path(ROOT) / "results" / "decompose_dev.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
