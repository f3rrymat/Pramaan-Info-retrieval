# IR Hackathon Master Spec: Role-Aware, Leak-Safe Legal Precedent Finder

Course: CSD358 Information Retrieval, mid-term hackathon. Track: **T6 (vertical search), domain: Indian law**.
This file is the complete context for building the project. Read all of it before writing code.

Legend: **[V]** = checked against a live source while this spec was written. **[M]** = written from memory; confirm before citing. **[CHECK]** = something the builder must verify against the real data or docs and report back, not assume.

---

## 0. How to use this file

**For the person who generates the code (the "architect"):**
1. Give this whole file to your Claude. Run the **Phase 0 scaffold prompt** (Section 14). It creates the repo skeleton, the frozen interfaces, toy data and the app shell, and you commit it to `main`.
2. Share the repo. Everyone clones it.

**For each of the four team members:**
1. Open your own Claude Code in the cloned repo, on your own branch (`feat/ws<N>-<topic>`).
2. Paste (a) Sections 1 to 12 of this file as shared context and (b) your own **Workstream N** section from Section 13.
3. Commit your own work from your own machine under your own git identity. Small, meaningful commits; one pull request per feature into `main`.

**For any Claude reading this file:** work only inside your workstream's folders. Never edit `src/irlegal/common/` (the frozen contracts) without asking the human. If the real data differs from what this spec assumes, adapt your code, say so plainly, and record it in `docs/data_notes.md`.

---

## 1. Rules of engagement (non-negotiable)

1. **Honesty over polish.** Never invent dataset statistics, results, citations or benchmark numbers. Every number in the README, report, UI and video comes from a real run of the code. Placeholders are marked `PLACEHOLDER`.
2. **No faked demos.** Nothing hard-coded, no screenshots standing in for a running system. The rubric gives 0 for a faked working system.
3. **Implement the IR machinery ourselves.** The inverted index, positional index, compression, skip pointers, heap top-K, champion lists, tiers, cluster pruning, k-gram index, edit distance, Soundex, lnc.ltc, BM25 and RRF must be our own code. Libraries are for utilities only (numpy, a Porter stemmer, FastAPI, pytest, matplotlib).
4. **No copying.** Do not copy code from the U-CREAT or TraceRetriever repositories, or any other published project. Cite papers; implement ideas from scratch.
5. **Build inside the hackathon window with a fresh repository.** Do not reuse earlier course projects.
6. **Data ethics.** Use the released dataset. Do not crawl any live site unless its robots.txt and terms allow it; default is the offline crawl simulation. Do not collect personal data. Credit every dataset.
7. **Declare AI use.** Keep `AI_USE.md` updated: which tool, which files, what it did.
8. **Do not claim superiority you have not measured.** README and report claims must match the measured numbers, including where we lose.

---

## 2. Problem statement

**Task: prior case retrieval (PCR).** A lawyer has an undecided case and wants the earlier judgments it should cite.

- **Input:** the *facts and issues* of the query case (pasted text, or a test query from the dataset).
- **Output:** a ranked list of earlier Indian judgments, each with a "why this precedent" explanation (shared statutes, which parts of the two cases matched, authority signals).

**Why this belongs to T6:** legal documents have structure (facts, issues, arguments, reasoning, decision), statutes, courts, dates and a citation network. The system uses that structure (zone indexes, parametric fields, static quality scores, Boolean and proximity queries), which is exactly what the track asks for, instead of treating a judgment as flat text.

**Why a "realistic" query:** many benchmark setups use a whole case document, with only the case citations masked, as the query. That includes the judge's reasoning, which would not exist for an undecided case (this realism critique appears in the LeCoPCR paper [V]; the TraceRetriever paper [V] builds role-based queries for the same reason). We therefore evaluate with **Facts + Issues** queries and report full-text queries only as a reference row.

---

## 3. What exists, and how we are different (honest positioning)

| Existing work | What it does |
|---|---|
| IL-PCR benchmark and U-CREAT (ACL 2023) [V] | Benchmark for Indian prior case retrieval; unsupervised event-extraction retrieval; states that BM25 is a strong baseline |
| TraceRetriever, "Segment First, Retrieve Better" (arXiv 2508.00679) [V] | Role-based queries (Facts, Issue, ...) on IL-PCR; BM25 + vector database + reciprocal rank fusion + cross-encoder re-ranking |
| LeCoPCR (arXiv 2501.14114) [V] | Generates legal concepts from the facts to improve prior case retrieval; critiques unrealistic full-document queries |
| General legal search portals | Keyword and Boolean search with citation information (we do not benchmark them) |

**Important:** role-based queries are **not** our novelty, because TraceRetriever already does that. We do not claim to beat neural state of the art; its published numbers use a different setup (cross-encoders, vector DB) and are context only.

**What we contribute (all measured, all explainable):**
1. A **classical zone index** with a **learned query-zone x document-zone weight matrix** (which part of the query case should match which part of the candidate).
2. A **deterministic statute-normalisation channel** ("Sec. 302 IPC" = "S.302 of the Indian Penal Code") scored by Jaccard.
3. A **leak-safe authority prior**, built from training-split citation links only, with a **leakage audit** showing how much a naive version would inflate results.
4. An **efficiency vs effectiveness study** with champion lists, authority-ordered tiers and cluster pruning.
5. **Full transparency:** every score decomposes into components shown in the UI.

