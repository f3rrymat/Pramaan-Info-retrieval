"""Assistant service: chat, speech to text, text to speech, language identification and the modality rule.

Nothing here reads case text. The only things sent to Sarvam are: the facts sheet (facts.py), the user's own typed
question or recorded audio, the recent conversation turns held by the browser, and reply text for speech.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any, Dict, List, Optional

from . import client, config, facts, languages as L, wav
from .client import AssistantError, NotConfigured

log = logging.getLogger("irlegal.assistant")

SYSTEM = """You are the AI assistant (Sarvam) inside Pramaan, a student information-retrieval project that ranks earlier Indian judgments (precedents) a new case might cite.
Your job: explain this precedent retrieval system, its results and its evaluation to the user.
Rules:
1. Numbers: use only numbers that appear in the FACTS SHEET below. If a number is not in the facts sheet, say you do not have it. Never estimate, round up or invent statistics.
2. You cannot see case text, case titles or the user's pasted text. Results are identified only by ids, courts, years, scores and score components. Never guess what a case is about.
3. You are an AI helper, not a lawyer. This is not legal advice; say so if the user asks for legal advice, and do not recommend legal actions.
4. Reply in {language}. Keep answers short and structured: at most about 150 words unless the user asks for more.
5. Explain IR ideas in plain words (tf-idf, BM25, neighbour vote, authority, leave-one-out, temporal filter, MAP, recall, bootstrap intervals) when they help.
{spoken}
FACTS SHEET
{facts}
END OF FACTS SHEET"""
SPOKEN = ("6. This answer will be read aloud. Write plain sentences only: no markdown, no tables, no bullet symbols, no long lists of ids, "
          "no special symbols. Say numbers in words-friendly form (for example 0.21 rather than 2.1e-1). Mention at most two ids.")
WRITTEN = "6. Light markdown is fine (short bullet lists, bold). Do not use tables wider than four columns."


# ------------------------------------------------------------------ modality and languages
def should_speak(input_mode: str, pref: str) -> bool:
    """Modality rule (task 2): voice in -> spoken + text; text in -> text only; the user setting may override."""
    if pref == "always":
        return True
    if pref == "never":
        return False
    return input_mode == "voice"


def status() -> Dict[str, Any]:
    on = config.configured()
    return {
        "configured": on, "label": "AI assistant (Sarvam)", "provider": "Sarvam AI",
        "message": None if on else "Assistant not configured",
        "models": {"chat": config.chat_model(), "stt": config.stt_model(), "tts": config.tts_model()} if on else None,
        "languages": {"chat": L.listing(L.CHAT), "stt": L.listing(L.STT), "tts": L.listing(L.TTS), "lid": L.listing(L.LID)},
        "limits": {"max_audio_seconds": config.MAX_AUDIO_SECONDS, "max_audio_bytes": config.MAX_AUDIO_BYTES, "max_question_chars": config.MAX_QUESTION_CHARS,
                   "tts_chars_per_request": config.tts_char_limit(), "rate_limits_per_minute": {k: v[0] for k, v in config.RATE_LIMITS.items()}},
        "privacy": "Your typed question or recorded audio and the recent turns of this conversation are sent to Sarvam AI. "
                   "Case text, case titles and pasted search text are never sent; the assistant only sees ids, courts, years, scores and saved aggregate results.",
    }


def detect_language(text: str) -> Optional[str]:
    """Sarvam text-lid on at most 1000 characters; None if unknown or the call fails (the caller falls back)."""
    try:
        d = client.post(config.LID_PATH, json={"input": text[: config.LID_MAX_CHARS]}, what="text-lid")
    except NotConfigured:
        raise
    except AssistantError:
        return None
    return L.normalise(d.get("language_code"))


# ------------------------------------------------------------------ chat
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _history(hist: Any) -> List[Dict[str, str]]:
    out = []
    for m in (hist or [])[-2 * config.MAX_HISTORY_TURNS:] if isinstance(hist, list) else []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"].strip():
            out.append({"role": m["role"], "content": m["content"][: config.MAX_HISTORY_CHARS]})
    while out and out[0]["role"] != "user":          # the conversation must start with a user turn
        out.pop(0)
    return out


def chat(message: str, *, history: Any = None, input_mode: str = "text", speak_pref: str = "follow", language: Optional[str] = None,
         voice_language: Optional[str] = None, context: Any = None, page: Optional[str] = None) -> Dict[str, Any]:
    if not config.configured():
        raise NotConfigured()
    message = (message or "").strip()
    if not message:
        raise AssistantError(422, "empty", "Type or say a question first.")
    if len(message) > config.MAX_QUESTION_CHARS:
        raise AssistantError(422, "too_long", f"Questions are limited to {config.MAX_QUESTION_CHARS} characters.")
    input_mode = "voice" if input_mode == "voice" else "text"
    speak_pref = speak_pref if speak_pref in ("follow", "always", "never") else "follow"

    notes = []
    forced = L.normalise(language) if language and language != "auto" else None
    detected = None
    if forced and forced not in L.CHAT:
        notes.append(f"Replies in {L.name(forced)} are not supported by the chat model; answering in English.")
        forced = L.DEFAULT
    if forced:
        lang, how = forced, "chosen"
    else:
        detected = L.normalise(voice_language) if input_mode == "voice" else detect_language(message)
        if detected in L.CHAT:
            lang, how = detected, "detected"
        elif detected:
            notes.append(f"{L.name(detected)} was detected, but the chat model answers in {len(L.CHAT)} languages; answering in English.")
            lang, how = L.DEFAULT, "fallback"
        else:
            lang, how = None, "mirror"                 # unknown: ask the model to mirror the user's language

    speak = should_speak(input_mode, speak_pref)
    if speak and lang is not None and lang not in L.TTS:
        notes.append(f"Spoken replies are not available in {L.name(lang)}; showing text only.")
        speak = False
    ctx = facts.clean_context(context)
    sheet = facts.build(ctx, page)
    sys_prompt = SYSTEM.format(language=f"{L.name(lang)} ({lang})" if lang else "the same language as the user's question",
                               spoken=SPOKEN if speak else WRITTEN, facts=sheet)
    body = {"model": config.chat_model(), "messages": [{"role": "system", "content": sys_prompt}, *_history(history), {"role": "user", "content": message}],
            "temperature": 0.2, "max_tokens": 2048}
    if config.reasoning_effort():
        body["reasoning_effort"] = config.reasoning_effort()
    d = client.post(config.CHAT_PATH, json=body, what="chat")
    try:
        content = d["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        raise AssistantError(502, "upstream_bad_reply", "Sarvam returned an answer in an unexpected shape.") from None
    reply = _THINK.sub("", content).strip()
    if not reply:
        raise AssistantError(502, "empty_reply", "The model returned no answer. Try a shorter or simpler question.")
    return {"reply": reply, "language": lang, "language_name": L.name(lang) if lang else None, "language_source": how,
            "detected_language": detected, "speak": speak, "tts_language": lang if speak else None, "notes": notes,
            "input_mode": input_mode, "model": config.chat_model(), "context_used": bool(ctx)}


# ------------------------------------------------------------------ speech to text
def stt(audio: bytes, language: Optional[str] = None) -> Dict[str, Any]:
    if not config.configured():
        raise NotConfigured()
    if len(audio) > config.MAX_AUDIO_BYTES:
        raise AssistantError(413, "audio_too_large", f"The recording is too large (limit {config.MAX_AUDIO_BYTES // 1000} kB).")
    try:
        w = wav.parse(audio)
    except ValueError as e:
        raise AssistantError(415, "audio_format", f"Send a WAV recording ({e}).") from None
    if w.seconds > config.MAX_AUDIO_SECONDS + 0.25:
        raise AssistantError(413, "audio_too_long", f"Recordings are limited to {int(config.MAX_AUDIO_SECONDS)} seconds.")
    if w.seconds < config.MIN_AUDIO_SECONDS:
        raise AssistantError(422, "audio_too_short", "The recording is too short. Hold the microphone a little longer.")
    code = L.normalise(language) if language and language != "auto" else None
    data = {"model": config.stt_model(), "mode": "transcribe", "language_code": code if code in L.STT else "unknown"}
    d = client.post(config.STT_PATH, files={"file": ("question.wav", audio, "audio/wav")}, data=data, what="speech-to-text")
    transcript = (d.get("transcript") or "").strip()
    det = L.normalise(d.get("language_code"))
    return {"transcript": transcript, "language": det, "language_name": L.name(det) if det else None,
            "language_probability": d.get("language_probability") if isinstance(d.get("language_probability"), (int, float)) else None,
            "seconds": round(w.seconds, 2)}


# ------------------------------------------------------------------ text to speech
_MD = [(re.compile(r"```.*?```", re.S), " "), (re.compile(r"`([^`]*)`"), r"\1"), (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
       (re.compile(r"https?://\S+"), "a link"), (re.compile(r"^\s{0,3}#{1,6}\s*", re.M), ""), (re.compile(r"^\s*[-*+]\s+", re.M), ""),
       (re.compile(r"^\s*\d+[.)]\s+", re.M), ""), (re.compile(r"[*_~|>#]"), " "), (re.compile(r"[ \t]{2,}"), " ")]
_SENT = re.compile(r"(?<=[.!?।॥])\s+|\n+")


def speakable(text: str) -> str:
    t = text
    for pat, rep in _MD:
        t = pat.sub(rep, t)
    return re.sub(r"\s*\n\s*", "\n", t).strip()


def sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT.split(text) if s and s.strip()]


def chunk(text: str, limit: int) -> List[str]:
    """Pack whole sentences into chunks of at most `limit` characters; split an over-long sentence at commas, then spaces."""
    out, cur = [], ""
    for s in sentences(text):
        while len(s) > limit:
            cut = max(s.rfind(", ", 0, limit), s.rfind(" ", 0, limit))
            cut = cut if cut > limit // 3 else limit
            head, s = s[:cut].strip(), s[cut:].lstrip(", ").strip()
            if cur:
                out.append(cur); cur = ""
            out.append(head)
        if not s:
            continue
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur); cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def decode_audio(b64: str) -> bytes:
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        raise AssistantError(502, "upstream_bad_audio", "Sarvam returned audio that could not be decoded.") from None
    try:
        wav.parse(raw)
    except ValueError:
        raise AssistantError(502, "upstream_bad_audio", "Sarvam returned audio that is not a WAV file.") from None
    return raw


def tts(text: str, language: str) -> bytes:
    if not config.configured():
        raise NotConfigured()
    lang = L.normalise(language)
    if lang not in L.TTS:
        raise AssistantError(422, "tts_language", f"Spoken replies are not available in {L.name(lang) if lang else 'this language'}.")
    clean = speakable(text or "")
    if not clean:
        raise AssistantError(422, "empty", "Nothing to read aloud.")
    if len(clean) > config.MAX_TTS_INPUT_CHARS:
        raise AssistantError(413, "too_long", f"Send at most {config.MAX_TTS_INPUT_CHARS} characters per request.")
    parts = []
    for piece in chunk(clean, config.tts_char_limit()):
        d = client.post(config.TTS_PATH, json={"text": piece, "language_code": lang, "model": config.tts_model(), "speaker": config.tts_speaker()}, what="text-to-speech")
        audios = d.get("audios")
        if not isinstance(audios, list) or not audios:
            raise AssistantError(502, "upstream_bad_audio", "Sarvam returned no audio.")
        parts += [decode_audio(a) for a in audios if isinstance(a, str)]
    try:
        return wav.merge(parts) if len(parts) > 1 else parts[0]
    except ValueError:
        raise AssistantError(502, "upstream_bad_audio", "Sarvam returned audio chunks that could not be joined.") from None
