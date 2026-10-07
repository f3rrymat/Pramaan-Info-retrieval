"""Leak-safe authority, recency and court prior (spec 9.5; DECISIONS D6, D20). Owner: WS3.

indegree(d) = (# pool documents citing d) + (# TRAIN queries citing d).   authority = log(1 + indegree).
Leave-one-out for a query q being scored:
  * if q is a train query, its own citations are subtracted (it is an edge of the graph);
  * if q's case also sits in the pool (0.3-0.6% of queries), that pool document's own outgoing
    edges are subtracted for EVERY split, because they equal q's gold labels.
Dev and test queries are never edges.
"""
from typing import Dict, Iterable, List, Optional, Set

import numpy as np

COURT_PRIOR = {"SC": 1.0, "HC": 0.6, "OTHER": 0.3}


class AuthorityGraph:
    def __init__(self, doc_ids: List[str], pool_cites: Dict[str, Iterable[str]], train_cites: Dict[str, Iterable[str]]):
        self.doc_ids = doc_ids
        self.idx = {d: i for i, d in enumerate(doc_ids)}
        self.pool_cites = {k: {c for c in v if c in self.idx} for k, v in pool_cites.items()}
        self.train_cites = {k: {c for c in v if c in self.idx} for k, v in train_cites.items()}
        self.base = np.zeros(len(doc_ids))
        for cites in list(self.pool_cites.values()) + list(self.train_cites.values()):
            for c in cites:
                self.base[self.idx[c]] += 1

    def indegree_for(self, qid: str, case_id: Optional[str] = None) -> np.ndarray:
        """In-degree vector with the query's own contribution removed (D20)."""
        v = self.base.copy()
        for c in self.train_cites.get(qid, ()):
            v[self.idx[c]] -= 1
        pid = case_id if case_id is not None else qid
        for c in self.pool_cites.get(pid, ()):
            v[self.idx[c]] -= 1
        return v

    def authority_for(self, qid: str, case_id: Optional[str] = None) -> np.ndarray:
        return np.log1p(self.indegree_for(qid, case_id))


def year_of(date: Optional[str]) -> Optional[int]:
    return int(date[:4]) if date and len(date) >= 4 and date[:4].isdigit() else None


def year_gap(query_date: Optional[str], doc_dates: List[Optional[str]]) -> np.ndarray:
    """query year - doc year; NaN where either date is missing (recency is then not applied)."""
    qy = year_of(query_date)
    out = np.full(len(doc_dates), np.nan, dtype=np.float32)
    if qy is None:
        return out
    for i, d in enumerate(doc_dates):
        y = year_of(d)
        if y is not None:
            out[i] = qy - y
    return out


def recency(gap: np.ndarray, tau: float) -> np.ndarray:
    """exp(-gap / tau) for docs that predate the query; 0 where a date is missing or the doc is newer."""
    g = np.where(np.isnan(gap), -1.0, gap)
    return np.where(g >= 0, np.exp(-np.maximum(g, 0) / tau), 0.0).astype(np.float32)


def court_vector(courts: List[Optional[str]]) -> np.ndarray:
    return np.array([COURT_PRIOR.get(c, COURT_PRIOR["OTHER"]) if c else COURT_PRIOR["OTHER"] for c in courts], dtype=np.float32)
