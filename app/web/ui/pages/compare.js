// Compare view: tf-idf, tuned BM25 and ours for the same query, side by side, with a rank-slope chart and the dev gold overlay.
import { h, clear, fmt, debounce } from "/ui/dom.js";
import { alertBox, badge, button, combobox, courtBadge, emptyState, errorState, pageHead, skeletonCards, table, toast } from "/ui/components.js";
import { get, post } from "/ui/api.js";
import { setUrlState, navigate } from "/ui/store.js";
import { slope } from "/ui/charts.js";
import { rankReplay } from "/ui/replay.js";
import { openCaseDrawer } from "/ui/casedrawer.js";

const RANKERS = [["tfidf", "tf-idf", "var(--f-court)"], ["bm25", "BM25 tuned", "var(--f-authority)"], ["ours", "Ours (Config A)", "var(--f-text)"]];

export default async function compare({ container, params, setCrumb, onCleanup }) {
  const S = { q: params.q || "", temporal: params.temporal !== "0", gold: params.gold === "1", focus: params.focus || "" };
  container.append(pageHead("Compare rankers", "The same dev query under three rankers. Lines in the slope chart follow each precedent from one ranker to the next; green dots are labelled citations (evaluation only)."));
  const body = h("div", { class: "stack" }, skeletonCards(1)); container.append(body);
  let qs, meta;
  try { [qs, meta] = await Promise.all([get("/api/queries"), get("/api/query_meta").catch(() => ({ items: {} }))]); } catch (e) { clear(body).append(errorState(e)); return; }
  const items = qs.queries.map((q) => { const m = meta.items[q.qid] || {}; return { value: q.qid, label: q.qid, meta: `${m.court || "?"} · ${m.year || "?"}`, node: () => [h("span", { class: "mono" }, q.qid), courtBadge(m.court), h("span", { class: "muted xs" }, m.year || "year ?")] }; });
  const picker = combobox({ items, value: S.q, placeholder: "Dev query id…", label: "Dev query", onSelect: (it) => { S.q = it.value; run(); } }); picker.setAttribute("data-focus-search", "");
  const rand = button("Random", { variant: "secondary", icon: "shuffle", onClick: () => { const it = items[Math.floor(Math.random() * items.length)]; picker.setValue(it.value); S.q = it.value; run(); } });
  const temporal = h("label", { class: "switch" }, h("input", { type: "checkbox", checked: S.temporal, onChange: (e) => { S.temporal = e.target.checked; run(); } }), "Temporal filter");
  const gold = h("label", { class: "switch", "data-tip": "Marks the dataset's labelled citations for this dev query. Evaluation only." }, h("input", { type: "checkbox", checked: S.gold, onChange: (e) => { S.gold = e.target.checked; run(); } }), "Evaluation overlay");
  clear(body).append(h("div", { class: "card row" }, h("div", { style: { minWidth: "260px", flex: "1 1 260px" } }, picker), rand, temporal, gold), h("div", { id: "cmp-out", class: "stack", "aria-live": "polite" }));
  const out = body.querySelector("#cmp-out");
  let token = 0, replayRef = null;
  onCleanup(() => replayRef && replayRef.destroy());

  async function run() {
    if (!S.q) { clear(out).append(h("div", { class: "card" }, emptyState("Choose a dev query", "Pick one above or press / to focus the picker.", { icon: "compare", action: button("Random query", { onClick: () => rand.click() }) }))); return; }
    const id = ++token; setUrlState("/compare", { q: S.q, temporal: S.temporal ? "" : "0", gold: S.gold ? "1" : "", focus: S.focus }); setCrumb(S.q);
    clear(out).append(skeletonCards(2));
    try {
      const filters = {}, base = { query_id: S.q, k: 50, temporal_filter: S.temporal, filters };
      const res = await Promise.all(RANKERS.map(([r]) => post("/api/search", { ...base, ranker: r })));
      const ov = S.gold ? await Promise.all(RANKERS.map(([r]) => post("/api/overlay", { query_id: S.q, ranker: r, temporal_filter: S.temporal, filters }).catch(() => null))) : null;
      if (id !== token) return;
      paint(res, ov);
      post("/api/history", { kind: "search", ref: S.q, params: { view: "compare", temporal_filter: S.temporal } }).catch(() => {});
    } catch (e) { if (id === token) clear(out).append(errorState(e, run)); }
  }

  function paint(res, ov) {
    const rankOf = res.map((r) => Object.fromEntries(r.results.map((x, i) => [x.doc_id, i + 1])));
    const goldIds = new Set(res[2].results.filter((x) => x.relevant).map((x) => x.doc_id).concat(res[0].results.filter((x) => x.relevant).map((x) => x.doc_id), res[1].results.filter((x) => x.relevant).map((x) => x.doc_id)));
    const maxRank = 20, ids = [...new Set([...res[2].results.slice(0, 15), ...res[0].results.slice(0, 8), ...res[1].results.slice(0, 8)].map((x) => x.doc_id))];
    const rows = ids.map((d) => ({ id: d, ranks: rankOf.map((m) => (m[d] && m[d] <= maxRank ? m[d] : null)), color: "var(--f-text)", gold: S.gold && goldIds.has(d) })).filter((r) => r.ranks.some(Boolean));
    rows.forEach((r, i) => { const t = r.ranks.filter(Boolean); r.color = `hsl(${(i * 47) % 360} 55% 48%)`; });
    clear(out);
    if (ov) out.append(h("div", { class: "overlay-box" }, badge("Evaluation only", "ok"), ...ov.map((o, i) => o ? h("span", {}, RANKERS[i][1] + ": ", h("b", { class: "num" }, `P@10 ${fmt(o["P@10"], 2)} · R@10 ${fmt(o["R@10"], 2)} · AP@100 ${fmt(o["AP@100"], 3)}`)) : null), h("span", { class: "xs muted" }, `${ov[0]?.n_relevant ?? "?"} labelled citations; labels are never used for ranking.`)));
    const cols = h("div", { class: "grid cols-3" }, RANKERS.map(([r, label, col], i) => h("section", { class: "card tight stack" }, h("div", { class: "row" }, h("h3", {}, label), h("span", { class: "spacer" }), h("span", { class: "xs muted" }, `${res[i].candidates_scored} scored`)),
      h("ol", { style: { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "4px" } }, res[i].results.slice(0, 10).map((x, j) => h("li", { class: "row", style: { gap: "8px", padding: "4px 6px", borderRadius: "var(--r-sm)", background: S.gold && x.relevant ? "var(--ok-soft)" : "transparent" }, "data-id": x.doc_id },
        h("span", { class: "num muted", style: { width: "22px" } }, j + 1), h("button", { class: "id", type: "button", style: { fontFamily: "var(--mono)", background: "none", border: 0, cursor: "pointer", color: "inherit", textDecoration: "underline", textDecorationColor: "var(--border-strong)" }, onClick: () => openCaseDrawer({ docId: x.doc_id, results: res[i].results, queryId: S.q, onOpen: (d) => openCaseDrawer({ docId: d, results: res[i].results, queryId: S.q }) }) }, x.doc_id), courtBadge(x.meta?.court), h("span", { class: "xs muted" }, (x.meta?.date || "").slice(0, 4)), S.gold && x.relevant ? badge("labelled", "gold") : null))))));
    out.append(cols);
    const replay = rankReplay({ columns: RANKERS.map((r) => r[1]), docs: ids.map((d) => ({ id: d, ranks: rankOf.map((m) => m[d] || null), gold: S.gold && goldIds.has(d) })), onOpen: (docId) => openCaseDrawer({ docId, results: res[2].results, queryId: S.q, ranker: "ours", temporal: res[2].temporal_applied, onOpen: (x) => openCaseDrawer({ docId: x, results: res[2].results, queryId: S.q }) }) });
    replayRef = replay;
    out.append(h("section", { class: "tile accent stack" }, h("h2", {}, "Replay the re-ranking"), replay.el));
    const climbers = ids.map((d) => ({ d, from: rankOf[0][d], to: rankOf[2][d] })).filter((x) => x.to && x.to <= 10 && (!x.from || x.from > x.to)).sort((a, b) => (b.from || 99) - (a.from || 99)).slice(0, 5);
    const hover = h("div", { class: "small muted" }, "Hover a line to follow one precedent.");
    out.append(h("section", { class: "card stack" }, h("div", { class: "row" }, h("h3", {}, "Rank movement"), h("span", { class: "spacer" }), h("span", { class: "xs muted" }, `Ranks 1 to ${maxRank}; precedents outside the top ${maxRank} of a ranker have no dot there`)),
      slope(RANKERS.map((r) => r[1]), rows, { maxRank, width: 640, onHover: (id) => { clear(hover).append(id ? `${id}: ${rankOf.map((m, i) => `${RANKERS[i][1]} ${m[id] ? "#" + m[id] : "not in the top 50"}`).join("  ·  ")}` : "Hover a line to follow one precedent."); } }), hover,
      climbers.length ? h("div", { class: "small" }, h("b", {}, "Biggest climbers from tf-idf to ours: "), climbers.map((c) => h("span", { class: "chip mono", style: { marginRight: "6px" } }, `${c.d} ${c.from ? "#" + c.from : "out"} → #${c.to}`))) : h("div", { class: "small muted" }, "No precedent entered the top 10 of the ours ranker from outside the tf-idf top 10 for this query.")));
    if (S.focus) { const li = out.querySelector(`li[data-id="${CSS.escape(S.focus)}"]`); li && li.scrollIntoView({ block: "center" }); }
  }
  run();
}
