"""IL-PCSR loader (implements CorpusSource). Owner: WS1.

Five parquet files: {train,dev,test}_queries, precedent_candidates (the shared pool),
statute_candidates. Mappings follow DECISIONS.md section 2:
  role   Facts->facts, Issue->issues, Argument by Petitioner/Respondent->arguments,
         Court Reasoning->reasoning, Conclusion->decision, Statute Analysis->statute_analysis,
         Precedent Analysis->precedent_analysis, NONE (and anything unknown)->other
  court  "Supreme Court of India"->SC, contains "High Court"->HC, else OTHER
  date   ISO yyyy-mm-dd if it parses, else None (no temporal filter for that pair)
Gold fields of queries (relevant_*) only ever land in Query.relevant (labels). The statute
gold fields are not read at all (D4).
"""
import datetime as _dt
import logging
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

from irlegal.common.config import load_config, repo_path
from irlegal.common.schema import Case, Query
from .query_builder import QueryBuilder

log = logging.getLogger(__name__)

ROLE_TO_ZONE = {
    "Facts": "facts",
    "Issue": "issues",
    "Argument by Petitioner": "arguments",
    "Argument by Respondent": "arguments",
    "Court Reasoning": "reasoning",
    "Conclusion": "decision",
    "Statute Analysis": "statute_analysis",
    "Precedent Analysis": "precedent_analysis",
    "NONE": "other",
    # Pool-only label (the pool has no "Court Reasoning"). D12 profile (scripts/profile_roles.py):
    # position gap to Court Reasoning 0.038 (<= 0.15), 11.2% in the last 10% (< 50%) -> reasoning.
    "Court Disclosure": "reasoning",
}
SPLIT_FILE = {"train": "train_queries", "val": "dev_queries", "dev": "dev_queries", "test": "test_queries"}
_QUERY_COLS = ["id", "date", "text", "rhetorical_roles", "relevant_precedent_ids"]
_POOL_COLS = ["id", "case_title", "date", "jurisdiction", "text", "rhetorical_roles", "relevant_precedent_ids"]


def role_to_zone(role: str) -> str:
    return ROLE_TO_ZONE.get(role, "other")


def map_court(jurisdiction: Optional[str]) -> Optional[str]:
    if not isinstance(jurisdiction, str) or not jurisdiction.strip():
        return None
    if jurisdiction.strip() == "Supreme Court of India":
        return "SC"
    if "High Court" in jurisdiction:
        return "HC"
    return "OTHER"


def parse_date(value) -> Optional[str]:
    """ISO yyyy-mm-dd when it parses as a real calendar date, else None."""
    if not isinstance(value, str):
        return None
    try:
        return _dt.date.fromisoformat(value.strip()[:10]).isoformat() if len(value.strip()) >= 10 else None
    except ValueError:
        return None


def zones_from_paragraphs(paragraphs, roles) -> Dict[str, List[str]]:
    zones: Dict[str, List[str]] = {}
    for para, role in zip(paragraphs, roles):
        zones.setdefault(role_to_zone(role), []).append(para)
    return zones


class IlPcsrCorpus:
    def __init__(self, data_dir: Optional[str] = None):
        cfg = load_config()["dataset"]
        self.dir = Path(data_dir) if data_dir else repo_path(cfg["local_dir"])
        self.builders = {v: QueryBuilder() for v in ("facts_issues", "full")}
        self._raw_builder = QueryBuilder(scrub=False)
        self.builder = self.builders["facts_issues"]       # headline view; scrub stats per view in self.builders
        self._pool: Optional[List[Case]] = None
        self._pool_by_id: Dict[str, Case] = {}
        self._queries: Dict[str, List[Query]] = {}

    # ------------------------------------------------------------ raw access
    def _read(self, name: str, cols=None) -> pd.DataFrame:
        return pd.read_parquet(self.dir / f"{name}.parquet", columns=cols)

    # ------------------------------------------------------------ CorpusSource
    def cases(self, pool: Optional[str] = None) -> List[Case]:
        """The shared precedent pool (one pool: `pool` is accepted for the protocol and ignored)."""
        if self._pool is None:
            df = self._read("precedent_candidates", _POOL_COLS)
            out = []
            for r in df.itertuples(index=False):
                paras = list(r.text)
                zones = zones_from_paragraphs(paras, r.rhetorical_roles)
                out.append(Case(
                    doc_id=r.id, title=r.case_title if isinstance(r.case_title, str) else "",
                    text="\n".join(paras), court=map_court(r.jurisdiction), date=parse_date(r.date),
                    zones=zones, statutes=set(), cites_out=list(r.relevant_precedent_ids), pool=None))
            self._pool = out
            self._pool_by_id = {c.doc_id: c for c in out}
        return self._pool

    def queries(self, split: str, view: str = "facts_issues", scrub: bool = True) -> List[Query]:
        key = f"{SPLIT_FILE[split]}:{view}:{scrub}"
        if key not in self._queries:
            canon = "val" if split == "dev" else split
            df = self._read(SPLIT_FILE[split], _QUERY_COLS)
            out = []
            for r in df.itertuples(index=False):
                zones = zones_from_paragraphs(list(r.text), r.rhetorical_roles)
                out.append((self.builders[view] if scrub else self._raw_builder).build(r.id, zones, parse_date(r.date), canon,
                                              r.relevant_precedent_ids, view=view))
            self._queries[key] = out
            (self.builders[view] if scrub else self._raw_builder).log_stats()
        return self._queries[key]

    def get_case(self, doc_id: str) -> Optional[Case]:
        self.cases()
        return self._pool_by_id.get(doc_id)

    # ------------------------------------------------------------ statutes (D13)
    def statutes(self) -> List[Dict]:
        """The statute table: [{id, name, text: [paragraphs]}]."""
        df = self._read("statute_candidates")
        return [{"id": r.id, "name": r.provision_name, "text": list(r.text)} for r in df.itertuples(index=False)]

    def pool_statute_ids(self) -> Dict[str, List[str]]:
        """DOC-SIDE corpus annotation: provision ids attached to each pool document (D13).
        Query-side gold statute fields are never read here (see evaluation/statute_eval.py)."""
        df = self._read("precedent_candidates", ["id", "relevant_statute_ids"])
        return {r.id: list(r.relevant_statute_ids) for r in df.itertuples(index=False)}

    # ------------------------------------------------------------ helpers
    def relevant_ids(self, split: str) -> Dict[str, Set[str]]:
        """qid -> gold cited ids, read straight from the parquet (labels only; cheap for train)."""
        df = self._read(SPLIT_FILE[split], ["id", "relevant_precedent_ids"])
        return {r.id: set(r.relevant_precedent_ids) for r in df.itertuples(index=False)}

    def train_indegree(self) -> Counter:
        """Popularity signal: number of TRAIN queries citing each id (D6: train edges only)."""
        c: Counter = Counter()
        for ids in self.relevant_ids("train").values():
            c.update(ids)
        return c
