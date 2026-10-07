"""Shared pipeline context: feature matrices, Config A, ranking, temporal filter. Owner: WS3/WS4.

One place builds the (n_queries x n_pool_docs) feature matrices so the runner, leakage audit,
efficiency study and the API all score the same way.
Config A (D23): first stage = tf-idf top 1000; net = w_text*text + w_nb*neighbour + w_auth*authority,
each min-max normalised over the candidate set; weights frozen from train CV (results/config_a_frozen.json).
"""
import json
from collections import Counter
from typing import Dict, List, Optional, Sequence

import numpy as np

from irlegal.common.config import load_config, repo_path
from irlegal.common.schema import Query
from irlegal.data.loader import IlPcsrCorpus
from irlegal.index.inverted import InvertedIndex
from irlegal.preprocess.normalizer import Analyzer
from irlegal.ranking import authority as au
from irlegal.ranking import netscore as ns
from irlegal.ranking import zonepair as zp
from irlegal.ranking.baselines import tie_key
from irlegal.ranking.bm25 import BM25Ranker
from irlegal.ranking.neighbours import NeighbourIndex

FIRST_STAGE = 1000
CONFIG_A_FEATURES = ("text", "neighbour", "authority")


def config_a_path():
    return repo_path(load_config()["paths"]["results_dir"], "config_a_frozen.json")


