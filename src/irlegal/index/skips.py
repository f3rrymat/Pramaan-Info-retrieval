"""Skip pointers for AND on sorted postings (IIR 2.3). Owner: WS1.

Spacing is sqrt(len). `intersect_skip` and `intersect_plain` both count comparisons so the
benchmark is machine-independent as well as timed.
"""
import math
import random
import time
from typing import List, Sequence, Tuple


def intersect_plain(a: Sequence[int], b: Sequence[int]) -> Tuple[List[int], int]:
    i = j = cmp = 0
    out: List[int] = []
    while i < len(a) and j < len(b):
        cmp += 1
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return out, cmp


def intersect_skip(a: Sequence[int], b: Sequence[int]) -> Tuple[List[int], int]:
    """Same result as intersect_plain; follows a skip pointer when its target is still <= the other id."""
    sa = max(1, int(math.sqrt(len(a)))); sb = max(1, int(math.sqrt(len(b))))
    i = j = cmp = 0
    out: List[int] = []
    while i < len(a) and j < len(b):
        cmp += 1
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif a[i] < b[j]:
            while i % sa == 0 and i + sa < len(a) and a[i + sa] <= b[j]:
                i += sa; cmp += 1
            if a[i] < b[j]:
                i += 1
        else:
            while j % sb == 0 and j + sb < len(b) and b[j + sb] <= a[i]:
                j += sb; cmp += 1
            if b[j] < a[i]:
                j += 1
    return out, cmp


def benchmark(lists: List[Sequence[int]], n_pairs: int = 500, seed: int = 13) -> dict:
    rng = random.Random(seed)
    pairs = [rng.sample(range(len(lists)), 2) for _ in range(n_pairs)]
    res = {}
    for name, fn in (("plain", intersect_plain), ("skip", intersect_skip)):
        t = time.perf_counter(); cmps = 0; size = 0
        for x, y in pairs:
            out, c = fn(lists[x], lists[y]); cmps += c; size += len(out)
        res[name] = {"seconds": round(time.perf_counter() - t, 4), "comparisons": cmps, "result_size": size}
    res["pairs"] = n_pairs
    return res
