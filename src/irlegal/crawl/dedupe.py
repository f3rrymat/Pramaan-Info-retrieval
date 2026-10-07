"""Near-duplicate detection by shingle Jaccard (IIR 19.6). Owner: WS1/WS2. Simulation only.

shingles(text, k): hashed k-word windows. jaccard(A, B) = |A n B| / |A u B|. ContentSeen keeps a bottom-m sketch (the m
smallest shingle hashes) of every page and an inverted map from sketch values to pages, so a new page is compared
only with pages that share a sketch value; the exact Jaccard of the shingle sets decides.
"""
import re
import zlib
from collections import defaultdict
from typing import Dict, List, Optional, Set


def shingles(text: str, k: int = 4) -> Set[int]:
    w = re.findall(r"[a-z0-9]+", text.lower())
    if len(w) < k:
        return {zlib.crc32(" ".join(w).encode())} if w else set()
    return {zlib.crc32(" ".join(w[i:i + k]).encode()) for i in range(len(w) - k + 1)}


def jaccard(a: Set[int], b: Set[int]) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


class ContentSeen:
    def __init__(self, threshold: float = 0.9, sketch: int = 16, k: int = 4):
        self.threshold, self.m, self.k = threshold, sketch, k
        self._sets: Dict[str, Set[int]] = {}
        self._by_hash: Dict[int, List[str]] = defaultdict(list)
        self.duplicates: List[tuple] = []

    def check_and_add(self, url: str, text: str) -> Optional[str]:
        """Return the url of an earlier near-duplicate (and record the pair), else None and remember the page."""
        s = shingles(text, self.k)
        sk = sorted(s)[: self.m]
        cands: Set[str] = set()
        for h in sk:
            cands.update(self._by_hash.get(h, ()))
        for c in sorted(cands):
            if jaccard(s, self._sets[c]) >= self.threshold:
                self.duplicates.append((url, c))
                return c
        self._sets[url] = s
        for h in sk:
            self._by_hash[h].append(url)
        return None
