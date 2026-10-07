"""D12: profile pool-only "Court Disclosure" against query-side "Court Reasoning". Aggregates only.

Writes results/role_profile.json. Usage: python scripts/profile_roles.py
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.preprocess.normalizer import Analyzer  # noqa: E402

D = ROOT / "data" / "ilpcsr"
an = Analyzer()


def profile(df, roles):
    pos = {r: [] for r in roles}
    toks = {r: [] for r in roles}
    vocab = {r: Counter() for r in roles}
    for paras, rr in zip(df.text, df.rhetorical_roles):
        n = len(rr)
        for i, (p, r) in enumerate(zip(paras, rr)):
            if r in pos:
                pos[r].append(i / (n - 1) if n > 1 else 0.5)
                t = an.analyze(p)
                toks[r].append(len(p.split()))
                if len(vocab[r]) < 10**7:
                    vocab[r].update(set(t))
    out = {}
    for r in roles:
        a = np.array(pos[r])
        out[r] = {"paragraphs": len(a), "mean_rel_position": round(float(a.mean()), 3),
                  "share_last_10pct": round(float((a > 0.9).mean()), 3),
                  "mean_words": round(float(np.mean(toks[r])), 1)}
    return out, vocab


q, qv = profile(pd.read_parquet(D / "train_queries.parquet"), ["Court Reasoning", "Conclusion", "Precedent Analysis", "Statute Analysis", "Facts"])
p, pv = profile(pd.read_parquet(D / "precedent_candidates.parquet"), ["Court Disclosure", "Conclusion", "Precedent Analysis", "Statute Analysis", "Facts"])


def distinctive(a, na, b, nb, k=12):
    sc = {t: math.log((a[t] + 1) / (na + 2)) - math.log((b.get(t, 0) + 1) / (nb + 2)) for t in a if a[t] >= 30}
    return [t for t, _ in sorted(sc.items(), key=lambda kv: -kv[1])[:k]]


cd, cr = pv["Court Disclosure"], qv["Court Reasoning"]
out = {"queries(train)": q, "pool": p,
       "distinctive_stems_Court_Disclosure_vs_Court_Reasoning": distinctive(cd, p["Court Disclosure"]["paragraphs"], cr, q["Court Reasoning"]["paragraphs"]),
       "distinctive_stems_Court_Reasoning_vs_Court_Disclosure": distinctive(cr, q["Court Reasoning"]["paragraphs"], cd, p["Court Disclosure"]["paragraphs"])}
# does Court Disclosure vocabulary look like Conclusion or like Court Reasoning? cosine over document-frequency vectors
def cos(a, b):
    keys = set(a) | set(b)
    x = np.array([a.get(k, 0) for k in keys], float); y = np.array([b.get(k, 0) for k in keys], float)
    return float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y)))
out["vocab_cosine_CourtDisclosure_vs"] = {"query Court Reasoning": round(cos(cd, cr), 3), "query Conclusion": round(cos(cd, qv["Conclusion"]), 3),
                                          "query Precedent Analysis": round(cos(cd, qv["Precedent Analysis"]), 3), "pool Conclusion": round(cos(cd, pv["Conclusion"]), 3)}
dpos, rpos = p["Court Disclosure"]["mean_rel_position"], q["Court Reasoning"]["mean_rel_position"]
last = p["Court Disclosure"]["share_last_10pct"]
rule = "reasoning" if (abs(dpos - rpos) <= 0.15 and last < 0.5) else ("decision" if last > 0.5 else "other")
out["D12_rule_result"] = {"position_gap": round(abs(dpos - rpos), 3), "share_last_10pct": last, "maps_to": rule}
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "role_profile.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
