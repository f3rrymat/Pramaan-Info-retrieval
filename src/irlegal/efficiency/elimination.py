"""Index elimination (IIR 7.1.4). Owner: WS4. Implements CandidateSelector.

Keep only query terms with idf = log10(N/df) >= threshold, and only documents that contain at least
`min_match` of those terms. `terms_kept` tells the scorer which postings to process.
"""
from typing import Optional, Set

import numpy as np

from irlegal.common.schema import Query


class EliminationSelector:
    def __init__(self, scorer, idf_threshold: float = 1.0, min_match: int = 1):
        self.sc, self.thr, self.min_match = scorer, idf_threshold, min_match

    def terms_kept(self, rows: np.ndarray, w: np.ndarray):
        keep = self.sc.idf(rows) >= self.thr
        return rows[keep], w[keep]

    def select(self, query: Query, k: int) -> Optional[Set[str]]:
        rows, w = self.sc.query_terms(query.text)
        rows, w = self.terms_kept(rows, w)
        if len(rows) == 0:
            return None
        cnt = np.zeros(self.sc.n, dtype=np.int32)
        for r in rows:
            a, b = self.sc.T.indptr[r], self.sc.T.indptr[r + 1]
            cnt[self.sc.T.indices[a:b]] += 1
        need = min(self.min_match, len(rows))
        return {self.sc.ctx.ids[d] for d in np.flatnonzero(cnt >= need)}
