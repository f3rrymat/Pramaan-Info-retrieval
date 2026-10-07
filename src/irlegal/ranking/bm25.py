"""Okapi BM25 over one index zone. Owner: WS3.

score(q, d) = sum over query tokens t (repeats count) of
    idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl)),   idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5))
k1 = 1.2, b = 0.75 (config ws3.bm25). dl, avgdl are token counts of the same zone.
Query-term handling `qtf_mode` (D14): "raw" multiplies by the query term count (default),
"binary" counts each distinct term once, "saturated" uses qtf * (k3 + 1) / (qtf + k3), k3 = 1.2.
"""
from collections import Counter

import numpy as np

from irlegal.common.config import load_config
from irlegal.common.schema import Query
from .baselines import IndexRanker


class BM25Ranker(IndexRanker):
    def __init__(self, index, analyzer, zone: str = "all", k1=None, b=None, seed: int = 13, label: str = "", qtf_mode: str = "raw", k3: float = 1.2):
        super().__init__(index, seed)
        assert qtf_mode in ("raw", "binary", "saturated")
        self.qtf_mode, self.k3 = qtf_mode, k3
        cfg = load_config()["ws3"]["bm25"]
        self.k1, self.b = (cfg["k1"] if k1 is None else k1), (cfg["b"] if b is None else b)
        self.analyzer, self.zone = analyzer, zone
        self.name = label or f"bm25[{zone}]"
        dl = index.doc_len_array(zone).astype(np.float64)
        self._dl = dl
        self._avgdl = dl.mean() if dl.size else 1.0

    def score_all(self, query: Query) -> np.ndarray:
        z = self.index.zones[self.zone]
        n = self.index.n_docs()
        scores = np.zeros(n)
        for t, qtf in Counter(self.analyzer.analyze(query.text)).items():
            sp = z.span(t)
            if sp is None:
                continue
            a, bnd = sp
            df = bnd - a
            idf = np.log(1.0 + (n - df + 0.5) / (df + 0.5))
            docs, tf = z.docs[a:bnd], z.tfs[a:bnd].astype(np.float64)
            denom = tf + self.k1 * (1.0 - self.b + self.b * self._dl[docs] / self._avgdl)
            w = qtf if self.qtf_mode == "raw" else 1.0 if self.qtf_mode == "binary" else qtf * (self.k3 + 1.0) / (qtf + self.k3)
            scores[docs] += w * idf * tf * (self.k1 + 1.0) / denom
        return scores
