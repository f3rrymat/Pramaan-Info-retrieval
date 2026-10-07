// Interactive SVG charts for the Evaluation dashboard. Geometry is always the true geometry (widths are attributes, so PNG export is exact);
// animation is transform-only (a scaleX from the old width to the new one) and is skipped when motion is reduced.
import { h, svg, fmt } from "/ui/dom.js";
import { motionOK } from "/ui/motion.js";

const EASE = "cubic-bezier(.2, .7, .2, 1)";
/** Set a bar's width attribute and glide from the old width (transform only). */
export function setBarWidth(rect, w, { duration = 600, delay = 0 } = {}) {
  const old = rect.width.baseVal.value;
  rect.setAttribute("width", Math.max(w, 0.0001));
  if (!motionOK() || !(w > 0)) return;
  const from = old > 0 ? old / w : 0;
  if (Math.abs(from - 1) < 0.002) return;
  rect.animate([{ transform: `scaleX(${from})` }, { transform: "scaleX(1)" }], { duration, delay, easing: EASE, fill: "backwards" });
}

/** A tooltip that follows the pointer inside `host` (a positioned element). */
export function tooltip(host) {
  const tip = h("div", { class: "chart-tip", role: "status", hidden: true });
  host.append(tip);
  return {
    show(html, ev) {
      tip.replaceChildren(...html); tip.hidden = false;
      const r = host.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
      const w = tip.offsetWidth, flip = x + w + 24 > r.width;
      tip.style.left = `${Math.max(4, flip ? x - w - 14 : x + 14)}px`; tip.style.top = `${Math.max(4, y - 10)}px`;
    },
    hide() { tip.hidden = true; },
  };
}

/**
 * Grouped horizontal bars: one group per system, one bar per metric. systems: [{name, values: {key: v}, ci?: [lo, hi] for MAP}]
 * metrics: [{key, label, color}]. update(systems, metrics, max) glides every bar to its new width.
 */
