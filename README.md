# Pramaan

**Pramaan: precedent finder for Indian law.** Role-aware, leak-safe prior case retrieval.

CSD358 Information Retrieval hackathon, track T6 (vertical search), domain: Indian law. Given the facts and issues of an undecided case, the system ranks earlier Indian judgments it should cite and explains each result. *Every number below is loaded from files in `results/` by `scripts/make_readme.py`.*

## What Pramaan is

When a lawyer writes a judgment, they cite earlier judgments (precedents). Pramaan takes the facts and issues of a case that has not been decided yet and ranks the earlier judgments it is most likely to cite, then shows the reasons for each result: which similar cases cite it, how often it is cited, and how the score is made up. It is a student research prototype built on the IL-PCSR corpus, not legal advice, and it runs on one machine with no outside services (the AI assistant is optional).

## What works

- Classical IR, implemented here: per-zone inverted and positional index with gap + variable-byte compression and skip pointers; tf-idf (lnc.ltc) and BM25; Boolean, phrase, proximity, zone, wildcard, spelling and Soundex queries; heap top-K, index elimination, champion lists, authority tiers and cluster pruning; reciprocal rank fusion; a Mercator-style crawl **simulation**.
- **Config A**: tf-idf first stage (top 1000) re-scored with text + neighbour vote + authority (weights frozen from 5-fold CV on train).
- A leakage audit, an efficiency study, paired bootstrap intervals, an API with a Search, Query Lab, Index Inspector, Evaluation, Efficiency and How it works UI.
- An optional **AI assistant (Sarvam)** that explains the system, the results and the evaluation by text or voice; it never sees case text (see *How the assistant works*).

### Planned

A cited-answer layer, an agentic research flow, Indic and multilingual search, a learned re-ranker and other citation-linked fields are planned; see the Roadmap below. None of them is built.

## How to run it

```bash
git clone <repository-url> && cd <repository-folder>        # your own copy; no data is in the repository
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # Python 3.10+
```

### Data (gated, never in this repository)

IL-PCSR is released for research use only and is gated on Hugging Face. Create an account, open the IL-PCSR dataset page of the Exploration-Lab authors, accept the conditions (research use only, no commercial use, no redistribution), then download the five parquet files (`train_queries`, `dev_queries`, `test_queries`, `precedent_candidates`, `statute_candidates`) into `data/ilpcsr/`. Each member uses their own account and token. `data/`, `results/` and index files are git-ignored and must not be shared.

### Run

```bash
make data      # data checks (aggregates only)
make index     # build and persist the index
make eval      # dev baselines, Config A, leakage audit, efficiency, figures
make demo      # API + UI on http://127.0.0.1:8000  (sign-in on by default; AUTH_REQUIRED=0 turns it off; case text hidden unless SHOW_TEXT=1)
make test      # pytest
```

Optional, for the AI assistant: get your own Sarvam AI key and put it in the environment of the shell that starts the server, without echoing it and without writing it to a file:

```bash
read -rs SARVAM_API_KEY && export SARVAM_API_KEY     # paste the key, press Enter; nothing is shown or saved in history
make demo
python scripts/assistant_smoke.py                    # one tiny chat, speech-to-text and text-to-speech call; prints OK or an error class only
unset SARVAM_API_KEY                                 # when you are done
```

Without `SARVAM_API_KEY` the app works exactly as before and the assistant shows "Assistant not configured". `.env.example` lists the variables; the app reads the process environment only, never a `.env` file, and `.env` is git-ignored. Never paste the key into the code, a chat, an issue or a screenshot.

### Sign-in, roles and the web app

The web app asks for a local sign-in by default. Create the three demo accounts once with `python scripts/seed_demo_users.py`: it writes random passwords to `data/demo_credentials.txt` (git-ignored, mode 0600) and prints only that file's path. Roles: **Researcher** (search, compare, Query Lab, saved and history), **Analyst** (adds the Evaluation, Leakage and Efficiency dashboards) and **Admin** (adds the Index Inspector, system status and the user list). Each role has its own accent colour and navigation. Set `AUTH_REQUIRED=0` to run without sign-in (for the demo video and tests; `DEMO_ROLE=analyst` picks the role then). Passwords are hashed with scrypt, the session cookie is signed, HttpOnly and SameSite=Lax, and its secret is generated on first run into `data/`. This sign-in only separates what each role sees; it is **not** access control for the dataset, whose own terms apply.

**Quick sign-in (local demo convenience only).** `make demo` sets `DEMO_QUICK_LOGIN=1`, which shows three role cards on the sign-in page; one click signs in as that role with no password and opens Search. The endpoint answers only when the flag is set **and** the request comes from a loopback address (127.0.0.1 or ::1), otherwise it returns 404, and forwarding headers are ignored. Role permissions are still enforced. It is a convenience, **not access control**: never enable it on a shared or hosted machine (`DEMO_QUICK_LOGIN=0 make demo` turns it off, and the password sign-in then works as before).

