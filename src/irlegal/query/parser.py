"""Query language parser. Owner: WS2.

Grammar (Westlaw-style; the operator set follows reference/stare-ir `boolean.py`, rewritten here)::

    expr   := or
    or     := and ( "OR" and )*
    and    := not ( ["AND"] not )*          adjacent operands are ANDed
    not    := "NOT" not | prox
    prox   := atom ( ("/" N | "pre/" N) atom )*     /N: within N words, any order; pre/N: first operand before second
    atom   := "(" expr ")" | "quoted phrase" | field:value | field:"quoted phrase" | word

Words may carry wildcards (`murder*`, `*tion`). Fields: a zone name (facts, issues, arguments, reasoning,
decision, statute_analysis, precedent_analysis, other) restricts a term or phrase to that zone; filters are
`court:SC|HC|OTHER`, `year:2010`, `year:2010..2015`, `year:>=2000`, `before:2015-06-30`, `after:2000-01-01`.
"""
import re
from dataclasses import dataclass
from typing import List, Tuple, Union

from irlegal.common.schema import ZONES

FILTERS = ("court", "year", "before", "after")
ZONE_FIELDS = tuple(ZONES) + ("fi", "all")


class QuerySyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class Term:
    word: str
    zone: str = ""


@dataclass(frozen=True)
class Phrase:
    text: str
    zone: str = ""


@dataclass(frozen=True)
class Filter:
    name: str
    value: str


@dataclass(frozen=True)
class Not:
    child: "Node"


@dataclass(frozen=True)
class And:
    children: Tuple["Node", ...]


@dataclass(frozen=True)
class Or:
    children: Tuple["Node", ...]


@dataclass(frozen=True)
class Prox:
    left: "Node"
    right: "Node"
    k: int
    ordered: bool


Node = Union[Term, Phrase, Filter, Not, And, Or, Prox]

_LEX = re.compile(r"""\s*(?:
      (?P<phrase>"[^"]*")
    | (?P<lp>\()
    | (?P<rp>\))
    | (?P<pre>pre/\d+)
    | (?P<prox>/\d+)
    | (?P<field>[A-Za-z_]+:(?:"[^"]*"|[^\s()"]+))
    | (?P<word>[^\s()"]+)
  )""", re.X)


def lex(q: str) -> List[Tuple[str, str]]:
    out, pos, q = [], 0, q.strip()
    while pos < len(q):
        m = _LEX.match(q, pos)
        if not m or m.end() == pos:
            raise QuerySyntaxError(f"cannot read the query near {q[pos:pos + 12]!r}")
        pos, kind = m.end(), m.lastgroup
        val = m.group(kind)
        if kind == "word" and val in ("AND", "OR", "NOT"):
            kind = val.lower()
        out.append((kind, val))
    return out


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self) -> Node:
        if not self.t:
            raise QuerySyntaxError("empty query")
        node = self.p_or()
        if self.i != len(self.t):
            raise QuerySyntaxError(f"unexpected {self.t[self.i][1]!r}")
        return node

    def p_or(self) -> Node:
        parts = [self.p_and()]
        while self.peek() == "or":
            self.take()
            parts.append(self.p_and())
        return parts[0] if len(parts) == 1 else Or(tuple(parts))

    def p_and(self) -> Node:
        parts = [self.p_not()]
        while True:
            k = self.peek()
            if k == "and":
                self.take()
                parts.append(self.p_not())
            elif k in ("phrase", "lp", "field", "word", "not"):
                parts.append(self.p_not())
            else:
                break
        return parts[0] if len(parts) == 1 else And(tuple(parts))

    def p_not(self) -> Node:
        if self.peek() == "not":
            self.take()
            return Not(self.p_not())
        return self.p_prox()

    def p_prox(self) -> Node:
        left = self.atom()
        while self.peek() in ("prox", "pre"):
            kind, val = self.take()
            left = Prox(left, self.atom(), int(val.split("/")[1]), kind == "pre")
        return left

    def atom(self) -> Node:
        if self.peek() is None:
            raise QuerySyntaxError("the query ends where an operand was expected")
        kind, val = self.take()
        if kind == "lp":
            node = self.p_or()
            if self.peek() != "rp":
                raise QuerySyntaxError("missing ')'")
            self.take()
            return node
        if kind == "phrase":
            return Phrase(val.strip('"'))
        if kind == "field":
            name, v = val.split(":", 1)
            name = name.lower()
            quoted = v.startswith('"')
            v = v.strip('"')
            if name in FILTERS:
                return Filter(name, v)
            if name in ZONE_FIELDS:
                return Phrase(v, name) if quoted else Term(v, name)
            raise QuerySyntaxError(f"unknown field {name!r}; zones: {', '.join(ZONE_FIELDS)}; filters: {', '.join(FILTERS)}")
        if kind in ("word",):
            return Term(val)
        raise QuerySyntaxError(f"unexpected {val!r}")


def parse(q: str) -> Node:
    return _Parser(lex(q)).parse()


def to_tree(node: Node) -> dict:
    """JSON-friendly nested dict for the Query Lab."""
    if isinstance(node, Term):
        return {"op": "TERM", "value": node.word, **({"zone": node.zone} if node.zone else {}), "wildcard": "*" in node.word}
    if isinstance(node, Phrase):
        return {"op": "PHRASE", "value": node.text, **({"zone": node.zone} if node.zone else {})}
    if isinstance(node, Filter):
        return {"op": "FILTER", "name": node.name, "value": node.value}
    if isinstance(node, Not):
        return {"op": "NOT", "children": [to_tree(node.child)]}
    if isinstance(node, (And, Or)):
        return {"op": "AND" if isinstance(node, And) else "OR", "children": [to_tree(c) for c in node.children]}
    if isinstance(node, Prox):
        return {"op": f"PRE/{node.k}" if node.ordered else f"/{node.k}", "children": [to_tree(node.left), to_tree(node.right)]}
    raise TypeError(node)


def pretty(node: Node, indent: int = 0) -> str:
    t, pad = to_tree(node), "  " * indent

    def go(d, lvl):
        p = "  " * lvl
        head = d["op"] + (f" {d.get('name', '')}:{d['value']}" if d["op"] == "FILTER" else f" {d['value']!r}" if "value" in d else "") + (f" [zone={d['zone']}]" if d.get("zone") else "")
        return "\n".join([p + head] + [go(c, lvl + 1) for c in d.get("children", [])])
    return go(t, indent)


def words_of(node: Node) -> List[str]:
    """Positive query words (for ranking Boolean results); words under NOT are excluded."""
    if isinstance(node, Term):
        return [node.word]
    if isinstance(node, Phrase):
        return node.text.split()
    if isinstance(node, (And, Or)):
        return [w for c in node.children for w in words_of(c)]
    if isinstance(node, Prox):
        return words_of(node.left) + words_of(node.right)
    return []
