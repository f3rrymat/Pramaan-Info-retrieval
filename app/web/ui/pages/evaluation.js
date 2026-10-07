// Evaluation dashboard (analyst, admin). Every number comes from saved runs served by /api/eval/*, /api/results/* and /api/public/provenance (D32, D48).
// Bento layout: KPI tiles, one grouped-bar + table tile for every system (dev/test toggle), ablation ladder as a story-mode stepper,
// leakage audit as an animated before/after, PR curve with a hover crosshair, and a clearly labelled section for what did not help.
import { h, clear, fmt, signed, reducedMotion } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { ZONES, alertBox, badge, button, countUp, downloadBlob, emptyState, errorState, exportSvgPng, kpi, pageHead, skeletonCards, skeletonChart, toCsv, zoneLabel, chip } from "/ui/components.js";
import { linkHover } from "/ui/motion.js";
import { explainMetric } from "/ui/assistant/panel.js";
import { get } from "/ui/api.js";
import { groupedBars, ladderChart, prChart, beforeAfter, tooltip } from "/ui/evalcharts.js";
import { ladderOf, narrate } from "/ui/evaldata.js";
import { onVisible } from "/ui/scrollstory.js";
import { explainChip } from "/ui/explain.js";

const A = "Config A (text + neighbour + authority)", AT = "Config A + temporal filter", T = "tf-idf lnc.ltc";
const find = (run, name) => run && Object.entries(run.macro).find(([k]) => k === name || k.startsWith(name))?.[1];
const COLS = ["P@5", "R@5", "P@10", "R@10", "P@20", "R@20", "MAP", "MRR", "nDCG@10"];
const SERIES_COL = ["var(--f-court)", "var(--f-authority)", "var(--f-text)", "var(--f-neighbour)", "var(--f-recency)"];

