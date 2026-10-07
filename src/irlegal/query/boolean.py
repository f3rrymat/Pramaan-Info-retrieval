"""Boolean / phrase / proximity evaluator over our Index Protocol. Owner: WS2.

Logic credit (AI_USE.md): operator set, df-ordered AND and the positional phrase / proximity idea follow
reference/stare-ir `boolean.py`; this module is rewritten against `irlegal.common.interfaces.Index`.

* Terms and wildcards use the whole-text zone `all` unless a zone is given (`facts:bail`).
* Positions exist ONLY for the zones `facts` and `issues` (DECISIONS D29), so phrase and proximity queries
  search those two zones (a document matches if either zone does). A phrase restricted to another zone falls
  back to an AND of its words and says so in the trace.
* Stop words are removed before positions are assigned, so "burden of proof" is the adjacent stems burden proof.
* AND is intersected smallest posting list first (`df_order`) or as written (`input_order`); both use the skip-pointer
  merge and count comparisons, which `benchmark_and` compares.
"""
import datetime as dt
import math
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from irlegal.index import skips
from .parser import (And, Filter, Node, Not, Or, Phrase, Prox, QuerySyntaxError, Term, parse, pretty, to_tree,
                     words_of)
from .tolerant import KGramIndex

POSITIONAL_ZONES = ("facts", "issues")


@dataclass
class AndStats:
    comparisons: int = 0
    intersections: int = 0


@dataclass
class BoolResult:
    docs: np.ndarray
    trace: List[str] = field(default_factory=list)
    stats: AndStats = field(default_factory=AndStats)
    tree: dict = field(default_factory=dict)
    pretty: str = ""


def _intersect(lists: Sequence[np.ndarray], strategy: str, stats: AndStats) -> np.ndarray:
    if not lists:
        return np.zeros(0, np.int32)
    ls = list(lists)
    if strategy == "df_order":
        ls.sort(key=len)
    acc = ls[0].tolist()
    for nxt in ls[1:]:
        if not acc:
            break
        acc, c = skips.intersect_skip(acc, nxt.tolist())
        stats.comparisons += c
        stats.intersections += 1
    return np.asarray(acc, dtype=np.int32)


