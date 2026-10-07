"""Net score, union first stage and weight search (spec 9.5; DECISIONS D19, D22). Owner: WS3.

net(q, d) = sum_f w_f * norm_f(q, d),  w_f >= 0, sum w = 1, over the candidate set of q.
norm_f = min-max within the candidate set (a constant column becomes 0).
Features: text, statute, authority, neighbour, recency, court  (schema.COMPONENTS plus neighbour).
Weights come from random search; every trial is scored on train queries only, with fold structure
for the nested-CV estimate. All score matrices are (n_queries, n_docs) float32.
"""
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

FEATURE_NAMES = ("text", "statute", "authority", "neighbour", "recency", "court")


def union_candidates(sources: Sequence[Tuple[np.ndarray, int]], tie: np.ndarray, exclude: np.ndarray) -> np.ndarray:
    """Boolean mask (nq, n): union over (score matrix, top-n) sources. `exclude[i]` = own doc index or -1."""
    nq, n = sources[0][0].shape
    mask = np.zeros((nq, n), dtype=bool)
    for S, top in sources:
        for i in range(nq):
            s = S[i].astype(np.float64).copy()
            if exclude[i] >= 0:
                s[exclude[i]] = -np.inf
            sel = np.lexsort((tie, -s))[:top]
            mask[i, sel[s[sel] > -np.inf]] = True
    if (exclude >= 0).any():
        mask[np.arange(nq)[exclude >= 0], exclude[exclude >= 0]] = False
    return mask


def minmax_masked(F: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Per-query min-max over candidates; non-candidates get 0 (they are masked out later)."""
    lo = np.where(mask, F, np.inf).min(axis=1, keepdims=True)
    hi = np.where(mask, F, -np.inf).max(axis=1, keepdims=True)
    rng = hi - lo
    out = np.where(rng > 0, (F - lo) / np.where(rng > 0, rng, 1.0), 0.0)
    return np.where(mask, out, 0.0).astype(np.float32)


def net_scores(norm_feats: Dict[str, np.ndarray], w: Dict[str, float], mask: np.ndarray) -> np.ndarray:
    s = np.zeros(mask.shape, dtype=np.float32)
    for f, x in w.items():
        if x:
            s += np.float32(x) * norm_feats[f]
    return np.where(mask, s, -np.inf)


def pair_ranks(S: np.ndarray, qi: np.ndarray, di: np.ndarray, chunk: int = 1500) -> np.ndarray:
    """Expected rank (ties split) of each relevant pair (query row qi, doc di); inf if the doc is not a candidate."""
    out = np.zeros(len(qi))
    for s in range(0, len(qi), chunk):
        a, b = qi[s:s + chunk], di[s:s + chunk]
        rows = S[a]
        v = rows[np.arange(len(a)), b][:, None]
        greater = (rows > v).sum(axis=1)
        equal = (rows == v).sum(axis=1)
        r = 1 + greater + (equal - 1) / 2.0
        out[s:s + chunk] = np.where(np.isneginf(v[:, 0]), np.inf, r)
    return out


def ap_from_ranks(ranks: np.ndarray, qi: np.ndarray, nq: int, n_rel: np.ndarray) -> np.ndarray:
    """Per-query AP from relevant-pair ranks; pairs with infinite rank (not candidates) add 0."""
    ok = np.isfinite(ranks)
    qi, ranks = qi[ok], ranks[ok]
    o = np.lexsort((ranks, qi))
    qi, ranks = qi[o], ranks[o]
    pos = np.arange(len(qi)) - np.searchsorted(qi, qi) + 1          # 1-based position among the query's relevant docs
    ap = np.zeros(nq)
    np.add.at(ap, qi, pos / ranks)
    return ap / np.maximum(n_rel, 1)


def random_search(norm_feats, mask, qi, di, n_rel, features: Sequence[str], folds: np.ndarray, trials: int = 200,
                  taus: Optional[Sequence[float]] = None, build_recency=None, seed: int = 13, seeds_weights=()):
    """Random search over simplex weights (and recency tau). Returns list of trial dicts sorted by CV MAP.

    Each trial: per-query AP on all train queries; `fold_map[f]` = mean AP of fold f.
    """
    rng = np.random.default_rng(seed)
    nq = mask.shape[0]
    out = []
    cache_tau: Dict[float, np.ndarray] = {}
    cand_w = [dict(zip(features, np.eye(len(features))[i])) for i in range(len(features))] + [dict(sw) for sw in seeds_weights]
    cand_w += [dict(zip(features, rng.dirichlet(np.ones(len(features))))) for _ in range(trials)]
    for w in cand_w:
        tau = float(rng.choice(taus)) if taus and "recency" in features and w.get("recency", 0) else (taus[0] if taus else None)
        if tau is not None and "recency" in features and build_recency is not None and tau not in cache_tau:
            cache_tau[tau] = minmax_masked(build_recency(tau), mask)
        nf = dict(norm_feats)
        if tau is not None and "recency" in features and build_recency is not None:
            nf["recency"] = cache_tau[tau]
        S = net_scores(nf, {k: float(v) for k, v in w.items()}, mask)
        ranks = pair_ranks(S, qi, di)
        ap = ap_from_ranks(ranks, qi, nq, n_rel)
        out.append({"w": {k: float(v) for k, v in w.items()}, "tau": tau, "MAP": float(ap.mean()),
                    "fold_map": [float(ap[folds == f].mean()) for f in range(int(folds.max()) + 1)], "ap": ap})
    out.sort(key=lambda t: -t["MAP"])
    return out


def nested_cv_map(trials: List[Dict], folds: np.ndarray) -> float:
    """Select the best trial on 4 folds, score on the held-out fold, average over folds."""
    res = []
    for f in range(int(folds.max()) + 1):
        sizes = np.array([(folds == g).sum() for g in range(int(folds.max()) + 1)], float)
        best = max(trials, key=lambda t: sum(t["fold_map"][g] * sizes[g] for g in range(len(sizes)) if g != f))
        res.append(best["fold_map"][f])
    return float(np.mean(res))
