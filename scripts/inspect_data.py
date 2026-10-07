"""Data checks for IL-PCSR (DECISIONS.md sections 2 and 3). Owner: WS1.

Prints AGGREGATES ONLY (never case text or titles) and saves them to
results/data_inspect.json. Usage: python scripts/inspect_data.py
"""
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.data.loader import ROLE_TO_ZONE, map_court, parse_date, zones_from_paragraphs  # noqa: E402

D = ROOT / "data" / "ilpcsr"
SPLITS = ["train_queries", "dev_queries", "test_queries"]
OUT = {}


def rec(key, val):
    OUT[key] = val
    print(f"{key}: {json.dumps(val, default=str)}")


def dist(xs):
    xs = list(xs)
    return {"mean": round(float(np.mean(xs)), 2), "median": float(np.median(xs)), "max": int(max(xs))} if xs else {}


def date_shape(s):
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", s)) if isinstance(s, str) else "<non-string>"


dfs = {n: pd.read_parquet(D / f"{n}.parquet") for n in SPLITS + ["precedent_candidates", "statute_candidates"]}
pool = dfs["precedent_candidates"]
pool_ids = set(pool.id)
rec("rows", {n: len(d) for n, d in dfs.items()})
rec("columns", {n: list(d.columns) for n, d in dfs.items()})
rec("duplicate_ids", {n: int(d.id.duplicated().sum()) for n, d in dfs.items()})

doc_sets = SPLITS + ["precedent_candidates"]
rec("len_text_ne_len_roles_rows", {n: int(sum(len(a) != len(b) for a, b in zip(dfs[n].text, dfs[n].rhetorical_roles)))
                                    for n in doc_sets})
rec("missing_title", {n: int((dfs[n].case_title.isna() | (dfs[n].case_title.fillna("").str.strip() == "")).sum()) for n in doc_sets})
rec("missing_date_raw", {n: int((dfs[n].date.isna() | (dfs[n].date.fillna("").str.strip() == "")).sum()) for n in doc_sets})
rec("date_parse_share", {n: round(float(np.mean([parse_date(x) is not None for x in dfs[n].date])), 4) for n in doc_sets})
rec("unparseable_date_shapes", {n: dict(Counter(date_shape(x) for x in dfs[n].date if parse_date(x) is None).most_common(5))
                                  for n in doc_sets})
rec("distinct_jurisdictions", {n: int(dfs[n].jurisdiction.nunique()) for n in doc_sets})
rec("missing_jurisdiction", {n: int(dfs[n].jurisdiction.isna().sum()) for n in doc_sets})
rec("top_jurisdictions_train", dfs["train_queries"].jurisdiction.value_counts().head(5).to_dict())
rec("pool_jurisdictions", pool.jurisdiction.value_counts().to_dict())
rec("court_mapping_share_pool", {k: round(v / len(pool), 4) for k, v in Counter(map_court(j) for j in pool.jurisdiction).items() if k})

# roles
unknown = Counter()
role_counts = {}
for n in doc_sets:
    c = Counter()
    for roles in dfs[n].rhetorical_roles:
        c.update(roles)
    role_counts[n] = dict(c.most_common())
    unknown.update({k: v for k, v in c.items() if k not in ROLE_TO_ZONE})
rec("role_counts", role_counts)
rec("unknown_role_labels", dict(unknown))

# size
for n in doc_sets:
    paras = [len(t) for t in dfs[n].text]
    toks = [sum(len(p.split()) for p in t) for t in dfs[n].text]
    rec(f"paragraphs_per_doc[{n}]", dist(paras))
    rec(f"whitespace_tokens_per_doc[{n}]", dist(toks))

# relevant ids
rel = {n: [set(x) for x in dfs[n].relevant_precedent_ids] for n in SPLITS}
for n in SPLITS:
    rec(f"relevant_per_query[{n}]", dist([len(s) for s in rel[n]]))
    allr = set().union(*rel[n])
    rec(f"relevant_in_pool_share[{n}]", round(len(allr & pool_ids) / len(allr), 4))
    rec(f"queries_with_zero_relevant[{n}]", int(sum(1 for s in rel[n] if not s)))
    rec(f"query_ids_in_pool_share[{n}]", round(float(np.mean([i in pool_ids for i in dfs[n].id])), 4))
    rec(f"query_cites_itself[{n}]", int(sum(1 for i, s in zip(dfs[n].id, rel[n]) if i in s)))
