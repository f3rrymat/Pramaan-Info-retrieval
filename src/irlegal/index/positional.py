"""Compact positional store (CSR over postings) used by the zone index. Owner: WS1.

Positions are int32 in one flat array; `offsets[p]:offsets[p+1]` are the positions of
posting p (posting p = one (term, doc) pair, in the same order as the zone's doc/tf arrays).
Positions are stored in memory as int32 and persisted as gap + variable-byte per posting.
"""
import numpy as np

from . import compress


class PositionalStore:
    def __init__(self, offsets: np.ndarray, positions: np.ndarray):
        self.offsets = offsets          # int64, len = n_postings + 1
        self.positions = positions      # int32

    def get(self, posting_idx: int) -> np.ndarray:
        return self.positions[self.offsets[posting_idx]:self.offsets[posting_idx + 1]]

    def nbytes(self) -> int:
        return int(self.offsets.nbytes + self.positions.nbytes)

    # ------------------------------------------------------------ persistence
    def encode(self) -> bytes:
        pos = self.positions.astype(np.int64)
        g = np.diff(pos, prepend=0) if pos.size else pos
        starts = self.offsets[:-1][np.diff(self.offsets) > 0]
        g[starts] = pos[starts]                      # first position of each posting is absolute
        return compress.vbyte_encode(g)

    @staticmethod
    def decode(blob: bytes, tfs: np.ndarray) -> "PositionalStore":
        offsets = np.concatenate(([0], np.cumsum(tfs, dtype=np.int64)))
        g = compress.vbyte_decode(blob)
        out = np.cumsum(g)
        starts = offsets[:-1][tfs > 0]
        # undo the running sum across posting boundaries: subtract the sum before each posting
        before = np.concatenate(([0], np.cumsum(g)))[starts]
        reps = np.repeat(before, tfs[tfs > 0])
        return PositionalStore(offsets, (out - reps).astype(np.int32))
