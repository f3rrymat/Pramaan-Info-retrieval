# STATUS (Pramaan; Phase G in progress, see docs/PHASE_G_PROGRESS.md)

All numbers live in `docs/results_tables.md` (generated from saved runs in `results/`). Nothing below is typed by hand from memory.

## Done
- **Data and index (WS1):** IL-PCSR loader with role/court/date mappings (D12: pool "Court Disclosure" -> reasoning), citation scrubber, tokenizer, Porter stemming, per-zone inverted index (+ derived `fi` and `all` zones), positions for facts/issues, gap + variable-byte compression, skip pointers, persisted to `data/index/`.
- **Ranking (WS3):** tf-idf lnc.ltc, BM25 (tuned), statute bridge (N2, marginal), authority with leave-one-out, **N7 citing-case neighbours**, net score, **Config A frozen** (`results/config_a_frozen.json`, train CV only), explanations (ids and numbers only).
- **Evaluation (WS4):** one runner for dev and test (macro and micro averages, per-query CSV, 11-point PR data, paired bootstrap), leakage audit (a-d), efficiency study (heap, elimination, champion lists, authority tiers, cluster pruning), report figures and tables.
- **Negative results kept:** learned zone-pair matrix W and its regularised variant (D18), union first stage (D23), tiers and elimination as pruning (large quality loss), statute channel (+0.001 MAP).
- **API and pages:** routers `ws1_index`, `ws3_search`, `ws4_eval` and the pages of the Phase E front end; the old panel helper `app/web/vendor/viz.js`. Real mode is automatic when `data/index` and `results/config_a_frozen.json` exist (force toy with `IRLEGAL_MODE=toy`). Titles and snippets (<= 200 chars) only with `SHOW_TEXT=1`.
- **Final test run: executed once** (`results/final.lock`). A second run needs `--allow-rerun` and must be reported as such.
- Tests: `python -m pytest -q` (the API smoke tests use the toy corpus; one real-mode test checks that no text is returned and skips when the index is absent).

## Phase E: product-grade front end (done)
- **Stack.** Plain JavaScript modules and CSS, no framework, no build step, no CDN, no network calls. Fonts (Inter, JetBrains Mono) are self-hosted in `app/web/fonts` with their OFL licences. Tokens live once in `app/web/styles/tokens.css` (light and dark, zone palette, role accents); components in `components.css`; the living style guide is `#/styleguide`.
- **Where things are.** `app/web/index.html` + `app/web/ui/` (main, router, shell, store, api, components, charts, case drawer, `pages/*`). The Phase C and D panels, `app.js`, `styles.css`, the vendored chart library and `/api/panels` were deleted in the cleanup after Phase E.
- **Auth (demo-grade, D37).** `app/security.py`, routers `auth_router.py`, `user_data.py`, `system_router.py`, `extras.py`. SQLite `data/app.db`, scrypt hashes with a per-user salt, HMAC-signed HttpOnly SameSite=Lax cookie, secret in `data/app_secret.key` (mode 0600), sign-in rate limit (5 failures per 5 minutes), `X-Requested-With` check on writes. `python scripts/seed_demo_users.py` writes random passwords to `data/demo_credentials.txt` and prints only the path. `AUTH_REQUIRED=0` disables sign-in (`DEMO_ROLE` picks the role). It separates what each role sees; it is **not** dataset access control.
- **Quick sign-in (local demo only).** `make demo` sets `DEMO_QUICK_LOGIN=1`: the sign-in page shows three role cards and `POST /api/auth/quick` signs in as a role without a password and issues the same signed HttpOnly cookie. It answers only if the flag is set AND the client address is loopback (127.0.0.1, ::1; forwarding headers are ignored); otherwise 404. Users are created on startup if missing, with random passwords that are never printed. Roles are still enforced. **Local demo convenience only: never enable it on a shared or hosted machine; it is not access control.** `DEMO_QUICK_LOGIN=0 make demo` or `uvicorn` without the variable keeps password-only sign-in.
- **Roles.** Researcher: Search, Compare, Query Lab, Saved, History, How it works, About. Analyst adds Evaluation and Efficiency and crawl. Admin adds Index Inspector, System status, Users. Each role has its own accent colour, navigation and start page.
- **Data safety (D36).** Titles and 200-character snippets only with `SHOW_TEXT=1`. Saved searches and history keep ids, settings and times; the server rejects any other field. Pasted text is never stored and never put in the URL.
- **Verification.** `python -m pytest -q` (including `tests/app/`), and the dev-only Playwright scripts (`requirements/dev.txt`, then `python -m playwright install chromium`): `scripts/ui_check.py` (one page set), `scripts/ui_matrix.py` (every page, light and dark, 1280 and 375 px: console errors, remote requests, horizontal overflow), `scripts/ui_qa.py` (sign-in, roles, sign-out, expired session). A curated set of screenshots (14 files: Search, Case drawer, Compare, Evaluation, Efficiency, How it works and Sign-in, light and dark) is in `docs/figures/ui/`; every other screenshot goes to the git-ignored `docs/figures/ui_all/`. None contains case text.
- **Known limits.** Phase E was exercised in headless Chromium only; Firefox and Safari were not run. Browsers log a console error for every intentional 401 or 403, so the sign-in QA separates those expected lines from real errors. The evaluation overlay's AP is truncated at rank 100 and says so. Recency is not a returned component of Config A, so the stacked bar shows text, neighbours and authority.