train_cited = set().union(*rel["train_queries"])
train_deg = Counter(i for s in rel["train_queries"] for i in s)
for n in ["dev_queries", "test_queries"]:
    allr = set().union(*rel[n])
    rec(f"distinct_relevant_cited_by_a_train_query[{n}]", round(len(allr & train_cited) / len(allr), 4))
    # per (query, relevant) pair
    pairs = [(i in train_cited) for s in rel[n] for i in s]
    rec(f"relevant_pairs_cited_by_a_train_query[{n}]", round(float(np.mean(pairs)), 4))

# statute table / gold statute ids exist (labels only; reported, not used)
stat_ids = set(dfs["statute_candidates"].id)
rec("gold_statute_ids_in_statute_table_share_train",
    round(float(np.mean([i in stat_ids for s in dfs["train_queries"].relevant_statute_ids for i in s])), 4))

# temporal sanity: relevant precedent dated strictly before the query
pdate = {i: parse_date(d) for i, d in zip(pool.id, pool.date)}
for n in SPLITS:
    both = before = eq = after = 0
    for qd, s in zip(dfs[n].date, rel[n]):
        qd = parse_date(qd)
        for i in s:
            pd_ = pdate.get(i)
            if qd and pd_:
                both += 1
                before += pd_ < qd
                eq += pd_ == qd
                after += pd_ > qd
    rec(f"temporal_pairs[{n}]", {"both_dates_known": both, "rel_before_query": before, "same_day": eq, "rel_after_query": after})

# --- leftovers in Facts / Issue paragraphs of queries
RAW = {
    "AIR": re.compile(r"\bA\.?I\.?R\.?\s*\(?\d{4}"),
    "SCC": re.compile(r"\bS\.?C\.?C\.?\b"),
    "SCR": re.compile(r"\bS\.?C\.?R\.?\b"),
    "SCALE": re.compile(r"\bSCALE\b"),
    "<CITATION>": re.compile(r"<\s*CITATION\s*>", re.I),
    "party_v_party": re.compile(r"\b[A-Z][\w.&'-]+(?:\s+\w[\w.&'-]*){0,4}\s+(?:v\.|vs\.?|versus)\s+[A-Z]"),
}
STAT = {
    "Section": re.compile(r"\bSection\b"), "Sec.": re.compile(r"\bSec\.", re.I),
    "Art.": re.compile(r"\bArt(?:icle|\.)\s*\d"), "u/s": re.compile(r"\bu/s\b", re.I),
}
from irlegal.data.query_builder import scrub_citations  # noqa: E402

for n in SPLITS:
    df = dfs[n]
    fi_texts, empty = [], 0
    for paras, roles in zip(df.text, df.rhetorical_roles):
        z = zones_from_paragraphs(list(paras), roles)
        t = " ".join(z.get("facts", []) + z.get("issues", []))
        empty += not t.strip()
        fi_texts.append(t)
    rec(f"fi_empty_queries[{n}]", empty)
    rec(f"fi_words_per_query[{n}]", dist([len(t.split()) for t in fi_texts]))
    rec(f"fi_raw_citation_patterns_queries_with_ge1[{n}]", {k: int(sum(1 for t in fi_texts if p.search(t))) for k, p in RAW.items()})
    rec(f"fi_statute_patterns_queries_with_ge1[{n}]", {k: int(sum(1 for t in fi_texts if p.search(t))) for k, p in STAT.items()})
    after = Counter()
    for t in fi_texts:
        _, c = scrub_citations(t)
        after.update(c)
    rec(f"fi_scrubber_removals[{n}]", dict(after))
    if n == "dev_queries":
        left = {k: int(sum(1 for t in fi_texts if p.search(scrub_citations(t)[0]))) for k, p in RAW.items()}
        rec("fi_dev_patterns_remaining_after_scrub_queries_with_ge1", left)

