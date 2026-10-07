// Rank replay for the Compare page: one scrubber moves every precedent from its rank under one ranker to its rank under the next.
// Positions are interpolated for display (transform only). Chips count promoted, demoted, unchanged and new entries for the segment in view.
import { h, clear, reducedMotion } from "/ui/dom.js";
import { icon } from "/ui/icons.js";

const ROW = 30, TOP = 12;
/** columns: ["tf-idf", "BM25 tuned", "Ours"]; docs: [{id, ranks: [r0, r1, r2] (null when outside the list), gold}] */
export function rankReplay({ columns, docs, onOpen }) {
  const items = docs.filter((d) => d.ranks.some((r) => r && r <= TOP));
  const n = columns.length, OUT = TOP + 2;
  const nodes = items.map((d) => h("div", { class: "rp-item", "data-id": d.id, tabindex: "0", role: "button", "aria-label": `Case ${d.id}`, onClick: () => onOpen && onOpen(d.id), onKeydown: (e) => { if (e.key === "Enter" && onOpen) onOpen(d.id); } },
    h("span", { class: "rp-rank num" }, ""), h("span", { class: "rp-id mono" }, d.id), d.gold ? h("span", { class: "rp-gold", "data-tip": "Labelled citation (evaluation only)" }, icon("check", { size: 12 })) : null, h("span", { class: "rp-note xs" }, "")));
  const stage = h("div", { class: "rp-stage", style: { height: `${TOP * ROW + 8}px` }, role: "list", "aria-label": "Precedents positioned by rank" }, nodes);
  const colLabel = h("div", { class: "rp-cols" }, columns.map((c, i) => h("button", { type: "button", class: "rp-col", onClick: () => { to(i); }, "aria-label": `Jump to ${c}` }, c)));
  const range = h("input", { type: "range", class: "range rp-range", min: 0, max: (n - 1) * 1000, value: 0, step: 1, "aria-label": "Replay position between rankers", "aria-valuetext": columns[0] });
  const chips = h("div", { class: "row rp-chips", "aria-live": "polite" });
  const playBtn = h("button", { class: "btn secondary sm", type: "button", onClick: () => (playing ? stop() : play()) }, icon("play", { size: 14 }), "Replay");
  let t = 0, playing = false, raf = 0, hl = null;
  const rk = (d, i) => (d.ranks[i] && d.ranks[i] <= TOP ? d.ranks[i] : null);
  function segmentStats(seg) {
    const a = seg, b = seg + 1, s = { promoted: [], demoted: [], same: [], fresh: [] };
    docs.forEach((d) => { const to = d.ranks[b], from = d.ranks[a]; if (!to || to > 10) return; if (!from) s.fresh.push(d.id); else if (to < from) s.promoted.push(d.id); else if (to > from) s.demoted.push(d.id); else s.same.push(d.id); });
    return s;
  }
  let shownSeg = -1;
  function paintChips(seg) {
    if (seg === shownSeg) return; shownSeg = seg;
    const s = segmentStats(seg);
    clear(chips).append(h("span", { class: "xs muted" }, `${columns[seg]} to ${columns[seg + 1]}, top 10:`),
      ...[["promoted", "▲", s.promoted, "ok"], ["demoted", "▼", s.demoted, "err"], ["unchanged", "=", s.same, ""], ["new in the top 10", "★", s.fresh, "info"]].map(([label, sym, ids, kind]) => h("button", { type: "button", class: `chip rp-chip ${kind}`, "aria-pressed": String(hl === label), onClick: () => { hl = hl === label ? null : label; shownSeg = -1; paintChips(seg); apply(); }, "data-ids": ids.join(",") }, `${sym} ${ids.length} ${label}`)));
    chips.__stats = s;
  }
  function apply() {
    const seg = Math.min(n - 2, Math.floor(t)), f = t - seg;
    const s = chips.__stats || segmentStats(seg);
    const want = hl ? { promoted: s.promoted, demoted: s.demoted, "unchanged": s.same, "new in the top 10": s.fresh }[hl] : null;
    items.forEach((d, i) => {
      const a = rk(d, seg) ?? OUT, b = rk(d, seg + 1) ?? OUT, pa = a === OUT ? b : a, pb = b === OUT ? a : b, y = (pa + (pb - pa) * f - 1) * ROW, vis = (a === OUT ? 0 : 1) * (1 - f) + (b === OUT ? 0 : 1) * f;
      const el = nodes[i];
      el.style.transform = `translateY(${y.toFixed(1)}px)`; el.style.opacity = String(want && !want.includes(d.id) ? Math.min(vis, 0.25) : vis); el.style.zIndex = String(1000 - Math.round(y));
      el.querySelector(".rp-rank").textContent = vis > 0.05 ? String(Math.round(pa + (pb - pa) * f)) : "";
      const mv = (d.ranks[seg + 1] ?? 99) - (d.ranks[seg] ?? 99);
      const note = el.querySelector(".rp-note"); note.textContent = f > 0.02 && a !== OUT && b !== OUT ? (b < a ? `▲${a - b}` : b > a ? `▼${b - a}` : "=") : f > 0.02 && a === OUT && b !== OUT ? "new" : "";
      note.className = `rp-note xs ${b < a ? "up" : b > a ? "down" : ""}`;
      void mv;
    });
    const near = Math.round(t); range.setAttribute("aria-valuetext", columns[near]);
    [...colLabel.children].forEach((c, i) => c.classList.toggle("on", i === near));
  }
  function set(v) { t = Math.max(0, Math.min(n - 1, v)); range.value = Math.round(t * 1000); paintChips(Math.min(n - 2, Math.floor(t + (t >= n - 1 ? -1e-6 : 0)))); apply(); }
  function to(i) { stop(); animateTo(i); }
  function animateTo(target, dur = 700) { if (reducedMotion()) return set(target); const from = t, t0 = performance.now(); cancelAnimationFrame(raf); const step = (now) => { const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3); set(from + (target - from) * e); if (k < 1) raf = requestAnimationFrame(step); }; raf = requestAnimationFrame(step); }
  function play() { playing = true; clear(playBtn).append(icon("pause", { size: 14 }), "Pause"); if (reducedMotion()) { set(n - 1); stop(); return; } const from = t >= n - 1 ? 0 : t, t0 = performance.now(), dur = (n - 1 - from) * 1800 + 200; const step = (now) => { const k = Math.min(1, (now - t0) / dur); set(from + (n - 1 - from) * k); if (k < 1 && playing) raf = requestAnimationFrame(step); else stop(); }; cancelAnimationFrame(raf); raf = requestAnimationFrame(step); }
  function stop() { playing = false; cancelAnimationFrame(raf); clear(playBtn).append(icon("play", { size: 14 }), "Replay"); }
  range.addEventListener("input", () => { stop(); set(+range.value / 1000); });
  set(0);
  return { el: h("div", { class: "stack rp" }, h("div", { class: "row" }, playBtn, h("span", { class: "grow" }), colLabel), stage, range, chips, h("p", { class: "xs muted" }, "Drag the slider or press Replay. Rows are the precedents in the top 12 of at least one ranker; positions between two rankers are interpolated for display. Green ticks are labelled citations (evaluation overlay)."))
    , destroy() { stop(); } };
}
