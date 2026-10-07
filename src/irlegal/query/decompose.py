"""Issue decomposition (N6, agentic-lite, no LLM): split the Issues of a query into sub-queries, retrieve each,
fuse the rankings with reciprocal rank fusion  score(d) = sum over lists 1 / (k + rank(d)),  k = 60. Owner: WS2.
"""
import re
from typing import Dict, List, Sequence, Tuple

_SPLIT = re.compile(r"(?<=[.?;:])\s+(?=[A-Z(\[\d])|\s+(?=Whether\b)|\s+(?=\(\s*(?:[ivx]+|[a-z]|\d+)\s*\)\s)")


def split_issues(text: str, min_words: int = 8) -> List[str]:
    """Issue statements: split at sentence ends, before 'Whether' and before numbered items; segments shorter than
    `min_words` are merged into the next one (a lone short segment is kept only if nothing else exists)."""
    parts = [p.strip() for p in _SPLIT.split(text or "") if p and p.strip()]
    out, carry = [], ""
    for p in parts:
        cur = (carry + " " + p).strip() if carry else p
        if len(cur.split()) < min_words:
            carry = cur
        else:
            out.append(cur)
            carry = ""
    if carry:
        if out:
            out[-1] = out[-1] + " " + carry
        else:
            out.append(carry)
    return out


def decompose(issues_text: str, min_words: int = 8) -> List[str]:
    """Sub-queries (one per issue statement); empty list when there are no issues."""
    return split_issues(issues_text, min_words)


def rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> List[Tuple[str, float]]:
    """Reciprocal rank fusion of best-first id lists. Ties break by the first list's order, then by id."""
    score: Dict[str, float] = {}
    first: Dict[str, int] = {}
    for lst in rankings:
        for r, d in enumerate(lst, 1):
            score[d] = score.get(d, 0.0) + 1.0 / (k + r)
            first.setdefault(d, r)
    return sorted(score.items(), key=lambda kv: (-kv[1], first[kv[0]], kv[0]))
