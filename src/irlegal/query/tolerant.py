"""Tolerant retrieval (IIR ch. 3): 3-gram wildcard index, edit-distance suggestions, Soundex. Owner: WS2.

Idea credit (AI_USE.md): the Soundex-for-party-names use follows reference/stare-ir `names.py`; the code here is
rewritten against plain vocabularies and the course algorithms.
"""
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set


def kgrams(term: str, k: int = 3) -> Set[str]:
    p = f"${term}$"
    return {p[i:i + k] for i in range(len(p) - k + 1)}


class KGramIndex:
    """gram -> sorted term ids. Wildcards (`cat*`, `*tion`, `co*ct`) are answered by intersecting gram lists
    and then filtering with the exact pattern (the k-gram step can only over-generate)."""

    def __init__(self, vocabulary: Iterable[str], k: int = 3):
        self.k = k
        self.terms: List[str] = sorted(set(vocabulary))
        self._grams: Dict[str, List[int]] = defaultdict(list)
        for i, t in enumerate(self.terms):
            for g in kgrams(t, k):
                self._grams[g].append(i)

    def wildcard(self, pattern: str, limit: int = 500) -> List[str]:
        pattern = pattern.lower()
        if "*" not in pattern:
            return [pattern] if pattern in set(self.terms) else []
        rx = re.compile("^" + ".*".join(re.escape(p) for p in pattern.split("*")) + "$")
        pieces = pattern.split("*")
        lists: List[List[int]] = []
        for j, piece in enumerate(pieces):
            if not piece:
                continue
            padded = ("$" if j == 0 else "") + piece + ("$" if j == len(pieces) - 1 else "")
            for i in range(len(padded) - self.k + 1):
                lists.append(self._grams.get(padded[i:i + self.k], []))
        if lists:
            lists.sort(key=len)
            cand = set(lists[0])
            for l in lists[1:]:
                cand &= set(l)
                if not cand:
                    break
            pool = [self.terms[i] for i in sorted(cand)]
        else:
            pool = self.terms                  # pieces too short for any gram: scan the dictionary
        return [t for t in pool if rx.match(t)][:limit]

    def similar(self, term: str, min_jaccard: float = 0.2) -> List[str]:
        """Terms sharing enough k-grams with `term` (candidate set for spelling correction)."""
        g = kgrams(term, self.k)
        counts: Dict[int, int] = defaultdict(int)
        for gram in g:
            for i in self._grams.get(gram, ()):
                counts[i] += 1
        out = []
        for i, c in counts.items():
            u = len(g) + len(kgrams(self.terms[i], self.k)) - c
            if c / u >= min_jaccard:
                out.append(self.terms[i])
        return out


def edit_distance(a: str, b: str, max_d: Optional[int] = None) -> int:
    """Levenshtein distance (insert, delete, substitute, each cost 1); stops early above max_d."""
    if abs(len(a) - len(b)) > (max_d if max_d is not None else 10 ** 9):
        return (max_d or 0) + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if max_d is not None and min(cur) > max_d:
            return max_d + 1
        prev = cur
    return prev[-1]


class SpellCorrector:
    """Suggestions for a word that is not in the dictionary: k-gram candidates, ranked by edit distance then df."""

    def __init__(self, kgram: KGramIndex, df: Optional[Dict[str, int]] = None):
        self.kg, self.df = kgram, df or {}
        self._set = set(kgram.terms)

    def suggest(self, word: str, n: int = 5, max_dist: int = 2) -> List[Dict]:
        w = word.lower()
        if w in self._set or len(w) < 3:
            return []
        scored = []
        for t in self.kg.similar(w):
            d = edit_distance(w, t, max_dist)
            if d <= max_dist:
                scored.append((d, -self.df.get(t, 0), t))
        scored.sort()
        return [{"term": t, "edit_distance": d, "df": -negdf} for d, negdf, t in scored[:n]]


_SOUNDEX = {**dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"), **dict.fromkeys("dt", "3"), "l": "4",
            **dict.fromkeys("mn", "5"), "r": "6"}


def soundex(name: str) -> str:
    """American Soundex: first letter + three digits; h and w do not separate equal codes, vowels do."""
    s = re.sub(r"[^a-z]", "", name.lower())
    if not s:
        return ""
    out, last = s[0].upper(), _SOUNDEX.get(s[0], "")
    for ch in s[1:]:
        code = _SOUNDEX.get(ch, "")
        if code and code != last:
            out += code
        if ch not in "hw":
            last = code
    return (out + "000")[:4]


class SoundexIndex:
    """Phonetic lookup for party-name variants (Gopalan / Gopalen, Mohd / Mohammed)."""

    def __init__(self, words: Iterable[str]):
        self.by_code: Dict[str, Set[str]] = defaultdict(set)
        for w in words:
            if w.isalpha() and len(w) > 2:
                self.by_code[soundex(w)].add(w.lower())

    def similar(self, name: str) -> List[str]:
        return sorted(self.by_code.get(soundex(name), ()))
