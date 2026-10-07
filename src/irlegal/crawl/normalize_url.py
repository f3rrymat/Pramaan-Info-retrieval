"""URL normalisation (IIR 20.2.1: "have I seen this URL?" needs canonical forms). Owner: WS1/WS2. Simulation only.

Canonical form: lower-case scheme and host, default port removed, fragment dropped, tracking parameters removed
(utm_*, ref, sessionid, sid), remaining parameters sorted, dot segments resolved, duplicate slashes collapsed,
trailing slash removed (except the root), unreserved percent-escapes decoded.
"""
import re
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

TRACKING = re.compile(r"^(utm_.*|ref|sessionid|sid|fbclid|gclid)$", re.I)
DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize(url: str) -> str:
    sp = urlsplit(url.strip())
    scheme = (sp.scheme or "https").lower()
    host = (sp.hostname or "").lower()
    port = sp.port
    netloc = host if (port is None or DEFAULT_PORTS.get(scheme) == port) else f"{host}:{port}"
    segs = []
    for s in re.sub(r"/{2,}", "/", unquote(sp.path) or "/").split("/"):
        if s == "..":
            if segs:
                segs.pop()
        elif s and s != ".":
            segs.append(s)
    path = "/" + "/".join(segs)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True) if not TRACKING.match(k)))
    return urlunsplit((scheme, netloc, path, query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()
