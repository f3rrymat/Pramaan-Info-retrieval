"""Dev-only UI verification with Playwright (requirements/dev.txt): visits pages, records console errors and failed requests,
checks for horizontal overflow and remote requests, and saves screenshots to docs/figures/ui/ (no case text: SHOW_TEXT is off).

Usage: python scripts/ui_check.py --routes "#/search,#/styleguide" --role admin --mode real --theme light --width 1280 --shots
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
ap = argparse.ArgumentParser()
ap.add_argument("--routes", default="#/search")
ap.add_argument("--role", default="admin")
ap.add_argument("--mode", default="real", choices=["real", "toy"])
ap.add_argument("--auth", default="0")
ap.add_argument("--theme", default="light")
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--height", type=int, default=860)
ap.add_argument("--shots", action="store_true")
ap.add_argument("--full", action="store_true")
ap.add_argument("--prefix", default="")
ap.add_argument("--wait", type=int, default=900)
ap.add_argument("--wait-for", default="", help="CSS selector to wait for (60 s)")
ap.add_argument("--script", default="", help="JS evaluated after load, per route")
a = ap.parse_args()

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "AUTH_REQUIRED": a.auth, "DEMO_ROLE": a.role, "IRLEGAL_MODE": a.mode, "IRLEGAL_APP_DB": str(ROOT / "data" / "ui_check.db"), "IRLEGAL_APP_SECRET": str(ROOT / "data" / "ui_check.key")}
env.pop("SHOW_TEXT", None)
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
base = f"http://127.0.0.1:{port}"
try:
    import urllib.request
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1).read(); break
        except Exception:
            time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    report = []
    out = ROOT / "docs" / "figures" / "ui_all"; out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": a.width, "height": a.height}, color_scheme=a.theme, reduced_motion="reduce")
        page = ctx.new_page()
        errors, remote = [], []
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url}"))
        page.on("request", lambda r: remote.append(r.url) if not r.url.startswith(base) and not r.url.startswith("data:") else None)
        page.on("response", lambda r: errors.append(f"http {r.status}: {r.url}") if r.status >= 400 and "/api/auth/me" not in r.url else None)
        import urllib.request as ur
        try:
            qid = json.load(ur.urlopen(base + "/api/queries", timeout=120))["queries"][0]["qid"]
        except Exception:
            qid = "Q-TE2"
        for route in [r.replace("{QID}", qid) for r in a.routes.split(",")]:
            errors.clear()
            page.goto(base + "/" + route, wait_until="networkidle")
            if a.wait_for:
                try:
                    page.wait_for_selector(a.wait_for, timeout=60000)
                except Exception as e:
                    errors.append(f"wait_for failed: {a.wait_for}")
            page.wait_for_timeout(a.wait)
            if a.script:
                page.evaluate(a.script); page.wait_for_timeout(a.wait)
            ov = page.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
            rep = {"route": route, "errors": list(errors), "horizontal_overflow": ov["sw"] > ov["cw"] + 1, "scrollWidth": ov["sw"], "clientWidth": ov["cw"], "title": page.title()}
            if a.shots:
                name = f"{a.prefix}{route.strip('#/').replace('/', '_').replace('?', '_').replace('=', '-').replace('&', '_')[:40] or 'home'}_{a.theme}_{a.width}.png"
                page.screenshot(path=str(out / name), full_page=a.full); rep["shot"] = name
            report.append(rep)
        b.close()
    print(json.dumps({"base": "local", "remote_requests": sorted(set(remote)), "pages": report}, indent=1))
finally:
    srv.terminate()
    try:
        err = srv.stderr.read().decode()[-1500:]
        if "Traceback" in err:
            print("SERVER STDERR:", err)
    except Exception:
        pass
