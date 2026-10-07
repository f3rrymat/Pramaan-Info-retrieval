"""Static checks on the front end: offline, tokens-only styling, every module import resolves, fonts and licences present."""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "app" / "web"


def _files(*suffixes):
    return [p for p in WEB.rglob("*") if p.is_file() and p.suffix in suffixes]


def test_no_remote_urls_in_the_front_end():
    pat = re.compile(r"https?://(?!www\.w3\.org)")
    for p in _files(".js", ".css", ".html"):
        text = p.read_text()
        if p.name.endswith("markdown") or p.name == "components.js":
            text = text.replace("/^https?:/.test(url)", "")       # the About page only links to https URLs the README already contains
        for m in pat.finditer(text):
            line = text[: m.start()].count("\n") + 1
            raise AssertionError(f"remote URL in {p.relative_to(WEB)}:{line}")


def test_colours_are_only_defined_in_tokens_css():
    hexc = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    for p in (WEB / "styles").glob("*.css"):
        if p.name == "tokens.css":
            continue
        assert not hexc.search(p.read_text()), f"hard-coded colour in {p.name}"


def test_every_module_import_resolves():
    imp = re.compile(r"(?:from|import\()\s*[\"'](/[^\"']+\.js)[\"']")
    for p in (WEB / "ui").rglob("*.js"):
        for target in imp.findall(p.read_text()):
            assert (WEB / target.lstrip("/")).exists(), f"{p.relative_to(WEB)} imports missing {target}"
    routes = re.findall(r"import\(\"(/ui/pages/[^\"]+)\"\)", (WEB / "ui" / "router.js").read_text())
    assert routes and all((WEB / r.lstrip("/")).exists() for r in routes)


def test_fonts_are_self_hosted_with_licences():
    for f in ("inter-latin-wght-normal.woff2", "jetbrains-mono-latin-wght-normal.woff2", "LICENSE-inter.txt", "LICENSE-jetbrains-mono.txt"):
        assert (WEB / "fonts" / f).exists()
    css = (WEB / "styles" / "tokens.css").read_text()
    assert "/fonts/inter-latin-wght-normal.woff2" in css and "@import" not in css


def test_zone_palette_has_seven_zones_in_both_themes():
    css = (WEB / "styles" / "tokens.css").read_text()
    for z in ("facts", "issues", "arguments", "reasoning", "decision", "statute_analysis", "precedent_analysis"):
        assert css.count(f"--z-{z}:") >= 3                           # light, dark, and the system-dark media block


def test_index_html_has_no_framework_or_cdn_and_reduced_motion_is_honoured():
    html = (WEB / "index.html").read_text()
    assert 'type="module" src="/ui/main.js"' in html and "cdn" not in html.lower()
    assert "prefers-reduced-motion" in (WEB / "styles" / "tokens.css").read_text() + (WEB / "styles" / "base.css").read_text()


def test_legacy_front_end_files_are_gone():
    for gone in ("app.js", "styles.css", "panels", "vendor"):
        assert not (WEB / gone).exists(), gone
