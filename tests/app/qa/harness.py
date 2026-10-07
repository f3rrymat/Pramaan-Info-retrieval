"""Shared helper for the Phase G browser checks (dev-only, Playwright). Starts the app on a free port with a throw-away user database
and quick sign-in enabled, so no credentials are read or printed. Not collected by pytest (no test_ prefix)."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def server(auth=True, quick=True, mode="real", show_text=False):
    tmp = ROOT / "data" / "qa_g"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*"):
        f.unlink()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "AUTH_REQUIRED": "1" if auth else "0", "IRLEGAL_MODE": mode,
           "IRLEGAL_APP_DB": str(tmp / "qa.db"), "IRLEGAL_APP_SECRET": str(tmp / "qa.key")}
    env.pop("SHOW_TEXT", None)
    if show_text:
        env["SHOW_TEXT"] = "1"
    if quick:
        env["DEMO_QUICK_LOGIN"] = "1"
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(240):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1).read()
                break
            except Exception:
                time.sleep(0.5)
        yield base
    finally:
        srv.terminate()


def sign_in(page, base, role="admin", landing="/search"):
    """Quick sign-in through the role card (the flag is on in `server()`), then wait for the shell."""
    page.goto(base + "/#/signin")
    page.wait_for_selector(".role-card")
    page.locator(".role-card", has_text=role.capitalize()).first.click()
    page.wait_for_selector(".sidebar", timeout=60000)
    if landing:
        page.goto(base + "/#" + landing)
