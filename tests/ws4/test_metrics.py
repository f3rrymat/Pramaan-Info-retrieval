"""Metrics against hand-computed values. ranked = a b c d e ; relevant = {a, c, f} (f never retrieved)."""
import math

import pytest

from irlegal.evaluation import runner
from irlegal.evaluation.metrics import (average_precision, evaluate_ranking, f1_at_k, ndcg_at_k,
                                        precision_at_k, recall_at_k, reciprocal_rank)

R = ["a", "b", "c", "d", "e"]
REL = {"a", "c", "f"}


def test_precision_recall_f1():
    assert precision_at_k(R, REL, 3) == pytest.approx(2 / 3)
    assert recall_at_k(R, REL, 3) == pytest.approx(2 / 3)
    assert f1_at_k(R, REL, 3) == pytest.approx(2 / 3)
    assert precision_at_k(R, REL, 5) == pytest.approx(0.4)
    assert f1_at_k(R, REL, 5) == pytest.approx(2 * 0.4 * (2 / 3) / (0.4 + 2 / 3))
    assert f1_at_k(["x"], REL, 1) == 0.0 and recall_at_k(R, set(), 3) == 0.0


def test_average_precision_and_rr():
    assert average_precision(R, REL) == pytest.approx((1 / 1 + 2 / 3) / 3)   # divides by |REL|, f is missed
    assert reciprocal_rank(R, REL) == 1.0
    assert reciprocal_rank(R, {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(R, {"zzz"}) == 0.0


def test_ndcg():
    dcg = 1 / math.log2(2) + 1 / math.log2(4)
    idcg = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at_k(R, REL, 5) == pytest.approx(dcg / idcg)
    assert ndcg_at_k(["a", "c", "f"], REL, 3) == pytest.approx(1.0)
    assert ndcg_at_k(R, {"a"}, 1) == 1.0


def test_evaluate_ranking_keys():
    m = evaluate_ranking(R, REL, ks=(5,))
    assert set(m) == {"MAP", "MRR", "P@5", "R@5", "F1@5", "nDCG@5"}


def test_test_split_requires_final_flag():
    with pytest.raises(PermissionError):
        runner.run("test")
    with pytest.raises(SystemExit):
        runner.main(["--split", "test"])
