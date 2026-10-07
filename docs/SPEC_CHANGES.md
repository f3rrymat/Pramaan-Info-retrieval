# Spec review and changes (contracts-v1)

Review of `IR_HACKATHON_MASTER_SPEC.md` before Phase 0, done against the live
IL-TUR dataset card on Hugging Face and the IL-PCR GitHub README (both read
2026-10-06). Items marked **DECIDE** need a team decision after the hour-1 data check.

## 1. Data facts that differ from the spec

| Spec says | Source says | Impact |
|---|---|---|
| One corpus of 7,070 docs; exclude only the query itself | IL-TUR ships **separate query and candidate pools per split**: train_queries 827, dev_queries 118, test_queries 237; train_candidates ~4.3k, dev_candidates ~1k, test_candidates ~1.7k (card rounds these; recount) | Official protocol ranks test queries against **test_candidates only**. Added `Case.pool` and `dataset.eval_pool` in config. |
| Courts: SC / HC / other, `court_prior` 1.0 / 0.6 / 0.3 | Card: candidate and query documents are **all Supreme Court** | `court_prior` is likely constant, so it carries no signal. Keep the component (cheap), expect its tuned weight to be 0, and drop it from novelty claims. Verify on real headers. |
| Licence CC BY-NC 4.0 | IL-PCR repo: CC BY-NC; IL-TUR HF card: **CC BY-NC-SA 4.0** | Credit both; we never redistribute data, so share-alike does not bite, but the README must name both licences. |
| "Find the files" | IL-TUR on HF is **gated**: log in, accept conditions, use an HF token | Every member who runs `make data` needs their own HF account and token. |
| `text` is a string | `text` is a **list of sentences** | Free sentence splitting; the loader joins for `Case.text` and keeps the list for the segmenter. |
| Hand-label ~30 judgments for zone accuracy | IL-TUR includes an **RR (rhetorical role) task**: 100 SC judgments, 21,184 sentences, 13 labels (Fact, Issue, ArgumentPetitioner, ArgumentRespondent, Statute, Precedent..., RatioOfTheDecision, RulingByPresentCourt, ...) | Evaluate the heuristic segmenter on RR test splits instead of hand-labelling (saves hours, gives a citable number). Caveat: RR covers Competition Law and Income Tax only, so report it as a domain-shifted estimate. |
| Metrics P/R/F1@k, MAP, ... | Leaderboard metric is **micro-F1@K** (SOTA listed 39.15%, event-based) | Add micro-F1@K so our numbers sit next to the official one (context only, setups differ). |

## 2. The biggest risk: N3 (leak-safe authority) may have no signal on test

`indegree_train(d)` counts training queries that cite `d`. If the train and test
candidate pools are disjoint (likely, since IL-TUR splits candidates too), every
test candidate has in-degree 0 and the authority prior is a constant on test.

**DECIDE after `scripts/inspect_data.py` reports pool overlap:**
- **(a) Overlap is substantial:** keep N3 as specified.
- **(b) Pools disjoint, keep the official protocol (recommended):** N3 becomes a
  negative-result finding. The leakage audit gets stronger, not weaker: an
  all-links authority will look great on test, and the train-only version shows
  that all of that gain was leakage. Recency stays as a static-quality signal.
- **(c) Pooled setting:** merge all candidate pools (~7k docs) so train links can
  reach test candidates. Non-standard, so report it as a separate labelled table,
  never mixed with official numbers.

The contracts support all three (`Case.pool`, `config.dataset.eval_pool`).

## 3. Contract changes made in Phase 0 (all additive, all defaulted)

Spec fields, order and meaning are unchanged (`tests/test_contracts.py` checks this).

- `schema.Case.pool: Optional[str] = None`: which candidate pool a case is in.
- `schema` constants: `QUERY_ZONES`, `SPLITS`, `COURTS`, `COMPONENTS` (one spelling for router, UI and eval).
- `Index.terms(zone)` and `Index.doc_ids()`: needed by k-gram/spelling (WS2), Index Inspector (WS1), norm precomputation (WS3) and cluster pruning (WS4).
- New Protocols at the cross-workstream seams: `CorpusSource` (WS1 to all), `Segmenter` (WS1), `StatuteNormalizer` (WS2 to WS1/WS3), `CandidateSelector` (WS4 to WS3).
- `Ranker.rank` opts documented: `candidates`, `exclude`, `weights`.
- `common/toy.py`: `ToyCorpus`, `ToyIndex`, `ToyRanker` implement the Protocols over the fixture.

Layout additions not in Section 11: `make/core.mk` and `requirements/base.txt`
(Phase 0 core, so `test`/`demo` and shared deps have one owner), `query/temporal.py`
(WS2's temporal filter helper had no file), `src/irlegal/cli.py` (WS3), `pyproject.toml`.

## 4. Smaller gaps and risks

1. **Novelty framing.** Learning zone weights is in the course textbook (IIR 6.1.2, weighted zone scoring) and per-field weighting is BM25F (Robertson, Zaragoza, Taylor 2004 [M]). Cite both; N1's claim is the *cross* matrix (query zone x candidate zone) on rhetorical-role zones for PCR, and what it reveals (e.g. facts->reasoning weight). N4 is a measured study of course techniques, not a novelty; call it a contribution, not novel. Strongest distinct pieces: N1 heatmap, N2 normaliser, and the leakage audit.
2. **Query zones depend on the segmenter.** The headline Facts+Issues setting inherits segmenter errors. Report the RR-based accuracy next to the main table and keep the position-thirds fallback as an ablation row.
3. **Leakage audit (c).** Temporal filtering is a sanity constraint, not leakage (true citations are always older). Report it under sanity checks.
4. **Dates.** Candidate headers seem to carry case numbers with years ("Appeal (civil) 2387 of 2001"), but the decision date may be missing. Measure coverage before relying on recency or the filter.
5. **Cost of learning W.** 12 zone-pair cosines per (query, candidate): precompute once per split (827 x ~4.3k x 12 floats is roughly 170 MB as float32), then coordinate ascent and the 200-trial random search are cheap.
6. **Windows.** `make` needs WSL or Git Bash. Anyone on plain Windows can run the underlying commands from `make/core.mk`.
7. **Scope.** Four people, 36 hours, eight UI tabs' worth of features. The cut order in Section 15 is right; additionally treat the Pipeline Inspector and Guided demo as polish.

## 5. Post-Phase-0 contract change (DECISIONS.md D8)

`schema.ZONES` gains two zones appended after the original six: `statute_analysis` and
`precedent_analysis` (IL-PCSR labels paragraphs with these roles). The first six are
unchanged, so existing code keeps working; `tests/test_contracts.py` now checks the prefix.
Dataset split name `dev` maps to `schema.SPLITS` entry `"val"` in the loader.
