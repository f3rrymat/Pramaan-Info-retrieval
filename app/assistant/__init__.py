"""Server-side AI assistant (Sarvam AI), DECISIONS D39 to D43.

The browser never talks to Sarvam: every call goes through app/routers/assistant_router.py. The key is read from the
environment variable SARVAM_API_KEY only, at call time, and never appears in a response, a log line or an error.
Case text and case titles are never sent (D42): the model's context is a facts sheet built from results/ and docs/
plus ids, courts, years, scores and score components of the current search.

Modules: config (environment, limits), languages (per-service language lists), client (httpx REST calls, retries on
5xx only), wav (WAV parsing and merging), facts (facts sheet with a hard size cap), ratelimit (per-session sliding
window), service (chat, speech to text, text to speech, language identification, modality rule).
"""