Case text and titles are hidden unless the server runs with `SHOW_TEXT=1`; signing in never changes that. Saved searches and history store ids, settings and times only. The front end is plain JavaScript modules and CSS (no framework, no build step, no CDN; fonts are self-hosted in `app/web/fonts`), so it works offline; a Content-Security-Policy with `connect-src 'self'` keeps the browser on this server. Press `Ctrl/Cmd+K` for the command palette (fuzzy matching, recent actions), `Alt+A` for the assistant and `?` for shortcuts; `#/styleguide` shows every component in both themes. Animations (gliding result cards, chart draw-in, count-up numbers, the live pipeline strip) follow the system's reduced-motion setting and can be switched off in Settings > Reduce motion.

Frozen weights and tuning artefacts are produced by `scripts/tune_bm25.py`, `scripts/run_b1.py`, `scripts/run_b2.py`, `scripts/freeze_config_a.py`; the final test run is `python -m irlegal.evaluation.runner --split test --final` (once; `results/final.lock`). See `docs/STATUS.md`.

## Research background

What earlier work did, what we take from it and what we do differently. Rows come from `docs/research_notes.md`; a status of RE-CHECK means the reference is not yet confirmed and must be checked before it is cited in the report.

| Paper | What it did | What we take from it | What we do differently or add |
|---|---|---|---|
| **IL-PCSR (EMNLP 2025)** | Released the corpus we use: 936 statutes, a 3,183-case precedent pool and 6,271 queries; citations inside queries are masked with placeholders such as [SECTION], [ACT], [PRECEDENT], [ENTITY]. | The corpus and its masked-query design. | A leak-safe protocol, Facts+Issues-only queries, citation-based features built only from training queries, and a measured leakage audit. |
| **U-CREAT (ACL 2023)** | Introduced the IL-PCR corpus and an unsupervised, event-based retrieval approach. | The prior case retrieval framing and the benchmark lineage. | No event extraction; classic IR index and scoring plus citation signals. |
| **TraceRetriever (arXiv 2508.00679)** | Builds queries from rhetorically significant segments (Facts, Issue) to mimic partial case knowledge; BM25 plus a vector database plus a cross-encoder, fused with reciprocal rank fusion; evaluated on IL-PCR and COLIEE 2025. | The role-based realistic-query idea. It is theirs, not ours. | We use the corpus's own role labels on IL-PCSR, no neural models, and add leak-safe neighbour and authority features and a leakage audit. |
| **Fenced citation context (arXiv 2607.17142)** | Shows that citation-context gains are inflated unless restricted to citations that predate the query, and adds popularity (degree) controls. | A popularity-only baseline and a temporal-fence ablation. | A different corpus and features; our leakage audit targets leave-one-out and how the citation graph is built. |
| **ABAI at COLIEE 2026 (arXiv 2609.26237)** | Reports that citation-graph features give only a small gain once own-citation leakage is removed. | Support for treating own-citation leakage as a real risk. | Our leave-one-out audit measures that risk on IL-PCSR. |
| **Huang et al. (ICAIL 2021)** | Compares a collaborative-filtering method over citation lists with text-based neural methods. | Collaborative filtering over citation lists is prior art for our neighbour vote. | Our neighbours are found by lnc.ltc similarity of Facts+Issues text, with explanations and leave-one-out. |
| **Bhattacharya et al. (IP&M 2022)** | Combines citation-network and text similarity for Indian Supreme Court cases. | The premise that text and the citation network are complementary. | Our net score combines a text score, a neighbour vote and authority, with weights learned on train only. |
| **Dasula et al. (arXiv 2406.01609)** | Cosine similarity over case descriptions plus clustering and classification to suggest citations (US Supreme Court data). | Related prior art for similarity-based citation suggestion. | Indian precedents, a leak-safe evaluation protocol and a neighbour vote over training citations rather than classification. |
| **IL-TUR (ACL 2024)** (part RE-CHECK) | A benchmark of Indian legal tasks that includes prior case retrieval (IL-PCR). | Context for the task. | We moved from its IL-PCR setting to IL-PCSR, which has one shared precedent pool (DECISIONS D1). |
| **IIR (Manning, Raghavan, Schütze 2008)** | The course text: indexes, tolerant retrieval, compression, tf-idf and zone scoring, efficient scoring, evaluation, BM25, crawling. | Every classical component in this repository (see the concept table). | We apply the techniques to rhetorical-role zones of Indian judgments and measure them on IL-PCSR. |
| **BM25 (2009) and BM25F (CIKM 2004)** | The BM25 ranking function; BM25F weights document fields before saturation. | Tuned BM25 as a baseline; BM25F as the reference point for weighting zones. | Our learned query-zone by document-zone matrix is a cross-zone variant; it did not beat tf-idf on dev (a reported negative result). |
| **RRF (SIGIR 2009)** | A simple fusion of ranked lists by summed reciprocal ranks. | RRF for fusing issue sub-queries. | Measured on dev; it hurt here (negative result). |
| **Mercator (1999); Broder et al. (1997)** | Front and back queues with per-host politeness; shingles for near-duplicate detection. | The frontier design and shingle-based duplicate checks of the crawl simulation. | A simulation over the citation graph with courts as hosts; no live traffic. |
| **Smucker et al. (CIKM 2007)** (part RE-CHECK) | Compares significance tests for IR evaluation. | Paired tests over queries; we report paired bootstrap 95% intervals. | We report intervals rather than p-values. |