# --- masking placeholders in the text ([ENTITY], [SECTION], [ACT], [PRECEDENT], ...)
PH = re.compile(r"\[([A-Z][A-Z_ ]{2,20})\]")
for n in SPLITS + ["precedent_candidates"]:
    df = dfs[n]
    tot, fi_q = Counter(), Counter()
    for paras, roles in zip(df.text, df.rhetorical_roles):
        z = zones_from_paragraphs(list(paras), roles)
        for name, ps in (("all", paras), ("FI", z.get("facts", []) + z.get("issues", []))):
            found = Counter(PH.findall(" ".join(ps)))
            (tot if name == "all" else fi_q).update(found.keys())      # docs containing placeholder
    rec(f"placeholder_docs_with_ge1[{n}]", {"all_text": dict(tot.most_common(8)), "facts_issues": dict(fi_q.most_common(8))})

# --- do Facts / Issue (and, for contrast, full text) name cited cases? (titles never printed)
def norm(s):
    s = re.sub(r"\b(?:vs|versus|v)\b\.?", " v ", s.lower())
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def parties(title):
    parts = norm(title).split(" v ")
    return [p for p in parts if len(p) >= 5][:2] if len(parts) == 2 else []


ptitle = dict(zip(pool.id, pool.case_title))
rec("pool_titles_with_v_pair_share", round(float(np.mean([bool(re.search(r"\bv(?:s)?\b\.?", t or "", re.I)) for t in pool.case_title])), 4))
df = dfs["dev_queries"]
c = Counter()
for paras, roles, rids in zip(df.text, df.rhetorical_roles, df.relevant_precedent_ids):
    z = zones_from_paragraphs(list(paras), roles)
    fi_raw = " ".join(z.get("facts", []) + z.get("issues", []))
    views = {"FI": norm(fi_raw), "FI_scrubbed": norm(scrub_citations(fi_raw)[0]), "full": norm(" ".join(paras))}
    anyq = Counter()
    for i in rids:
        t = ptitle.get(i)
        if not isinstance(t, str) or len(norm(t)) < 8:
            c["pairs_without_usable_title"] += 1
            continue
        pt = parties(t)
        full_title = norm(t)
        for v, txt in views.items():
            ex = full_title in txt
            loose = len(pt) == 2 and all(p in txt for p in pt)
            c[f"pairs_exact[{v}]"] += ex
            c[f"pairs_both_parties[{v}]"] += loose
            anyq[f"queries_exact[{v}]"] |= ex
            anyq[f"queries_both_parties[{v}]"] |= loose
        c["pairs"] += 1
    c.update({k: int(v) for k, v in anyq.items()})
    c["queries"] += 1
rec("cited_case_names_in_dev_queries", dict(c))

# --- section 3: pool artifact
cited_any = {}
for n in SPLITS:
    cited_any[n] = set().union(*rel[n])
pool_cites = set().union(*[set(x) for x in pool.relevant_precedent_ids])
by_query = set().union(*cited_any.values())
rec("pool_cited_by_some_query_any_split_share", round(len(pool_ids & by_query) / len(pool_ids), 4))
rec("pool_cited_by_some_query_or_pool_doc_share", round(len(pool_ids & (by_query | pool_cites)) / len(pool_ids), 4))
rec("pool_cited_by_train_query_share", round(len(pool_ids & cited_any["train_queries"]) / len(pool_ids), 4))
zero = {i for i in pool_ids if train_deg[i] == 0}
dev_test = cited_any["dev_queries"] | cited_any["test_queries"]
pos = pool_ids - zero
rec("pool_zero_train_indegree", {"n": len(zero), "share_of_pool": round(len(zero) / len(pool_ids), 4),
    "share_relevant_to_some_dev_or_test_query": round(len(zero & dev_test) / max(1, len(zero)), 4),
    "share_of_positive_indegree_ids_relevant_to_dev_or_test": round(len(pos & dev_test) / max(1, len(pos)), 4),
    "zero_indegree_ids_cited_by_no_query_at_all": len(zero - by_query)})
# precision of "zero indegree" as a predictor of relevance, per dev/test relevant pair
for n in ["dev_queries", "test_queries"]:
    pairs = [i for s in rel[n] for i in s]
    rec(f"relevant_pairs_with_zero_train_indegree[{n}]", round(float(np.mean([train_deg[i] == 0 for i in pairs])), 4))
rec("train_indegree_dist_over_pool", dist([train_deg[i] for i in pool_ids]))

Path(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "data_inspect.json").write_text(json.dumps(OUT, indent=1, default=str))
