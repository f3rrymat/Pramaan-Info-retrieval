"""Phase B2 (D19-D22): authority, recency, court, neighbours, union first stage, net score, ablation ladder.

DEV only; the test split is never loaded. Weights/hyperparameters are chosen by 5-fold CV on train.
Saves results/b2_*.json|csv. Usage: python scripts/run_b2.py
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
from irlegal.evaluation.metrics import evaluate_ranking  # noqa: E402
from irlegal.index.inverted import InvertedIndex  # noqa: E402
from irlegal.preprocess.normalizer import Analyzer  # noqa: E402
from irlegal.query.statutes import StatuteBridge  # noqa: E402
from irlegal.ranking import authority as au  # noqa: E402
from irlegal.ranking import netscore as ns  # noqa: E402
from irlegal.ranking import zonepair as zp  # noqa: E402
from irlegal.ranking.baselines import tie_key  # noqa: E402
from irlegal.ranking.bm25 import BM25Ranker  # noqa: E402
from irlegal.ranking.explain import explain_result, shared_statute_tokens  # noqa: E402
from irlegal.ranking.neighbours import NeighbourIndex  # noqa: E402

cfg = load_config()
SEED = cfg["seed"]
RES = Path(repo_path(cfg["paths"]["results_dir"]))
M_STAT, UNION_SIZES, FROZEN_SIZE = 3, (100, 200, 300), 300
K_GRID, P_GRID = (10, 20, 50, 100), (1.0, 2.0, 4.0)
TAUS = (5.0, 10.0, 20.0)
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


index = InvertedIndex.load(repo_path(cfg["paths"]["index_dir"]))
an = Analyzer()
corpus = IlPcsrCorpus()
cases = corpus.cases()
ids = index.doc_ids()
assert [c.doc_id for c in cases] == ids
n_docs = len(ids)
tie = tie_key(n_docs, SEED)
doc_dates = [c.date for c in cases]
court_vec = au.court_vector([c.court for c in cases])

train_q_all = corpus.queries("train")
train_q = [q for q in train_q_all if q.text and q.relevant - {q.case_id}]
dev_q = [q for q in corpus.queries("val") if q.relevant - {q.case_id}]
dev_full = {q.qid: q for q in corpus.queries("val", view="full")}
log("train scored", len(train_q), "train in graph/neighbours", len(train_q_all), "dev", len(dev_q))


def own_idx(qs):
    return np.array([index.index_of(q.case_id) if index.index_of(q.case_id) is not None else -1 for q in qs])


def pairs(qs):
    qi, di, nrel = [], [], np.zeros(len(qs), dtype=np.int64)
    for i, q in enumerate(qs):
        r = sorted({index.index_of(d) for d in q.relevant - {q.case_id}} - {None})
        nrel[i] = len(r)
        qi += [i] * len(r); di += r
    return np.array(qi), np.array(di), nrel


# ---------------------------------------------------------------- feature matrices
zm = zp.ZoneMatrices(index, an)
from collections import Counter  # noqa: E402


def text_matrix(texts, chunk=250):
    out = np.zeros((len(texts), n_docs), dtype=np.float32)
    for s in range(0, len(texts), chunk):
        Q = zm._query_matrix("all", [Counter(an.analyze(t)) for t in texts[s:s + chunk]])
        out[s:s + chunk] = (Q @ zm.T["all"]).toarray()
    return out


bm = json.load(open(RES / "bm25_tuning.json"))["tuned"]["all"]
bm25 = BM25Ranker(index, an, "all", k1=bm["k1"], b=bm["b"], qtf_mode=bm["qtf"])
ann = corpus.pool_statute_ids()
pool_docs = [(c.doc_id, ann[c.doc_id], c.text, " ".join(c.zones.get("facts", []) + c.zones.get("issues", []))) for c in cases]
bridge = StatuteBridge(corpus.statutes(), pool_docs, an, enrich=True)
graph = au.AuthorityGraph(ids, {c.doc_id: c.cites_out for c in cases}, corpus.relevant_ids("train"))
nidx = NeighbourIndex(train_q_all, ids, an, max_k=100)          # TRAIN queries only (constructor enforces)
log("neighbour index", len(nidx.qids), "train queries; vocab", len(nidx.vocab))


def build(qs, full_text=None):
    texts = [q.text for q in qs]
    f = {"text": text_matrix(texts)}
    f["bm25"] = np.stack([bm25.score_all(q) for q in qs]).astype(np.float32)
    f["statute"] = bridge.channel_scores(texts, M_STAT).astype(np.float32)
    f["authority"] = np.stack([graph.authority_for(q.qid, q.case_id) for q in qs]).astype(np.float32)
    f["court"] = np.broadcast_to(court_vec, (len(qs), n_docs)).copy()
    f["gap"] = np.stack([au.year_gap(q.date, doc_dates) for q in qs])
    nb_self = [q.qid if q.split == "train" else None for q in qs]
    f["nb_idx"], f["nb_sim"] = nidx.top_neighbours(texts, nb_self)
    return f


t = time.time()
TR, DV = build(train_q), build(dev_q)
log(f"features built ({time.time() - t:.0f}s)")
own_tr, own_dv = own_idx(train_q), own_idx(dev_q)
qi_tr, di_tr, nrel_tr = pairs(train_q)
qi_dv, di_dv, nrel_dv = pairs(dev_q)
folds = np.random.default_rng(SEED).permutation(len(train_q)) % 5
ALL_TR = np.ones((len(train_q), n_docs), bool)
ALL_TR[np.arange(len(train_q))[own_tr >= 0], own_tr[own_tr >= 0]] = False


def alone_ap(S, mask):
    Sm = np.where(mask, S, -np.inf)
    return ns.ap_from_ranks(ns.pair_ranks(Sm, qi_tr, di_tr), qi_tr, len(train_q), nrel_tr)


# ---------------------------------------------------------------- N7 neighbours: k, p by 5-fold CV on train
grid = []
for k in K_GRID:
    for p in P_GRID:
        ap = alone_ap(nidx.votes(TR["nb_idx"], TR["nb_sim"], k, p), ALL_TR)
        grid.append({"k": k, "p": p, "CV_MAP": round(float(np.mean([ap[folds == f].mean() for f in range(5)])), 5),
                     "fold_MAP": [round(float(ap[folds == f].mean()), 5) for f in range(5)]})
best_nb = max(grid, key=lambda g: g["CV_MAP"])
log("neighbour grid best", best_nb)
TR["neighbour"] = nidx.votes(TR["nb_idx"], TR["nb_sim"], best_nb["k"], best_nb["p"])
DV["neighbour"] = nidx.votes(DV["nb_idx"], DV["nb_sim"], best_nb["k"], best_nb["p"])

# ---------------------------------------------------------------- candidate sets
def top_mask(S, top, own):
    return ns.union_candidates([(S, top)], tie, own)


def union_mask(F, size, own):
    pos = lambda S: np.where(S > 0, S, -np.inf)
    return ns.union_candidates([(F["text"], size), (F["bm25"], size), (pos(F["statute"]), size // 2),
                                (pos(F["authority"]), size // 2), (pos(F["neighbour"]), size)], tie, own)


def recall_of(mask, qi, di, nrel):
    return float(np.mean(np.bincount(qi, weights=mask[qi, di], minlength=len(nrel)) / np.maximum(nrel, 1)))


M1000_TR, M1000_DV = top_mask(TR["text"], 1000, own_tr), top_mask(DV["text"], 1000, own_dv)
union_info = {}
for size in UNION_SIZES:
    mt, md = union_mask(TR, size, own_tr), union_mask(DV, size, own_dv)
    union_info[size] = {"dev_recall": round(recall_of(md, qi_dv, di_dv, nrel_dv), 4), "dev_mean_union_size": round(float(md.sum(1).mean()), 1),
                        "train_recall": round(recall_of(mt, qi_tr, di_tr, nrel_tr), 4), "train_mean_union_size": round(float(mt.sum(1).mean()), 1)}
union_info["tfidf_top1000_only"] = {"dev_recall": round(recall_of(M1000_DV, qi_dv, di_dv, nrel_dv), 4), "dev_mean_size": 1000}
for N in (300, 500):
    union_info[f"tfidf_top{N}_only"] = {"dev_recall": round(recall_of(top_mask(DV["text"], N, own_dv), qi_dv, di_dv, nrel_dv), 4)}
log("union recall", json.dumps(union_info))
MU_TR, MU_DV = union_mask(TR, FROZEN_SIZE, own_tr), union_mask(DV, FROZEN_SIZE, own_dv)    # size frozen a priori


# ---------------------------------------------------------------- net score search on train (5-fold CV)
def norm_feats(F, mask, which):
    return {f: ns.minmax_masked(F[f], mask) for f in which if f != "recency"}


def search(features, mask, trials, label):
    t = time.time()
    nf = norm_feats(TR, mask, features)
    rec = (lambda tau: au.recency(TR["gap"], tau)) if "recency" in features else None
    res = ns.random_search(nf, mask, qi_tr, di_tr, nrel_tr, features, folds, trials=trials, taus=TAUS,
                           build_recency=rec, seed=SEED)
    nested = ns.nested_cv_map(res, folds)
    log(f"search {label}: best CV MAP {res[0]['MAP']:.4f} nested {nested:.4f} ({time.time() - t:.0f}s) w={ {k: round(v, 3) for k, v in res[0]['w'].items()} } tau={res[0]['tau']}")
    return res, nested


# ---------------------------------------------------------------- dev scoring
def rank_ids(net, mask, tfidf, removed=None):
    out = []
    for i in range(net.shape[0]):
        key = np.where(mask[i], net[i], -np.inf)
        rm = removed[i].astype(np.int8) if removed is not None else np.zeros(n_docs, np.int8)
        o = np.lexsort((tie, -tfidf[i], -key, rm))
        o = o[o != own_dv[i]] if own_dv[i] >= 0 else o
        out.append([ids[d] for d in o])
    return out


def dev_metrics(rankings):
    return [evaluate_ranking(r, q.relevant - {q.case_id}) for r, q in zip(rankings, dev_q)]


def net_dev(F, mask, w, tau=None):
    feats = list(w)
    nf = {f: ns.minmax_masked(F[f], mask) for f in feats if f != "recency"}
    if "recency" in feats:
        nf["recency"] = ns.minmax_masked(au.recency(F["gap"], tau or 10.0), mask)
    return ns.net_scores(nf, w, mask)


def temporal_removed(qs):
    qd = [q.date for q in qs]
    rm = np.zeros((len(qs), n_docs), bool)
    for i, q in enumerate(qs):
        if q.date:
            for j, d in enumerate(doc_dates):
                if d and d >= q.date:
                    rm[i, j] = True
    return rm


per, desc = {}, {}


def add(name, rankings, note=""):
    per[name] = dev_metrics(rankings); desc[name] = note


zeros_dev = np.zeros((len(dev_q), n_docs), np.float32)
ALL_DV = np.ones((len(dev_q), n_docs), bool)
BASE = "1 tf-idf lnc.ltc, Facts+Issues (first stage)"
add(BASE, rank_ids(DV["text"], ALL_DV, zeros_dev))
add("ref: popularity-only, authority (pool + train edges, LOO)", rank_ids(DV["authority"], ALL_DV, zeros_dev))
add("ref: neighbour votes alone", rank_ids(DV["neighbour"], ALL_DV, zeros_dev), f"k={best_nb['k']} p={best_nb['p']}")
trainpop = np.broadcast_to(np.array([corpus.train_indegree().get(d, 0) for d in ids], np.float32), (len(dev_q), n_docs))
add("ref: popularity-only, train in-degree (Phase A)", rank_ids(trainpop, ALL_DV, zeros_dev))
add("ref: BM25 tuned alone", rank_ids(DV["bm25"], ALL_DV, zeros_dev), f"k1={bm['k1']} b={bm['b']}")

searches, configs = {}, {}
# feature alone on top of tf-idf (candidates = tf-idf top 1000)
for f in ("authority", "recency", "court"):
    res, nest = search(["text", f], M1000_TR, 60, f"text+{f}")
    w, tau = res[0]["w"], res[0]["tau"]
    add(f"2 tf-idf + {f} alone", rank_ids(net_dev(DV, M1000_DV, w, tau), M1000_DV, DV["text"]), json.dumps({"w": w, "tau": tau}))
    configs[f"text+{f}"] = {"w": w, "tau": tau, "CV_MAP": res[0]["MAP"], "nested_CV_MAP": nest}
# ladder
ladder = [("3 + statute channel", ["text", "statute"]),
          ("4 + authority", ["text", "statute", "authority"]),
          ("5 + neighbours", ["text", "statute", "authority", "neighbour"]),
          ("6 + recency and court", ["text", "statute", "authority", "neighbour", "recency", "court"])]
for name, feats in ladder:
    res, nest = search(feats, M1000_TR, 200, name)
    w, tau = res[0]["w"], res[0]["tau"]
    add(name + " (candidates: tf-idf top 1000)", rank_ids(net_dev(DV, M1000_DV, w, tau), M1000_DV, DV["text"]), json.dumps({"w": w, "tau": tau}))
    configs[name] = {"w": w, "tau": tau, "CV_MAP": res[0]["MAP"], "nested_CV_MAP": nest}

# union stage: 3 frozen configs chosen on train CV only
ALLF = ["text", "statute", "authority", "neighbour", "recency", "court"]
resU, nestU = search(ALLF, MU_TR, 200, "union, all features")
resN, nestN = search([f for f in ALLF if f != "neighbour"], MU_TR, 200, "union, no neighbour")
cfgA = resU[0]
cfgB = next(t for t in resU if t["w"]["text"] >= 0.5)
cfgC = resN[0]
frozen = {"A_best_cv": cfgA, "B_text_weight_ge_0.5": cfgB, "C_no_neighbour": cfgC}
frozen_json = {k: {"w": {f: round(x, 5) for f, x in v["w"].items()}, "tau": v["tau"], "CV_MAP": round(v["MAP"], 5),
                   "fold_MAP": [round(x, 5) for x in v["fold_map"]]} for k, v in frozen.items()}
frozen_json["nested_CV_MAP_all_features"] = round(nestU, 5)
frozen_json["nested_CV_MAP_no_neighbour"] = round(nestN, 5)
for k, v in frozen.items():
    add(f"7 + union first stage, frozen config {k}", rank_ids(net_dev(DV, MU_DV, v["w"], v["tau"]), MU_DV, DV["text"]),
        json.dumps({"w": {f: round(x, 4) for f, x in v["w"].items()}, "tau": v["tau"]}))
HEAD = "7 + union first stage, frozen config A_best_cv"

# temporal filter ablation (D15), applied after candidate generation
rm_dv = temporal_removed(dev_q)
both_known = np.array([[bool(q.date and d) for d in doc_dates] for q in dev_q])
rel_removed = float(np.mean([rm_dv[i, j] for i, j in zip(qi_dv, di_dv) if both_known[i, j]]))
add("tf-idf + temporal filter", rank_ids(DV["text"], ALL_DV, zeros_dev, rm_dv))
add(HEAD + " + temporal filter", rank_ids(net_dev(DV, MU_DV, cfgA["w"], cfgA["tau"]), MU_DV, DV["text"], rm_dv))
# full-judgment reference rows (not comparable, D16)
full_texts = [dev_full[q.qid].text for q in dev_q]
DVF = dict(DV); DVF["text"] = text_matrix(full_texts)
add("REFERENCE (full-judgment query): tf-idf", rank_ids(DVF["text"], ALL_DV, zeros_dev))
add("REFERENCE (full-judgment text feature): " + HEAD, rank_ids(net_dev(DVF, MU_DV, cfgA["w"], cfgA["tau"]), MU_DV, DVF["text"]))

# ---------------------------------------------------------------- bootstrap vs tf-idf, tables
rows = {n: {k: round(float(np.mean([m[k] for m in ms])), 4) for k in ("MAP", "MRR", "nDCG@10", "nDCG@20", "R@5", "R@10", "R@20", "P@10")} for n, ms in per.items()}
rng = np.random.default_rng(SEED)
BI = rng.integers(0, len(dev_q), size=(1000, len(dev_q)))
ci = {}
for n, ms in per.items():
    ci[n] = {}
    for k in ("MAP", "MRR", "nDCG@10", "R@10", "R@20"):
        d = np.array([m[k] for m in ms]) - np.array([m[k] for m in per[BASE]])
        means = d[BI].mean(axis=1)
        ci[n][k] = [round(float(d.mean()), 4), round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]
    rows[n]["n_queries"] = len(ms)
out = {"split": "dev", "query": "facts_issues unless marked REFERENCE", "temporal_filter": "off except rows marked", "rows": rows,
       "diff_vs_tfidf_[mean,lo95,hi95]": ci, "row_notes": desc, "neighbour_grid_5fold_cv_on_train": grid, "neighbour_best": best_nb,
       "union_recall": union_info, "frozen_union_size": FROZEN_SIZE,
       "temporal": {"share_of_dev_query_doc_pairs_with_both_dates": round(float(both_known.mean()), 4),
                    "share_of_relevant_pairs_with_both_dates_post_dating_query_or_same_day": round(rel_removed, 4)},
       "search_configs": configs}
(RES / "b2_ablation_dev.json").write_text(json.dumps(out, indent=1))
(RES / "b2_netscore_configs.json").write_text(json.dumps(frozen_json, indent=1))
with open(RES / "b2_ablation_dev.csv", "w", newline="") as f:
    cols = ["row"] + list(next(iter(rows.values()))) + [f"{k} diff [lo,hi]" for k in ("MAP", "MRR", "nDCG@10", "R@10", "R@20")]
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for n, r in rows.items():
        w.writerow({"row": n, **r, **{f"{k} diff [lo,hi]": f"{ci[n][k][0]:+.4f} [{ci[n][k][1]:+.4f},{ci[n][k][2]:+.4f}]" for k in ci[n]}})

# ---------------------------------------------------------------- explanation example (ids and numbers only)
i = 0
q = dev_q[i]
order = np.lexsort((tie, -DV["text"][i], -np.where(MU_DV[i], net_dev(DV, MU_DV, cfgA["w"], cfgA["tau"])[i], -np.inf)))[:3]
pred_rows, _ = bridge.predict(q.text, M_STAT)
nf = {f: ns.minmax_masked(DV[f], MU_DV)[i] for f in cfgA["w"] if f != "recency"}
nf["recency"] = ns.minmax_masked(au.recency(DV["gap"], cfgA["tau"] or 10.0), MU_DV)[i]
ex = [explain_result(ids[d], {f: float(nf[f][d]) for f in cfgA["w"]}, cfgA["w"],
                     neighbours=nidx.explain(DV["nb_idx"][i], DV["nb_sim"][i], d, best_nb["k"]),
                     shared_statutes=shared_statute_tokens(bridge, pred_rows, d)) for d in order]
(RES / "b2_explain_example.json").write_text(json.dumps({"query_id": q.qid, "results": ex}, indent=1))
log("done")
for n, r in rows.items():
    print(f"{n[:78]:78s} MAP {r['MAP']:.4f} MRR {r['MRR']:.4f} nDCG10 {r['nDCG@10']:.4f} R10 {r['R@10']:.4f} R20 {r['R@20']:.4f}  dMAP {ci[n]['MAP']}")
