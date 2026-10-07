# Data notes

Owner: WS1. Every number below comes from `scripts/inspect_data.py` (saved to `results/data_inspect.json`)
or `scripts/build_index.py` (`results/index_report.json`), run 2026-10-06 on the local IL-PCSR files.
Aggregates only; no case text or titles appear here.

## Source
- **IL-PCSR** (prior case and statute retrieval), local copy in `data/ilpcsr/`, five parquet files. Dataset card: CC BY-NC-SA 4.0, research use only, no redistribution. Never committed.
- Earlier text about IL-PCR / IL-TUR packaging in SPEC_CHANGES.md is superseded by DECISIONS.md D1.

## Results
| Check | Result |
|---|---|
| Rows | train queries 5,017; dev 627; test 627; precedent pool 3,183; statutes 936 |
| Duplicate ids | 0 in every file |
| `len(text) == len(rhetorical_roles)` | holds for every row, every file |
| Relevant precedents per query (mean / median / max) | train 2.70 / 2 / 21; dev 2.72 / 2 / 21; test 2.58 / 2 / 22 |
| Queries with zero relevant ids | train 5; dev 1; test 1 (skipped in metrics) |
| Relevant ids inside the pool | 100% in all three splits |
| Query cites its own id | test: 1 query (own id is excluded from candidates and from its relevant set) |
| Query ids that also occur in the pool | train 0.28%; dev 0.64%; test 0.48% |
| Distinct relevant ids cited by some train query | dev 89.2%; test 86.6% (by pair: dev 91.1%; test 87.3%) |
| Parseable date | train 94.3%; dev 93.3%; test 93.8%; pool 86.8%. Unparseable = empty string or a bare year ("9999" shape) |
| Missing title | train 330; dev 41; test 35; pool 383 |
| Jurisdictions | distinct: train 28, dev 27, test 26, pool 17. Pool: Supreme Court 2,839 (89.2%), High Courts 344 (10.8%), nothing else |
| Paragraphs per doc (mean / median / max) | queries about 39-43 / 32-35 / 230-282; pool 67.0 / 39 / 3,178 |
| Whitespace tokens per doc (mean / median / max) | train 3,351 / 2,866 / 10,010; dev 3,599; test 3,553; pool 7,882 / 4,667 / 417,204 |
| Facts+Issues query length (words, mean / median) | train 525 / 401; dev 548 / 400; test 562 / 439 |
| Queries whose Facts+Issues text is empty | train 147 (2.9%); dev 15; test 22 |
| Official evaluation protocol | none shipped; DECISIONS D1 rule used: shared pool, minus the query's own id |

### Role labels (paragraph counts)
| Label | train queries | dev | test | pool |
|---|---|---|---|---|
| Precedent Analysis | 58,766 | 8,033 | 7,368 | 69,537 |
| Court Reasoning | 28,606 | 3,718 | 3,672 | **0** |
| Statute Analysis | 27,190 | 3,897 | 3,857 | 46,306 |
| Conclusion | 24,845 | 3,341 | 2,995 | 19,906 |
| Issue | 19,379 | 2,468 | 2,461 | 17,950 |
| Facts | 14,731 | 2,027 | 1,950 | 12,201 |
| Argument by Petitioner | 13,250 | 1,878 | 1,658 | 8,055 |
| Argument by Respondent | 8,838 | 1,325 | 1,118 | 5,704 |
| NONE | 663 | 77 | 88 | 3,183 |
| **Court Disclosure** | 0 | 0 | 0 | **30,317** |

### D12 profile: pool "Court Disclosure" vs query "Court Reasoning" (`scripts/profile_roles.py`, paragraphs from train queries / pool)
| Role | Paragraphs | Mean relative position | Share in last 10% | Mean words |
|---|---|---|---|---|
| Court Disclosure (pool) | 30,317 | 0.564 | 11.2% | 167.3 |
| Court Reasoning (train queries) | 28,606 | 0.526 | 7.6% | 119.2 |
| Conclusion (queries / pool) | 24,845 / 19,906 | 0.853 / 0.826 | 52.2% / 46.5% | 41.6 / 56.9 |
| Precedent Analysis (queries / pool) | 58,766 / 69,537 | 0.589 / 0.568 | 7.4% / 9.2% | 85.0 / 105.4 |

Position gap to Court Reasoning is 0.038 (rule: <= 0.15) and 11.2% sits in the last 10% (rule: < 50%), so **D12 maps "Court Disclosure" to `reasoning`** in the loader. Vocabulary cosine (document-frequency vectors): Court Disclosure vs query Court Reasoning 0.925, vs query Conclusion 0.773, vs query Precedent Analysis 0.888. Distinctive stems of Court Disclosure over Court Reasoning are mostly constitutional/statute references (art.14, art.226, art.32, s.34, s.313) and judge names (the pool is unmasked); the reverse direction is dominated by years and masking artefacts. Pool paragraphs average 40% longer than the query-side ones. A human spot check may still override. The earlier finding 1 below is superseded by this mapping.

