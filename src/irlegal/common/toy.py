"""Toy stubs that satisfy the frozen Protocols, backed by tests/fixtures/toy_corpus.

Purpose: let every workstream build and test against the contracts before the real
modules land. NOT real IR: whitespace tokenisation, no stemming, raw term overlap.
Never report numbers from these classes. Replace usages with the real modules
(leave `TODO(wsN)` markers until then).

    from irlegal.common.toy import ToyCorpus, ToyIndex, ToyRanker
    corpus = ToyCorpus()
    index = ToyIndex(corpus.cases())
    ranker = ToyRanker(corpus, index)
    results = ranker.rank(corpus.queries("test")[0], k=5)
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .config import load_config, repo_path
from .schema import QUERY_ZONES, ZONES, Case, Query, Result

_TOKEN = re.compile(r"[a-z0-9]+")


def toy_tokens(text: str) -> List[str]:
    """Deliberately naive tokeniser for the toy stubs only."""
    return _TOKEN.findall(text.lower())


def _read_jsonl(path: Path) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _case_from_row(row: dict, pool: Optional[str]) -> Case:
    zones = {z: list(row["zones"].get(z, [])) for z in ZONES if row["zones"].get(z)}
    text = " ".join(s for z in ZONES for s in zones.get(z, []))
    return Case(
        doc_id=row.get("doc_id") or row["case_id"],
        title=row["title"],
        text=text,
        court=row.get("court"),
        date=row.get("date"),
        zones=zones,
        statutes=set(row.get("statutes", [])),
        cites_out=list(row.get("cites_out") or row.get("relevant") or []),
        pool=pool,
    )


class ToyCorpus:
    """Implements CorpusSource over the toy fixture files."""

    def __init__(self, folder: Optional[Path] = None):
        folder = Path(folder) if folder else repo_path(load_config()["paths"]["toy_corpus"])
        self._cases = [_case_from_row(r, r.get("pool")) for r in _read_jsonl(folder / "cases.jsonl")]
        qrows = _read_jsonl(folder / "queries.jsonl")
        # Query documents are full Case objects too (pool=None: they are not candidates).
        self._query_cases = [_case_from_row(r, None) for r in qrows]
        self._queries = [self._query_from_row(r) for r in qrows]
        self._by_id = {c.doc_id: c for c in self._cases + self._query_cases}

    @staticmethod
    def _query_from_row(row: dict) -> Query:
        # TOY: takes facts+issues verbatim. The real builder (WS1, query_builder.py)
        # must also scrub <CITATION> and reporter citations; the fixture contains some
        # on purpose so that tests can check the scrubber.
        zones = {z: " ".join(row["zones"].get(z, [])) for z in QUERY_ZONES}
        return Query(
            qid=row["qid"],
            case_id=row["case_id"],
            text=" ".join(zones[z] for z in QUERY_ZONES),
            zones=zones,
            statutes=set(row.get("statutes", [])),
            date=row.get("date"),
            split=row["split"],
            relevant=set(row["relevant"]),
        )

    def cases(self, pool: Optional[str] = None) -> List[Case]:
        return [c for c in self._cases if pool is None or c.pool == pool]

    def queries(self, split: str) -> List[Query]:
        return [q for q in self._queries if q.split == split]

    def get_case(self, doc_id: str) -> Optional[Case]:
        return self._by_id.get(doc_id)


class ToyIndex:
    """Implements Index with plain dicts. Real one: WS1 index/inverted.py."""

    def __init__(self, cases: Iterable[Case]):
        self._post: Dict[str, Dict[str, Dict[str, List[int]]]] = defaultdict(lambda: defaultdict(dict))
        self._len: Dict[Tuple[str, str], int] = {}
        self._meta: Dict[str, Dict] = {}
        for c in cases:
            self._meta[c.doc_id] = {"title": c.title, "court": c.court, "date": c.date,
                                    "statutes": sorted(c.statutes), "pool": c.pool}
            for zone, sents in c.zones.items():
                toks = toy_tokens(" ".join(sents))
                self._len[(c.doc_id, zone)] = len(toks)
                for pos, t in enumerate(toks):
                    self._post[zone][t].setdefault(c.doc_id, []).append(pos)

    def df(self, term: str, zone: str) -> int:
        return len(self._post[zone].get(term, {}))

    def postings(self, term: str, zone: str) -> List[Tuple[str, int]]:
        return sorted((d, len(p)) for d, p in self._post[zone].get(term, {}).items())

    def positions(self, term: str, zone: str, doc_id: str) -> List[int]:
        return list(self._post[zone].get(term, {}).get(doc_id, []))

    def doc_len(self, doc_id: str, zone: str) -> int:
        return self._len.get((doc_id, zone), 0)

    def meta(self, doc_id: str) -> Dict:
        return dict(self._meta.get(doc_id, {}))

    def n_docs(self) -> int:
        return len(self._meta)

    def terms(self, zone: str) -> Iterable[str]:
        return sorted(self._post[zone].keys())

    def doc_ids(self) -> List[str]:
        return sorted(self._meta)


_SPLIT_TO_POOL = {"train": "train", "val": "val", "test": "test"}


class ToyRanker:
    """Implements Ranker. TOY scoring: count of query-token hits + statute Jaccard.

    Exists only so the API and UI have something real to call. Real rankers: WS3.
    """

    name = "toy"

    def __init__(self, corpus: ToyCorpus, index: ToyIndex):
        self.corpus = corpus
        self.index = index

    def rank(self, query: Query, k: int, **opts) -> List[Result]:
        candidates: Optional[Set[str]] = opts.get("candidates")
        exclude: Set[str] = set(opts.get("exclude", ())) | {query.case_id}
        pool = _SPLIT_TO_POOL.get(query.split)  # per-split candidate pool (official protocol)
        pool_ids = {c.doc_id for c in self.corpus.cases(pool)} if pool else set(self.index.doc_ids())
        allowed = (pool_ids if candidates is None else pool_ids & set(candidates)) - exclude

        hits: Dict[str, float] = defaultdict(float)
        for term in set(toy_tokens(query.text)):
            for zone in ZONES:
                for doc_id, tf in self.index.postings(term, zone):
                    if doc_id in allowed:
                        hits[doc_id] += tf
        top = max(hits.values(), default=0.0) or 1.0

        results = []
        for doc_id in allowed:
            d_stat = set(self.index.meta(doc_id).get("statutes", []))
            union = query.statutes | d_stat
            jac = len(query.statutes & d_stat) / len(union) if union else 0.0
            text = hits.get(doc_id, 0.0) / top
            comps = {"text": text, "statute": jac, "authority": 0.0, "court": 0.0, "recency": 0.0}
            score = 0.7 * text + 0.3 * jac
            results.append(Result(doc_id, score, comps,
                                  {"toy": True, "shared_statutes": sorted(query.statutes & d_stat)}))
        results.sort(key=lambda r: (-r.score, r.doc_id))
        return results[:k]


_BUNDLE = None


def toy_bundle() -> Tuple[ToyCorpus, ToyIndex, ToyRanker]:
    """Shared, lazily built toy objects (used by routers until real modules land)."""
    global _BUNDLE
    if _BUNDLE is None:
        corpus = ToyCorpus()
        index = ToyIndex(corpus.cases())
        _BUNDLE = (corpus, index, ToyRanker(corpus, index))
    return _BUNDLE
