"""Freeze Config A (D23) from TRAIN data only: random search (200 trials) over weights of
text, neighbour, authority with candidates = tf-idf top 1000, 5-fold CV over train queries.
Does not read dev or test. Saves results/config_a_frozen.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.ranking import netscore as ns  # noqa: E402
from irlegal.ranking.pipeline import CONFIG_A_FEATURES, Context, config_a_path  # noqa: E402

ctx = Context()
qs = [q for q in ctx.train_queries if q.text and ctx.relevant(q)]
F = ctx.features(qs, loo=True)
own = ctx.own_idx(qs)
mask = ctx.first_stage_mask(F["text"], own)
qi, di, nrel = [], [], np.zeros(len(qs), dtype=np.int64)
for i, q in enumerate(qs):
    r = sorted({ctx.index.index_of(d) for d in ctx.relevant(q)} - {None})
    nrel[i] = len(r); qi += [i] * len(r); di += r
qi, di = np.array(qi), np.array(di)
folds = np.random.default_rng(ctx.seed).permutation(len(qs)) % 5
nf = {f: ns.minmax_masked(F[f], mask) for f in CONFIG_A_FEATURES}
res = ns.random_search(nf, mask, qi, di, nrel, list(CONFIG_A_FEATURES), folds, trials=200, seed=ctx.seed)
nested = ns.nested_cv_map(res, folds)
best = res[0]
out = {"features": list(CONFIG_A_FEATURES), "weights": {k: round(v, 5) for k, v in best["w"].items()},
       "first_stage": "tf-idf lnc.ltc Facts+Issues top 1000", "train_queries": len(qs),
       "CV_MAP": round(best["MAP"], 5), "fold_MAP": [round(x, 5) for x in best["fold_map"]], "nested_CV_MAP": round(nested, 5),
       "neighbour": {"k": ctx.k_nb, "p": ctx.p_nb}, "frozen": "weights chosen on train only; dev/test not read"}
config_a_path().write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