### Findings that contradict or extend DECISIONS.md
1. **Pool and queries use different role label sets.** "Court Disclosure" (30,317 paragraphs) occurs only in the pool; "Court Reasoning" occurs only in queries. So the pool's `reasoning` zone is empty. "Court Disclosure" is mapped to `other` for now (meaning unverified). This matters for N1: the query-reasoning x candidate-reasoning cell cannot be learned unless "Court Disclosure" is declared equivalent to reasoning. NONE appears exactly once per pool document (3,183).
2. **Query text is masked, pool text is not.** Placeholders `[SECTION]`, `[ACT]`, `[ENTITY]`, `[PRECEDENT]`, `[CASE NUMBER]` appear in the queries (documents containing at least one in Facts+Issues, dev: SECTION 530/627, ACT 532, ENTITY 455, CASE NUMBER 294, PRECEDENT 75) and in none of the pool documents (pool has bracketed judge names only). Consequences: (a) the analyzer strips these placeholders; (b) **statute identities are masked in most query Facts+Issues**, so N2 (statute channel from text) has little to work with on the query side; (c) vocabulary is asymmetric between queries and the pool.
3. **Statute patterns that survive in Facts+Issues** (queries with at least one, dev): "Section" 25, "Sec." 3, "Art." 4, "u/s" 6 of 627 (test: 17 / 2 / 1 / 7).
4. **Case citations in Facts+Issues are rare.** Dev queries with a raw AIR / SCC / SCR / SCALE / "v." pair pattern: 4 / 7 / 0 / 1 / 13. The scrubber removed (dev, Facts+Issues): SCC 12, AIR 5, party-pair-with-year 2, SCALE 1; train 140 removals in total. After scrubbing, dev still has 1 query with "SCC" and 11 with a "v." pair that has no year. No `<CITATION>` token occurs in the data (the masking uses `[PRECEDENT]`).
5. **Cited case names**: an exact normalised match of a cited precedent's title in the query text found 0 of 1,473 usable (query, cited id) pairs in Facts+Issues and 0 in the full text; titles are missing for 231 pairs. Titles are probably masked in the query text too, so a name leak could not be shown by this check; it does not prove there is none.
6. **Temporal sanity.** Where both dates are known, a relevant precedent is dated after the query in 2.2% of pairs (train 244 of 11,069; dev 31 of 1,382; test 34 of 1,354). A hard temporal filter therefore loses roughly 2% of true positives. Both dates are known for 1,382 of 1,704 dev pairs (81%).
7. **Pool artifact (DECISIONS section 3).** (a) 97.1% of pool ids are cited by some query in any split; 90.4% by a train query. (b) Pool ids with zero train in-degree: 307 (9.6%); **69.7%** of them are relevant to some dev or test query, versus 55.5% for ids with positive train in-degree; 93 of the 307 are cited by no query at all. At the (query, relevant id) pair level only 8.9% (dev) and 12.7% (test) of relevant ids have zero train in-degree, close to their 9.6% share of the pool, so low popularity is not a strong positive signal. Net-score weights stay non-negative (D7). Train in-degree over the pool: mean 4.26, median 3, max 182.

## Preprocessing and index (Phase A)
- Tokenizer keeps `s.302`, `art.21`; stop words are our own list; Porter stemmer from nltk (stemmer only).
- Index: 3,183 documents, 12.26M indexed tokens (whole-text zone), 100,166 distinct terms (whole text). Zones: the 8 schema zones plus derived `fi` (facts + issues) and `all`. Positions are kept for facts and issues only.
- Persisted size (gap + variable-byte, all zones): 17.9 MB versus 65.0 MB as raw int32 arrays (a 3.6x reduction); in-memory index 73.6 MB; process RSS grew from 185 MB to 1,060 MB during the build (transient token lists).
- Skip-pointer AND benchmark (500 random pairs of whole-text lists with df >= 50): 325,540 comparisons without skips versus 309,058 with skips (5% fewer); wall time was not better. Lists are short (at most 3,183 docs), so skips barely pay here.

## Later findings (phases B to D; numbers are in `results/`, listed here only by file)
- **Pool artifact and popularity** (`results/data_inspect.json`): ids with zero train citations are not a positive signal at the pair level; popularity alone is weak (`results/dev_eval.json`).
- **Citation graph**: pool-internal edges plus TRAIN-query edges only; a query whose case also sits in the pool loses that pool document's own edges for every split (`ranking/authority.py`).
- **Neighbour feature**: built from TRAIN queries only; the index constructor rejects any non-train query; leave-one-out for train queries (`results/leakage_audit.json` shows the inflation without it).
- **Temporal sanity**: a small share of relevant precedents is dated after the query; the filter is reported side by side (`results/dev_eval.json`, `results/test_eval.json`).
- **D12** is applied in the loader: "Court Disclosure" maps to `reasoning`; profile in `results/role_profile.json`. A human spot check has not been done.
- **Statute table**: the `text` column is a list of paragraphs per provision; 906 of 936 provision names parse to a normaliser token (`results/statute_bridge.json`).
- **Not used as inputs, anywhere**: query gold statute ids (evaluation only, `evaluation/statute_eval.py`) and dev/test citations.

- `results/` ships with the project and contains aggregates only (ids, scores, counts); the one text-derived field found (stem lists in `role_profile.json`) was removed, see `docs/results_scan.md`.
