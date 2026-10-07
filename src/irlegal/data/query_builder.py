"""Realistic query building with citation scrubbing (spec 9.1, DECISIONS D3/D4). Owner: WS1.

The headline query is Facts + Issues only (schema.QUERY_ZONES). Case-citation strings are
removed from it; the number of removals per pattern group is counted, never the text.
Gold fields (relevant_*) are NEVER read here: query statutes stay empty until the statute
normaliser (WS2) runs on this text.
"""
import logging
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from irlegal.common.schema import QUERY_ZONES, Query

log = logging.getLogger(__name__)

_Y = r"(?:1[6-9]|20)\d\d"
_NUM = r"\d+[A-Za-z]?"
# Reporter citations. Order matters: longer / more specific patterns first.
PATTERNS: List[Tuple[str, "re.Pattern"]] = [
    ("placeholder", re.compile(r"<\s*CITATION\s*>", re.I)),
    ("AIR", re.compile(rf"\bA\.?\s?I\.?\s?R\.?\s*(?:\(?{_Y}\)?\s*)?(?:[A-Z][A-Za-z.]{{0,12}}\s*)?(?:\(?{_NUM}\)?)?", re.I)),
    # AIR must be followed by a year or number to count; checked in _air_ok.
    ("SCC", re.compile(rf"(?:[\(\[]\s*{_Y}\s*[\)\]]|\b{_Y})\s*(?:\(\s*\d+\s*\)\s*|\d+\s+|Supp\.?\s*(?:\(\s*\d+\s*\)\s*)?)?S\.?\s?C\.?\s?C\.?\s*(?:\(\s*[A-Za-z]+\s*\)\s*)?(?:Supp\.?\s*)?\d*", re.I)),
    ("SCC", re.compile(rf"\bS\.?C\.?C\.?\s*(?:\(\s*[A-Za-z]+\s*\)\s*)?\d+\s*(?:\(\s*{_Y}\s*\))?", re.I)),
    ("SCR", re.compile(rf"(?:[\(\[]\s*{_Y}\s*[\)\]]|\b{_Y})\s*(?:\(\s*\d+\s*\)\s*|Supp\.?\s*(?:\(\s*\d+\s*\)\s*)?|\d+\s+)?S\.?\s?C\.?\s?R\.?\s*\d*", re.I)),
    ("SCALE", re.compile(rf"(?:[\(\[]\s*{_Y}\s*[\)\]]|\b{_Y})\s*(?:\(\s*\d+\s*\)\s*|\d+\s+)?SCALE\s*\d*", re.I)),
    ("other_reporter", re.compile(rf"(?:[\(\[]\s*{_Y}\s*[\)\]]|\b{_Y})\s*(?:\(\s*\d+\s*\)\s*)?(?:J\.?T\.?|I\.?L\.?R\.?|Cri\.?\s?L\.?\s?J\.?|CrLJ|MANU|ITR|SCJ)\s*\d*", re.I)),
    # "State of X v. Y" with a year in brackets/parens right after, or ", 1973".
    ("party_pair_year", re.compile(
        rf"\b[A-Z][\w.&'’-]*(?:\s+(?:of|and|&|the|for|[A-Z][\w.&'’-]*)){{0,6}}\s+(?:v\.?|vs\.?|versus)\s+"
        rf"[A-Z][\w.&'’-]*(?:\s+(?:of|and|&|the|for|[A-Z][\w.&'’-]*)){{0,8}}\s*,?\s*[\(\[]\s*{_Y}\s*[\)\]]")),
    ("party_pair_year", re.compile(
        rf"\b[A-Z][\w.&'’-]*(?:\s+(?:of|and|&|the|for|[A-Z][\w.&'’-]*)){{0,6}}\s+(?:v\.?|vs\.?|versus)\s+"
        rf"[A-Z][\w.&'’-]*(?:\s+(?:of|and|&|the|for|[A-Z][\w.&'’-]*)){{0,8}}\s*,\s*{_Y}\b")),
]
_AIR_OK = re.compile(rf"\d")


def scrub_citations(text: str) -> Tuple[str, Counter]:
    """Remove case-citation strings. Returns (clean_text, removals_per_pattern_group)."""
    counts: Counter = Counter()
    for name, pat in PATTERNS:
        def _sub(m, name=name):
            if name == "AIR" and not _AIR_OK.search(m.group(0)):
                return m.group(0)          # bare "AIR" (e.g. the word) is not a citation
            counts[name] += 1
            return " "
        text = pat.sub(_sub, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip(), counts


class QueryBuilder:
    """Builds Query objects from role-labelled paragraphs; keeps aggregate scrub statistics."""

    def __init__(self, scrub: bool = True):
        self.scrub = scrub          # False only for the leakage audit (c)
        self.scrub_stats: Counter = Counter()
        self.n_built = 0
        self.n_empty = 0

    def zone_texts(self, zones: Dict[str, List[str]], names=QUERY_ZONES) -> Dict[str, str]:
        out = {}
        for z in names:
            raw = " ".join(zones.get(z, []))
            clean, c = scrub_citations(raw) if self.scrub else (raw, Counter())
            self.scrub_stats.update(c)
            out[z] = clean
        return out

    def build(self, qid: str, zones: Dict[str, List[str]], date: Optional[str], split: str,
              relevant, view: str = "facts_issues") -> Query:
        """view: 'facts_issues' (headline, D3) or 'full' (reference row only: all zones)."""
        names = QUERY_ZONES if view == "facts_issues" else tuple(zones.keys())
        zt = self.zone_texts(zones, names)
        text = " ".join(zt[z] for z in names if zt[z])
        self.n_built += 1
        self.n_empty += not text
        # statutes=set(): never taken from gold fields (D4); WS2's normaliser fills it from text.
        return Query(qid=qid, case_id=qid, text=text, zones=zt, statutes=set(), date=date,
                     split=split, relevant=set(relevant))

    def log_stats(self):
        log.info("scrubber: %d queries, %d empty, removals=%s", self.n_built, self.n_empty, dict(self.scrub_stats))
