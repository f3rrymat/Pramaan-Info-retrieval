"""Phase G checks: product name, public landing endpoint (aggregates only), provenance, static wiring of the new pages.
Endpoint checks run against whatever results/ exists; without results the endpoints must say so and not invent anything."""
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.server import app

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "app" / "web"
H = {"X-Requested-With": "irl"}
c = TestClient(app)


def test_product_name_is_pramaan_in_user_visible_strings():
    for p in list(WEB.rglob("*.js")) + list(WEB.rglob("*.html")):
        assert "Precedent Finder" not in p.read_text(), f"old product name in {p.relative_to(ROOT)}"
    assert "<title>Pramaan</title>" in (WEB / "index.html").read_text()
    readme = (ROOT / "README.md").read_text()
    assert readme.startswith("# Pramaan") and "Pramaan: precedent finder for Indian law" in readme


def test_landing_is_public_and_has_no_case_text(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    r = c.get("/api/public/landing")
    assert r.status_code == 200
    d = r.json()
    assert "provenance" in d
    if not d["available"]:
        return
    blob = json.dumps({k: v for k, v in d.items() if k != "notes"})   # "notes" holds paper titles, which are bibliography not case titles
    for banned in ("snippet", "\"title\"", "judgment text"):
        assert banned not in blob
    assert len(d["examples"]) in (0, 3)
    for e in d["examples"]:
        assert set(e) == {"qid", "court", "year", "n_relevant", "systems"} and len(e["systems"]) == 3
        assert all(0 <= s["AP"] <= 1 for s in e["systems"])
    assert set(d["leakage"]).issubset({"config_A", "neighbour_alone", "authority_alone"})
    assert all(p["short"] for p in d["notes"]["papers"])


def test_provenance_lists_file_times_only():
    d = c.get("/api/public/provenance").json()
    assert set(d) >= {"files", "updated", "note"}
    for v in d["files"].values():
        assert re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d$", v)


def test_landing_route_and_assets_are_wired():
    router = (WEB / "ui" / "router.js").read_text()
    assert 'path: "/"' in router and "landing.js" in router
    assert (WEB / "fonts" / "LICENSE-fraunces.txt").exists() and (WEB / "fonts" / "fraunces-latin-wght-normal.woff2").exists()
    html = (WEB / "index.html").read_text()
    assert "pramaan.css" in html and "landing.css" in html
    css = (WEB / "styles" / "landing.css").read_text() + (WEB / "styles" / "pramaan.css").read_text()
    # motion rule (Phase G): no layout properties inside transitions
    for m in re.finditer(r"transition:\s*([^;]+);", css):
        assert not re.search(r"\b(width|height|top|left|margin|padding)\b", m.group(1).replace("min-width", "")), m.group(0)


def test_strategy_switcher_offers_only_real_rankers():
    js = (WEB / "ui" / "strategy.js").read_text()
    values = re.findall(r'value: "(\w+)", label', js)
    assert values == ["tfidf", "bm25", "ours", "ours_t", "boolean"]
    for banned in ("semantic", "dense", "neural", "simulated", "embedding"):
        assert banned not in js.lower()


def test_search_bar_never_puts_pasted_text_in_the_url_or_storage():
    sb = (WEB / "ui" / "searchbar.js").read_text()
    assert "localStorage" not in sb and "sessionStorage" not in sb and "location.hash" not in sb
    assert "AS.consented()" in sb and "configured" in sb          # the mic icon needs both the key and the consent


def test_search_results_keep_their_shape_and_gain_only_additive_meta(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    r = c.post("/api/search", json={"query_id": next(iter(c.get("/api/query_meta").json()["items"])), "ranker": "ours", "k": 3}, headers=H)
    assert r.status_code == 200
    d = r.json()
    assert {"ranker", "results"} <= set(d)
    for x in d["results"]:
        assert {"court", "date"} <= set(x["meta"])   # real mode adds "cited_by" (additive)
    assert "Server-Timing" in r.headers


def test_evaluation_page_shows_p_r_map_for_every_system_and_reads_only_the_api():
    js = (WEB / "ui" / "pages" / "evaluation.js").read_text()
    assert 'const COLS = ["P@5", "R@5", "P@10", "R@10", "P@20", "R@20", "MAP"' in js
    assert "Object.entries(r.macro)" in js                       # every system in the saved run, none added or removed
    for needle in ("/api/eval/summary", "/api/eval/ablation", "/api/eval/leakage", "/api/public/provenance", "What did not help", "Numbers come from saved runs on this machine"):
        assert needle in js
    assert not re.search(r"\b0\.\d{3}\b", js.replace("0.0001", "")), "a literal result number is typed in evaluation.js"


def test_every_metric_the_page_shows_exists_in_the_saved_run(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    r = c.get("/api/eval/summary")
    d = r.json() if r.status_code == 200 else {}
    if not d.get("available"):
        return
    for name, m in d["dev"]["macro"].items():
        for col in ("P@5", "R@5", "P@10", "R@10", "P@20", "R@20", "MAP"):
            assert col in m, (name, col)
