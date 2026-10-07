"""Shared lazy state for the real-data routers (files starting with "_" are not routers). Owner: WS3/WS4.

Mode: "real" when data/index and results/config_a_frozen.json exist, else "toy" (tests and fresh clones).
Force toy with IRLEGAL_MODE=toy. Case titles and text snippets are returned only when SHOW_TEXT=1 (D11).
"""
import json
import os
import threading
from pathlib import Path
from typing import Optional

from irlegal.common.config import load_config, repo_path

SNIPPET_CHARS = 200
_lock = threading.Lock()
_ctx = None


def show_text() -> bool:
    return os.environ.get("SHOW_TEXT") == "1"


def mode() -> str:
    if os.environ.get("IRLEGAL_MODE", "").lower() == "toy":
        return "toy"
    cfg = load_config()["paths"]
    ok = repo_path(cfg["index_dir"], "meta.json").exists() and repo_path(cfg["results_dir"], "config_a_frozen.json").exists()
    return "real" if ok else "toy"


def results_file(name: str) -> Optional[dict]:
    p = repo_path(load_config()["paths"]["results_dir"], name)
    return json.loads(p.read_text()) if p.exists() else None


def ctx():
    """The heavy pipeline context, built on first use (several seconds)."""
    global _ctx
    with _lock:
        if _ctx is None:
            from irlegal.ranking.pipeline import Context
            _ctx = Context()
        return _ctx


def clip(text: str) -> str:
    t = " ".join(text.split())
    return t[:SNIPPET_CHARS] + ("…" if len(t) > SNIPPET_CHARS else "")


class Light:
    """Index + query machinery without the heavy ranking context (parser, Boolean search, suggestions)."""

    def __init__(self):
        from irlegal.index.inverted import InvertedIndex
        from irlegal.preprocess.normalizer import Analyzer
        from irlegal.query.boolean import BooleanSearcher
        from irlegal.query.tolerant import KGramIndex, SoundexIndex, SpellCorrector
        self.mode = mode()
        self.an = Analyzer()
        if self.mode == "toy":
            from irlegal.common.toy import ToyCorpus
            corpus = ToyCorpus()
            self.cases = {c.doc_id: c for c in corpus.cases()}
            self.index = InvertedIndex.build(list(self.cases.values()), self.an)
        else:
            self.index = InvertedIndex.load(repo_path(load_config()["paths"]["index_dir"]))
            self.cases = None                        # loaded only when SHOW_TEXT=1
        self.searchers = {s: BooleanSearcher(self.index, self.an, s) for s in ("df_order", "input_order")}
        vocab = list(self.index.terms("all"))
        self.kg = KGramIndex(vocab)
        self.df = {t: self.index.df(t, "all") for t in vocab}
        self.spell = SpellCorrector(self.kg, self.df)
        self.soundex = SoundexIndex(vocab)

    def case(self, doc_id: str):
        if self.cases is None:
            from irlegal.data.loader import IlPcsrCorpus
            self.cases = {c.doc_id: c for c in IlPcsrCorpus().cases()}
        return self.cases.get(doc_id)


_light = None


def light() -> Light:
    global _light
    with _lock:
        if _light is None or _light.mode != mode():
            _light = Light()
        return _light