export function groupedBars(systems, metrics, { max = 1, left = 230, width = 760, tip, onHover, caption = "" } = {}) {
  const barH = 11, gap = 3, pad = 12, rowH = metrics.length * (barH + gap) + pad, Ht = systems.length * rowH + 30;
  const x = (v, m) => (v / m) * (width - left - 56);
  const g = svg("svg", { class: "chart gbars", viewBox: `0 0 ${width} ${Ht}`, role: "img", "aria-label": `Grouped bars: ${metrics.map((m) => m.label).join(", ")} for ${systems.length} systems` });
  const grid = svg("g", {}); g.append(grid);
  const groups = systems.map((s, i) => {
    const y0 = 24 + i * rowH;
    const bars = metrics.map((m, j) => svg("rect", { class: "bar gb", x: left, y: y0 + j * (barH + gap), width: 0.0001, height: barH, rx: 3, fill: m.color, "data-metric": m.key }));
    const vals = metrics.map((m, j) => svg("text", { class: "gb-val", x: left + 4, y: y0 + j * (barH + gap) + barH - 2 }, ""));
    const wh = svg("g", { class: "gb-whisker" }, svg("line", { class: "whisker" }), svg("line", { class: "whisker cap-l" }), svg("line", { class: "whisker cap-r" }));
    const label = svg("text", { class: "series-label", x: left - 10, y: y0 + (metrics.length * (barH + gap)) / 2 + 3, "text-anchor": "end" }, s.name.length > 38 ? s.name.slice(0, 37) + "…" : s.name);
    const grp = svg("g", { class: "gb-group", "data-series": s.name, tabindex: "0", "aria-label": `${s.name}: ${metrics.map((m) => `${m.label} ${fmt(s.values[m.key], 3)}`).join(", ")}` }, svg("rect", { class: "gb-hit", x: 0, y: y0 - pad / 2, width, height: rowH, fill: "transparent" }), label, bars, vals, wh);
    const show = (ev) => { if (tip) tip.show([h("b", {}, s.name), ...metrics.map((m) => h("div", { class: "tip-row" }, h("i", { style: { background: m.color } }), `${m.label} `, h("b", { class: "num" }, fmt(cur.systems[i].values[m.key], 4)))),
      cur.systems[i].ci ? h("div", { class: "xs" }, `MAP 95% interval of the difference to tf-idf: [${fmt(cur.systems[i].ci[0], 3)}, ${fmt(cur.systems[i].ci[1], 3)}]`) : null].filter(Boolean), ev); onHover && onHover(s.name); };
    grp.addEventListener("pointermove", show); grp.addEventListener("pointerleave", () => { tip && tip.hide(); onHover && onHover(null); });
    grp.addEventListener("focus", () => { const r = grp.getBoundingClientRect(); show({ clientX: r.left + 160, clientY: r.top + 6 }); }); grp.addEventListener("blur", () => { tip && tip.hide(); });
    g.append(grp);
    return { grp, bars, vals, wh, y0 };
  });
  const cur = { systems, metrics, max };
  function update(sys, mets, mx, { animate = true } = {}) {
    cur.systems = sys; cur.metrics = mets; cur.max = mx;
    grid.replaceChildren();
    const step = mx > 0.6 ? 0.2 : mx > 0.3 ? 0.1 : 0.05;
    for (let t = 0; t <= mx + 1e-9; t += step) grid.append(svg("line", { class: "gridline", x1: left + x(t, mx), x2: left + x(t, mx), y1: 16, y2: Ht - 6 }), svg("text", { x: left + x(t, mx), y: 11, "text-anchor": "middle" }, +t.toFixed(2)));
    groups.forEach((gr, i) => {
      const s = sys[i];
      gr.bars.forEach((b, j) => { const m = mets[j]; b.setAttribute("fill", m.color); b.setAttribute("data-metric", m.key); const v = s.values[m.key] ?? 0; if (animate) setBarWidth(b, Math.max(x(v, mx), 1), { delay: i * 25 }); else b.setAttribute("width", Math.max(x(v, mx), 1)); });
      gr.vals.forEach((t, j) => { const m = mets[j], v = s.values[m.key] ?? 0; t.setAttribute("x", left + x(v, mx) + 5); t.textContent = fmt(v, 3); });
      const last = mets.length - 1;                                       // the MAP bar is last; whisker only when an interval exists
      const wh = gr.wh, mapV = s.values[mets[last].key] ?? 0, y = gr.y0 + last * (barH + gap) + barH / 2;
      if (s.ci) {
        const [lo, hi] = [mapV + s.ci[0], mapV + s.ci[1]], [a, b2, c] = wh.children;
        a.setAttribute("x1", left + x(lo, mx)); a.setAttribute("x2", left + x(hi, mx)); a.setAttribute("y1", y); a.setAttribute("y2", y);
        b2.setAttribute("x1", left + x(lo, mx)); b2.setAttribute("x2", left + x(lo, mx)); b2.setAttribute("y1", y - 4); b2.setAttribute("y2", y + 4);
        c.setAttribute("x1", left + x(hi, mx)); c.setAttribute("x2", left + x(hi, mx)); c.setAttribute("y1", y - 4); c.setAttribute("y2", y + 4);
        wh.style.opacity = "1";
        gr.vals[last].setAttribute("x", left + x(Math.max(hi, mapV), mx) + 6);
      } else wh.style.opacity = "0";
      gr.grp.setAttribute("aria-label", `${s.name}: ${mets.map((m) => `${m.label} ${fmt(s.values[m.key], 3)}`).join(", ")}`);
    });
  }
  update(systems, metrics, max, { animate: false });
  requestAnimationFrame(() => update(systems, metrics, max));       // entrance: bars grow from zero
  groups.forEach((gr) => gr.bars.forEach((b) => b.setAttribute("width", 0.0001)));
  return { el: g, update };
}

