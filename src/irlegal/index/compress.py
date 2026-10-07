"""Gap encoding + variable-byte codes (IIR 5.3), our own implementation. Owner: WS1.

Variable byte: a non-negative integer is split into 7-bit groups, least significant group
first; the LAST byte of each number has its high bit set (value >= 128), so the stream is
self-delimiting. Numbers are vectorised with numpy for speed; semantics are the textbook ones.
Gap encoding: a sorted posting list d1<d2<... is stored as d1, d2-d1, d3-d2, ...
"""
import numpy as np


def vbyte_encode(values) -> bytes:
    v = np.asarray(values, dtype=np.uint64)
    if v.size == 0:
        return b""
    nbytes = np.ones(v.shape, dtype=np.int64)
    for k in range(1, 10):
        nbytes += (v >> np.uint64(7 * k)) > 0
    starts = np.cumsum(nbytes) - nbytes
    out = np.zeros(int(nbytes.sum()), dtype=np.uint8)
    for k in range(int(nbytes.max())):
        sel = nbytes > k
        out[starts[sel] + k] = ((v[sel] >> np.uint64(7 * k)) & np.uint64(127)).astype(np.uint8)
    out[starts + nbytes - 1] |= 128
    return out.tobytes()


def vbyte_decode(data: bytes) -> np.ndarray:
    b = np.frombuffer(data, dtype=np.uint8)
    if b.size == 0:
        return np.zeros(0, dtype=np.int64)
    last = np.flatnonzero(b >= 128)                    # index of the final byte of each number
    first = np.concatenate(([0], last[:-1] + 1))
    num_id = np.repeat(np.arange(last.size), last - first + 1)
    shift = (np.arange(b.size) - first[num_id]).astype(np.uint64) * np.uint64(7)
    contrib = (b & 127).astype(np.uint64) << shift
    out = np.zeros(last.size, dtype=np.uint64)
    np.add.at(out, num_id, contrib)
    return out.astype(np.int64)


def gaps(sorted_ids) -> np.ndarray:
    a = np.asarray(sorted_ids, dtype=np.int64)
    return np.diff(a, prepend=0) if a.size else a


def ungap(g) -> np.ndarray:
    return np.cumsum(np.asarray(g, dtype=np.int64))


def encode_postings(doc_ids, tfs) -> bytes:
    """One posting list -> gap-encoded doc ids followed by tfs, both variable-byte."""
    return vbyte_encode(gaps(doc_ids)) + vbyte_encode(tfs)


def decode_postings(data: bytes):
    n = vbyte_decode(data)
    half = len(n) // 2
    return ungap(n[:half]), n[half:]
