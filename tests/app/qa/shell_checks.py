"""Shell behaviour checks (dev-only, Playwright): progress bar on a slow request, nav indicator glide, offline banner with retry, still-loading hint,
notification history, account menu role badge, command palette actions, landing -> sign-in role preselect. Prints PASS/FAIL lines."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import server, sign_in  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

fails = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra)
    if not cond:
        fails.append(name)


with server() as base, sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 860})
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") and "net::ERR" not in m.text and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    # landing -> role card -> sign-in with the role preselected
    pg.goto(base + "/"); pg.wait_for_selector(".role-tile")
    pg.hover(".role-tile >> nth=1"); pg.click(".role-tile >> nth=1 >> text=Continue as Analyst"); pg.wait_for_selector(".signin")
    ok("role card on the overview opens sign-in with that role selected", "role=analyst" in pg.url and pg.locator(".role-card.selected[data-role=analyst]").count() == 1, pg.url)
    pg.locator(".role-card[data-role=analyst]").click(); pg.wait_for_selector(".sidebar", timeout=60000)
    ok("analyst lands on Evaluation after quick sign-in via the card", True)
    # nav indicator glides
    pg.goto(base + "/#/evaluation"); pg.wait_for_selector(".nav-link[aria-current=page]"); pg.wait_for_timeout(400)
    t1 = pg.evaluate("getComputedStyle(document.querySelector('.nav-ind')).transform")
    pg.click(".nav-link[data-path='/search']"); pg.wait_for_timeout(500)
    t2 = pg.evaluate("getComputedStyle(document.querySelector('.nav-ind')).transform")
    ok("navigation indicator moves to the active item", t1 != t2, f"{t1} -> {t2}")
    # progress bar on a slow request
    pg.route("**/api/queries", lambda r: (time.sleep(0.9), r.continue_()))
    pg.evaluate("location.hash = '#/compare'")
    pg.wait_for_selector(".netbar.on", state="attached", timeout=3000); ok("progress bar shows while a request is in flight", True)
    pg.wait_for_selector(".netbar.on", state="detached", timeout=15000); ok("progress bar hides when requests finish", True)
    pg.unroute("**/api/queries")
    # still-loading hint after 2 s
    pg.route("**/api/queries", lambda r: (time.sleep(2.6), r.continue_()))
    pg.evaluate("location.hash = '#/search'")
    pg.wait_for_selector(".still-loading", timeout=6000); ok("'still loading' hint appears after 2 s", True)
    pg.wait_for_selector(".qbar-input", timeout=20000); pg.unroute("**/api/queries")
    # notification history
    pg.fill(".qbar-input", "135524194"); pg.keyboard.press("Enter"); pg.wait_for_selector(".result", timeout=60000)
    pg.click(".icon-btn.star >> nth=0"); pg.wait_for_selector(".toast")
    pg.click("button[aria-label=Notifications]"); pg.wait_for_selector(".notes-modal")
    ok("notification history lists the save message", "saved" in pg.inner_text(".notes-modal").lower()); pg.keyboard.press("Escape")
    # account menu role badge
    pg.click("button[title='Account menu']"); ok("account menu shows the role badge", "Analyst" in pg.inner_text(".menu-head")); pg.keyboard.press("Escape")
    # palette actions
    pg.keyboard.press("Control+k"); pg.wait_for_selector(".palette-item"); txt = pg.inner_text(".palette")
    ok("palette lists pages, actions and a random dev query action", "Go to Search" in txt and "Toggle light" in txt and "random dev query" in txt, txt[:200].replace("\n", "|")); pg.keyboard.press("Escape")
    # offline banner and retry
    pg.route("**/api/**", lambda r: r.abort())
    pg.evaluate("location.hash = '#/history'")
    pg.wait_for_selector(".offline-banner", timeout=10000); ok("stopped server shows a retry banner", "not reachable" in pg.inner_text(".offline-banner"))
    ok("status chip says Offline", "Offline" in pg.inner_text(".mode-chip"))
    pg.unroute("**/api/**"); pg.click(".offline-banner >> text=Retry now")
    pg.wait_for_selector(".offline-banner", state="detached", timeout=15000); ok("banner clears when the server answers again", True)
    ok("status chip is back to a data mode", "Offline" not in pg.inner_text(".mode-chip"))
    ok("no unexpected console errors", not errs, str(errs[:3]))
    b.close()
print("FAILED:" if fails else "ALL PASSED", fails)
sys.exit(1 if fails else 0)
