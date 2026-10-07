"""Parser and evaluator on a small hand-built index (positions exist for facts and issues only)."""
import pytest

from irlegal.common.schema import Case
from irlegal.index.inverted import InvertedIndex
from irlegal.preprocess.normalizer import Analyzer
from irlegal.query import boolean as B
from irlegal.query.parser import And, Filter, Not, Or, Phrase, Prox, QuerySyntaxError, Term, parse, to_tree

AN = Analyzer()


def _case(i, court, date, **zones):
    return Case(doc_id=i, title="", text="", court=court, date=date, zones={z: [t] for z, t in zones.items()})


CASES = [
    _case("A", "SC", "1990-05-01", facts="the accused committed murder with a knife", issues="whether the burden of proof was discharged", decision="appeal dismissed"),
    _case("B", "HC", "2005-03-03", facts="murder trial witness turned hostile", issues="whether dowry death is proved", reasoning="murder charge fails"),
    _case("C", "SC", "2012-07-07", facts="land acquisition compensation awarded", issues="whether compensation is adequate", decision="appeal allowed"),
    _case("D", "OTHER", None, facts="knife attack and murder near market", issues="proof of intention"),
]
INDEX = InvertedIndex.build(CASES, AN)


def S(strategy="df_order"):
    return B.BooleanSearcher(INDEX, AN, strategy)


def ids(q, strategy="df_order"):
    r = S(strategy).search(q)
    return [INDEX.doc_ids()[d] for d in r.docs]


def test_parse_tree_shapes():
    assert parse("a b") == And((Term("a"), Term("b")))
    assert parse("a OR b AND c") == Or((Term("a"), And((Term("b"), Term("c")))))
    assert parse("NOT a") == Not(Term("a"))
    assert parse('"burden of proof"') == Phrase("burden of proof")
    assert parse("murder /5 knife") == Prox(Term("murder"), Term("knife"), 5, False)
    assert parse("murder pre/3 knife") == Prox(Term("murder"), Term("knife"), 3, True)
    assert parse("facts:murder") == Term("murder", "facts")
    assert parse('issues:"burden proof"') == Phrase("burden proof", "issues")
    assert parse("court:SC year:1990..2000") == And((Filter("court", "SC"), Filter("year", "1990..2000")))
    assert parse("(a OR b) c").children[0] == Or((Term("a"), Term("b")))
    assert to_tree(parse("a AND NOT b"))["children"][1]["op"] == "NOT"


@pytest.mark.parametrize("bad", ["", "(a", "a)", "AND", "murder /5", "nofield:x y:", "a OR"])
def test_syntax_errors(bad):
    with pytest.raises(QuerySyntaxError):
        parse(bad)


def test_boolean_operators():
    assert ids("murder") == ["A", "B", "D"]
    assert ids("murder AND knife") == ["A", "D"]
    assert ids("murder knife") == ["A", "D"]                       # implicit AND
    assert ids("knife OR compensation") == ["A", "C", "D"]
    assert ids("murder AND NOT knife") == ["B"]
    assert ids("NOT murder") == ["C"]
    assert ids("(knife OR dowry) AND murder") == ["A", "B", "D"]
    assert ids("zzzzz") == []


def test_stop_words_are_ignored_not_fatal():
    assert ids("the murder") == ["A", "B", "D"]
    r = S().search("the of")
    assert len(r.docs) == 4 and any("only stop words" in t for t in r.trace)


def test_zone_restriction():
    assert ids("facts:murder") == ["A", "B", "D"]
    assert ids("reasoning:murder") == ["B"]
    assert ids("decision:murder") == []
    assert ids("issues:dowry") == ["B"]


def test_phrase_and_stop_word_gap():
    assert ids('"burden of proof"') == ["A"]                       # stop word dropped on both sides
    assert ids('"proof burden"') == []                             # order matters
    assert ids('"murder knife"') == ["A"]                          # "with a" removed, so the stems are adjacent
    assert ids('"knife murder"') == []
    assert ids('issues:"burden proof"') == ["A"]
    assert ids('"dowry death"') == ["B"]
    assert ids('"compensation awarded"') == ["C"]
    assert ids('"awarded compensation"') == []
    assert ids('facts:"land acquisition"') == ["C"]


def test_proximity():
    assert ids("murder /1 knife") == ["A"]
    assert ids("murder /2 knife") == ["A", "D"]
    assert ids("knife pre/2 murder") == ["D"]
    assert ids("murder pre/1 knife") == ["A"]
    assert ids("knife pre/1 murder") == []                         # ordered: knife must come first, and in A it does not
    assert ids('"dowry death" /3 proved') == ["B"]
    assert ids("murder /0 knife") == []


def test_phrase_in_a_zone_without_positions_falls_back_and_says_so():
    r = S().search('decision:"appeal dismissed"')
    assert [INDEX.doc_ids()[d] for d in r.docs] == ["A"]
    assert any("keeps no positions" in t for t in r.trace)


def test_wildcards_in_queries():
    assert ids("murd*") == ["A", "B", "D"]
    assert ids("acquis*") == ["C"]                                 # the dictionary holds stems: acquisition -> acquisit
    assert ids("compens*") == ["C"] and ids("compens* AND NOT adequate") == []
    assert ids("xyz*") == []


def test_date_and_court_filters():
    assert ids("court:SC") == ["A", "C"]
    assert ids("murder court:HC") == ["B"]
    assert ids("year:1990..2005") == ["A", "B"]
    assert ids("year:>=2000") == ["B", "C"]
    assert ids("before:2000-01-01") == ["A"]
    assert ids("after:2000-01-01") == ["B", "C"]                    # D has no date: never matches a date filter
    assert ids("murder year:2005") == ["B"]
    with pytest.raises(QuerySyntaxError):
        S().search("before:yesterday")


def test_and_strategies_agree_and_df_order_never_costs_more_here():
    for q in ("murder knife proof", "murder AND knife AND market", "knife AND murder AND attack AND near"):
        assert ids(q, "input_order") == ids(q, "df_order")
    b = B.benchmark_and(S, ["murder knife proof", "murder knife market attack", "murder witness trial"], repeats=1)
    assert b["input_order"]["total_hits"] == b["df_order"]["total_hits"]
    assert b["df_order"]["comparisons"] <= b["input_order"]["comparisons"]


def test_ranking_orders_matches_by_tfidf():
    s = S()
    r = s.search("murder")
    ranked = s.rank(r, "murder", k=3)
    assert {d for d, _ in ranked} == {"A", "B", "D"}
    assert [x for _, x in ranked] == sorted([x for _, x in ranked], reverse=True)