### References

- S. Paul, D. Ghumare, P. Goyal, S. Ghosh, A. Modi. *IL-PCSR: Legal Corpus for Prior Case and Statute Retrieval*. EMNLP 2025 (main). arXiv:2511.00268. *Status: VERIFIED.*
- Joshi et al. *U-CREAT: Unsupervised Case Retrieval using Events extrAcTion*. ACL 2023. arXiv:2307.05260. *Status: VERIFIED.*
- Nigam, Dubey, Shallum, Bhattacharya. *Segment First, Retrieve Better: Realistic Legal Search via Rhetorical Role-Based Queries* (TraceRetriever). arXiv:2508.00679. *Status: VERIFIED.*
- Liu, Tan, Liu. *Fenced Citation-Context Retrieval for Case Law: Temporal Leakage and Degree Control Across Two Jurisdictions*. arXiv:2607.17142. *Status: VERIFIED.*
- Cho, Park, Choi, Han. *ABAI at COLIEE 2026 Task 1*. arXiv:2609.26237. *Status: VERIFIED.*
- Huang et al. *Context-Aware Legal Citation Recommendation using Deep Learning*. ICAIL 2021. *Status: VERIFIED.*
- Bhattacharya et al. *Legal Case Document Similarity: You Need Both Network and Text*. Information Processing and Management, 2022. arXiv:2209.12474. *Status: VERIFIED.*
- Dasula et al. *Judgement Citation Retrieval using Contextual Similarity*. arXiv:2406.01609. *Status: VERIFIED.*
- A. Joshi, S. Paul, A. Sharma, P. Goyal, S. Ghosh, A. Modi. *IL-TUR: Benchmark for Indian Legal Text Understanding and Reasoning*. ACL 2024. *Status: VERIFIED, re-checked 2026-10-07; part RE-CHECK.*
- C. D. Manning, P. Raghavan, H. Schütze. *Introduction to Information Retrieval*. Cambridge University Press, 2008. *Status: VERIFIED, re-checked 2026-10-07.*
- S. Robertson, H. Zaragoza. *The Probabilistic Relevance Framework: BM25 and Beyond*. Foundations and Trends in Information Retrieval 3(4), 2009. S. Robertson, H. Zaragoza, M. Taylor. *Simple BM25 extension to multiple weighted fields*. CIKM 2004. *Status: VERIFIED, re-checked 2026-10-07.*
- G. V. Cormack, C. L. A. Clarke, S. Büttcher. *Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods*. SIGIR 2009. *Status: VERIFIED, re-checked 2026-10-07.*
- A. Heydon, M. Najork. *Mercator: A scalable, extensible web crawler*. World Wide Web 2(4), 1999. A. Z. Broder, S. C. Glassman, M. S. Manasse, G. Zweig. *Syntactic clustering of the web*. WWW6, 1997. *Status: VERIFIED, re-checked 2026-10-07.*
- M. D. Smucker, J. Allan, B. Carterette. *A comparison of statistical significance tests for information retrieval evaluation*. CIKM 2007. *Status: VERIFIED, re-checked 2026-10-07; part RE-CHECK.*

## Our contributions

Framed honestly: what is ours and what is a known idea applied here. Numbers come from `results/`.

- **A leak-safe evaluation protocol for precedent retrieval on IL-PCSR, with a measured leakage audit.** Scoring training queries without leave-one-out inflates Config A MAP from 0.2681 to 0.8742. Adding dev links to the authority graph (+0.0030 [+0.0018, +0.0043]), switching citation scrubbing off (+0.0004 [-0.0000, +0.0011]) and the temporal filter (+0.0106 [+0.0042, +0.0166]) are measured separately (dev MAP differences with 95% intervals).
- **Realistic Facts+Issues queries using the corpus's own role labels.** The role-based query idea comes from TraceRetriever; the evaluation setting on IL-PCSR and the leak controls are ours.
- **A citing-case neighbour vote with explanations, leave-one-out and a popularity-only baseline.** It is a combination of known ideas (collaborative filtering over citation lists and nearest-neighbour citation retrieval), not a new algorithm.
- **A measured efficiency study of course techniques**: heap top-K, champion lists, authority tiers, index elimination and cluster pruning (see Efficiency).
- **Honest negative or marginal results with intervals**: the learned zone-pair matrix, the statute bridge, the union first stage, issue decomposition, and priority crawling against BFS (see Limitations and negative results).

## IR concepts and where they live

Course reference: Manning, Raghavan and Schütze, *Introduction to Information Retrieval* (IIR), unless another source is named. Every path below exists in this repository (checked by `scripts/make_readme.py`).

