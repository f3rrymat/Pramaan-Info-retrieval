"""Sign-in and role QA with Playwright (dev-only). Starts the server with AUTH_REQUIRED=1 and a throw-away database,
checks validation, wrong password, the three roles (different navigation and accent colour), sign-out and expired-session
handling, collects console errors, and saves screenshots (no case text: SHOW_TEXT is off).
Usage: python scripts/ui_qa.py [--mode real|toy]
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="real"); a = ap.parse_args()
tmp = ROOT / "data" / "ui_qa"; tmp.mkdir(parents=True, exist_ok=True)
for f in tmp.glob("*"): f.unlink()
os.environ.update({"IRLEGAL_APP_DB": str(tmp / "qa.db"), "IRLEGAL_APP_SECRET": str(tmp / "qa.key")})
from app import security as sec  # noqa: E402
con = sec.connect(); PW = {}
for name in ("researcher", "analyst", "admin"):
    PW[name] = f"qa-{name}-pass-1234"
    con.execute("INSERT INTO users (username, role, pw_hash, created_at) VALUES (?,?,?,?)", (name, name, sec.hash_password(PW[name]), time.time()))
con.commit()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "AUTH_REQUIRED": "1", "IRLEGAL_MODE": a.mode}; env.pop("SHOW_TEXT", None)
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
base = f"http://127.0.0.1:{port}"; out = ROOT / "docs" / "figures" / "ui_all"; out.mkdir(parents=True, exist_ok=True)
res = {"checks": [], "unexpected_console_errors": [], "expected_console_errors": []}
def ok(name, cond, extra=""):
    res["checks"].append({"check": name, "pass": bool(cond), "detail": extra}); print(("PASS " if cond else "FAIL ") + name, extra)
try:
    import urllib.request
    for _ in range(120):
        try: urllib.request.urlopen(base + "/api/health", timeout=1).read(); break
        except Exception: time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        navs, accents = {}, {}
        def new(theme="light", w=1280):
            ctx = b.new_context(viewport={"width": w, "height": 860}, color_scheme=theme, reduced_motion="reduce"); pg = ctx.new_page(); errs = []
            def on_console(m):
                if m.type in ("error", "warning"):
                    (res["expected_console_errors"] if ("status of 401" in m.text or "status of 403" in m.text) else res["unexpected_console_errors"]).append(m.text)   # 401s and the deliberate researcher -> /api/eval 403 probe
            pg.on("console", on_console); pg.on("pageerror", lambda e: res["unexpected_console_errors"].append(str(e)))
            pg.on("requestfailed", lambda r: res["unexpected_console_errors"].append("requestfailed " + r.url))
            return ctx, pg
        ctx, pg = new()
        pg.goto(base + "/"); pg.wait_for_selector(".hero"); ok("anonymous visitor lands on the public overview (Phase G)", pg.locator(".hero-h").count() == 1 and "#/signin" not in pg.url, pg.url)
        pg.click(".lnav >> text=Sign in"); pg.wait_for_selector(".signin"); ok("the overview's Sign in button opens the sign-in page", "#/signin" in pg.url, pg.url)
        pg.wait_for_timeout(800); pg.screenshot(path=str(out / "signin_light_1280.png"))
        ok("sign-in shows headline numbers from saved runs", pg.locator(".hero-stat .v").count() >= 1 or a.mode == "toy")
        pg.click("button[type=submit]"); ok("empty form shows validation errors", pg.locator(".field-error").count() == 2)
        pg.fill("input[name=username]", "researcher"); pg.fill("input[name=password]", "wrong"); pg.click("button[type=submit]"); pg.wait_for_selector(".alert.err")
        ok("wrong password gives a generic error", "Invalid username or password" in pg.inner_text(".alert.err"))
        ok("password is not in the page text", "wrong" not in pg.inner_text("body"))
        for role in ("researcher", "analyst", "admin"):
            ctx2, pg2 = new()
            pg2.goto(base + "/#/signin"); pg2.wait_for_selector(".signin")
            pg2.fill("input[name=username]", role); pg2.fill("input[name=password]", PW[role]); pg2.click("button[type=submit]")
            pg2.wait_for_selector(".sidebar", timeout=60000); pg2.wait_for_timeout(1200)
            navs[role] = pg2.eval_on_selector_all(".nav-link", "els => els.map(e => e.textContent.replace(/[A-Z] [A-Z]$/, '').trim())")
            accents[role] = pg2.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--role').trim()")
            ok(f"{role} lands on its own start page", {"researcher": "#/search", "analyst": "#/evaluation", "admin": "#/status"}[role] in pg2.url, pg2.url)
            pg2.screenshot(path=str(out / f"role_{role}_light_1280.png"))
            ck = ctx2.cookies(); c = [x for x in ck if x["name"] == sec.COOKIE]
            ok(f"{role}: session cookie is HttpOnly and SameSite=Lax", c and c[0]["httpOnly"] and c[0]["sameSite"] == "Lax")
            ok(f"{role}: cookie is not readable from JavaScript", sec.COOKIE not in pg2.evaluate("document.cookie"))
            if role == "researcher":
                pg2.goto(base + "/#/evaluation"); pg2.wait_for_timeout(800)
                ok("researcher cannot open Evaluation (role page)", "not part of your role" in pg2.inner_text("#page"))
                r = pg2.evaluate("fetch('/api/eval/summary').then(r => r.status)"); ok("researcher gets 403 from the evaluation API", r == 403, str(r))
                pg2.goto(base + "/#/search"); pg2.wait_for_timeout(500)
                pg2.keyboard.press("Control+k"); pg2.wait_for_selector(".palette"); ok("command palette opens with Ctrl+K", True); pg2.screenshot(path=str(out / "palette_light_1280.png")); pg2.keyboard.press("Escape")
                pg2.keyboard.press("?"); pg2.wait_for_selector(".modal"); ok("shortcut sheet opens with ?", "Command palette" in pg2.inner_text(".modal")); pg2.keyboard.press("Escape")
                # expired session (Phase G): drop the cookie, trigger an API call; a sign-in dialog opens over the page, which keeps its state
                ctx2.clear_cookies(); pg2.evaluate("location.hash = '#/history'"); before = pg2.url
                pg2.wait_for_selector(".session-modal", timeout=15000); ok("lost session opens a sign-in dialog over the page", pg2.locator(".sidebar").count() == 1 and pg2.url == before, pg2.url)
                pg2.fill(".session-modal input[aria-label=Password]", PW[role]); pg2.click(".session-modal button[type=submit]"); pg2.wait_for_selector(".session-modal", state="detached", timeout=15000)
                ok("signing in again from the dialog keeps the page and the user", pg2.url == before and pg2.locator(".sidebar").count() == 1, pg2.url)
                ctx2.clear_cookies(); pg2.evaluate("location.hash = '#/saved'"); pg2.wait_for_selector(".session-modal", timeout=15000)
                pg2.click(".session-modal >> text=Go to the sign-in page"); pg2.wait_for_selector(".signin", timeout=15000); ok("'Go to the sign-in page' sends the user to sign-in", "#/signin" in pg2.url, pg2.url)
            if role == "admin":
                pg2.click("button[title='Account menu']"); pg2.click("text=Sign out"); pg2.wait_for_selector(".hero"); ok("sign out returns to the public overview", pg2.locator(".hero-h").count() == 1 and "#/signin" not in pg2.url, pg2.url)
                r = pg2.evaluate("fetch('/api/system/status').then(r => r.status)"); ok("after sign-out the admin API answers 401", r == 401, str(r))
            ctx2.close()
        ok("navigation differs by role", len({tuple(v) for v in navs.values()}) == 3, json.dumps({k: len(v) for k, v in navs.items()}))
        ok("accent colour differs by role", len(set(accents.values())) == 3, json.dumps(accents))
        res["navigation"] = navs; res["accents"] = accents
        for theme, w, nm in (("dark", 1280, "signin_dark_1280"), ("light", 375, "signin_light_375")):
            c3, p3 = new(theme, w); p3.goto(base + "/#/signin"); p3.wait_for_selector(".signin"); p3.wait_for_timeout(800)
            ov = p3.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"); ok(f"sign-in has no horizontal overflow ({nm})", not ov)
            p3.screenshot(path=str(out / f"{nm}.png")); c3.close()
        b.close()
finally:
    srv.terminate()
# ---------------------------------------------------------------- quick sign-in (local demo flag) on a second server
s2 = socket.socket(); s2.bind(("127.0.0.1", 0)); port2 = s2.getsockname()[1]; s2.close()
srv2 = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port2), "--log-level", "warning"], cwd=ROOT, env={**env, "DEMO_QUICK_LOGIN": "1"}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
base2 = f"http://127.0.0.1:{port2}"
try:
    for _ in range(120):
        try: urllib.request.urlopen(base2 + "/api/health", timeout=1).read(); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as p2:
        b2 = p2.chromium.launch()
        for role in ("researcher", "analyst", "admin"):
            cx = b2.new_context(viewport={"width": 1280, "height": 860}, color_scheme="light", reduced_motion="reduce"); pq = cx.new_page()
            pq.on("console", lambda m: res["unexpected_console_errors"].append(m.text) if m.type in ("error", "warning") and "status of 40" not in m.text else None)
            pq.goto(base2 + "/#/signin"); pq.wait_for_selector(".role-card")
            ok(f"quick login ({role}): three role cards, password form hidden", pq.locator(".role-card").count() == 3 and not pq.locator("input[name=username]").is_visible())
            if role == "researcher":
                pq.screenshot(path=str(out / "signin_quick_light_1280.png"))
                pq.click("text=Use a password instead"); ok("'Use a password instead' reveals the form", pq.locator("input[name=username]").is_visible()); pq.click("text=Hide the password form")
            pq.locator(".role-card", has_text={"researcher": "Researcher", "analyst": "Analyst", "admin": "Admin"}[role]).first.click()
            pq.wait_for_selector(".sidebar", timeout=60000); pq.wait_for_timeout(600)
            ok(f"quick login ({role}) lands on Search", "#/search" in pq.url, pq.url)
            ev = pq.evaluate("fetch('/api/eval/summary').then(r => r.status)")
            ok(f"quick login ({role}): evaluation API status matches the role", ev == (403 if role == "researcher" else 200), str(ev))
            if role == "researcher":
                pq.goto(base2 + "/#/evaluation"); pq.wait_for_timeout(700); ok("quick-login researcher still cannot open the Evaluation page", "not part of your role" in pq.inner_text("#page"))
            cx.close()
        # without the flag the cards never appear and the endpoint is 404 (a third server, flag unset)
        s3 = socket.socket(); s3.bind(("127.0.0.1", 0)); port3 = s3.getsockname()[1]; s3.close()
        srv3 = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port3), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        base3 = f"http://127.0.0.1:{port3}"
        for _ in range(120):
            try: urllib.request.urlopen(base3 + "/api/health", timeout=1).read(); break
            except Exception: time.sleep(0.5)
        cx = b2.new_context(); pg = cx.new_page(); pg.goto(base3 + "/#/signin"); pg.wait_for_selector(".signin"); ok("flag off: no role cards", pg.locator(".role-card").count() == 0)
        ok("flag off: quick endpoint is 404", pg.evaluate("fetch('/api/auth/quick', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'irl'}, body: JSON.stringify({role: 'admin'})}).then(r => r.status)") == 404)
        b2.close(); srv3.terminate()
finally:
    srv2.terminate()
res["passed"] = sum(c["pass"] for c in res["checks"]); res["total"] = len(res["checks"])
print(json.dumps({k: res[k] for k in ("passed", "total", "unexpected_console_errors", "expected_console_errors")}, indent=1))
