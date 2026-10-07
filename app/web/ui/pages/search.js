// Search workspace. State lives in the URL (#/search?q=...) so every result view is a shareable link. Pasted text is never put in the URL.
import { h, clear, fmt, debounce } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { alertBox, badge, button, chip, courtBadge, dualRange, emptyState, errorState, hbar, legend, modal, pageHead, scoreRing, segmented, skeletonCards, stackBar, toast, zoneLabel, ZONES, FEATURE_LABEL } from "/ui/components.js";
import { searchBar } from "/ui/searchbar.js";
import { strategySwitch, strategyOf, STRATEGIES } from "/ui/strategy.js";
import { get, post, del } from "/ui/api.js";
import { setUrlState, navigate, session as appSession } from "/ui/store.js";
import { openCaseDrawer } from "/ui/casedrawer.js";
import { snapshot, playFlip, motionOK } from "/ui/motion.js";
import { pipelineStrip } from "/ui/pipeline.js";
import { explainResult } from "/ui/assistant/panel.js";

const YMIN = 1900, YMAX = 2025, SHOW = 10;

export function readState(p) {
  return { q: p.q || "", ranker: ["tfidf", "bm25", "ours"].includes(p.ranker) ? p.ranker : "ours", prune: ["none", "champion", "tier", "elimination"].includes(p.prune) ? p.prune : "none",
    court: p.court ? p.court.split(",").filter(Boolean) : [], yf: p.yf ? +p.yf : YMIN, yt: p.yt ? +p.yt : YMAX, temporal: p.temporal === "0" ? false : true, ov: p.ov === "1",
    w: p.w ? p.w.split(",").map(Number) : null };
}
export const requestBody = (s, k = 50) => ({ ...(s.q ? { query_id: s.q } : {}), ranker: s.ranker, pruning: s.prune, k, temporal_filter: s.temporal,
  filters: { ...(s.court.length ? { court: s.court } : {}), ...(s.yf > YMIN ? { year_from: s.yf } : {}), ...(s.yt < YMAX ? { year_to: s.yt } : {}) } });

