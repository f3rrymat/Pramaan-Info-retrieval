"""Cluster pruning (IIR 7.1.6) for the neighbour search over TRAIN queries. Owner: WS4.

About sqrt(N) random leaders; every follower is attached to its nearest leader (cosine on the lnc rows of
the neighbour index). A query is compared with the leaders only, then with the followers of its b
nearest leaders. `select` returns the ids of the train queries that will be compared (a CandidateSelector
over the neighbour index; the ids are train-query ids, not pool documents).
"""
from typing import Optional, Set

import numpy as np

from irlegal.common.schema import Query


class ClusterPruner:
    def __init__(self, nidx, seed: int = 13, n_leaders: Optional[int] = None):
        self.nidx = nidx
        n = nidx.D.shape[0]
        L = n_leaders or int(round(np.sqrt(n)))
        rng = np.random.default_rng(seed)
        self.leaders = np.sort(rng.choice(n, size=L, replace=False))
        sim = (nidx.D @ nidx.D[self.leaders].T).toarray()                # (n, L)
        sim[self.leaders, np.arange(L)] = 2.0                            # a leader follows itself
        self.assign = sim.argmax(axis=1)
        self.members = [np.flatnonzero(self.assign == j) for j in range(L)]
        self.DL = nidx.D[self.leaders]

    def candidate_rows(self, qvec, b: int) -> np.ndarray:
        s = (qvec @ self.DL.T).toarray().ravel()
        near = np.argsort(-s, kind="stable")[:b]
        return np.concatenate([self.members[j] for j in near])

    def select(self, query: Query, k: int, b: int = 1) -> Optional[Set[str]]:
        q = self.nidx._query_matrix([query.text])
        return {self.nidx.qids[i] for i in self.candidate_rows(q, b)}
