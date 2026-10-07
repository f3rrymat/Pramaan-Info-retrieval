// Efficiency dashboard and crawl simulation (analyst, admin). Takeaways are generated from the saved numbers, not written by hand.
import { h, clear, fmt, pct, signed } from "/ui/dom.js";
import { alertBox, button, downloadBlob, emptyState, errorState, exportSvgPng, kpi, pageHead, segmented, skeletonCards, skeletonChart, table, tabs, toCsv } from "/ui/components.js";
import { linkHover } from "/ui/motion.js";
import { explainMetric } from "/ui/assistant/panel.js";
import { get } from "/ui/api.js";
import { lines, scatter, seriesLegend } from "/ui/charts.js";
import { tradeoffExplorer, crawlReplay } from "/ui/explorer.js";
import { reducedMotion } from "/ui/dom.js";
import { onVisible } from "/ui/scrollstory.js";
import { explainChip } from "/ui/explain.js";

const FAM = [["champion lists", "Champion lists", "var(--f-neighbour)"], ["authority tiers", "Authority tiers", "var(--f-authority)"], ["index elimination", "Index elimination", "var(--f-recency)"], ["cluster pruning", "Cluster pruning", "var(--f-text)"]];

export function takeaway(rows, baseRow, family, unit) {
  const r = rows.filter((x) => x.family === family && !x.method.includes("alone") && x !== baseRow);
  if (!r.length) return "No rows for this family in the saved run.";
  const ok = r.filter((x) => x.MAP_retained >= 0.95).sort((a, b) => a.mean_candidates_scored - b.mean_candidates_scored)[0];
  const best = [...r].sort((a, b) => b.MAP_retained - a.MAP_retained)[0];
  const b = baseRow.mean_candidates_scored;
  const lat = (x) => (x.median_ms < baseRow.median_ms ? `faster (${x.median_ms} ms against ${baseRow.median_ms} ms median)` : `not faster in this Python implementation (${x.median_ms} ms against ${baseRow.median_ms} ms median)`);
  if (ok) return `${ok.method} keeps ${pct(ok.MAP_retained, 0)} of MAP and ${pct(ok["R@10_retained"], 0)} of R@10 while scoring ${pct(1 - ok.mean_candidates_scored / b, 0)} fewer ${unit} (${ok.mean_candidates_scored} against ${b}). Latency: ${lat(ok)}.`;
  return `No setting keeps 95% of MAP. The best, ${best.method}, keeps ${pct(best.MAP_retained, 0)} of MAP and ${pct(best["R@10_retained"], 0)} of R@10 while scoring ${pct(1 - best.mean_candidates_scored / b, 0)} fewer ${unit}. The cheapest settings lose far more.`;
}