**Positioning sentence for the README and report (edit only if numbers force it):** "We build an auditable, structure-aware classical IR system for prior case retrieval under a realistic Facts+Issues query setting, and measure what each structural component adds over standard lexical baselines."

---

## 4. Data

**Primary: IL-PCR** (Joshi et al., ACL 2023) [V]
- 7,070 English Indian legal documents; 1,182 query documents; about 6.8 relevant (cited) cases per query; built from IndianKanoon starting with the 100 most-cited Supreme Court judgments plus the cases they cite.
- Split 70/10/20 train/validation/test; the test split has 237 queries [V].
- Hyperlinked case citations are replaced by the token `<CITATION>`; statute references are kept. An alternate version removes whole sentences containing citations [V].
- **Licence [V]:** CC BY-NC 4.0, research use only. Credit the authors in README and report.
- **Where to get it:** the IL-PCR GitHub README (Exploration-Lab/IL-PCR) points to Hugging Face and the IL-TUR benchmark [V]. **[CHECK]** Find the actual files; do not guess names. IL-TUR's packaging may list different counts, so recount after download.

**Hour-1 verification tasks (write `scripts/inspect_data.py`, report results in `docs/data_notes.md`):**
- Fields available: document id, text, query id, relevant (cited) ids, split.
- Counts of documents, queries and queries per split.
- Whether court, date, or role annotations exist; if not, how often a date and court can be extracted from the text header.
- How often statute patterns occur.
- Whether query texts still contain case-citation strings such as "AIR 1973 SC 1461" or "(2005) 3 SCC 112"; if yes, the scrubber (Section 9.1) must remove them.
- The dataset's official evaluation protocol, if documented (candidate pool, exclusion of the query itself). If none, exclude only the query document itself and record the choice.

**Optional extension:** IL-PCSR (prior case and statute retrieval corpus) [V, existence only]. Not needed for the hackathon core.

---

## 5. Research papers (what we take, what we change)

