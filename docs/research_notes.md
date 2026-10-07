<!-- Data for scripts/make_readme.py (DECISIONS D44). Edit this file, then run: python scripts/make_readme.py
     Rules: only references listed here; never invent a reference, author, venue or result; never claim a method that a paper
     below introduced. Numbers are NOT typed here: {placeholders} are filled from results/ by the script (D32). -->
# Research notes

Status legend. **VERIFIED**: title, venue or arXiv id and the described content were read on the source page.
**VERIFIED (re-checked 2026-10-07)**: a RE-CHECK item whose bibliographic details were confirmed on the source page during Phase F.
**RE-CHECK**: not confirmed yet; confirm before citing in the report.

## Papers

### IL-PCSR
- status: VERIFIED. Authors re-read on arxiv.org on 2026-10-07: Paul, Ghumare, Goyal, Ghosh, Modi (the Phase F brief said "Mehta et al."; the source page and the dataset credit agree on Paul et al.).
- citation: S. Paul, D. Ghumare, P. Goyal, S. Ghosh, A. Modi. *IL-PCSR: Legal Corpus for Prior Case and Statute Retrieval*. EMNLP 2025 (main). arXiv:2511.00268.
- short: IL-PCSR (EMNLP 2025)
- did: Released the corpus we use: 936 statutes, a 3,183-case precedent pool and 6,271 queries; citations inside queries are masked with placeholders such as [SECTION], [ACT], [PRECEDENT], [ENTITY].
- take: The corpus and its masked-query design.
- differ: A leak-safe protocol, Facts+Issues-only queries, citation-based features built only from training queries, and a measured leakage audit.

### U-CREAT
- status: VERIFIED
- citation: Joshi et al. *U-CREAT: Unsupervised Case Retrieval using Events extrAcTion*. ACL 2023. arXiv:2307.05260.
- short: U-CREAT (ACL 2023)
- did: Introduced the IL-PCR corpus and an unsupervised, event-based retrieval approach.
- take: The prior case retrieval framing and the benchmark lineage.
- differ: No event extraction; classic IR index and scoring plus citation signals.

### Segment First, Retrieve Better (TraceRetriever)
- status: VERIFIED
- citation: Nigam, Dubey, Shallum, Bhattacharya. *Segment First, Retrieve Better: Realistic Legal Search via Rhetorical Role-Based Queries* (TraceRetriever). arXiv:2508.00679.
- short: TraceRetriever (arXiv 2508.00679)
- did: Builds queries from rhetorically significant segments (Facts, Issue) to mimic partial case knowledge; BM25 plus a vector database plus a cross-encoder, fused with reciprocal rank fusion; evaluated on IL-PCR and COLIEE 2025.
- take: The role-based realistic-query idea. It is theirs, not ours.
- differ: We use the corpus's own role labels on IL-PCSR, no neural models, and add leak-safe neighbour and authority features and a leakage audit.

### Fenced citation-context retrieval
- status: VERIFIED
- citation: Liu, Tan, Liu. *Fenced Citation-Context Retrieval for Case Law: Temporal Leakage and Degree Control Across Two Jurisdictions*. arXiv:2607.17142.
- short: Fenced citation context (arXiv 2607.17142)
- did: Shows that citation-context gains are inflated unless restricted to citations that predate the query, and adds popularity (degree) controls.
- take: A popularity-only baseline and a temporal-fence ablation.
- differ: A different corpus and features; our leakage audit targets leave-one-out and how the citation graph is built.

### ABAI at COLIEE 2026
- status: VERIFIED
- citation: Cho, Park, Choi, Han. *ABAI at COLIEE 2026 Task 1*. arXiv:2609.26237.
- short: ABAI at COLIEE 2026 (arXiv 2609.26237)
- did: Reports that citation-graph features give only a small gain once own-citation leakage is removed.
- take: Support for treating own-citation leakage as a real risk.
- differ: Our leave-one-out audit measures that risk on IL-PCSR.

### Context-aware legal citation recommendation
- status: VERIFIED
- citation: Huang et al. *Context-Aware Legal Citation Recommendation using Deep Learning*. ICAIL 2021.
- short: Huang et al. (ICAIL 2021)
- did: Compares a collaborative-filtering method over citation lists with text-based neural methods.
- take: Collaborative filtering over citation lists is prior art for our neighbour vote.
- differ: Our neighbours are found by lnc.ltc similarity of Facts+Issues text, with explanations and leave-one-out.

