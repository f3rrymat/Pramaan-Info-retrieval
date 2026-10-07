"""Ranking metrics (binary relevance). Owner: WS4.

All take `ranked`, a best-first list of doc ids (the FULL ranking), and `relevant`, a set of ids.
  P@k      = hits in top k / k
  R@k      = hits in top k / |relevant|
  F1@k     = 2PR / (P + R)  (0 if both 0)
  AP       = (1/|relevant|) * sum over ranks i holding a relevant doc of P@i   (MAP = mean over queries)
  RR       = 1 / rank of the first relevant doc (0 if none)                     (MRR = mean)
  nDCG@k   = DCG@k / IDCG@k, DCG = sum rel_i / log2(i + 1), IDCG = DCG of the ideal list
"""
import math
from typing import Dict, Sequence, Set


def precision_at_k(ranked: Sequence[str], relevant: Set[str], k: int) -> float:
    return sum(1 for d in ranked[:k] if d in relevant) / k


def recall_at_k(ranked: Sequence[str], relevant: Set[str], k: int) -> float:
    return sum(1 for d in ranked[:k] if d in relevant) / len(relevant) if relevant else 0.0


def f1_at_k(ranked: Sequence[str], relevant: Set[str], k: int) -> float:
    p, r = precision_at_k(ranked, relevant, k), recall_at_k(ranked, relevant, k)
    return 2 * p * r / (p + r) if p + r else 0.0


def average_precision(ranked: Sequence[str], relevant: Set[str]) -> float:
    if not relevant:
        return 0.0
    hits, total = 0, 0.0
    for i, d in enumerate(ranked, 1):
        if d in relevant:
            hits += 1
            total += hits / i
    return total / len(relevant)


def reciprocal_rank(ranked: Sequence[str], relevant: Set[str]) -> float:
    for i, d in enumerate(ranked, 1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: Set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, d in enumerate(ranked[:k], 1) if d in relevant)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / idcg if idcg else 0.0


def interpolated_pr(ranked: Sequence[str], relevant: Set[str], levels: Sequence[float] = tuple(i / 10 for i in range(11))) -> list:
    """11-point interpolated precision: at recall level r, the maximum precision at any rank with recall >= r."""
    if not relevant:
        return [0.0] * len(levels)
    hits, pts = 0, []
    for i, d in enumerate(ranked, 1):
        if d in relevant:
            hits += 1
            pts.append((hits / len(relevant), hits / i))
    return [max([p for r, p in pts if r >= lv - 1e-12], default=0.0) for lv in levels]


def evaluate_ranking(ranked: Sequence[str], relevant: Set[str], ks=(5, 10, 20)) -> Dict[str, float]:
    out = {"MAP": average_precision(ranked, relevant), "MRR": reciprocal_rank(ranked, relevant)}
    for k in ks:
        out[f"P@{k}"] = precision_at_k(ranked, relevant, k)
        out[f"R@{k}"] = recall_at_k(ranked, relevant, k)
        out[f"F1@{k}"] = f1_at_k(ranked, relevant, k)
        out[f"nDCG@{k}"] = ndcg_at_k(ranked, relevant, k)
    return out
