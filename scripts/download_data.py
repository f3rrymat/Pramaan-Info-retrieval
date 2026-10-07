"""Download the IL-PCR data (IL-TUR 'PCR' task) into data/raw/. Owner: WS1.

Facts from the Hugging Face dataset card (read 2026-10-06, verify after download):
  * repo "Exploration-Lab/IL-TUR"; gated: each member must log in on huggingface.co,
    accept the dataset conditions, then run `huggingface-cli login` (token).
  * card usage: load_dataset("Exploration-Lab/IL-TUR", "<task_name>", revision="script")
  * PCR splits: train_queries, dev_queries, test_queries, train_candidates,
    dev_candidates, test_candidates; fields: id, text (list of sentences),
    relevant_candidates (None for candidates).

TODO(ws1): implement; save raw splits as JSONL; never commit data/.
"""

if __name__ == "__main__":
    raise SystemExit("TODO(ws1): not implemented yet -- see docstring and docs/data_notes.md")