| Concept | Course reference | Where in the code | Where you see it |
|---|---|---|---|
| Tokenisation, stop words, Porter stemming | IIR ch. 2 (The term vocabulary and postings lists) | `src/irlegal/preprocess/tokenizer.py`, `src/irlegal/preprocess/normalizer.py` | How it works (Analyse); Index Inspector |
| Inverted and positional index; phrase and proximity queries | IIR ch. 2 (Positional postings and phrase queries) | `src/irlegal/index/inverted.py`, `src/irlegal/index/positional.py`, `src/irlegal/query/parser.py`, `src/irlegal/query/boolean.py` | Query Lab |
| Skip pointers; AND with the smallest posting list first | IIR ch. 2 (Faster postings list intersection via skip pointers) | `src/irlegal/index/skips.py`, `src/irlegal/query/boolean.py`, `scripts/bench_and.py` | Query Lab; `results/and_benchmark.json` |
| Wildcards (3-gram index), edit distance, Soundex | IIR ch. 3 (Wildcard queries; k-gram indexes; Edit distance; Phonetic correction) | `src/irlegal/query/tolerant.py` | Query Lab (suggestions) |
| Index compression: gaps and variable-byte codes | IIR ch. 5 (Postings file compression; Variable byte codes) | `src/irlegal/index/compress.py` | Index Inspector; `results/index_report.json` |
| tf-idf, SMART lnc.ltc, cosine | IIR ch. 6 (Variant tf-idf functions; Document and query weighting schemes) | `src/irlegal/ranking/vsm.py` | Search and Compare (tf-idf) |
| Weighted zone scoring and learning the weights | IIR ch. 6 (Weighted zone scoring; Learning weights); BM25F (CIKM 2004) | `src/irlegal/ranking/zonepair.py`, `scripts/run_b1.py`, `scripts/run_w_variant.py` | Evaluation, Negative results; `results/zone_matrix.json`, `results/w_variant.json` |
| BM25, tuned on dev | IIR ch. 11 (Okapi BM25: a non-binary model); Robertson and Zaragoza (2009) | `src/irlegal/ranking/bm25.py`, `scripts/tune_bm25.py` | Compare rankers; `results/bm25_tuning.json` |
| Net score: weighted sum of normalised features | IIR ch. 6 (Weighted zone scoring) | `src/irlegal/ranking/netscore.py`, `src/irlegal/ranking/pipeline.py`, `scripts/freeze_config_a.py` | Search (score bars, re-weight sliders); `results/config_a_frozen.json` |
| Authority from citations, leave-one-out | Bhattacharya et al. (2022); ABAI (2026) | `src/irlegal/ranking/authority.py` | Case drawer (authority, in-degree) |
| Citing-case neighbour vote | Huang et al. (2021); Dasula et al. (2024) | `src/irlegal/ranking/neighbours.py`, `src/irlegal/ranking/explain.py` | Search (Why this result); case drawer graph |
| Heap top-K; index elimination; champion lists; tiered indexes; cluster pruning | IIR ch. 7 (Efficient scoring and ranking; Index elimination; Champion lists; Tiered indexes; Cluster pruning) | `src/irlegal/efficiency/heap.py`, `src/irlegal/efficiency/elimination.py`, `src/irlegal/efficiency/champions.py`, `src/irlegal/efficiency/tiers.py`, `src/irlegal/efficiency/cluster.py` | Efficiency and crawl; Search (Pruning); `results/efficiency.json` |
| Evaluation: precision, recall, MAP, MRR, nDCG, 11-point PR | IIR ch. 8 (Evaluation of ranked retrieval results) | `src/irlegal/evaluation/metrics.py`, `src/irlegal/evaluation/runner.py` | Evaluation; `results/dev_eval.json`, `results/test_eval.json` |
| Paired bootstrap intervals | Smucker, Allan, Carterette (2007) | `src/irlegal/evaluation/bootstrap.py`, `src/irlegal/evaluation/runner.py` | Evaluation (interval charts) |
| Leakage audit; temporal filter | Fenced citation context (2026); ABAI (2026) | `src/irlegal/evaluation/leakage.py`, `src/irlegal/query/temporal.py`, `src/irlegal/ranking/pipeline.py` | Evaluation, Leakage audit; Search (temporal filter); `results/leakage_audit.json` |
| Realistic queries; citation scrubbing | TraceRetriever (2025); IL-PCSR (2025) | `src/irlegal/data/query_builder.py`, `src/irlegal/data/loader.py` | How it works (Query); Search pipeline strip |
| Reciprocal rank fusion of issue sub-queries | Cormack, Clarke, Büttcher (2009) | `src/irlegal/query/decompose.py`, `src/irlegal/ranking/fusion.py`, `scripts/run_decompose.py` | Evaluation, Negative results; `results/decompose_dev.json` |
| Crawling: frontier, politeness, URL normalisation, shingles | IIR ch. 20 (Crawler architecture; The URL frontier); Mercator (1999); Broder et al. (1997) | `src/irlegal/crawl/frontier.py`, `src/irlegal/crawl/normalize_url.py`, `src/irlegal/crawl/dedupe.py`, `src/irlegal/crawl/simulate.py` | Efficiency and crawl, Crawl simulation; `results/crawl_sim.json` |

## Headline results

Facts + Issues queries (citation strings scrubbed). Candidates: the full pool of 3183 precedents minus the query's own case. Dev: 626 queries; test: 626 queries, run once.

**Dev, 626 queries**

