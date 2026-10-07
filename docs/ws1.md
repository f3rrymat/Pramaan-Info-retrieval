### WS1: data, preprocessing, index
- **What it does.** Loads the five IL-PCSR parquet files (`data/loader.py`), maps role labels to zones (Facts, Issue, Argument by Petitioner or Respondent, Court Reasoning and the pool-only "Court Disclosure" to reasoning, Conclusion to decision, Statute Analysis, Precedent Analysis), builds the realistic query (Facts + Issues, citation strings scrubbed, `data/query_builder.py`), tokenises with statute-aware tokens (`s.302`, `art.21`), stems with Porter, and builds a per-zone inverted index plus derived `fi` and `all` zones, with positions kept only for facts and issues. The index is persisted with gap + variable-byte compression; skip pointers are benchmarked.
- **Run.** `make index` (or `python scripts/build_index.py`); data checks with `make data` (or `python scripts/inspect_data.py`); role profile with `python scripts/profile_roles.py`.
- **Results.** Index size, compression ratio and the skip benchmark are loaded from `results/index_report.json` (see the generated results in the README).
- **Limitations.** Query text is masked (`[SECTION]`, `[ACT]`, `[ENTITY]`, `[PRECEDENT]`), pool text is not; one pool role label ("Court Disclosure") is mapped to reasoning from a position profile, not from a human check.

### WS1 stretch: crawl simulation
- **What it does.** `crawl/` replays a Mercator-style crawl (front queues by in-links discovered so far, back queues per host, virtual politeness clock, URL normalisation, shingle-Jaccard duplicate check) over the citation graph, with courts as simulated hosts. No network traffic.
- **Run.** `python scripts/run_crawl_sim.py` (writes `results/crawl_sim.json`).
