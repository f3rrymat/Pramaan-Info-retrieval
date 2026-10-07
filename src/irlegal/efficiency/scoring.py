"""Shared sparse scorer for the efficiency study (tf-idf lnc.ltc over the whole-text zone). Owner: WS4.

T is the CSR (term x doc) lnc matrix of ranking.zonepair.ZoneMatrices. A query is (term rows, ltc weights).
"""
from collections import Counter
from typing import Optional, Set, Tuple

import numpy as np


class TextScorer:
    def __init__(self, ctx):
        self.ctx, self.T = ctx, ctx.zm.T["all"]
        self.zi = ctx.index.zones["all"]
        self.n = ctx.n
        self.idx_of = ctx.index.index_of

    def query_terms(self, text: str) -> Tuple[np.ndarray, np.ndarray]:
        Q = self.ctx.zm._query_matrix("all", [Counter(self.ctx.an.analyze(text))])
        return Q.indices.copy(), Q.data.copy()

    def idf(self, rows: np.ndarray) -> np.ndarray:
        return np.log10(self.n / self.zi.df_arr[rows])

    def doc_mask(self, ids: Optional[Set[str]]) -> Optional[np.ndarray]:
        if ids is None:
            return None
        m = np.zeros(self.n, bool)
        m[[self.idx_of(d) for d in ids]] = True
        return m

    def score(self, rows, w, mask: Optional[np.ndarray] = None):
        """Returns (scores, postings_processed, docs_scored). Only docs in `mask` accumulate."""
        s = np.zeros(self.n)
        post = 0
        for r, wt in zip(rows, w):
            a, b = self.T.indptr[r], self.T.indptr[r + 1]
            docs, data = self.T.indices[a:b], self.T.data[a:b]
            if mask is not None:
                keep = mask[docs]
                docs, data = docs[keep], data[keep]
            s[docs] += wt * data
            post += len(docs)
        return s, post, int((s > 0).sum())