| system | P@5 | R@5 | P@10 | R@10 | P@20 | R@20 | MAP |
|---|---|---|---|---|---|---|---|
| random | 0.0022 | 0.0039 | 0.0016 | 0.0062 | 0.0010 | 0.0071 | 0.0045 |
| popularity (train in-degree) | 0.0188 | 0.0374 | 0.0136 | 0.0529 | 0.0098 | 0.0707 | 0.0355 |
| tf-idf lnc.ltc | 0.0575 | 0.1366 | 0.0399 | 0.1804 | 0.0280 | 0.2380 | 0.1220 |
| BM25 tuned | 0.0588 | 0.1353 | 0.0419 | 0.1837 | 0.0329 | 0.2750 | 0.1242 |
| **Config A** (text + neighbour + authority) | 0.1288 | 0.2254 | 0.0805 | 0.2844 | 0.0502 | 0.3582 | 0.2063 |
| **Config A + temporal filter (headline)** | 0.1339 | 0.2333 | 0.0851 | 0.3016 | 0.0522 | 0.3710 | 0.2169 |

**Test, 626 queries (run once)**

| system | P@5 | R@5 | P@10 | R@10 | P@20 | R@20 | MAP |
|---|---|---|---|---|---|---|---|
| random | 0.0006 | 0.0003 | 0.0011 | 0.0034 | 0.0007 | 0.0050 | 0.0028 |
| popularity (train in-degree) | 0.0166 | 0.0339 | 0.0128 | 0.0510 | 0.0088 | 0.0679 | 0.0364 |
| tf-idf lnc.ltc | 0.0652 | 0.1593 | 0.0474 | 0.2253 | 0.0331 | 0.3000 | 0.1362 |
| BM25 tuned | 0.0665 | 0.1604 | 0.0492 | 0.2257 | 0.0343 | 0.3024 | 0.1410 |
| **Config A** (text + neighbour + authority) | 0.1134 | 0.2265 | 0.0733 | 0.2937 | 0.0477 | 0.3806 | 0.2006 |
| **Config A + temporal filter (headline)** | 0.1188 | 0.2392 | 0.0768 | 0.3144 | 0.0502 | 0.4054 | 0.2087 |

On **test**, Config A + temporal filter vs tf-idf: MAP difference +0.0725 [+0.0482, +0.0969] (paired bootstrap, 1000 resamples); Config A without the filter: +0.0644 [+0.0399, +0.0906]; the temporal filter alone adds +0.0081 [+0.0034, +0.0124] to Config A. Config A vs tuned BM25: +0.0596 [+0.0352, +0.0832].

**How to read this.**

- The neighbour feature (cosine-nearest TRAIN queries voting for the precedents they cite) carries most of the gain: the same net score built without it (config C, dev) reaches MAP 0.1186 versus 0.1220 for tf-idf and 0.2063 for Config A. N7 is a combination of known ideas (citation collaborative filtering, nearest-neighbour citation retrieval), not an invention.
- The pool contains only precedents cited somewhere in the corpus, which favours citation-based signals; neighbour MAP on train exceeds dev, so test may differ: Config A beats tf-idf by +0.0843 MAP on dev and by +0.0644 on test.
- Config A here is the re-frozen three-feature version (`results/config_a_frozen.json`: weights {'text': 0.35444, 'neighbour': 0.48788, 'authority': 0.15768}).
- The temporal filter drops candidates that are not strictly earlier than the query where both dates are known (81.4% of pairs); it also removes 2.5% of relevant precedents, which the data itself dates after the query.
- First-stage recall@1000 is 0.8354: a ceiling for every reranker. Rows marked REFERENCE (full-judgment query) are in `docs/results_tables.md`; they are not comparable.

## Leakage audit (dev, and train for the first line)

- Without leave-one-out, scoring train queries inflates Config A MAP from 0.2681 to 0.8742 (+0.6061 [+0.5877, +0.6249]).
- Authority built from train + dev links changes dev MAP by +0.0030 [+0.0018, +0.0043].
- Citation scrubbing off changes dev MAP of Config A by +0.0004 [-0.0000, +0.0011].
- Temporal filter on vs off, Config A: +0.0106 [+0.0042, +0.0166].

## Efficiency (dev)

Exhaustive tf-idf scores 3101.3 documents per query. Champion lists (r=200): 2815.3 candidates, 100% of MAP kept. Cluster pruning of the neighbour search (b=3): 475.8 of 5017 train queries compared, 95% of Config A MAP kept. Index elimination and authority tiers lose much more quality (see `docs/results_tables.md`). Latencies are Python wall times on one machine.

AND processing order (300 random 3-5 word queries): smallest list first needs 1,218,408 posting comparisons versus 1,399,590 as written.

## Index

3183 documents, 12,259,946 indexed tokens; persisted size 18.31 MB with gap + variable-byte codes versus 66.36 MB raw.

## Screenshots

Curated screenshots from `docs/figures/ui/` (no case text; captions say when the data is the toy corpus or the replies are mocked). The QA scripts write every other screenshot to the git-ignored `docs/figures/ui_all/`.

