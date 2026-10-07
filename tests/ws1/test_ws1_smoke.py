"""WS1 tests live here (tokenizer, segmenter, index, codec round-trips)."""
from irlegal.common.toy import ToyCorpus


def test_ws1_placeholder_fixture_has_leaky_query_text():
    # The toy query cases contain <CITATION> and reporter citations on purpose,
    # so the real query_builder scrubber has something to remove.
    corpus = ToyCorpus()
    raw = corpus.get_case("QC-TR1").text
    assert "<CITATION>" in raw and "AIR 1985 SC 1461" in raw