/** Ladder chart for the story-mode stepper. steps: [{label, MAP, ci?}] -> {el, setStep(i)}; bars after step i are collapsed. */
export function ladderChart(steps, { width = 760, left = 220, rowH = 40, max } = {}) {
  const mx = max ?? Math.max(...steps.map((s) => s.MAP + (s.ci ? Math.max(s.ci[1], 0) : 0))) * 1.12, x = (v) => (v / mx) * (width - left - 70), Ht = steps.length * rowH + 20;
  const g = svg("svg", { class: "chart ladder-chart", viewBox: `0 0 ${width} ${Ht}`, role: "img", "aria-label": "Ablation ladder: MAP after each step" });
  const rows = steps.map((s, i) => {
    const y = 10 + i * rowH;
    const bar = svg("rect", { class: "bar lad", x: left, y, width: x(s.MAP), height: 20, rx: 4, fill: "var(--brand)" });
    const wh = s.ci ? svg("g", { class: "lad-wh" }, svg("line", { class: "whisker", x1: left + x(s.MAP + s.ci[0]), x2: left + x(s.MAP + s.ci[1]), y1: y + 10, y2: y + 10 }), svg("line", { class: "whisker", x1: left + x(s.MAP + s.ci[0]), x2: left + x(s.MAP + s.ci[0]), y1: y + 5, y2: y + 15 }), svg("line", { class: "whisker", x1: left + x(s.MAP + s.ci[1]), x2: left + x(s.MAP + s.ci[1]), y1: y + 5, y2: y + 15 })) : null;
    const val = svg("text", { class: "lad-val", x: left + x(Math.max(s.MAP + (s.ci ? s.ci[1] : 0), s.MAP)) + 8, y: y + 15 }, fmt(s.MAP, 3));
    const delta = i ? svg("text", { class: `lad-delta ${s.delta >= 0.003 ? "up" : s.delta <= -0.003 ? "down" : ""}`, x: left + x(Math.max(s.MAP + (s.ci ? s.ci[1] : 0), s.MAP)) + 52, y: y + 15 }, `${s.delta >= 0 ? "+" : "−"}${Math.abs(s.delta).toFixed(3)}`) : null;
    const lab = svg("text", { class: "series-label", x: left - 10, y: y + 15, "text-anchor": "end" }, s.label);
    const row = svg("g", { class: "lad-row off", "data-series": s.label }, lab, bar, wh, val, delta);
    g.append(row);
    return row;
  });
  return { el: g, setStep(i) { rows.forEach((r, j) => { r.classList.toggle("off", j > i); r.classList.toggle("cur", j === i); }); } };
}