| | |
|---|---|
| ![Pramaan overview: headline, live card from a saved run, headline MAP numbers](docs/figures/ui/landing_light.png)<br>*Pramaan overview: headline, live card from a saved run, headline MAP numbers* | ![The overview in the dark theme](docs/figures/ui/landing_dark.png)<br>*The overview in the dark theme* |
| ![Overview: ablation ladder and leakage audit bars, drawn from saved runs](docs/figures/ui/landing_evidence_light.png)<br>*Overview: ablation ladder and leakage audit bars, drawn from saved runs* | ![Sign-in with the three roles](docs/figures/ui/signin_light.png)<br>*Sign-in with the three roles* |
| ![Search: hero bar, strategy switcher, analytics pill and result cards (real index, text hidden)](docs/figures/ui/search_light.png)<br>*Search: hero bar, strategy switcher, analytics pill and result cards (real index, text hidden)* | ![Search in the dark theme](docs/figures/ui/search_dark.png)<br>*Search in the dark theme* |
| ![Search: pipeline strip with server timings and an expanded case record](docs/figures/ui/search_pipeline_record_light.png)<br>*Search: pipeline strip with server timings and an expanded case record* | ![Case drawer: why it ranks here, citing train cases, citation neighbourhood](docs/figures/ui/case_drawer_light.png)<br>*Case drawer: why it ranks here, citing train cases, citation neighbourhood* |
| ![Compare rankers: rank replay with promoted, demoted and unchanged chips](docs/figures/ui/compare_light.png)<br>*Compare rankers: rank replay with promoted, demoted and unchanged chips* | ![Evaluation: every system with P@k, R@k and MAP (saved runs only)](docs/figures/ui/evaluation_light.png)<br>*Evaluation: every system with P@k, R@k and MAP (saved runs only)* |
| ![Evaluation in the dark theme](docs/figures/ui/evaluation_dark.png)<br>*Evaluation in the dark theme* | ![Evaluation: the ablation ladder in story mode](docs/figures/ui/evaluation_story_light.png)<br>*Evaluation: the ablation ladder in story mode* |
| ![Efficiency: trade-off explorer with a draggable operating point](docs/figures/ui/efficiency_light.png)<br>*Efficiency: trade-off explorer with a draggable operating point* | ![Index Inspector: postings as blocks, compression, skip-pointer jump](docs/figures/ui/index_inspector_light.png)<br>*Index Inspector: postings as blocks, compression, skip-pointer jump* |
| ![How it works: scroll story with concept chips linked to code modules](docs/figures/ui/how_it_works_light.png)<br>*How it works: scroll story with concept chips linked to code modules* | ![AI assistant panel (no key set on the capture machine, so it shows "not configured")](docs/figures/ui/assistant_panel_light.png)<br>*AI assistant panel (no key set on the capture machine, so it shows "not configured")* |

**Slots for future screenshots** (add the file to `docs/figures/ui/`, list it in `docs/research_notes.md`, re-run this script):

- [ ] Assistant panel with a real Sarvam answer (capture with your own key; check that no case text is visible)
- [ ] Voice mode with a real microphone on a phone, in an Indian language

## Limitations and negative results

### Limitations

- The pool is made of precedents cited in the corpus; real search would face a much larger, unlabelled candidate set.
- The neighbour feature carries most of the gain over tf-idf.
- The pool's reasoning zone is built from the label "Court Disclosure", which is broader than the query-side "Court Reasoning" (DECISIONS D12).
- Query text is masked ([SECTION], [ACT], ...) while pool text is not, so statute identities are mostly unavailable on the query side.
- Phrase and proximity operators work on the facts and issues zones only; efficiency latencies are Python wall times on one machine; the crawl is a simulation.
- First-stage recall@1000 is 0.8354, a hard ceiling for every reranker.
- The temporal filter removes 2.5% of relevant precedents, which the data dates after their query.
- Dev (626 queries) was used for tuning choices that cross-validation could not make; the single test run is the only untouched estimate.
- Case titles and text are never printed by default; the UI shows ids, courts, years and scores. The assistant never receives them.

### Negative and marginal results

These were tried, measured with intervals where possible, and kept out of the headline system.

- **Learned zone-pair matrix.** Regularised variant (D18) on dev: MAP -0.0064 [-0.0145, +0.0010] vs tf-idf; survives the criterion: **False**. The first learned matrix also failed on dev (`results/zone_matrix.json`).
- **Statute channel.** Adds +0.0014 [-0.0013, +0.0043] MAP over tf-idf on dev (marginal). Query text is masked, so statute identities are mostly unavailable on the query side.
- **Union first stage.** Dev recall 0.8076 at a mean union size of 596.2 versus 0.8434 for tf-idf top 1000; no MAP gain, so it is not used.
- **Issue decomposition (N6).** 6.44 sub-queries per query on average; RRF of sub-queries changes dev MAP by -0.0407 [-0.0550, -0.0276].
- **Crawl simulation (N5).** Share of the 200 most-cited documents fetched after 1000 / 3000 fetches: priority crawler 0.224 / 0.573, BFS 0.233 / 0.566 (simulation, no live traffic; in-link priority did not beat BFS here).

## Roadmap

Phases and the measurable goal that would finish each one. These are plans, not results; every number quoted in a goal comes from `results/`.

