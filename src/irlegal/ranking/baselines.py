"""Ranker base class plus the two query-independent baselines (random, popularity). Owner: WS3.

Every ranker here exposes `score_all(query) -> np.ndarray` aligned with `index.doc_ids()`
(fast path used by the evaluation runner) and the Ranker protocol's `rank()`.
Ties are broken by a fixed random key (seeded), never by pool order, so a tie cannot favour
whichever documents the parquet file happens to list first.
"""
import zlib
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set

import numpy as np

from irlegal.common.schema import Query, Result


def tie_key(n: int, seed: int = 13) -> np.ndarray:
    return np.random.default_rng(seed).permutation(n)


class IndexRanker:
    name = "base"

    def __init__(self, index, seed: int = 13):
        self.index = index
        self._ids = index.doc_ids()
        self._tie = tie_key(len(self._ids), seed)

    def score_all(self, query: Query) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def order(self, query: Query, exclude: Iterable[str] = (), candidates: Optional[Set[str]] = None):
        """Doc indices best-first. The query's own case and `exclude` are removed; `candidates` restricts."""
        s = self.score_all(query).astype(np.float64)
        drop = [self.index.index_of(d) for d in {query.case_id, *exclude}]
        keep = np.ones(len(s), dtype=bool)
        for i in drop:
            if i is not None:
                keep[i] = False
        if candidates is not None:
            keep &= np.isin(self._ids, list(candidates))
        idx = np.flatnonzero(keep)
        o = np.lexsort((self._tie[idx], -s[idx]))
        return idx[o], s

    def rank(self, query: Query, k: int, **opts) -> List[Result]:
        idx, s = self.order(query, opts.get("exclude", ()), opts.get("candidates"))
        return [Result(self._ids[i], float(s[i]), {"text": float(s[i])}, {"ranker": self.name}) for i in idx[:k]]


class RandomRanker(IndexRanker):
    name = "random"

    def __init__(self, index, seed: int = 13):
        super().__init__(index, seed)
        self.seed = seed

    def score_all(self, query: Query) -> np.ndarray:
        rng = np.random.default_rng([self.seed, zlib.crc32(query.qid.encode())])
        return rng.random(len(self._ids))


class PopularityRanker(IndexRanker):
    """Ignores the query: rank by in-degree from TRAIN queries (D6). Dev/test queries are never edges."""
    name = "popularity"

    def __init__(self, index, train_indegree: Dict[str, int], seed: int = 13):
        super().__init__(index, seed)
        self._pop = np.array([train_indegree.get(d, 0) for d in self._ids], dtype=np.float64)

    def score_all(self, query: Query) -> np.ndarray:
        return self._pop
