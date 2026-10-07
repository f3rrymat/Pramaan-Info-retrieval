"""Frozen data contracts (contracts-v1). Owner: all four workstreams jointly.

FROZEN after Phase 0. Changing anything here needs all four members to agree and
goes through one dedicated pull request (spec Section 11).

The dataclasses are exactly the ones in the Master Spec, Section 11. Lines marked
"ADDED (contracts-v1)" are additive, have defaults, and do not change the meaning of
any spec field; docs/SPEC_CHANGES.md explains why each one exists.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

ZONES = ("facts", "issues", "arguments", "reasoning", "decision", "other",
         "statute_analysis", "precedent_analysis")  # last two ADDED (DECISIONS.md D8)

# ADDED (contracts-v1): canonical names shared by router, UI and evaluation code.
QUERY_ZONES = ("facts", "issues")                 # the realistic query (spec 9.1)
SPLITS = ("train", "val", "test")
COURTS = ("SC", "HC", "OTHER")
COMPONENTS = ("text", "statute", "authority", "court", "recency")  # net-score parts (spec 9.5)


@dataclass
class Case:
    doc_id: str
    title: str
    text: str
    court: Optional[str] = None            # "SC", "HC", "OTHER" or None
    date: Optional[str] = None             # ISO "yyyy-mm-dd" or "yyyy" or None
    zones: Dict[str, List[str]] = field(default_factory=dict)  # zone -> sentences
    statutes: Set[str] = field(default_factory=set)            # e.g. {"IPC_302"}
    cites_out: List[str] = field(default_factory=list)         # ground-truth cited doc_ids
    # ADDED (contracts-v1): which candidate pool the case belongs to. IL-TUR ships
    # separate candidate pools per split ("train", "val", "test"); None = unknown or pooled.
    pool: Optional[str] = None


@dataclass
class Query:
    qid: str
    case_id: str
    text: str                      # realistic query text (facts + issues)
    zones: Dict[str, str]
    statutes: Set[str]
    date: Optional[str]
    split: str                     # "train" | "val" | "test"
    relevant: Set[str]             # ground-truth cited doc_ids


@dataclass
class Result:
    doc_id: str
    score: float
    components: Dict[str, float]   # text / statute / authority / court / recency / per-zone-pair
    explanation: Dict              # matched statutes, top terms per zone, zone-pair contributions
