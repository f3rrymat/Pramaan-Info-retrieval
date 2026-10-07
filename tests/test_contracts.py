"""Phase 0 contract tests. Owner: all. These must keep passing on main."""
import dataclasses
import importlib
import pkgutil

import pytest
from fastapi.testclient import TestClient

import irlegal
from irlegal.common import interfaces as I
from irlegal.common.schema import COMPONENTS, ZONES, Case, Query, Result
from irlegal.common.toy import ToyCorpus, ToyIndex, ToyRanker


@pytest.fixture(scope="module")
def toy():
    corpus = ToyCorpus()
    index = ToyIndex(corpus.cases())
    return corpus, index, ToyRanker(corpus, index)


def test_spec_fields_unchanged():
    # The spec's fields must exist in the spec's order; additions only at the end.
    assert [f.name for f in dataclasses.fields(Case)][:8] == [
        "doc_id", "title", "text", "court", "date", "zones", "statutes", "cites_out"]
    assert [f.name for f in dataclasses.fields(Query)] == [
        "qid", "case_id", "text", "zones", "statutes", "date", "split", "relevant"]
    assert [f.name for f in dataclasses.fields(Result)] == ["doc_id", "score", "components", "explanation"]
    # first six are frozen (spec); D8 appended two more after them
    assert ZONES[:6] == ("facts", "issues", "arguments", "reasoning", "decision", "other")
    assert ZONES[6:] == ("statute_analysis", "precedent_analysis")


def test_toy_corpus_loads(toy):
    corpus, _, _ = toy
    assert len(corpus.cases()) == 20
    assert {c.pool for c in corpus.cases()} == {"train", "val", "test"}
    assert sum(len(corpus.queries(s)) for s in ("train", "val", "test")) == 6
    for s in ("train", "val", "test"):
        pool_ids = {c.doc_id for c in corpus.cases(s)}
        for q in corpus.queries(s):
            assert q.relevant and q.relevant <= pool_ids, "relevant docs must be in the query's own pool"
            for d in q.relevant:  # prior cases are older than the query
                assert corpus.get_case(d).date < q.date


def test_toy_objects_satisfy_protocols(toy):
    corpus, index, ranker = toy
    assert isinstance(corpus, I.CorpusSource)
    assert isinstance(index, I.Index)
    assert isinstance(ranker, I.Ranker)


def test_toy_index_basics(toy):
    _, index, _ = toy
    assert index.n_docs() == 20
    assert index.df("dowry", "facts") >= 1
    doc, tf = index.postings("dowry", "facts")[0]
    assert len(index.positions("dowry", "facts", doc)) == tf
    assert "dowry" in set(index.terms("facts"))


def test_toy_ranker_respects_pool_and_exclusion(toy):
    corpus, _, ranker = toy
    q = corpus.queries("test")[0]
    res = ranker.rank(q, k=10)
    pool = {c.doc_id for c in corpus.cases("test")}
    assert res and all(r.doc_id in pool for r in res)
    assert all(r.doc_id != q.case_id for r in res)
    assert [r.score for r in res] == sorted((r.score for r in res), reverse=True)
    assert set(COMPONENTS) <= set(res[0].components)
    restricted = ranker.rank(q, k=10, candidates={"S04"})
    assert [r.doc_id for r in restricted] == ["S04"]


def test_every_module_imports():
    for info in pkgutil.walk_packages(irlegal.__path__, "irlegal."):
        importlib.import_module(info.name)


def test_server_discovers_routers_and_serves_the_web_app():
    from app.server import app
    client = TestClient(app)
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and not health["router_errors"]
    assert {"ws1_index", "ws2_query", "ws3_search", "ws4_eval"} <= set(health["routers"])
    assert client.get("/ui/main.js").status_code == 200 and client.get("/styles/tokens.css").status_code == 200
    assert client.get("/").status_code == 200
    r = client.post("/api/search", json={"query_id": "Q-TE2", "k": 3}).json()
    assert r["source"] == "toy" and r["results"]
    assert client.get("/api/eval/summary").json()["available"] in (True, False)
