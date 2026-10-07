"""Phase G quality gates (dev-only, Playwright). Not collected by pytest.

For every page, at 375, 768, 1280 and 1920 px in light and dark: console errors (deliberate 401/403 listed separately), remote requests,
horizontal overflow, case text in API responses (SHOW_TEXT is off, so no title/snippet may appear), contrast (WCAG AA, computed in the page),
keyboard order (focus visible, no trap, skip link first), CLS and long tasks during route changes. Results go to docs/figures/ui_all/gates.json.

Usage: python tests/app/qa/final_gates.py [--quick] [--widths 375,768,1280,1920] [--no-contrast]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import ROOT, server, sign_in  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--quick", action="store_true")
ap.add_argument("--widths", default="375,768,1280,1920")
ap.add_argument("--no-contrast", action="store_true")
ap.add_argument("--role", default="admin")
args = ap.parse_args()
OUT = ROOT / "docs" / "figures" / "ui_all"
OUT.mkdir(parents=True, exist_ok=True)
QID = "135524194"
PUBLIC = ["#/", "#/signin"]
PAGES = [f"#/search?q={QID}&run=1", f"#/compare?q={QID}&gold=1", "#/querylab?q=murder /3 knife court:SC", "#/saved", "#/history", "#/evaluation", "#/efficiency", "#/index?term=dowry",
         "#/status", "#/users", "#/how", "#/assistant", "#/about", "#/settings", "#/styleguide"]

INIT = """
window.__perf = { cls: 0, shifts: [], long: [] };
try { new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__perf.cls += e.value; window.__perf.shifts.push(e.value); } }).observe({ type: 'layout-shift', buffered: true }); } catch (e) {}
try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__perf.long.push(Math.round(e.duration)); }).observe({ type: 'longtask', buffered: true }); } catch (e) {}
"""

CONTRAST = """
() => {
  const parse = (c) => {
    let m = c.match(/^rgba?\\(([^)]+)\\)/);
    if (m) { const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; }
    m = c.match(/^color\\(srgb ([^)]+)\\)/);
    if (m) { const p = m[1].split(/[ \\/]+/).filter(Boolean).map(Number); return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1 }; }
    return null;
  };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const root = parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
  const base = over(root, { r: 255, g: 255, b: 255, a: 1 });
  const bad = [], seen = new Set(); let checked = 0, skipped = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode; if (!n.textContent.trim()) continue;
    const el = n.parentElement; if (!el || el.closest('script,style,svg,[hidden],.sr-only,[aria-hidden="true"]')) continue;
    const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (el.closest('[disabled],[aria-disabled="true"]')) continue;
    let op = 1, bg = null, unknown = false, e = el;
    const layers = [];
    while (e) { const s = getComputedStyle(e); op *= parseFloat(s.opacity); if (s.backgroundImage !== 'none' && !/^url/.test(s.backgroundImage) ) { unknown = true; } const c = parse(s.backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } e = e.parentElement; }
    if (op < 0.2) continue;
    if (unknown) { skipped++; continue; }
    let b = base; for (let i = layers.length - 1; i >= 0; i--) b = over(layers[i], b);
    let f = parse(cs.color); if (!f) continue; f = over({ ...f, a: f.a * op }, b);
    const L1 = lum(f), L2 = lum(b), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700, large = px >= 24 || (px >= 18.66 && bold);
    checked++;
    if (ratio < (large ? 3 : 4.5)) { const key = el.tagName + '.' + (el.className && el.className.baseVal === undefined ? el.className : '') + ratio.toFixed(1); if (!seen.has(key)) { seen.add(key); bad.push({ el: el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.split(' ')[0] : ''), ratio: +ratio.toFixed(2), size: px }); } }
  }
  return { checked, skipped, bad: bad.slice(0, 12), nbad: bad.length };
}
"""

def page_first_focusable(page):
    return page.evaluate("""() => { const el = document.querySelector('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])'); return el ? (el.classList.contains('skip-link') ? 'skip-link' : el.tagName.toLowerCase() + '.' + el.className) : 'none'; }""")


def tab_walk(page, n=60):
    page.evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0,0); const r = document.createRange(); r.setStart(document.body, 0); r.collapse(true); const s = getSelection(); s.removeAllRanges(); s.addRange(r);")
    stops = []
    for _ in range(n):
        page.keyboard.press("Tab")
        s = page.evaluate("""() => { const a = document.activeElement; if (!a || a === document.body) return null; const r = a.getBoundingClientRect(); const cs = getComputedStyle(a);
          const focusStyle = cs.boxShadow !== 'none' || cs.outlineStyle !== 'none' || !!a.closest('.qbar-field,.strat,.toggle,.role-tile') ;
          return { tag: a.tagName.toLowerCase(), name: (a.getAttribute('aria-label') || a.textContent || a.getAttribute('placeholder') || '').trim().slice(0, 28), y: Math.round(r.y + scrollY), x: Math.round(r.x), visible: r.width > 0 && r.height > 0, focusStyle }; }""")
        if s is None:                      # focus can sit on <body> for one frame while a combobox list hides; press again once
            page.keyboard.press("Tab")
            s = page.evaluate("() => { const a = document.activeElement; if (!a || a === document.body) return null; const r = a.getBoundingClientRect(); const cs = getComputedStyle(a); return { tag: a.tagName.toLowerCase(), name: (a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 28), y: Math.round(r.y + scrollY), x: Math.round(r.x), visible: r.width > 0 && r.height > 0, focusStyle: cs.boxShadow !== 'none' || cs.outlineStyle !== 'none' }; }")
            if s is None:
                break
        stops.append(s)
        if len(stops) > 3 and stops[-1] == stops[0]:
            break
    return stops


def main():
    widths = [int(x) for x in args.widths.split(",")]
    if args.quick:
        widths = [1280]
    themes = ["light"] if args.quick else ["light", "dark"]
    res = {"matrix": [], "console_unexpected": [], "console_expected_401_403": [], "remote_requests": [], "case_text_leaks": [], "overflow": [], "contrast": [], "keyboard": [], "perf": []}
    t0 = time.time()
    with server(show_text=False) as base, sync_playwright() as p:
        b = p.chromium.launch()
        host = base.split("//")[1]
        for theme in themes:
            for w in widths:
                # ---- anonymous (public pages)
                for role_ctx in ("anon", args.role):
                    ctx = b.new_context(viewport={"width": w, "height": 900}, color_scheme=theme)
                    ctx.add_init_script(INIT)
                    pg = ctx.new_page()
                    label = f"{theme}@{w}/{role_ctx}"

                    def on_console(m, label=label):
                        if m.type in ("error", "warning"):
                            txt = m.text
                            (res["console_expected_401_403"] if ("status of 401" in txt or "status of 403" in txt) else res["console_unexpected"]).append(f"{label}: {txt[:160]}")

                    def on_req(r, label=label):
                        if r.url.split("/")[2] != host and not r.url.startswith(("data:", "blob:")):
                            res["remote_requests"].append(f"{label}: {r.url[:100]}")

                    def on_resp(r, label=label):
                        try:
                            u = r.url
                            if any(x in u for x in ("/api/search", "/api/case_detail", "/api/query/run", "/api/overlay")) and r.status == 200:
                                txt = r.text()
                                if '"title"' in txt or '"snippet"' in txt:
                                    res["case_text_leaks"].append(f"{label}: {u.split('/api/')[-1][:40]}")
                        except Exception:
                            pass
                    pg.on("console", on_console); pg.on("pageerror", lambda e, label=label: res["console_unexpected"].append(f"{label}: PAGEERROR {str(e)[:150]}")); pg.on("request", on_req); pg.on("response", on_resp)
                    routes = PUBLIC
                    if role_ctx != "anon":
                        sign_in(pg, base, args.role, None)
                        routes = PAGES
                    for ri, r in enumerate(routes):
                        if ri == 0 and role_ctx == "anon":
                            pg.goto(base + "/" + r)
                        else:
                            pg.evaluate("window.__perf && (window.__perf.cls = 0, window.__perf.long.length = 0)")
                            pg.evaluate("h => { location.hash = h; }", r)
                        try:
                            pg.wait_for_selector(".page > *:not(.skel), .signin, .landing .hero", timeout=45000)
                        except Exception:
                            res["console_unexpected"].append(f"{label} {r}: page did not render")
                        pg.wait_for_timeout(1400)
                        perf = pg.evaluate("window.__perf ? { cls: window.__perf.cls, long: window.__perf.long.slice() } : null")
                        ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                        if ov > 1:
                            res["overflow"].append(f"{label} {r}: +{ov}px")
                        row = {"label": label, "route": r, "cls": round(perf["cls"], 4) if perf else None, "long_tasks": perf["long"] if perf else None}
                        res["perf"].append(row)
                        if not args.no_contrast and (w == 1280 or (w == 375 and r in ("#/", "#/signin"))):
                            c = pg.evaluate(CONTRAST)
                            if c["nbad"]:
                                res["contrast"].append({"label": label, "route": r, "checked": c["checked"], "failing": c["nbad"], "samples": c["bad"][:6]})
                        if (w == 1280 and theme == "light") or (r in ("#/", "#/signin") and w == 375):
                            stops = tab_walk(pg)
                            probs = []
                            if not stops:
                                probs.append("no focusable element")
                            else:
                                first = page_first_focusable(pg)
                                if r not in ("#/", "#/signin") and first != "skip-link":
                                    probs.append(f"first focusable in the document is {first}, not the skip link")
                                probs += [f"focus not visible on {s['tag']} '{s['name']}'" for s in stops if not s["visible"]]
                                probs += [f"no focus style on {s['tag']} '{s['name']}'" for s in stops if not s["focusStyle"]][:4]
                                if len(stops) < 3:
                                    probs.append("fewer than 3 tab stops")
                            res["keyboard"].append({"label": label, "route": r, "stops": len(stops), "problems": probs})
                        res["matrix"].append(f"{label} {r}")
                    ctx.close()
        b.close()
    perf = [x for x in res["perf"] if x["cls"] is not None]
    lt = [d for x in perf for d in (x["long_tasks"] or [])]
    res["summary"] = {"pages_checked": len(res["matrix"]), "seconds": round(time.time() - t0),
                      "cls_max": max((x["cls"] for x in perf), default=None), "cls_mean": round(sum(x["cls"] for x in perf) / max(len(perf), 1), 4),
                      "cls_worst_route": max(perf, key=lambda x: x["cls"])["label"] + " " + max(perf, key=lambda x: x["cls"])["route"] if perf else None,
                      "long_tasks_total": len(lt), "long_task_max_ms": max(lt, default=0), "pages_with_long_tasks": sum(1 for x in perf if x["long_tasks"]),
                      "console_unexpected": len(res["console_unexpected"]), "console_expected_401_403": len(res["console_expected_401_403"]),
                      "remote_requests": len(res["remote_requests"]), "case_text_leaks": len(res["case_text_leaks"]), "overflow": len(res["overflow"]),
                      "contrast_pages_failing": len(res["contrast"]), "keyboard_pages_with_problems": sum(1 for k in res["keyboard"] if k["problems"])}
    (OUT / "gates.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["summary"], indent=1))
    for k in ("console_unexpected", "remote_requests", "case_text_leaks", "overflow"):
        for x in res[k][:8]:
            print(k, x)
    for x in res["contrast"][:10]:
        print("contrast", x["label"], x["route"], x["failing"], x["samples"][:3])
    for x in res["keyboard"]:
        if x["problems"]:
            print("keyboard", x["label"], x["route"], x["problems"][:3])


main()
