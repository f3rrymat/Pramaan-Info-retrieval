# Toy corpus (hand-made, fictional)

20 candidate cases (`cases.jsonl`: 10 in the train pool, 4 val, 6 test) and 6 queries
(`queries.jsonl`: 3 train, 1 val, 2 test). Party names and facts are invented; they do
not describe real judgments. Relevant cases are always in the query's own pool and older
than the query, mirroring the per-split protocol of IL-TUR PCR.

Deliberate test hooks:
- Query cases contain `<CITATION>`, "AIR 1985 SC 1461" and "(1994) 3 SCC 112" in their
  non-query zones and one `<CITATION>` in the facts, so the WS1 scrubber has work to do.
- Statutes appear in varied forms ("Section 302 read with Section 34 IPC", "u/s 138 of
  the N.I. Act", "Art. 21", "Sec. 80IA", "Section 80-IA of the Income-tax Act, 1961")
  for the WS2 normaliser. The `statutes` field holds the expected canonical tokens.
- T05, T07 and T10 cite older train-pool cases, giving WS3 a tiny citation graph.

Never report numbers computed on this corpus.
