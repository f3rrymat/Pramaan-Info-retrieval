"""SMART lnc.ltc cosine ranking over one index zone. Owner: WS3.

Document side (lnc): w = 1 + log10(tf), no idf, cosine-normalised over the document's zone vector.
Query side (ltc):    w = (1 + log10(tf)) * log10(N / df), cosine-normalised over the query's terms.
Note 1 + log10(tf), NOT log10(1 + tf). Query terms absent from the zone vocabulary are ignored.
score(q, d) = sum_t wq(t) * wd(t, d)
"""
from collections import Counter

import numpy as np

from irlegal.common.schema import Query
from .baselines import IndexRanker


class TfidfRanker(IndexRanker):
    def __init__(self, index, analyzer, zone: str = "all", seed: int = 13, label: str = ""):
        super().__init__(index, seed)
        self.analyzer, self.zone = analyzer, zone
        self.name = label or f"tfidf_lnc_ltc[{zone}]"
        z = index.zones[zone]
        w = 1.0 + np.log10(z.tfs.astype(np.float64))
        norm2 = np.bincount(z.docs, weights=w * w, minlength=index.n_docs())
        self._norm = np.sqrt(norm2)
        self._norm[self._norm == 0] = 1.0

    def score_all(self, query: Query) -> np.ndarray:
        z = self.index.zones[self.zone]
        n = self.index.n_docs()
        terms, wq = [], []
        for t, tf in Counter(self.analyzer.analyze(query.text)).items():
            df = self.index.df(t, self.zone)
            if df:
                terms.append(t)
                wq.append((1.0 + np.log10(tf)) * np.log10(n / df))
        scores = np.zeros(n)
        if not terms:
            return scores
        wq = np.array(wq)
        norm_q = np.sqrt((wq ** 2).sum())
        if norm_q > 0:
            wq = wq / norm_q
        for t, w in zip(terms, wq):
            a, b = z.span(t)
            docs = z.docs[a:b]
            scores[docs] += w * (1.0 + np.log10(z.tfs[a:b])) / self._norm[docs]
        return scores
