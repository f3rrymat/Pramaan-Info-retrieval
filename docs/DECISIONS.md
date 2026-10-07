# DECISIONS.md (read this first; it overrides the Master Spec and SPEC_CHANGES.md where they differ)

Project: role-aware, leak-safe prior case retrieval, CSD358 IR hackathon, track T6.
Numbers in Section 2 come from a real run on the downloaded files. Anything marked **[CHECK]** has not been verified yet: verify it with `scripts/inspect_data.py` and record the result in `docs/data_notes.md`.

---

## 1. Decisions

| # | Decision |
|---|---|
| D1 | **Dataset: IL-PCSR only** (local copy in `data/ilpcsr/`, five parquet files). Not IL-PCR, not IL-TUR. One **shared** precedent pool, so `eval_pool: shared`. |
| D2 | **N3 (leak-safe authority) stays.** The authority signal is real on this dataset (Section 2). SPEC_CHANGES option (a) applies. |
| D3 | **Headline query = Facts + Issues only** (`schema.QUERY_ZONES`). Reference rows may use the full judgment, but it contains the court's precedent analysis, which names cited cases, so it is never the headline. |
| D4 | **Gold fields are labels, never inputs.** For queries: `relevant_precedent_ids`, `relevant_precedents`, `relevant_statute_ids`, `relevant_statutes` must never reach a ranker, an index, an authority feature or a query view. Query statutes come only from the statute normaliser run on the query's own Facts+Issues text. |
| D5 | **Split roles.** Train queries: authority graph (with leave-one-out when a train query is itself being scored) and zone-pair weight learning (a sample of at most 1,500 queries is fine). Dev queries: tuning and model selection. **Test queries: touched once, at the end, behind an explicit `--final` flag.** Never tune on test. |
| D6 | **Authority graph = pool-internal citation edges + TRAIN-query edges only.** Dev and test queries are never edges. |
| D7 | **Net-score weights are non-negative** (spec 9.5). This blocks the pool artifact in Section 3 from being exploited as "inverse popularity". |
| D8 | **Existing contract change (additive, one PR):** extend `schema.ZONES` by appending two zones after the existing six: `statute_analysis` and `precedent_analysis`. The first six stay identical. Update `tests/test_contracts.py` to check the prefix. Nothing else in `common/` changes without asking. |
| D9 | **UI stack: the starter's FastAPI shell**, not Streamlit. UI is not graded, so build it last and keep it simple. |
| D10 | **No git operations for now** (no add, commit, push, config). Commits come later, by each member, under roll numbers. |
| D11 | **Privacy:** never print case text or titles to the terminal or logs. Reports contain aggregates only. `data/`, index files and `results/` are never committed or uploaded (dataset terms: research use only, no redistribution). |

## 2. Verified facts about the real data (from a run on 2026-10-06)

