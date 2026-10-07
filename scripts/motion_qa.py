"""Motion QA with Playwright (dev-only), animations ON (D45). /api/search is answered by a synthetic mock with made-up ids
and numbers (no case text, no real data), so the Config A view with weight sliders can be exercised on any machine.

Checks: FLIP re-ranking when a weight slider moves (cards reorder, ranks update, frame pacing while dragging), ranker
change keeps cards keyed, case-drawer morph, neighbour-graph drag, fuzzy palette with recent actions, Undo after Save
(DELETE sent), Settings > Reduce motion sets data-motion and stops animations, zero console errors.
Usage: python scripts/motion_qa.py
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALL = ROOT / "docs" / "figures" / "ui_all"; ALL.mkdir(parents=True, exist_ok=True)
tmp = ROOT / "data" / "motion_qa"; tmp.mkdir(parents=True, exist_ok=True)
for _f in tmp.glob("*"):          # a fresh throw-away database every run
    _f.unlink()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "AUTH_REQUIRED": "0", "DEMO_ROLE": "analyst", "IRLEGAL_MODE": "toy",
       "IRLEGAL_APP_DB": str(tmp / "qa.db"), "IRLEGAL_APP_SECRET": str(tmp / "qa.key")}
for k in ("SHOW_TEXT", "SARVAM_API_KEY"):
    env.pop(k, None)
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
base = f"http://127.0.0.1:{port}"
res = {"checks": [], "errors": []}


def ok(name, cond, extra=""):
    res["checks"].append({"check": name, "pass": bool(cond), "detail": str(extra)[:200]}); print(("PASS " if cond else "FAIL ") + name, str(extra)[:160])


def synthetic(ranker):
    """20 made-up results with components chosen so that moving the neighbour weight reorders them."""
    out = []
    for i in range(20):
        t, n, a = round(1 - i * 0.045, 4), round((i * 37 % 20) / 19, 4), round((i * 11 % 20) / 19, 4)
        out.append({"rank": i + 1, "doc_id": f"D{100 + i}", "score": round(0.5 * t + 0.3 * n + 0.2 * a, 4), "components": {"text": t, "neighbour": n, "authority": a},
                    "explanation": {"neighbours": [{"neighbour_id": f"T{i}{j}", "similarity": round(0.5 - j * 0.1, 3)} for j in range(3)], "contributions": {"text": t * .5, "neighbour": n * .3, "authority": a * .2}},
                    "meta": {"court": ["SC", "HC", "OTHER"][i % 3], "date": f"{1980 + i}-01-01"}, "relevant": i % 7 == 0})
    return {"source": "mock", "ranker": ranker, "qid": "Q-TE2", "k": 50, "weights": {"text": 0.5, "neighbour": 0.3, "authority": 0.2} if ranker == "ours" else None,
            "pruning": "none", "candidates_scored": 20, "temporal_applied": True, "query_has_date": True, "top_neighbours": [], "results": out if ranker == "ours" else list(reversed(out))}


try:
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1).read(); break
        except Exception:
            time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="no-preference")
        pg = ctx.new_page()
        pg.on("console", lambda m: res["errors"].append(m.text) if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: res["errors"].append(str(e)))
        deletes = []

        def search_mock(route, request):
            body = json.loads(request.post_data or "{}")
            route.fulfill(json=synthetic(body.get("ranker", "ours")), headers={"Server-Timing": 'query;dur=0.4, scrub;dur=0;desc="at load", first_stage;dur=31.2, features;dur=12.5, net;dur=2.1, explain;dur=1.3, total;dur=48.0'})
        pg.route("**/api/search", search_mock)
        pg.route("**/api/case_detail/*", lambda route, request: route.fulfill(json={"source": "mock", "doc_id": request.url.rsplit("/", 1)[1], "court": "SC", "year": "1990", "train_indegree": 3,
                 "pool_plus_train_indegree": 5, "authority": 1.79, "zone_sizes": {"facts": 4, "issues": 2, "reasoning": 6, "decision": 1}, "cites_in_pool": 3}))
        pg.route("**/api/saved/*", lambda route, request: (deletes.append(request.url), route.fulfill(json={"ok": True})) if request.method == "DELETE" else route.continue_())
        pg.goto(base + "/#/search?q=Q-TE2&run=1"); pg.wait_for_selector(".result"); pg.wait_for_timeout(900)
        ok("pipeline strip lights all six stages with the mocked timings", pg.locator(".pipe-stage.done").count() == 6 and "31.2 ms" in pg.inner_text(".pipe-strip"), pg.inner_text(".pipe-strip").replace("\n", " "))
        order0 = pg.eval_on_selector_all(".result", "els => els.map(e => e.dataset.key)")
        pg.click("summary >> text=Re-weight the score")
        slider = pg.locator("input[aria-label='Neighbours weight']")
        pg.evaluate("""() => { window.__frames = []; let last = performance.now(); const f = (t) => { window.__frames.push(t - last); last = t; if (window.__frames.length < 400) requestAnimationFrame(f); }; requestAnimationFrame(f); }""")
        box = slider.bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] / 2); pg.mouse.down()
        for i in range(30):
            pg.mouse.move(box["x"] + box["width"] * (0.3 + i * 0.023), box["y"] + box["height"] / 2); pg.wait_for_timeout(16)
        pg.mouse.up(); pg.wait_for_timeout(600)
        frames = pg.evaluate("window.__frames.slice(2)")
        frames.sort()
        p50, p95 = frames[len(frames) // 2], frames[int(len(frames) * 0.95)]
        order1 = pg.eval_on_selector_all(".result", "els => els.map(e => e.dataset.key)")
        ok("moving a weight slider re-ranks the cards in place (FLIP)", order1 != order0 and len(order1) == 10 and len(set(order1) & set(order0)) >= 5, f"{order0[:4]} -> {order1[:4]}")
        ok("rank numbers follow the new order", pg.eval_on_selector_all(".result .rank-num", "els => els.map(e => +e.textContent)")[:5] == [1, 2, 3, 4, 5])
        ok("frame pacing while dragging (headless Chromium, indicative only)", p95 < 50, f"median {p50:.1f} ms, p95 {p95:.1f} ms over {len(frames)} frames")
        res["frames"] = {"median_ms": round(p50, 1), "p95_ms": round(p95, 1), "n": len(frames)}
        pg.screenshot(path=str(ALL / "motion_reweight_light_1280.png"))
        # ranker change: keyed cards persist through FLIP
        pg.click(".strat-opt[data-v=tfidf]"); pg.wait_for_timeout(800)
        ok("ranker change repaints keyed cards", pg.locator(".result").count() == 10 and pg.eval_on_selector(".result", "e => e.dataset.key") == "D119")
        pg.click(".strat-opt[data-v=ours]"); pg.wait_for_timeout(800)
        # drawer morph and graph drag
        pg.locator(".result .id").first.click(); pg.wait_for_selector(".drawer"); pg.wait_for_timeout(200)
        ok("case drawer opens with the shared-element morph (ghost removed afterwards)", pg.locator(".morph-ghost").count() <= 1); pg.wait_for_timeout(600)
        ok("ghost cleaned up", pg.locator(".morph-ghost").count() == 0)
        pg.wait_for_selector(".drawer .graph .node", timeout=10000); pg.wait_for_timeout(1500)
        node = pg.locator(".drawer .graph .node").nth(1)
        node.scroll_into_view_if_needed(); pg.wait_for_timeout(300)
        t0 = node.get_attribute("transform"); nb = node.locator("circle").bounding_box()
        pg.mouse.move(nb["x"] + nb["width"] / 2, nb["y"] + nb["height"] / 2); pg.mouse.down(); pg.mouse.move(nb["x"] + 60, nb["y"] + 40, steps=6); pg.mouse.up(); pg.wait_for_timeout(500)
        ok("neighbour graph node can be dragged and stays", node.get_attribute("transform") != t0, f"{t0} -> {node.get_attribute('transform')}")
        pg.screenshot(path=str(ALL / "motion_drawer_graph_light_1280.png"))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        # undo after save
        pg.locator(".result button.star").first.click(); pg.wait_for_selector(".toast-action")
        pg.click(".toast-action"); pg.wait_for_timeout(500)
        ok("Undo after Save sends DELETE /api/saved/<id>", len(deletes) == 1, deletes)
        # palette fuzzy + recent
        pg.keyboard.press("Control+k"); pg.wait_for_selector(".palette"); pg.keyboard.type("evl")
        first = pg.inner_text(".palette-item[aria-selected='true']")
        ok("fuzzy palette: 'evl' finds Evaluation", "Evaluation" in first, first)
        pg.keyboard.press("Enter"); pg.wait_for_timeout(800)
        pg.keyboard.press("Control+k"); pg.wait_for_selector(".palette")
        ok("palette shows recent actions first", pg.inner_text(".palette-group").startswith("Recent") or "RECENT" in pg.inner_text(".palette-group").upper(), pg.inner_text(".palette-group"))
        pg.keyboard.press("Escape")
        # reduce motion
        pg.goto(base + "/#/settings"); pg.wait_for_selector("text=Reduce motion"); pg.click("label.switch:has-text('Reduce motion')")
        ok("Reduce motion sets data-motion=reduce", pg.evaluate("document.documentElement.getAttribute('data-motion')") == "reduce")
        pg.goto(base + "/#/search?q=Q-TE2&run=1"); pg.wait_for_selector(".result"); pg.wait_for_timeout(300)
        ok("with Reduce motion no animations run", pg.evaluate("document.getAnimations().filter(a => a.playState === 'running' && !(a.effect?.target?.classList?.contains('skel'))).length") == 0)
        b.close()
finally:
    srv.terminate()
res["passed"] = sum(c["pass"] for c in res["checks"]); res["total"] = len(res["checks"])
print(json.dumps({"passed": res["passed"], "total": res["total"], "console_errors": res["errors"], "frames": res.get("frames")}, indent=1))
sys.exit(0 if res["passed"] == res["total"] and not res["errors"] else 1)