| Paper | Take | Change or add |
|---|---|---|
| Joshi, Sharma, Tanikella, Modi. *U-CREAT: Unsupervised Case Retrieval using Events extrAcTion*. ACL 2023 [V] | IL-PCR data, splits, baseline context | We do not use its event pipeline |
| Nigam, Dubey, Shallum, Bhattacharya. *Segment First, Retrieve Better: Realistic Legal Search via Rhetorical Role-Based Queries*. arXiv 2508.00679, 2025 [V] | Realistic role-based query idea; evaluation metrics list | We differ: classical zone index, learned zone-pair matrix, statute channel, leak-safe authority, efficiency study, explanations |
| Santosh, Olguin Nolasco, Grabmair. *LeCoPCR*. arXiv 2501.14114, 2025 [V] | Realism critique; explicit legal concepts help | Our statute normalisation is a deterministic version of the idea |
| Bhattacharya et al. *Identification of Rhetorical Roles of Sentences in Indian Legal Judgments*. JURIX 2019 [V as cited by Nigam et al.; **CHECK** the original] | Background for the role zones | Lightweight heuristic segmenter, accuracy measured |
| Joshi et al. *IL-TUR* benchmark, ACL 2024 [V for title and venue; **CHECK** authors] | Packaging of IL-PCR | None |
| Heydon and Najork, *Mercator* (the course's crawling lecture cites Heydon et al.) [V that the lecture cites it] | Front/back queue frontier, politeness | Authority-priority frontier replayed on the citation graph (stretch) |
| Robertson and Zaragoza, BM25 / probabilistic relevance framework (2009) [M]; Cormack, Clarke and Buettcher, reciprocal rank fusion, SIGIR 2009 [M]; Manning, Raghavan and Schuetze, *Introduction to Information Retrieval* (course text) | BM25, RRF, all course algorithms | Confirm exact citations before the report |

Course lectures used: Lecture 1 (Boolean retrieval), 2 (vocabulary and postings), 3 (dictionaries and tolerant retrieval), 5 (compression), 6 (tf-idf and vector space), 7 (scoring and results assembly), 8 (evaluation), 20 (crawling).

---

## 6. How the system works (plain language) and the end-to-end flow

**In one paragraph:** We load a corpus of Indian judgments and split each into rough parts (facts, issues, arguments, reasoning, decision). We index each part separately so we can say *which part of the query matches which part of a candidate*. We also pull out the laws mentioned (statutes), the court and the year. When a user enters the facts and issues of a case, the system finds candidate judgments, scores them by text similarity per part, by overlap of statutes, and by how authoritative and recent the candidate is, and returns a ranked list where every score is explained. Pruning structures keep it fast. A separate evaluation harness measures everything against the dataset's own citation judgments.

**Flow (what happens when a user searches):**

| Step | What happens | IR concept | Novelty |
|---|---|---|---|
| 1 | The query text is cleaned (citation strings removed) and split into zones; only Facts and Issues are kept | Document unit, tokenisation, zones | Leak-safe query building |
| 2 | Words are normalised (case folding, stop words, stemming); statutes are normalised to tokens like `IPC_302` | Normalisation, equivalence classes | N2 statute channel |
| 3 | The query is parsed (free text, or Boolean/phrase/proximity/zone/date filters); rare terms are processed first | Boolean retrieval, query optimisation | None |
| 4 | Candidates are found through the per-zone inverted indexes (with pruning: high-idf terms, champion lists, authority tiers, cluster leaders) | Inverted index, efficient scoring | N4 |
| 5 | For every (query zone, candidate zone) pair, cosine similarity (lnc.ltc) is computed; BM25 is available as a baseline | Vector space model, zone scoring | N1 learned matrix |
| 6 | Statute overlap (Jaccard), authority, court level and recency are combined with the text scores into a net score; candidates dated after the query are removed | Static quality g(d), net score | N3 leak-safe authority |
| 7 | Several rankers can be fused with reciprocal rank fusion | Rank fusion | None |
| 8 | The top K are returned with an explanation (shared statutes, strongest zone pairs, top terms, authority, court, year) | Result assembly | Transparency |

---

## 7. IR concept map (lecture, where it lives in code)

| Lecture topic | Concept | Module |
|---|---|---|
| Boolean retrieval | Inverted index, AND/OR/NOT, postings intersection, df-ordered processing | `index/inverted.py`, `query/boolean.py` |
| Vocabulary and postings | Tokenisation, normalisation, case folding, stop words, Porter vs lemma, Soundex, skip pointers, positional index, phrase queries | `preprocess/*`, `index/positional.py`, `index/skips.py`, `query/tolerant.py` |
| Dictionaries and tolerant retrieval | k-gram wildcard index, edit distance, spelling correction | `query/tolerant.py` |
| Compression | Gap encoding, variable-byte codes | `index/compress.py` |
| tf-idf and vector space | Log tf, idf, cosine, SMART lnc.ltc, Jaccard | `ranking/vsm.py`, `query/statutes.py` |
| Scoring and results assembly | Heap top-K, index elimination, champion lists, static quality and net score, tiered index, cluster pruning, zone and parametric indexes, proximity, query parser | `efficiency/*`, `ranking/netscore.py`, `index/parametric.py`, `query/parser.py` |
| Evaluation | P, R, F1, P@k, MAP, MRR, nDCG, interpolated PR curve | `evaluation/*` |
| Crawling (stretch) | URL frontier, politeness, URL normalisation, content-seen, Mercator queues | `crawl/*` |
| Outside the syllabus (extra marks) | BM25, reciprocal rank fusion, optional dense baseline | `ranking/bm25.py`, `ranking/fusion.py` |

Use the concepts that fit; each must have a real job and show up in an evaluation or the UI.

---

## 8. Novelty contributions

| ID | Contribution | Test (ablation or measurement) |
|---|---|---|
| N1 | **Zone-pair weight matrix:** learn how much each query zone (facts, issues) should match each candidate zone (facts, issues, arguments, reasoning, decision, statutes) | Flat full text vs same-zone only vs learned matrix; publish the matrix as a heatmap |
| N2 | **Statute channel:** deterministic normalisation of statute mentions, Jaccard overlap as a net-score component | With vs without; normaliser accuracy on a hand-labelled sample |
| N3 | **Leak-safe authority prior:** citation in-degree from training-split links only (leave-one-out for training queries), plus court level and recency; temporal filter | With vs without; **leakage audit**: rerun with authority built from all links and show how much metrics inflate |
| N4 | **Efficiency-effectiveness frontier:** champion lists, authority-ordered tiers, cluster pruning | Quality vs speed curve; also report number of candidates scored (machine-independent) |
| N5 (stretch) | **Authority-priority crawl simulation** | Share of top-cited cases found vs fetch budget, against BFS |
| N6 (stretch) | **Issue decomposition (agentic-lite):** split a brief into issue sub-queries, retrieve each, fuse | Recall@k vs single query |

Be honest in the report: the corpus is about 7k documents, so latency gains are modest.

---

## 9. Algorithms and definitions (exact)

Write all formulas in plain text in code comments and docs.

### 9.1 Query building and leak guards
- A query case's text is segmented into zones (9.2). The **realistic query** is Facts + Issues (and Arguments only in a labelled reference variant).
- Remove the `<CITATION>` token and scrub case-citation patterns (AIR/SCC/SCR/SCALE-style strings, "v." party-name pairs followed by a year in brackets) from query text. Log how many were removed.
- Exclude the query document itself from the candidates. Apply the temporal filter (9.6).

### 9.2 Zone segmentation (heuristic, no trained model required)
- Split into sentences. Label each sentence FACTS, ISSUES, ARGUMENTS, REASONING, DECISION or OTHER.
- Use cue phrases plus relative position, then enforce the usual order (facts first, decision last) with a monotonic decoding (Viterbi over states with cue likelihoods).
- Cue examples: facts ("the facts of the case", "brief facts", "FIR was registered"); issues ("the question that arises", "point for determination", "whether"); arguments ("learned counsel for the appellant submitted", "it was contended"); reasoning ("we are of the view", "in our opinion", "having considered"); decision ("appeal is dismissed", "appeal is allowed", "in the result", "we direct").
- **Evaluate:** hand-label about 30 judgments, report per-zone accuracy. If accuracy is poor, fall back to position thirds and say so. If the dataset ships role annotations **[CHECK]**, use them instead and cite the source.

### 9.3 Statute normalisation
- Output tokens such as `IPC_302`, `CRPC_161`, `CONST_ART_21`, `ITACT1961_80IA`.
- Act aliases: IPC = "Indian Penal Code", "I.P.C."; CRPC = "Code of Criminal Procedure", "Cr.P.C."; CPC = "Code of Civil Procedure", "C.P.C."; CONST = "Constitution of India" (Articles); ITACT1961 = "Income Tax Act", "Income-tax Act, 1961"; NIACT = "Negotiable Instruments Act"; EVIDENCE = "Indian Evidence Act"; CONTRACT = "Indian Contract Act". Unknown acts: slugify the act name.
- Section patterns: "Section 302", "Sec. 302", "S. 302", "s.302", "u/s 302", "Sections 302 and 304", "302/34", sub-sections "302(1)(a)" (index the base section; keep the detailed token as an optional extra).
- Statute Jaccard: |Q ∩ D| / |Q ∪ D|; also provide an idf-weighted variant. Evaluate normaliser accuracy on a labelled sample.

### 9.4 Text scoring
- **lnc.ltc (SMART).** Document side: weight = 1 + log10(tf) for tf > 0, no idf, cosine-normalised. Query side: weight = (1 + log10(tf)) x log10(N / df), cosine-normalised. Note: use `1 + log10(tf)`, **not** `log10(1 + tf)` (the course corrected this slip).
- **Per zone:** each zone has its own vocabulary statistics. Query zone vectors use the idf of the candidate zone's collection.
- **BM25:** score = sum over query terms of idf(t) x tf x (k1 + 1) / (tf + k1 x (1 - b + b x dl / avgdl)), idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5)); start with k1 = 1.2, b = 0.75 and tune on validation.
- **Zone-pair score:** S(q, d) = sum over (qz, dz) of W[qz][dz] x cosine(q_qz, d_dz). Learn W (non-negative, sum 1) on **training** queries by coordinate ascent over a small grid, maximising MAP; choose settings on validation.
- **Proximity (optional boost):** smallest window containing the query's highest-idf terms inside the facts zone; boost = 1 / (1 + window / 50).
- **RRF:** score(d) = sum over rankers of 1 / (60 + rank).

