"""Normalisation: case folding (in the tokenizer), stop words, Porter stemming. Owner: WS1.

Stop words are our own list (no nltk downloads): a general English list plus a short
list of legal boilerplate. Only the Porter stemmer comes from nltk (utility, no data files).
"""
import re
from typing import Dict, List

from nltk.stem.porter import PorterStemmer

from .tokenizer import is_reference_token, tokenize

ENGLISH_STOP = frozenset("""
a about above after again against all am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further
had has have having he her here hers herself him himself his how i if in into is it its itself
me more most my myself no nor not of off on once only or other our ours ourselves out over own
same she should so some such than that the their theirs them themselves then there these they
this those through to too under until up very was we were what when where which while who whom
why will with would you your yours yourself yourselves also may shall upon thus hence
""".split())

LEGAL_STOP = frozenset("""
aforesaid hereinafter herein hereto hereby thereof thereto thereby therein whereas whereof
hon'ble honble hon ble ld sd learned said versus vs
""".split())

STOPWORDS = ENGLISH_STOP | LEGAL_STOP
MAX_TOKEN_LEN = 40
# The dataset masks entities in the text: "[ENTITY]", "[SECTION]", "[ACT]", "[PRECEDENT]" ...
# They carry no content, so they are removed before tokenising.
_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z_ ]{2,20}\]")


class Analyzer:
    """text -> list of index terms (tokenise, drop stop words, stem). Caches stems."""

    def __init__(self, stem: bool = True, stopwords=STOPWORDS):
        self.stem = stem
        self.stopwords = stopwords
        self._stemmer = PorterStemmer()
        self._cache: Dict[str, str] = {}

    def _norm(self, tok: str) -> str:
        r = self._cache.get(tok)
        if r is None:
            if self.stem and tok.isalpha() and len(tok) > 3:
                r = self._stemmer.stem(tok)
            else:
                r = tok
            self._cache[tok] = r
        return r

    def analyze(self, text: str) -> List[str]:
        out = []
        for tok in tokenize(_PLACEHOLDER.sub(" ", text)):
            if len(tok) < 2 or len(tok) > MAX_TOKEN_LEN or tok in self.stopwords:
                continue
            out.append(tok if is_reference_token(tok) else self._norm(tok))
        return out
