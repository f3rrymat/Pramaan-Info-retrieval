"""Statute normaliser (spec 9.3) and the statute bridge (DECISIONS D13). Owner: WS2.

Normaliser: free text -> canonical tokens such as IPC_302, CRPC_161, CONST_ART_21.
  * section markers: Section(s), Sec., S., s., Ss., u/s, u/ss; article markers: Article(s), Art., Arts.
  * number lists: "302 and 304", "302, 304", "302/34" (every number gets a token)
  * sub-sections "302(1)(a)": the base section is the token; `detail=True` adds IPC_302(1)(a) too
  * the act is read from the words right AFTER the numbers ("of the Indian Penal Code", "IPC",
    "I.P.C.") or right BEFORE the marker ("IPC Section 302", "Indian Penal Code, Section 302").
    Known acts use short codes; an unknown "... Act" is slugified (MANIPUR_MUNICIPALITIES_ACT).
    A section without a recognisable act yields no token (it would be ambiguous). Articles
    default to the Constitution.

Bridge (D13): query text is masked, so the query side PREDICTS provisions by retrieving over the
statute table with the query's Facts+Issues only. Each provision is a pseudo-document made of its
own name and text, optionally enriched with the Facts+Issues text of pool documents annotated with
it (doc-side annotation). Gold statute fields of a query are never an input; they are used only by
evaluation/statute_eval.py to measure prediction Recall@k.
"""
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import scipy.sparse as sp

# alias regex (matched on lower-cased text) -> short code
ACTS: List[Tuple[str, str]] = [
    (r"indian\s+penal\s+code|i\.\s?p\.\s?c\b\.?|ipc\b", "IPC"),
    (r"code\s+of\s+criminal\s+procedure|cr\.\s?p\.\s?c\b\.?|crpc\b|cr\.\s?pc\b", "CRPC"),
    (r"code\s+of\s+civil\s+procedure|c\.\s?p\.\s?c\b\.?|cpc\b", "CPC"),
    (r"constitution(?:\s+of\s+india)?", "CONST"),
    (r"income[\s-]*tax\s+act", "ITACT"),
    (r"negotiable\s+instruments?\s+act|n\.\s?i\.\s?act", "NIACT"),
    (r"indian\s+evidence\s+act|evidence\s+act", "EVIDENCE"),
    (r"indian\s+contract\s+act|contract\s+act", "CONTRACT"),
    (r"narcotic\s+drugs\s+and\s+psychotropic\s+substances\s+act|n\.\s?d\.\s?p\.\s?s\.?\s+act|ndps\s+act", "NDPS"),
    (r"prevention\s+of\s+corruption\s+act", "PCA"),
    (r"motor\s+vehicles?\s+act", "MVACT"),
    (r"transfer\s+of\s+property\s+act", "TPACT"),
    (r"limitation\s+act", "LIMITATION"),
    (r"land\s+acquisition\s+act", "LAACT"),
    (r"industrial\s+disputes\s+act", "IDACT"),
    (r"companies\s+act", "COMPANIES"),
    (r"arbitration(?:\s+and\s+conciliation)?\s+act", "ARBITRATION"),
]
_ACT_RE = [(re.compile(a), c) for a, c in ACTS]
_ANY_ACT = "|".join(f"(?:{a})" for a, _ in ACTS)

