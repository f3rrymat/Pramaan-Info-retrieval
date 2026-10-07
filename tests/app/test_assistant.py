"""Assistant (Sarvam) with every outbound call mocked: no network, no real key. D40 to D43."""
import base64
import json
import logging
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.assistant import client as sclient, config, facts, ratelimit, service, wav
from app.server import app

H = {"X-Requested-With": "irl"}
FAKE_KEY = "sk_test_FAKE-key-never-leak-7781"          # a fake sentinel, not a real key
UPSTREAM_SECRET = "UPSTREAM_BODY_MUST_NOT_BE_ECHOED"


class Mock:
    """Records every outbound request and answers like the documented Sarvam endpoints."""

    def __init__(self):
        self.calls, self.lid, self.stt_lang, self.fail = [], "hi-IN", "ta-IN", {}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = req.read()
        self.calls.append({"path": req.url.path, "host": req.url.host, "headers": dict(req.headers), "body": body})
        seq = self.fail.get(req.url.path)
        if seq:
            st = seq.pop(0)
            if st == "timeout":
                raise httpx.ReadTimeout("slow", request=req)
            return httpx.Response(st, json={"error": {"message": UPSTREAM_SECRET}})
        if req.url.path == "/text-lid":
            return httpx.Response(200, json={"request_id": "r1", "language_code": self.lid, "script_code": "Deva"})
        if req.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "<think>x</think>Config A combines text, neighbours and authority."}}]})
        if req.url.path == "/speech-to-text":
            return httpx.Response(200, json={"request_id": "r2", "transcript": "what is map", "language_code": self.stt_lang, "language_probability": 0.9})
        if req.url.path == "/text-to-speech":
            text = json.loads(body)["text"]
            clip = wav.build(1, 24000, 16, b"\x01\x00" * (10 * len(text)))
            return httpx.Response(200, json={"request_id": "r3", "audios": [base64.b64encode(clip).decode()]})
        return httpx.Response(404, json={})

    def bodies(self):
        return b"\n".join(c["body"] for c in self.calls).decode("utf-8", "replace")


@pytest.fixture
def mock(monkeypatch):
    m = Mock()
    sclient.set_transport(httpx.MockTransport(m), sleep=lambda s: None)
    ratelimit.reset()
    yield m
    sclient.set_transport(None)
    ratelimit.reset()


@pytest.fixture
def keyed(monkeypatch, mock):
    monkeypatch.setenv("SARVAM_API_KEY", FAKE_KEY)
    return TestClient(app)


def test_status_and_endpoints_when_unconfigured(monkeypatch, mock):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    c = TestClient(app)
    s = c.get("/api/assistant/status").json()
    assert s["configured"] is False and s["message"] == "Assistant not configured" and s["label"] == "AI assistant (Sarvam)"
    assert {x["code"] for x in s["languages"]["tts"]} >= {"en-IN", "hi-IN", "ta-IN"} and len(s["languages"]["stt"]) == 23
    for path, kw in (("/api/assistant/chat", {"json": {"message": "hi"}}), ("/api/assistant/tts", {"json": {"text": "hi", "language": "en-IN"}}),
                     ("/api/assistant/stt", {"content": wav.silence(1.0), "headers": {**H, "Content-Type": "audio/wav"}})):
        r = c.post(path, headers=kw.pop("headers", H), **kw)
        assert r.status_code == 503 and r.json() == {"detail": "Assistant not configured", "code": "not_configured"}
    assert mock.calls == []
    assert c.get("/api/health").json()["status"] == "ok"               # the rest of the app is unaffected


