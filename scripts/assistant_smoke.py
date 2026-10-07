"""One tiny real call per Sarvam service, only if SARVAM_API_KEY is set in the environment (D41).
Prints OK or the error class for each call, never any content (no reply text, no transcript, no audio, no key).

Usage:  read -rs SARVAM_API_KEY && export SARVAM_API_KEY
        python scripts/assistant_smoke.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from app.assistant import config, service, wav  # noqa: E402
from app.assistant.client import AssistantError  # noqa: E402

if not config.configured():
    print("SKIPPED: SARVAM_API_KEY is not set (nothing was sent).")
    sys.exit(0)

results = {}


def run(name, fn):
    try:
        fn()
        results[name] = "OK"
    except AssistantError as e:
        results[name] = f"ERROR {e.code} (HTTP {e.status})"
    except Exception as e:                              # report the class only, never the message (it could echo content)
        results[name] = f"ERROR {type(e).__name__}"
    print(f"{name:15s} {results[name]}")


print(f"models: chat {config.chat_model()}, stt {config.stt_model()}, tts {config.tts_model()} (speaker {config.tts_speaker()})")
run("chat", lambda: service.chat("In one short sentence: what is MAP?", language="en-IN", page="/evaluation"))
run("speech-to-text", lambda: service.stt(wav.silence(1.0)))          # a silent 1 s clip: an empty transcript is still OK
run("text-to-speech", lambda: service.tts("Hello.", "en-IN"))
sys.exit(0 if all(v == "OK" for v in results.values()) else 1)
