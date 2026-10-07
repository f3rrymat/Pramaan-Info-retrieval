"""Benchmark AND processing order on the real index: as written (`input_order`) vs smallest posting list first
(`df_order`), both with skip pointers. Queries: 3-5 random words from random dev queries (words, never printed).
Saves results/and_benchmark.json. Usage: python scripts/bench_and.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.data.loader import IlPcsrCorpus  # noqa: E402
from irlegal.index.inverted import InvertedIndex  # noqa: E402
from irlegal.preprocess.normalizer import STOPWORDS, Analyzer  # noqa: E402
from irlegal.query.boolean import BooleanSearcher, benchmark_and  # noqa: E402
from irlegal.preprocess.tokenizer import tokenize  # noqa: E402

cfg = load_config()
index = InvertedIndex.load(repo_path(cfg["paths"]["index_dir"]))
an = Analyzer()
rng = np.random.default_rng(cfg["seed"])
dev = IlPcsrCorpus().queries("val")
queries = []
while len(queries) < 300:
    q = dev[rng.integers(len(dev))]
    words = [w for w in tokenize(q.text) if w.isalpha() and len(w) > 3 and w not in STOPWORDS]
    if len(words) >= 8:
        queries.append(" AND ".join(rng.choice(words, size=int(rng.integers(3, 6)), replace=False)))
out = benchmark_and(lambda strat: BooleanSearcher(index, an, strat), queries, repeats=3)
out["note"] = "comparisons are counted by the skip-pointer merge; seconds are wall time on this machine; pool = %d docs" % index.n_docs()
(Path(repo_path("results")) / "and_benchmark.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
