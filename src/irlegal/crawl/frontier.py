"""Mercator-style URL frontier (IIR 20.2.3). Owner: WS1/WS2. Simulation only: nothing is fetched from a network.

Front queues hold URLs by priority; back queues hold URLs of ONE host each. A heap keyed by the time a host may be
contacted again enforces politeness on a VIRTUAL clock. When a back queue empties it is refilled from the front queues
(biased toward high priority) with a URL of a host that has no back queue; URLs of hosts that already own a back queue
are appended to it.

Priority comes from in-links discovered so far: `add(url, priority)` can be called again for a URL that gained
in-links; the higher entry then wins and the stale lower entry is skipped on pop.
"""
import heapq
import random
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from .normalize_url import host_of


class MercatorFrontier:
    def __init__(self, n_front: int = 3, n_back: int = 8, delay: float = 5.0, bias: Optional[List[float]] = None, seed: int = 13):
        self.front: List[Deque[str]] = [deque() for _ in range(n_front)]
        self.bias = bias or [8.0, 3.0, 1.0][:n_front] + [1.0] * max(0, n_front - 3)
        self.n_back, self.delay = n_back, delay
        self.back: Dict[int, Deque[str]] = {}
        self.host_queue: Dict[str, int] = {}
        self.free = list(range(n_back))
        self.heap: List[Tuple[float, int]] = []          # (earliest contact time, back queue id)
        self.queued: Dict[str, int] = {}                 # url -> best (lowest) priority level queued
        self.done: Set[str] = set()
        self.host_next: Dict[str, float] = {}             # politeness memory survives the retirement of a back queue
        self.pulled: Set[str] = set()                    # already moved to a back queue: priorities no longer matter
        self.rng = random.Random(seed)

    def add(self, url: str, priority: int) -> None:
        if url in self.done or url in self.pulled:
            return
        p = min(priority, len(self.front) - 1)
        if url in self.queued and self.queued[url] <= p:
            return
        self.queued[url] = p
        self.front[p].append(url)

    def _pull_front(self) -> Optional[str]:
        """Draw one live URL from the front queues, biased by priority weights."""
        while True:
            live = [i for i, q in enumerate(self.front) if q]
            if not live:
                return None
            i = self.rng.choices(live, weights=[self.bias[j] for j in live])[0]
            url = self.front[i].popleft()
            if url in self.done or self.queued.get(url) != i:
                continue                                  # stale entry (already crawled, or re-queued higher)
            self.pulled.add(url)
            return url

    def _refill(self) -> None:
        """Fill empty back queues: each takes URLs until one belongs to a host with no queue (Mercator step)."""
        while self.free:
            url = self._pull_front()
            if url is None:
                return
            h = host_of(url)
            if h in self.host_queue:
                self.back[self.host_queue[h]].append(url)
                continue
            b = self.free.pop()
            self.host_queue[h] = b
            self.back[b] = deque([url])
            heapq.heappush(self.heap, (self.host_next.get(h, 0.0), b))

    def pop(self, now: float) -> Optional[Tuple[str, float]]:
        """Next (url, fetch_time): the earliest permitted contact; the clock never goes backwards."""
        self._refill()
        while self.heap:
            t, b = heapq.heappop(self.heap)
            q = self.back[b]
            if not q:                                     # empty: retire this queue, refill from the front
                for h, qb in list(self.host_queue.items()):
                    if qb == b:
                        del self.host_queue[h]
                self.free.append(b)
                self._refill()
                continue
            url = q.popleft()
            when = max(now, t)
            self.done.add(url)
            self.queued.pop(url, None)
            self.host_next[host_of(url)] = when + self.delay
            heapq.heappush(self.heap, (when + self.delay, b))
            return url, when
        return None

    def __len__(self) -> int:
        return sum(1 for u, p in self.queued.items() if u not in self.done)
