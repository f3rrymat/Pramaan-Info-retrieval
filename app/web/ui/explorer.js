// Trade-off explorer for the Efficiency page: a draggable operating point along the real measured points of one pruning method.
// Between two measured points the position is interpolated (straight line in log work against quality kept) for display only;
// the readout says "measured" when the point sits on a saved run and "interpolated" otherwise. All numbers come from results/efficiency.json.
import { h, svg, clear, fmt, pct } from "/ui/dom.js";

const nf = (v) => (v >= 100 ? Math.round(v).toLocaleString("en-US") : v.toFixed(1));

/**
 * rows: [{ method, x: candidates scored, y: MAP kept (0..1), y2: R@10 kept }] sorted by x, including the exhaustive endpoint (x = base, y = 1).
 * base: candidates scored by the exhaustive method. unit: "documents" or "train queries". sentence(): the generated takeaway for the method.
 */
export function tradeoffExplorer({ rows, base, unit, name, color = "var(--brand)", sentence }) {
  const pts = [...rows].sort((a, b) => a.x - b.x);
  const W = 720, H = 300, pad = { l: 52, r: 18, t: 16, b: 44 };
  const lx = pts.map((p) => Math.log10(Math.max(p.x, 1))), lo = Math.min(...lx) - 0.08, hi = Math.max(...lx) + 0.08;
  const X = (v) => pad.l + ((Math.log10(Math.max(v, 1)) - lo) / (hi - lo)) * (W - pad.l - pad.r), Y = (v) => pad.t + (1 - v) * (H - pad.t - pad.b);
  const g = svg("svg", { class: "chart explorer", viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": `Trade-off for ${name}` });
  [0, 0.25, 0.5, 0.75, 1].forEach((v) => g.append(svg("line", { class: "gridline", x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v) }), svg("text", { x: pad.l - 8, y: Y(v) + 4, "text-anchor": "end" }, `${Math.round(v * 100)}%`)));
  const decades = []; for (let d = Math.ceil(lo); d <= Math.floor(hi); d++) decades.push(d);
  decades.forEach((d) => g.append(svg("line", { class: "gridline", x1: X(10 ** d), x2: X(10 ** d), y1: pad.t, y2: H - pad.b }), svg("text", { x: X(10 ** d), y: H - pad.b + 16, "text-anchor": "middle" }, (10 ** d).toLocaleString("en-US"))));
  g.append(svg("text", { x: pad.l + (W - pad.l - pad.r) / 2, y: H - 6, "text-anchor": "middle" }, `${unit} scored per query (log scale)`), svg("text", { x: 14, y: pad.t + (H - pad.t - pad.b) / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${pad.t + (H - pad.t - pad.b) / 2})` }, "MAP kept vs exhaustive"));
  g.append(svg("path", { class: "ex-line", d: pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(""), fill: "none", stroke: color, "stroke-width": 2, "stroke-dasharray": "5 5", opacity: 0.7 }));
  pts.forEach((p) => g.append(svg("circle", { class: "ex-pt", cx: X(p.x), cy: Y(p.y), r: 5, fill: "var(--surface)", stroke: color, "stroke-width": 2.2 }, svg("title", {}, `${p.method}: ${nf(p.x)} ${unit}, ${pct(p.y, 0)} of MAP kept (measured)`))));
  const handle = svg("g", { class: "ex-handle", role: "slider", tabindex: "0", "aria-label": `Operating point for ${name}`, "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": 0 },
    svg("circle", { class: "ex-halo", r: 15, fill: color, opacity: 0.18 }), svg("circle", { class: "ex-dot", r: 8, fill: color, stroke: "var(--surface)", "stroke-width": 2.5 }));
  g.append(handle);
  const label = svg("text", { class: "ex-label", "text-anchor": "middle" }, ""); g.append(label);

  // position u in [0, 1] along the measured points (piecewise linear in index)
  const at = (u) => {
    const k = Math.min(pts.length - 1, u * (pts.length - 1)), i = Math.min(Math.floor(k), pts.length - 2), f = pts.length === 1 ? 0 : k - i, a = pts[Math.max(i, 0)], b = pts[Math.min(i + 1, pts.length - 1)];
    const lerp = (p, q) => p + (q - p) * f, lg = (p, q) => 10 ** (Math.log10(Math.max(p, 1)) * (1 - f) + Math.log10(Math.max(q, 1)) * f);
    return { x: lg(a.x, b.x), y: lerp(a.y, b.y), y2: lerp(a.y2 ?? a.y, b.y2 ?? b.y), a, b, f, measured: f < 0.02 ? a : f > 0.98 ? b : null };
  };
  const readX = h("b", { class: "num ex-big" }), readY = h("b", { class: "num ex-big" }), readR = h("b", { class: "num ex-big" }), state = h("span", { class: "badge" });
  const sent = h("p", { class: "ex-sentence", "aria-live": "polite" });
  const tile = (l, v, sub) => h("div", { class: "ex-tile" }, h("div", { class: "xs muted" }, l), v, sub);
  const subX = h("div", { class: "xs muted" }), subY = h("div", { class: "xs muted" });
  const range = h("input", { type: "range", class: "range ex-range", min: 0, max: 1000, step: 1, value: 1000, "aria-label": `Move along the measured ${name} settings` });
  let u = 1;
  const paint = () => {
    const p = at(u), cx = X(p.x), cy = Y(p.y);
    handle.setAttribute("transform", `translate(${cx.toFixed(1)} ${cy.toFixed(1)})`); handle.setAttribute("aria-valuenow", Math.round(p.y * 100)); handle.setAttribute("aria-valuetext", `${nf(p.x)} ${unit}, ${pct(p.y, 0)} of MAP kept, ${p.measured ? "measured" : "interpolated"}`);
    label.setAttribute("x", Math.min(Math.max(cx, pad.l + 70), W - pad.r - 70)); label.setAttribute("y", cy - 22); label.textContent = p.measured ? p.measured.method : "interpolated";
    readX.textContent = nf(p.x); readY.textContent = pct(p.y, 0); readR.textContent = pct(p.y2, 0);
    subX.textContent = `${pct(Math.max(0, 1 - p.x / base), 0)} fewer than exhaustive (${nf(base)})`; subY.textContent = "of the exhaustive MAP";
    state.className = `badge ${p.measured ? "ok" : "warn"}`; state.textContent = p.measured ? `Measured: ${p.measured.method}` : `Interpolated between ${p.a.method} and ${p.b.method} (display only)`;
    range.value = Math.round(u * 1000);
    clear(sent).append(`${p.measured ? "At the measured setting " + p.measured.method : "At this interpolated point"}, ${nf(p.x)} ${unit} are scored per query and ${pct(p.y, 0)} of MAP is kept (${pct(Math.max(0, 1 - p.x / base), 0)} less work than exhaustive). `, sentence ? sentence() : "");
  };
  const uFrom = (ev) => {
    const r = g.getBoundingClientRect(), px = ((ev.clientX - r.left) / r.width) * W, lv = lo + ((px - pad.l) / (W - pad.l - pad.r)) * (hi - lo);
    const xs = pts.map((q) => Math.log10(Math.max(q.x, 1)));
    if (lv <= xs[0]) return 0; if (lv >= xs[xs.length - 1]) return 1;
    let i = 0; while (i < xs.length - 2 && lv > xs[i + 1]) i++;
    return Math.min(1, Math.max(0, (i + (lv - xs[i]) / (xs[i + 1] - xs[i])) / (pts.length - 1)));
  };
  let dragging = false;
  handle.addEventListener("pointerdown", (e) => { dragging = true; handle.setPointerCapture(e.pointerId); e.preventDefault(); });
  handle.addEventListener("pointermove", (e) => { if (dragging) { u = uFrom(e); paint(); } });
  handle.addEventListener("pointerup", () => { dragging = false; });
  g.addEventListener("pointerdown", (e) => { if (!e.target.closest(".ex-handle")) { u = uFrom(e); paint(); dragging = true; handle.setPointerCapture?.(e.pointerId); } });
  handle.addEventListener("keydown", (e) => { const step = e.shiftKey ? 0.1 : 1 / (pts.length - 1); if (e.key === "ArrowRight" || e.key === "ArrowUp") u = Math.min(1, u + step); else if (e.key === "ArrowLeft" || e.key === "ArrowDown") u = Math.max(0, u - step); else if (e.key === "Home") u = 0; else if (e.key === "End") u = 1; else return; e.preventDefault(); paint(); });
  range.addEventListener("input", () => { u = +range.value / 1000; paint(); });
  const snap = h("div", { class: "row", style: { gap: "6px" } }, h("span", { class: "xs muted" }, "Jump to a measured setting:"), pts.map((p, i) => h("button", { type: "button", class: "chip", onClick: () => { u = pts.length > 1 ? i / (pts.length - 1) : 0; paint(); } }, p.method.replace(/^(champion lists|authority tiers|index elimination|cluster pruning)[ ,:]*/i, "") || p.method)));
  const el = h("div", { class: "stack" }, h("div", { class: "ex-readouts" }, tile(`${unit[0].toUpperCase() + unit.slice(1)} scored`, readX, subX), tile("MAP kept", readY, subY), tile("R@10 kept", readR, h("div", { class: "xs muted" }, "of the exhaustive R@10")), h("div", { class: "ex-tile" }, h("div", { class: "xs muted" }, "This point is"), state)),
    h("div", { class: "chart-host" }, g), range, snap, sent);
  paint();
  return { el };
}

/**
 * Replay of a saved crawl run: the saved curves (share of the most-cited documents found against fetch budget) drawn segment by segment with a
 * marker per series. The saved file stores only a handful of budgets, so the marker position between two budgets is interpolated for display.
 * series: [{ name, color, points: [[budget, share]] }]
 */
export function crawlReplay(series, { reduced = false } = {}) {
  const W = 720, H = 300, pad = { l: 52, r: 18, t: 16, b: 44 };
  const buds = series[0].points.map((p) => p[0]), b0 = Math.min(...buds), b1 = Math.max(...buds), ymax = Math.min(1, Math.max(...series.flatMap((s) => s.points.map((p) => p[1]))) * 1.1);
  const X = (v) => pad.l + ((v - b0) / (b1 - b0)) * (W - pad.l - pad.r), Y = (v) => pad.t + (1 - v / ymax) * (H - pad.t - pad.b);
  const g = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Replay of a saved crawl run" });
  for (let i = 0; i <= 4; i++) { const v = (ymax / 4) * i; g.append(svg("line", { class: "gridline", x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v) }), svg("text", { x: pad.l - 8, y: Y(v) + 4, "text-anchor": "end" }, `${Math.round(v * 100)}%`)); }
  buds.forEach((b) => g.append(svg("text", { x: X(b), y: H - pad.b + 16, "text-anchor": "middle" }, b)));
  g.append(svg("text", { x: pad.l + (W - pad.l - pad.r) / 2, y: H - 6, "text-anchor": "middle" }, "fetch budget (pages fetched)"));
  const segs = series.map((s) => s.points.slice(1).map((p, i) => { const a = s.points[i], el = svg("path", { class: "rp-seg", d: `M${X(a[0])},${Y(a[1])} L${X(p[0])},${Y(p[1])}`, fill: "none", stroke: s.color, "stroke-width": 2.6, "stroke-linecap": "round" }); g.append(el); return { el, end: p[0] }; }));
  const marks = series.map((s) => { const m = svg("circle", { class: "rp-mark", r: 6, fill: s.color, stroke: "var(--surface)", "stroke-width": 2, cx: 0, cy: 0 }); g.append(m); return m; });
  const interp = (s, b) => { const ps = s.points; if (b <= ps[0][0]) return ps[0][1]; for (let i = 1; i < ps.length; i++) if (b <= ps[i][0]) { const f = (b - ps[i - 1][0]) / (ps[i][0] - ps[i - 1][0]); return ps[i - 1][1] + (ps[i][1] - ps[i - 1][1]) * f; } return ps[ps.length - 1][1]; };
  const outs = series.map((s) => h("div", { class: "ex-tile" }, h("div", { class: "xs muted" }, h("i", { class: "dot", style: { "--dc": s.color } }), ` ${s.name}`), h("b", { class: "num ex-big" }, "0%")));
  const budget = h("b", { class: "num" }, String(b0));
  const range = h("input", { type: "range", class: "range", min: 0, max: 1000, value: 1000, "aria-label": "Replay position (fetch budget)" });
  let raf = 0;
  const show = (p) => {
    const b = b0 + p * (b1 - b0); budget.textContent = Math.round(b).toLocaleString("en-US"); range.value = Math.round(p * 1000);
    series.forEach((s, i) => { const v = interp(s, b); marks[i].setAttribute("transform", `translate(${X(b).toFixed(1)} ${Y(v).toFixed(1)})`); outs[i].lastChild.textContent = `${(v * 100).toFixed(1)}%`; segs[i].forEach((sg) => { sg.el.style.opacity = sg.end <= b + 1e-9 ? "1" : "0.12"; }); });
  };
  const play = () => { cancelAnimationFrame(raf); if (reduced) return show(1); const t0 = performance.now(), dur = 5200; const step = (t) => { const p = Math.min(1, (t - t0) / dur); show(p); if (p < 1) raf = requestAnimationFrame(step); }; raf = requestAnimationFrame(step); };
  range.addEventListener("input", () => { cancelAnimationFrame(raf); show(+range.value / 1000); });
  show(1);
  const replayBtn = h("button", { class: "btn secondary sm", type: "button", onClick: play }, "Replay");
  return { el: h("div", { class: "stack" }, h("div", { class: "row" }, h("span", { class: "badge info" }, "Replay of a saved run"), replayBtn, h("span", { class: "grow" }), h("span", { class: "small muted" }, "Budget "), budget), h("div", { class: "chart-host" }, g), range, h("div", { class: "ex-readouts" }, ...outs), h("p", { class: "xs muted" }, "The saved run stores the share found at a few budgets; between them the marker is interpolated for display only. Nothing is fetched: this is a simulation over the citation graph.")), play };
}
