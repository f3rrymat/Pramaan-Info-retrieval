"""Phase B1 (D13, D17): first stage, zone-pair features, learned W, statute bridge; DEV rows only.

Usage: python scripts/run_b1.py            (train sample + dev; the test split is never loaded)
Saves results/zone_matrix.json, results/statute_bridge.json, results/b1_dev_rows.{json,csv}.
Features are cached in data/cache/ (git-ignored).
"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.data.loader import IlPcsrCorpus  # noqa: E402
from irlegal.evaluation.metrics import average_precision, evaluate_ranking  # noqa: E402
from irlegal.evaluation.statute_eval import gold_statute_ids, prediction_recall  # noqa: E402
from irlegal.index.inverted import InvertedIndex  # noqa: E402
from irlegal.preprocess.normalizer import Analyzer  # noqa: E402
from irlegal.query.statutes import StatuteBridge  # noqa: E402
from irlegal.ranking import zonepair as zp  # noqa: E402
from irlegal.ranking.baselines import tie_key  # noqa: E402
from irlegal.ranking.bm25 import BM25Ranker  # noqa: E402
from irlegal.ranking.vsm import TfidfRanker  # noqa: E402

cfg = load_config()
SEED = cfg["seed"]
NMAX, TRAIN_N = 1000, 1500
N_GRID, M_GRID = (300, 500, 1000), (3, 5, 10)
BETA_GRID = (0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
RES = Path(repo_path(cfg["paths"]["results_dir"]))
CACHE = Path(repo_path("data", "cache"))
CACHE.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


index = InvertedIndex.load(repo_path(cfg["paths"]["index_dir"]))
an = Analyzer()
corpus = IlPcsrCorpus()
ids = index.doc_ids()
n_docs = len(ids)
tie = tie_key(n_docs, SEED)

# ---------------------------------------------------------------- queries
train_all = [q for q in corpus.queries("train") if q.text and q.relevant - {q.case_id}]
rng = np.random.default_rng(SEED)
train = [train_all[i] for i in sorted(rng.choice(len(train_all), size=min(TRAIN_N, len(train_all)), replace=False))]
dev_all = corpus.queries("val")
dev = [q for q in dev_all if q.relevant - {q.case_id}]          # 15 empty-text queries stay in (rank by tie-break)
log("train sample", len(train), "dev", len(dev))


def rel_info(queries, cand):
    rel = np.zeros(cand.shape, dtype=bool)
    nrel = np.zeros(len(queries), dtype=np.int64)
    for i, q in enumerate(queries):
        r = {index.index_of(d) for d in q.relevant - {q.case_id}} - {None}
        nrel[i] = len(r)
        rel[i] = np.isin(cand[i], list(r))
    return rel, nrel


def load_features(name, queries):
    f = CACHE / f"b1_{name}_{len(queries)}_{SEED}_{NMAX}.npz"
    if f.exists():
        z = np.load(f)
        return z["cand"], z["X"], z["full"]
    zm = zp.ZoneMatrices(index, an)
    own = [index.index_of(q.case_id) for q in queries]
    t = time.time()
    cand, X, full = zp.first_stage_and_features(zm, queries, NMAX, tie, own)
    np.savez(f, cand=cand, X=X, full=full)
    log(f"features {name} computed in {time.time() - t:.0f}s, X {X.nbytes / 2**20:.0f} MB")
    return cand, X, full


cand_tr, X_tr, _ = load_features("train", train)
cand_dv, X_dv, full_dv = load_features("dev", dev)
rel_tr, nrel_tr = rel_info(train, cand_tr)
rel_dv, nrel_dv = rel_info(dev, cand_dv)

# ---------------------------------------------------------------- first-stage recall@N on dev
recall_N = {}
for N in (100, 200, 300, 500, 1000):
    recall_N[N] = round(float(np.mean(rel_dv[:, :N].sum(1) / np.maximum(nrel_dv, 1))), 4)
log("first-stage (tf-idf lnc.ltc, Facts+Issues, whole text) dev recall@N", recall_N)

# ---------------------------------------------------------------- learn W for each N, choose N and sweep on dev
learned = {}
for N in N_GRID:
    t = time.time()
    ws, hist = zp.learn_weights(X_tr[:, :N], rel_tr[:, :N], nrel_tr, dev=(X_dv[:, :N], rel_dv[:, :N], nrel_dv))
    dev_maps = [h["dev_MAP"] for h in hist]
    best_sweep = int(np.argmax(dev_maps))
    learned[N] = {"w": ws[best_sweep], "w_last": ws[-1], "dev_MAP_last": dev_maps[-1], "sweep": best_sweep, "history": hist, "dev_MAP": dev_maps[best_sweep]}
    log(f"N={N}: sweeps {len(hist) - 1}, chosen sweep {best_sweep}, dev MAP {dev_maps[best_sweep]:.4f} ({time.time() - t:.0f}s)")
N_BEST = max(learned, key=lambda n: learned[n]["dev_MAP"])
W = learned[N_BEST]["w"]
log("chosen N", N_BEST)

Wd = {qv: {pz: round(float(W[zp.FEATURES.index((qv, pz))]), 5) for pz in zp.POOL_ZONES} for qv in zp.QUERY_VIEWS}
RES.mkdir(exist_ok=True)
(RES / "zone_matrix.json").write_text(json.dumps({
    "rows_query_view": list(zp.QUERY_VIEWS), "cols_pool_zone": list(zp.POOL_ZONES), "W": Wd,
    "first_stage": "tf-idf lnc.ltc, Facts+Issues query vs whole text", "N_candidates": N_BEST,
    "train_queries": len(train), "learner": "coordinate ascent on MAP over first-stage candidates, weights >= 0, sum 1",
    "chosen_sweep_by_dev": learned[N_BEST]["sweep"],
    "W_last_sweep_not_selected": {qv: {pz: round(float(learned[N_BEST]["w_last"][zp.FEATURES.index((qv, pz))]), 5) for pz in zp.POOL_ZONES} for qv in zp.QUERY_VIEWS},
    "note": "dev MAP was highest at sweep 0 (the tf-idf baseline), so W above is the one-hot baseline; W_last_sweep_not_selected is the fully trained matrix (train MAP up, dev MAP down).", "history_per_N": {str(n): v["history"] for n, v in learned.items()},
    "dev_first_stage_recall_at_N": recall_N}, indent=1))

# ---------------------------------------------------------------- statute bridge
ann = corpus.pool_statute_ids()
pool_docs = [(c.doc_id, ann[c.doc_id], c.text, " ".join(c.zones.get("facts", []) + c.zones.get("issues", [])))
             for c in corpus.cases()]
assert [p[0] for p in pool_docs] == ids
t = time.time()
bridge = StatuteBridge(corpus.statutes(), pool_docs, an, enrich=True)
log(f"bridge built {time.time() - t:.0f}s", bridge.coverage)
gold = gold_statute_ids("val")                       # evaluation labels only
pred_recall = {"provision_text_only": prediction_recall(StatuteBridge(corpus.statutes(), pool_docs, an, enrich=False), dev_all, gold, (3, 5, 10)),
               "text_plus_pool_doc_profiles": prediction_recall(bridge, dev_all, gold, (3, 5, 10))}
log("statute prediction recall (dev)", pred_recall)

ch_tr = {m: bridge.channel_scores([q.text for q in train], m) for m in M_GRID}
ch_dv = {m: bridge.channel_scores([q.text for q in dev], m) for m in M_GRID}


def gather(a, cand):
    return np.take_along_axis(a, cand.astype(np.int64), axis=1)


def combine(text, ch, beta):
    mx = text.max(axis=1, keepdims=True)
    return text / np.where(mx > 0, mx, 1.0) + beta * ch


def pick_beta(text, ch, rel, nrel):
    scores = {b: float(zp.map_from_scores(combine(text, ch, b), rel, nrel).mean()) for b in BETA_GRID}
    return max(scores, key=scores.get), scores


N = N_BEST
base_tr, base_dv = X_tr[:, :N, zp.BASE_FEATURE], X_dv[:, :N, zp.BASE_FEATURE]
w_tr, w_dv = X_tr[:, :N] @ W.astype(np.float32), X_dv[:, :N] @ W.astype(np.float32)
chosen = {}
for m in M_GRID:
    ctr, cdv = gather(ch_tr[m], cand_tr[:, :N]), gather(ch_dv[m], cand_dv[:, :N])
    b_t, _ = pick_beta(base_tr, ctr, rel_tr[:, :N], nrel_tr)       # beta from TRAIN
    b_w, _ = pick_beta(w_tr, ctr, rel_tr[:, :N], nrel_tr)
    chosen[m] = {"beta_tfidf": b_t, "beta_W": b_w,
                 "dev_MAP_tfidf_channel": float(zp.map_from_scores(combine(base_dv, cdv, b_t), rel_dv[:, :N], nrel_dv).mean()),
                 "dev_MAP_W_channel": float(zp.map_from_scores(combine(w_dv, cdv, b_w), rel_dv[:, :N], nrel_dv).mean())}
    log("m", m, chosen[m])
M_BEST = max(chosen, key=lambda m: chosen[m]["dev_MAP_tfidf_channel"])     # m chosen once, on the tf-idf ablation
log("chosen m", M_BEST)
ch_dv_c = gather(ch_dv[M_BEST], cand_dv[:, :N])

# ---------------------------------------------------------------- dev rows (full-ranking metrics)
def rerank(scores):
    """Candidate order by `scores`, then the rest in first-stage order; own case removed."""
    out = []
    for i, q in enumerate(dev):
        top = np.argsort(-scores[i], kind="stable")
        order = list(cand_dv[i, :N][top]) + [d for d in full_dv[i][N:] if d != index.index_of(q.case_id)]
        out.append([ids[d] for d in order])
    return out


def metrics_rows(rankings):
    per = [evaluate_ranking(r, q.relevant - {q.case_id}) for r, q in zip(rankings, dev)]
    return per


rows, per_q = {}, {}
own_dv = [index.index_of(q.case_id) for q in dev]
fs = [[ids[d] for d in full_dv[i] if d != own_dv[i]] for i in range(len(dev))]
per_q["tfidf_lnc_ltc FI query, whole text (first stage)"] = metrics_rows(fs)
bm = json.load(open(RES / "bm25_tuning.json"))
for label, par in (("bm25 default (k1=1.2,b=0.75,raw) FI query, whole text", bm["default"]["all"]),
                   (f"bm25 tuned (k1={bm['tuned']['all']['k1']},b={bm['tuned']['all']['b']},{bm['tuned']['all']['qtf']}) FI query, whole text", bm["tuned"]["all"])):
    r = BM25Ranker(index, an, "all", k1=par["k1"], b=par["b"], qtf_mode=par["qtf"])
    per_q[label] = metrics_rows([[ids[d] for d in r.order(q)[0]] for q in dev])
per_q[f"tfidf + statute channel (m={M_BEST}, beta={chosen[M_BEST]['beta_tfidf']})"] = metrics_rows(rerank(combine(base_dv, ch_dv_c, chosen[M_BEST]["beta_tfidf"])))
per_q[f"W-learned (N={N})"] = metrics_rows(rerank(w_dv))
wl_dv = X_dv[:, :N] @ learned[N]["w_last"].astype(np.float32)
per_q[f"W-learned, last sweep (not selected by dev) (N={N})"] = metrics_rows(rerank(wl_dv))
per_q[f"W-learned + statute channel (m={M_BEST}, beta={chosen[M_BEST]['beta_W']})"] = metrics_rows(rerank(combine(w_dv, ch_dv_c, chosen[M_BEST]["beta_W"])))
for name, per in per_q.items():
    rows[name] = {k: round(float(np.mean([p[k] for p in per])), 4) for k in per[0]}
    rows[name]["n_queries"] = len(per)

# paired bootstrap on AP vs the tf-idf first stage (1000 resamples, seed 13)
def boot(a, b):
    d = np.array(a) - np.array(b)
    r = np.random.default_rng(SEED)
    means = [d[r.integers(0, len(d), len(d))].mean() for _ in range(1000)]
    return {"mean_diff": round(float(d.mean()), 4), "ci95": [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]}

base_name = "tfidf_lnc_ltc FI query, whole text (first stage)"
ap = {n: [p["MAP"] for p in per] for n, per in per_q.items()}
sig = {n: boot(ap[n], ap[base_name]) for n in ap if n != base_name}

out = {"split": "dev", "query_view": "facts_issues (headline, D16)", "temporal_filter": "off (D15)",
       "N_candidates": N, "m": M_BEST, "rows": rows, "paired_bootstrap_MAP_vs_tfidf": sig,
       "first_stage_recall_at_N": recall_N, "bm25_tuning_best_on_grid_edge": "see results/bm25_tuning.json",
       "statute": {"coverage": bridge.coverage, "prediction_recall_dev": pred_recall, "m_choices": chosen}}
(RES / "b1_dev_rows.json").write_text(json.dumps(out, indent=1))
(RES / "statute_bridge.json").write_text(json.dumps(out["statute"], indent=1))
with open(RES / "b1_dev_rows.csv", "w", newline="") as f:
    cols = ["ranker"] + list(next(iter(rows.values())).keys())
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for n, r in rows.items():
        w.writerow({"ranker": n, **r})
log("done")
print(json.dumps({"rows": rows, "bootstrap": sig}, indent=1))
