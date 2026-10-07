"""N5 crawl simulation on the citation graph (simulation only, no network). Saves results/crawl_sim.json.

Pages = pool precedents + TRAIN queries; links = cited documents; hosts = jurisdictions; virtual politeness clock.
Compares the in-link-priority Mercator crawler with BFS on the share of the 200 most-cited pool documents fetched
within a budget, averaged over 5 random seed sets. Usage: python scripts/run_crawl_sim.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.crawl.dedupe import ContentSeen  # noqa: E402
from irlegal.crawl.simulate import SimWeb, crawl, share_found, slug  # noqa: E402
from irlegal.data.loader import IlPcsrCorpus  # noqa: E402

cfg = load_config()
D = Path(repo_path(cfg["dataset"]["local_dir"]))
pool = pd.read_parquet(D / "precedent_candidates.parquet", columns=["id", "jurisdiction", "relevant_precedent_ids"])
train = pd.read_parquet(D / "train_queries.parquet", columns=["id", "jurisdiction", "relevant_precedent_ids"])
corpus = IlPcsrCorpus()
text_pool = {c.doc_id: " ".join(c.text.split()[:300]) for c in corpus.cases()}
text_q = {q.qid: " ".join(q.text.split()[:300]) for q in corpus.queries("train")}
pool_ids = set(pool.id)
pages = {}
for r in pool.itertuples(index=False):
    pages[r.id] = (slug(r.jurisdiction) + ".sim", [c for c in r.relevant_precedent_ids if c in pool_ids and c != r.id], text_pool[r.id])
for r in train.itertuples(index=False):
    pages["q" + r.id] = (slug(r.jurisdiction) + ".sim", [c for c in r.relevant_precedent_ids if c in pool_ids], text_q[r.id])
indeg = Counter(c for pid, (_, out, _) in pages.items() for c in out)
# Legal portals list both "cites" and "cited by" on a case page, so links run both ways. Without the back-links a
# crawl that starts at train-query pages is a dead end after two hops (verified on a first run: ~37 pages reachable).
cited_by = {}
for pid, (_, out, _) in pages.items():
    for c in out:
        cited_by.setdefault(c, []).append(pid)
for pid, (h, out, t) in list(pages.items()):
    if pid in pool_ids:
        pages[pid] = (h, sorted(set(out) | set(cited_by.get(pid, []))), t)
web = SimWeb(pages, seed=cfg["seed"])
K = 200
targets = [d for d, _ in sorted(((d, indeg[d]) for d in pool_ids), key=lambda x: (-x[1], x[0]))[:K]]
budgets = [100, 250, 500, 1000, 2000, 3000, 5000]
rng = np.random.default_rng(cfg["seed"])
qids = ["q" + i for i in train.id]
res = {"priority (in-links so far, biased front queues)": [], "priority strict (almost always the top queue)": [], "BFS (single FIFO front queue)": []}
stats = {}
for trial in range(5):
    seeds = [qids[i] for i in rng.choice(len(qids), size=10, replace=False)]
    for name, (mode, bias) in {"priority (in-links so far, biased front queues)": ("priority", None),
                               "priority strict (almost always the top queue)": ("priority", [10000.0, 1.0, 1.0]),
                               "BFS (single FIFO front queue)": ("bfs", None)}.items():
        order, st = crawl(web, seeds, budget=max(budgets), mode=mode, seed=cfg["seed"] + trial, bias=bias)
        res[name].append(share_found(order, targets, budgets))
        stats.setdefault(name, []).append(st)
curves = {n: {str(b): round(float(np.mean([r[b] for r in rs])), 4) for b in budgets} for n, rs in res.items()}
seeds = [qids[i] for i in rng.choice(len(qids), size=10, replace=False)]
order, st = crawl(web, seeds, budget=3000, mode="priority", dedupe=ContentSeen(0.9), seed=cfg["seed"])
out = {"simulation_only": True, "pages": len(pages), "pool_docs": len(pool_ids), "train_query_pages": len(qids), "hosts": len({v[0] for v in pages.values()}),
       "targets": f"{K} most-cited pool documents (pool + train in-degree, used only for scoring)", "seeds_per_trial": 10, "trials": 5,
       "politeness": {"delay_virtual_units": 5.0, "fetch_time": 1.0, "back_queues": 8},
       "share_of_targets_fetched_by_budget": curves,
       "mean_run_stats": {n: {k: round(float(np.mean([s[k] for s in ss])), 1) for k in ss[0]} for n, ss in stats.items()},
       "duplicate_check_run_3000_fetches": st,
       "graph": "links run both ways: a page lists what it cites and, for pool documents, the pages that cite it (cites + cited-by)", "note": "link URLs are rendered in noisy variants and merged by normalisation; stats show how many raw URLs were merged"}
(Path(repo_path("results")) / "crawl_sim.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
