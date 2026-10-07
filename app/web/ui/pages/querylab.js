// Query Lab: syntax-highlighted query box, operator examples, visual parse tree, suggestions, and the same result card as Search.
import { h, clear, fmt, debounce } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { alertBox, badge, button, chip, courtBadge, emptyState, errorState, pageHead, scoreRing, segmented, skeletonCards, toast } from "/ui/components.js";
import { post } from "/ui/api.js";
import { setUrlState } from "/ui/store.js";
import { openCaseDrawer } from "/ui/casedrawer.js";

const EXAMPLES = [["AND", "murder AND knife"], ["OR", "bail OR parole"], ["NOT", "murder AND NOT dowry"], ["Phrase", '"burden of proof"'], ["Proximity /k", "murder /3 knife"], ["Ordered pre/k", "knife pre/3 murder"],
  ["Zone", "facts:murder"], ["Wildcard", "murd*"], ["Suffix wildcard", "*tion"], ["Court filter", "murder court:SC"], ["Year range", "murder year:1990..2005"], ["Date filter", "murder before:2000-01-01"], ["Spelling", "mudrer"]];
const TOKEN = /("[^"]*")|(\(|\))|(pre\/\d+|\/\d+)|([A-Za-z_]+:(?:"[^"]*"|[^\s()"]+))|(\bAND\b|\bOR\b|\bNOT\b)|([^\s()"]*\*[^\s()"]*)|(\s+)|([^\s()"]+)/g;

export function highlight(q) {
  const out = [];
  q.replace(TOKEN, (m, phrase, paren, prox, field, op, wild, space, word) => {
    out.push(phrase ? h("span", { class: "tok-phrase" }, m) : paren ? h("span", { class: "tok-paren" }, m) : prox ? h("span", { class: "tok-prox" }, m) : field ? h("span", { class: "tok-field" }, m) : op ? h("span", { class: "tok-op" }, m) : wild ? h("span", { class: "tok-wild" }, m) : m);
    return m;
  });
  return out;
}
function tree(n) {
  const lab = n.op === "FILTER" ? [h("span", { class: "pnode op" }, "FILTER"), h("span", { class: "pnode" }, `${n.name} = ${n.value}`)] : n.value !== undefined ? [h("span", { class: "pnode" }, n.op === "PHRASE" ? "“" + n.value + "”" : n.value, n.zone ? h("span", { class: "zone-chip", style: { "--zc": `var(--z-${n.zone})` } }, n.zone) : null, n.wildcard ? badge("wildcard", "info") : null), h("span", { class: "xs muted" }, n.op === "PHRASE" ? "phrase" : "term")] : [h("span", { class: "pnode op" }, n.op)];
  return h("li", {}, h("span", { class: "row", style: { gap: "6px", display: "inline-flex" } }, lab), n.children ? h("ul", {}, n.children.map(tree)) : null);
}