### 9.5 Net score
Normalise each component to [0, 1] within the candidate set, then:
`net(q, d) = a x text(q, d) + b x statute_jaccard(q, d) + c x authority(d) + e x court_prior(d) + f x recency(q, d)`
with a, b, c, e, f >= 0 summing to 1, tuned on **validation** by random search (about 200 trials). One final run on test.
- `authority(d) = log(1 + indegree_train(d))`, min-max scaled. `indegree_train(d)` = number of **training-split** query cases that cite d. **For a training query, subtract that query's own links (leave-one-out)**; otherwise training leaks. Validation and test queries use the full training-link in-degree.
- `court_prior`: Supreme Court 1.0, High Court 0.6, other 0.3 (starting values; tune or fix and report). Extract court from the header text.
- `recency(q, d) = exp(-(year(q) - year(d)) / tau)`, tau tuned.

### 9.6 Temporal filter
If both dates are known, drop candidates whose date is not strictly before the query's date. Report the share of queries and candidates where dates were available. If dates cannot be extracted reliably, say so and skip the filter.

### 9.7 Index structures
- Per-zone inverted index; term dictionary with df; postings with tf; positions for the facts and issues zones (and statute tokens).
- **Memory:** documents average about 8k units each **[CHECK units]**, so a full positional index in plain Python lists may be too large. Store positions in compact arrays (the `array` module or numpy) with delta encoding, measure memory, and restrict positions to the zones that need them if necessary.
- Compression: gap encoding plus variable-byte; report index size before and after.
- Skip pointers: spacing about sqrt(list length); benchmark AND with and without skips.
- Parametric fields: court, year; used for filters and tier building.

### 9.8 Efficiency modules
- **Heap top-K** vs full sort (report the difference).
- **Index elimination:** keep only query terms above an idf threshold; require at least k of n query terms.
- **Champion lists:** per term, the r highest-weight documents.
- **Tiered index:** tier 1 = top fraction of documents by authority; fall through to later tiers only if fewer than K results.
- **Cluster pruning:** about sqrt(N) random leaders, followers assigned to the nearest leader; query goes to the nearest leader(s).
- Measure, against the exhaustive ranker: median and p95 latency, candidates scored, MAP and Recall@10 retained.

### 9.9 Crawl simulation (stretch)
Replay a crawl over the citation graph: F front queues by priority, B back queues one per simulated "host" (use court or year buckets), a heap of next-allowed times with a virtual politeness clock, URL normalisation, and a shingle-Jaccard content-seen check. Priority must use only in-links discovered **so far** (no knowledge of the full graph). Metric: share of the top-cited cases found vs fetch budget, against BFS. Live crawling only if the source's robots.txt and terms allow it.

---

## 10. Evaluation protocol

- **Setup:** all learning and tuning on train and validation; run the 237 test queries once for reported numbers. Fixed random seeds; every run saved to `results/<run_id>/` (metrics.json, per_query.csv, config).
- **Queries:** Facts+Issues (main). Reference rows: full text; Facts-only.
- **Baselines:** (B1) tf-idf lnc.ltc on full text; (B2) BM25 on full text; (B3) BM25 on Facts+Issues. Optional (B4): a small dense-embedding baseline, declared, because published results on IL-PCR disagree about whether lexical or dense retrieval wins.
- **Metrics:** P@k, R@k, F1@k for k = 5, 10, 20; MAP; MRR; nDCG (binary relevance); interpolated precision-recall curve.
- **Significance:** paired bootstrap over test queries (1000 resamples) for key comparisons.
- **Ablations (add one at a time):** zones, learned matrix (N1), statute channel (N2), authority/court/recency and temporal filter (N3), RRF, proximity.
- **Leakage audit:** (a) authority from all links vs train-only; (b) query with vs without scrubbed citations; (c) with vs without the temporal filter. Report the inflation.
- **Sanity checks:** zone-segmenter accuracy, statute-normaliser accuracy, a few hand-judged queries.
- **Efficiency:** Section 9.8 metrics, plus index sizes with and without compression.
- **Reporting:** published numbers from other papers are context only; their setups differ.
- **Figures (auto-generated by `make eval`):** PR curve, ablation bars, zone-pair heatmap, efficiency curve, leakage bars, crawl curve (if built). Also export JSON for the UI.

