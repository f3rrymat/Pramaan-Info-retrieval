"""D14: tune BM25 on DEV only (k1, b, query-term handling) for Facts+Issues queries against
full-text docs ("all") and Facts+Issues docs ("fi"). Saves results/bm25_tuning.{json,csv}.
Usage: python scripts/tune_bm25.py
"""
import csv
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.data.loader import IlPcsrCorpus  # noqa: E402
from irlegal.evaluation.metrics import evaluate_ranking  # noqa: E402
from irlegal.index.inverted import InvertedIndex  # noqa: E402
from irlegal.preprocess.normalizer import Analyzer  # noqa: E402
from irlegal.ranking.bm25 import BM25Ranker  # noqa: E402

cfg = load_config()
index = InvertedIndex.load(repo_path(cfg["paths"]["index_dir"]))
an = Analyzer()
qs = [q for q in IlPcsrCorpus().queries("val") if q.relevant - {q.case_id}]
ids = index.doc_ids()
rows = []
for zone, qmode, k1, b in itertools.product(("all", "fi"), ("binary", "raw", "saturated"), (0.9, 1.2, 1.5, 2.0), (0.4, 0.6, 0.75, 0.9)):
    r = BM25Ranker(index, an, zone, k1=k1, b=b, qtf_mode=qmode)
    ms = [evaluate_ranking([ids[i] for i in r.order(q)[0]], q.relevant - {q.case_id}, (10,)) for q in qs]
    rows.append({"doc_zone": zone, "qtf": qmode, "k1": k1, "b": b, "n": len(ms),
                 **{m: round(float(np.mean([x[m] for x in ms])), 4) for m in ("MAP", "MRR", "R@10", "nDCG@10")}})
# B2 task 1: one more step (k1 12 and 20 with b 1.0), then tuning stops. The first grid peaked in its corner (k1=2.0, b=0.9), so extend it beyond the D14 grid (raw qtf only).
for zone, k1, b in itertools.product(("all", "fi"), (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 20.0), (0.9, 1.0)):
    if any(r["doc_zone"] == zone and r["k1"] == k1 and r["b"] == b and r["qtf"] == "raw" for r in rows):
        continue
    r = BM25Ranker(index, an, zone, k1=k1, b=b, qtf_mode="raw")
    ms = [evaluate_ranking([ids[i] for i in r.order(q)[0]], q.relevant - {q.case_id}, (10,)) for q in qs]
    rows.append({"doc_zone": zone, "qtf": "raw", "k1": k1, "b": b, "n": len(ms), "extended_grid": True,
                 **{m: round(float(np.mean([x[m] for x in ms])), 4) for m in ("MAP", "MRR", "R@10", "nDCG@10")}})
default = {z: next(r for r in rows if r["doc_zone"] == z and r["qtf"] == "raw" and r["k1"] == 1.2 and r["b"] == 0.75) for z in ("all", "fi")}
best = {z: max((r for r in rows if r["doc_zone"] == z), key=lambda r: r["MAP"]) for z in ("all", "fi")}
out = Path(repo_path(cfg["paths"]["results_dir"]))
out.mkdir(exist_ok=True)
(out / "bm25_tuning.json").write_text(json.dumps({"split": "dev", "query": "facts_issues", "selection": "MAP",
                                                  "default": default, "tuned": best, "grid": rows}, indent=1))
with open(out / "bm25_tuning.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]) + ['extended_grid'], restval='')
    w.writeheader(); w.writerows(rows)
print("default", json.dumps(default)); print("tuned", json.dumps(best))
