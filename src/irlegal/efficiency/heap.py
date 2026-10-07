"""Heap top-K (IIR 7.1.2), our own binary min-heap. Owner: WS4.

Keeping the K best of n scores with a size-K min-heap costs O(n log K) instead of the O(n log n) of a
full sort. Ties break toward the smaller doc id so both methods return the same list.
"""
from typing import List, Sequence, Tuple


def _less(a: Tuple[float, int], b: Tuple[float, int]) -> bool:
    """True if a ranks WORSE than b (lower score, or equal score and larger doc id)."""
    return a[0] < b[0] or (a[0] == b[0] and a[1] > b[1])


def _sift_down(h: List[Tuple[float, int]], i: int) -> None:
    n = len(h)
    while True:
        l, r, m = 2 * i + 1, 2 * i + 2, i
        if l < n and _less(h[l], h[m]):
            m = l
        if r < n and _less(h[r], h[m]):
            m = r
        if m == i:
            return
        h[i], h[m] = h[m], h[i]
        i = m


def _sift_up(h: List[Tuple[float, int]], i: int) -> None:
    while i > 0:
        p = (i - 1) // 2
        if _less(h[i], h[p]):
            h[i], h[p] = h[p], h[i]
            i = p
        else:
            return


def top_k_heap(scores: Sequence[float], k: int) -> List[Tuple[int, float]]:
    """(doc, score) of the k best, best first."""
    h: List[Tuple[float, int]] = []
    for d, s in enumerate(scores):
        item = (s, d)
        if len(h) < k:
            h.append(item)
            _sift_up(h, len(h) - 1)
        elif _less(h[0], item):
            h[0] = item
            _sift_down(h, 0)
    out = sorted(h, key=lambda x: (-x[0], x[1]))
    return [(d, s) for s, d in out]


def top_k_sort(scores: Sequence[float], k: int) -> List[Tuple[int, float]]:
    """Reference: sort everything."""
    order = sorted(range(len(scores)), key=lambda d: (-scores[d], d))
    return [(d, scores[d]) for d in order[:k]]
