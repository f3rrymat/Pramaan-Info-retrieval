"""Authority-ordered tiers (IIR 7.2.1). Owner: WS4. Implements CandidateSelector.

Documents are ranked by query-independent authority (in-degree from pool + TRAIN edges only) and cut into
tiers by cumulative fraction (e.g. 0.2, 0.5, 1.0). With `fall_through` the selector stops at the first
tier whose accumulated documents match at least k results; otherwise it returns exactly the first tier
up to `max_fraction`.
"""
from typing import Optional, Sequence, Set

import numpy as np

from irlegal.common.schema import Query


class TierSelector:
    def __init__(self, scorer, authority: np.ndarray, fractions: Sequence[float] = (0.2, 0.5, 1.0), fall_through: bool = True,
                 max_fraction: Optional[float] = None):
        self.sc, self.fractions, self.fall, self.max_fraction = scorer, tuple(fractions), fall_through, max_fraction
        order = np.lexsort((scorer.ctx.tie, -authority))
        self.rank = np.empty(len(order), dtype=np.int64)
        self.rank[order] = np.arange(len(order))
        self.n = len(order)

    def select_mask(self, rows: np.ndarray, k: int):
        match = np.zeros(self.n, bool)
        for r in rows:
            a, b = self.sc.T.indptr[r], self.sc.T.indptr[r + 1]
            match[self.sc.T.indices[a:b]] = True
        if not self.fall:
            frac = self.max_fraction or self.fractions[-1]
            return self.rank < int(np.ceil(frac * self.n)), 1
        for t, f in enumerate(self.fractions, 1):
            m = self.rank < int(np.ceil(f * self.n))
            if (m & match).sum() >= k or f >= 1.0:
                return m, t
        return m, len(self.fractions)

    def select(self, query: Query, k: int) -> Optional[Set[str]]:
        rows, _ = self.sc.query_terms(query.text)
        m, _ = self.select_mask(rows, k)
        return {self.sc.ctx.ids[d] for d in np.flatnonzero(m)}
