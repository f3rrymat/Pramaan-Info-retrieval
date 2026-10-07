import random

import numpy as np

from irlegal.common.schema import Case
from irlegal.index import compress, skips
from irlegal.index.inverted import InvertedIndex
from irlegal.preprocess.normalizer import Analyzer


def test_vbyte_round_trip_and_known_bytes():
    vals = [0, 1, 127, 128, 129, 16383, 16384, 2**31 - 1, 2**40]
    assert compress.vbyte_decode(compress.vbyte_encode(vals)).tolist() == vals
    assert compress.vbyte_encode([5]) == bytes([5 | 128])          # one byte, high bit marks the end
    assert compress.vbyte_encode([128]) == bytes([0, 1 | 128])      # low 7 bits first
    assert compress.vbyte_decode(b"").size == 0


def test_vbyte_random_round_trip():
    rng = random.Random(1)
    vals = [rng.choice([rng.randrange(0, 200), rng.randrange(0, 10**6), rng.randrange(0, 2**33)]) for _ in range(5000)]
    assert compress.vbyte_decode(compress.vbyte_encode(vals)).tolist() == vals


def test_gaps_and_postings():
    assert compress.gaps([3, 7, 8, 20]).tolist() == [3, 4, 1, 12]
    assert compress.ungap([3, 4, 1, 12]).tolist() == [3, 7, 8, 20]
    docs, tfs = [2, 5, 900], [1, 4, 2]
    d, t = compress.decode_postings(compress.encode_postings(docs, tfs))
    assert d.tolist() == docs and t.tolist() == tfs


def test_skip_intersection_matches_plain():
    rng = random.Random(2)
    for _ in range(300):
        a = sorted(rng.sample(range(400), rng.randint(0, 150)))
        b = sorted(rng.sample(range(400), rng.randint(0, 150)))
        want = sorted(set(a) & set(b))
        assert skips.intersect_plain(a, b)[0] == want == skips.intersect_skip(a, b)[0]


def _cases():
    texts = {
        "A": {"facts": ["dowry harassment dowry death"], "issues": ["whether dowry death proved"], "decision": ["appeal dismissed"]},
        "B": {"facts": ["land acquisition compensation"], "decision": ["appeal allowed"]},
        "C": {"facts": ["murder trial witness"], "issues": ["whether witness reliable"], "reasoning": ["witness credible"]},
    }
    return [Case(doc_id=k, title="", text="", zones=v) for k, v in texts.items()]


def test_index_postings_positions_and_persistence(tmp_path):
    ix = InvertedIndex.build(_cases(), Analyzer())
    assert ix.n_docs() == 3 and ix.doc_ids() == ["A", "B", "C"]
    assert ix.df("dowri", "facts") == 1 and ix.df("dowri", "all") == 1
    assert ix.postings("dowri", "facts") == [("A", 2)]
    assert ix.positions("dowri", "facts", "A") == [0, 2]            # "dowry harassment dowry death"
    assert ix.positions("dowri", "facts", "B") == []
    assert ix.postings("appeal", "decision") == [("A", 1), ("B", 1)]
    assert ix.df("appeal", "all") == 2 and ix.doc_len("A", "facts") == 4
    assert ix.doc_len("A", "fi") == ix.doc_len("A", "facts") + ix.doc_len("A", "issues")
    assert "witit" not in set(ix.terms("facts")) and "murder" in set(ix.terms("facts"))
    sizes = ix.save(tmp_path)
    assert sizes["all"]["gap_vbyte_bytes"] > 0
    iy = InvertedIndex.load(tmp_path)
    for z in ix.zones:
        a, b = ix.zones[z], iy.zones[z]
        assert a.terms == b.terms
        assert np.array_equal(a.docs, b.docs) and np.array_equal(a.tfs, b.tfs) and np.array_equal(a.offsets, b.offsets)
    assert iy.positions("dowri", "facts", "A") == [0, 2]
    assert iy.postings("appeal", "decision") == ix.postings("appeal", "decision")
