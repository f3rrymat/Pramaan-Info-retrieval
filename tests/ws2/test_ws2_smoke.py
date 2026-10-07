"""WS2 tests live here (statute normaliser, parser, tolerant retrieval)."""
from irlegal.common.toy import ToyCorpus


def test_ws2_placeholder_statute_forms_present():
    # Varied statute spellings the normaliser must map to IPC_302, NIACT_138, ITACT1961_80IA, ...
    text = " ".join(c.text for c in ToyCorpus().cases())
    for form in ("Section 302 read with Section 34 IPC", "u/s 138", "Art. 21", "Sec. 80IA", "Section 80-IA"):
        assert form in text
