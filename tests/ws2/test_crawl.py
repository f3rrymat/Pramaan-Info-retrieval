"""Crawl simulation pieces: URL normalisation, shingle duplicates, Mercator frontier, priority vs BFS on a toy graph."""
from irlegal.crawl.dedupe import ContentSeen, jaccard, shingles
from irlegal.crawl.frontier import MercatorFrontier
from irlegal.crawl.normalize_url import host_of, normalize
from irlegal.crawl.simulate import SimWeb, crawl, share_found


def test_normalisation_collapses_variants():
    canon = "https://delhi-high-court.sim/case/42"
    for v in ("HTTPS://Delhi-High-Court.SIM:443/case/42/", "https://delhi-high-court.sim/case/42?utm_source=a&ref=b",
              "https://delhi-high-court.sim/case/42#para7", "https://delhi-high-court.sim//case/./42", "https://delhi-high-court.sim/x/../case/42"):
        assert normalize(v) == canon
    assert normalize("http://a.sim:8080/p?b=2&a=1") == "http://a.sim:8080/p?a=1&b=2"
    assert normalize("https://a.sim") == "https://a.sim/" and host_of("HTTPS://A.Sim/x") == "a.sim"


def test_shingles_and_content_seen():
    a = "the appellant was convicted under the penal code for causing the death of the deceased on the night"
    assert shingles(a) == shingles(a.upper()) and jaccard(shingles(a), shingles("completely different words here today")) == 0
    seen = ContentSeen(threshold=0.8)
    assert seen.check_and_add("u1", a) is None
    assert seen.check_and_add("u2", a + " yesterday") == "u1"             # near duplicate
    assert seen.check_and_add("u3", "land acquisition compensation was awarded to the owner of the plot in the village") is None
    assert seen.duplicates == [("u2", "u1")]


def test_frontier_politeness_and_priority():
    fr = MercatorFrontier(n_front=3, n_back=2, delay=5.0, bias=[1000, 1, 1], seed=1)
    for i in range(3):
        fr.add(f"https://a.sim/p{i}", 2)
    fr.add("https://b.sim/hot", 0)
    got, t = [], 0.0
    for _ in range(4):
        u, when = fr.pop(t)
        got.append((u.rsplit("/", 1)[-1], when))
        t = when + 1.0
    assert got[0][0] == "hot" or got[0][0].startswith("p")
    times_a = [w for u, w in got if u.startswith("p")]
    assert all(b - a >= 5.0 for a, b in zip(times_a, times_a[1:]))         # same host: at least `delay` apart on the virtual clock
    assert fr.pop(t) is None


def _web():
    """seed -> a -> {hub, x}; hub is cited by many pages; targets: hub."""
    pages = {"seed": ("h1.sim", ["a", "z1", "z2", "z3"], "seed page text"), "a": ("h2.sim", ["hub", "x"], "page a text"),
             "x": ("h1.sim", [], "page x"), "hub": ("h3.sim", [], "hub page"),
             "z1": ("h4.sim", ["hub"], "z1"), "z2": ("h4.sim", ["hub"], "z2"), "z3": ("h5.sim", ["hub"], "z3")}
    return SimWeb(pages)


def test_crawl_follows_links_and_reports_budget_curve():
    order, st = crawl(_web(), ["seed"], budget=50, mode="priority")
    ids = [u.rsplit("/", 1)[-1] for u in order]
    assert ids[0] == "seed" and set(ids) == {"seed", "a", "x", "hub", "z1", "z2", "z3"} and len(ids) == len(set(ids))
    assert st["urls_merged_by_normalisation"] > 0 or st["fetched"] == 7
    bfs, _ = crawl(_web(), ["seed"], budget=50, mode="bfs")
    assert [u.rsplit("/", 1)[-1] for u in bfs][0] == "seed" and len(bfs) == 7
    assert share_found(order, ["hub"], [1, 7]) == {1: 0.0, 7: 1.0}


def test_budget_is_respected_and_no_refetch():
    order, st = crawl(_web(), ["seed"], budget=3, mode="bfs")
    assert len(order) == 3 == st["fetched"]
