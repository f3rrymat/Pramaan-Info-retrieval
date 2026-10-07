// Case detail drawer: counts and numbers only; titles and 200-character snippets appear only when the server runs with SHOW_TEXT=1.
import { h, clear, fmt } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { ZONES, button, courtBadge, drawer, errorState, hbar, skeleton, stackBar, legend, toast, zoneLabel, FEATURE_LABEL } from "/ui/components.js";
import { get, post, del } from "/ui/api.js";
import { neighbourGraph } from "/ui/charts.js";
import { navigate } from "/ui/store.js";
import { morph } from "/ui/motion.js";
import { explainResult } from "/ui/assistant/panel.js";

export function openCaseDrawer({ docId, results = [], queryId, params = {}, onOpen, fromRect, ranker, temporal, weights }) {
  const body = h("div", { class: "stack" }, skeleton("60%", "20px"), skeleton("100%", "90px"), skeleton("100%", "140px"));
  const saveBtn = button("Save", { variant: "secondary", size: "sm", icon: "bookmark", onClick: async () => {
    try {
      const r = await post("/api/saved", { kind: "case", ref: docId, params: {} });
      if (r.duplicate) return toast("Already saved.", "ok");
      toast(`Case ${docId} saved.`, "ok", { action: { label: "Undo", run: async () => { try { await del(`/api/saved/${r.id}`); toast("Save undone.", ""); } catch (e) { toast(e.message, "err"); } } } });
    } catch (e) { toast(e.message, "err"); } } });
  const cmpBtn = button("Compare rankers", { variant: "secondary", size: "sm", icon: "compare", onClick: () => { d.close(); navigate("/compare", { q: queryId, focus: docId }); } });
  const mine = results.find((r) => r.doc_id === docId);
  const explainBtn = mine ? button("Explain", { variant: "secondary", size: "sm", icon: "spark", title: "Explain this result (AI assistant)", onClick: () => { d.close(); explainResult(mine, { queryId, ranker, temporal, weights }); } }) : null;
  const d = drawer({ title: `Case ${docId}`, body, actions: h("div", { class: "row", style: { gap: "6px" } }, explainBtn, saveBtn, queryId ? cmpBtn : null) });
  if (fromRect) morph(fromRect, d.el);
  (async () => {
    try {
      const c = await get(`/api/case_detail/${encodeURIComponent(docId)}`);
      clear(body);
      body.append(h("div", { class: "row" }, h("span", { class: "mono", style: { fontWeight: 650 } }, c.doc_id), courtBadge(c.court), h("span", { class: "muted" }, c.year || "year unknown"), c.source === "toy" ? h("span", { class: "badge warn" }, "toy data") : null));
      if (c.title) body.append(h("div", {}, h("div", { class: "label" }, "Title (SHOW_TEXT=1)"), h("div", {}, c.title), c.snippet && h("p", { class: "small muted" }, c.snippet)));
      body.append(h("div", { class: "grid cols-2" },
        stat("Authority", c.authority == null ? "–" : fmt(c.authority, 3), "log(1 + in-degree), pool and train edges"), stat("Train in-degree", c.train_indegree ?? "–", "train queries that cite it"),
        stat("Pool + train in-degree", c.pool_plus_train_indegree ?? "–", "all citing pages used for authority"), stat("Cites inside the pool", c.cites_in_pool, "outgoing citations to pool cases")));
      if (mine) {
        const keys = Object.keys(mine.components);
        body.append(h("section", { class: "stack" }, h("h3", {}, "Why it ranks here"), stackBar(keys.map((k) => ({ key: k, value: (mine.explanation?.contributions?.[k]) ?? mine.components[k] }))), legend(keys),
          h("div", { class: "stack", style: { gap: "6px" } }, Object.entries(mine.explanation?.contributions || mine.components).map(([k, v]) => hbar(FEATURE_LABEL[k] || k, v, 1, { color: `var(--f-${k})`, text: fmt(v, 3) })))));
        const nbs = mine.explanation?.neighbours || [];
        body.append(h("section", { class: "stack" }, h("h3", {}, "Similar train cases that cite it"), nbs.length ? h("div", { class: "stack", style: { gap: "6px" } }, nbs.slice(0, 8).map((n) => hbar(n.neighbour_id, n.similarity, 1, { color: "var(--f-neighbour)", text: fmt(n.similarity, 3) }))) : h("p", { class: "small muted" }, "No train case among the nearest neighbours cites this precedent; it ranks on text and authority."),
          (mine.explanation?.shared_statutes || []).length ? h("div", { class: "row" }, h("span", { class: "small muted" }, "Shared statutes"), mine.explanation.shared_statutes.map((s) => h("span", { class: "chip mono" }, s))) : null));
      }
      const sizes = Object.entries(c.zone_sizes || {});
      if (sizes.length) {
        const mx = Math.max(...sizes.map(([, n]) => n), 1);
        body.append(h("section", { class: "stack" }, h("h3", {}, "Paragraphs per zone"), h("p", { class: "small muted" }, "Counts only. The zone colours are the same everywhere in the app."), h("div", { class: "stack", style: { gap: "6px" } }, sizes.sort((a, b) => ZONES.indexOf(a[0]) - ZONES.indexOf(b[0])).map(([z, n]) => hbar(zoneLabel(z), n, mx, { color: `var(--z-${z})`, text: String(n) })))));
      }
      if (mine && results.length > 1) {
        const top = results.slice(0, 8), seen = new Map(), edges = [];
        top.forEach((r) => (r.explanation?.neighbours || []).forEach((n) => { if (!seen.has(n.neighbour_id)) seen.set(n.neighbour_id, n.similarity); edges.push([n.neighbour_id, r.doc_id]); }));
        const ids = new Set(top.map((r) => r.doc_id)); if (!ids.has(docId)) top.push(mine);
        const neigh = [...seen.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([id, sim]) => ({ id, sim }));
        body.append(h("section", { class: "stack" }, h("h3", {}, "Citation neighbourhood"), h("p", { class: "small muted" }, "Hover or focus a node to see its connections. Click a candidate to open it."),
          neighbourGraph({ queryId: queryId || "query", neighbours: neigh, candidates: top.map((r) => ({ id: r.doc_id })), edges, selected: docId, onSelect: (id) => { d.close(); onOpen && onOpen(id); } })));
      }
    } catch (e) { clear(body).append(errorState(e)); }
  })();
  return d;
}
const stat = (l, v, hint) => h("div", { class: "card flat tight kpi" }, h("div", { class: "l" }, l), h("div", { class: "v", style: { fontSize: "var(--t-xl)" } }, String(v)), h("div", { class: "xs muted" }, hint));