| Item | Value |
|---|---|
| Files | train_queries, dev_queries, test_queries, precedent_candidates, statute_candidates (.parquet) |
| Rows | train queries 5,017; dev 627; test 627; precedent pool 3,183; statutes 936 |
| Columns (queries and pool) | id, case_title, date, jurisdiction, text (list of paragraphs), rhetorical_roles (list), relevant_statutes, relevant_statute_ids, relevant_precedents, relevant_precedent_ids |
| Columns (statutes) | id, provision_name, text |
| Role labels (train query paragraphs) | Precedent Analysis 58,766; Court Reasoning 28,606; Statute Analysis 27,190; Conclusion 24,845; Issue 19,379; Facts 14,731; Argument by Petitioner 13,250; Argument by Respondent 8,838; NONE 663 |
| Parseable date | train 94.3%; dev 93.3%; test 93.8%; pool 86.8% |
| Distinct jurisdictions | train 28; dev 27; test 26; pool 17 |
| Top train-query jurisdictions | Delhi District Court 638; Delhi High Court 622; Punjab-Haryana High Court 531; Gujarat High Court 348; Supreme Court of India 336 |
| Relevant precedents per query (mean) | train 2.70; dev 2.72; test 2.58 |
| Relevant ids inside the pool | 100% for train, dev and test |
| Distinct relevant ids cited by some train query | dev 89.2%; test 86.6% |
| Query ids that also occur in the pool | train 0.3%; dev 0.6%; test 0.5% (always exclude the query's own case) |

**Consequences**
- With about 2.6 relevant precedents per query, P@10 cannot be high. **Headline metrics: Recall@k (5, 10, 20), MAP, MRR, nDCG.** P@k and F1@k are secondary tables.
- Role label mapping (D8): Facts to `facts`; Issue to `issues`; Argument by Petitioner and Argument by Respondent to `arguments`; Court Reasoning to `reasoning`; **Conclusion to `decision`**; Statute Analysis to `statute_analysis`; Precedent Analysis to `precedent_analysis`; NONE to `other`.
- Court mapping: "Supreme Court of India" to `SC`; names containing "High Court" to `HC`; everything else to `OTHER`. The court prior is applied to candidates (the pool).
- Dates: if the query date or the candidate date is missing, do not apply the temporal filter to that pair. Report the share of pairs where it was applied. Report results with and without the filter as separate rows.

## 3. Pool artifact to check before trusting any authority result [CHECK]
If the precedent pool was built as "every precedent cited by some query in any split", then a pool document with **zero training citations** is, by construction, cited by some dev or test query. That would make low popularity itself a leak. `inspect_data.py` must report: (a) the share of pool ids cited by at least one query in any split; (b) among pool ids with zero train in-degree, the share that are relevant to some dev or test query. If (b) is high, document it in `docs/data_notes.md`, keep weights non-negative (D7), and state it in the report.

## 4. Baselines and evaluation protocol
- Candidate set for every query: the full precedent pool (3,183), minus the query's own id.
- Baselines, all reported on dev during development: **random**; **popularity-only** (rank by train in-degree, ignoring the query); **tf-idf lnc.ltc, full text**; **BM25, full text**; **BM25, Facts+Issues**.
- The authority gain must be compared against the popularity-only baseline, otherwise popularity gets credited to the model.
- Query text is scrubbed of case-citation strings (AIR, SCC, SCR, SCALE, "v." party pairs with years) before it is used; log how many patterns were removed. Check whether Facts and Issue paragraphs still name cited cases.
- Ablation ladder, leakage audit and significance tests follow Master Spec Section 10.

## 5. Novelty status (be honest in the report)
- **N1** learned query-zone x document-zone matrix: kept. Cite IIR 6.1.2 (weighted zone scoring) and BM25F [M]. The claim is the *cross* matrix on rhetorical-role zones for precedent retrieval, and what it shows.
- **N2** statute channel from text-normalised tokens (not from gold annotations): kept. Evaluate normaliser accuracy on a labelled sample.
- **N3** leak-safe authority: kept, with the popularity-only baseline and the Section 3 check.
- **N4** efficiency study (champion lists, authority tiers, cluster pruning): a measured study of course techniques, not a novelty claim.
- **N5 crawl simulation, N6 issue decomposition:** stretch, only after the core works.
- Role-based queries are not ours (TraceRetriever did it). Do not claim them.

## 6. Reference code policy
`reference/stare-ir/` (read-only, git-ignored, written earlier today for this same project) may be read and ported with attribution in `AI_USE.md`. Known issues, do not copy blindly: its `role_to_zone` does not map **"Conclusion"** (it falls into `other`); it has no citation scrubbing; its "full" mode is a reference setting, not a headline; its statute bridge uses doc-side gold annotations (not in v1). Do not copy its folder layout; keep `src/irlegal/`.

## 7. Build order and handoff
1. **Phase A:** data inspection, contract extension (D8), loader, preprocessing, index, baselines on dev.
2. **Phase B:** statute normaliser, zone-pair scoring and learning, authority, net score, fusion, explanations.
3. **Phase C:** evaluation harness, ablations, leakage audit, efficiency modules, API routers, minimal UI panels.
4. **About 70% = end of Phase C.** Remaining work for the next member: query parser (Boolean, phrase, proximity, wildcard, spelling, Soundex), crawl simulation, UI polish, README assembly, report figures, tests.
5. Before handing over: `python -m pytest -q` passes; write `docs/STATUS.md` (done, in progress, not started, known issues, commands to run); **delete `data/`, index files, `results/`, `.venv` and any token before zipping.** The next member downloads the dataset with their own account.

## 8. Working rules for the builder
- One phase per session. Keep replies short: a summary, never whole files.
- Never invent numbers, statistics or citations. Every reported number comes from a saved run in `results/`.
- Work only inside the workstream folders named in the Master Spec Section 11.
- If the real data contradicts this file, stop, say so, and propose the fix. Do not silently adapt.

## Phase A review (D12 to D17)
D12 "Court Disclosure" (pool only): profile it against the query-side "Court Reasoning" using mean relative paragraph position, share in the last 10% of paragraphs, mean tokens and distinctive words. If its mean relative position is within 0.15 of Court Reasoning's and under 50% of it sits in the last 10% of paragraphs, map it to `reasoning`; if over 50% sits in the last 10%, map it to `decision`; otherwise keep it as `other` and report. Loader level, pool only. A human spot check may override.
D13 N2 is redefined as a STATUTE BRIDGE because query text is masked. Query side: predict the top-m provisions by retrieving over statute_candidates using the query's Facts+Issues only. Doc side: each pool document's relevant_statute_ids (corpus annotation; report coverage) plus normaliser tokens from pool text. A query's gold statute fields are used ONLY to evaluate prediction quality (Recall@k), never as an input anywhere. This replaces the D4 sentence about extracting query statutes with the normaliser.
D14 BM25 must be tuned on dev (k1, b, query-term-frequency handling) and reported as default AND tuned. The bar to beat on the headline is the strongest tuned simple baseline with Facts+Issues queries.
D15 The temporal filter is an ablation row, OFF in the headline until dev shows a net gain. Report that 2.2% of relevant precedents post-date their query.
D16 Headline comparisons use Facts+Issues queries only. Full-judgment rows are reference rows, not comparable.
D17 Two-stage ranking: a first stage yields N candidates per query (N chosen on dev from 300, 500, 1000, with recall@N reported); features and learning run on those. W is learned on at most 1,500 train queries; hyperparameters on dev; test only at the end behind --final.

## Phase B1 review (D18 to D22)
D18 Learned W stays as a reported NEGATIVE result. Try ONE regularised variant, time-boxed: 6 a-priori pairs {facts+issues x whole, facts x facts, issues x issues, issues x reasoning, facts x precedent_analysis, facts+issues x statute_analysis}, non-negative, shrinkage toward the whole-text pair, stopping chosen by 5-fold CV on train. If dev does not beat tf-idf with a bootstrap interval excluding zero, stop and report it as negative. No further W attempts.
D19 Hyperparameters and stopping use 5-fold CV over train queries. Dev is only the final check among at most 3 frozen configurations, with paired bootstrap intervals. Test stays untouched until --final.
D20 Leave-one-out rule: any feature built from train citations (authority, neighbour votes) must exclude the scored train query's own contribution when that query is itself being scored. Dev and test queries are never in any graph or index.
D21 N7 "citing-case neighbours": index the Facts+Issues text of TRAIN queries (own inverted index or sparse lnc.ltc). For a query, take the top-k similar train queries (k from 10, 20, 50, 100; exclude itself), and score each pool document by the sum over neighbours of similarity^p times (neighbour cites document). Evaluate it alone and as a feature. Explanations list neighbour ids and similarities only, never case text.
D22 Net score features (all non-negative weights): text (tf-idf Facts+Issues, or W-variant only if it survives), statute channel, authority (log train in-degree, leave-one-out), neighbour vote, recency (only where both dates parse), court prior. Candidates = union first stage: tf-idf top N, tuned BM25 top N, statute-channel top, popularity top, neighbour-vote top. Report recall at the union size and the mean union size. Temporal filter stays an ablation row (D15).

## Phase B2 review (D23 to D27)
D23 Headline system = Config A (text + neighbour vote + authority, weights frozen from train CV), first stage tf-idf top 1000. The union first stage is a settled negative result (recall 0.808 vs 0.843, no MAP gain). No more first-stage tuning.
D24 Report the headline with and without the temporal filter side by side, on dev and on test.
D25 No further ranking changes; Config A is frozen. The test split is run ONCE at the end of this phase through --final, for: random, popularity, tf-idf, tuned BM25, Config A, Config A + temporal filter, plus labelled full-judgment reference rows. After a final run the runner writes results/final.lock and refuses a second run unless an explicit --allow-rerun flag is passed.
D26 Report caveats: the pool consists of precedents cited in the corpus, which favours citation-based signals; neighbour MAP on train (0.258) exceeds dev (0.194), so test may shift; N7 is a combination of known ideas and must be framed that way.
D27 Do NOT edit app/server.py, app/web/index.html, app.js, styles.css, anything in src/irlegal/query/ other than statutes.py, or src/irlegal/crawl/: another member owns them. If a shell change is needed, list it in docs/STATUS.md.

## Phase C review (D28 to D32)
D28 D27 is lifted: this phase owns src/irlegal/query/ (all files), src/irlegal/crawl/, app/server.py and the web shell. Do not change ranking, evaluation, efficiency, data, preprocess or index code; if a bug there blocks you, report it instead of editing.
D29 Port from reference/stare-ir (boolean.py, names.py, crawler/) only as LOGIC, rewritten against our Index Protocol and zone names (issues, arguments, ...). Positions exist only for facts and issues, so phrase and proximity work on those zones; document this. Credit every ported idea in AI_USE.md.
D30 Headline for README and report: Config A + temporal filter, shown in one table next to Config A without the filter. State that the neighbour feature carries most of the gain, that the pool contains only precedents cited in the corpus, that the final Config A is the re-frozen three-feature version (results/config_a_frozen.json), and that the learned zone-pair matrix and the statute channel are negative or marginal. N7 is a combination of known ideas (citation collaborative filtering, nearest-neighbour citation retrieval); never call it an invention.
D31 SHOW_TEXT stays off by default. Never commit data, index files or case text. The README explains Hugging Face gated access for IL-PCSR; no data in the repo.
D32 Every README and UI number is loaded from files in results/ by script, never typed by hand.

## Phase E: product-grade front end (D33 to D38)
D33 Scope: the front end and its thin backend support only. You own app/ (server, routers, web) and may add scripts/seed_demo_users.py and tests/app/. Do NOT change ranking, evaluation, efficiency, data, preprocess, index, query or crawl code. Existing API response shapes stay unchanged; new endpoints are additive and live in new router files.
D34 Stack: vanilla JavaScript ES modules, plain CSS with design tokens, no framework, no build step, no CDN, no network calls. Everything works offline. Vendor any library locally under app/web/vendor with its licence file (a small chart library is allowed; hand-written SVG is preferred where simple). Fonts: self-host under app/web/fonts if they can be downloaded now, otherwise use a good system font stack. Never load fonts or scripts from a remote host.
D35 Honesty: no lorem ipsum, no invented statistics, testimonials, logos, user counts or team names. Every number shown comes from the API or from files in results/ (D32). Do not describe the sign-in as dataset access control. No personal names anywhere in the UI; use workstream labels if attribution is needed.
D36 Data safety: case text and titles stay hidden unless the server runs with SHOW_TEXT=1, and signing in never changes that. Snippets are at most 200 characters. Saved searches and history store ids, parameters and timestamps only, never case text. Screenshots must not contain case text.
D37 Auth (local, demo-grade, additive): SQLite at data/app.db (git-ignored); passwords hashed with hashlib.scrypt and a per-user salt; signed HttpOnly SameSite=Lax session cookie with a secret generated on first run into data/ (git-ignored); simple rate limit on sign-in; no passwords or secrets in the repo, in logs or in the README. scripts/seed_demo_users.py creates three roles with randomly generated passwords written once to data/demo_credentials.txt (git-ignored) and prints only the file path. Roles: Researcher (search, compare, save), Analyst (adds Evaluation, Leakage and Efficiency dashboards), Admin (adds Index Inspector, system status, user list). Each role has a distinct accent colour and a visibly different navigation, not just different permissions. An AUTH_REQUIRED=0 environment option lets the app run without sign-in for the video and tests; default is on.
D38 Verification: 122 existing tests still pass; add API tests for the new endpoints; zero console errors on every page; use Playwright for screenshots if it can be installed as a dev-only dependency (requirements/dev.txt), otherwise jsdom, and say which. Do not run the test split or any git command.

## Phase F: assistant, research notes, livelier UI (D39 to D45)
D39 Scope: you own app/ (server, routers, web), scripts/make_readme.py, docs/research_notes.md, AI_USE.md, .env.example and tests/app/. Do NOT change ranking, evaluation, efficiency, data, preprocess, index, query or crawl code. Existing API response shapes stay unchanged; new endpoints are additive and live in new router files.
D40 D34 is amended for ONE thing only: a server-side assistant router may call the Sarvam AI REST API (https://api.sarvam.ai, header api-subscription-key). The browser still loads no remote resources and never talks to Sarvam; set connect-src 'self' in the CSP. The whole app must work exactly as before with no key and no network; the assistant then shows "Assistant not configured" and nothing else changes.
D41 Secrets: the key is read from the environment variable SARVAM_API_KEY only. Never in the repo, in logs, in error messages, in the browser, in screenshots or in tests. Add .env.example with an empty SARVAM_API_KEY= line and add .env to .gitignore. The README explains export via read -s.
D42 Privacy: case text and case titles are NEVER sent to Sarvam, even when SHOW_TEXT=1. The assistant's context is a "facts sheet" built on the server from: files in results/, docs/ (README, STATUS, research_notes), and, for the current search, ids, courts, years, scores and score components. Pasted query text from the Search box is never forwarded. The user's own typed question or recorded audio does go to Sarvam when the assistant is used: show a one-time consent notice saying so, require a click to accept, and remember the choice in the browser only.
D43 Honesty: the assistant explains the system, the results and the evaluation. It is an AI helper, not legal advice, and says so in its first message. Every number it states must come from the facts sheet; if a number is not there it says it does not have it. No invented statistics. Label it "AI assistant (Sarvam)" in the UI.
D44 Research notes are data in docs/research_notes.md and are rendered into the README by scripts/make_readme.py. Use only references marked VERIFIED or RE-CHECK in the list below, never invent a reference, author, venue or result, and never claim a method as our invention if a paper below did it. If you have network access, re-check every RE-CHECK item (title, authors, venue, year) and mark the result; if not, keep it marked RE-CHECK in the file. Numbers in the README still come from results/ (D32).
D45 UI motion: everything animated respects prefers-reduced-motion; no layout thrash; keep interaction at 60 fps on a normal laptop; no remote fonts, scripts or images; contrast stays AA; the existing 155+ tests, scripts/ui_qa.py and the page sweep keep passing.

## Phase G: interface pass. Scope: app/web and additive read-only backend support. No change to ranking, evaluation, efficiency, data, preprocess, index, query or crawl code. Numbers come from the API or results/. No frameworks or remote resources. Motion limited to transform and opacity with reduced-motion support.
