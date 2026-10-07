"""Legal-aware tokenizer. Owner: WS1.

Splits lower-cased text into word tokens, but keeps statute references as ONE token:
    "S.302", "s. 302", "Sec. 302(1)", "Section 302", "u/s 302"  ->  "s.302", "s.302(1)", ...
    "Art. 21", "Article 21(1)(a)"                               ->  "art.21", ...
"u/s" is treated as "section". A bare "s" needs a following "." so that "the court's 5
judges" is not read as a section. Lists ("Sections 302 and 304") only fuse the first number;
proper multi-section handling is the statute normaliser's job (WS2).
"""
import re
from typing import List

# bare "s" must be followed by a period; the long forms may omit it.
_TOKEN_RE = re.compile(
    r"(?P<ref>(?:\b(?P<long>sections?|secs?|u/ss?|articles?|arts?)\b\s*\.?\s*|(?<![\w'])(?P<short>s)\.\s*)"
    r"(?P<num>\d+[a-z]{0,2}(?:\(\w{1,3}\))*))"
    r"|(?P<word>[a-z0-9]+(?:['’][a-z]+)?)"
)


def tokenize(text: str) -> List[str]:
    """Lower-case and split. Statute references come out as 's.<n>' / 'art.<n>'."""
    out: List[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        if m.group("ref"):
            kind = (m.group("long") or "s")
            prefix = "art" if kind.startswith("art") else "s"
            out.append(f"{prefix}.{m.group('num')}")
        else:
            w = m.group("word")
            if w.endswith(("'s", "’s")):
                w = w[:-2]
            out.append(w)
    return out


def is_reference_token(tok: str) -> bool:
    return tok.startswith(("s.", "art.")) and any(c.isdigit() for c in tok)
