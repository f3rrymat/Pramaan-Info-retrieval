"""Thin httpx REST client for Sarvam AI. Retries only on 5xx; never puts the key, a payload or an upstream body into
an exception message or a log line. Tests swap the transport with set_transport(httpx.MockTransport(...)).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from . import config

log = logging.getLogger("irlegal.assistant")
# httpx/httpcore never log header values, but keep their debug chatter out of the server log anyway.
for _name in ("httpx", "httpcore"):
    _lg = logging.getLogger(_name)
    if _lg.level == logging.NOTSET:
        _lg.setLevel(logging.WARNING)

_transport: Optional[httpx.BaseTransport] = None
_sleep = time.sleep


def set_transport(transport: Optional[httpx.BaseTransport], sleep=None) -> None:
    """Tests only: route every outbound call through a mock transport (and optionally skip backoff sleeps)."""
    global _transport, _sleep
    _transport = transport
    _sleep = sleep or time.sleep


class AssistantError(Exception):
    """A user-facing error. `message` is safe to show: it never contains the key, a payload or upstream text."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class NotConfigured(AssistantError):
    def __init__(self):
        super().__init__(503, "not_configured", "Assistant not configured")


def _upstream_error(status: int) -> AssistantError:
    if status in (401, 403):
        return AssistantError(502, "upstream_auth", "Sarvam did not accept the API key. Check SARVAM_API_KEY on the server.")
    if status == 429:
        return AssistantError(429, "upstream_rate_limited", "Sarvam's rate limit or quota was reached. Wait a moment and try again.")
    if status in (400, 404, 413, 422):
        return AssistantError(502, "upstream_rejected", f"Sarvam rejected the request (status {status}).")
    if status >= 500:
        return AssistantError(502, "upstream_unavailable", f"Sarvam is unavailable right now (status {status}). Try again shortly.")
    return AssistantError(502, "upstream_error", f"Unexpected answer from Sarvam (status {status}).")


def _headers() -> dict:
    key = config.api_key()
    if not key:
        raise NotConfigured()
    return {"api-subscription-key": key, "Accept": "application/json"}


def post(path: str, *, json: Optional[dict] = None, files: Optional[dict] = None, data: Optional[dict] = None, what: str = "call") -> dict:
    """POST to api.sarvam.ai and return the decoded JSON body. Retries up to RETRIES_ON_5XX times on 5xx only."""
    headers = _headers()
    timeout = httpx.Timeout(config.TIMEOUT_READ, connect=config.TIMEOUT_CONNECT)
    attempt = 0
    with httpx.Client(base_url=config.BASE_URL, timeout=timeout, transport=_transport) as client:
        while True:
            attempt += 1
            t0 = time.perf_counter()
            try:
                r = client.post(path, json=json, files=files, data=data, headers=headers)
            except httpx.TimeoutException:
                log.warning("sarvam %s: timeout", what)
                raise AssistantError(504, "upstream_timeout", "Sarvam did not answer in time. Try again.") from None
            except httpx.HTTPError as e:
                log.warning("sarvam %s: network error %s", what, type(e).__name__)
                raise AssistantError(502, "upstream_unreachable", "The server could not reach Sarvam. Check the network connection of the server.") from None
            ms = (time.perf_counter() - t0) * 1000
            if r.status_code >= 500 and attempt <= config.RETRIES_ON_5XX:
                log.info("sarvam %s: status %s, retry %d", what, r.status_code, attempt)
                _sleep(0.4 * attempt)
                continue
            if r.status_code >= 400:
                log.warning("sarvam %s: status %s after %d attempt(s)", what, r.status_code, attempt)
                raise _upstream_error(r.status_code)
            log.info("sarvam %s: ok in %.0f ms", what, ms)
            try:
                return r.json()
            except ValueError:
                raise AssistantError(502, "upstream_bad_json", "Sarvam returned an answer that is not JSON.") from None
