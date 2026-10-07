"""Zone-pair features and weight learning (spec 9.4, DECISIONS D17). Owner: WS3.

Feature (qv, pz) = lnc.ltc cosine between the query view `qv` (facts | issues | facts_issues) and
pool-document zone `pz` (facts, issues, arguments, reasoning, decision, statute_analysis,
precedent_analysis, all). Each pool zone uses its own df; N is the pool size. Document side:
w = (1 + log10 tf) / ||.||; query side: w = (1 + log10 tf) * log10(N / df), cosine-normalised.
This is the same arithmetic as ranking/vsm.py, batched with scipy.sparse (a test checks they agree).

Score(q, d) = sum over (qv, pz) of W[qv][pz] * cosine(q_qv, d_pz), W >= 0 and sum W = 1.
Learning: coordinate ascent on MAP over first-stage candidates.
"""
from collections import Counter
from typing import Dict, List, Sequence, Tuple

import numpy as np
import scipy.sparse as sp

QUERY_VIEWS = ("facts", "issues", "facts_issues")
POOL_ZONES = ("facts", "issues", "arguments", "reasoning", "decision", "statute_analysis", "precedent_analysis", "all")
FEATURES: List[Tuple[str, str]] = [(qv, pz) for qv in QUERY_VIEWS for pz in POOL_ZONES]
BASE_FEATURE = FEATURES.index(("facts_issues", "all"))      # = the tf-idf Facts+Issues baseline


class ZoneMatrices:
    """lnc document matrices (n_terms x n_docs, CSR) for the pool zones of an InvertedIndex."""

    def __init__(self, index, analyzer):
        self.index, self.analyzer = index, analyzer
        self.n = index.n_docs()
        self.T: Dict[str, sp.csr_matrix] = {}
        for z in POOL_ZONES:
            zi = index.zones[z]
            w = 1.0 + np.log10(zi.tfs.astype(np.float64))
            norm = np.sqrt(np.bincount(zi.docs, weights=w * w, minlength=self.n))
            norm[norm == 0] = 1.0
            self.T[z] = sp.csr_matrix((w / norm[zi.docs], zi.docs, zi.offsets), shape=(len(zi.terms), self.n))

    def _query_matrix(self, zone: str, counters: List[Counter]) -> sp.csr_matrix:
        zi = self.index.zones[zone]
        indptr, cols, vals = [0], [], []
        for c in counters:
            row = []
            for t, tf in c.items():
                r = zi.row.get(t)
                if r is not None:
                    df = zi.df_arr[r]
                    row.append((r, (1.0 + np.log10(tf)) * np.log10(self.n / df)))
            if row:
                v = np.array([x[1] for x in row])
                v = v / np.sqrt((v ** 2).sum())
                cols.extend(x[0] for x in row); vals.extend(v)
            indptr.append(len(cols))
        return sp.csr_matrix((vals, cols, indptr), shape=(len(counters), len(zi.terms)))

    def cosines(self, view_texts: Dict[str, List[str]], chunk: int = 100):
        """Yield (start, array[chunk, n_docs, len(FEATURES)] float32) over query chunks."""
        nq = len(next(iter(view_texts.values())))
        toks = {v: [Counter(self.analyzer.analyze(t)) for t in ts] for v, ts in view_texts.items()}
        for s in range(0, nq, chunk):
            e = min(nq, s + chunk)
            out = np.zeros((e - s, self.n, len(FEATURES)), dtype=np.float32)
            for v in QUERY_VIEWS:
                for z in POOL_ZONES:
                    Q = self._query_matrix(z, toks[v][s:e])
                    out[:, :, FEATURES.index((v, z))] = (Q @ self.T[z]).toarray()
            yield s, out


def first_stage_and_features(zm: ZoneMatrices, queries, n_cand: int, tie: np.ndarray, own_idx: List):
    """Candidates = top n_cand docs by the first stage (feature facts_issues x all), own case removed.

    Returns cand (nq, n_cand) int32 in first-stage order, X (nq, n_cand, K) float32, full_order (nq, n) int16/32.
    """
    views = {"facts": [q.zones.get("facts", "") for q in queries], "issues": [q.zones.get("issues", "") for q in queries],
             "facts_issues": [q.text for q in queries]}
    cand = np.zeros((len(queries), n_cand), dtype=np.int32)
    X = np.zeros((len(queries), n_cand, len(FEATURES)), dtype=np.float32)
    full = np.zeros((len(queries), zm.n), dtype=np.int32)
    for s, block in zm.cosines(views):
        for j in range(block.shape[0]):
            q = s + j
            base = block[j, :, BASE_FEATURE].astype(np.float64)
            if own_idx[q] is not None:
                base[own_idx[q]] = -np.inf
            order = np.lexsort((tie, -base))
            full[q] = order
            cand[q] = order[:n_cand]
            X[q] = block[j, cand[q], :]
    return cand, X, full


def map_from_scores(scores: np.ndarray, rel: np.ndarray, n_rel: np.ndarray) -> np.ndarray:
    """Per-query AP of candidate rankings. scores, rel: (nq, N); n_rel: relevant count incl. those outside N."""
    order = np.argsort(-scores, axis=1, kind="stable")
    r = np.take_along_axis(rel, order, axis=1).astype(np.float64)
    prec = np.cumsum(r, axis=1) / np.arange(1, r.shape[1] + 1)
    return (prec * r).sum(axis=1) / np.maximum(n_rel, 1)


def learn_weights(X, rel, n_rel, dev=None, init=None, sweeps: int = 6, grid=(0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6)):
    """Coordinate ascent on train MAP. Weights are non-negative; reported normalised to sum 1.

    dev = (X_dev, rel_dev, n_rel_dev) is only used to record the dev MAP after each sweep.
    Returns (list of normalised weight vectors, one per sweep incl. the start; history list of dicts).
    """
    K = X.shape[2]
    w = np.zeros(K) if init is None else np.array(init, dtype=np.float64)
    if init is None:
        w[BASE_FEATURE] = 1.0

    def f(wv):
        return float(map_from_scores(X @ wv.astype(np.float32), rel, n_rel).mean())

    best = f(w)
    hist = [{"sweep": 0, "train_MAP": round(best, 5),
             **({"dev_MAP": round(float(map_from_scores(dev[0] @ (w / w.sum()).astype(np.float32), dev[1], dev[2]).mean()), 5)} if dev else {})}]
    ws = [w / w.sum()]
    for sw in range(1, sweeps + 1):
        improved = False
        for k in range(K):
            total = w.sum()
            cur = w[k]
            for v in grid:
                cand = max(v * total, 0.0)
                if abs(cand - cur) < 1e-12:
                    continue
                w2 = w.copy(); w2[k] = cand
                if w2.sum() <= 0:
                    continue
                m = f(w2)
                if m > best + 1e-6:
                    best, w, improved = m, w2, True
                    cur = cand
        wn = w / w.sum()
        h = {"sweep": sw, "train_MAP": round(best, 5)}
        if dev:
            h["dev_MAP"] = round(float(map_from_scores(dev[0] @ wn.astype(np.float32), dev[1], dev[2]).mean()), 5)
        hist.append(h)
        ws.append(wn)
        if not improved:
            break
    return ws, hist
