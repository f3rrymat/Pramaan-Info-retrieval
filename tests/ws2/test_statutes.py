"""Statute normaliser variants, and the D13/D4 guard: query gold statute fields never reach a ranker."""
import re
from pathlib import Path

import pandas as pd
import pytest

from irlegal.common.interfaces import StatuteNormalizer
from irlegal.query.statutes import RegexStatuteNormalizer, StatuteBridge, provision_token

N = RegexStatuteNormalizer()


@pytest.mark.parametrize("text,want", [
    ("Section 302 of the Indian Penal Code", {"IPC_302"}),
    ("Sec. 302 IPC", {"IPC_302"}),
    ("S. 302 I.P.C.", {"IPC_302"}),
    ("s.302 IPC", {"IPC_302"}),
    ("u/s 302 IPC", {"IPC_302"}),
    ("Sections 302 and 304 IPC", {"IPC_302", "IPC_304"}),
    ("Sections 302/34 IPC", {"IPC_302", "IPC_34"}),
    ("convicted under 302/34 IPC", {"IPC_302", "IPC_34"}),
    ("IPC Section 420", {"IPC_420"}),
    ("Cr.P.C. Section 161", {"CRPC_161"}),
    ("Section 482 of the Code of Criminal Procedure, 1973", {"CRPC_482"}),
    ("Section 9 of the Code of Civil Procedure", {"CPC_9"}),
    ("Art. 21 of the Constitution", {"CONST_ART_21"}),
    ("Article 14 and 19", {"CONST_ART_14", "CONST_ART_19"}),
    ("Sec 80IA of the Income-tax Act, 1961", {"ITACT_80IA"}),
    ("Section 138 of the Negotiable Instruments Act", {"NIACT_138"}),
    ("Section 3 of The Manipur Municipalities Act, 1994", {"MANIPUR_MUNICIPALITIES_ACT_3"}),
    ("Section 302(1)(a) IPC", {"IPC_302"}),
    ("section 5 of the Act", set()),                      # act unknown: no token
    ("the court's 5 judges, Section 9 only", set()),
    ("no statute here", set()),
])
def test_variants(text, want):
    assert N.extract(text) == want


def test_detail_option_and_protocol():
    assert RegexStatuteNormalizer(detail=True).extract("Section 302(1)(a) IPC") == {"IPC_302", "IPC_302(1)(A)"}
    assert isinstance(N, StatuteNormalizer)


def test_provision_token_from_table_names():
    assert provision_token("Section 302 of The Indian Penal Code, 1860") == "IPC_302"
    assert provision_token("Article 233 of The Constitution Of India, 1949") == "CONST_ART_233"
    assert provision_token("Section 144 of The Code Of Criminal Procedure, 1973") == "CRPC_144"


# ------------------------------------------------------------------ gold statutes never reach a ranker
SRC = Path(__file__).resolve().parents[2] / "src" / "irlegal"
ALLOWED = {"data/loader.py", "evaluation/statute_eval.py"}      # pool doc-side annotation / evaluation labels


def test_gold_statute_fields_only_referenced_in_allowed_modules():
    offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py")
                 if "relevant_statute" in p.read_text() and str(p.relative_to(SRC)) not in ALLOWED]
    assert offenders == []


def test_loader_never_reads_query_gold_statutes():
    from irlegal.data import loader
    assert not any("statute" in c for c in loader._QUERY_COLS)


def _row(i, statutes):
    return dict(id=i, case_title="T", date="2000-01-02", jurisdiction="Supreme Court of India",
                text=["theft of a bicycle", "whether theft proved"], rhetorical_roles=["Facts", "Issue"],
                relevant_statutes=["x"], relevant_statute_ids=statutes, relevant_precedents=[], relevant_precedent_ids=["P1"])


def test_changing_query_gold_statutes_changes_no_ranker_input(tmp_path):
    """Two corpora identical except for the QUERY gold statute columns -> identical queries and channel."""
    import numpy as np
    from irlegal.data.loader import IlPcsrCorpus
    from irlegal.preprocess.normalizer import Analyzer

    outs = []
    for tag, gold in (("a", ["S1"]), ("b", ["S2"])):
        d = tmp_path / tag
        d.mkdir()
        pd.DataFrame([_row("P1", ["S1"]), _row("P2", ["S2"])]).to_parquet(d / "precedent_candidates.parquet")
        for sp in ("train", "dev", "test"):
            pd.DataFrame([_row(f"{sp}1", gold)]).to_parquet(d / f"{sp}_queries.parquet")
        pd.DataFrame([{"id": "S1", "provision_name": "Section 378 of The Indian Penal Code, 1860", "text": ["theft"]},
                      {"id": "S2", "provision_name": "Section 420 of The Indian Penal Code, 1860", "text": ["cheating"]}]
                     ).to_parquet(d / "statute_candidates.parquet")
        c = IlPcsrCorpus(str(d))
        q = c.queries("val")[0]
        assert q.statutes == set()
        pool = [(x.doc_id, c.pool_statute_ids()[x.doc_id], x.text, x.text) for x in c.cases()]
        bridge = StatuteBridge(c.statutes(), pool, Analyzer())
        outs.append((q.text, q.statutes, q.zones, bridge.channel_scores([q.text], 2)))
    assert outs[0][:3] == outs[1][:3]
    assert np.array_equal(outs[0][3], outs[1][3])
