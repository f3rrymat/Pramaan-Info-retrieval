"""Assistant UI QA with Playwright (dev-only). No Sarvam call and no key: the browser's /api/assistant/* requests are
answered by mocks inside Playwright, except for the "not configured" check, which uses the real server without a key.
Chromium runs with a fake microphone (--use-fake-device-for-media-stream, --use-fake-ui-for-media-stream).

Checks: unconfigured state, one-time consent, text question (text-only reply), language chip, mic recording with waveform
and countdown, voice reply that is spoken AND shown, Stop speaking (button and Escape), Listen, autoplay blocked -> Tap to
play, error + Retry, Explain this result (ids and numbers only in the request), 375 px layout, zero unexpected console errors.
Screenshots: docs/figures/ui_all/assistant_*.png; a curated few are copied to docs/figures/ui/ (no case text, no key).

Usage: python scripts/assistant_qa.py [--mode toy|real]
"""
import argparse
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="toy"); a = ap.parse_args()
ALL, CUR = ROOT / "docs" / "figures" / "ui_all", ROOT / "docs" / "figures" / "ui"
ALL.mkdir(parents=True, exist_ok=True); CUR.mkdir(parents=True, exist_ok=True)
tmp = ROOT / "data" / "assistant_qa"; tmp.mkdir(parents=True, exist_ok=True)
for _f in tmp.glob("*"):          # a fresh throw-away database every run
    _f.unlink()


def tone_wav(seconds=1.6, rate=24000, freq=330.0) -> bytes:
    n = int(seconds * rate)
    pcm = b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
    return b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm


s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "AUTH_REQUIRED": "0", "DEMO_ROLE": "researcher", "IRLEGAL_MODE": a.mode,
       "IRLEGAL_APP_DB": str(tmp / "qa.db"), "IRLEGAL_APP_SECRET": str(tmp / "qa.key")}
for k in ("SHOW_TEXT", "SARVAM_API_KEY"):
    env.pop(k, None)
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
base = f"http://127.0.0.1:{port}"
res = {"checks": [], "unexpected_console_errors": [], "expected_console_errors": [], "shots": []}


def ok(name, cond, extra=""):
    res["checks"].append({"check": name, "pass": bool(cond), "detail": str(extra)[:200]}); print(("PASS " if cond else "FAIL ") + name, str(extra)[:160])