export default async function search(ctx) {
  const { container, params, onCleanup, setCrumb, session } = ctx;
  const S = readState(params);
  let data = null, overlay = null, weights = null, defaultW = null, shown = SHOW, runId = 0, pasted = "";
  const cards = new Map();
  const keys = ["text", "neighbour", "authority"];
  const root = h("div", { class: "stack", style: { gap: "var(--s-5)" } });
  container.append(pageHead("Find precedents", "Type a dev query id or paste the facts of a case, pick a strategy, and see which earlier judgments are suggested and why. The headline system is Ours with the temporal filter.",
    h("div", { class: "row" }, button("Share link", { variant: "secondary", icon: "link", size: "sm", onClick: async () => { try { await navigator.clipboard.writeText(location.href); toast("Link copied.", "ok"); } catch (_) { toast("Copy the address bar instead.", ""); } } }))), root);
  root.append(skeletonCards(2));

  let qs, meta, head = { rows: [] };
  try { [qs, meta, head] = await Promise.all([get("/api/queries"), get("/api/query_meta").catch(() => ({ items: {} })), get("/api/public/headline").catch(() => ({ rows: [] }))]); } catch (e) { clear(root).append(errorState(e, () => navigate("/search", params))); return; }
  clear(root);
  const rows = Object.fromEntries((head.rows || []).map((r) => [r.key, r]));
  const items = qs.queries.map((q) => { const m = meta.items[q.qid] || {}; return { value: q.qid, label: q.qid, meta: `${m.court || "?"} · ${m.year || q.date?.slice(0, 4) || "?"}`, court: m.court, year: m.year || q.date?.slice(0, 4) }; });
  const saved = new Map();                                        // case id -> saved row id (for the star on each card)
  const loadSaved = () => get("/api/saved").then((r) => { saved.clear(); r.items.filter((i) => i.kind === "case").forEach((i) => saved.set(i.ref, i.id)); cards.forEach((c) => c.paintStar && c.paintStar()); }).catch(() => {});
  loadSaved();
  const pins = new Map();                                         // pinned results (kept for this page visit)

  // ---------------------------------------------------------------- hero bar, strategy switcher, analytics pill
  const bar = searchBar({ items, value: S.q, onQuery: (id) => { S.q = id; pasted = ""; run(); }, onText: (txt) => { pasted = txt; S.q = ""; run(); } });
  const random = button("Random dev query", { variant: "ghost", size: "sm", icon: "shuffle", title: "Pick a random dev query", onClick: () => { const it = items[Math.floor(Math.random() * items.length)]; bar.setValue(it.value); S.q = it.value; pasted = ""; run(); } });
  const strat = strategySwitch({ value: strategyOf(S.ranker, S.temporal), rows, onChange: (v) => {
    if (v === "boolean") { navigate("/querylab", S.q ? {} : {}); return; }
    const s = STRATEGIES.find((x) => x.value === v); S.ranker = s.ranker; S.temporal = s.temporal; temporalInput.checked = S.temporal; weights = null; if (S.q || pasted) run(); else setUrlState("/search", urlParams()); } });
  onCleanup(() => strat.destroy());
  const pillText = h("span", { class: "apill-text" }, "No search yet");
  const pill = h("button", { class: "apill", type: "button", "aria-expanded": "false", "aria-controls": "pipe-strip", disabled: true, onClick: () => { const open = strip.el.hidden; strip.el.hidden = !open; pill.setAttribute("aria-expanded", String(open)); } }, icon("gauge", { size: 15 }), pillText, icon("chevD", { size: 14 }));
  const recent = h("div", { class: "row", style: { gap: "6px" } });
  const hero = h("section", { class: "search-hero", "aria-label": "Search" }, bar.el,
    h("div", { class: "row search-sub" }, random, h("span", { class: "grow" }), recent),
    h("div", { class: "row strat-row" }, h("span", { class: "label" }, "Strategy"), strat.el, h("span", { class: "grow" }), pill));
  const courts = h("div", { class: "row", style: { gap: "6px" } }, [["SC", "Supreme Court"], ["HC", "High Courts"], ["OTHER", "Other"]].map(([c, t]) => chip(t, { pressed: S.court.includes(c), onClick: function () { S.court = S.court.includes(c) ? S.court.filter((x) => x !== c) : [...S.court, c]; this.setAttribute("aria-pressed", String(S.court.includes(c))); debouncedRun(); } })));
  const years = dualRange({ min: YMIN, max: YMAX, lo: S.yf, hi: S.yt, label: "Year", onChange: (a, b) => { S.yf = a; S.yt = b; debouncedRun(); } });
  const temporalInput = h("input", { type: "checkbox", checked: S.temporal, onChange: (e) => { S.temporal = e.target.checked; strat.set(strategyOf(S.ranker, S.temporal)); run(); } });
  const temporal = h("label", { class: "switch" }, temporalInput, "Temporal filter", h("span", { class: "xs muted", "data-tip": "Drops candidates that are not strictly earlier than the query where both dates are known. It also drops the 2 to 3 percent of true citations that the data dates later." }, icon("info", { size: 14 })));
  const prune = segmented([{ value: "none", label: "None" }, { value: "champion", label: "Champion" }, { value: "tier", label: "Tiers" }, { value: "elimination", label: "Elim." }], S.prune, (v) => { S.prune = v; run(); }, { label: "Pruning" });
  const panel = h("aside", { class: "panel-sticky", "aria-label": "Filters" },
    h("div", { class: "card stack" }, h("h3", {}, "Filters"), h("div", { class: "label" }, "Court level"), courts, h("div", { class: "label" }, "Year of the precedent"), years, temporal, h("div", { class: "label" }, "Pruning (efficiency study)"), prune));
  const results = h("section", { class: "stack", "aria-live": "polite", "aria-busy": "false" });
  const tray = h("div", { class: "pin-tray", hidden: true, role: "region", "aria-label": "Pinned cases" });
  const strip = pipelineStrip();
  strip.el.hidden = true; strip.el.id = "pipe-strip";
  onCleanup(() => strip.destroy());
  root.append(hero, h("div", { class: "workspace" }, panel, h("div", { class: "stack results-col", style: { gap: "var(--s-4)", minWidth: 0 } }, strip.el, results, tray)));

  const debouncedRun = debounce(() => run(), 350);
  const history = async () => { try { const r = await get("/api/history?limit=8"); clear(recent); const seen = new Set(); r.items.filter((i) => i.ref !== "pasted" && !seen.has(i.ref) && seen.add(i.ref)).slice(0, 5).forEach((i) => recent.append(chip(i.ref, { mono: true, onClick: () => { S.q = i.ref; pasted = ""; bar.setValue(i.ref); run(); } }))); if (!recent.children.length) recent.append(h("span", { class: "xs muted" }, "Your last searches will appear here.")); bar.invalidate(); } catch (_) { clear(recent).append(h("span", { class: "xs muted" }, "History unavailable.")); } };
  history();

  // ---------------------------------------------------------------- run
  async function run() {
    const id = ++runId;
    if (!S.q && !pasted) { data = null; paintEmpty(); return; }
    setUrlState("/search", urlParams());
    setCrumb(S.q || "pasted text");
    const before = snapshot(results);                     // cards glide from here to their new ranks (FLIP)
    const hadCards = before.size > 0;
    if (!hadCards) clear(results).append(skeletonCards(3)); else results.classList.add("refreshing");
    results.setAttribute("aria-busy", "true");
    strip.start();
    pill.disabled = false; pillText.textContent = "Searching…";
    const t0 = performance.now();
    try {
      const body = { ...requestBody(S), ...(S.q ? {} : { text: pasted }) };
      const [{ data: res, timing }, ov] = await Promise.all([post("/api/search", body, { meta: true }), S.ov && S.q ? post("/api/overlay", { query_id: S.q, ranker: S.ranker, pruning: S.prune, filters: body.filters, temporal_filter: S.temporal }).catch(() => null) : null]);
      if (id !== runId) return;
      strip.finish(timing, performance.now() - t0);
      const total = timing.find((x) => x.name === "total")?.dur;
      clear(pillText).append(...[total != null ? h("b", { class: "num" }, total < 100 ? `${total.toFixed(1)} ms` : `${Math.round(total)} ms`) : null, total != null ? " server" : null, res.candidates_scored != null ? [" · ", h("b", { class: "num" }, res.candidates_scored.toLocaleString("en-US")), " scored"] : null, res.results ? [" · ", h("b", { class: "num" }, res.results.length), " shown"] : null].flat().filter(Boolean));
      data = res; overlay = ov; shown = SHOW;
      defaultW = res.weights ? keys.map((k) => res.weights[k] ?? 0) : null;
      weights = S.w && defaultW && S.w.length === 3 && S.w.every((x) => x >= 0) ? S.w : defaultW ? [...defaultW] : null;
      post("/api/history", { kind: "search", ref: S.q || "pasted", params: { ranker: S.ranker, pruning: S.prune, temporal_filter: S.temporal, k: 50, filters: body.filters } }).then(history).catch(() => {});
      paint(before);
    } catch (e) { if (id === runId) { strip.fail(); pillText.textContent = "Search failed"; clear(results).append(errorState(e, run)); } } finally { results.setAttribute("aria-busy", "false"); results.classList.remove("refreshing"); }
  }
  function urlParams() { return { q: S.q, ranker: S.ranker === "ours" ? "" : S.ranker, prune: S.prune === "none" ? "" : S.prune, court: S.court.join(","), yf: S.yf > YMIN ? S.yf : "", yt: S.yt < YMAX ? S.yt : "", temporal: S.temporal ? "" : "0", ov: S.ov ? "1" : "", w: weights && defaultW && weights.some((x, i) => Math.abs(x - defaultW[i]) > 1e-6) ? weights.map((x) => x.toFixed(3)).join(",") : "" }; }
  function paintEmpty() { clear(results).append(h("div", { class: "card" }, emptyState("Choose a dev query to begin", "Type a dev query id above, press / to focus the search bar, or try a random dev query. Results show ids, courts, years and score components; case text stays hidden unless the server runs with SHOW_TEXT=1.", { icon: "search", action: button("Try a random query", { icon: "shuffle", onClick: () => random.click() }) }))); }

  // ---------------------------------------------------------------- ranking view (client-side re-weighting)
  function view() {
    const base = data.results.map((r) => ({ ...r }));
    base.forEach((r, i) => { r.rank0 = i + 1; });
    if (data.ranker === "ours" && weights) {
      const tot = weights.reduce((a, b) => a + b, 0) || 1;
      base.forEach((r) => { r.net = keys.reduce((s, k, i) => s + (weights[i] / tot) * (r.components[k] ?? 0), 0); });
      base.sort((a, b) => b.net - a.net || a.rank0 - b.rank0);
    } else { const top = base[0]?.score || 1; base.forEach((r) => { r.net = top ? r.score / top : 0; }); }
    base.forEach((r, i) => { r.rank = i + 1; });
    return base;
  }
  function saveSearch() {
    return async () => {
      try {
        const r = await post("/api/saved", { kind: "search", ref: S.q || "pasted", params: { ranker: S.ranker, pruning: S.prune, temporal_filter: S.temporal, k: 50, filters: requestBody(S).filters, ...(weights && defaultW && data.ranker === "ours" ? { weights: Object.fromEntries(keys.map((k, i) => [k, +weights[i].toFixed(3)])) } : {}) } });
        if (r.duplicate) return toast("That search is already saved.", "ok");
        toast("Search saved.", "ok", { action: { label: "Undo", run: async () => { try { await del(`/api/saved/${r.id}`); toast("Save undone.", ""); } catch (e) { toast(e.message, "err"); } } } });
      } catch (e) { toast(e.message, "err"); }
    };
  }
  function paint(before) {
    const v = view(), ghost = S.ov && data.results.some((r) => r.relevant !== undefined);
    clear(results); cards.clear();
    results.append(h("div", { class: "card tight row" },
      h("div", { class: "grow" }, h("b", {}, `${v.length} results`), h("span", { class: "muted small" }, ` · ${STRATEGIES.find((x) => x.value === strategyOf(data.ranker, data.temporal_applied || S.temporal))?.full || data.ranker} ${data.candidates_scored != null ? ` · ${data.candidates_scored} documents scored` : ""}${data.pruning && data.pruning !== "none" ? ` (${data.pruning} pruning)` : ""}`),
        data.temporal_applied ? badge("temporal filter on", "brand") : S.temporal && !data.query_has_date ? badge("pasted text has no date: filter skipped", "warn") : null, data.source === "toy" ? badge("toy data", "warn") : null),
      S.q ? h("label", { class: "switch", "data-tip": "Marks results that are in the dataset's labelled set for this dev query. Evaluation only; the ranker never sees it." }, h("input", { type: "checkbox", checked: S.ov, onChange: (e) => { S.ov = e.target.checked; run(); } }), "Evaluation overlay") : null,
      button("Save search", { variant: "secondary", size: "sm", icon: "bookmark", onClick: saveSearch() })));
    if (S.ov && overlay) results.append(h("div", { class: "overlay-box", role: "region", "aria-label": "Evaluation overlay" }, badge("Evaluation only", "ok"),
      h("span", {}, h("b", { class: "num" }, overlay.n_relevant), " labelled citations"), h("span", {}, "P@10 ", h("b", { class: "num" }, fmt(overlay["P@10"], 2))), h("span", {}, "R@10 ", h("b", { class: "num" }, fmt(overlay["R@10"], 2))), h("span", { "data-tip": overlay.note }, "AP@100 ", h("b", { class: "num" }, fmt(overlay["AP@100"], 3))),
      h("span", { class: "xs muted" }, `${overlay.relevant_in_top100} of ${overlay.n_relevant} are in the top 100. Uses the dataset's labels; never an input to ranking.`)));
    if (data.ranker === "ours" && weights) results.append(weightPanel());
    if (!v.length) { results.append(h("div", { class: "card" }, emptyState("No results with these filters", "Loosen the year range, court level or temporal filter.", { icon: "filter", action: button("Reset filters", { onClick: () => { S.court = []; S.yf = YMIN; S.yt = YMAX; S.temporal = false; navigate("/search", { ...urlParams(), temporal: "0", court: "", yf: "", yt: "" }); } }) }))); return; }
    const list = h("div", { class: "stack result-list", style: { gap: "var(--s-3)" } });
    results.append(list);
    v.slice(0, shown).forEach((r, i) => { const c = card(r, i, ghost); cards.set(r.doc_id, c); list.append(c); });
    if (v.length > shown) results.append(moreButton(v));
    playFlip(list, before || new Map());
  }
  const moreButton = (v) => button(`Show ${Math.min(10, v.length - shown)} more`, { variant: "secondary", onClick: (e) => { shown += 10; e.currentTarget.remove(); const list = results.querySelector(".result-list"); const before = snapshot(list); const vv = view(); vv.slice(shown - 10, shown).forEach((r, i) => { const c = card(r, shown - 10 + i, S.ov); cards.set(r.doc_id, c); list.append(c); }); if (vv.length > shown) results.append(moreButton(vv)); playFlip(list, before); } });

  function weightPanel() {
    const weightsOut = [];
    const tot = weights.reduce((a, b) => a + b, 0) || 1, changed = defaultW && weights.some((x, i) => Math.abs(x - defaultW[i]) > 1e-6);
    const sliders = keys.map((k, i) => { const out = h("output", { class: "num small", style: { minWidth: "44px", textAlign: "right" } }, `${((weights[i] / tot) * 100).toFixed(0)}%`);
      const inp = h("input", { type: "range", class: "range", min: 0, max: 1, step: 0.01, value: weights[i], "aria-label": `${FEATURE_LABEL[k]} weight`, onInput: (e) => { weights[i] = Math.max(0, +e.target.value); const t = weights.reduce((a, b) => a + b, 0) || 1; weightsOut.forEach((o, j) => { o.textContent = `${((weights[j] / t) * 100).toFixed(0)}%`; }); scheduleRepaint(); setUrlState("/search", urlParams()); } });
      weightsOut.push(out);
      return h("div", { class: "row", style: { flexWrap: "nowrap" } }, h("span", { class: "small", style: { width: "92px", display: "inline-flex", gap: "6px", alignItems: "center" } }, h("i", { class: "dot", style: { "--dc": `var(--f-${k})` } }), FEATURE_LABEL[k]), h("div", { class: "grow" }, inp), out); });
    const box = h("details", { class: "card tight disclose", open: changed || null }, h("summary", {}, "Re-weight the score (client side, instant)"), h("div", { class: "stack", style: { marginTop: "var(--s-3)" } }, h("p", { class: "xs muted" }, "Weights are non-negative and normalised. Moving a slider re-ranks the 50 returned results and the cards glide to their new places; nothing is sent to the server."), ...sliders,
      h("div", { class: "row" }, button("Reset to frozen weights", { variant: "secondary", size: "sm", icon: "shuffle", disabled: !changed, onClick: () => { weights = [...defaultW]; setUrlState("/search", urlParams()); const t = weights.reduce((a, b) => a + b, 0) || 1; sliders.forEach((row, j) => { row.querySelector("input").value = weights[j]; weightsOut[j].textContent = `${((weights[j] / t) * 100).toFixed(0)}%`; }); repaintCards(); } }), legend(keys))));
    return box;
  }
  let raf = 0;
  function scheduleRepaint() { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; repaintCards(); }); }
  /** Re-rank in place: existing cards are reused (rings and bars animate to their new values) and glide to their new rank. */
  function repaintCards() {
    const list = results.querySelector(".result-list");
    if (!list) return paint();
    const v = view(), before = snapshot(list);
    const keep = new Set(v.slice(0, shown).map((r) => r.doc_id));
    [...cards.keys()].forEach((k) => { if (!keep.has(k)) { cards.get(k).remove(); cards.delete(k); } });
    v.slice(0, shown).forEach((r, i) => { let c = cards.get(r.doc_id); if (c) c.update(r); else { c = card(r, i, S.ov); cards.set(r.doc_id, c); } list.append(c); });
    playFlip(list, before, { duration: 380 });
  }

  function whyContent(why, r) {
    const nbs = r.explanation?.neighbours || [];
    clear(why).append(h("div", { class: "small" }, h("b", {}, "How the score is made")), data.ranker === "ours" && weights ? h("div", { class: "stack", style: { gap: "6px" } }, keys.map((k, j) => { const t = weights.reduce((a, b) => a + b, 0) || 1; return h("div", { class: "hbar", style: { gridTemplateColumns: "92px 1fr 60px" } }, h("span", {}, FEATURE_LABEL[k]), h("div", { class: "track" }, h("div", { class: "fill", style: { "--hc": `var(--f-${k})`, transform: `scaleX(${(r.components[k] ?? 0)})` } })), h("span", { class: "num small", style: { textAlign: "right" } }, `${fmt(r.components[k], 2)} × ${((weights[j] / t) * 100).toFixed(0)}%`)); })) : h("p", { class: "small muted" }, "This ranker has a single text score; the other components belong to the Ours ranker."),
      nbs.length ? h("div", { class: "stack", style: { gap: "6px" } }, h("div", { class: "small muted" }, "Similar train cases that cite it (id and similarity)"), nbs.slice(0, 5).map((n) => h("div", { class: "hbar", style: { gridTemplateColumns: "110px 1fr 52px" } }, h("span", { class: "mono xs" }, n.neighbour_id), h("div", { class: "track" }, h("div", { class: "fill", style: { "--hc": "var(--f-neighbour)", transform: `scaleX(${n.similarity})` } })), h("span", { class: "num xs", style: { textAlign: "right" } }, fmt(n.similarity, 3))))) : h("p", { class: "small muted" }, "No similar train case cites this precedent."),
      (r.explanation?.shared_statutes || []).length ? h("div", { class: "row" }, h("span", { class: "small muted" }, "Shared statutes"), r.explanation.shared_statutes.map((s) => h("span", { class: "chip mono" }, s))) : h("span", { hidden: true }));
  }
  const parts = (r) => keys.map((k, j) => { const t = weights ? weights.reduce((a, b) => a + b, 0) || 1 : 1; return { key: k, value: (r.components[k] ?? 0) * ((weights ? weights[j] : 1) / t) }; });

  /** "Case record": metadata only (court, date, citation counts, paragraph counts per zone), plus a match profile while text is hidden. */
  async function recordContent(box, r) {
    clear(box).append(h("div", { class: "skel", style: { height: "60px" }, "aria-hidden": "true" }));
    try {
      const c = await get(`/api/case_detail/${encodeURIComponent(r.doc_id)}`);
      const sizes = Object.entries(c.zone_sizes || {}), mx = Math.max(...sizes.map(([, n]) => n), 1);
      const tot = keys.reduce((s, k, j) => s + (r.components[k] ?? 0) * ((weights ? weights[j] : 1)), 0) || 1;
      clear(box).append(
        h("div", { class: "rec-grid" }, [["Court", c.court || "?"], ["Date", c.date || c.year || "unknown"], ["Cited by (train queries)", c.train_indegree ?? "n/a"], ["Authority", c.authority == null ? "n/a" : fmt(c.authority, 2)], ["Cites inside the pool", c.cites_in_pool ?? "n/a"]].map(([l, v]) => h("div", { class: "rec-cell" }, h("div", { class: "xs muted" }, l), h("b", { class: "num" }, String(v))))),
        sizes.length ? h("div", { class: "stack", style: { gap: "4px" } }, h("div", { class: "small muted" }, "Paragraphs per zone (counts only)"), sizes.map(([z, n]) => h("div", { class: "hbar", style: { gridTemplateColumns: "120px 1fr 36px" } }, h("span", { class: "xs" }, zoneLabel(z)), h("div", { class: "track" }, h("div", { class: "fill", style: { "--hc": `var(--z-${z})`, transform: `scaleX(${(n / mx)})` } })), h("span", { class: "num xs", style: { textAlign: "right" } }, n)))) : null,
        !appSession.show_text ? h("div", { class: "match-profile" }, h("div", { class: "small" }, h("b", {}, "Match profile"), h("span", { class: "muted" }, " (case text is hidden, so this shows where the match comes from)")),
          h("div", { class: "row", style: { gap: "6px" } }, keys.map((k, j) => h("span", { class: "mp-chip", style: { "--mc": `var(--f-${k})` } }, h("i", {}), `${FEATURE_LABEL[k]} ${(((r.components[k] ?? 0) * (weights ? weights[j] : 1) / tot) * 100).toFixed(0)}%`)),
            h("span", { class: "mp-chip plain" }, `${(r.explanation?.neighbours || []).length} citing neighbours`), h("span", { class: "mp-chip plain" }, `${(r.explanation?.shared_statutes || []).length} shared statutes`))) : null);
    } catch (e) { clear(box).append(h("p", { class: "small muted" }, `The case record could not be loaded: ${e.message}`)); }
  }

  function card(r0, i, ghost) {
    let r = r0, recordLoaded = false;
    const isGold = ghost && r.relevant === true;
    const why = h("div", { class: "why", hidden: true, id: `why-${r.doc_id}` }), rec = h("div", { class: "why record", hidden: true, id: `rec-${r.doc_id}` });
    whyContent(why, r);
    const toggler = (label, panel, ic, onOpen) => { const b = h("button", { class: "chip-btn", type: "button", "aria-expanded": "false", "aria-controls": panel.id, onClick: () => { panel.hidden = !panel.hidden; b.setAttribute("aria-expanded", String(!panel.hidden)); if (!panel.hidden && onOpen) onOpen(); } }, icon(ic, { size: 14 }), label, icon("chevD", { size: 13 })); return b; };
    const whyBtn = toggler("Explain relevance score", why, "layers");
    const recBtn = toggler("Case record", rec, "database", () => { if (!recordLoaded) { recordLoaded = true; recordContent(rec, r); } });
    const rankNum = h("span", { class: "rank-num" }, r.rank), delta = h("small", { class: "rank-delta" });
    const paintDelta = () => { const d = r.rank0 - r.rank; delta.className = `rank-delta ${d > 0 ? "up" : d < 0 ? "down" : "same"}`; delta.textContent = d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : "·"; delta.setAttribute("aria-label", d ? `moved ${Math.abs(d)} ${d > 0 ? "up" : "down"}` : "unchanged"); };
    paintDelta();
    const ring = scoreRing(r.net, { color: "var(--brand)", label: "Relative score" });
    const sbar = data.ranker === "ours" ? stackBar(parts(r)) : null;
    let el;
    const open = () => { const rect = el.getBoundingClientRect(); openCaseDrawer({ docId: r.doc_id, results: view(), queryId: S.q, fromRect: rect, ranker: data.ranker, temporal: data.temporal_applied, weights: weightsObj(), onOpen: (id) => openCaseDrawer({ docId: id, results: view(), queryId: S.q, ranker: data.ranker, temporal: data.temporal_applied, weights: weightsObj() }) }); };
    const star = h("button", { class: "icon-btn star", type: "button", "aria-pressed": "false", "aria-label": "Save this case", title: "Save this case", onClick: async () => {
      try {
        if (saved.has(r.doc_id)) { const id = saved.get(r.doc_id); await del(`/api/saved/${id}`); saved.delete(r.doc_id); paintStar(); return toast(`Case ${r.doc_id} removed from Saved.`, ""); }
        const x = await post("/api/saved", { kind: "case", ref: r.doc_id, params: {} }); saved.set(r.doc_id, x.id); paintStar();
        toast(`Case ${r.doc_id} saved.`, "ok", { action: { label: "Undo", run: async () => { try { await del(`/api/saved/${x.id}`); saved.delete(r.doc_id); paintStar(); toast("Save undone.", ""); } catch (e2) { toast(e2.message, "err"); } } } });
      } catch (e2) { toast(e2.message, "err"); } } }, icon("star", { size: 18 }));
    const paintStar = () => { const on = saved.has(r.doc_id); star.setAttribute("aria-pressed", String(on)); star.title = on ? "Saved. Click to remove." : "Save this case"; star.setAttribute("aria-label", star.title); };
    paintStar();
    const pin = h("button", { class: "icon-btn pin", type: "button", "aria-pressed": "false", "aria-label": "Pin to compare", title: "Pin to compare (up to 4)", onClick: () => { if (pins.has(r.doc_id)) pins.delete(r.doc_id); else if (pins.size >= 4) return toast("You can pin up to 4 cases. Unpin one first.", "err"); else pins.set(r.doc_id, true); paintPin(); paintTray(); } }, icon("pin", { size: 18 }));
    const paintPin = () => { const on = pins.has(r.doc_id); pin.setAttribute("aria-pressed", String(on)); pin.title = on ? "Pinned. Click to unpin." : "Pin to compare (up to 4)"; pin.setAttribute("aria-label", pin.title); };
    paintPin();
    const rY = (r.meta?.date || "").slice(0, 4);
    el = h("article", { class: `result ${isGold ? "gold" : ""}`, "data-key": r.doc_id },
      h("div", { class: "rank" }, h("span", { class: "rank-badge" }, rankNum), delta),
      h("div", { class: "stack", style: { gap: "var(--s-2)", minWidth: 0 } },
        h("div", { class: "meta" }, h("button", { class: "id", type: "button", onClick: open, title: "Open the case drawer" }, r.doc_id), courtBadge(r.meta?.court), h("span", { class: "tag" }, rY || "year ?"),
          r.meta?.cited_by != null ? h("span", { class: "tag", "data-tip": "Train queries that cite this case (the in-degree behind the authority score)" }, `cited by ${r.meta.cited_by}`) : null,
          isGold ? h("span", { class: "badge gold", "data-tip": "In the dataset's labelled set for this dev query (evaluation only)" }, icon("check", { size: 12 }), "labelled citation") : null, r.title ? h("span", { class: "small" }, r.title) : null),
        r.snippet ? h("p", { class: "small muted" }, r.snippet) : null, sbar,
        h("div", { class: "row card-actions" }, whyBtn, recBtn, h("button", { class: "chip-btn spark", type: "button", title: "Explain this result (AI assistant): ids and scores only", onClick: () => explainResult(r, { queryId: S.q || "pasted", ranker: data.ranker, temporal: data.temporal_applied, weights: weightsObj() }) }, icon("spark", { size: 14 }), "Explain this result"), h("span", { class: "grow" }), pin, star),
        why, rec),
      h("div", { class: "ring-col stack", style: { alignItems: "center", gap: "var(--s-2)" } }, ring));
    el.paintStar = paintStar; el.paintPin = paintPin;
    el.update = (nr) => {
      const moved = nr.rank !== r.rank; r = nr;
      rankNum.textContent = r.rank; paintDelta(); ring.set(r.net); sbar && sbar.set(parts(r));
      if (!why.hidden) whyContent(why, r);
      if (moved && motionOK()) rankNum.animate([{ transform: "scale(1)" }, { transform: "scale(1.3)" }, { transform: "scale(1)" }], { duration: 320, easing: "ease-out" });
    };
    return el;
  }
  // pinned cases: a small tray with a side-by-side view
  function paintTray() {
    cards.forEach((c) => c.paintPin && c.paintPin());
    tray.hidden = pins.size === 0; clear(tray);
    if (!pins.size) return;
    tray.append(icon("pin", { size: 16 }), h("b", {}, `${pins.size} pinned`), h("span", { class: "muted xs mono" }, [...pins.keys()].join(", ")), h("span", { class: "grow" }),
      button("Compare pinned", { size: "sm", icon: "compare", disabled: pins.size < 2, title: pins.size < 2 ? "Pin at least two cases" : "", onClick: showPinned }), button("Clear", { variant: "ghost", size: "sm", onClick: () => { pins.clear(); paintTray(); } }));
  }
  function showPinned() {
    const v = view().filter((r) => pins.has(r.doc_id));
    const maxNet = Math.max(...v.map((r) => r.net), 0.001);
    modal({ title: "Pinned cases side by side", body: h("div", { class: "pin-compare", style: { "--n": v.length } }, v.map((r) => h("div", { class: "card flat tight stack", style: { gap: "var(--s-2)" } },
      h("div", { class: "row" }, h("b", { class: "mono" }, r.doc_id), courtBadge(r.meta?.court), h("span", { class: "muted xs" }, (r.meta?.date || "").slice(0, 4) || "year ?")),
      h("div", { class: "xs muted" }, `Rank ${r.rank}${r.meta?.cited_by != null ? ` · cited by ${r.meta.cited_by}` : ""}`),
      hbar("Relative score", r.net, maxNet, { color: "var(--brand)", text: fmt(r.net, 2) }),
      ...Object.entries(r.components).map(([k, val]) => hbar(FEATURE_LABEL[k] || k, val, 1, { color: `var(--f-${k})`, text: fmt(val, 2) })),
      (r.explanation?.shared_statutes || []).length ? h("div", { class: "row", style: { gap: "4px" } }, r.explanation.shared_statutes.map((s) => h("span", { class: "chip mono" }, s))) : null))) });
  }
  const weightsObj = () => (weights ? Object.fromEntries(keys.map((k, i) => [k, +(weights[i] / (weights.reduce((a, b) => a + b, 0) || 1)).toFixed(4)])) : undefined);

    if (S.q && (params.run || params.q)) run(); else paintEmpty();
}