## Phase F: assistant, research notes, livelier UI (done)
- **AI assistant (Sarvam), D40 to D43.** Server side: `app/assistant/` (config, languages, client with retries on 5xx only and safe errors, WAV parsing and merging, facts sheet with a hard cap, per-session rate limit, service) and `app/routers/assistant_router.py`: `GET /api/assistant/status`, `POST /api/assistant/chat`, `POST /api/assistant/stt` (raw WAV body; no new dependency), `POST /api/assistant/tts` (returns audio/wav, chunked by sentence). Models and limits follow the Sarvam docs read on 2026-10-07: chat `sarvam-105b` (`sarvam-m` and `sarvam-30b` are deprecated), STT `saaras:v4` mode transcribe with a 30 s REST limit, TTS `bulbul:v3` speaker `shubh` with 2500 characters per request, language identification `/text-lid`. Overrides: `SARVAM_CHAT_MODEL`, `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER`, `SARVAM_REASONING_EFFORT`.
- **Privacy.** Case text and titles are never sent, even with `SHOW_TEXT=1`; the browser sends ids and numbers only, and the server whitelists them again (`facts.clean_context`). Pasted search text is never forwarded. A one-time consent notice (remembered in the browser) precedes the first question. The conversation lives in `sessionStorage` only.
- **Front end.** Floating "Ask" button on every page (Alt+A), side panel and the full page `#/assistant` (same component); text and voice input; replies follow the input mode (voice in: spoken + text; text in: text only; Settings > Speak replies overrides); Listen on every answer; Stop speaking button and Esc; "Tap to play" when autoplay is blocked; mic states idle, recording (live waveform and 30 s countdown), transcribing, thinking, speaking; recordings are re-encoded in JavaScript as 16 kHz mono WAV; language chip (auto-detect or a chosen language from the supported list); page-specific suggested questions; Explain this result (result cards, case drawer) and Explain this metric (KPI cards); copy, retry, clear.
- **Motion (D45).** FLIP re-ranking (weight sliders and ranker changes), staggered entrance, animated rings and stacked bars, count-up KPIs, shared-element morph from a result card into the case drawer, route fade, skeletons for charts, chart draw-in and linked hover across charts, tables and legends, neighbour graph with gentle physics and drag, fuzzy command palette with recent actions, undo toasts (save; deferred delete of saved items and history), press and focus feedback, a live pipeline strip on Search with server timings (`Server-Timing` header from `/api/search`; the JSON body is unchanged). Settings > Reduce motion, which also follows the OS setting.
- **Security headers.** `app/server.py` sends a Content-Security-Policy with `connect-src 'self'` (no inline scripts: the pre-paint theme script moved to `app/web/ui/boot.js`), `Permissions-Policy: microphone=(self)`, `nosniff`, `no-referrer`.
- **README.** `scripts/make_readme.py` now renders `docs/research_notes.md` (research background, contributions, IR concepts with checked file paths, screenshots, limitations and negative results, how the assistant works). Without `results/` it carries the number sections over unchanged from the existing README and prints a warning.
- **Tests and QA.** `python -m pytest -q`: 172 passed, 1 skipped (adds `tests/app/test_assistant.py`, 13 tests with Sarvam mocked and no key, and `tests/app/test_phase_f_static.py`). `scripts/assistant_qa.py` (Playwright, fake microphone, mocked assistant endpoints; 28 checks), `scripts/motion_qa.py` (animations on, synthetic `/api/search` with made-up ids; 13 checks; frame pacing while dragging a weight slider in headless Chromium: median 16.7 ms, p95 about 33 ms, indicative only), `scripts/ui_qa.py` (38 checks; the deliberate researcher-to-`/api/eval` 403 is now classed as expected) and `scripts/ui_matrix.py` (now includes `#/assistant`; 15 pages x light/dark x 1280/375 px, no console errors, no overflow, no remote requests). All were run in toy mode; real mode needs the data. `scripts/assistant_smoke.py` makes one tiny real call per service when `SARVAM_API_KEY` is set and prints only OK or an error class.