export default async function efficiency({ container }) {
  container.append(pageHead("Efficiency and crawl", "Quality kept against work saved, measured on dev. Candidates scored is machine independent; latency is Python wall time on one machine."));
  const body = h("div", { class: "stack" }, h("div", { class: "grid cols-4" }, skeletonCards(1), skeletonCards(1), skeletonCards(1), skeletonCards(1)), skeletonChart("300px")); container.append(body);
  linkHover(container);
  let eff, crawl;
  try { [eff, crawl] = await Promise.all([get("/api/eval/efficiency"), get("/api/results/crawl_sim")]); } catch (e) { clear(body).append(errorState(e, () => location.reload())); return; }
  const content = h("div", { class: "stack" });
  clear(body).append(tabs([{ id: "pruning", label: "Pruning" }, { id: "crawl", label: "Crawl simulation" }], "pruning", (id) => { clear(content); (id === "pruning" ? pruning : crawlPane)(); }), content);

  function pruning() {
    if (!eff.available) return content.append(h("div", { class: "card" }, emptyState("No efficiency run saved", eff.status, { icon: "gauge" })));
    const d = eff.data, text = d.text_stage, base = text.find((x) => x.family === "baseline"), cl = d.cluster_pruning, clBase = cl.find((x) => x.method.startsWith("exhaustive neighbour search (Config A"));
    let fam = "champion lists";
    const chartBox = h("div", {}), take = h("div", {}), tbl = h("div", {}), exBox = h("div", {});
    const draw = () => {
      const all = [...text.filter((x) => x.family !== "baseline"), ...cl.filter((x) => !x.method.includes("alone") && x !== clBase)];
      const pts = all.map((x) => ({ label: x.method, x: Math.max(x.mean_candidates_scored, 1), y: x.MAP_retained, color: x.family === fam ? FAM.find((f) => f[0] === x.family)[2] : "var(--bar-muted)" }));
      clear(chartBox).append(scatter(pts, { xLabel: "mean candidates scored (log scale): documents for text stages, train queries for cluster pruning", yLabel: "MAP kept vs exhaustive" }));
      const isCl = fam === "cluster pruning", baseRow = isCl ? clBase : base;
      clear(take).append(alertBox(takeaway(isCl ? cl : text, baseRow, fam, isCl ? "train queries" : "documents"), "ok", "target"));
      const famRows = (isCl ? cl : text).filter((x) => x.family === fam && !x.method.includes("alone") && x !== baseRow).map((x) => ({ method: x.method, x: Math.max(x.mean_candidates_scored, 1), y: x.MAP_retained, y2: x["R@10_retained"] }));
      famRows.push({ method: "exhaustive", x: baseRow.mean_candidates_scored, y: 1, y2: 1 });
      const unit = isCl ? "train queries" : "documents", famName = FAM.find((f) => f[0] === fam);
      clear(exBox).append(tradeoffExplorer({ rows: famRows, base: baseRow.mean_candidates_scored, unit, name: famName[1], color: famName[2], sentence: () => takeaway(isCl ? cl : text, baseRow, fam, unit) }).el);
      const rows = (isCl ? cl : text).filter((x) => x.family === fam || x === baseRow);
      clear(tbl).append(table(["Method", "Candidates", "Median ms", "p95 ms", "MAP", "MAP kept", "R@10 kept"], rows.map((x) => [x.method, x.mean_candidates_scored, x.median_ms, x.p95_ms, fmt(x.MAP), pct(x.MAP_retained, 0), pct(x["R@10_retained"], 0)]), { numeric: [1, 2, 3, 4, 5, 6], highlight: (i, r) => r[0] === baseRow.method, rowKey: (r) => r[0] }));
    };
    const sel = segmented(FAM.map(([v, l]) => ({ value: v, label: l })), fam, (v) => { fam = v; draw(); }, { label: "Method" });
    content.append(h("div", { class: "grid cols-4" }, kpi("Documents scored by exhaustive tf-idf", base.mean_candidates_scored, { decimals: 0, hint: `of ${d.pool_docs} in the pool`, onExplain: explainMetric }), kpi("Exhaustive MAP", base.MAP, { decimals: 3, onExplain: explainMetric }), kpi("Train queries in the neighbour index", d.train_queries_in_neighbour_index, { decimals: 0, onExplain: explainMetric }), kpi("Dev queries", d.n_queries, { decimals: 0 })),
      h("section", { class: "tile accent stack" }, h("div", { class: "card-head" }, h("h2", {}, "Trade-off explorer"), explainChip("efficiency trade-off: quality kept against work saved"), sel), h("p", { class: "small muted" }, "Pick a method, then drag the point along its measured settings. Between two measured settings the position is interpolated for display only."), exBox),
      h("section", { class: "card stack" }, h("div", { class: "card-head" }, h("h2", {}, "All methods at a glance"), button("PNG", { variant: "secondary", size: "sm", icon: "image", onClick: () => exportSvgPng(chartBox.querySelector("svg"), "efficiency.png") })), chartBox, h("p", { class: "xs muted" }, "Each dot is one setting. The selected family is coloured; the dashed green line is exhaustive search. Text-stage rows are relative to exhaustive tf-idf; cluster rows to the exhaustive neighbour search inside Config A."), take, tbl),
      h("section", { class: "card stack" }, h("h3", {}, `Heap top-K against full sort${d.heap_equals_sort_on_50_queries ? " (identical output verified on 50 queries)" : ""}`), table(["K", "Method", "Median ms", "p95 ms"], d.heap_vs_sort.map((x) => [x.K, x.method, x.median_ms, x.p95_ms]), { numeric: [0, 2, 3] })));
    draw();
  }

  function crawlPane() {
    if (!crawl.available) return content.append(h("div", { class: "card" }, emptyState("No crawl simulation saved", crawl.status, { icon: "gauge" })));
    const d = crawl.data, curves = d.share_of_targets_fetched_by_budget, names = Object.keys(curves), buds = Object.keys(curves[names[0]]).map(Number);
    const col = { priority: "var(--f-neighbour)", "priority strict": "var(--f-authority)", BFS: "var(--f-court)" };
    const ser = names.map((n) => ({ name: n, color: n.startsWith("BFS") ? col.BFS : n.startsWith("priority strict") ? col["priority strict"] : col.priority, points: buds.map((b) => [b, curves[n][b]]) }));
    const pr = names.find((n) => n.startsWith("priority (")), bfs = names.find((n) => n.startsWith("BFS"));
    const ahead = buds.filter((b) => curves[pr][b] > curves[bfs][b]).length, last = buds[buds.length - 1], mid = buds[Math.floor(buds.length / 2)];
    const rp = crawlReplay(ser, { reduced: reducedMotion() });
    const chart = lines(ser, { xLabel: "fetch budget (pages fetched)", yLabel: "share of the most-cited documents found", yMax: 1, xTicks: buds, xFmt: (v) => v });
    content.append(h("div", { class: "alert warn" }, h("div", {}, h("b", {}, "Simulation only. "), `No network traffic: the crawler replays a crawl over the citation graph (${d.pages.toLocaleString()} pages, ${d.hosts} courts as hosts, virtual politeness clock). Targets: ${d.targets}. Averaged over ${d.trials} random seed sets of ${d.seeds_per_trial} pages.`)),
      h("section", { class: "tile accent stack" }, h("div", { class: "card-head" }, h("h2", {}, "Crawl replay"), explainChip("crawl simulation")), rp.el),
      h("section", { class: "card stack" }, h("div", { class: "card-head" }, h("h2", {}, "Share of the most-cited documents found against fetch budget"), button("PNG", { variant: "secondary", size: "sm", icon: "image", onClick: () => exportSvgPng(chart, "crawl.png") }), button("CSV", { variant: "secondary", size: "sm", icon: "download", onClick: () => downloadBlob("crawl.csv", new Blob([toCsv([["budget", ...names], ...buds.map((b) => [b, ...names.map((n) => curves[n][b])])])], { type: "text/csv" })) })), chart, seriesLegend(ser),
        alertBox(`The in-link priority crawler is ahead of BFS at ${ahead} of ${buds.length} budgets; at ${mid} fetches the difference is ${signed(curves[pr][mid] - curves[bfs][mid], 3)} and at ${last} it is ${signed(curves[pr][last] - curves[bfs][last], 3)}. On this graph, prioritising by in-links discovered so far did not clearly beat breadth-first search.`, "", "info"),
        h("p", { class: "xs muted" }, `Links run both ways (a page lists what it cites and, for pool documents, who cites it). Without the back-links the crawl dies after about two hops. ${d.note}`),
        table(["Budget", ...names], buds.map((b) => [b, ...names.map((n) => fmt(curves[n][b], 3))]), { numeric: [1, 2, 3] }),
        d.duplicate_check_run_3000_fetches ? h("p", { class: "small" }, `Shingle-Jaccard duplicate check in a ${d.duplicate_check_run_3000_fetches.fetched}-fetch run: ${d.duplicate_check_run_3000_fetches.near_duplicates} near-duplicate pages found; ${d.duplicate_check_run_3000_fetches.urls_merged_by_normalisation.toLocaleString()} raw URLs merged by normalisation.`) : null));
  }
  pruning();
}
