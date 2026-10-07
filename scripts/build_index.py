"""Build and persist the pool index to data/index/ and write results/index_report.json.

Reports sizes (raw int32 vs gap+vbyte), in-memory bytes, process memory, the skip-pointer
benchmark. Aggregates only. Usage: python scripts/build_index.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from irlegal.common.config import load_config, repo_path  # noqa: E402
from irlegal.data.loader import IlPcsrCorpus  # noqa: E402
from irlegal.index import skips  # noqa: E402
from irlegal.index.inverted import InvertedIndex  # noqa: E402
from irlegal.preprocess.normalizer import Analyzer  # noqa: E402


def rss_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 2**20, 1)
    except ImportError:
        return None


def main():
    cfg = load_config()
    out_dir = repo_path(cfg["paths"]["index_dir"])
    rss0 = rss_mb()
    t = time.time()
    cases = IlPcsrCorpus().cases()
    an = Analyzer(stem=cfg["ws1"]["stemmer"] == "porter")
    ix = InvertedIndex.build(cases, an, tuple(cfg["ws1"]["positional_zones"]))
    t_build = time.time() - t
    rss1 = rss_mb()
    sizes = ix.save(out_dir)
    mem = ix.memory_bytes()
    # skip benchmark on the 'all' zone: postings of terms with df >= 50
    z = ix.zones["all"]
    lists = [z.docs[z.offsets[i]:z.offsets[i + 1]].tolist() for i in np.flatnonzero(z.df_arr >= 50)[:3000]]
    bench = skips.benchmark(lists, n_pairs=500, seed=cfg["seed"])
    report = {
        "n_docs": ix.n_docs(), "build_seconds": round(t_build, 1),
        "process_rss_mb_before_after_build": [rss0, rss1],
        "in_memory_index_mb": {k: round(v / 2**20, 1) for k, v in mem.items()},
        "in_memory_index_total_mb": round(sum(mem.values()) / 2**20, 1),
        "persisted_sizes_bytes": sizes,
        "persisted_total": {
            "raw_int32_mb": round(sum(s["raw_int32_bytes"] for s in sizes.values()) / 2**20, 2),
            "gap_vbyte_mb": round(sum(s["gap_vbyte_bytes"] for s in sizes.values()) / 2**20, 2)},
        "skip_benchmark_all_zone_df_ge_50": {"n_lists": len(lists), **bench},
        "tokens_all_zone": int(ix.doc_len_array("all").sum()),
        "stem_cache_size": len(an._cache),
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "index_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
