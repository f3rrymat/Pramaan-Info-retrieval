"""Assistant configuration. Values follow the Sarvam documentation read on 2026-10-07 (docs.sarvam.ai):

* chat:  POST /v1/chat/completions, model sarvam-105b (sarvam-m and sarvam-30b are listed as deprecated), header
         api-subscription-key, reply in choices[0].message.content, optional reasoning_effort (low, medium, high, max).
* STT:   POST /speech-to-text, multipart (file, model saaras:v4, mode transcribe, language_code "unknown" for
         detection); the REST endpoint accepts at most 30 seconds of audio per request. No byte limit is documented,
         so ours is derived from 30 s of 16 kHz mono 16-bit WAV plus headroom.
* TTS:   POST /text-to-speech, JSON (text, language_code, model bulbul:v3, speaker); at most 2500 characters per
         request for bulbul:v3 (1500 for bulbul:v2); response {"audios": [base64 WAV, ...]}.
* LID:   POST /text-lid, JSON {"input"}; at most 1000 characters.

Only SARVAM_API_KEY is secret. The base URL is fixed on purpose (no environment override), so the key can only ever
be sent to api.sarvam.ai.
"""
from __future__ import annotations

import os

BASE_URL = "https://api.sarvam.ai"
CHAT_PATH, STT_PATH, TTS_PATH, LID_PATH = "/v1/chat/completions", "/speech-to-text", "/text-to-speech", "/text-lid"

DEFAULT_CHAT_MODEL = "sarvam-105b"
DEFAULT_STT_MODEL = "saaras:v4"
DEFAULT_TTS_MODEL = "bulbul:v3"
DEFAULT_TTS_SPEAKER = "shubh"
DEFAULT_REASONING = "low"

MAX_AUDIO_SECONDS = 30.0                 # documented REST limit for speech to text
MAX_AUDIO_BYTES = 2_000_000              # 30 s at 16 kHz mono 16-bit is 960,000 bytes; headroom for 22.05/24 kHz input
MIN_AUDIO_SECONDS = 0.3
MAX_QUESTION_CHARS = 1000                # also the documented text-lid input limit
MAX_HISTORY_TURNS = 8
MAX_HISTORY_CHARS = 2000
MAX_TTS_INPUT_CHARS = 3000               # per call to our /tts endpoint (the client sends a sentence or two)
LID_MAX_CHARS = 1000
TTS_LIMITS = {"bulbul:v3": 2500, "bulbul:v2": 1500}
FACTS_MAX_CHARS = 14_000                 # hard cap on the facts sheet sent as context
CONTEXT_MAX_RESULTS = 10

TIMEOUT_CONNECT, TIMEOUT_READ = 5.0, 45.0
RETRIES_ON_5XX = 2
RATE_LIMITS = {"chat": (12, 60.0), "stt": (12, 60.0), "tts": (60, 60.0)}   # (requests, window seconds) per session


def api_key() -> str:
    """The key, read fresh from the environment on every call. Never log or return it."""
    return os.environ.get("SARVAM_API_KEY", "").strip()


def configured() -> bool:
    return bool(api_key())


def chat_model() -> str:
    return os.environ.get("SARVAM_CHAT_MODEL", DEFAULT_CHAT_MODEL).strip() or DEFAULT_CHAT_MODEL


def stt_model() -> str:
    return os.environ.get("SARVAM_STT_MODEL", DEFAULT_STT_MODEL).strip() or DEFAULT_STT_MODEL


def tts_model() -> str:
    return os.environ.get("SARVAM_TTS_MODEL", DEFAULT_TTS_MODEL).strip() or DEFAULT_TTS_MODEL


def tts_speaker() -> str:
    return os.environ.get("SARVAM_TTS_SPEAKER", DEFAULT_TTS_SPEAKER).strip().lower() or DEFAULT_TTS_SPEAKER


def reasoning_effort():
    """low | medium | high | max, or None to leave the field out (SARVAM_REASONING_EFFORT=none)."""
    v = os.environ.get("SARVAM_REASONING_EFFORT", DEFAULT_REASONING).strip().lower()
    return v if v in ("low", "medium", "high", "max") else None


def tts_char_limit() -> int:
    return TTS_LIMITS.get(tts_model(), 1500)