### Network and text for legal case similarity
- status: VERIFIED
- citation: Bhattacharya et al. *Legal Case Document Similarity: You Need Both Network and Text*. Information Processing and Management, 2022. arXiv:2209.12474.
- short: Bhattacharya et al. (IP&M 2022)
- did: Combines citation-network and text similarity for Indian Supreme Court cases.
- take: The premise that text and the citation network are complementary.
- differ: Our net score combines a text score, a neighbour vote and authority, with weights learned on train only.

### Judgement citation retrieval by contextual similarity
- status: VERIFIED
- citation: Dasula et al. *Judgement Citation Retrieval using Contextual Similarity*. arXiv:2406.01609.
- short: Dasula et al. (arXiv 2406.01609)
- did: Cosine similarity over case descriptions plus clustering and classification to suggest citations (US Supreme Court data).
- take: Related prior art for similarity-based citation suggestion.
- differ: Indian precedents, a leak-safe evaluation protocol and a neighbour vote over training citations rather than classification.

### IL-TUR
- status: VERIFIED (re-checked 2026-10-07: title, authors Joshi, Paul, Sharma, Goyal, Ghosh, Modi, ACL 2024 long papers, and that the benchmark includes a Prior Case Retrieval task). The per-split candidate-pool detail was not visible on the pages read; RE-CHECK it in the paper's appendix before citing it.
- citation: A. Joshi, S. Paul, A. Sharma, P. Goyal, S. Ghosh, A. Modi. *IL-TUR: Benchmark for Indian Legal Text Understanding and Reasoning*. ACL 2024.
- short: IL-TUR (ACL 2024)
- did: A benchmark of Indian legal tasks that includes prior case retrieval (IL-PCR).
- take: Context for the task.
- differ: We moved from its IL-PCR setting to IL-PCSR, which has one shared precedent pool (DECISIONS D1).