## Phase D additions (all done)
- **Query language** (`query/parser.py`, `query/boolean.py`): AND, OR, NOT, parentheses, phrases, proximity `/k` and `pre/k`, zone restriction, `court:` `year:` `before:` `after:` filters; AND smallest-list-first with a benchmark (`results/and_benchmark.json`). Positions exist only for facts and issues, so phrase and proximity search those two zones.
- **Tolerant retrieval** (`query/tolerant.py`): 3-gram wildcards, edit-distance suggestions, Soundex.
- **Shell and panels**: mode banner (real or toy, text shown or hidden) from `/api/health`; Search preselects a dev query and the headline system (Config A + temporal filter); Query Lab, Index Inspector, Evaluation, Efficiency, How it works (pipeline SVG, concept map, numbers loaded from saved runs). JavaScript was syntax-checked with node and every endpoint was exercised through the API; it was **not clicked through in a browser** here.
- **Crawl simulation** (`crawl/*`, `scripts/run_crawl_sim.py`) and **issue decomposition** (`query/decompose.py`, `scripts/run_decompose.py`): both reported as measured; neither beats its baseline (priority crawl vs BFS, RRF of issues vs the single query).
- **README** is generated: `python scripts/make_readme.py` (numbers from `results/`, prose from `docs/ws*.md`).

## Still open (humans)
- README "Work division" and `AI_USE.md` reviewer column are `PLACEHOLDER`.
- Get your own Sarvam AI key and the IL-PCSR data; capture the two screenshot slots listed in `docs/research_notes.md` (real assistant answer, real voice mode) and check that they show no case text.
- RE-CHECK items in `docs/research_notes.md`: the IL-TUR per-split pool detail and the content claim of Smucker et al. (2007).
- The 8-page report and the 5-8 minute demo video; each member must be able to explain their module.
- A human spot check of the D12 mapping ("Court Disclosure" to reasoning); a browser check of the UI (layout, dark mode, keyboard use).
- Optional stretch not built: `query/tools.py` (tool registry for a future agent), live crawling (not allowed without robots.txt review).

## Known issues and caveats (report these)
- **Assistant not exercised against the real Sarvam API in Phase F** (no key in that session). Field names follow the docs read on 2026-10-07 (TTS uses `language_code`); run `python scripts/assistant_smoke.py` with your own key once.
- `/api/search` does not scrub citation strings from **pasted** text (dev queries are scrubbed when the corpus is read); the pipeline strip says "not applied". Changing this would change pasted-text rankings, so it was left for the team to decide.
- Playwright: the QA scripts need a Chromium that matches the installed Playwright version (`python -m playwright install chromium` after `pip install -r requirements/dev.txt`).
- The pool is made of precedents cited in the corpus, which favours citation-based signals (D26). Neighbour MAP on train (0.258) exceeds dev (0.194); the test gain over tf-idf is smaller than the dev gain.
- Query text is masked (`[SECTION]`, `[ACT]`, ...) and pool text is not; statute identities are mostly unavailable on the query side, so N2 is weak.
- 2.3-2.5% of relevant precedents post-date their query, so the temporal filter removes some true positives; it still gains net (reported side by side, D24).
- BM25's tuned optimum (k1=12, b=1) is large; it is within noise of tf-idf. The grid stops there (D14/B2).
- First stage recall@1000 is about 0.84: a hard ceiling for every reranker.
- Efficiency latencies are wall time on one machine in Python; compare candidates scored instead. Champion lists keep full quality; elimination and authority tiers cost 30-60% of MAP.
- A pasted-text query has no date, no train id and no ground truth: temporal filter and relevance badges do not apply.
- `data/cache/*.npz` holds cached feature matrices from Phase B1 (git-ignored; safe to delete).

