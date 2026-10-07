"""Frozen interfaces (contracts-v1). Owner: all four workstreams jointly.

`Index` and `Ranker` are exactly as in the Master Spec, Section 11, plus two additive
Index methods. The other Protocols are ADDED (contracts-v1): they are the seams where
one workstream's code calls another's, so each side can build against the toy stubs
(src/irlegal/common/toy.py) until the real module lands. See docs/SPEC_CHANGES.md.
"""
from typing import Dict, Iterable, List, Optional, Protocol, Set, Tuple, runtime_checkable

from .schema import Case, Query, Result


@runtime_checkable
class Index(Protocol):
    def df(self, term: str, zone: str) -> int: ...
    def postings(self, term: str, zone: str) -> List[Tuple[str, int]]: ...   # (doc_id, tf)
    def positions(self, term: str, zone: str, doc_id: str) -> List[int]: ...
    def doc_len(self, doc_id: str, zone: str) -> int: ...                     # number of tokens
    def meta(self, doc_id: str) -> Dict: ...                                   # court, date, statutes
    def n_docs(self) -> int: ...
    # ADDED (contracts-v1): needed by tolerant retrieval (k-gram, spelling), the
    # Index Inspector, cosine-norm precomputation and cluster pruning.
    def terms(self, zone: str) -> Iterable[str]: ...
    def doc_ids(self) -> List[str]: ...


@runtime_checkable
class Ranker(Protocol):
    # opts used across workstreams (all optional):
    #   candidates: Optional[Set[str]]  restrict scoring to these doc_ids (from a CandidateSelector)
    #   exclude: Set[str]               doc_ids never returned (the query's own case is always excluded)
    #   weights: Dict[str, float]       net-score weights keyed by schema.COMPONENTS
    def rank(self, query: Query, k: int, **opts) -> List[Result]: ...


# ---------------------------------------------------------------- ADDED (contracts-v1)

@runtime_checkable
class CorpusSource(Protocol):
    """WS1 provides the real one; everyone else codes against it."""
    def cases(self, pool: Optional[str] = None) -> List[Case]: ...     # pool None = all candidates
    def queries(self, split: str) -> List[Query]: ...
    def get_case(self, doc_id: str) -> Optional[Case]: ...


@runtime_checkable
class Segmenter(Protocol):
    """WS1. Sentences in, zone -> sentences out (keys from schema.ZONES)."""
    def segment(self, sentences: List[str]) -> Dict[str, List[str]]: ...


@runtime_checkable
class StatuteNormalizer(Protocol):
    """WS2. Free text in, canonical statute tokens out (e.g. {"IPC_302", "CONST_ART_21"})."""
    def extract(self, text: str) -> Set[str]: ...


@runtime_checkable
class CandidateSelector(Protocol):
    """WS4 pruning (champion lists, tiers, clusters, elimination).

    Returns the doc_ids to score, or None meaning "no pruning, score everything".
    Passed to a Ranker as rank(query, k, candidates=...).
    """
    def select(self, query: Query, k: int) -> Optional[Set[str]]: ...