export default async function evaluation({ container }) {
  container.append(pageHead("Evaluation", "Saved runs only: nothing here is recomputed or typed by hand. Facts + Issues queries; rows marked REFERENCE use the full judgment and are not comparable."));
  const body = h("div", { class: "stack" }, h("div", { class: "grid cols-4" }, skeletonCards(1), skeletonCards(1), skeletonCards(1), skeletonCards(1)), skeletonChart()); container.append(body);
  linkHover(container);
  let sum, abl, leak, zm, wv, dec, prov = null;
  try {
    [sum, abl, leak, zm, wv, dec] = await Promise.all([get("/api/eval/summary"), get("/api/eval/ablation"), get("/api/eval/leakage"), get("/api/eval/zone_matrix"), get("/api/results/w_variant"), get("/api/results/decompose_dev")]);
    prov = await get("/api/public/provenance").catch(() => null);
  } catch (e) { clear(body).append(errorState(e, () => location.reload())); return; }
  if (!sum.available) { clear(body).append(h("div", { class: "card" }, emptyState("No saved evaluation run on this machine", sum.status || "Run python -m irlegal.evaluation.runner --split dev to create one.", { icon: "chart" }))); return; }
  const dev = sum.dev, test = sum.test;
  const state = { split: "dev", k: 10 };
  const run = () => (state.split === "test" && test ? test : dev);
  const exportBtns = (getSvg, rows, name) => h("div", { class: "row", style: { gap: "6px" } }, button("CSV", { variant: "secondary", size: "sm", icon: "download", title: "Download this table as CSV", onClick: () => downloadBlob(`${name}.csv`, new Blob([toCsv(rows())], { type: "text/csv" })) }),
    getSvg ? button("PNG", { variant: "secondary", size: "sm", icon: "image", title: "Download this chart as PNG", onClick: () => { const s = getSvg(); s && exportSvgPng(s, `${name}.png`); } }) : null);
  const tile = (cls, ...kids) => h("section", { class: `tile ${cls}` }, ...kids);

  // ------------------------------------------------------------------ KPI tiles
  const aT = find(dev, AT), t0 = find(dev, T), tt = find(test, T), atT = find(test, AT);
  const kpis = h("div", { class: "bento" },
    ...[["Ours + temporal filter · dev MAP", aT?.MAP, `${dev.n_queries} dev queries`], ["Ours + temporal filter · test MAP", atT?.MAP, test ? `${test.n_queries} test queries, run once` : "test split not run here"], ["tf-idf baseline · dev MAP", t0?.MAP, "lnc.ltc, Facts + Issues"], ["tf-idf baseline · test MAP", tt?.MAP, test ? "run once" : "test split not run here"]]
      .map(([l, v, hint]) => h("div", { class: "b3" }, kpi(l, v, { decimals: 3, hint, onExplain: explainMetric }))));

  // ------------------------------------------------------------------ all systems: toggle, grouped bars, table
  const metricsFor = (k) => [{ key: `P@${k}`, label: `P@${k}`, color: "var(--m-p)" }, { key: `R@${k}`, label: `R@${k}`, color: "var(--m-r)" }, { key: "MAP", label: "MAP", color: "var(--m-map)" }];
  const systemsOf = (r) => {
    const diffs = r["bootstrap_diff_[mean,lo95,hi95]"]?.vs_tfidf || {};
    return Object.entries(r.macro).map(([name, m]) => { const d = diffs[name]?.MAP; return { name, values: m, ci: d && d[2] > d[1] ? [d[1] - d[0], d[2] - d[0]] : null }; });
  };
  const chartHost = h("div", { class: "chart-host" });
  const hoverTip = tooltip(chartHost);
  const gbx = groupedBars(systemsOf(run()), metricsFor(state.k), { max: niceMax(run(), state.k), tip: hoverTip });
  chartHost.prepend(gbx.el);
  const tbody = h("tbody", {});
  const table = h("div", { class: "table-wrap" }, h("table", { class: "table eval-table" }, h("thead", {}, h("tr", {}, h("th", {}, "System"), ...COLS.map((c) => h("th", { class: "n" }, c)))), tbody));
  const paintTable = () => {
    const r = run(); clear(tbody);
    Object.entries(r.macro).forEach(([n, m]) => tbody.append(h("tr", { class: n.startsWith(AT) ? "hl" : "", "data-series": n }, h("td", {}, n), ...COLS.map((c) => h("td", { class: "n" }, m[c] == null ? "–" : fmt(m[c], 4))))));
    if (!reducedMotion()) tbody.animate([{ opacity: 0.35 }, { opacity: 1 }], { duration: 320, easing: "ease-out" });
  };
  const rowsForCsv = () => [["System", ...COLS], ...Object.entries(run().macro).map(([n, m]) => [n, ...COLS.map((c) => m[c])])];
  // dev / test toggle with a gliding thumb
  const mkToggle = (opts, cur, on, label) => {
    const thumb = h("span", { class: "tg-thumb", "aria-hidden": "true" });
    const bs = opts.map(([v, l, dis, tip]) => h("button", { type: "button", role: "radio", class: "tg-opt", "aria-checked": String(v === cur), disabled: dis || null, "data-tip": tip || null, onClick: () => { if (dis) return; set(v); on(v); } }, l));
    const el = h("div", { class: "toggle", role: "radiogroup", "aria-label": label, style: { "--n": opts.length } }, thumb, bs);
    const set = (v) => { const i = Math.max(0, opts.findIndex((o) => o[0] === v)); thumb.style.transform = `translateX(${i * 100}%)`; bs.forEach((b, j) => b.setAttribute("aria-checked", String(j === i))); };
    set(cur);
    return { el, set };
  };
  const splitToggle = mkToggle([["dev", `Dev · ${dev.n_queries}`], ["test", `Test · ${test ? test.n_queries : "n/a"}`, !test, test ? "Final run, done once" : "The test split has not been run on this machine"]], "dev", (v) => { state.split = v; refreshSystems(); refreshPr(); }, "Split");
  const kToggle = mkToggle([[5, "k = 5"], [10, "k = 10"], [20, "k = 20"]].map(([v, l]) => [String(v), l]), "10", (v) => { state.k = +v; refreshSystems(); }, "Cut-off k");
  function refreshSystems() { const r = run(); gbx.update(systemsOf(r), metricsFor(state.k), niceMax(r, state.k)); paintTable(); sysLegend(); noteEl.textContent = noteText(); }
  const sysLegend = () => { clear(legendEl).append(...metricsFor(state.k).map((m) => h("span", {}, h("i", { style: { "--lc": m.color } }), m.label))); };
  const legendEl = h("div", { class: "legend" });
  const noteText = () => { const r = run(); return `${r.n_queries} ${state.split} queries, macro-averaged. Whiskers on the MAP bars are the 95% paired-bootstrap interval of the MAP difference to tf-idf (${r.bootstrap_resamples} resamples over queries), centred on the system's MAP. Temporal filter: both dates are known for ${(r.notes.share_pairs_both_dates_known * 100).toFixed(1)}% of query-document pairs.`; };
  const noteEl = h("p", { class: "xs muted" }, noteText());
  const systems = tile("b12", h("div", { class: "card-head" }, h("h2", {}, "Every system: P@k, R@k and MAP"), explainChip("systems table: P@k, R@k and MAP"), splitToggle.el, kToggle.el, exportBtns(() => gbx.el, rowsForCsv, "all_systems")),
    legendEl, chartHost, table, noteEl);
  sysLegend(); paintTable();
  if (!test) systems.append(alertBox("The test split has not been run on this machine. It is only run once, with --final.", "warn", "lock"));

  // ------------------------------------------------------------------ ablation ladder (story mode)
  const ablationTile = (() => {
    if (!abl.available) return tile("b12", h("h2", {}, "Ablation ladder"), emptyState("No ablation file", abl.status, { icon: "layers" }));
    const a = abl.data, diffs = a["diff_vs_tfidf_[mean,lo95,hi95]"];
    const steps = ladderOf(Object.entries(a.rows).map(([row, m]) => ({ row, MAP: m.MAP, ci: diffs[row]?.MAP && diffs[row].MAP[2] > diffs[row].MAP[1] ? [diffs[row].MAP[1] - diffs[row].MAP[0], diffs[row].MAP[2] - diffs[row].MAP[0]] : null })));
    const lc = ladderChart(steps);
    let i = 0;
    const narr = h("p", { class: "narration", "aria-live": "polite" });
    const counter = h("span", { class: "xs muted num" });
    const prev = button("Previous", { variant: "secondary", size: "sm", icon: "chevL", onClick: () => go(i - 1) }), next = button("Next step", { size: "sm", icon: "chevR", onClick: () => go(i + 1) });
    const dots = h("div", { class: "step-dots", role: "tablist", "aria-label": "Ladder steps" }, steps.map((s, j) => h("button", { class: "step-dot", type: "button", role: "tab", "aria-label": `Step ${j + 1}: ${s.label}`, onClick: () => go(j) })));
    function go(j) {
      i = Math.max(0, Math.min(steps.length - 1, j)); lc.setStep(i); narr.textContent = narrate(steps, i); counter.textContent = `Step ${i + 1} of ${steps.length}: ${steps[i].label}`;
      prev.disabled = i === 0; next.disabled = i === steps.length - 1; [...dots.children].forEach((d, k) => { d.setAttribute("aria-selected", String(k === i)); d.classList.toggle("done", k < i); });
    }
    const el = tile("b8 story-tile", h("div", { class: "card-head" }, h("h2", {}, "Ablation ladder: one signal at a time"), explainChip("ablation ladder"), exportBtns(() => lc.el, () => [["Step", "MAP", "Change"], ...steps.map((s) => [s.label, s.MAP, s.delta ?? ""])], "ablation_ladder")),
      h("p", { class: "small muted" }, "Dev queries. Each step adds one signal to the one before. Whiskers are the 95% interval of the paired MAP difference to tf-idf. Use the buttons or the left and right arrow keys."),
      h("div", { class: "chart-host" }, lc.el), narr, h("div", { class: "row stepper" }, prev, next, dots, h("span", { class: "grow" }), counter));
    el.setAttribute("tabindex", "0"); el.setAttribute("aria-label", "Ablation ladder story, use arrow keys");
    el.addEventListener("keydown", (e) => { if (e.target.closest("button")) return; if (e.key === "ArrowRight") { e.preventDefault(); go(i + 1); } else if (e.key === "ArrowLeft") { e.preventDefault(); go(i - 1); } });
    go(0);
    const side = h("section", { class: "tile b4" }, h("h3", {}, "Other rows that were tried"), h("p", { class: "small muted" }, "Not on the ladder: single-signal rows and the two weaker step-7 weightings. MAP on dev."),
      h("ul", { class: "plain-list" }, Object.entries(a.rows).filter(([n]) => !n.startsWith("REFERENCE") && !n.startsWith("ref:") && !steps.some((s) => s.row === n)).map(([n, m]) => h("li", {}, h("span", { class: "grow small" }, n.replace(/\(candidates.*?\)/, "").trim()), h("b", { class: "num small" }, fmt(m.MAP, 3))))));
    return h("div", { class: "bento", style: { gridColumn: "1 / -1" } }, el, side);
  })();

  // ------------------------------------------------------------------ leakage audit (animated before / after) and PR curve
  const leakTile = (() => {
    if (!leak.available) return tile("b6", h("h2", {}, "Leakage audit"), emptyState("No leakage audit", leak.status, { icon: "lock" }));
    const L = leak.data, a = L.a_no_leave_one_out_train_queries, items = [], det = [];
    const add = (label, before, after, ci, tone) => { items.push({ label, before, after, tone }); det.push([label, before, after, `${signed(ci[0])} [${signed(ci[1])}, ${signed(ci[2])}]`]); };
    for (const s of ["config_A", "neighbour_alone"]) add(`(a) no leave-one-out: ${s.replace("_", " ")}`, a[s].with_LOO.MAP, a[s].without_LOO.MAP, a[s]["inflation_[mean,lo95,hi95]"].MAP, "bad");
    { const b = L.b_authority_train_plus_dev_links_vs_train_only_scoring_dev.config_A; add("(b) dev links in authority: config A", b.train_only.MAP, b.train_plus_dev.MAP, b["inflation_[mean,lo95,hi95]"].MAP, "bad"); }
    for (const s of ["tfidf", "config_A"]) { const c = L.c_citation_scrubbing_off_vs_on_dev[s]; add(`(c) scrubbing off: ${s.replace("_", " ")}`, c.scrubbed.MAP, c.not_scrubbed.MAP, c["difference_unscrubbed_minus_scrubbed_[mean,lo95,hi95]"].MAP, "bad"); }
    { const d = L.d_temporal_filter_on_vs_off_dev.config_A; add("(d) temporal filter on: config A", d.off.MAP, d.on.MAP, d["difference_on_minus_off_[mean,lo95,hi95]"].MAP, "good"); }
    const ba = beforeAfter(items, { width: 640, left: 250 });
    const tg = mkToggle([["before", "Before: as shipped"], ["after", "After: with the change"]], "before", (v) => ba.set(v), "Leakage audit state");
    const replay = () => { ba.set("before", { animate: false }); tg.set("before"); setTimeout(() => { ba.set("after"); tg.set("after"); }, reducedMotion() ? 0 : 450); };
    const el = tile("b7", h("div", { class: "card-head" }, h("h2", {}, "Leakage audit"), explainChip("leakage audit (leave-one-out)"), tg.el, button("Replay", { variant: "ghost", size: "sm", icon: "shuffle", onClick: replay }), exportBtns(() => ba.el, () => [["Audit", "Before MAP", "After MAP", "Delta [95%]"], ...det], "leakage_audit")),
      alertBox(`Without leave-one-out, scoring train queries inflates Config A MAP from ${fmt(a.config_A.with_LOO.MAP, 3)} to ${fmt(a.config_A.without_LOO.MAP, 3)}: a query would find its own citations. The shipped system uses leave-one-out; dev and test queries are never in the graph.`, "warn", "alert"),
      h("div", { class: "chart-host" }, ba.el),
      h("div", { class: "table-wrap" }, h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Audit", "Before", "After", "Delta [95% interval]"].map((x, j) => h("th", { class: j ? "n" : "" }, x)))), h("tbody", {}, det.map((r) => h("tr", { "data-series": r[0] }, h("td", {}, r[0]), h("td", { class: "n" }, fmt(r[1], 4)), h("td", { class: "n" }, fmt(r[2], 4)), h("td", { class: "n" }, r[3])))))),
      h("p", { class: "xs muted" }, `Audit (a) uses ${a.n_queries} train queries; (b) to (d) use dev queries. The test split is never used here.`));
    onVisible(el, () => setTimeout(() => { ba.set("after"); tg.set("after"); }, reducedMotion() ? 0 : 500), { threshold: 0.45 });
    return el;
  })();

  const prHost = h("div", { class: "chart-host" });
  const prState = { on: new Set([T, AT, A, "BM25 tuned"]) };
  const prTile = tile("b5 pr-tile", h("div", { class: "card-head" }, h("h2", {}, "Precision-recall curve"), explainChip("precision-recall curve")), prHost);
  let prSvg = null, prChips = h("div", { class: "row", style: { gap: "6px" } }), prTip = null;
  function refreshPr() {
    const r = run(), x = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];
    const names = Object.keys(r.pr_curve_11pt).filter((n) => !n.startsWith("REFERENCE") && n !== "random");
    const ser = names.filter((n) => [...prState.on].some((o) => n.startsWith(o))).map((n) => ({ name: n, color: SERIES_COL[names.indexOf(n) % 5], points: x.map((v, j) => [v, r.pr_curve_11pt[n][j]]) }));
    clear(prHost); const host = h("div", { class: "chart-host" }); prTip = tooltip(host);
    const c = prChart(ser, { tip: prTip, width: 560, height: 330 }); prSvg = c.el; host.prepend(c.el);
    clear(prChips).append(...names.map((n) => chip(n, { pressed: ser.some((s) => s.name === n), onClick: () => { const k = [...prState.on].find((o) => n.startsWith(o)) || n; prState.on.has(k) ? prState.on.delete(k) : prState.on.add(k); refreshPr(); } })));
    prHost.append(host, prChips, h("p", { class: "xs muted" }, `${state.split === "test" ? "Test" : "Dev"} run, ${r.n_queries} queries. Hover or use the arrow keys to read precision at each recall level; 11-point interpolation: the best precision at that recall or higher, averaged over queries.`));
    const head = prTile.querySelector(".card-head"); if (head && !head.querySelector(".btn")) head.append(exportBtns(() => prSvg, () => [["system", ...x], ...ser.map((s) => [s.name, ...s.points.map((p) => p[1])])], "pr_curve"));
  }
  refreshPr();

  // ------------------------------------------------------------------ negative results (clearly labelled)
  const negTile = (() => {
    const cards = [];
    if (wv.available) { const m = wv.data.dev.MAP; cards.push(["Learned zone-pair matrix", "did not help", `A regularised variant with six a-priori pairs changed dev MAP by ${signed(m.diff)} [${signed(m.ci95[0])}, ${signed(m.ci95[1])}] against tf-idf; the interval does not exclude zero.`]); }
    if (abl.available) { const r = abl.data["diff_vs_tfidf_[mean,lo95,hi95]"], k = Object.keys(r).find((n) => n.startsWith("3 + statute")); if (k) cards.push(["Statute channel", "marginal", `Adds ${signed(r[k].MAP[0])} MAP [${signed(r[k].MAP[1])}, ${signed(r[k].MAP[2])}] over tf-idf.`]);
      const u = abl.data.union_recall; cards.push(["Union first stage", "did not help", `Recall ${fmt(u["300"].dev_recall, 3)} at a mean union size of ${u["300"].dev_mean_union_size} against ${fmt(u.tfidf_top1000_only.dev_recall, 3)} for tf-idf top 1000.`]); }
    if (dec.available) { const r = dec.data.rows["RRF of issue sub-queries only"]["MAP_diff_vs_single_[mean,lo95,hi95]"]; cards.push(["Issue decomposition (RRF of sub-queries)", "hurt", `${dec.data.mean_sub_queries_per_query} sub-queries per query on average; MAP change against the single query ${signed(r[0])} [${signed(r[1])}, ${signed(r[2])}].`]); }
    const el = h("section", { class: "tile b12 negative", "aria-labelledby": "neg-h" }, h("div", { class: "row" }, badge("Negative results", "warn"), h("h2", { id: "neg-h" }, "What did not help")),
      h("p", { class: "small muted" }, "These ideas were tried and are reported as measured. They are not part of the headline system."),
      h("div", { class: "grid cols-2" }, cards.map(([t, tag, text]) => h("div", { class: "card flat stack" }, h("div", { class: "row" }, h("h3", {}, t), badge(tag, tag === "marginal" ? "warn" : "err")), h("p", { class: "small" }, text)))));
    if (zm.available) {
      const W = zm.data.W_last_sweep_not_selected || zm.data.W, cols = zm.data.cols_pool_zone, mx = Math.max(...Object.values(W).flatMap((r) => Object.values(r)), 1e-9);
      const head = h("thead", {}, h("tr", {}, h("th", {}, ""), ...cols.map((c) => h("th", {}, c === "all" ? "whole text" : zoneLabel(c)))));
      const cell = (row, c) => h("td", { class: "n", style: { background: `color-mix(in srgb, var(--z-${ZONES.includes(c) ? c : "other"}) ${Math.round((row[c] / mx) * 80)}%, transparent)` } }, fmt(row[c], 3));
      el.append(h("div", { class: "stack" }, h("h3", {}, "Fully trained zone-pair matrix (not selected)"), h("p", { class: "small muted" }, "Rows: query view. Columns: zone of the candidate document, coloured with the zone palette. Trained weights do not beat the plain whole-text pair."),
        h("div", { class: "table-wrap" }, h("table", { class: "table" }, head, h("tbody", {}, ...Object.entries(W).map(([rv, row]) => h("tr", {}, h("th", {}, rv.replace("_", " + ")), ...cols.map((c) => cell(row, c)))))))));
    }
    return el;
  })();

  // ------------------------------------------------------------------ provenance footer
  const updated = prov?.updated;
  const foot = h("p", { class: "xs muted prov-foot", "data-testid": "provenance" }, icon("database", { size: 14 }), ` Numbers come from saved runs on this machine${updated ? `, updated ${updated}` : ""}. Files: ${prov ? Object.keys(prov.files).join(", ") : "unknown"}.`);

  clear(body).append(kpis, systems, ablationTile, h("div", { class: "bento" }, leakTile, prTile), negTile, foot);
}

function niceMax(run, k) {
  const m = Math.max(...Object.values(run.macro).flatMap((x) => [x[`P@${k}`] ?? 0, x[`R@${k}`] ?? 0, x.MAP ?? 0]), 0.05);
  return m > 0.6 ? 1 : m > 0.4 ? 0.6 : m > 0.25 ? 0.5 : 0.3;
}