---

## 11. Architecture, repository layout and merge safety

```
ir-legal/
  README.md  AI_USE.md  Makefile  requirements.txt  config.yaml
  requirements/ ws1.txt ws2.txt ws3.txt ws4.txt         # requirements.txt just includes these
  make/ ws1.mk ws2.mk ws3.mk ws4.mk                      # Makefile just includes these
  docs/ data_notes.md  ws1.md ws2.md ws3.md ws4.md       # README assembles from these
  scripts/ inspect_data.py  download_data.py
  src/irlegal/
    common/        schema.py  interfaces.py  config.py              # FROZEN after Phase 0
    data/          loader.py  splits.py  query_builder.py            # WS1
    preprocess/    tokenizer.py  normalizer.py  segmenter.py         # WS1
    index/         inverted.py  positional.py  compress.py  skips.py  parametric.py  # WS1
    query/         parser.py  boolean.py  statutes.py  tolerant.py  decompose.py  tools.py  # WS2
    ranking/       vsm.py  bm25.py  zonepair.py  authority.py  netscore.py  fusion.py  explain.py  # WS3
    efficiency/    heap.py  elimination.py  champions.py  tiers.py  cluster.py   # WS4
    evaluation/    metrics.py  runner.py  ablate.py  bootstrap.py  leakage.py  plots.py  # WS4
    crawl/         frontier.py  normalize_url.py  dedupe.py  simulate.py          # WS1 (stretch)
  app/
    server.py                    # WS2: FastAPI shell, auto-discovers routers
    routers/ ws1_index.py ws2_query.py ws3_search.py ws4_eval.py   # one router per workstream
    web/ index.html  app.js  styles.css  vendor/
         panels/ index_inspector.js  query_lab.js  results.js  evaluation.js  efficiency.js
  tests/ ws1/ ws2/ ws3/ ws4/
  results/  data/    # both git-ignored
```

**Merge-conflict rules (designed so conflicts are unlikely, not impossible):**
- Each workstream edits **only its own folders, router, panel, tests, docs file, requirements file and make file**. No shared file has two writers.
- `requirements.txt` and `Makefile` contain only include lines pointing to the per-workstream files. The README is assembled from `docs/ws*.md` by a script (WS4).
- The FastAPI shell **auto-discovers** every module in `app/routers/` and every file in `app/web/panels/` (the server exposes `/api/panels`), so no registry file is edited.
- `common/` is frozen after Phase 0. A change needs all four members to agree, and goes through a single dedicated pull request.
- Branch per workstream; small pull requests into `main`; rebase on `main` often; `main` must always run (`make test` passes).
- Data, results and notebooks are not committed.
- Until another workstream's real module lands, code against the toy stubs from Phase 0 (`common/interfaces.py` Protocols plus `tests/fixtures/toy_corpus`).

**Frozen contracts (`common/schema.py`, `common/interfaces.py`):**

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Set, Tuple

ZONES = ("facts", "issues", "arguments", "reasoning", "decision", "other")

@dataclass
class Case:
    doc_id: str
    title: str
    text: str
    court: Optional[str] = None            # "SC", "HC", "OTHER" or None
    date: Optional[str] = None             # ISO "yyyy-mm-dd" or "yyyy" or None
    zones: Dict[str, List[str]] = field(default_factory=dict)  # zone -> sentences
    statutes: Set[str] = field(default_factory=set)            # e.g. {"IPC_302"}
    cites_out: List[str] = field(default_factory=list)         # ground-truth cited doc_ids

@dataclass
class Query:
    qid: str
    case_id: str
    text: str                      # realistic query text (facts + issues)
    zones: Dict[str, str]
    statutes: Set[str]
    date: Optional[str]
    split: str                     # "train" | "val" | "test"
    relevant: Set[str]             # ground-truth cited doc_ids

@dataclass
class Result:
    doc_id: str
    score: float
    components: Dict[str, float]   # text / statute / authority / court / recency / per-zone-pair
    explanation: Dict              # matched statutes, top terms per zone, zone-pair contributions

class Index(Protocol):
    def df(self, term: str, zone: str) -> int: ...
    def postings(self, term: str, zone: str) -> List[Tuple[str, int]]: ...   # (doc_id, tf)
    def positions(self, term: str, zone: str, doc_id: str) -> List[int]: ...
    def doc_len(self, doc_id: str, zone: str) -> int: ...
    def meta(self, doc_id: str) -> Dict: ...                                   # court, date, statutes
    def n_docs(self) -> int: ...

class Ranker(Protocol):
    def rank(self, query: Query, k: int, **opts) -> List[Result]: ...