class Context:
    def __init__(self, corpus: Optional[IlPcsrCorpus] = None):
        cfg = load_config()
        self.cfg, self.seed = cfg, cfg["seed"]
        self.index = InvertedIndex.load(repo_path(cfg["paths"]["index_dir"]))
        self.an = Analyzer(stem=cfg["ws1"]["stemmer"] == "porter")
        self.corpus = corpus or IlPcsrCorpus()
        self.cases = self.corpus.cases()
        self.ids = self.index.doc_ids()
        self.n = len(self.ids)
        self.tie = tie_key(self.n, self.seed)
        self.doc_dates = [c.date for c in self.cases]
        self.court_vec = au.court_vector([c.court for c in self.cases])
        self.zm = zp.ZoneMatrices(self.index, self.an)
        res = repo_path(cfg["paths"]["results_dir"])
        tuned = json.load(open(res / "bm25_tuning.json"))["tuned"]["all"]
        self.bm25 = BM25Ranker(self.index, self.an, "all", k1=tuned["k1"], b=tuned["b"], qtf_mode=tuned["qtf"])
        self.bm25_params = {"k1": tuned["k1"], "b": tuned["b"], "qtf": tuned["qtf"]}
        nb = json.load(open(res / "b2_ablation_dev.json"))["neighbour_best"]
        self.k_nb, self.p_nb = nb["k"], nb["p"]
        self._train_q = None
        self._graph = None
        self._nidx = None
        self._train_indeg = None

    # ------------------------------------------------------------ lazily built train-side structures
    @property
    def train_queries(self) -> List[Query]:
        if self._train_q is None:
            self._train_q = self.corpus.queries("train")
        return self._train_q

    @property
    def graph(self) -> au.AuthorityGraph:
        if self._graph is None:
            self._graph = au.AuthorityGraph(self.ids, {c.doc_id: c.cites_out for c in self.cases},
                                            self.corpus.relevant_ids("train"))
        return self._graph

    @property
    def nidx(self) -> NeighbourIndex:
        if self._nidx is None:
            self._nidx = NeighbourIndex(self.train_queries, self.ids, self.an, max_k=100)   # TRAIN only
        return self._nidx

    @property
    def train_indegree(self) -> np.ndarray:
        if self._train_indeg is None:
            c = self.corpus.train_indegree()
            self._train_indeg = np.array([c.get(d, 0) for d in self.ids], dtype=np.float32)
        return self._train_indeg

    # ------------------------------------------------------------ features
    def own_idx(self, qs: Sequence[Query]) -> np.ndarray:
        return np.array([self.index.index_of(q.case_id) if self.index.index_of(q.case_id) is not None else -1 for q in qs])

    def text_matrix(self, texts: Sequence[str], chunk: int = 250) -> np.ndarray:
        out = np.zeros((len(texts), self.n), dtype=np.float32)
        for s in range(0, len(texts), chunk):
            Q = self.zm._query_matrix("all", [Counter(self.an.analyze(t)) for t in texts[s:s + chunk]])
            out[s:s + chunk] = (Q @ self.zm.T["all"]).toarray()
        return out

    def authority_matrix(self, qs, loo: bool = True, graph: Optional[au.AuthorityGraph] = None) -> np.ndarray:
        g = graph or self.graph
        if loo:
            return np.stack([g.authority_for(q.qid, q.case_id) for q in qs]).astype(np.float32)
        return np.broadcast_to(np.log1p(g.base).astype(np.float32), (len(qs), self.n)).copy()

    def neighbour_matrix(self, qs, loo: bool = True, texts: Optional[Sequence[str]] = None):
        texts = texts if texts is not None else [q.text for q in qs]
        selfs = [q.qid if (loo and q.split == "train") else None for q in qs]
        idx, sim = self.nidx.top_neighbours(list(texts), selfs)
        return self.nidx.votes(idx, sim, self.k_nb, self.p_nb), idx, sim

    def features(self, qs: Sequence[Query], loo: bool = True, bm25: bool = False, text_override=None) -> Dict[str, np.ndarray]:
        F = {"text": self.text_matrix([q.text for q in qs]) if text_override is None else text_override}
        F["authority"] = self.authority_matrix(qs, loo)
        F["neighbour"], F["nb_idx"], F["nb_sim"] = self.neighbour_matrix(qs, loo)
        F["gap"] = np.stack([au.year_gap(q.date, self.doc_dates) for q in qs])
        if bm25:
            F["bm25"] = np.stack([self.bm25.score_all(q) for q in qs]).astype(np.float32)
        return F

    # ------------------------------------------------------------ Config A and ranking
    def config_a(self) -> Dict[str, float]:
        return json.load(open(config_a_path()))["weights"]

    def first_stage_mask(self, text: np.ndarray, own: np.ndarray, top: int = FIRST_STAGE) -> np.ndarray:
        return ns.union_candidates([(text, top)], self.tie, own)

    def net(self, F, mask, weights: Optional[Dict[str, float]] = None) -> np.ndarray:
        w = weights or self.config_a()
        nf = {f: ns.minmax_masked(F[f], mask) for f in w if w[f]}
        return ns.net_scores(nf, w, mask)

    def removed_by_date(self, qs: Sequence[Query]) -> np.ndarray:
        """True where both dates are known and the document is NOT strictly before the query (D15)."""
        rm = np.zeros((len(qs), self.n), bool)
        for i, q in enumerate(qs):
            if q.date:
                for j, d in enumerate(self.doc_dates):
                    if d and d >= q.date:
                        rm[i, j] = True
        return rm

    def both_dates_known(self, qs: Sequence[Query]) -> np.ndarray:
        return np.array([[bool(q.date and d) for d in self.doc_dates] for q in qs])

    def rank_ids(self, qs, net, mask, tail, removed=None) -> List[List[str]]:
        """Best-first id lists: candidates by `net`, then the rest by `tail`; removed docs last; own case dropped."""
        own = self.own_idx(qs)
        out = []
        for i in range(len(qs)):
            key = np.where(mask[i], net[i], -np.inf)
            rm = removed[i].astype(np.int8) if removed is not None else np.zeros(self.n, np.int8)
            o = np.lexsort((self.tie, -tail[i], -key, rm))
            if own[i] >= 0:
                o = o[o != own[i]]
            out.append([self.ids[d] for d in o])
        return out

    def relevant(self, q: Query) -> set:
        return q.relevant - {q.case_id}
