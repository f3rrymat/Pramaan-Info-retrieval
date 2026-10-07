import re
from pathlib import Path

import pytest

from irlegal.evaluation import leakage

SRC = Path(leakage.__file__)


def test_audit_refuses_the_test_split():
    with pytest.raises(ValueError):
        leakage._split("test")
    assert leakage.ALLOWED_SPLITS == ("train", "val")
    assert leakage._split("val") == "val"


def test_audit_source_never_requests_the_test_split():
    src = SRC.read_text()
    assert not re.search(r"queries\(\s*[\"']test", src)
    assert not re.search(r"relevant_ids\(\s*[\"']test", src)
    # the only mentions of 'test' are the guard text and docs
    code_lines = [l for l in src.splitlines() if "test" in l.lower() and not l.strip().startswith(("#", '"', "'"))]
    assert all("_split" in l or "ALLOWED" in l or "raise" in l or "refuses" in l or "test_" in l for l in code_lines), code_lines
