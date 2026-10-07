// Hero search bar: one field for a dev query id or pasted facts, with grouped, keyboard-navigable suggestions from real sources only:
// recent searches (history), saved searches, dev query ids (GET /api/queries), index terms and did-you-mean (GET /api/suggest).
// The field grows into a multi-line box when case facts are pasted. Pasted text is never put in the URL and is not stored.
import { h, clear, debounce } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { courtBadge } from "/ui/components.js";
import { get } from "/ui/api.js";
import { navigate } from "/ui/store.js";
import { MOD } from "/ui/shell.js";
import * as AS from "/ui/assistant/state.js";
import { openPanel } from "/ui/assistant/panel.js";

const LONG = 100;                                              // characters after which the field is treated as pasted facts
const GROUPS = ["Recent searches", "Saved searches", "Dev queries", "Index terms", "Did you mean"];

/** items: [{ value, meta, court, year }] dev queries. onQuery(id) runs a dev query; onText(text) runs pasted facts. */
export function searchBar({ items, value = "", onQuery, onText, onRandom }) {
  let sugg = [], sel = -1, open = false, seq = 0, mic = null, cache = { hist: null, saved: null };
  const input = h("textarea", { class: "qbar-input", rows: 1, placeholder: "Dev query id, or paste the facts and issues of a case", "aria-label": "Search: dev query id or pasted facts", "aria-autocomplete": "list", "aria-controls": "qbar-pop", "aria-expanded": "false", role: "combobox", spellcheck: "false", autocomplete: "off", "data-focus-search": "" });
  input.value = value;
  const clearBtn = h("button", { class: "qbar-icon", type: "button", "aria-label": "Clear the search", title: "Clear", hidden: !value, onClick: () => { input.value = ""; grow(); input.focus(); refresh(); } }, icon("x", { size: 16 }));
  const hint = h("kbd", { class: "qbar-kbd", "aria-hidden": "true", title: "Command palette" }, `${MOD} K`);
  const micSlot = h("span", { class: "qbar-micslot" });
  const go = h("button", { class: "btn qbar-go", type: "button", onClick: () => submit() }, "Search");
  const note = h("div", { class: "qbar-note xs muted", hidden: true }, "Pasted text is sent to the server for this search only. It is not stored and not put in the URL. Press ", h("kbd", {}, `${MOD} Enter`), " to search.");
  const pop = h("div", { class: "qbar-pop", id: "qbar-pop", role: "listbox", hidden: true, "aria-label": "Suggestions" });
  const field = h("div", { class: "qbar-field" }, h("span", { class: "qbar-lead", "aria-hidden": "true" }, icon("search", { size: 20 })), input, clearBtn, micSlot, hint, go);
  const el = h("div", { class: "qbar", role: "search" }, field, note, pop);

  const isFacts = () => /\n/.test(input.value) || input.value.length > LONG;
  function grow() {
    input.style.height = "auto";
    const max = 9 * 24 + 8;
    input.style.height = `${Math.min(input.scrollHeight, max)}px`;
    const facts = isFacts();
    el.classList.toggle("facts", facts); note.hidden = !facts; hint.hidden = facts || !!input.value; clearBtn.hidden = !input.value;
    go.textContent = facts ? "Search pasted text" : "Search";
  }
  const exact = () => items.find((x) => x.value === input.value.trim());
  function submit(choice) {
    if (choice) return pick(choice);
    const v = input.value.trim();
    if (!v) return input.focus();
    if (isFacts()) { close(); return onText(input.value); }
    const hit = exact();
    if (hit) { close(); return onQuery(hit.value); }
    if (/^\d+$/.test(v)) { close(); return onQuery(v); }                          // an id the picker does not list: the server answers 404 with a clear message
    const first = sugg.find((s) => s.kind === "query" || s.kind === "history" || s.kind === "saved");
    if (first && first.value.includes(v)) return pick(first);
    if (/^[A-Za-z][\w-]*$/.test(v)) return navigate("/querylab", { q: v });     // a single word is an index term: Boolean search
    close(); onText(input.value);
  }
  function pick(s) {
    close();
    if (s.kind === "query" || s.kind === "history" || s.kind === "saved") { input.value = s.value; grow(); onQuery(s.value); }
    else if (s.kind === "term" || s.kind === "dym") navigate("/querylab", { q: s.value });
  }

  async function fill() {
    const mine = ++seq, v = input.value.trim(), low = v.toLowerCase(), out = [];
    if (isFacts()) { sugg = []; return paint(); }
    try { cache.hist = cache.hist || (await get("/api/history?limit=30")).items; } catch (_) { cache.hist = cache.hist || []; }
    try { cache.saved = cache.saved || (await get("/api/saved")).items; } catch (_) { cache.saved = cache.saved || []; }
    if (mine !== seq) return;
    const seen = new Set(), match = (ref) => ref && ref !== "pasted" && (!low || ref.toLowerCase().includes(low));
    cache.hist.filter((i) => match(i.ref) && !seen.has(i.ref) && seen.add(i.ref)).slice(0, 4).forEach((i) => out.push({ kind: "history", group: GROUPS[0], value: i.ref, label: i.ref, meta: "recent" }));
    const seenS = new Set();
    (cache.saved || []).filter((i) => i.kind === "search" && match(i.ref) && !seenS.has(i.ref) && seenS.add(i.ref)).slice(0, 3).forEach((i) => out.push({ kind: "saved", group: GROUPS[1], value: i.ref, label: i.ref, meta: `saved${i.params?.ranker ? ` · ${i.params.ranker}` : ""}` }));
    const dev = items.filter((x) => !low || x.value.includes(low)).slice(0, low ? 6 : 4);
    dev.forEach((x) => out.push({ kind: "query", group: GROUPS[2], value: x.value, label: x.value, court: x.court, year: x.year }));
    sugg = out.filter((x, i, a) => x.kind !== "query" || !a.some((y, j) => j < i && y.value === x.value && y.kind !== "query"));
    paint();
    if (/^[A-Za-z][A-Za-z-]{2,}$/.test(v)) {
      try {
        const [w, d] = await Promise.all([get(`/api/suggest?term=${encodeURIComponent(v.toLowerCase() + "*")}`).catch(() => null), get(`/api/suggest?term=${encodeURIComponent(v.toLowerCase())}`).catch(() => null)]);
        if (mine !== seq) return;
        (w?.items || []).slice(0, 4).forEach((t) => sugg.push({ kind: "term", group: GROUPS[3], value: t, label: t, meta: "opens Query Lab" }));
        (d?.kind === "spelling" ? d.items : []).slice(0, 3).forEach((t) => sugg.push({ kind: "dym", group: GROUPS[4], value: t, label: t, meta: "opens Query Lab" }));
        paint();
      } catch (_) { /* index terms are optional */ }
    }
  }
  const refresh = debounce(() => { fill(); }, 120);
  function paint() {
    clear(pop);
    if (!open) { pop.hidden = true; input.setAttribute("aria-expanded", "false"); return; }
    if (!sugg.length) { pop.hidden = !input.value.trim() || isFacts(); if (!pop.hidden) pop.append(h("div", { class: "qbar-empty small muted" }, "No saved search or dev query id matches. Press Enter to search anyway.")); input.setAttribute("aria-expanded", String(!pop.hidden)); return; }
    pop.hidden = false; input.setAttribute("aria-expanded", "true");
    const q = input.value.trim().toLowerCase();
    let last = null;
    sugg.forEach((s, i) => {
      if (s.group !== last) { pop.append(h("div", { class: "qbar-group", role: "presentation" }, s.group)); last = s.group; }
      const label = q && s.label.toLowerCase().includes(q) ? (() => { const k = s.label.toLowerCase().indexOf(q); return [s.label.slice(0, k), h("mark", {}, s.label.slice(k, k + q.length)), s.label.slice(k + q.length)]; })() : s.label;
      pop.append(h("div", { class: "qbar-item", role: "option", id: `sb-${i}`, "aria-selected": String(i === sel), onMousedown: (e) => { e.preventDefault(); submit(s); }, onMousemove: () => { if (sel !== i) { sel = i; mark(); } } },
        icon(s.kind === "history" ? "clock" : s.kind === "saved" ? "bookmark" : s.kind === "query" ? "search" : "code", { size: 15 }), h("span", { class: s.kind === "term" || s.kind === "dym" ? "" : "mono" }, label),
        s.court ? courtBadge(s.court) : null, s.year ? h("span", { class: "muted xs" }, s.year) : null, s.meta ? h("span", { class: "muted xs qbar-meta" }, s.meta) : null));
    });
    input.setAttribute("aria-activedescendant", sel >= 0 ? `sb-${sel}` : "");
  }
  function mark() { pop.querySelectorAll(".qbar-item").forEach((n, j) => n.setAttribute("aria-selected", String(j === sel))); input.setAttribute("aria-activedescendant", sel >= 0 ? `sb-${sel}` : ""); pop.querySelector(`#sb-${sel}`)?.scrollIntoView({ block: "nearest" }); }
  const close = () => { open = false; sel = -1; paint(); };

  input.addEventListener("input", () => { grow(); open = true; sel = -1; refresh(); });
  input.addEventListener("paste", () => setTimeout(() => { grow(); open = false; paint(); }, 0));
  input.addEventListener("focus", () => { open = !isFacts(); fill(); });
  input.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== input) close(); }, 120));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { if (!sugg.length) return; e.preventDefault(); open = true; sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + sugg.length) % sugg.length; paint(); mark(); }
    else if (e.key === "Enter") {
      if (isFacts()) { if (e.ctrlKey || e.metaKey) { e.preventDefault(); submit(); } return; }
      if (e.shiftKey) return;
      e.preventDefault(); submit(sel >= 0 ? sugg[sel] : undefined);
    } else if (e.key === "Escape") { if (open) { e.preventDefault(); e.stopPropagation(); close(); } else if (input.value) { input.value = ""; grow(); } }
  });
  document.addEventListener("history:changed", () => { cache = { hist: null, saved: null }; });

  // the microphone appears only when the assistant is configured and the visitor already consented; it opens the assistant panel
  AS.status().then((s) => { if (s?.configured && AS.consented()) { mic = h("button", { class: "qbar-icon", type: "button", "aria-label": "Ask the AI assistant by voice", title: "Ask the AI assistant (opens the assistant panel; your pasted text is never sent to it)", onClick: () => openPanel() }, icon("mic", { size: 18 })); micSlot.append(mic); } }).catch(() => {});

  grow(); requestAnimationFrame(grow);
  return {
    el, input,
    setValue(v) { input.value = v || ""; grow(); },
    focus() { input.focus(); },
    invalidate() { cache = { hist: null, saved: null }; },
  };
}