def test_chat_happy_path_detects_language_and_follows_text_mode(keyed, mock):
    r = keyed.post("/api/assistant/chat", json={"message": "Config A kya hai?", "input_mode": "text", "page": "/evaluation"}, headers=H)
    d = r.json()
    assert r.status_code == 200 and d["reply"] == "Config A combines text, neighbours and authority."   # think block removed
    assert d["language"] == "hi-IN" and d["language_source"] == "detected" and d["speak"] is False and d["tts_language"] is None
    paths = [c["path"] for c in mock.calls]
    assert paths == ["/text-lid", "/v1/chat/completions"] and all(c["host"] == "api.sarvam.ai" for c in mock.calls)
    body = json.loads(mock.calls[1]["body"])
    assert body["model"] == config.DEFAULT_CHAT_MODEL and body["messages"][0]["role"] == "system" and body["messages"][-1]["content"] == "Config A kya hai?"
    sysm = body["messages"][0]["content"]
    assert "FACTS SHEET" in sysm and "not legal advice" in sysm.lower() and "Hindi (hi-IN)" in sysm and "evaluation page" in sysm
    assert mock.calls[1]["headers"]["api-subscription-key"] == FAKE_KEY       # sent to Sarvam only, in the header


def test_modality_rule():
    assert service.should_speak("voice", "follow") and not service.should_speak("text", "follow")
    assert service.should_speak("text", "always") and not service.should_speak("voice", "never")


def test_voice_chat_speaks_and_forced_language_and_fallbacks(keyed, mock):
    d = keyed.post("/api/assistant/chat", json={"message": "what is map", "input_mode": "voice", "voice_language": "ta-IN"}, headers=H).json()
    assert d["speak"] is True and d["tts_language"] == "ta-IN" and d["language"] == "ta-IN"
    assert "/text-lid" not in [c["path"] for c in mock.calls]                 # voice uses the STT language
    d = keyed.post("/api/assistant/chat", json={"message": "x", "input_mode": "voice", "speak_pref": "never", "language": "bn-IN"}, headers=H).json()
    assert d["speak"] is False and d["language"] == "bn-IN" and d["language_source"] == "chosen"
    d = keyed.post("/api/assistant/chat", json={"message": "x", "input_mode": "voice", "voice_language": "ur-IN"}, headers=H).json()
    assert d["language"] == "en-IN" and d["speak"] is True and any("Urdu" in n for n in d["notes"])
    mock.fail["/text-lid"] = [500, 500, 500]
    d = keyed.post("/api/assistant/chat", json={"message": "hello", "speak_pref": "always"}, headers=H).json()
    assert d["language"] is None and d["language_source"] == "mirror" and d["speak"] is True     # LID failed: mirror, no crash


def test_stt_roundtrip(keyed, mock):
    r = keyed.post("/api/assistant/stt", content=wav.silence(1.2), headers={**H, "Content-Type": "audio/wav"})
    d = r.json()
    assert r.status_code == 200 and d["transcript"] == "what is map" and d["language"] == "ta-IN" and d["seconds"] == 1.2
    call = mock.calls[-1]
    assert call["path"] == "/speech-to-text" and call["headers"]["content-type"].startswith("multipart/form-data")
    assert b'name="model"\r\n\r\nsaaras:v4' in call["body"] and b'name="mode"\r\n\r\ntranscribe' in call["body"] and b'name="language_code"\r\n\r\nunknown' in call["body"]


def test_oversized_long_and_wrong_audio_rejected(keyed, mock):
    big = wav.build(1, 16000, 16, b"\x00" * (config.MAX_AUDIO_BYTES + 10))
    r = keyed.post("/api/assistant/stt", content=big, headers={**H, "Content-Type": "audio/wav"})
    assert r.status_code == 413 and r.json()["code"] == "audio_too_large"
    long = wav.build(1, 8000, 16, b"\x00\x00" * 8000 * 31)                      # 31 s, under the byte cap
    r = keyed.post("/api/assistant/stt", content=long, headers={**H, "Content-Type": "audio/wav"})
    assert r.status_code == 413 and r.json()["code"] == "audio_too_long"
    r = keyed.post("/api/assistant/stt", content=b"OggS" + b"\x00" * 100, headers={**H, "Content-Type": "audio/wav"})
    assert r.status_code == 415
    r = keyed.post("/api/assistant/stt", content=wav.silence(1.0), headers={**H, "Content-Type": "audio/webm"})
    assert r.status_code == 415
    assert mock.calls == []