```

---

## 12. Frontend specification (not graded, but presentation matters)

**Stack (no build step, works offline for recording):** FastAPI backend serving a static single-page app (HTML, CSS, ES-module JavaScript). Charts via a vendored Chart.js in `app/web/vendor/`. A CLI (`python -m irlegal.cli`) must also work; the UI is a layer on top of the same API.

**Design:** clean, modern legal-tech look; responsive; light and dark mode; clear typography; no clutter. Tabs: **Search | Query Lab | Index Inspector | Evaluation | Efficiency | How it works**.

**Dynamic features:**
- **Search:** paste facts and issues or pick a test query; filters (date, court); ranker switch (tf-idf, BM25, ours); pruning switch (none, champion, tier, cluster).
- **Result cards:** title, court, year, net score as a **stacked bar of components**, statute chips, highlighted matched terms, an "explain" drawer showing the strongest zone pairs. Relevant (ground-truth) cases are marked when a dataset query is used.
- **Live re-weighting:** sliders for the net-score weights re-rank client-side instantly (the API returns component scores for the top 100).
- **Pipeline Inspector:** for the current query, shows each stage's real output (cleaned query, zones, statute tokens, terms with df and idf, postings preview, per-zone scores, net-score breakdown). This is what the video shows.
- **Query Lab:** type Boolean/phrase/proximity/zone queries; see the parsed structure; wildcard and spelling suggestions.
- **Index Inspector:** zone segmentation viewer for any case; postings viewer for any term; index size before and after compression.
- **Evaluation:** metrics table, PR curve, ablation chart, zone-pair heatmap, leakage chart, loaded from `results/`.
- **Efficiency:** quality-vs-speed curve, candidates scored.
- **Guided demo:** a button that walks through the flow step by step.

**API (each workstream owns its router):**
`GET /api/health`, `GET /api/panels`, `GET /api/queries`, `POST /api/parse`, `POST /api/search` (text or query_id, ranker, filters, weights, pruning, k), `GET /api/case/{doc_id}`, `GET /api/inspect/index?term=&zone=`, `GET /api/eval/summary`, `GET /api/eval/zone_matrix`, `GET /api/eval/efficiency`.

---

## 13. Four workstreams (balanced; each has code, novelty, concepts, research, a UI panel, tests)

Each workstream has a must-build core and a stretch item. If time is short, drop stretch items first.

### Workstream 1: Data, preprocessing and index
**Must build**
- `data/`: loader for the real dataset, official splits, realistic-query builder with citation scrubbing and leak guards, `scripts/inspect_data.py`, `docs/data_notes.md`.
- `preprocess/`: legal-aware tokenizer (keeps "S.302", "Art. 21", "u/s" forms), case folding, stop words (general plus legal), Porter vs lemma comparison; heuristic zone segmenter (9.2) with accuracy on about 30 hand-labelled judgments; court and date extraction.
- `index/`: per-zone inverted index, positional index (memory-aware), gap + variable-byte compression with before/after sizes, skip pointers with an AND benchmark, parametric fields, a persisted index on disk.
- Router `ws1_index.py` and panel `index_inspector.js` (zone viewer, postings viewer, sizes).
**Stretch:** `crawl/` simulation (9.9).
**Novelty:** role-zone index with a measured heuristic segmenter; leak-safe query building.
**Concepts:** what a document is, tokenisation, normalisation, stemming, zone/positional/parametric indexes, compression, skip pointers (and crawling if built).
**Reads and explains:** IL-PCR / U-CREAT; the rhetorical-roles paper.
**Done when:** the real corpus indexes end to end with one command; tests pass; the zone accuracy and compression numbers are produced by scripts; the panel works.

### Workstream 2: Query understanding, statutes and app shell
**Must build**
- `query/statutes.py`: statute normaliser (9.3), per-statute index, Jaccard and idf-weighted Jaccard, accuracy on a labelled sample.
- `query/parser.py` and `boolean.py`: free text; Boolean AND/OR/NOT; phrase; proximity (`"section 302" /5 murder`); zone-restricted (`facts:murder`); date and court filters; AND processed in increasing-df order with a benchmark.
- `query/tolerant.py`: k-gram wildcard index, edit-distance spelling correction against the corpus vocabulary, Soundex for party-name variants.
- Temporal filter helper (9.6).
- `app/server.py`: the FastAPI shell with router and panel auto-discovery; static layout, styles, theme, tab system; the Query Lab panel and `ws2_query.py` router.
**Stretch:** `decompose.py` (issue decomposition, N6) and `tools.py`, a thin tool registry (search, filter, get_case, compare, explain) with JSON schemas, which is the plug-in point for a future LLM agent (Section 17).
**Novelty:** N2 (statute channel).
**Concepts:** Boolean retrieval, query optimisation, tolerant retrieval, Soundex, Jaccard, query parsers.
**Reads and explains:** LeCoPCR; IIR tolerant retrieval chapter.
**Done when:** the parser handles all listed query forms with tests; the statute normaliser's measured accuracy is reported; the shell loads every panel and router without any shared-file edits.

### Workstream 3: Ranking, fusion and explanations
**Must build**
- `ranking/vsm.py`: lnc.ltc per zone; `bm25.py`; baselines B1 to B3 as `Ranker` implementations.
- `ranking/zonepair.py`: zone-pair scoring and weight learning (9.4); export the matrix for the heatmap.
- `ranking/authority.py`: leak-safe authority (9.5) with leave-one-out for training queries; court prior; recency.
- `ranking/netscore.py`: normalisation, net score, weight tuner on validation.
- `ranking/fusion.py`: RRF; optional proximity boost.
- `ranking/explain.py`: per-result explanation (shared statutes, strongest zone pairs, top contributing terms, authority/court/year).
- Router `ws3_search.py` implementing `/api/search` with ranker switching and component scores; panel `results.js` (result cards, stacked score bars, live re-weighting sliders, explain drawer, zone-pair heatmap).
**Stretch:** an optional dense baseline (declared) wrapped as a `Ranker`.
**Novelty:** N1 (zone-pair matrix) and N3 (leak-safe authority).
**Concepts:** vector space model, SMART weighting, zone scoring, static quality g(d), net score, proximity, rank fusion, BM25.
**Reads and explains:** TraceRetriever; BM25; RRF.
**Done when:** all rankers run on the real corpus; learned matrix and tuned weights are saved to `results/`; explanations render in the UI; tests cover the formulas on a hand-computed toy example.

### Workstream 4: Evaluation, efficiency and release assets
**Must build**
- `evaluation/metrics.py`: P/R/F1@k, MAP, MRR, nDCG, interpolated PR curve, each unit-tested against hand-computed examples.
- `evaluation/runner.py`, `ablate.py`, `bootstrap.py`, `leakage.py`, `plots.py`: run baselines and ablations, paired bootstrap, the three leakage audits (Section 10), auto-generated figures and JSON for the UI.
- `efficiency/`: heap top-K, index elimination, champion lists, authority tiers, cluster pruning; the quality-vs-speed experiment (9.8).
- Router `ws4_eval.py`; panels `evaluation.js` and `efficiency.js`.
- Release assets: `Makefile` targets (`data`, `index`, `eval`, `demo`, `test`), the script that assembles the README from `docs/ws*.md`, `AI_USE.md`, the report figures, the report skeleton.
**Stretch:** cluster-pruning refinements; extra error analysis (queries where each ranker fails).
**Novelty:** N4 and the leakage audit.
**Concepts:** heap top-K, index elimination, champion lists, tiered index, cluster pruning, all evaluation metrics, PR curves.
**Reads and explains:** the LeCoPCR realism critique; IIR efficient scoring and evaluation chapters.
**Done when:** `make eval` regenerates every table and figure from scratch; metric functions pass tests; the efficiency curve and leakage chart exist; README reproduces the run.

---

## 14. Phase 0 scaffold prompt (run first, once)

> You are the architect. Using the Master Spec, create the repository skeleton exactly as in Section 11: all folders, empty modules with docstrings stating the owning workstream, `common/schema.py` and `common/interfaces.py` exactly as given, a tiny hand-made toy corpus in `tests/fixtures/toy_corpus` (about 20 short cases with zones, statutes, dates, citations) with a toy `Index` and toy `Ranker` implementing the Protocols, the FastAPI shell (`app/server.py`) that auto-discovers routers in `app/routers/` and panels in `app/web/panels/` and serves `/api/health` and `/api/panels`, the static shell (`index.html`, `app.js`, `styles.css`, tabs, light/dark theme), per-workstream requirements and make files that the root `requirements.txt` and `Makefile` include, `.gitignore` (data/, results/, notebooks, caches), a README stub, `AI_USE.md`, and a pytest that loads the toy corpus. Make `make test` and `make demo` work. Commit to `main` with a clear message and tag `contracts-v1`. Do not implement any real IR logic.

---

## 15. Timeline (36 hours from release; compress if the clock has already started)

| Hours | Goal |
|---|---|
| 0 to 2 | Plan locked; Phase 0 scaffold merged; dataset downloaded; hour-1 data checks done; contracts frozen |
| 2 to 10 | Walking skeleton: loader, basic index, tf-idf and BM25 baselines producing real numbers end to end; toy stubs replaced by real modules as they land |
| 10 to 20 | Zones, statute channel, authority prior, net score, RRF, parser, first UI panels |
| 20 to 28 | Efficiency modules, ablations, bootstrap, leakage audit, polish the UI; stretch items only if the core is stable |
| 28 to 34 | README that reproduces the run, report (8 pages), demo video |
| 34 to 36 | Buffer, final reproducibility check on a clean clone, submit |

**Cut order if short on time:** crawl simulation, issue decomposition, dense baseline, cluster pruning, wildcard queries, UI polish. **Must work:** index, zones, baselines, net score, evaluation with ablation, the Search and Evaluation panels.

---

## 16. Git workflow

- Branch per workstream: `feat/ws1-index`, `feat/ws2-query`, `feat/ws3-ranking`, `feat/ws4-eval`.
- Commit after each working unit (a function with its tests, a figure script, a panel). Use clear messages, for example `feat(index): add variable-byte codec with round-trip tests`.
- One pull request per feature into `main`; a teammate reviews quickly; `make test` must pass.
- Rebase on `main` before opening a pull request. Never force-push `main`.
- Everyone commits from their own machine under their own git identity (`git config user.name` and `user.email`).
- If a module you need is not merged yet, use the toy stub and leave a `TODO(ws<N>)` marker.

---

## 17. Agentic roadmap and beyond lawyers

**In this version (optional stretch):** issue decomposition (N6), a tool registry with JSON schemas (`query/tools.py`). No LLM is required for either.

**Future agentic layer (design now, build later):**
- An LLM planner calls the registered tools: search, filter by statute/date/court, fetch a case, compare two cases, explain, and cite-check.
- Multi-turn follow-ups ("narrow to High Courts after 2010", "drop the limitation point") that rewrite the query and re-run retrieval, reusing the same ranker.
- Per-issue retrieval plus fusion to build a precedent table for a whole brief.
- Statute retrieval alongside case retrieval (the IL-PCSR corpus supports this).
- Any LLM use must be declared and must never replace the IR core.

**Beyond lawyers (the abstractions are domain-neutral):** zones, statute-like references, authority and recency generalise. Possible users: law students and clerks, journalists, policy and compliance analysts. Possible domains: tax tribunals, consumer forums, regulatory orders, patents; other jurisdictions (for example the Canadian COLIEE data). The heuristic role segmenter is tuned for Indian judgments and would need adapting.

---

## 18. Deliverables, rubric mapping and checklists

**Rubric (100 marks):** IR principles 30; working system 20; evaluation 15; novelty 10; report 10; video 10; track relevance 5.

| Rubric line | How we answer it |
|---|---|
| IR principles (30) | Section 7 map; each concept has a job and appears in an evaluation or the UI |
| Working system (20) | Real end-to-end run on real queries; README reproduces it with make targets |
| Evaluation (15) | Section 10: judged benchmark, baselines, metrics, ablation, significance, leakage audit |
| Novelty (10) | N1 to N4 core; N5 and N6 stretch; honest positioning against prior work |
| Track relevance (5) | Law is a named T6 domain; structure, statutes and authority are used |
| Report (10) / Video (10) | Below |

**Submission:** repository link with README; 5 to 8 minute demo video (unlisted link); report PDF of at most 8 pages including work division and AI-use declaration.

**README must have:** what it is; setup; where the data comes from (with licence and credit); one-command run; what works; what is planned; results tables; limitations.

**Report outline (at most 8 pages):** 1 Problem and track relevance (papers referred to); 2 How we used IR (principles, where in code, why; pipeline diagram); 3 Beyond IR; 4 Novelty and creativity; 5 Evaluation (tables and graphs, baselines, ablations, leakage audit); 6 Limitations and next steps (with roadmap); 7 Work division (short note, no percentages); AI-use declaration.

**Video outline (5 to 8 minutes, no slides, live):** problem and track fit (under 1 min); system running on real queries including one limitation; pipeline with real intermediate output (postings, weights, scores); evaluation results against baselines; each member explains the component they own and its novelty. **Each member must be able to explain their own module's code and the concepts behind it.**

**Final checklist before submitting:**
- [ ] Fresh clone runs: `make data`, `make index`, `make eval`, `make demo`
- [ ] Every number in README, report and video comes from a saved run
- [ ] Dataset credited with licence (CC BY-NC 4.0, research use)
- [ ] `AI_USE.md` complete and reflected in the report
- [ ] No live crawling unless robots.txt and terms allowed it
- [ ] Limitations stated, including where baselines win
- [ ] Citations verified (every [M] item checked or removed)

---

## 19. Risks and first-hour checklist

**Risks:** heuristic zoning may be noisy; dense models may beat a lexical system on some metrics; the corpus is small for efficiency claims; authority features leak test labels if built from all links; the positional index may not fit memory if built naively; date and court extraction may be unreliable.

**First-hour checklist:**
- [ ] Locate and download the real dataset; run `inspect_data.py`; write `docs/data_notes.md`
- [ ] Confirm fields, counts, splits, protocol, citation strings in text
- [ ] Check date, court, role-annotation availability; decide filter and zone strategy
- [ ] Check statute pattern frequency
- [ ] Confirm one canonical repository; Phase 0 scaffold merged; contracts frozen
- [ ] Confirm each member's environment (Python version, packages, Claude Code login, git identity)

---

## Appendix: references

- [V] Joshi, Sharma, Tanikella, Modi. U-CREAT: Unsupervised Case Retrieval using Events extrAcTion. ACL 2023 (aclanthology.org/2023.acl-long.777; arXiv 2307.05260). IL-PCR repository: github.com/Exploration-Lab/IL-PCR (CC BY-NC 4.0).
- [V] Nigam, Dubey, Shallum, Bhattacharya. Segment First, Retrieve Better: Realistic Legal Search via Rhetorical Role-Based Queries. arXiv 2508.00679 (2025).
- [V] Santosh, Olguin Nolasco, Grabmair. LeCoPCR: Legal Concept-guided Prior Case Retrieval for European Court of Human Rights cases. arXiv 2501.14114 (2025).
- [V as cited] Bhattacharya, Paul, Ghosh, Ghosh, Wyner. Identification of Rhetorical Roles of Sentences in Indian Legal Judgments. JURIX 2019. Confirm the original before citing.
- [V title and venue] IL-TUR: Benchmark for Indian Legal Text Understanding and Reasoning. ACL 2024. Confirm authors.
- [M] Robertson and Zaragoza. The Probabilistic Relevance Framework: BM25 and Beyond. 2009.
- [M] Cormack, Clarke, Buettcher. Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods. SIGIR 2009.
- [M] Heydon and Najork. Mercator: A Scalable, Extensible Web Crawler. 1999.
- Manning, Raghavan, Schuetze. Introduction to Information Retrieval (course text); course lecture decks 1, 2, 3, 5 (recap), 6, 7, 8, 20.
