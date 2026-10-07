"""Evaluation-only access to QUERY gold statute labels (D13). Owner: WS4.

This is the only module besides the loader's pool accessor that may read `relevant_statute_ids`.
Nothing here feeds a ranker: it measures how well predicted provisions match the gold ones.
"""
from pathlib import Path
from typing import Dict, List, Sequence, Set

import pandas as pd

from irlegal.common.config import load_config, repo_path
from irlegal.data.loader import SPLIT_FILE


def gold_statute_ids(split: str) -> Dict[str, Set[str]]:
    d = Path(repo_path(load_config()["dataset"]["local_dir"]))
    df = pd.read_parquet(d / f"{SPLIT_FILE[split]}.parquet", columns=["id", "relevant_statute_ids"])
    return {r.id: set(r.relevant_statute_ids) for r in df.itertuples(index=False)}


def prediction_recall(bridge, queries, gold: Dict[str, Set[str]], ms: Sequence[int] = (5, 10)) -> Dict[str, float]:
    """Mean Recall@k of the bridge's top-k provisions against gold, over queries with gold and non-empty text."""
    out = {}
    kmax = max(ms)
    ranked = {}
    for q in queries:
        if q.text and gold.get(q.qid):
            rows, _ = bridge.predict(q.text, kmax)
            ranked[q.qid] = [bridge.prov_ids[r] for r in rows]
    for k in ms:
        vals = [len(set(ranked[qid][:k]) & gold[qid]) / len(gold[qid]) for qid in ranked]
        out[f"Recall@{k}"] = round(sum(vals) / len(vals), 4)
    out["n_queries"] = len(ranked)
    return out