def test_tts_chunking_base64_decoding_and_merge(keyed, mock, monkeypatch):
    text = " ".join(f"Sentence number {i} explains a metric." for i in range(40))
    chunks = service.chunk(text, 200)
    assert all(len(c) <= 200 for c in chunks) and len(chunks) > 1 and " ".join(chunks) == text
    assert all(len(c) <= 50 for c in service.chunk("a" * 30 + ", " + "b" * 120, 50))          # an over-long sentence is split too
    monkeypatch.setitem(config.TTS_LIMITS, "bulbul:v3", 300)
    r = keyed.post("/api/assistant/tts", json={"text": "**Bold** answer. " + text, "language": "en-IN"}, headers=H)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    tts_calls = [json.loads(c["body"]) for c in mock.calls if c["path"] == "/text-to-speech"]
    assert len(tts_calls) > 1 and all(len(b["text"]) <= 300 for b in tts_calls)
    assert all(b["model"] == "bulbul:v3" and b["speaker"] == "shubh" and b["language_code"] == "en-IN" for b in tts_calls)
    assert "*" not in "".join(b["text"] for b in tts_calls)                                     # markdown stripped for speech
    merged = wav.parse(r.content)
    assert merged.sample_rate == 24000 and len(merged.data) == sum(20 * len(b["text"]) for b in tts_calls)
    r = keyed.post("/api/assistant/tts", json={"text": "hello", "language": "ur-IN"}, headers=H)
    assert r.status_code == 422 and r.json()["code"] == "tts_language"
    with pytest.raises(service.AssistantError):
        service.decode_audio(base64.b64encode(b"not audio at all, definitely not RIFF").decode())


