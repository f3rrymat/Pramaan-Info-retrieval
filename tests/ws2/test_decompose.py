import pytest

from irlegal.query.decompose import decompose, rrf, split_issues


def test_rrf_hand_computed():
    out = dict(rrf([["a", "b", "c"], ["b", "c", "a"]], k=60))
    assert out["a"] == pytest.approx(1 / 61 + 1 / 63)
    assert out["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert out["c"] == pytest.approx(1 / 63 + 1 / 62)
    assert [d for d, _ in rrf([["a", "b", "c"], ["b", "c", "a"]])] == ["b", "a", "c"]
    assert rrf([]) == [] and [d for d, _ in rrf([["x"], ["y"], ["x"]])] == ["x", "y"]


def test_split_on_whether_numbering_and_sentences():
    t = ("Whether the accused can be convicted solely on the testimony of a hostile witness in the case. "
         "Whether the delay in lodging the first information report is fatal to the prosecution case against him.")
    assert len(split_issues(t)) == 2 and split_issues(t)[0].startswith("Whether the accused")
    n = "(i) Whether the sale deed executed by the minor is void or voidable under the contract act. (ii) Whether limitation bars the suit filed after twelve years."
    assert len(split_issues(n)) == 2
    assert split_issues("") == [] and decompose(None or "") == []


def test_short_fragments_are_merged_not_dropped():
    s = split_issues("Is it so? Whether the appellant is entitled to compensation under the motor vehicles act for the injuries suffered.")
    assert len(s) == 1 and "Is it so?" in s[0]
    assert split_issues("Bail?") == ["Bail?"]
