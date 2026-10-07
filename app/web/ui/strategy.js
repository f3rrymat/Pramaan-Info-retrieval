// Segmented strategy switcher with a gliding thumb. Offers only rankers that exist: tf-idf (lnc.ltc), BM25 (tuned), Ours, Ours + temporal filter,
// and Boolean query (which opens Query Lab; it returns a set, not a ranking, so no MAP). Tooltips show dev and test MAP read from results/.
import { h, fmt } from "/ui/dom.js";

export const STRATEGIES = [
  { value: "tfidf", label: "tf-idf", full: "tf-idf (lnc.ltc)", key: "tfidf", ranker: "tfidf", temporal: false },
  { value: "bm25", label: "BM25", full: "BM25 (tuned)", key: "bm25", ranker: "bm25", temporal: false },
  { value: "ours", label: "Ours", full: "Ours (Config A)", key: "config_a", ranker: "ours", temporal: false },
  { value: "ours_t", label: "Ours + temporal", full: "Ours + temporal filter", key: "config_a_tf", ranker: "ours", temporal: true },
  { value: "boolean", label: "Boolean", full: "Boolean query", key: null, ranker: null, temporal: false },
];
/** Which segment a (ranker, temporal) pair lights up. */
export const strategyOf = (ranker, temporal) => (ranker === "ours" ? (temporal ? "ours_t" : "ours") : ranker);

export function strategySwitch({ value, rows = {}, onChange }) {
  const tipOf = (s) => {
    if (!s.key) return `${s.full}: returns the set of documents that satisfy the expression, not a ranking, so no MAP is reported. Opens Query Lab.`;
    const r = rows[s.key];
    if (!r) return `${s.full}: no saved MAP on this machine.`;
    const dev = r.dev?.MAP, test = r.test?.MAP;
    return `${s.full}. MAP on dev ${dev != null ? fmt(dev, 3) : "n/a"}${test != null ? `, on test ${fmt(test, 3)}` : ""}.`;
  };
  const thumb = h("span", { class: "strat-thumb", "aria-hidden": "true" });
  const btns = STRATEGIES.map((s) => h("button", { type: "button", role: "radio", class: "strat-opt", "data-v": s.value, "aria-checked": "false", tabindex: "-1", "data-tip": tipOf(s), "aria-label": tipOf(s), onClick: () => choose(s.value, true) }, s.label));
  const el = h("div", { class: "strat", role: "radiogroup", "aria-label": "Ranking strategy" }, thumb, btns);
  let cur = value;
  function place() {
    const i = Math.max(0, STRATEGIES.findIndex((s) => s.value === cur)), b = btns[i];
    if (!b || !b.offsetWidth) return;
    el.style.setProperty("--tw", `${b.offsetWidth}px`);
    thumb.style.transform = `translateX(${b.offsetLeft}px)`;
    btns.forEach((x, j) => { x.setAttribute("aria-checked", String(j === i)); x.tabIndex = j === i ? 0 : -1; });
  }
  function choose(v, fire) { cur = v; place(); if (fire) onChange(v); }
  el.addEventListener("keydown", (e) => {
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (!(e.key in keys)) return;
    e.preventDefault();
    const i = STRATEGIES.findIndex((s) => s.value === cur), n = (i + keys[e.key] + STRATEGIES.length) % STRATEGIES.length;
    choose(STRATEGIES[n].value, true); btns[n].focus();
  });
  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => { thumb.style.transition = "none"; place(); requestAnimationFrame(() => { thumb.style.transition = ""; }); }) : null;
  ro && ro.observe(el);
  requestAnimationFrame(() => { thumb.style.transition = "none"; place(); requestAnimationFrame(() => { thumb.style.transition = ""; }); });
  return { el, set(v) { choose(v, false); }, destroy() { ro && ro.disconnect(); } };
}