/** PR curve with a hover crosshair. series: [{name, color, points: [[recall, precision]]}] */
export function prChart(series, { width = 760, height = 320, tip } = {}) {
  const pad = { l: 52, r: 16, t: 14, b: 40 }, iw = width - pad.l - pad.r, ih = height - pad.t - pad.b;
  const ymax = Math.max(0.05, ...series.flatMap((s) => s.points.map((p) => p[1]))) * 1.08;
  const X = (v) => pad.l + v * iw, Y = (v) => pad.t + ih - (v / ymax) * ih;
  const g = svg("svg", { class: "chart pr-chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Interpolated precision against recall" });
  for (let i = 0; i <= 5; i++) { const v = (ymax / 5) * i; g.append(svg("line", { class: "gridline", x1: pad.l, x2: width - pad.r, y1: Y(v), y2: Y(v) }), svg("text", { x: pad.l - 8, y: Y(v) + 4, "text-anchor": "end" }, v.toFixed(2))); }
  for (let i = 0; i <= 10; i += 2) g.append(svg("text", { x: X(i / 10), y: height - pad.b + 16, "text-anchor": "middle" }, (i / 10).toFixed(1)));
  g.append(svg("text", { x: pad.l + iw / 2, y: height - 6, "text-anchor": "middle" }, "recall"), svg("text", { x: 14, y: pad.t + ih / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${pad.t + ih / 2})` }, "interpolated precision"));
  const paths = series.map((s) => { const p = svg("path", { class: "pr-line draw", d: s.points.map((q, i) => `${i ? "L" : "M"}${X(q[0]).toFixed(1)},${Y(q[1]).toFixed(1)}`).join(""), fill: "none", stroke: s.color, "stroke-width": 2.4, "stroke-linejoin": "round", "data-series": s.name, pathLength: 1 }); g.append(p); return p; });
  const cross = svg("line", { class: "crosshair", y1: pad.t, y2: pad.t + ih, x1: 0, x2: 0, style: "opacity:0" });
  const dots = series.map((s) => svg("circle", { class: "pr-dot", r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 1.5, style: "opacity:0" }));
  g.append(cross, ...dots);
  const move = (ev) => {
    const r = g.getBoundingClientRect(), px = ((ev.clientX - r.left) / r.width) * width, k = Math.max(0, Math.min(10, Math.round(((px - pad.l) / iw) * 10)));
    const xx = X(k / 10); cross.setAttribute("x1", xx); cross.setAttribute("x2", xx); cross.style.opacity = "1";
    series.forEach((s, i) => { dots[i].setAttribute("cx", xx); dots[i].setAttribute("cy", Y(s.points[k][1])); dots[i].style.opacity = "1"; });
    tip && tip.show([h("b", {}, `Recall ${(k / 10).toFixed(1)}`), ...series.map((s) => h("div", { class: "tip-row" }, h("i", { style: { background: s.color } }), `${s.name.length > 30 ? s.name.slice(0, 29) + "…" : s.name} `, h("b", { class: "num" }, fmt(s.points[k][1], 3))))], ev);
  };
  const leave = () => { cross.style.opacity = "0"; dots.forEach((d) => { d.style.opacity = "0"; }); tip && tip.hide(); };
  g.addEventListener("pointermove", move); g.addEventListener("pointerleave", leave);
  g.setAttribute("tabindex", "0");
  g.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); const r = g.getBoundingClientRect(); const cur = +(cross.getAttribute("x1") || pad.l); const k = Math.max(0, Math.min(10, Math.round(((cur - pad.l) / iw) * 10) + (e.key === "ArrowRight" ? 1 : -1))); move({ clientX: r.left + (X(k / 10) / width) * r.width, clientY: r.top + 20 }); } });
  g.addEventListener("blur", leave);
  return { el: g };
}

/** Animated before/after bars for the leakage audit. items: [{label, before, after, tone: "bad"|"good", ci?, note}] */
export function beforeAfter(items, { width = 760, left = 270, rowH = 44 } = {}) {
  const mx = Math.max(...items.flatMap((i) => [i.before, i.after])) * 1.1, x = (v) => (v / mx) * (width - left - 90), Ht = items.length * rowH + 14;
  const g = svg("svg", { class: "chart ba-chart", viewBox: `0 0 ${width} ${Ht}`, role: "img", "aria-label": "Leakage audit: MAP before and after the change" });
  const rows = items.map((it, i) => {
    const y = 8 + i * rowH;
    const base = svg("rect", { class: "bar", x: left, y, width: Math.max(x(it.before), 1), height: 22, rx: 4, fill: "var(--bar-muted)" });
    const over = svg("rect", { class: "bar ba-over", x: left, y, width: Math.max(x(it.after), 1), height: 22, rx: 4, fill: it.tone === "good" ? "var(--ok)" : "var(--err)", "data-tone": it.tone });
    const val = svg("text", { class: "lad-val", x: left + x(it.before) + 8, y: y + 16 }, fmt(it.before, 3));
    const lab = svg("text", { class: "series-label", x: left - 10, y: y + 16, "text-anchor": "end", "data-series": it.label }, it.label.length > 44 ? it.label.slice(0, 43) + "…" : it.label);
    g.append(svg("g", { "data-series": it.label }, lab, base, over, val));
    return { it, base, over, val, y };
  });
  let state = "before";
  function tween(node, a, b, ms) {
    const my = (node.__tok = (node.__tok || 0) + 1);
    if (!motionOK()) { node.textContent = fmt(b, 3); return; }
    const t0 = performance.now(); const step = (t) => { if (my !== node.__tok) return; const k = Math.min(1, (t - t0) / ms); node.textContent = fmt(a + (b - a) * (1 - Math.pow(1 - k, 3)), 3); if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step);
  }
  function set(next, { animate = true } = {}) {
    state = next;
    rows.forEach((r, i) => {
      const to = next === "after" ? r.it.after : r.it.before, from = next === "after" ? r.it.before : r.it.after;
      if (next === "after") { r.over.style.opacity = "1"; if (animate && motionOK()) r.over.animate([{ transform: `scaleX(${Math.max(x(r.it.before), 1) / Math.max(x(r.it.after), 1)})` }, { transform: "scaleX(1)" }], { duration: 700, delay: i * 40, easing: EASE, fill: "backwards" }); r.val.setAttribute("x", left + x(Math.max(r.it.after, r.it.before)) + 8); }
      else { r.over.style.opacity = "0"; r.val.setAttribute("x", left + x(r.it.before) + 8); }
      if (animate) tween(r.val, from, to, 700); else r.val.textContent = fmt(to, 3);
    });
  }
  set("before", { animate: false });
  return { el: g, set, get state() { return state; } };
}
