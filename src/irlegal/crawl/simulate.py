"""Replay a crawl over the citation graph (spec 9.9, N5). Owner: WS1/WS2. SIMULATION ONLY: no network traffic.

Pages: pool precedents and TRAIN queries. A page links to the documents it cites (its gold-free `relevant_precedent_ids`
as stored in the corpus: these are the page's hyperlinks). Hosts: the court / jurisdiction of each page (17 pool + 28
query jurisdictions), politeness on a virtual clock. Link URLs are rendered in noisy variants (upper-case host, default port,
tracking parameters, fragments) that `normalize_url` must collapse.

Priority crawler: a URL's front queue is set from the number of distinct in-links DISCOVERED SO FAR (no knowledge of the full graph).
BFS baseline: one FIFO front queue, same politeness machinery.
Metric: share of the K most-cited pool documents (by full in-degree, only used for scoring) that have been fetched, versus fetch budget.
"""
import random
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .dedupe import ContentSeen
from .frontier import MercatorFrontier
from .normalize_url import host_of, normalize


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


class SimWeb:
    """pages: id -> (host, outlinks[ids], content text). Never exposes anything but URLs and content strings."""

    def __init__(self, pages: Dict[str, Tuple[str, List[str], str]], seed: int = 13):
        self.pages, self.rng = pages, random.Random(seed)

    def url(self, pid: str, noisy: bool = False) -> str:
        host = self.pages[pid][0]
        base = f"https://{host}/case/{pid}"
        if not noisy:
            return base
        v = self.rng.randrange(5)
        return [f"HTTPS://{host.upper()}:443/case/{pid}/", f"{base}?utm_source=cite&ref=x", f"{base}#para{self.rng.randrange(40)}",
                f"https://{host}//case/./{pid}", f"{base}?b=2&a=1&utm_campaign=z"][v] if v < 5 else base

    def fetch(self, url: str):
        """(content, out-link urls) for a canonical url; None if unknown (a dangling link)."""
        pid = url.rsplit("/", 1)[-1]
        if pid not in self.pages or host_of(url) != self.pages[pid][0]:
            return None
        host, out, text = self.pages[pid]
        return text, [self.url(o, noisy=True) for o in out if o in self.pages]


def crawl(web: SimWeb, seeds: Sequence[str], budget: int, mode: str = "priority", delay: float = 5.0, fetch_time: float = 1.0,
          thresholds: Tuple[int, int] = (2, 4), dedupe: Optional[ContentSeen] = None, seed: int = 13, bias: Optional[List[float]] = None):
    """Run one crawl. mode: 'priority' (in-links discovered so far) or 'bfs'. Returns (fetch order, stats)."""
    n_front = 3 if mode == "priority" else 1
    fr = MercatorFrontier(n_front=n_front, n_back=8, delay=delay, bias=bias, seed=seed)
    inlinks: Dict[str, set] = defaultdict(set)          # discovered in-links per canonical url (distinct sources)
    seen_raw, merged = set(), 0
    now, order, times = 0.0, [], []

    def prio(u):
        n = len(inlinks[u])
        return 0 if n >= thresholds[1] else 1 if n >= thresholds[0] else 2

    def discover(raw, source):
        nonlocal merged
        u = normalize(raw)
        if raw not in seen_raw:
            seen_raw.add(raw)
            merged += raw != u
        if source is not None:
            inlinks[u].add(source)
        fr.add(u, prio(u) if mode == "priority" else 0)

    for s in seeds:
        discover(web.url(s), None)
    while len(order) < budget:
        nxt = fr.pop(now)
        if nxt is None:
            break
        url, when = nxt
        now = when + fetch_time
        page = web.fetch(url)
        if page is None:
            continue
        text, links = page
        if dedupe is not None and dedupe.check_and_add(url, text) is not None:
            order.append(url); times.append(now)
            continue                                     # near-duplicate page: counted as a fetch, links not followed
        order.append(url); times.append(now)
        for raw in links:
            discover(raw, url)
    return order, {"fetched": len(order), "virtual_time": round(now, 1), "urls_merged_by_normalisation": merged,
                   "near_duplicates": len(dedupe.duplicates) if dedupe else 0, "frontier_left": len(fr)}


def share_found(order: Sequence[str], targets: Iterable[str], budgets: Sequence[int]) -> Dict[int, float]:
    """Share of `targets` (page ids) fetched within the first b fetches, for each budget."""
    tgt = set(targets)
    pos = {u.rsplit("/", 1)[-1]: i for i, u in enumerate(order)}
    return {b: round(sum(1 for t in tgt if pos.get(t, 10 ** 9) < b) / len(tgt), 4) for b in budgets}
