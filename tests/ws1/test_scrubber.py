from irlegal.data.query_builder import QueryBuilder, scrub_citations


def test_reporter_citations_removed_and_counted():
    t = "See AIR 1973 SC 1461, (2005) 3 SCC 112, 1961 (3) SCR 123 and 2005 (4) SCALE 12 here."
    clean, c = scrub_citations(t)
    for frag in ("AIR", "SCC", "SCR", "SCALE", "1461", "112"):
        assert frag not in clean
    assert c["AIR"] == 1 and c["SCC"] == 1 and c["SCR"] == 1 and c["SCALE"] == 1
    assert clean.startswith("See") and clean.endswith("here.")


def test_party_pair_with_year_removed():
    clean, c = scrub_citations("In State of Punjab v. Ram Singh (1990) the court held. Also Kesavananda v. State of Kerala, 1973 held.")
    assert "Punjab" not in clean and "Kesavananda" not in clean
    assert c["party_pair_year"] == 2


def test_innocent_text_untouched():
    t = "The air was clean. Section 302 of the Code applied in 1994 to the accused."
    clean, c = scrub_citations(t)
    assert clean == t and sum(c.values()) == 0


def test_placeholder_token_removed():
    clean, c = scrub_citations("as held in <CITATION> the rule")
    assert "CITATION" not in clean and c["placeholder"] == 1


def test_builder_counts_and_uses_only_facts_issues():
    b = QueryBuilder()
    q = b.build("q1", {"facts": ["Fact AIR 1950 SC 27."], "issues": ["Whether x?"], "reasoning": ["secret"]},
                "2001-01-01", "val", ["d1"])
    assert q.text == "Fact . Whether x?" and "secret" not in q.text
    assert b.scrub_stats["AIR"] == 1 and q.statutes == set() and q.relevant == {"d1"}
    empty = b.build("q2", {"reasoning": ["only reasoning"]}, None, "val", [])
    assert empty.text == "" and b.n_empty == 1
