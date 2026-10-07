"""Phase F static and contract checks: no inline script (CSP), the browser never names Sarvam, motion switch, research
notes are well-formed data, the README generator builds the six new sections in order, /api/search keeps its JSON shape
and adds only a Server-Timing header."""
import re
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.server import app

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "app" / "web"
H = {"X-Requested-With": "irl"}


def test_no_inline_scripts_and_browser_never_calls_sarvam():
    html = (WEB / "index.html").read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> would be blocked by the CSP"
    for p in WEB.rglob("*.js"):
        assert "sarvam.ai" not in p.read_text().lower(), f"{p.name} must not talk to Sarvam; the server does"
    assert "SARVAM_API_KEY" not in "".join(p.read_text() for p in WEB.rglob("*.js") if p.name != "panel.js")


def test_reduce_motion_switch_is_wired():
    css = (WEB / "styles" / "motion.css").read_text()
    assert ':root[data-motion="reduce"]' in css and "animation-duration: .01ms" in css
    dom = (WEB / "ui" / "dom.js").read_text()
    assert 'getAttribute("data-motion") === "reduce"' in dom and "prefers-reduced-motion" in dom
    assert "reduceMotion" in (WEB / "ui" / "boot.js").read_text()


def test_research_notes_are_well_formed():
    notes = (ROOT / "docs" / "research_notes.md").read_text()
    papers = re.split(r"(?m)^### ", notes.split("## Papers", 1)[1].split("\n## ", 1)[0])[1:]
    assert len(papers) >= 10
    for p in papers:
        status = re.search(r"(?m)^- status: (.*)$", p).group(1)
        assert status.startswith(("VERIFIED", "RE-CHECK")), status[:40]
        for k in ("citation", "short", "did", "take", "differ"):
            assert re.search(rf"(?m)^- {k}: .+$", p), (p[:30], k)
    table = notes.split("## IR concepts", 1)[1].split("\n## ", 1)[0]
    for row in [l for l in table.splitlines() if l.startswith("| ") and not l.startswith("| Concept")]:
        for path in re.findall(r"`([^`]+)`", row.split("|")[3]):
            assert (ROOT / path).exists(), path


def test_readme_generator_builds_sections_in_order(tmp_path):
    out = tmp_path / "README.md"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_readme.py"), "--out", str(out)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-400:]
    text = out.read_text()
    order = ["## Research background", "## Our contributions", "## IR concepts and where they live", "## Screenshots", "## Limitations and negative results", "## How the assistant works and what it sends to a third party"]
    pos = [text.index(t) for t in order]
    assert pos == sorted(pos)
    assert "{" not in text.split("## Our contributions", 1)[1].split("## IR concepts", 1)[0]     # every placeholder was filled
    assert "Mehta" not in text and "Paul, Ghumare" in text


def test_search_json_shape_unchanged_and_server_timing_added():
    c = TestClient(app)
    r = c.post("/api/search", json={"query_id": "Q-TE2", "k": 5}, headers=H)
    assert r.status_code == 200 and set(r.json()) == {"source", "ranker", "qid", "results"}           # toy shape, as before Phase F
    st = r.headers["server-timing"]
    assert st.startswith("query;dur=") and "explain;dur=" in st and "total;dur=" in st
