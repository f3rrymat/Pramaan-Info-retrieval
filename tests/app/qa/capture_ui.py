"""Capture the curated README screenshots into docs/figures/ui/ (dev-only, Playwright). SHOW_TEXT is off and no assistant key is set,
so no case text and no key can appear. Usage: python tests/app/qa/capture_ui.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import ROOT, server, sign_in  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = ROOT / "docs" / "figures" / "ui"
OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*.png"):
    f.unlink()
Q = "135524194"
with server() as base, sync_playwright() as p:
    b = p.chromium.launch()
    def page(theme="light", w=1280, h=860):
        ctx = b.new_context(viewport={"width": w, "height": h}, color_scheme=theme); return ctx, ctx.new_page()
    # public pages
    for theme in ("light", "dark"):
        ctx, pg = page(theme)
        pg.goto(base + "/"); pg.wait_for_selector(".proof-cell"); pg.wait_for_timeout(1800); pg.screenshot(path=str(OUT / f"landing_{theme}.png"))
        if theme == "light":
            pg.evaluate("document.querySelector('#sec-evidence').scrollIntoView()"); pg.wait_for_timeout(1600); pg.screenshot(path=str(OUT / "landing_evidence_light.png"))
        pg.goto(base + "/#/signin"); pg.wait_for_selector(".role-card"); pg.wait_for_timeout(700); pg.screenshot(path=str(OUT / f"signin_{theme}.png")); ctx.close()
    # researcher flows
    for theme in ("light", "dark"):
        ctx, pg = page(theme)
        sign_in(pg, base, "researcher", f"/search?q={Q}&run=1"); pg.wait_for_selector(".result", timeout=60000); pg.wait_for_timeout(1200)
        pg.screenshot(path=str(OUT / f"search_{theme}.png"))
        if theme == "light":
            pg.click(".apill"); pg.wait_for_timeout(500); pg.locator(".chip-btn >> text=Case record").first.click(); pg.wait_for_timeout(1000); pg.screenshot(path=str(OUT / "search_pipeline_record_light.png"))
            pg.locator(".result .id").first.click(); pg.wait_for_selector(".drawer"); pg.wait_for_timeout(1200); pg.screenshot(path=str(OUT / "case_drawer_light.png")); pg.keyboard.press("Escape")
            pg.goto(base + f"/#/compare?q={Q}&gold=1"); pg.wait_for_selector(".rp-item", timeout=60000); pg.wait_for_timeout(800); pg.locator(".rp").scroll_into_view_if_needed()
            pg.evaluate("(()=>{const r=document.querySelector('.rp-range'); r.value=1000; r.dispatchEvent(new Event('input',{bubbles:true}));})()"); pg.wait_for_timeout(500); pg.screenshot(path=str(OUT / "compare_light.png"))
            pg.goto(base + "/#/how"); pg.wait_for_selector(".story"); pg.evaluate("document.querySelector('#step-s3').scrollIntoView({block:'center'})"); pg.wait_for_timeout(900); pg.screenshot(path=str(OUT / "how_it_works_light.png"))
            pg.keyboard.press("Alt+a"); pg.wait_for_selector(".as-panel"); pg.wait_for_timeout(900); pg.screenshot(path=str(OUT / "assistant_panel_light.png"))
        ctx.close()
    # analyst / admin pages
    for theme in ("light", "dark"):
        ctx, pg = page(theme)
        sign_in(pg, base, "analyst", "/evaluation"); pg.wait_for_selector(".eval-table", timeout=60000); pg.wait_for_timeout(1500); pg.screenshot(path=str(OUT / f"evaluation_{theme}.png"))
        if theme == "light":
            for _ in range(5): pg.click(".stepper .btn >> text=Next step")
            pg.locator(".story-tile").scroll_into_view_if_needed(); pg.wait_for_timeout(900); pg.screenshot(path=str(OUT / "evaluation_story_light.png"))
            pg.goto(base + "/#/efficiency"); pg.wait_for_selector(".explorer", timeout=60000); pg.wait_for_timeout(900)
            box = pg.locator(".explorer").bounding_box(); pg.mouse.move(box["x"] + box["width"] * .45, box["y"] + box["height"] * .5); pg.mouse.down(); pg.mouse.move(box["x"] + box["width"] * .55, box["y"] + box["height"] * .4); pg.mouse.up()
            pg.locator(".explorer").scroll_into_view_if_needed(); pg.wait_for_timeout(500); pg.screenshot(path=str(OUT / "efficiency_light.png"))
        ctx.close()
    ctx, pg = page("light")
    sign_in(pg, base, "admin", "/index?term=dowry&and=murder"); pg.wait_for_selector(".pblock", timeout=60000); pg.wait_for_timeout(1500); pg.screenshot(path=str(OUT / "index_inspector_light.png")); ctx.close()
    b.close()
print(sorted(f.name for f in OUT.glob("*.png")))
