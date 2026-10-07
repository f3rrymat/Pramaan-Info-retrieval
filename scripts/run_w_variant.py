"""D18: ONE regularised zone-pair variant. 6 a-priori pairs, non-negative, shrinkage toward the whole-text pair
(its weight is fixed at 1; the others are additive and bounded by the grid), stopping by 5-fold CV on train.
Dev is the final check with a paired bootstrap. Reuses the B1 feature cache (1,500 train queries, N=1000).
Saves results/w_variant.json. Usage: python scripts/run_w_variant.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.data.loader import IlPcsrCorpus  # noqa: E402
from irlegal.evaluation.metrics import evaluate_ranking  # noqa: E402
from irlegal.index.inverted import InvertedIndex  # noqa: E402
from irlegal.ranking import zonepair as zp  # noqa: E402

cfg = load_config()
SEED, NMAX = cfg["seed"], 1000
PAIRS = [("facts_issues", "all"), ("facts", "facts"), ("issues", "issues"), ("issues", "reasoning"),
         ("facts", "precedent_analysis"), ("facts_issues", "statute_analysis")]
COLS = [zp.FEATURES.index(p) for p in PAIRS]
GRID, SWEEPS = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8), 5

index = InvertedIndex.load(repo_path(cfg["paths"]["index_dir"]))
corpus = IlPcsrCorpus()
ids = index.doc_ids()
train_all = [q for q in corpus.queries("train") if q.text and q.relevant - {q.case_id}]
rng = np.random.default_rng(SEED)
train = [train_all[i] for i in sorted(rng.choice(len(train_all), size=min(1500, len(train_all)), replace=False))]
dev = [q for q in corpus.queries("val") if q.relevant - {q.case_id}]
C = Path(repo_path("data", "cache"))
z_tr, z_dv = np.load(C / f"b1_train_{len(train)}_{SEED}_{NMAX}.npz"), np.load(C / f"b1_dev_{len(dev)}_{SEED}_{NMAX}.npz")


def rel_info(qs, cand):
    rel = np.zeros(cand.shape, bool); n = np.zeros(len(qs), int)
    for i, q in enumerate(qs):
        r = {index.index_of(d) for d in q.relevant - {q.case_id}} - {None}
        n[i] = len(r); rel[i] = np.isin(cand[i], list(r))
    return rel, n


Xtr, Xdv = z_tr["X"][:, :, COLS], z_dv["X"][:, :, COLS]
rel_tr, n_tr = rel_info(train, z_tr["cand"])
rel_dv, n_dv = rel_info(dev, z_dv["cand"])


def mapf(X, rel, n, a):
    return float(zp.map_from_scores(X @ np.concatenate(([1.0], a)).astype(np.float32), rel, n).mean())


def fit(X, rel, n, sweeps, hold=None):
    """Coordinate ascent on a >= 0 (5 additive weights). Returns a per sweep (index 0 = baseline) and held-out MAP per sweep."""
    a = np.zeros(len(COLS) - 1)
    path, held = [a.copy()], ([mapf(*hold, a)] if hold else [])
    best = mapf(X, rel, n, a)
    for _ in range(sweeps):
        for k in range(len(a)):
            for v in GRID:
                a2 = a.copy(); a2[k] = v
                m = mapf(X, rel, n, a2)
                if m > best + 1e-6:
                    best, a = m, a2
        path.append(a.copy())
        if hold:
            held.append(mapf(*hold, a))
    return path, held


folds = rng.permutation(len(train)) % 5
cv = []
for f in range(5):
    tr, te = folds != f, folds == f
    _, held = fit(Xtr[tr], rel_tr[tr], n_tr[tr], SWEEPS, hold=(Xtr[te], rel_tr[te], n_tr[te]))
    cv.append(held)
cv_mean = np.mean(cv, axis=0)
best_sweep = int(np.argmax(cv_mean))
path, _ = fit(Xtr, rel_tr, n_tr, max(best_sweep, 0))
a = path[best_sweep]
print("CV held-out MAP per sweep (0 = tf-idf):", np.round(cv_mean, 5).tolist(), "-> stop at", best_sweep, "a =", np.round(a, 3).tolist())


def dev_metrics(a):
    w = np.concatenate(([1.0], a)).astype(np.float32)
    s = Xdv @ w
    out = []
    for i, q in enumerate(dev):
        cand = z_dv["cand"][i]
        order = list(cand[np.argsort(-s[i], kind="stable")]) + [d for d in z_dv["full"][i][NMAX:] if d != index.index_of(q.case_id)]
        out.append(evaluate_ranking([ids[d] for d in order], q.relevant - {q.case_id}))
    return out


base, var = dev_metrics(np.zeros(5)), dev_metrics(a)
bi = np.random.default_rng(SEED).integers(0, len(dev), size=(1000, len(dev)))
res = {}
for k in ("MAP", "MRR", "nDCG@10", "R@10", "R@20"):
    d = np.array([v[k] for v in var]) - np.array([b[k] for b in base])
    m = d[bi].mean(axis=1)
    res[k] = {"tfidf": round(float(np.mean([b[k] for b in base])), 4), "variant": round(float(np.mean([v[k] for v in var])), 4),
              "diff": round(float(d.mean()), 4), "ci95": [round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]}
survives = res["MAP"]["ci95"][0] > 0
out = {"pairs": [list(p) for p in PAIRS], "whole_text_weight": 1.0, "additive_weights": dict(zip([f"{a_}x{b_}" for a_, b_ in PAIRS[1:]], np.round(a, 4).tolist())),
       "cv_heldout_MAP_per_sweep_0_is_tfidf": np.round(cv_mean, 5).tolist(), "chosen_sweep": best_sweep,
       "dev": res, "survives_D18_criterion": bool(survives), "train_queries": len(train)}
(Path(repo_path("results")) / "w_variant.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