def test_rate_limit_per_session(keyed, mock, monkeypatch):
    monkeypatch.setitem(config.RATE_LIMITS, "chat", (2, 60.0))
    codes = [keyed.post("/api/assistant/chat", json={"message": "q", "language": "en-IN"}, headers=H).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = keyed.post("/api/assistant/chat", json={"message": "q"}, headers=H)
    assert r.json()["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


def test_retries_only_on_5xx(keyed, mock):
    mock.fail["/v1/chat/completions"] = [502, 500]
    assert keyed.post("/api/assistant/chat", json={"message": "q", "language": "en-IN"}, headers=H).status_code == 200
    assert sum(c["path"] == "/v1/chat/completions" for c in mock.calls) == 3
    mock.calls.clear(); mock.fail["/v1/chat/completions"] = [429]
    r = keyed.post("/api/assistant/chat", json={"message": "q", "language": "en-IN"}, headers=H)
    assert r.status_code == 429 and sum(c["path"] == "/v1/chat/completions" for c in mock.calls) == 1
    mock.calls.clear(); mock.fail["/v1/chat/completions"] = [400]
    r = keyed.post("/api/assistant/chat", json={"message": "q", "language": "en-IN"}, headers=H)
    assert r.status_code == 502 and len(mock.calls) == 1


def test_key_never_in_responses_or_logs(keyed, mock, caplog):
    caplog.set_level(logging.DEBUG)
    out = []
    out.append(keyed.get("/api/assistant/status"))
    out.append(keyed.post("/api/assistant/chat", json={"message": "hello"}, headers=H))
    out.append(keyed.post("/api/assistant/stt", content=wav.silence(1.0), headers={**H, "Content-Type": "audio/wav"}))
    out.append(keyed.post("/api/assistant/tts", json={"text": "Hello there.", "language": "en-IN"}, headers=H))
    for path, err in (("/v1/chat/completions", [401]), ("/v1/chat/completions", [503, 503, 503]), ("/v1/chat/completions", ["timeout"]), ("/speech-to-text", [403]), ("/text-to-speech", [422])):
        mock.fail[path] = list(err)
        if path == "/speech-to-text":
            out.append(keyed.post("/api/assistant/stt", content=wav.silence(1.0), headers={**H, "Content-Type": "audio/wav"}))
        elif path == "/text-to-speech":
            out.append(keyed.post("/api/assistant/tts", json={"text": "Hi.", "language": "en-IN"}, headers=H))
        else:
            out.append(keyed.post("/api/assistant/chat", json={"message": "x", "language": "en-IN"}, headers=H))
    assert [r.status_code for r in out[-5:]] == [502, 502, 504, 502, 502]
    for r in out:
        blob = r.text + json.dumps(dict(r.headers)) if r.headers.get("content-type", "").startswith("application/json") else json.dumps(dict(r.headers))
        assert FAKE_KEY not in blob and UPSTREAM_SECRET not in blob
    assert FAKE_KEY not in caplog.text and UPSTREAM_SECRET not in caplog.text
    assert "Check SARVAM_API_KEY" in out[-5].json()["detail"]


def test_case_text_never_in_outbound_payload(keyed, mock, monkeypatch):
    monkeypatch.setenv("SHOW_TEXT", "1")
    from irlegal.common.toy import toy_bundle
    corpus, _, _ = toy_bundle()
    res = keyed.post("/api/search", json={"query_id": "Q-TE2", "k": 10}, headers=H).json()["results"]
    secrets_ = set()
    for c in corpus.cases():
        secrets_.add(c.title)
        secrets_.update(p for zone in c.zones.values() for p in zone if len(p) > 25)
    ctx = {"kind": "search", "query_id": "Q-TE2", "ranker": "ours", "temporal_filter": True,
           "results": [{**r, "court": r.get("meta", {}).get("court"), "year": (r.get("meta", {}).get("date") or "")[:4], "title": next(iter(secrets_)),
                        "snippet": "SNIPPET-THAT-MUST-NOT-LEAK", "neighbours": [{"neighbour_id": "T1", "similarity": 0.4}]} for r in res],
           "text": "PASTED-QUERY-TEXT-MUST-NOT-LEAK", "metric": {"name": "dev MAP", "value": 0.2}}
    r = keyed.post("/api/assistant/chat", json={"message": "Explain these results", "context": ctx, "language": "en-IN", "page": "/search"}, headers=H)
    assert r.status_code == 200 and r.json()["context_used"] is True
    sent = mock.bodies()
    assert res[0]["doc_id"] in sent                                            # ids and numbers do go
    assert "SNIPPET-THAT-MUST-NOT-LEAK" not in sent and "PASTED-QUERY-TEXT-MUST-NOT-LEAK" not in sent
    leaked = [s for s in secrets_ if s and s in sent]
    assert leaked == [], f"case text or title sent to Sarvam: {leaked[:2]}"
    keyed.post("/api/assistant/tts", json={"text": "Short reply.", "language": "en-IN"}, headers=H)
    assert not [s for s in secrets_ if s and s in mock.bodies()]


def test_facts_sheet_has_a_hard_cap(monkeypatch):
    big = {"results": [{"doc_id": f"D{i}", "score": 0.5, "components": {"text": 0.1, "neighbour": 0.2, "authority": 0.3}} for i in range(50)], "query_id": "Q1"}
    s = facts.build(facts.clean_context(big), "/search")
    assert len(s) <= config.FACTS_MAX_CHARS and "Result D0" in s and "Result D10" not in s           # at most 10 results
    monkeypatch.setattr(config, "FACTS_MAX_CHARS", 600)
    assert len(facts.build(facts.clean_context(big), "/search")) <= 600
    assert facts.clean_context({"results": [{"doc_id": "bad id with spaces", "title": "x"}], "query_id": "<script>"}) == {}


def test_csp_forbids_remote_connections():
    c = TestClient(app)
    for path in ("/", "/api/health"):
        csp = c.get(path).headers["content-security-policy"]
        assert "connect-src 'self'" in csp and "script-src 'self'" in csp and "unsafe-eval" not in csp
        assert not re.search(r"https?://", csp)
    html = c.get("/").text
    assert "<script>" not in html and 'src="/ui/boot.js"' in html                # no inline script
