import random

import numpy as np

from irlegal.common.interfaces import CandidateSelector
from irlegal.efficiency.champions import ChampionSelector
from irlegal.efficiency.elimination import EliminationSelector
from irlegal.efficiency.heap import top_k_heap, top_k_sort
from irlegal.efficiency.tiers import TierSelector


def test_heap_equals_full_sort():
    rng = random.Random(5)
    for _ in range(300):
        s = [rng.choice([0.0, 0.5, 1.0, rng.random()]) for _ in range(rng.randint(0, 80))]
        k = rng.randint(1, 20)
        assert top_k_heap(s, k) == top_k_sort(s, k)


class _Ctx:
    def __init__(self, n):
        self.ids = [f"d{i}" for i in range(n)]
        self.tie = np.arange(n)
        self.an = None


def _scorer():
    """3 terms over 6 docs; lnc weights hand-set."""
    import scipy.sparse as sp
    rows = [[(0, .9), (1, .5), (2, .1)], [(1, .8), (3, .7)], [(2, .6), (4, .2), (5, .3)]]
    ind, data, ptr = [], [], [0]
    for r in rows:
        ind += [d for d, _ in r]; data += [w for _, w in r]; ptr.append(len(ind))
    T = sp.csr_matrix((data, ind, ptr), shape=(3, 6))

    class S:
        n = 6
        ctx = _Ctx(6)
        idx_of = staticmethod(lambda d: int(d[1:]))
        def __init__(s):
            s.T = T
            s.zi = type("Z", (), {"df_arr": np.array([3, 2, 3])})()
        def idf(s, r):
            return np.log10(6 / s.zi.df_arr[r])
        def query_terms(s, text):
            return np.array([0, 1, 2]), np.array([1.0, 1.0, 1.0])
    return S()


def test_selectors_follow_protocol_and_behave():
    sc = _scorer()
    q = type("Q", (), {"text": "x"})()
    ch = ChampionSelector(sc, r=1)
    assert isinstance(ch, CandidateSelector) and ch.select(q, 3) == {"d0", "d1", "d2"}       # best doc of each term
    el = EliminationSelector(sc, idf_threshold=0.0, min_match=2)
    assert isinstance(el, CandidateSelector) and el.select(q, 3) == {"d1", "d2"}       # only d1 and d2 hold two query terms
    hi = EliminationSelector(sc, idf_threshold=0.4, min_match=1)                              # drops terms with df=3 (idf .30)
    assert hi.select(q, 3) == {"d1", "d3"}
    tiers = TierSelector(sc, np.array([5, 4, 3, 2, 1, 0], dtype=np.float32), fall_through=False, max_fraction=0.5)
    assert isinstance(tiers, CandidateSelector) and tiers.select(q, 3) == {"d0", "d1", "d2"}
