"""Batched scipy.sparse cosines must equal the inverted-index lnc.ltc scorer (D17)."""
import random

import numpy as np

from irlegal.common.schema import Case, Query
from irlegal.index.inverted import InvertedIndex
from irlegal.preprocess.normalizer import Analyzer
from irlegal.ranking import zonepair as zp
from irlegal.ranking.vsm import TfidfRanker

WORDS = [f"word{i}" for i in range(60)]


def _corpus(n=40, seed=3):
    rng = random.Random(seed)
    cases = []
    for i in range(n):
        zones = {z: [" ".join(rng.choices(WORDS, k=rng.randint(5, 30)))] for z in
                 ("facts", "issues", "arguments", "reasoning", "decision", "statute_analysis", "precedent_analysis")
                 if rng.random() < 0.8}
        cases.append(Case(doc_id=f"D{i}", title="", text="", zones=zones))
    return cases


def _queries(n=20, seed=4):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        f, s = " ".join(rng.choices(WORDS, k=rng.randint(3, 25))), " ".join(rng.choices(WORDS, k=rng.randint(0, 10)))
        out.append(Query(f"Q{i}", f"Q{i}", f"{f} {s}".strip(), {"facts": f, "issues": s}, set(), None, "val", set()))
    return out


def test_sparse_cosines_match_index_scorer():
    an = Analyzer()
    index = InvertedIndex.build(_corpus(), an)
    zm = zp.ZoneMatrices(index, an)
    qs = _queries()
    views = {"facts": [q.zones["facts"] for q in qs], "issues": [q.zones["issues"] for q in qs],
             "facts_issues": [q.text for q in qs]}
    got = np.concatenate([b for _, b in zm.cosines(views, chunk=7)], axis=0)       # chunking must not matter
    assert got.shape == (20, 40, len(zp.FEATURES))
    for qv in zp.QUERY_VIEWS:
        for pz in zp.POOL_ZONES:
            ranker = TfidfRanker(index, an, pz)
            for qi, q in enumerate(qs):
                text = {"facts": q.zones["facts"], "issues": q.zones["issues"], "facts_issues": q.text}[qv]
                want = ranker.score_all(Query(q.qid, q.case_id, text, {}, set(), None, "val", set()))
                assert np.allclose(got[qi, :, zp.FEATURES.index((qv, pz))], want, atol=1e-5), (qv, pz, qi)


def test_map_from_scores_hand_example():
    scores = np.array([[0.9, 0.8, 0.7, 0.1]])
    rel = np.array([[True, False, True, False]])
    # ranking a(rel) b c(rel) d -> AP = (1/1 + 2/3) / n_rel, with 3 relevant in total (one outside the list)
    assert np.isclose(map_ap(scores, rel, 3), (1 + 2 / 3) / 3)


def map_ap(scores, rel, n):
    return zp.map_from_scores(scores, rel, np.array([n]))[0]


def test_learned_weights_are_nonnegative_and_sum_to_one():
    rng = np.random.default_rng(0)
    nq, N, K = 40, 30, len(zp.FEATURES)
    X = rng.random((nq, N, K)).astype(np.float32)
    rel = np.zeros((nq, N), bool)
    rel[np.arange(nq), rng.integers(0, N, nq)] = True
    X[rel, 3] += 1.0                                  # feature 3 is informative
    ws, hist = zp.learn_weights(X, rel, rel.sum(1), sweeps=3)
    w = ws[-1]
    assert (w >= 0).all() and abs(w.sum() - 1) < 1e-9 and w[3] == w.max()
    assert hist[-1]["train_MAP"] >= hist[0]["train_MAP"]