## Run commands (from the repository root; `export PYTHONPATH=src:.` or use `make`)
```
pip install -r requirements.txt
python scripts/inspect_data.py              # data checks -> results/data_inspect.json
python scripts/build_index.py               # index -> data/index, results/index_report.json
python scripts/tune_bm25.py                 # dev tuning grid (only if you want to redo it)
python scripts/freeze_config_a.py           # Config A weights from train CV
python -m irlegal.evaluation.runner --split dev
python -m irlegal.evaluation.leakage        # dev + train only
python scripts/run_efficiency.py
python scripts/run_w_variant.py             # D18 negative result (needs data/cache from scripts/run_b1.py)
python scripts/make_report_assets.py        # figures + docs/results_tables.md
python scripts/bench_and.py                 # AND order benchmark
python scripts/run_crawl_sim.py             # crawl simulation (no network)
python scripts/run_decompose.py             # issue decomposition on dev
python scripts/make_readme.py               # README from docs/ws*.md, docs/research_notes.md and results/
read -rs SARVAM_API_KEY && export SARVAM_API_KEY   # optional: the AI assistant (never paste the key anywhere else)
python scripts/assistant_smoke.py           # optional: one tiny real call per Sarvam service; prints OK or an error class
python scripts/assistant_qa.py              # dev-only Playwright QA of the assistant (mocked endpoints, fake microphone)
python scripts/motion_qa.py                 # dev-only Playwright QA of the animations (synthetic search results)
SHOW_TEXT=0 make demo                       # API + UI on http://127.0.0.1:8000
python -m pytest -q
python -m irlegal.evaluation.runner --split test --final --allow-rerun   # DO NOT run again without a reason
bash scripts/package_handoff.sh             # zip without data, results, .git, tokens
```
Order for a fresh machine: download the dataset yourself (own account), `build_index.py`, `run_b1.py` (feature cache, statute bridge), `run_b2.py` (ablation ladder and neighbour grid; writes `results/b2_ablation_dev.json`, needed by the runner), `freeze_config_a.py`, then the dev runner.

## Before zipping
`bash scripts/package_handoff.sh` excludes `data/`, `results/`, `.git`, `.venv`, caches, and aborts if a parquet, pickle, npz/npy, index blob or token file would be inside. Delete any token from your shell history and environment as well.

## Phase G: interface pass (Pramaan), see docs/PHASE_G_PROGRESS.md for the task-by-task state
- Display name is **Pramaan** in every user-visible string; packages, folders, env vars and file paths are unchanged.
- New: public overview page at `#/` (also shown after sign-out), brand mark and Fraunces display font (OFL, `app/web/fonts/LICENSE-fraunces.txt`), search hero bar and strategy switcher, analytics pill, redesigned result cards, evaluation dashboard (bento, dev/test toggle, story-mode ladder, animated leakage audit, PR hover crosshair), compare replay, efficiency explorer and crawl replay, Index Inspector with blocks and skip-pointer demo, How it works scroll story, progress bar, status polling with offline banner and backoff, expired-session dialog, notification history.
- Additive API: `GET /api/public/landing`, `GET /api/public/provenance`, `results[].meta.cited_by` in `/api/search` (real mode), `ord` per posting in `/api/inspect/index`. No ranking, evaluation, efficiency, data, preprocess, index, query or crawl code changed.
- Checks: `python -m pytest -q` (182 passed), `scripts/ui_qa.py` (41), `tests/app/qa/shell_checks.py`, `tests/app/qa/final_gates.py` (quick run only), `scripts/motion_qa.py`, `scripts/assistant_qa.py`, `scripts/ui_matrix.py`.
- Not done: full-viewport gate matrix, frame sequences, videos, after-scores in `docs/ui_audit.md`. Firefox and Safari were not tested (Chromium only; View Transitions fall back to a CSS fade).
- **results/ ships with the project** (in the handoff zip and committable) and contains aggregates, ids and scores only; scan in `docs/results_scan.md`. `data/`, index files, `.db`, credentials and `.env` are still excluded. Test: `tests/app/test_packaging.py`.