| Phase | What | Measurable goal |
|---|---|---|
| 1. Cited answers (retrieval-augmented layer) | Pramaan writes a short answer in which every statement cites retrieved case ids. | every statement in a hand-checked set of answers cites at least one retrieved id, and the check is reported with the number of answers read |
| 2. Agentic research flow | The system plans sub-questions, searches, reads results and reports what it could not find. | on dev queries, recall@20 of the flow is compared with Config A + temporal filter (recall@20 0.3710 today) with a paired bootstrap interval |
| 3. Indic and multilingual search | Queries and cases in Hindi and other Indian languages. | a labelled multilingual query set exists and the same metrics (P@k, R@k, MAP) are reported per language |
| 4. Learned re-ranker | A trained re-ranker over the current features, kept leak-safe. | beats Config A + temporal filter on dev MAP (0.2169 today) with an interval that excludes zero, then one run on test |
| 5. Other citation-linked fields | Scientific papers and patents, which also cite earlier work. | the same pipeline runs on one such corpus with a leakage audit and the same report tables |

## How the assistant works and what it sends to a third party

The assistant explains this system, its results and its evaluation. It is an AI helper, not legal advice, and it says so in its first message. The browser never talks to Sarvam: it calls this server's `/api/assistant/*` endpoints, and the server calls the Sarvam AI REST API with the key from the environment variable `SARVAM_API_KEY` (never in the repository, logs, errors, the browser, screenshots or tests). Without a key the panel shows "Assistant not configured" and nothing else changes.

Typed questions get a text reply; spoken questions get a text reply and a spoken one, read sentence by sentence so speech starts early, with a Stop speaking button (or Esc). Settings > Speak replies can override this. The reply language follows the detected language of the question, and a language chip lets the user choose another supported language.

**Models and limits** (environment variables `SARVAM_CHAT_MODEL`, `SARVAM_TTS_SPEAKER`, `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL` override the defaults): chat `sarvam-105b`, speech to text `saaras:v4` (mode transcribe), text to speech `bulbul:v3` (speaker `shubh`), language identification `/text-lid`; replies in 11 languages (English and 10 Indian languages), speech input in 23, spoken replies in 11; at most 30 s of audio per question (the documented REST limit) and 2000 kB; questions up to 1000 characters; speech is synthesised sentence by sentence within the documented 2500-character limit per request; a facts sheet of at most 14,000 characters; per-session rate limits of 12 questions, 12 recordings and 60 speech requests per minute.

**Sent to Sarvam AI** (a third-party service; its own terms apply) only after a one-time consent click that is remembered in the browser:

- the question the user typed, or the audio they recorded (as a WAV file);
- the recent turns of the current conversation, which the browser keeps for this tab only (never stored on our server);
- a facts sheet built on the server from whitelisted JSON files in `results/` (numbers only) and sections of `README.md`, `docs/STATUS.md` and `docs/research_notes.md`;
- for "Explain this result" and "Explain this metric": ids, courts, years, scores, score components and the ids and similarities of the train cases that cite a result;
- the text of a reply when it is read aloud.

**Never sent:** case text, case titles or snippets (even when the server runs with `SHOW_TEXT=1`), text pasted into the Search box, passwords, session cookies. The key stays on the server: the browser never sees it and only talks to this server. Every number the assistant states must come from the facts sheet; if a number is not there it says it does not have it. It is an AI helper, not legal advice.

**Code:** `app/assistant/` (service, facts sheet, client with retries on 5xx only, WAV handling, rate limit) and `app/routers/assistant_router.py` (`/api/assistant/status`, `/chat`, `/stt`, `/tts`); the panel is `app/web/ui/assistant/`. Tests: `tests/app/test_assistant.py` (Sarvam mocked; no key needed) and `scripts/assistant_qa.py` (Playwright with a fake microphone and mocked endpoints).

## Components

### WS1: data, preprocessing, index
- **What it does.** Loads the five IL-PCSR parquet files (`data/loader.py`), maps role labels to zones (Facts, Issue, Argument by Petitioner or Respondent, Court Reasoning and the pool-only "Court Disclosure" to reasoning, Conclusion to decision, Statute Analysis, Precedent Analysis), builds the realistic query (Facts + Issues, citation strings scrubbed, `data/query_builder.py`), tokenises with statute-aware tokens (`s.302`, `art.21`), stems with Porter, and builds a per-zone inverted index plus derived `fi` and `all` zones, with positions kept only for facts and issues. The index is persisted with gap + variable-byte compression; skip pointers are benchmarked.
- **Run.** `make index` (or `python scripts/build_index.py`); data checks with `make data` (or `python scripts/inspect_data.py`); role profile with `python scripts/profile_roles.py`.
- **Results.** Index size, compression ratio and the skip benchmark are loaded from `results/index_report.json` (see the generated results in the README).
- **Limitations.** Query text is masked (`[SECTION]`, `[ACT]`, `[ENTITY]`, `[PRECEDENT]`), pool text is not; one pool role label ("Court Disclosure") is mapped to reasoning from a position profile, not from a human check.

