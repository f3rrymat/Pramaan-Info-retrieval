"""N7 citing-case neighbours (DECISIONS D21, D20). Owner: WS3.

Sparse lnc.ltc index over the Facts+Issues text of TRAIN queries only. For a query, take the top-k
most similar train queries (itself excluded when it is a train query) and score each pool document
d by  sum over neighbours n of  sim(q, n)^p * [n cites d].
Dev and test queries can never enter the index: the constructor rejects any non-train query.
Explanations use neighbour ids and similarities only.
"""
from collections import Counter
from typing import Dict, List, Optional, Sequence

import numpy as np
import scipy.sparse as sp


class NeighbourIndex:
    def __init__(self, train_queries, doc_ids: List[str], analyzer, max_k: int = 100):
        bad = [q.qid for q in train_queries if q.split != "train"]
        if bad:
            raise ValueError(f"neighbour index accepts TRAIN queries only; got {len(bad)} non-train")
        self.qids = [q.qid for q in train_queries]
        self.pos = {q: i for i, q in enumerate(self.qids)}
        self.analyzer, self.max_k = analyzer, max_k
        self.doc_idx = {d: i for i, d in enumerate(doc_ids)}
        self.n_docs = len(doc_ids)
        counters = [Counter(analyzer.analyze(q.text)) for q in train_queries]
        self.vocab: Dict[str, int] = {}
        for c in counters:
            for t in c:
                self.vocab.setdefault(t, len(self.vocab))
        rows, cols, vals = [], [], []
        for i, c in enumerate(counters):
            for t, tf in c.items():
                rows.append(i); cols.append(self.vocab[t]); vals.append(1.0 + np.log10(tf))
        D = sp.csr_matrix((vals, (rows, cols)), shape=(len(counters), len(self.vocab)))
        df = np.bincount(D.indices, minlength=len(self.vocab))
        self.idf = np.log10(len(counters) / np.maximum(df, 1))
        norm = np.sqrt(np.asarray(D.multiply(D).sum(axis=1)).ravel())
        norm[norm == 0] = 1.0
        self.D = sp.diags(1.0 / norm) @ D                                    # lnc rows
        crow, ccol = [], []
        for i, q in enumerate(train_queries):
            for d in q.relevant:
                if d in self.doc_idx:
                    crow.append(i); ccol.append(self.doc_idx[d])
        self.C = sp.csr_matrix((np.ones(len(crow)), (crow, ccol)), shape=(len(counters), self.n_docs))   # cites

    def _query_matrix(self, texts: Sequence[str]) -> sp.csr_matrix:
        rows, cols, vals = [], [], []
        for i, t in enumerate(texts):
            c = Counter(self.analyzer.analyze(t))
            row = [(self.vocab[w], (1.0 + np.log10(tf)) * self.idf[self.vocab[w]]) for w, tf in c.items() if w in self.vocab]
            if row:
                v = np.array([x[1] for x in row])
                n = np.sqrt((v ** 2).sum())
                for (j, _), x in zip(row, v / (n if n > 0 else 1.0)):
                    rows.append(i); cols.append(j); vals.append(x)
        return sp.csr_matrix((vals, (rows, cols)), shape=(len(texts), len(self.vocab)))

    def top_neighbours(self, texts: Sequence[str], self_ids: Sequence[Optional[str]], chunk: int = 250):
        """Returns (idx, sim) arrays (nq, max_k), most similar first; a query's own train row is excluded."""
        nq = len(texts)
        idx = np.zeros((nq, self.max_k), dtype=np.int32)
        sim = np.zeros((nq, self.max_k), dtype=np.float32)
        for s in range(0, nq, chunk):
            e = min(nq, s + chunk)
            S = (self._query_matrix(texts[s:e]) @ self.D.T).toarray()
            for j in range(e - s):
                me = self.pos.get(self_ids[s + j]) if self_ids[s + j] is not None else None
                if me is not None:
                    S[j, me] = -1.0                                       # leave-one-out (D20)
            top = np.argpartition(-S, self.max_k, axis=1)[:, :self.max_k]
            ts = np.take_along_axis(S, top, axis=1)
            o = np.argsort(-ts, axis=1, kind="stable")
            idx[s:e] = np.take_along_axis(top, o, axis=1)
            sim[s:e] = np.take_along_axis(ts, o, axis=1)
        return idx, np.maximum(sim, 0.0)

    def votes(self, idx: np.ndarray, sim: np.ndarray, k: int, p: float) -> np.ndarray:
        """(nq, n_docs) dense vote matrix: sum over the top-k neighbours of sim^p * cites."""
        nq = idx.shape[0]
        w = sp.csr_matrix((np.power(sim[:, :k], p).ravel(), idx[:, :k].ravel(), np.arange(0, nq * k + 1, k)),
                          shape=(nq, len(self.qids)))
        return np.asarray((w @ self.C).todense(), dtype=np.float32)

    def explain(self, idx_row: np.ndarray, sim_row: np.ndarray, doc_index: int, k: int) -> List[Dict]:
        """Neighbour ids and similarities (never text) among the top-k that cite the document."""
        out = []
        for n, s in zip(idx_row[:k], sim_row[:k]):
            if self.C[n, doc_index]:
                out.append({"neighbour_id": self.qids[n], "similarity": round(float(s), 4)})
        return out
