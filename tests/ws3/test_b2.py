"""Authority leave-one-out, neighbour index isolation, net-score helpers, explanations (D20, D21)."""
import numpy as np
import pytest

from irlegal.common.schema import Query
from irlegal.evaluation.metrics import average_precision
from irlegal.preprocess.normalizer import Analyzer
from irlegal.ranking import authority as au
from irlegal.ranking import netscore as ns
from irlegal.ranking.explain import explain_result
from irlegal.ranking.neighbours import NeighbourIndex


def Q(qid, text, split="train", rel=()):
    return Query(qid, qid, text, {}, set(), None, split, set(rel))


DOCS = ["d0", "d1", "d2", "d3"]


def test_authority_leave_one_out():
    g = au.AuthorityGraph(DOCS, pool_cites={"d0": ["d1"], "dev9": ["d2", "d3"]},
                          train_cites={"t1": ["d1", "d2"], "t2": ["d2"]})
    assert g.base.tolist() == [0, 2, 3, 1]
    # a train query loses exactly its own two edges
    assert g.indegree_for("t1").tolist() == [0, 1, 2, 1]
    # a dev query that is NOT in the pool keeps every edge
    assert g.indegree_for("dev1").tolist() == [0, 2, 3, 1]
    # a dev query whose case is also a pool document loses that pool document's outgoing edges
    assert g.indegree_for("dev9").tolist() == [0, 2, 2, 0]
    assert np.allclose(g.authority_for("t1"), np.log1p([0, 1, 2, 1]))


def test_recency_and_court():
    gap = au.year_gap("2010-01-01", ["2000-05-05", None, "2015-01-01", "2010-03-03"])
    assert np.isnan(gap[1]) and gap.tolist()[0] == 10 and gap[2] == -5
    r = au.recency(gap, tau=10.0)
    assert r[0] == pytest.approx(np.exp(-1)) and r[1] == 0 and r[2] == 0 and r[3] == 1
    assert au.court_vector(["SC", "HC", "OTHER", None]) == pytest.approx([1.0, 0.6, 0.3, 0.3])
    assert np.isnan(au.year_gap(None, ["2000-01-01"])[0])


def _train_queries():
    return [Q("t1", "theft of a bicycle from the market", rel=["d0"]),
            Q("t2", "theft of a bicycle near the station", rel=["d1"]),
            Q("t3", "land acquisition compensation award", rel=["d2"])]


def test_neighbour_index_rejects_dev_and_test_queries():
    qs = _train_queries()
    for split in ("val", "test"):
        with pytest.raises(ValueError):
            NeighbourIndex(qs + [Q("x", "theft", split=split)], DOCS, Analyzer())
    ni = NeighbourIndex(qs, DOCS, Analyzer(), max_k=2)
    assert ni.qids == ["t1", "t2", "t3"]


def test_neighbour_leave_one_out_and_votes():
    qs = _train_queries()
    ni = NeighbourIndex(qs, DOCS, Analyzer(), max_k=2)
    # scoring train query t1: it must not be its own neighbour, so d0 (cited only by t1) gets no vote
    idx, sim = ni.top_neighbours([qs[0].text], ["t1"])
    assert 0 not in idx[0][:2] or sim[0][list(idx[0]).index(0)] <= 0
    v = ni.votes(idx, sim, k=2, p=1.0)
    assert v[0, 0] == 0 and v[0, 1] > 0                   # t2 (similar) cites d1
    # the same text scored as a NON-train query finds t1 itself and votes for d0
    idx2, sim2 = ni.top_neighbours([qs[0].text], [None])
    v2 = ni.votes(idx2, sim2, k=2, p=1.0)
    assert v2[0, 0] > v2[0, 1] > 0
    assert ni.explain(idx2[0], sim2[0], 0, 2)[0]["neighbour_id"] == "t1"


def test_ap_from_ranks_matches_metric():
    rng = np.random.default_rng(1)
    nq, n = 30, 40
    S = rng.random((nq, n)).astype(np.float32)
    mask = np.ones((nq, n), bool)
    mask[:, 35:] = False
    S = np.where(mask, S, -np.inf)
    rel = [rng.choice(n, size=rng.integers(1, 4), replace=False) for _ in range(nq)]
    qi = np.concatenate([[i] * len(r) for i, r in enumerate(rel)])
    di = np.concatenate(rel)
    ap = ns.ap_from_ranks(ns.pair_ranks(S, qi, di), qi, nq, np.array([len(r) for r in rel]))
    for i in range(nq):
        ranked = [str(d) for d in np.argsort(-S[i], kind="stable") if mask[i, d]]
        assert ap[i] == pytest.approx(average_precision(ranked, {str(d) for d in rel[i]}))


def test_minmax_union_and_search():
    F = np.array([[1.0, 3.0, 5.0, 9.0], [2.0, 2.0, 2.0, 2.0]], dtype=np.float32)
    mask = np.array([[True, True, True, False], [True, True, True, True]])
    out = ns.minmax_masked(F, mask)
    assert out[0].tolist() == [0.0, 0.5, 1.0, 0.0] and out[1].tolist() == [0, 0, 0, 0]
    tie = np.arange(4)
    m = ns.union_candidates([(F, 1), (-F, 1)], tie, np.array([-1, 2]))
    assert m[0].tolist() == [True, False, False, True] and not m[1][2]
    # search recovers an informative feature
    rng = np.random.default_rng(0)
    nq, n = 60, 30
    good, noise = rng.random((nq, n)), rng.random((nq, n))
    rel_doc = rng.integers(0, n, nq)
    good[np.arange(nq), rel_doc] += 2
    mask = np.ones((nq, n), bool)
    nf = {"text": ns.minmax_masked(good.astype(np.float32), mask), "statute": ns.minmax_masked(noise.astype(np.float32), mask)}
    folds = np.arange(nq) % 5
    res = ns.random_search(nf, mask, np.arange(nq), rel_doc, np.ones(nq), ["text", "statute"], folds, trials=20)
    assert res[0]["w"]["text"] > res[0]["w"]["statute"] and res[0]["MAP"] > 0.9
    assert 0 <= ns.nested_cv_map(res, folds) <= 1


def test_explain_has_no_text_and_sorted_contributions():
    e = explain_result("D1", {"text": 1.0, "authority": 0.5, "statute": 0.0}, {"text": 0.6, "authority": 0.2, "statute": 0.2},
                       neighbours=[{"neighbour_id": "t9", "similarity": 0.4}], shared_statutes=["IPC_302"],
                       zone_cosines={"facts_issues|all": 0.3, "issues|reasoning": 0.1})
    assert list(e["contributions"]) == ["text", "authority", "statute"]
    assert e["net_score"] == pytest.approx(0.7) and e["shared_statutes"] == ["IPC_302"]
    assert all(isinstance(v, (str, int, float, list, dict)) for v in e.values())
