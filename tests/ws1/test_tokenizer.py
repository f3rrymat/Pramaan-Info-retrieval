from irlegal.preprocess.normalizer import Analyzer
from irlegal.preprocess.tokenizer import tokenize


def test_statute_references_stay_intact():
    assert tokenize("S.302") == ["s.302"]
    assert tokenize("Art. 21") == ["art.21"]
    assert tokenize("Section 302(1)(a) IPC") == ["s.302(1)(a)", "ipc"]
    assert tokenize("u/s 482") == ["s.482"]
    assert tokenize("Article 14 and Sec. 5") == ["art.14", "and", "s.5"]


def test_not_everything_is_a_section():
    assert tokenize("the court's 5 judges") == ["the", "court", "5", "judges"]
    assert tokenize("The Supreme Court said so") == ["the", "supreme", "court", "said", "so"]


def test_case_folding_and_possessive():
    assert tokenize("Hon'ble Court's ORDER") == ["hon'ble", "court", "order"]


def test_analyzer_stopwords_stemming_placeholders():
    a = Analyzer()
    assert a.analyze("The accused were convicted under Section 302") == ["accus", "convict", "s.302"]
    assert a.analyze("[ENTITY] filed [SECTION] petition") == ["file", "petit"]
    assert Analyzer(stem=False).analyze("convicted") == ["convicted"]
