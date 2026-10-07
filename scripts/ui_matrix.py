"""Run scripts/ui_check.py for every page in light and dark at 1280 and 375 px; prints console errors, remote requests and overflow.
Dev-only (Playwright). Usage: python scripts/ui_matrix.py [--mode real|toy] [--role admin] [--shots]"""
import argparse, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="real"); ap.add_argument("--role", default="admin"); ap.add_argument("--shots", action="store_true"); a = ap.parse_args()
ROUTES = "#/search?q={QID}&run=1,#/compare?q={QID}&gold=1,#/querylab?q=murder /3 knife court:SC,#/saved,#/history,#/evaluation,#/efficiency,#/index?term=dowry,#/status,#/users,#/how,#/assistant,#/about,#/settings,#/styleguide"
total = 0
for theme, width in (("light", 1280), ("dark", 1280), ("light", 375), ("dark", 375)):
    cmd = [sys.executable, "scripts/ui_check.py", "--routes", ROUTES, "--role", a.role, "--mode", a.mode, "--theme", theme, "--width", str(width), "--prefix", "qa_", "--wait-for", ".page > *:not(.skel)", "--wait", "2000"] + (["--shots"] if a.shots else [])
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    try:
        d = json.loads(r.stdout[r.stdout.index("{"):])
    except Exception:
        print(theme, width, "FAILED", r.stderr[-400:]); continue
    bad = [(p["route"][:36], p["errors"][:2], p["scrollWidth"]) for p in d["pages"] if p["errors"] or p["horizontal_overflow"]]
    total += len(bad)
    print(f"{theme:5s} {width:5d}  pages {len(d['pages'])}  remote requests {d['remote_requests']}  problems {bad}")
print("pages with a console error or horizontal overflow:", total)
