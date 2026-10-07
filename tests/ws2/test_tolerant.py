import pytest

from irlegal.query.tolerant import KGramIndex, SoundexIndex, SpellCorrector, edit_distance, kgrams, soundex

VOCAB = ["cat", "catch", "category", "cattle", "act", "action", "nation", "notion", "motion", "convict", "convention", "murder", "murderer", "mother", "dowri"]


def test_kgrams_use_boundary_markers():
    assert kgrams("cat") == {"$ca", "cat", "at$"}


def test_wildcards():
    kg = KGramIndex(VOCAB)
    assert kg.wildcard("cat*") == ["cat", "catch", "category", "cattle"]
    assert kg.wildcard("*tion") == ["action", "convention", "motion", "nation", "notion"]
    assert kg.wildcard("con*ion") == ["convention"]
    assert kg.wildcard("mur*er") == ["murder", "murderer"]
    assert kg.wildcard("m*r") == ["mother", "murder", "murderer"]            # pieces shorter than a gram fall back to a scan
    assert kg.wildcard("zzz*") == []
    assert kg.wildcard("act") == ["act"] and kg.wildcard("nope") == []


def test_wildcard_matches_a_brute_force_scan():
    import re
    kg = KGramIndex(VOCAB)
    for pat in ("c*t", "*er", "*o*", "mo*n", "ca*gory"):
        rx = re.compile("^" + ".*".join(map(re.escape, pat.split("*"))) + "$")
        assert kg.wildcard(pat) == sorted(t for t in VOCAB if rx.match(t))


def test_edit_distance():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3 and edit_distance("same", "same") == 0
    assert edit_distance("murdar", "murder") == 1
    assert edit_distance("abcdef", "uvwxyz", max_d=2) == 3          # early exit above the bound


def test_spelling_suggestions_ranked_by_distance_then_df():
    kg = KGramIndex(VOCAB)
    sc = SpellCorrector(kg, {"murder": 50, "murderer": 5, "mother": 90})
    s = sc.suggest("murdar")
    assert s[0]["term"] == "murder" and s[0]["edit_distance"] == 1
    assert sc.suggest("murder") == []                                  # already in the dictionary
    assert sc.suggest("xqzvw") == []


@pytest.mark.parametrize("a,b", [("Robert", "Rupert"), ("Gopalan", "Gopalen"), ("Sharma", "Sarma"), ("Smith", "Smyth")])
def test_soundex_variants_share_a_code(a, b):
    assert soundex(a) == soundex(b)


def test_soundex_known_codes():
    assert soundex("Robert") == "R163" and soundex("Rupert") == "R163"
    assert soundex("Ashcraft") == "A261" and soundex("Tymczak") == "T522" and soundex("Pfister") == "P236"
    assert soundex("") == ""
    idx = SoundexIndex(["gopalan", "gopalen", "kumar", "gopal"])
    assert idx.similar("Gopalan") == ["gopalan", "gopalen"]