_NUM = r"\d+[a-z]{0,2}(?:\(\w{1,3}\))*"
_SEC_MARK = r"(?:sections?|secs?\b\.?|ss\.|s\.|u/ss?\.?)"
_ART_MARK = r"(?:articles?|arts?\b\.?)"
_NUMLIST = rf"{_NUM}(?:\s*(?:,|/|&|\band\b|\bor\b)\s*{_NUM})*"
_MARKED = re.compile(rf"(?<![\w'])(?P<mark>{_SEC_MARK}|{_ART_MARK})\s*(?P<nums>{_NUMLIST})", re.I)
# numbers glued straight to an act name with no marker: "302/34 IPC"
_UNMARKED = re.compile(rf"(?<![\w./(])(?P<nums>{_NUM}(?:\s*/\s*{_NUM})+|{_NUM})\s+(?P<act>{_ANY_ACT})(?![\w])", re.I)
_AFTER = re.compile(rf"^[\s,;]*(?:(?:of|under|in|read\s+with)\s+)?(?:the\s+)?(?P<act>{_ANY_ACT})", re.I)
_BEFORE = re.compile(rf"(?P<act>{_ANY_ACT})[\s,;(]*$", re.I)
_UNKNOWN_ACT = re.compile(r"^[\s,;]*(?:of|under)\s+(?:the\s+)?(?P<name>(?:(?!the\b)[a-z&'-]+\s+){1,6}?act)\b", re.I)


def _code(act_text: str) -> Optional[str]:
    t = act_text.lower()
    for rx, code in _ACT_RE:
        if rx.fullmatch(t.strip()) or rx.match(t.strip()):
            return code
    return None


def _slug(name: str) -> str:
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w and w != "the" and not re.fullmatch(r"\d{4}", w)]
    return "_".join(w.upper() for w in words)


class RegexStatuteNormalizer:
    """Implements irlegal.common.interfaces.StatuteNormalizer."""

    def __init__(self, detail: bool = False):
        self.detail = detail

    def extract(self, text: str) -> Set[str]:
        low = text.lower()
        out: Set[str] = set()
        for m in _MARKED.finditer(low):
            is_art = m.group("mark").lower().startswith("art")
            nums = re.findall(_NUM, m.group("nums"))
            act = None
            after = _AFTER.match(low[m.end(): m.end() + 120])
            if after:
                act = _code(after.group("act"))
            if act is None:
                before = _BEFORE.search(low[max(0, m.start() - 70): m.start()])
                if before:
                    act = _code(before.group("act"))
            if act is None:
                unk = _UNKNOWN_ACT.match(low[m.end(): m.end() + 120])
                if unk:
                    act = _slug(unk.group("name"))
            if act is None and is_art:
                act = "CONST"
            if not act:
                continue
            for n in nums:
                base = re.match(r"\d+[a-z]{0,2}", n).group(0).upper()
                prefix = f"{act}_ART_" if is_art or act == "CONST" else f"{act}_"
                out.add(prefix + base)
                if self.detail and base != n.upper():
                    out.add(prefix + n.upper())
        for m in _UNMARKED.finditer(low):
            act = _code(m.group("act"))
            if act and act != "CONST":
                for n in re.findall(_NUM, m.group("nums")):
                    base = re.match(r"\d+[a-z]{0,2}", n).group(0).upper()
                    if len(base) <= 4:
                        out.add(f"{act}_{base}")
        return out


def provision_token(name: str, norm: Optional[RegexStatuteNormalizer] = None) -> Optional[str]:
    """Token for a statute-table row such as 'Section 302 of The Indian Penal Code, 1860' (None if unparseable)."""
    toks = (norm or RegexStatuteNormalizer()).extract(name)
    return next(iter(sorted(toks))) if len(toks) >= 1 else None


# ----------------------------------------------------------------------------- bridge

