"""Per-zone inverted index with tf, df and doc lengths; persisted to disk. Implements Index.

Owner: WS1. Zones are schema.ZONES plus two derived ones: "fi" (facts + issues) and "all"
(whole text). Each zone is stored in CSR form: sorted terms, `offsets` into flat doc/tf arrays.
Positions are kept only for facts and issues (config ws1.positional_zones).
"""
import json
import time
from array import array
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from irlegal.common.schema import ZONES, Case
from . import compress
from .positional import PositionalStore

DERIVED_ZONES = ("fi", "all")
INDEX_ZONES = tuple(ZONES) + DERIVED_ZONES


class ZoneIndex:
    def __init__(self, terms: List[str], offsets: np.ndarray, docs: np.ndarray, tfs: np.ndarray,
                 positional: Optional[PositionalStore] = None):
        self.terms = terms
        self.row = {t: i for i, t in enumerate(terms)}
        self.offsets = offsets
        self.docs = docs
        self.tfs = tfs
        self.positional = positional
        self.df_arr = np.diff(offsets).astype(np.int32)

    def span(self, term: str) -> Optional[Tuple[int, int]]:
        r = self.row.get(term)
        return None if r is None else (int(self.offsets[r]), int(self.offsets[r + 1]))

    def nbytes(self) -> int:
        n = self.offsets.nbytes + self.docs.nbytes + self.tfs.nbytes
        return int(n + (self.positional.nbytes() if self.positional else 0))


class _ZoneBuilder:
    def __init__(self, keep_positions: bool):
        self.keep_positions = keep_positions
        self.vocab: Dict[str, int] = {}
        self.rows, self.docs, self.tfs = array("i"), array("i"), array("i")
        self.pos = array("i")

    def add_doc(self, doc_idx: int, tokens: Sequence[str]):
        by_term: Dict[str, List[int]] = {}
        if self.keep_positions:
            for i, t in enumerate(tokens):
                by_term.setdefault(t, []).append(i)
            items = ((t, len(p), p) for t, p in by_term.items())
        else:
            c: Dict[str, int] = {}
            for t in tokens:
                c[t] = c.get(t, 0) + 1
            items = ((t, n, None) for t, n in c.items())
        for t, n, p in items:
            r = self.vocab.setdefault(t, len(self.vocab))
            self.rows.append(r); self.docs.append(doc_idx); self.tfs.append(n)
            if p is not None:
                self.pos.extend(p)

    def finish(self) -> ZoneIndex:
        terms = sorted(self.vocab)
        remap = np.zeros(len(self.vocab), dtype=np.int64)
        for new, t in enumerate(terms):
            remap[self.vocab[t]] = new
        rows = remap[np.frombuffer(self.rows, dtype=np.int32)] if len(self.rows) else np.zeros(0, np.int64)
        docs = np.frombuffer(self.docs, dtype=np.int32).copy()
        tfs = np.frombuffer(self.tfs, dtype=np.int32).copy()
        order = np.argsort(rows, kind="stable")             # stable: docs stay ascending inside a term
        offsets = np.concatenate(([0], np.cumsum(np.bincount(rows, minlength=len(terms))))).astype(np.int64)
        positional = None
        if self.keep_positions:
            pos = np.frombuffer(self.pos, dtype=np.int32)
            src_start = np.cumsum(tfs, dtype=np.int64) - tfs
            lens = tfs[order].astype(np.int64)
            st = src_start[order]
            new_start = np.cumsum(lens) - lens
            idx = np.repeat(st - new_start, lens) + np.arange(int(lens.sum()), dtype=np.int64)
            positional = PositionalStore(np.concatenate(([0], np.cumsum(lens))), pos[idx].copy())
        return ZoneIndex(terms, offsets, docs[order], tfs[order], positional)