class BooleanSearcher:
    def __init__(self, index, analyzer, strategy: str = "df_order"):
        assert strategy in ("df_order", "input_order")
        self.index, self.an, self.strategy = index, analyzer, strategy
        self.ids = index.doc_ids()
        self.idx = {d: i for i, d in enumerate(self.ids)}
        self.n = len(self.ids)
        self._kg: Dict[str, KGramIndex] = {}
        meta = [index.meta(d) for d in self.ids]
        self.courts = np.array([(m.get("court") or "") for m in meta])
        self.dates = [m.get("date") or "" for m in meta]
        self._doc_cache: Dict = {}

    # ------------------------------------------------------------ public
    def search(self, query: str) -> BoolResult:
        node = parse(query)
        res = BoolResult(np.zeros(0, np.int32), tree=to_tree(node), pretty=pretty(node))
        out = self._eval(node, res)
        res.docs = np.arange(self.n, dtype=np.int32) if out is None else out
        if out is None:
            res.trace.append("the query is only stop words: no constraint, returns every document")
        return res

    def rank(self, result: BoolResult, query: str, k: int = 20):
        """Order Boolean matches by tf-idf over the query's positive words (whole-text zone). Returns [(doc_id, score)]."""
        words = [w for w in words_of(parse(query))]
        scores = np.zeros(self.n)
        for w in words:
            for stem in self._stems(w, "all"):
                docs, tfs = self._arrays(stem, "all")
                if len(docs):
                    scores[docs] += (1 + np.log10(tfs)) * math.log10(self.n / len(docs))
        docs = result.docs
        order = docs[np.lexsort((docs, -scores[docs]))][:k]
        return [(self.ids[d], round(float(scores[d]), 4)) for d in order]

    # ------------------------------------------------------------ helpers
    def _kgram(self, zone: str) -> KGramIndex:
        if zone not in self._kg:
            self._kg[zone] = KGramIndex(self.index.terms(zone))
        return self._kg[zone]

    def _stems(self, word: str, zone: str) -> List[str]:
        """Dictionary terms for a user word: wildcard expansion, or the analysed (stemmed) word."""
        w = word.lower()
        if "*" in w:
            return self._kgram(zone).wildcard(w)
        toks = self.an.analyze(w)
        return toks[:1]

    def _arrays(self, stem: str, zone: str):
        key = (stem, zone)
        if key not in self._doc_cache:
            if hasattr(self.index, "posting_arrays"):
                d, t = self.index.posting_arrays(stem, zone)
                self._doc_cache[key] = (np.asarray(d, dtype=np.int32), np.asarray(t, dtype=np.int32))
            else:
                p = self.index.postings(stem, zone)
                self._doc_cache[key] = (np.array([self.idx[d] for d, _ in p], dtype=np.int32), np.array([t for _, t in p], dtype=np.int32))
        return self._doc_cache[key]

    # ------------------------------------------------------------ evaluation
    def _eval(self, node: Node, res: BoolResult) -> Optional[np.ndarray]:
        if isinstance(node, Term):
            return self._term(node, res)
        if isinstance(node, Phrase):
            return self._phrase(node, res)
        if isinstance(node, Filter):
            return self._filter(node, res)
        if isinstance(node, Prox):
            return self._prox_docs(node, res)
        if isinstance(node, Or):
            parts = [p for p in (self._eval(c, res) for c in node.children) if p is not None]
            if not parts:
                return None
            out = np.unique(np.concatenate(parts)).astype(np.int32)
            res.trace.append(f"OR of {len(parts)} operands -> {len(out)} docs")
            return out
        if isinstance(node, Not):
            inner = self._eval(node.child, res)
            if inner is None:
                return None
            out = np.setdiff1d(np.arange(self.n, dtype=np.int32), inner)
            res.trace.append(f"NOT -> {len(out)} docs")
            return out
        if isinstance(node, And):
            pos, neg = [], []
            for c in node.children:
                if isinstance(c, Not):
                    inner = self._eval(c.child, res)
                    if inner is not None:
                        neg.append(inner)
                else:
                    r = self._eval(c, res)
                    if r is not None:
                        pos.append(r)
            if not pos and not neg:
                return None
            if pos:
                out = _intersect(pos, self.strategy, res.stats)
                res.trace.append(f"AND of operands with sizes {[len(p) for p in pos]} [{self.strategy}] -> {len(out)} docs")
            else:
                out = np.arange(self.n, dtype=np.int32)
            for g in neg:
                out = np.setdiff1d(out, g)
            if neg:
                res.trace.append(f"AND NOT {len(neg)} operand(s) -> {len(out)} docs")
            return out.astype(np.int32)
        raise QuerySyntaxError(f"cannot evaluate {node!r}")

    def _term(self, node: Term, res: BoolResult) -> Optional[np.ndarray]:
        zone = node.zone or "all"
        stems = self._stems(node.word, zone)
        if not stems:
            if "*" not in node.word and not self.an.analyze(node.word):
                res.trace.append(f"{node.word!r} is a stop word: ignored")
                return None
            res.trace.append(f"{node.word!r} matches no dictionary term in zone {zone}: 0 docs")
            return np.zeros(0, np.int32)
        parts = [self._arrays(s, zone)[0] for s in stems]
        out = parts[0] if len(parts) == 1 else np.unique(np.concatenate(parts))
        res.trace.append(f"{node.word!r} [{zone}] -> df={len(out)}" + (f" (wildcard, {len(stems)} terms)" if "*" in node.word else ""))
        return out.astype(np.int32)

    def _phrase_stems(self, text: str) -> List[str]:
        return self.an.analyze(text)

    def _phrase_in_zone(self, stems: List[str], zone: str, res: BoolResult) -> Dict[int, np.ndarray]:
        lists = [self._arrays(s, zone)[0] for s in stems]
        cands = _intersect(lists, self.strategy, res.stats)
        out: Dict[int, np.ndarray] = {}
        for d in cands.tolist():
            p0 = np.asarray(self.index.positions(stems[0], zone, self.ids[d]))
            for off, s in enumerate(stems[1:], 1):
                if not len(p0):
                    break
                p0 = p0[np.isin(p0 + off, np.asarray(self.index.positions(s, zone, self.ids[d])))]
            if len(p0):
                out[d] = p0
        return out

    def _phrase(self, node: Phrase, res: BoolResult) -> Optional[np.ndarray]:
        stems = self._phrase_stems(node.text)
        if not stems:
            res.trace.append(f"phrase {node.text!r} is only stop words: ignored")
            return None
        if node.zone and node.zone not in POSITIONAL_ZONES:
            res.trace.append(f"zone {node.zone} keeps no positions: phrase {node.text!r} treated as an AND of its words")
            return _intersect([self._arrays(s, node.zone)[0] for s in stems], self.strategy, res.stats)
        zones = [node.zone] if node.zone else list(POSITIONAL_ZONES)
        docs = set()
        for z in zones:
            docs |= set(self._phrase_in_zone(stems, z, res))
        out = np.array(sorted(docs), dtype=np.int32)
        res.trace.append(f"phrase {node.text!r} in {'/'.join(zones)} -> {len(out)} docs (positions exist only for facts and issues)")
        return out

    def _positions(self, node: Node, zone: str, res: BoolResult) -> Dict[int, np.ndarray]:
        if isinstance(node, Phrase):
            stems = self._phrase_stems(node.text)
            return self._phrase_in_zone(stems, zone, res) if stems else {}
        if isinstance(node, Term):
            acc: Dict[int, List[np.ndarray]] = {}
            for s in self._stems(node.word, zone):
                for d in self._arrays(s, zone)[0].tolist():
                    acc.setdefault(d, []).append(np.asarray(self.index.positions(s, zone, self.ids[d])))
            return {d: np.sort(np.concatenate(v)) for d, v in acc.items()}
        if isinstance(node, Prox):
            return self._prox_zone(node, zone, res)
        raise QuerySyntaxError("proximity operands must be words or phrases")

    def _prox_zone(self, node: Prox, zone: str, res: BoolResult) -> Dict[int, np.ndarray]:
        A, B = self._positions(node.left, zone, res), self._positions(node.right, zone, res)
        out: Dict[int, np.ndarray] = {}
        for d in sorted(set(A) & set(B)):
            pa, pb = A[d], B[d]
            if node.ordered:          # some a with 1 <= b - a <= k
                lo = np.searchsorted(pa, pb - node.k, side="left")
                hi = np.searchsorted(pa, pb - 1, side="right")
                ok = hi > lo
            else:                     # some a != b with |a - b| <= k
                lo = np.searchsorted(pa, pb - node.k, side="left")
                hi = np.searchsorted(pa, pb + node.k, side="right")
                same = np.array([(pa == b).any() for b in pb])
                ok = (hi - lo) > same.astype(int)
            if ok.any():
                out[d] = pb[ok]
        return out

    def _prox_docs(self, node: Prox, res: BoolResult) -> np.ndarray:
        zones = list(POSITIONAL_ZONES)
        docs = set()
        for z in zones:
            docs |= set(self._prox_zone(node, z, res))
        out = np.array(sorted(docs), dtype=np.int32)
        res.trace.append(f"proximity {'pre/' if node.ordered else '/'}{node.k} in facts/issues -> {len(out)} docs")
        return out

    def _filter(self, node: Filter, res: BoolResult) -> np.ndarray:
        v = node.value
        if node.name == "court":
            m = self.courts == v.upper()
        elif node.name == "year":
            years = np.array([int(d[:4]) if d[:4].isdigit() else -1 for d in self.dates])
            if ".." in v:
                lo, hi = (int(x) for x in v.split(".."))
            elif v.startswith((">=", "<=")):
                n = int(v[2:]); lo, hi = (n, 9999) if v[0] == ">" else (0, n)
            elif v[0] in "<>":
                n = int(v[1:]); lo, hi = (n + 1, 9999) if v[0] == ">" else (0, n - 1)
            else:
                lo = hi = int(v)
            m = (years >= lo) & (years <= hi) & (years >= 0)
        else:                                   # before / after
            try:
                dt.date.fromisoformat(v)
            except ValueError as e:
                raise QuerySyntaxError(f"{node.name}: needs a date yyyy-mm-dd") from e
            known = np.array([len(d) >= 10 for d in self.dates])
            cmp_ = np.array([d[:10] < v if node.name == "before" else d[:10] > v for d in self.dates])
            m = known & cmp_
        res.trace.append(f"{node.name}:{v} -> {int(m.sum())} docs (documents without that metadata never match)")
        return np.flatnonzero(m).astype(np.int32)


def benchmark_and(searcher_factory, queries: Sequence[str], repeats: int = 3) -> dict:
    """Same AND queries with `input_order` vs `df_order`: comparisons (machine independent) and seconds."""
    out = {}
    for strat in ("input_order", "df_order"):
        s = searcher_factory(strat)
        t, comps, ixs, hits = 1e9, 0, 0, 0
        for _ in range(repeats):
            t0 = time.perf_counter(); comps = ixs = hits = 0
            for q in queries:
                r = s.search(q)
                comps += r.stats.comparisons; ixs += r.stats.intersections; hits += len(r.docs)
            t = min(t, time.perf_counter() - t0)
        out[strat] = {"comparisons": comps, "intersections": ixs, "total_hits": hits, "seconds": round(t, 4)}
    out["queries"] = len(queries)
    return out
