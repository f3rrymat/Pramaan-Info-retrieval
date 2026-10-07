"""Champion lists (IIR 7.1.3). Owner: WS4. Implements CandidateSelector.

For every term, the r documents with the highest lnc weight. The candidate set of a query is the union
of its terms' champion lists; only those documents are scored.
"""
from typing import Dict, Optional, Set

import numpy as np

from irlegal.common.schema import Query


class ChampionSelector:
    def __init__(self, scorer, r: int):
        self.sc, self.r = scorer, r
        T = scorer.T
        self.champ: Dict[int, np.ndarray] = {}
        for row in range(T.shape[0]):
            a, b = T.indptr[row], T.indptr[row + 1]
            docs, data = T.indices[a:b], T.data[a:b]
            self.champ[row] = docs if len(docs) <= r else docs[np.argpartition(-data, r - 1)[:r]]

    def select_mask(self, rows: np.ndarray) -> np.ndarray:
        m = np.zeros(self.sc.n, bool)
        for r in rows:
            m[self.champ[r]] = True
        return m

    def select(self, query: Query, k: int) -> Optional[Set[str]]:
        rows, _ = self.sc.query_terms(query.text)
        m = self.select_mask(rows)
        return {self.sc.ctx.ids[d] for d in np.flatnonzero(m)}