export default async function querylab({ container, params, setCrumb }) {
  let strategy = "df_order";
  container.append(pageHead("Query Lab", "Boolean, phrase, proximity, zone, wildcard and filter queries over the index. Phrase and proximity search the facts and issues zones only, because positions are kept for those two."));
  const input = h("textarea", { class: "textarea", rows: 1, spellcheck: "false", "aria-label": "Query", "aria-describedby": "ql-hint", placeholder: 'e.g. murder /3 knife court:SC', value: params.q || "" });
  const pre = h("pre", { "aria-hidden": "true" });
  const box = h("div", { class: "codebox" }, pre, input);
  const sync = () => { clear(pre); highlight(input.value).forEach((n) => pre.append(n)); pre.append("\n"); input.style.height = "auto"; input.style.height = `${Math.max(48, input.scrollHeight)}px`; pre.style.height = input.style.height; };
  const run = button("Run query", { icon: "play", onClick: () => runQuery() });
  const strat = segmented([{ value: "df_order", label: "Smallest list first" }, { value: "input_order", label: "As written" }], strategy, (v) => { strategy = v; runQuery(); }, { label: "AND processing order" });
  const filterRow = h("div", { class: "row" }, h("span", { class: "label" }, "Add filter"),
    ...[["court:SC", "Supreme Court"], ["court:HC", "High Court"], ["year:2000..2010", "Years 2000–2010"], ["before:2000-01-01", "Before 2000"], ["after:2010-01-01", "After 2010"]].map(([t, l]) => chip(l, { onClick: () => { input.value = `${input.value.trim()} ${t}`.trim(); sync(); parseNow(); input.focus(); } })));
  const examples = h("div", { class: "row", style: { gap: "6px" } }, EXAMPLES.map(([l, q]) => chip(`${l}: ${q}`, { mono: true, onClick: () => { input.value = q; sync(); runQuery(); } })));
  const parsed = h("div", { class: "card stack" }), results = h("div", { class: "card stack", "aria-live": "polite" });
  container.append(h("div", { class: "card stack" }, h("div", { class: "row", style: { flexWrap: "nowrap", alignItems: "stretch" } }, h("div", { class: "grow" }, box), run), h("div", { id: "ql-hint", class: "xs muted" }, "Enter runs the query; Shift+Enter adds a line. Operators: AND OR NOT ( ) \"phrase\" /k pre/k zone:term term* court: year: before: after:"), h("div", { class: "row" }, h("span", { class: "label" }, "AND order"), strat), filterRow, h("div", { class: "label" }, "Examples"), examples),
    h("div", { class: "grid cols-2", style: { alignItems: "start" } }, parsed, results));
  const ro = [parsed, results];
  const emptyParse = () => clear(parsed).append(h("h3", {}, "Parsed query"), emptyState("Nothing to parse yet", "Type a query or click an example. The tree shows how the operators group.", { icon: "code" }));
  emptyParse(); clear(results).append(h("h3", {}, "Results"), emptyState("No query run yet", "Results show ids, courts, years and scores. Case text stays hidden unless the server runs with SHOW_TEXT=1.", { icon: "search" }));

  async function parseNow() {
    const q = input.value.trim(); if (!q) return emptyParse();
    try {
      const p = await post("/api/parse", { q });
      clear(parsed).append(h("h3", {}, "Parsed query"));
      if (!p.ok) { parsed.append(alertBox(`Syntax: ${p.error}`, "warn", "alert")); }
      else {
        parsed.append(h("ul", { class: "ptree" }, tree(p.parsed)));
        if (p.statutes.length) parsed.append(h("div", { class: "row" }, h("span", { class: "small muted" }, "Statute tokens"), p.statutes.map((s) => h("span", { class: "chip mono" }, s))));
        if (p.suggestions.length) parsed.append(h("div", { class: "stack" }, h("div", { class: "label" }, "Suggestions"), p.suggestions.map((s) => h("div", { class: "row", style: { gap: "6px" } }, h("span", { class: "small" }, h("b", {}, s.word), ` (${{ none: "known word", spelling: "spelling", wildcard: "wildcard" }[s.kind] || s.kind})`),
          (s.items || []).map((i) => chip(`${i.term || i}${i.edit_distance != null ? ` d=${i.edit_distance}` : ""}`, { mono: true, onClick: () => { input.value = input.value.split(s.word).join(i.term || i); sync(); runQuery(); } })),
          (s.soundex || []).length ? [h("span", { class: "xs muted" }, "sounds like"), s.soundex.map((t) => chip(t, { mono: true }))] : null))));
      }
    } catch (e) { clear(parsed).append(errorState(e)); }
  }
  async function runQuery() {
    const q = input.value.trim(); if (!q) return toast("Type a query first.", "err");
    setUrlState("/querylab", { q }); setCrumb(q.length > 24 ? q.slice(0, 23) + "…" : q);
    clear(results).append(h("h3", {}, "Results"), skeletonCards(2)); parseNow();
    try {
      const r = await post("/api/query/run", { q, k: 20, strategy });
      clear(results).append(h("h3", {}, "Results"));
      if (!r.ok) return results.append(alertBox(`Syntax: ${r.error}`, "warn", "alert"));
      results.append(h("div", { class: "row small" }, h("b", { class: "num" }, r.n_matches), " matching documents", h("span", { class: "muted" }, `· ${r.and_comparisons} posting comparisons (${r.strategy === "df_order" ? "smallest list first" : "as written"}) · ${r.mode} data`)),
        h("details", { class: "disclose" }, h("summary", {}, "How it was evaluated"), h("ol", { class: "small muted", style: { margin: "6px 0", paddingLeft: "1.2rem" } }, r.trace.map((t) => h("li", {}, t)))), h("p", { class: "xs muted" }, r.note));
      if (!r.results.length) return results.append(emptyState("No documents match", "Loosen the query: drop a term, widen a proximity window, or use a wildcard.", { icon: "search" }));
      const top = r.results[0].score || 1;
      r.results.forEach((x, i) => results.append(h("article", { class: "result", style: { animationDelay: `${Math.min(i, 8) * 25}ms`, boxShadow: "none" } }, h("div", { class: "rank" }, i + 1),
        h("div", { class: "stack", style: { gap: "4px" } }, h("div", { class: "meta" }, h("button", { class: "id", type: "button", onClick: () => openCaseDrawer({ docId: x.doc_id, results: [] }) }, x.doc_id), courtBadge(x.court), h("span", { class: "muted small" }, (x.date || "").slice(0, 4) || "year ?"), x.title ? h("span", { class: "small" }, x.title) : null), x.snippet ? h("p", { class: "small muted" }, x.snippet) : null),
        h("div", { class: "ring-col" }, scoreRing(x.score / top, { label: "Relative tf-idf score" })))));
    } catch (e) { clear(results).append(h("h3", {}, "Results"), errorState(e, runQuery)); }
  }
  const dp = debounce(parseNow, 450);
  input.addEventListener("input", () => { sync(); dp(); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runQuery(); } });
  sync();
  if (params.q) runQuery();
}