try:
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1).read(); break
        except Exception:
            time.sleep(0.5)
    real_status = json.load(urllib.request.urlopen(base + "/api/assistant/status"))
    from playwright.sync_api import sync_playwright
    TONE = tone_wav()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"])
        calls = []
        state = {"chat_fail": 0}

        def mock(route, request):
            path = request.url.split("/api/assistant/")[1].split("?")[0]
            if path == "status":
                return route.fulfill(json={**real_status, "configured": True, "message": None, "models": {"chat": "sarvam-105b", "stt": "saaras:v4", "tts": "bulbul:v3"}})
            if path == "chat":
                body = json.loads(request.post_data or "{}"); calls.append(("chat", body))
                if state["chat_fail"]:
                    state["chat_fail"] -= 1
                    return route.fulfill(status=502, json={"detail": "Sarvam is unavailable right now (status 503). Try again shortly.", "code": "upstream_unavailable"})
                voice = body.get("input_mode") == "voice"
                lang = body.get("language") if body.get("language") not in (None, "auto") else (body.get("voice_language") or "en-IN")
                speak = voice if body.get("speak_pref", "follow") == "follow" else body.get("speak_pref") == "always"
                reply = ("The final score adds three signals. **Text** is the tf-idf match, **neighbours** are similar train cases that cite the precedent, "
                         "and **authority** is how often it is cited. Each is scaled to 0–1 first. I can only see ids and numbers, not case text.")
                return route.fulfill(json={"reply": reply, "language": lang, "language_name": {"en-IN": "English", "hi-IN": "Hindi"}.get(lang, lang), "language_source": "chosen" if body.get("language") not in (None, "auto") else "detected",
                                           "speak": speak, "tts_language": lang if speak else None, "notes": [], "input_mode": body.get("input_mode"), "model": "mock", "context_used": bool(body.get("context"))})
            if path == "stt":
                data = request.post_data_buffer or b""; calls.append(("stt", {"bytes": len(data), "riff": data[:4] == b"RIFF", "ctype": request.headers.get("content-type")}))
                return route.fulfill(json={"transcript": "How is the final score combined?", "language": "en-IN", "language_name": "English", "language_probability": 0.97, "seconds": 1.5})
            if path == "tts":
                calls.append(("tts", json.loads(request.post_data or "{}")))
                return route.fulfill(status=200, body=TONE, headers={"Content-Type": "audio/wav"})
            return route.fulfill(status=404, json={"detail": "not mocked"})

        def new(theme="light", w=1280, mocked=True, init=None):
            ctx = b.new_context(viewport={"width": w, "height": 860}, color_scheme=theme, permissions=["microphone"])
            pg = ctx.new_page()
            if init:
                pg.add_init_script(init)

            def on_console(m):
                if m.type in ("error", "warning"):
                    (res["expected_console_errors"] if "status of 502" in m.text else res["unexpected_console_errors"]).append(m.text)
            pg.on("console", on_console); pg.on("pageerror", lambda e: res["unexpected_console_errors"].append(str(e)))
            pg.on("request", lambda r: res["unexpected_console_errors"].append("remote request " + r.url) if not r.url.startswith(base) and not r.url.startswith(("data:", "blob:")) else None)
            if mocked:
                pg.route("**/api/assistant/**", mock)
            return ctx, pg

        def shot(pg, name, curated=None):
            pg.screenshot(path=str(ALL / f"assistant_{name}.png")); res["shots"].append(f"ui_all/assistant_{name}.png")
            if curated:
                shutil.copy(ALL / f"assistant_{name}.png", CUR / curated); res["shots"].append(f"ui/{curated}")

        # 1. not configured (real server, no key, no mocks)
        ctx, pg = new(mocked=False)
        pg.goto(base + "/#/search"); pg.wait_for_selector(".as-fab")
        pg.click(".as-fab"); pg.wait_for_selector(".as-unconfigured")
        ok("no key: panel says 'Assistant not configured'", "Assistant not configured" in pg.inner_text(".as-panel"))
        ok("no key: composer is disabled", pg.is_disabled(".as-input") and pg.is_disabled(".as-mic"))
        shot(pg, "unconfigured_light_1280")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        ok("Escape closes the panel", pg.locator(".as-host").count() == 0)
        ctx.close()

        # 2. consent, text question, language chip
        ctx, pg = new()
        qid0 = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/queries")))["queries"][0]["qid"]
        pg.goto(base + f"/#/search?q={qid0}&run=1"); pg.wait_for_selector(".result"); pg.wait_for_timeout(700)
        pg.keyboard.press("Alt+a"); pg.wait_for_selector(".as-panel .as-input:not([disabled])")
        ok("Alt+A opens the panel; label 'AI assistant (Sarvam)'", "AI assistant (Sarvam)" in pg.inner_text(".as-head"))
        ok("first message says it is not legal advice", "not legal advice" in pg.inner_text(".as-msg.greeting").lower())
        ok("suggested questions depend on the page", "neighbour score" in pg.inner_text(".as-suggest"))
        pg.fill(".as-input", "How is the final score combined?"); pg.keyboard.press("Enter")
        pg.wait_for_selector(".as-consent"); shot(pg, "consent_light_1280")
        ok("consent notice appears before anything is sent", not [c for c in calls if c[0] == "chat"])
        pg.click(".as-consent .btn >> text=Accept and continue"); pg.wait_for_selector(".as-msg.assistant:not(.greeting):not(.as-typing)")
        ok("text question -> text reply, nothing spoken", pg.locator(".as-speakbar").is_hidden() and not [c for c in calls if c[0] == "tts"])
        ok("chat request uses input_mode text and the page", calls[-1][1].get("input_mode") == "text" and calls[-1][1].get("page") == "/search")
        pg.click(".as-lang"); pg.wait_for_selector(".as-lang-menu:not([hidden])"); shot(pg, "language_menu_light_1280")
        pg.click(".as-lang-opt >> text=Hindi"); ok("language chip shows the forced language", "Hindi" in pg.inner_text(".as-lang"))
        pg.fill(".as-input", "Explain MAP"); pg.keyboard.press("Enter"); pg.wait_for_timeout(600)
        ok("forced language is sent with the question", calls[-1][1].get("language") == "hi-IN")
        pg.click(".as-lang"); pg.click(".as-lang-opt >> text=Auto-detect")
        shot(pg, "panel_light_1280", "assistant_panel_light.png")
        # error + retry
        state["chat_fail"] = 1
        pg.fill(".as-input", "Is the gain significant?"); pg.keyboard.press("Enter"); pg.wait_for_selector(".as-msg.err")
        ok("error is shown with a Retry button", pg.locator(".as-msg.err .btn >> text=Retry").count() == 1)
        n_before = len([c for c in calls if c[0] == "chat"])
        pg.click(".as-msg.err .btn >> text=Retry"); pg.wait_for_timeout(700)
        ok("Retry sends the question again and the error disappears", len([c for c in calls if c[0] == "chat"]) == n_before + 1 and pg.locator(".as-msg.err").count() == 0)
        # mic recording -> voice reply (spoken + text), Stop speaking
        pg.click(".as-mic"); pg.wait_for_selector(".as[data-state='recording']")
        pg.wait_for_timeout(1500)
        ok("recording shows a waveform and a countdown", pg.locator(".as-rec:not([hidden]) canvas.as-wave").count() == 1 and int(pg.inner_text(".as-secs")) <= 29)
        shot(pg, "recording_light_1280", "assistant_recording_light.png")
        pg.click(".as-rec .btn >> text=Stop and send")
        pg.wait_for_selector(".as-speakbar:not([hidden])", timeout=15000)
        stt = [c for c in calls if c[0] == "stt"]
        ok("speech-to-text got a WAV recording", stt and stt[-1][1]["riff"] and stt[-1][1]["ctype"].startswith("audio/wav") and stt[-1][1]["bytes"] < 2_000_000, stt[-1][1] if stt else "")
        ok("voice question is sent with input_mode voice", [c for c in calls if c[0] == "chat"][-1][1].get("input_mode") == "voice")
        ok("voice reply: text is shown while speaking", pg.locator(".as-msg.assistant.speaking .as-bubble").count() == 1)
        ok("Stop speaking button is visible", pg.locator(".as-speakbar .btn >> text=Stop speaking").is_visible())
        shot(pg, "speaking_light_1280", "assistant_voice_light.png")
        pg.click(".as-speakbar .btn >> text=Stop speaking"); pg.wait_for_timeout(250)
        paused = pg.evaluate("() => [...document.querySelectorAll('audio')].every(a => a.paused)")
        ok("Stop speaking halts audio at once and keeps the text", pg.locator(".as-speakbar").is_hidden() and pg.locator(".as-msg.assistant:not(.greeting)").count() >= 3)
        ok("first TTS request is a single sentence (speech starts early)", len([c for c in calls if c[0] == "tts"][0][1]["text"]) < 120)
        pg.locator(".as-listen").last.click(); pg.wait_for_selector(".as-speakbar:not([hidden])", timeout=10000)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(250)
        ok("Listen speaks a message; Escape stops it", pg.locator(".as-speakbar").is_hidden() and pg.locator(".as-host").count() == 1)
        pg.set_viewport_size({"width": 375, "height": 760}); pg.wait_for_timeout(400)
        ov = pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        ok("375 px: panel is full width, no horizontal overflow", not ov and abs(pg.eval_on_selector(".as-host", "e => e.getBoundingClientRect().width") - 375) < 2)
        shot(pg, "panel_light_375", "assistant_mobile_light.png")
        ctx.close()

        # 3. autoplay blocked -> Tap to play
        block = "(() => { const orig = HTMLMediaElement.prototype.play; let n = 0; HTMLMediaElement.prototype.play = function () { if (n++ === 0) return Promise.reject(new DOMException('blocked', 'NotAllowedError')); return orig.call(this); }; try { localStorage.setItem('irl.assistant.consent.v1', 'true'); } catch (e) {} })();"
        ctx, pg = new(init=block)
        pg.goto(base + "/#/assistant"); pg.wait_for_selector(".as-page .as-input:not([disabled])")
        ok("#/assistant shows the same component as a full page; no floating button there", pg.locator(".as-page").count() == 1 and pg.locator(".as-fab").is_hidden())
        pg.locator(".as-chip").first.click(); pg.wait_for_selector(".as-msg.assistant:not(.greeting):not(.as-typing)")
        pg.locator(".as-listen").last.click(); pg.wait_for_selector(".as-speakbar .btn >> text=Tap to play", timeout=10000)
        ok("autoplay blocked -> 'Tap to play' is offered", True)
        pg.click(".as-speakbar .btn >> text=Tap to play"); pg.wait_for_timeout(400)
        ok("Tap to play resumes speech", pg.locator(".as[data-state='speaking']").count() == 1 or pg.locator(".as-speakbar").is_hidden())
        pg.keyboard.press("Escape")
        ctx.close()

        # 4. Explain this result (Search) and dark theme
        ctx, pg = new("dark")
        pg.add_init_script("try { localStorage.setItem('irl.assistant.consent.v1', 'true'); } catch (e) {}")
        pg.goto(base + "/#/search"); pg.wait_for_selector(".qbar-input")
        qid = pg.evaluate("fetch('/api/queries').then(r => r.json()).then(d => d.queries[0].qid)")
        pg.goto(base + f"/#/search?q={qid}&run=1"); pg.wait_for_selector(".result"); pg.wait_for_timeout(900)
        pg.click(".apill"); pg.wait_for_timeout(300)
        ok("pipeline strip shows server timings", pg.locator(".pipe-stage.done").count() >= 3 and "ms" in pg.inner_text(".pipe-strip"))
        shot(pg, "search_pipeline_dark_1280", "search_pipeline_dark.png")
        pg.locator(".result").first.locator("button[title^='Explain this result']").click()
        pg.wait_for_selector(".as-panel .as-ctx:not([hidden])")
        ok("Explain this result pre-fills a question and attaches context", "Explain why result" in pg.input_value(".as-input") and "Only ids and numbers" in pg.inner_text(".as-ctx"))
        pg.keyboard.press("Enter"); pg.wait_for_selector(".as-msg.assistant:not(.greeting):not(.as-typing)")
        body = [c for c in calls if c[0] == "chat"][-1][1]
        ctxj = json.dumps(body.get("context"))
        allowed = {"doc_id", "rank", "court", "year", "score", "components", "relevant", "neighbours"}
        items = (body.get("context") or {}).get("results") or []
        ok("result context carries ids and numbers only (no title, snippet or text)", items and all(set(r) <= allowed for r in items) and "text" not in body["context"] and '"title"' not in ctxj and '"snippet"' not in ctxj, ctxj[:160])
        shot(pg, "explain_result_dark_1280", "assistant_explain_dark.png")
        ctx.close()
        b.close()
finally:
    srv.terminate()
res["passed"] = sum(c["pass"] for c in res["checks"]); res["total"] = len(res["checks"])
print(json.dumps({k: res[k] for k in ("passed", "total", "unexpected_console_errors", "expected_console_errors")}, indent=1))
sys.exit(0 if res["passed"] == res["total"] and not res["unexpected_console_errors"] else 1)
