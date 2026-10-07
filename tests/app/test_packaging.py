"""The handoff zip ships results/ (aggregates only) and never data/, index blobs, databases, credentials or .env."""
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def names(tmp_path_factory):
    out = tmp_path_factory.mktemp("pkg") / "handoff.zip"
    r = subprocess.run(["bash", str(ROOT / "scripts" / "package_handoff.sh"), str(out)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-300:] + r.stderr[-300:]
    return zipfile.ZipFile(out).namelist()


def test_results_folder_is_in_the_zip(names):
    on_disk = [p for p in (ROOT / "results").rglob("*") if p.is_file() and p.suffix not in (".npz", ".npy", ".pkl", ".parquet")]
    in_zip = [n for n in names if n.startswith("results/") and not n.endswith("/")]
    assert len(in_zip) == len(on_disk)
    assert "results/dev_eval.json" in in_zip or not (ROOT / "results" / "dev_eval.json").exists()


def test_data_index_db_and_secrets_are_not_in_the_zip(names):
    assert not [n for n in names if n.startswith("data/")]
    bad = [n for n in names if n.endswith((".parquet", ".pkl", ".npz", ".npy", ".db", ".sqlite", ".vb", ".pem")) or "secret" in n.lower() or "credential" in n.lower()]
    assert not bad
    assert [n for n in names if n.rsplit("/", 1)[-1].startswith(".env")] in ([], [".env.example"])


def test_shipped_role_profile_has_no_stem_lists():
    p = ROOT / "results" / "role_profile.json"
    if p.exists():
        import json
        assert not [k for k in json.loads(p.read_text()) if k.startswith("distinctive_stems")]