class StatuteBridge:
    """Provision retrieval from Facts+Issues text, and the doc-side provision sets / channel score.

    provisions: list of dicts {id, name, text (list[str])}
    pool_docs:  list of (doc_id, annotated_provision_ids, full_text, facts_issues_text)
    """

    def __init__(self, provisions, pool_docs, analyzer, enrich: bool = True, normalizer=None):
        from irlegal.common.schema import Case
        from irlegal.index.inverted import InvertedIndex
        from irlegal.ranking.bm25 import BM25Ranker

        self.norm = normalizer or RegexStatuteNormalizer()
        self.analyzer = analyzer
        self.prov_ids = [p["id"] for p in provisions]
        self.prov_row = {i: r for r, i in enumerate(self.prov_ids)}
        self.prov_token = [provision_token(p["name"], self.norm) for p in provisions]
        tok2rows: Dict[str, List[int]] = {}
        for r, t in enumerate(self.prov_token):
            if t:
                tok2rows.setdefault(t, []).append(r)
        # --- doc-side sets (as provision rows): annotation + normaliser tokens from the pool text
        n_prov = len(self.prov_ids)
        self.doc_ids = [d[0] for d in pool_docs]
        annotated, from_text = [], []
        for _, ann, full, _fi in pool_docs:
            a = {self.prov_row[i] for i in ann if i in self.prov_row}
            t = {r for tok in self.norm.extract(full) for r in tok2rows.get(tok, [])}
            annotated.append(a); from_text.append(t)
        rows, cols = [], []
        for di, (a, t) in enumerate(zip(annotated, from_text)):
            for r in a | t:
                rows.append(di); cols.append(r)
        self.doc_prov = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(pool_docs), n_prov))
        df = np.asarray(self.doc_prov.sum(axis=0)).ravel()
        self.idf = np.log((len(pool_docs) + 1.0) / (df + 1.0))
        self.coverage = {
            "pool_docs": len(pool_docs),
            "docs_with_annotation": sum(1 for a in annotated if a),
            "docs_with_normaliser_tokens": sum(1 for t in from_text if t),
            "docs_with_either": sum(1 for a, t in zip(annotated, from_text) if a or t),
            "docs_with_both_agree_overlap": sum(1 for a, t in zip(annotated, from_text) if a & t),
            "provisions_total": n_prov, "provisions_with_token": sum(1 for t in self.prov_token if t),
            "provisions_in_some_doc_set": int((df > 0).sum()),
            "mean_provisions_per_doc": round(float(np.asarray(self.doc_prov.sum(axis=1)).mean()), 3),
        }
        # --- provision pseudo-documents
        extra: Dict[int, List[str]] = {r: [] for r in range(n_prov)}
        if enrich:
            for (_, ann, _full, fi), a in zip(pool_docs, annotated):
                for r in a:
                    extra[r].append(fi)
        cases = [Case(doc_id=p["id"], title="", text="", zones={"other": [p["name"], *list(p["text"]), *extra[r]]})
                 for r, p in enumerate(provisions)]
        self.index = InvertedIndex.build(cases, analyzer)
        self._bm25 = BM25Ranker(self.index, analyzer, "all", k1=1.2, b=0.75, qtf_mode="saturated")
        self.enrich = enrich

    def predict(self, text: str, m: int):
        """Top-m (provision row, weight) from Facts+Issues text. weights sum to 1 over the m provisions."""
        from irlegal.common.schema import Query
        q = Query("stat", "stat", text, {}, set(), None, "val", set())
        s = self._bm25.score_all(q)
        top = np.argsort(-s, kind="stable")[:m]
        top = top[s[top] > 0]
        if top.size == 0:
            return [], np.zeros(0)
        return top.tolist(), s[top] / s[top].sum()

    def channel_vector(self, text: str, m: int) -> np.ndarray:
        """Dense weight vector over provisions: retrieval-score weight x provision idf."""
        v = np.zeros(len(self.prov_ids))
        rows, w = self.predict(text, m)
        for r, x in zip(rows, w):
            v[r] = x * self.idf[r]
        return v

    def channel_scores(self, texts: List[str], m: int) -> np.ndarray:
        """(n_queries x n_pool_docs): sum over predicted provisions held by the doc of weight x idf, / max idf."""
        V = sp.csr_matrix(np.stack([self.channel_vector(t, m) for t in texts]))
        return np.asarray((V @ self.doc_prov.T).todense()) / max(float(self.idf.max()), 1e-9)