### WS1 stretch: crawl simulation
- **What it does.** `crawl/` replays a Mercator-style crawl (front queues by in-links discovered so far, back queues per host, virtual politeness clock, URL normalisation, shingle-Jaccard duplicate check) over the citation graph, with courts as simulated hosts. No network traffic.
- **Run.** `python scripts/run_crawl_sim.py` (writes `results/crawl_sim.json`).

### WS2: query understanding and the app shell
- **What it does.** A query language with AND, OR, NOT, parentheses, phrases, proximity (`/k`, `pre/k`), zone restriction (`facts:bail`), wildcards, and `court:`, `year:`, `before:`, `after:` filters (`query/parser.py`, `query/boolean.py`). AND is processed smallest posting list first. Tolerant retrieval: 3-gram wildcard index, edit-distance suggestions, Soundex (`query/tolerant.py`). A regex statute normaliser and a statute bridge (`query/statutes.py`). Issue decomposition with reciprocal rank fusion (`query/decompose.py`). The FastAPI shell auto-discovers routers and serves the static web app.
- **Run.** `make demo` then open the Query Lab tab; `python scripts/bench_and.py` for the AND-order benchmark; `python scripts/run_decompose.py` for the decomposition experiment.
- **Limits.** Positions exist only for facts and issues, so phrase and proximity search those two zones; stop words are removed before positions are assigned. The query text of the dataset is masked, so statute tokens are rarely available from the query side.

### Front end (app/)
- **What it does.** A sign-in page, then a role-specific workspace: Search (dev-query combobox, ranker selector, filter chips, client-side re-weighting, evaluation overlay, case drawer with a hover-linked neighbour graph), Compare (rank-slope chart), Query Lab (highlighted input, parse tree, suggestions), Evaluation, Efficiency and crawl, Index Inspector, System status, Users, Saved, History, How it works, About and Settings, plus a living style guide at `#/styleguide`. Command palette (Ctrl/Cmd+K), keyboard shortcuts (`?`), light and dark themes, compact density, reduced-motion support, responsive from 375 px.
- **Run.** `python scripts/seed_demo_users.py` then `make demo`; `AUTH_REQUIRED=0 make demo` skips sign-in. Dev-only checks: `python scripts/ui_matrix.py`, `python scripts/ui_qa.py` (Playwright, see `requirements/dev.txt`).
- **Limits.** Demo-grade local auth (not dataset access control); verified in headless Chromium only.

### WS3: ranking
- **What it does.** tf-idf (SMART lnc.ltc) and BM25 baselines; a leak-safe authority prior (log in-degree from pool and TRAIN edges with leave-one-out); N7 "citing-case neighbours" (cosine nearest TRAIN queries vote for the precedents they cite, a combination of known ideas: citation collaborative filtering and nearest-neighbour citation retrieval); a net score with weights from random search and 5-fold cross-validation on train; **Config A** = text + neighbour + authority over a tf-idf top-1000 first stage, optionally with a temporal filter. Explanations carry ids and numbers only.
- **Negative or marginal results kept.** The learned zone-pair matrix and its regularised variant did not beat tf-idf on dev; the statute channel adds almost nothing; a union first stage did not help.
- **Run.** `python scripts/run_b1.py`, `python scripts/run_b2.py`, `python scripts/freeze_config_a.py`, `python scripts/run_w_variant.py`.

### WS4: evaluation, efficiency, release assets
- **What it does.** Metrics (P, R, F1 at 5, 10, 20, MAP, MRR, nDCG, 11-point interpolated PR, macro and micro averages) with paired bootstrap intervals; one runner for dev and test (the test split needs `--final` and runs once, guarded by `results/final.lock`); a leakage audit (no leave-one-out, dev links in the authority graph, citation scrubbing off, temporal filter); an efficiency study (heap top-K, index elimination, champion lists, authority tiers, cluster pruning) with latency and candidates scored; figures and tables for the report.
- **Run.** `make eval` (dev only), `python scripts/make_report_assets.py`, `python scripts/make_readme.py`.

## Data credits and licences

- **IL-PCSR**: Paul, Ghumare, Goyal, Ghosh, Modi, *IL-PCSR: Legal Corpus for Prior Case and Statute Retrieval*, EMNLP 2025. Licence on its Hugging Face page: CC BY-NC-SA 4.0, research use only. No data is redistributed here.
- Case texts originate from Indian court judgments as compiled by the dataset authors.

## AI use

See `AI_USE.md`: which tool wrote which files, who reviewed them, and what the assistant feature sends to Sarvam AI.

## Work division

Each member owns, runs and can explain the components below. The work was developed together.

- 2510110008: data loading and Facts+Issues queries with citation scrubbing, tokenizer, evaluation metrics, paired bootstrap, dev and test runner, leakage audit, landing page and evaluation dashboard, README generator.
- 2410110026: query language (Boolean, phrase, proximity, wildcard, spelling, Soundex), statute bridge, issue decomposition, crawl simulation, server and sign-in, app shell and Query Lab.
- 2410110246: tf-idf and BM25 baselines and tuning, zone-pair experiments, neighbour vote, authority and net score, Config A freeze, results tables, search API, design system, Search and Compare pages.
- 2410110420: zone index with compression and skip pointers, efficiency study, Index Inspector and Efficiency pages, Sarvam assistant, packaging, research notes and concept map.
