"""Command-line search: `python -m irlegal.cli --query Q-TE1` or `--text "..."`.

Owner: WS3 (search is theirs). Phase 0 uses ToyRanker. TODO(ws3): real rankers.
"""
import argparse

from irlegal.common.schema import QUERY_ZONES, SPLITS, Query
from irlegal.common.toy import toy_bundle


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Find prior cases (Phase 0: toy ranker).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="dataset query id, e.g. Q-TE1")
    g.add_argument("--text", help="facts and issues as free text")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args(argv)

    corpus, index, ranker = toy_bundle()
    if args.query:
        matches = [q for s in SPLITS for q in corpus.queries(s) if q.qid == args.query]
        if not matches:
            ap.error(f"unknown query id {args.query}")
        query = matches[0]
    else:
        query = Query("adhoc", "adhoc", args.text, {z: "" for z in QUERY_ZONES} | {"facts": args.text},
                      set(), None, "adhoc", set())
    print(f"[toy ranker -- not a real result] query {query.qid}")
    for i, r in enumerate(ranker.rank(query, args.k), 1):
        m = index.meta(r.doc_id)
        mark = "  *cited*" if r.doc_id in query.relevant else ""
        print(f"{i:>2}. {r.score:.3f}  {r.doc_id}  {m['title']} ({m['court']}, {m['date']}){mark}")


if __name__ == "__main__":
    main()