class InvertedIndex:
    """Implements irlegal.common.interfaces.Index over the precedent pool."""

    def __init__(self, doc_ids: List[str], meta: List[Dict], zones: Dict[str, ZoneIndex],
                 doc_len: Dict[str, np.ndarray]):
        self._doc_ids = doc_ids
        self._idx = {d: i for i, d in enumerate(doc_ids)}
        self._meta = meta
        self.zones = zones
        self._doc_len = doc_len

    # ------------------------------------------------------------ build
    @classmethod
    def build(cls, cases: List[Case], analyzer, positional_zones=("facts", "issues"), cache=None) -> "InvertedIndex":
        builders = {z: _ZoneBuilder(z in positional_zones) for z in INDEX_ZONES}
        n = len(cases)
        doc_len = {z: np.zeros(n, dtype=np.int32) for z in INDEX_ZONES}
        for di, case in enumerate(cases):
            toks: Dict[str, List[str]] = {z: [] for z in INDEX_ZONES}
            for z, paras in case.zones.items():
                for p in paras:
                    t = analyzer.analyze(p)
                    toks[z].extend(t)
                    toks["all"].extend(t)
                    if z in ("facts", "issues"):
                        toks["fi"].extend(t)
            for z in INDEX_ZONES:
                doc_len[z][di] = len(toks[z])
                if toks[z]:
                    builders[z].add_doc(di, toks[z])
        zones = {z: b.finish() for z, b in builders.items()}
        meta = [{"court": c.court, "date": c.date, "statutes": sorted(c.statutes)} for c in cases]
        return cls([c.doc_id for c in cases], meta, zones, doc_len)

    # ------------------------------------------------------------ Index protocol
    def df(self, term: str, zone: str) -> int:
        sp = self.zones[zone].span(term)
        return 0 if sp is None else sp[1] - sp[0]

    def postings(self, term: str, zone: str) -> List[Tuple[str, int]]:
        docs, tfs = self.posting_arrays(term, zone)
        return [(self._doc_ids[d], int(t)) for d, t in zip(docs, tfs)]

    def positions(self, term: str, zone: str, doc_id: str) -> List[int]:
        z = self.zones[zone]
        sp = z.span(term)
        if sp is None or z.positional is None or doc_id not in self._idx:
            return []
        k = int(np.searchsorted(z.docs[sp[0]:sp[1]], self._idx[doc_id]))
        if k >= sp[1] - sp[0] or z.docs[sp[0] + k] != self._idx[doc_id]:
            return []
        return z.positional.get(sp[0] + k).tolist()

    def doc_len(self, doc_id: str, zone: str) -> int:
        return int(self._doc_len[zone][self._idx[doc_id]])

    def meta(self, doc_id: str) -> Dict:
        return self._meta[self._idx[doc_id]]

    def n_docs(self) -> int:
        return len(self._doc_ids)

    def terms(self, zone: str) -> Iterable[str]:
        return iter(self.zones[zone].terms)

    def doc_ids(self) -> List[str]:
        return list(self._doc_ids)

    # ------------------------------------------------------------ numpy accessors (rankers)
    def posting_arrays(self, term: str, zone: str) -> Tuple[np.ndarray, np.ndarray]:
        z = self.zones[zone]
        sp = z.span(term)
        if sp is None:
            return np.zeros(0, np.int32), np.zeros(0, np.int32)
        return z.docs[sp[0]:sp[1]], z.tfs[sp[0]:sp[1]]

    def doc_len_array(self, zone: str) -> np.ndarray:
        return self._doc_len[zone]

    def index_of(self, doc_id: str) -> Optional[int]:
        return self._idx.get(doc_id)

    def memory_bytes(self) -> Dict[str, int]:
        out = {z: self.zones[z].nbytes() for z in INDEX_ZONES}
        out["doc_len"] = int(sum(a.nbytes for a in self._doc_len.values()))
        return out

    # ------------------------------------------------------------ persistence (gap + vbyte)
    def save(self, directory) -> Dict:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"doc_ids": self._doc_ids, "meta": self._meta, "zones": list(self.zones)}))
        np.savez_compressed(d / "doc_len.npz", **self._doc_len)
        sizes = {}
        for name, z in self.zones.items():
            g = np.diff(z.docs.astype(np.int64), prepend=0)
            starts = z.offsets[:-1][z.df_arr > 0]
            g[starts] = z.docs[starts]                     # gaps restart at every term
            blobs = {"df": compress.vbyte_encode(z.df_arr), "docs": compress.vbyte_encode(g),
                     "tfs": compress.vbyte_encode(z.tfs)}
            raw = z.docs.nbytes + z.tfs.nbytes
            comp = sum(len(b) for b in blobs.values())
            if z.positional is not None:
                blobs["pos"] = z.positional.encode()
                raw += z.positional.positions.nbytes
                comp += len(blobs["pos"])
            (d / f"{name}.terms").write_text("\n".join(z.terms))
            for k, b in blobs.items():
                (d / f"{name}.{k}.vb").write_bytes(b)
            sizes[name] = {"raw_int32_bytes": int(raw), "gap_vbyte_bytes": int(comp),
                           "n_terms": len(z.terms), "n_postings": int(len(z.docs)),
                           "n_positions": int(len(z.positional.positions)) if z.positional else 0}
        (d / "sizes.json").write_text(json.dumps(sizes, indent=1))
        return sizes

    @classmethod
    def load(cls, directory) -> "InvertedIndex":
        d = Path(directory)
        m = json.loads((d / "meta.json").read_text())
        dl = np.load(d / "doc_len.npz")
        zones = {}
        for name in m["zones"]:
            terms = (d / f"{name}.terms").read_text().split("\n") if (d / f"{name}.terms").stat().st_size else []
            df = compress.vbyte_decode((d / f"{name}.df.vb").read_bytes()).astype(np.int32)
            offsets = np.concatenate(([0], np.cumsum(df, dtype=np.int64)))
            g = compress.vbyte_decode((d / f"{name}.docs.vb").read_bytes())
            tfs = compress.vbyte_decode((d / f"{name}.tfs.vb").read_bytes()).astype(np.int32)
            run = np.cumsum(g)
            starts = offsets[:-1][df > 0]
            before = np.concatenate(([0], run))[starts]
            docs = (run - np.repeat(before, df[df > 0])).astype(np.int32)
            pos = None
            if (d / f"{name}.pos.vb").exists():
                pos = PositionalStore.decode((d / f"{name}.pos.vb").read_bytes(), tfs.astype(np.int64))
            zones[name] = ZoneIndex(terms, offsets, docs, tfs, pos)
        return cls(m["doc_ids"], m["meta"], zones, {k: dl[k] for k in dl.files})
