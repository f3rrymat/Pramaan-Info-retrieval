"""AI assistant endpoints (Sarvam AI), DECISIONS D40 to D43. Additive; nothing else changes when no key is set.

GET  /api/assistant/status   configured yes/no, languages per service, limits (never the key)
POST /api/assistant/chat     {message, history?, input_mode: text|voice, speak_pref: follow|always|never, language?, voice_language?, context?, page?}
POST /api/assistant/stt      raw WAV body (Content-Type audio/wav), ?language=auto -> {transcript, language}
POST /api/assistant/tts      {text, language} -> audio/wav (chunked by sentence on the server to respect the per-request limit)

The middleware in app/server.py requires a signed-in session (or AUTH_REQUIRED=0) and the X-Requested-With header.
Errors are {"detail", "code"} and never contain the key, a payload or upstream text.
"""
from __future__ import annotations

import hashlib
from typing import Any, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app import security as sec
from app.assistant import config, ratelimit, service
from app.assistant.client import AssistantError

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatIn(BaseModel):
    message: str
    history: List[Any] = []
    input_mode: str = "text"
    speak_pref: str = "follow"
    language: Optional[str] = "auto"
    voice_language: Optional[str] = None
    context: Optional[dict] = None
    page: Optional[str] = None


class TtsIn(BaseModel):
    text: str
    language: str


def _session(request: Request) -> str:
    u = getattr(request.state, "user", None)
    tok = request.cookies.get(sec.COOKIE, "")
    return f"{u['id'] if u else 'anon'}:{hashlib.sha256(tok.encode()).hexdigest()[:16]}"


def _err(e: AssistantError) -> JSONResponse:
    headers = {"Retry-After": "30"} if e.status == 429 else None
    return JSONResponse({"detail": e.message, "code": e.code}, status_code=e.status, headers=headers)


def _limited(request: Request, kind: str) -> Optional[JSONResponse]:
    wait = ratelimit.check(_session(request), kind)
    if wait:
        return JSONResponse({"detail": f"Too many assistant requests. Try again in {wait} s.", "code": "rate_limited", "retry_after": wait},
                            status_code=429, headers={"Retry-After": str(wait)})
    return None


@router.get("/status")
def status():
    return service.status()


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    if not config.configured():
        return _err(service.NotConfigured())
    lim = _limited(request, "chat")
    if lim:
        return lim
    try:
        return service.chat(body.message, history=body.history, input_mode=body.input_mode, speak_pref=body.speak_pref, language=body.language,
                            voice_language=body.voice_language, context=body.context, page=body.page)
    except AssistantError as e:
        return _err(e)


@router.post("/stt")
async def stt(request: Request, language: str = "auto"):
    if not config.configured():
        return _err(service.NotConfigured())
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in ("audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"):
        return _err(AssistantError(415, "audio_format", "Send the recording as audio/wav."))
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > config.MAX_AUDIO_BYTES:
        return _err(AssistantError(413, "audio_too_large", f"The recording is too large (limit {config.MAX_AUDIO_BYTES // 1000} kB)."))
    buf = bytearray()
    async for part in request.stream():
        buf += part
        if len(buf) > config.MAX_AUDIO_BYTES:
            return _err(AssistantError(413, "audio_too_large", f"The recording is too large (limit {config.MAX_AUDIO_BYTES // 1000} kB)."))
    lim = _limited(request, "stt")
    if lim:
        return lim
    try:
        return service.stt(bytes(buf), language)
    except AssistantError as e:
        return _err(e)


@router.post("/tts")
def tts(body: TtsIn, request: Request):
    if not config.configured():
        return _err(service.NotConfigured())
    lim = _limited(request, "tts")
    if lim:
        return lim
    try:
        audio = service.tts(body.text, body.language)
    except AssistantError as e:
        return _err(e)
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
