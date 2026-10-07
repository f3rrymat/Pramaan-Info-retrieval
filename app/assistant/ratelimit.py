"""Per-session sliding-window rate limit for the assistant endpoints (in memory, per process)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

from . import config

_lock = threading.Lock()
_hits: Dict[Tuple[str, str], deque] = defaultdict(deque)


def check(session: str, kind: str, now: Optional[float] = None) -> int:
    """Record one request; return 0 if allowed, else the seconds to wait (the request is not recorded then)."""
    limit, window = config.RATE_LIMITS[kind]
    now = now if now is not None else time.monotonic()
    with _lock:
        q = _hits[(session, kind)]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(q[0] + window - now) + 1)
        q.append(now)
        return 0


def reset() -> None:
    with _lock:
        _hits.clear()
