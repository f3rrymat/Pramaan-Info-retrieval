"""Loader mappings (DECISIONS section 2) and the gold-field rule (D4), on a tiny synthetic parquet set."""
import pandas as pd
import pytest

from irlegal.data.loader import IlPcsrCorpus, map_court, parse_date, role_to_zone, zones_from_paragraphs


def test_role_mapping():
    expect = {"Facts": "facts", "Issue": "issues", "Argument by Petitioner": "arguments",
              "Argument by Respondent": "arguments", "Court Reasoning": "reasoning",
              "Conclusion": "decision", "Statute Analysis": "statute_analysis",
              "Precedent Analysis": "precedent_analysis", "NONE": "other", "never-seen": "other",
              "Court Disclosure": "reasoning"}   # D12
    for role, zone in expect.items():
        assert role_to_zone(role) == zone


def test_court_mapping():
    assert map_court("Supreme Court of India") == "SC"
    assert map_court("Delhi High Court") == "HC"
    assert map_court("Jammu & Kashmir High Court - Srinagar Bench") == "HC"
    assert map_court("Delhi District Court") == "OTHER"
    assert map_court(None) is None and map_court("  ") is None


def test_date_parsing():
    assert parse_date("2017-01-24") == "2017-01-24"
    for bad in ("", "1995", None, "2017-13-45", float("nan")):
        assert parse_date(bad) is None


def test_zones_from_paragraphs_groups_by_zone():
    z = zones_from_paragraphs(["a", "b", "c"], ["Argument by Petitioner", "Facts", "Argument by Respondent"])
    assert z == {"arguments": ["a", "c"], "facts": ["b"]}


def _row(i, rel, text=("Facts para", "Issue para", "Decision para"),
         roles=("Facts", "Issue", "Conclusion"), jur="Supreme Court of India"):
    return dict(id=i, case_title="T " + i, date="2000-01-02", jurisdiction=jur, text=list(text),
                rhetorical_roles=list(roles), relevant_statutes=["Sec 302 IPC"], relevant_statute_ids=["99"],
                relevant_precedents=["x"], relevant_precedent_ids=list(rel))


@pytest.fixture
def corpus(tmp_path):
    pd.DataFrame([_row("P1", []), _row("P2", ["P1"], jur="Delhi High Court")]).to_parquet(tmp_path / "precedent_candidates.parquet")
    for name in ("train", "dev", "test"):
        pd.DataFrame([_row(f"{name}1", ["P1", "P2"])]).to_parquet(tmp_path / f"{name}_queries.parquet")
    return IlPcsrCorpus(str(tmp_path))


def test_pool_cases(corpus):
    cases = {c.doc_id: c for c in corpus.cases()}
    assert set(cases) == {"P1", "P2"}
    assert cases["P2"].court == "HC" and cases["P2"].cites_out == ["P1"]
    assert cases["P1"].zones["decision"] == ["Decision para"]
    assert cases["P1"].statutes == set()          # gold statute fields are not read (D4)


def test_queries_are_facts_issues_only_and_gold_is_label_only(corpus):
    q = corpus.queries("val")[0]
    assert q.split == "val" and q.text == "Facts para Issue para"
    assert "Decision" not in q.text
    assert q.relevant == {"P1", "P2"}
    assert q.statutes == set()                     # D4: never from gold
    full = corpus.queries("val", view="full")[0]
    assert "Decision para" in full.text
    assert corpus.queries("dev") is corpus.queries("dev")   # alias, cached


def test_train_indegree(corpus):
    assert corpus.train_indegree() == {"P1": 1, "P2": 1}