### Introduction to Information Retrieval
- status: VERIFIED (re-checked 2026-10-07 on the book's online table of contents and section pages: the chapters and section titles used in the concept table below; Soundex in the phonetic-correction section, lnc.ltc in "Document and query weighting schemes", a heap for top K in "Efficient scoring and ranking").
- citation: C. D. Manning, P. Raghavan, H. Schütze. *Introduction to Information Retrieval*. Cambridge University Press, 2008.
- short: IIR (Manning, Raghavan, Schütze 2008)
- did: The course text: indexes, tolerant retrieval, compression, tf-idf and zone scoring, efficient scoring, evaluation, BM25, crawling.
- take: Every classical component in this repository (see the concept table).
- differ: We apply the techniques to rhetorical-role zones of Indian judgments and measure them on IL-PCSR.

### BM25 and BM25F
- status: VERIFIED (re-checked 2026-10-07: Foundations and Trends in IR 3(4), 333–389, 2009; CIKM 2004 for the multiple-fields paper)
- citation: S. Robertson, H. Zaragoza. *The Probabilistic Relevance Framework: BM25 and Beyond*. Foundations and Trends in Information Retrieval 3(4), 2009. S. Robertson, H. Zaragoza, M. Taylor. *Simple BM25 extension to multiple weighted fields*. CIKM 2004.
- short: BM25 (2009) and BM25F (CIKM 2004)
- did: The BM25 ranking function; BM25F weights document fields before saturation.
- take: Tuned BM25 as a baseline; BM25F as the reference point for weighting zones.
- differ: Our learned query-zone by document-zone matrix is a cross-zone variant; it did not beat tf-idf on dev (a reported negative result).

### Reciprocal rank fusion
- status: VERIFIED (re-checked 2026-10-07: SIGIR 2009, pages 758–759)
- citation: G. V. Cormack, C. L. A. Clarke, S. Büttcher. *Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods*. SIGIR 2009.
- short: RRF (SIGIR 2009)
- did: A simple fusion of ranked lists by summed reciprocal ranks.
- take: RRF for fusing issue sub-queries.
- differ: Measured on dev; it hurt here (negative result).

### Crawling and near-duplicates
- status: VERIFIED (re-checked 2026-10-07: Mercator in World Wide Web journal 2(4), 1999; Broder, Glassman, Manasse, Zweig at WWW6, 1997, shingles and resemblance)
- citation: A. Heydon, M. Najork. *Mercator: A scalable, extensible web crawler*. World Wide Web 2(4), 1999. A. Z. Broder, S. C. Glassman, M. S. Manasse, G. Zweig. *Syntactic clustering of the web*. WWW6, 1997.
- short: Mercator (1999); Broder et al. (1997)
- did: Front and back queues with per-host politeness; shingles for near-duplicate detection.
- take: The frontier design and shingle-based duplicate checks of the crawl simulation.
- differ: A simulation over the citation graph with courts as hosts; no live traffic.

### Significance tests for IR
- status: VERIFIED for title, authors, venue and year (re-checked 2026-10-07: CIKM 2007). RE-CHECK the content claim (paired bootstrap and randomisation tests) in the paper itself.
- citation: M. D. Smucker, J. Allan, B. Carterette. *A comparison of statistical significance tests for information retrieval evaluation*. CIKM 2007.
- short: Smucker et al. (CIKM 2007)
- did: Compares significance tests for IR evaluation.
- take: Paired tests over queries; we report paired bootstrap 95% intervals.
- differ: We report intervals rather than p-values.

## Our contributions

- **A leak-safe evaluation protocol for precedent retrieval on IL-PCSR, with a measured leakage audit.** Scoring training queries without leave-one-out inflates Config A MAP from {loo_with} to {loo_without}. Adding dev links to the authority graph ({leak_b}), switching citation scrubbing off ({leak_c}) and the temporal filter ({leak_d}) are measured separately (dev MAP differences with 95% intervals).
- **Realistic Facts+Issues queries using the corpus's own role labels.** The role-based query idea comes from TraceRetriever; the evaluation setting on IL-PCSR and the leak controls are ours.
- **A citing-case neighbour vote with explanations, leave-one-out and a popularity-only baseline.** It is a combination of known ideas (collaborative filtering over citation lists and nearest-neighbour citation retrieval), not a new algorithm.
- **A measured efficiency study of course techniques**: heap top-K, champion lists, authority tiers, index elimination and cluster pruning (see Efficiency).
- **Honest negative or marginal results with intervals**: the learned zone-pair matrix, the statute bridge, the union first stage, issue decomposition, and priority crawling against BFS (see Limitations and negative results).

## Caveats

- The pool contains only precedents cited somewhere in the corpus, which favours citation-based signals.
- The neighbour feature carries most of the gain over tf-idf.
- The pool's reasoning zone is built from the label "Court Disclosure", which is broader than the query-side "Court Reasoning" (DECISIONS D12).
- Query text is masked ([SECTION], [ACT], ...) while pool text is not, so statute identities are mostly unavailable on the query side.
- Phrase and proximity operators work on the facts and issues zones only; efficiency latencies are Python wall times on one machine; the crawl is a simulation.

## IR concepts

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

## Screenshots

- landing_light.png | Pramaan overview: headline, live card from a saved run, headline MAP numbers
- landing_dark.png | The overview in the dark theme
- landing_evidence_light.png | Overview: ablation ladder and leakage audit bars, drawn from saved runs
- signin_light.png | Sign-in with the three roles
- search_light.png | Search: hero bar, strategy switcher, analytics pill and result cards (real index, text hidden)
- search_dark.png | Search in the dark theme
- search_pipeline_record_light.png | Search: pipeline strip with server timings and an expanded case record
- case_drawer_light.png | Case drawer: why it ranks here, citing train cases, citation neighbourhood
- compare_light.png | Compare rankers: rank replay with promoted, demoted and unchanged chips
- evaluation_light.png | Evaluation: every system with P@k, R@k and MAP (saved runs only)
- evaluation_dark.png | Evaluation in the dark theme
- evaluation_story_light.png | Evaluation: the ablation ladder in story mode
- efficiency_light.png | Efficiency: trade-off explorer with a draggable operating point
- index_inspector_light.png | Index Inspector: postings as blocks, compression, skip-pointer jump
- how_it_works_light.png | How it works: scroll story with concept chips linked to code modules
- assistant_panel_light.png | AI assistant panel (no key set on the capture machine, so it shows "not configured")

## Screenshot slots

- Assistant panel with a real Sarvam answer (capture with your own key; check that no case text is visible)
- Voice mode with a real microphone on a phone, in an Indian language

## Assistant

The assistant explains this system, its results and its evaluation. It is an AI helper, not legal advice, and it says so in its first message. The browser never talks to Sarvam: it calls this server's `/api/assistant/*` endpoints, and the server calls the Sarvam AI REST API with the key from the environment variable `SARVAM_API_KEY` (never in the repository, logs, errors, the browser, screenshots or tests). Without a key the panel shows "Assistant not configured" and nothing else changes.

Typed questions get a text reply; spoken questions get a text reply and a spoken one, read sentence by sentence so speech starts early, with a Stop speaking button (or Esc). Settings > Speak replies can override this. The reply language follows the detected language of the question, and a language chip lets the user choose another supported language.
