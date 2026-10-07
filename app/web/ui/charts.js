// Hand-written SVG charts. All colours come from tokens, so every chart follows the theme.
import { h, svg, fmt, reducedMotion } from "/ui/dom.js";

const W = 760;
function axisX(g, x, ticks, y, fmtTick = (t) => t) { ticks.forEach((t) => { g.append(svg("line", { class: "gridline", x1: x(t), x2: x(t), y1: 6, y2: y }), svg("text", { x: x(t), y: y + 14, "text-anchor": "middle" }, fmtTick(t))); }); }

/** Horizontal bars with optional 95% whisker. rows: [{label, value, lo?, hi?, color?, note?}] */
export function barsCI(rows, { width = W, min, max, left = 250, rowH = 30, unit = "", zeroLine = true, decimals = 3 } = {}) {
  const lo = min ?? Math.min(0, ...rows.map((r) => r.lo ?? r.value)), hi = max ?? Math.max(...rows.map((r) => r.hi ?? r.value), 1e-9) * 1.08;
  const x = (v) => left + ((v - lo) / (hi - lo || 1)) * (width - left - 30), Ht = rows.length * rowH + 28;
  const g = svg("svg", { class: "chart", viewBox: `0 0 ${width} ${Ht}`, role: "img", "aria-label": `Bar chart, ${rows.length} rows` });
  const step = niceStep((hi - lo) / 5), ticks = []; for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) ticks.push(+t.toFixed(6));
  axisX(g, x, ticks, rows.length * rowH + 6, (t) => +t.toFixed(3));
  if (zeroLine && lo < 0) g.append(svg("line", { class: "axis", x1: x(0), x2: x(0), y1: 4, y2: rows.length * rowH + 6 }));
  rows.forEach((r, i) => {
    const y = 8 + i * rowH, x0 = x(Math.max(lo, Math.min(0, hi)));
    const key = r.series || r.label;
    const bar = svg("rect", { class: `bar grow${r.value < 0 ? " neg" : ""}`, x: Math.min(x0, x(r.value)), y, width: Math.abs(x(r.value) - x0), height: 18, rx: 3, fill: r.color || "var(--bar)", opacity: ".9", "data-series": key, style: `animation-delay:${Math.min(i, 12) * 45}ms` }, svg("title", {}, `${r.label}: ${fmt(r.value, decimals)}${r.lo != null ? ` [${fmt(r.lo, decimals)}, ${fmt(r.hi, decimals)}]` : ""}${unit}`));
    g.append(svg("text", { x: left - 10, y: y + 13, "text-anchor": "end", class: "series-label", "data-series": key }, r.label.length > 40 ? r.label.slice(0, 39) + "…" : r.label), bar);
    if (r.lo != null) g.append(svg("line", { class: "whisker", x1: x(r.lo), x2: x(r.hi), y1: y + 9, y2: y + 9 }), svg("line", { class: "whisker", x1: x(r.lo), x2: x(r.lo), y1: y + 4, y2: y + 14 }), svg("line", { class: "whisker", x1: x(r.hi), x2: x(r.hi), y1: y + 4, y2: y + 14 }));
    g.append(svg("text", { x: Math.max(x(r.value), x(r.hi ?? r.value)) + 6, y: y + 13, style: "font-variant-numeric:tabular-nums;font-weight:600" }, fmt(r.value, decimals)));
  });
  return g;
}
function niceStep(raw) { const p = Math.pow(10, Math.floor(Math.log10(raw || 1))), f = raw / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; }

/** Paired before/after bars (leakage). rows: [{label, before, after, note}] */
export function pairedBars(rows, { width = W, left = 230, rowH = 46, max, beforeLabel = "Clean", afterLabel = "Leaky" } = {}) {
  const hi = (max ?? Math.max(...rows.flatMap((r) => [r.before, r.after]))) * 1.1, x = (v) => left + (v / hi) * (width - left - 60), Ht = rows.length * rowH + 40;
  const g = svg("svg", { class: "chart", viewBox: `0 0 ${width} ${Ht}`, role: "img", "aria-label": "Paired before and after bars" });
  for (let t = 0; t <= hi; t += niceStep(hi / 5)) g.append(svg("line", { class: "gridline", x1: x(t), x2: x(t), y1: 20, y2: Ht - 8 }), svg("text", { x: x(t), y: 14, "text-anchor": "middle" }, +t.toFixed(2)));
  rows.forEach((r, i) => {
    const y = 28 + i * rowH;
    g.append(svg("text", { x: left - 10, y: y + 20, "text-anchor": "end" }, r.label),
      svg("rect", { class: "bar grow", x: left, y, width: x(r.before) - left, height: 14, rx: 3, fill: "var(--bar-muted)", "data-series": r.label, style: `animation-delay:${i * 60}ms` }, svg("title", {}, `${beforeLabel}: ${fmt(r.before)}`)),
      svg("rect", { class: "bar grow", x: left, y: y + 17, width: x(r.after) - left, height: 14, rx: 3, fill: r.color || "var(--err)", "data-series": r.label, style: `animation-delay:${i * 60 + 120}ms` }, svg("title", {}, `${afterLabel}: ${fmt(r.after)}`)),
      svg("text", { x: x(r.before) + 6, y: y + 11 }, fmt(r.before, 3)), svg("text", { x: x(r.after) + 6, y: y + 28, style: "font-weight:700" }, `${fmt(r.after, 3)}${r.note ? "  " + r.note : ""}`));
  });
  return g;
}

/** Multi-series line chart. series: [{name, color, points:[[x,y]]}] */
export function lines(series, { width = W, height = 300, xLabel, yLabel, xTicks, yMax, xFmt = (v) => v, logX = false } = {}) {
  const pad = { l: 52, r: 16, t: 14, b: 40 };
  const xs = series.flatMap((s) => s.points.map((p) => p[0])), ys = series.flatMap((s) => s.points.map((p) => p[1]));
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y1 = yMax ?? Math.max(...ys, 1e-9) * 1.05;
  const X = (v) => pad.l + (logX ? (Math.log(v) - Math.log(x0)) / (Math.log(x1) - Math.log(x0) || 1) : (v - x0) / (x1 - x0 || 1)) * (width - pad.l - pad.r), Y = (v) => height - pad.b - (v / y1) * (height - pad.t - pad.b);
  const g = svg("svg", { class: "chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${yLabel || "Line"} chart` });
  for (let t = 0; t <= y1 + 1e-9; t += niceStep(y1 / 5)) g.append(svg("line", { class: "gridline", x1: pad.l, x2: width - pad.r, y1: Y(t), y2: Y(t) }), svg("text", { x: pad.l - 8, y: Y(t) + 4, "text-anchor": "end" }, +t.toFixed(2)));
  (xTicks || [x0, x1]).forEach((t) => g.append(svg("text", { x: X(t), y: height - pad.b + 16, "text-anchor": "middle" }, xFmt(t))));
  g.append(svg("line", { class: "axis", x1: pad.l, x2: width - pad.r, y1: height - pad.b, y2: height - pad.b }), svg("line", { class: "axis", x1: pad.l, x2: pad.l, y1: pad.t, y2: height - pad.b }));
  xLabel && g.append(svg("text", { x: (pad.l + width - pad.r) / 2, y: height - 6, "text-anchor": "middle" }, xLabel));
  yLabel && g.append(svg("text", { x: 12, y: (pad.t + height - pad.b) / 2, transform: `rotate(-90 12 ${(pad.t + height - pad.b) / 2})`, "text-anchor": "middle" }, yLabel));
  series.forEach((s) => {
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join("");
    g.append(svg("path", { d, fill: "none", stroke: s.color, "stroke-width": 2.2, "stroke-linejoin": "round", "stroke-dasharray": s.dash || null, class: s.dash ? null : "draw", pathLength: s.dash ? null : 1, "data-series": s.name }));
    s.points.forEach((p, j) => g.append(svg("circle", { cx: X(p[0]), cy: Y(p[1]), r: 3, fill: s.color, class: "dot-in", "data-series": s.name, style: `animation-delay:${300 + j * 40}ms` }, svg("title", {}, `${s.name}: ${xFmt(p[0])} → ${fmt(p[1], 3)}`))));
  });
  return g;
}
export const seriesLegend = (series) => h("div", { class: "legend" }, series.map((s) => h("span", { "data-series": s.name, tabindex: "0" }, h("i", { style: { "--lc": s.color } }), s.name)));

/** Scatter: points [{label, x, y, group, color}] with log x. */
export function scatter(points, { width = W, height = 320, xLabel, yLabel, logX = true, yMax = 1.05 } = {}) {
  const pad = { l: 52, r: 16, t: 14, b: 42 }, xs = points.map((p) => p.x), x0 = Math.min(...xs) * 0.8, x1 = Math.max(...xs) * 1.2;
  const X = (v) => pad.l + ((logX ? Math.log(v) - Math.log(x0) : v - x0) / ((logX ? Math.log(x1) - Math.log(x0) : x1 - x0) || 1)) * (width - pad.l - pad.r), Y = (v) => height - pad.b - (v / yMax) * (height - pad.t - pad.b);
  const g = svg("svg", { class: "chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Scatter chart" });
  for (let t = 0; t <= yMax; t += 0.2) g.append(svg("line", { class: "gridline", x1: pad.l, x2: width - pad.r, y1: Y(t), y2: Y(t) }), svg("text", { x: pad.l - 8, y: Y(t) + 4, "text-anchor": "end" }, t.toFixed(1)));
  [100, 300, 1000, 3000, 5000].filter((t) => t >= x0 && t <= x1).forEach((t) => g.append(svg("line", { class: "gridline", x1: X(t), x2: X(t), y1: pad.t, y2: height - pad.b }), svg("text", { x: X(t), y: height - pad.b + 16, "text-anchor": "middle" }, t)));
  g.append(svg("line", { class: "axis", x1: pad.l, x2: width - pad.r, y1: height - pad.b, y2: height - pad.b }), svg("line", { class: "axis", x1: pad.l, x2: pad.l, y1: pad.t, y2: height - pad.b }),
    svg("text", { x: (pad.l + width - pad.r) / 2, y: height - 6, "text-anchor": "middle" }, xLabel), svg("text", { x: 12, y: height / 2, transform: `rotate(-90 12 ${height / 2})`, "text-anchor": "middle" }, yLabel));
  g.append(svg("line", { x1: pad.l, x2: width - pad.r, y1: Y(1), y2: Y(1), stroke: "var(--ok)", "stroke-dasharray": "4 4", opacity: ".7" }));
  points.forEach((p, j) => g.append(svg("circle", { cx: X(p.x), cy: Y(p.y), r: 6, fill: p.color, opacity: ".85", stroke: "var(--surface)", "stroke-width": 1.5, tabindex: "0", class: "dot-in", "data-series": p.label, style: `animation-delay:${Math.min(j, 20) * 25}ms` }, svg("title", {}, `${p.label}: ${p.x} candidates, ${(p.y * 100).toFixed(0)}% of MAP kept`))));
  return g;
}

/** Rank slope chart. columns: ["tf-idf","BM25","ours"]; rows: [{id, ranks:[r1,r2,r3], color, gold}]; lower rank is higher up. */
export function slope(columns, rows, { width = 640, rowH = 22, maxRank = 20, onHover } = {}) {
  const colX = columns.map((_, i) => 70 + (i * (width - 140)) / Math.max(columns.length - 1, 1)), Ht = maxRank * rowH + 50;
  const g = svg("svg", { class: "chart slope", viewBox: `0 0 ${width} ${Ht}`, role: "img", "aria-label": "Rank movement between rankers" });
  const Y = (r) => 36 + (Math.min(r, maxRank + 1) - 1) * rowH;
  columns.forEach((c, i) => g.append(svg("text", { x: colX[i], y: 16, "text-anchor": "middle", style: "font-weight:700" }, c)));
  for (let r = 1; r <= maxRank; r += 1) columns.forEach((_, i) => g.append(svg("text", { x: colX[i] + (i === 0 ? -34 : 34), y: Y(r) + 4, "text-anchor": i === 0 ? "end" : "start", style: "opacity:.55" }, r)));
  rows.forEach((row) => {
    const pts = row.ranks.map((r, i) => (r ? [colX[i], Y(r)] : null));
    const segs = [];
    for (let i = 0; i < pts.length - 1; i += 1) if (pts[i] && pts[i + 1]) segs.push(svg("path", { pathLength: 1, class: `slope-line draw ${row.gold ? "gold" : ""}`, d: `M${pts[i][0]} ${pts[i][1]} C${(pts[i][0] + pts[i + 1][0]) / 2} ${pts[i][1]} ${(pts[i][0] + pts[i + 1][0]) / 2} ${pts[i + 1][1]} ${pts[i + 1][0]} ${pts[i + 1][1]}`, stroke: row.color, "stroke-dasharray": row.gold ? null : null, "data-id": row.id }, svg("title", {}, `${row.id}: ${row.ranks.map((r) => r || ">" + maxRank).join(" → ")}`)));
    segs.forEach((s) => { s.addEventListener("mouseenter", () => { g.classList.add("hovering"); g.querySelectorAll(`[data-id="${CSS.escape(row.id)}"]`).forEach((n) => n.classList.add("on")); onHover && onHover(row.id); });
      s.addEventListener("mouseleave", () => { g.classList.remove("hovering"); g.querySelectorAll(".on").forEach((n) => n.classList.remove("on")); onHover && onHover(null); }); g.append(s); });
    pts.forEach((p, i) => p && g.append(svg("circle", { cx: p[0], cy: p[1], r: row.gold ? 5 : 3.5, fill: row.gold ? "var(--ok)" : row.color, stroke: row.gold ? "var(--surface)" : "none", "stroke-width": 1.5 })));
  });
  return g;
}

/** Neighbour graph: query -> neighbour cases -> candidate precedents. Hover or focus highlights connections.
 * Gentle physics: nodes settle from their columns with springs (to their column slot and along edges) and a little
 * repulsion; any node can be dragged and stays where it is dropped. Static layout when motion is reduced. */
export function neighbourGraph({ queryId, neighbours, candidates, edges, selected, onSelect, width = 480, height = 320 }) {
  const g = svg("svg", { class: "graph", viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": "Graph of the query, similar cases and candidate precedents. Drag nodes to rearrange; press Enter on a candidate to open it." });
  const colX = [46, width / 2, width - 60], place = (items, x) => items.map((it, i) => ({ ...it, x, y: 24 + ((i + 0.5) * (height - 48)) / Math.max(items.length, 1) }));
  const Q = place([{ id: queryId, kind: "query" }], colX[0]).map((n) => ({ ...n, y: height / 2 })), N = place(neighbours.map((n) => ({ id: n.id, sim: n.sim, kind: "neighbour" })), colX[1]), C = place(candidates.map((c) => ({ id: c.id, kind: "candidate" })), colX[2]);
  const nodes = [...Q, ...N, ...C];
  nodes.forEach((n) => { n.ax = n.x; n.ay = n.y; n.vx = 0; n.vy = 0; });
  const pos = Object.fromEntries(nodes.map((n) => [`${n.kind}:${n.id}`, n]));
  const edgeEls = [];
  N.forEach((n) => edgeEls.push({ a: Q[0], b: n, w: 0.8 + 3.2 * (n.sim || 0), ends: [`query:${queryId}`, `neighbour:${n.id}`] }));
  edges.forEach(([nid, cid]) => pos[`neighbour:${nid}`] && pos[`candidate:${cid}`] && edgeEls.push({ a: pos[`neighbour:${nid}`], b: pos[`candidate:${cid}`], w: 1.4, ends: [`neighbour:${nid}`, `candidate:${cid}`] }));
  const pathD = (e) => `M${e.a.x.toFixed(1)} ${e.a.y.toFixed(1)} C${((e.a.x + e.b.x) / 2).toFixed(1)} ${e.a.y.toFixed(1)} ${((e.a.x + e.b.x) / 2).toFixed(1)} ${e.b.y.toFixed(1)} ${e.b.x.toFixed(1)} ${e.b.y.toFixed(1)}`;
  edgeEls.forEach((e) => { e.el = svg("path", { class: "edge", d: pathD(e), fill: "none", "stroke-width": e.w, "data-ends": e.ends.join("|") }); g.append(e.el); });
  const nodeEls = [];
  const R = { query: 9, neighbour: 6, candidate: 7.5 }, COL = { query: "var(--brand)", neighbour: "var(--f-neighbour)", candidate: "var(--f-authority)" };
  const draw = () => { nodes.forEach((n) => n.el.setAttribute("transform", `translate(${n.x.toFixed(1)} ${n.y.toFixed(1)})`)); edgeEls.forEach((e) => e.el.setAttribute("d", pathD(e))); };
  nodes.forEach((n) => {
    const key = `${n.kind}:${n.id}`, r = R[n.kind], sel = n.kind === "candidate" && n.id === selected;
    const el = svg("g", { class: "node", tabindex: "0", role: "button", "data-key": key, "aria-label": `${n.kind} ${n.id}${n.sim != null ? `, similarity ${n.sim}` : ""}` },
      svg("circle", { cx: 0, cy: 0, r, fill: COL[n.kind], stroke: sel ? "var(--text)" : "var(--surface)", "stroke-width": sel ? 3 : 1.5 }),
      svg("text", { x: n.kind === "candidate" ? -r - 4 : r + 4, y: 4, "text-anchor": n.kind === "candidate" ? "end" : "start" }, String(n.id).length > 11 ? String(n.id).slice(0, 10) + "…" : n.id),
      svg("title", {}, `${n.kind}: ${n.id}${n.sim != null ? ` (similarity ${n.sim})` : ""}`));
    n.el = el;
    const on = () => { g.classList.add("hovering"); const related = new Set([key]); edgeEls.forEach((e) => { const hit = e.ends.includes(key); e.el.classList.toggle("on", hit); if (hit) e.ends.forEach((x) => related.add(x)); }); nodeEls.forEach((m) => m.classList.toggle("on", related.has(m.getAttribute("data-key")))); };
    const off = () => { g.classList.remove("hovering"); edgeEls.forEach((e) => e.el.classList.remove("on")); nodeEls.forEach((m) => m.classList.remove("on")); };
    el.addEventListener("mouseenter", on); el.addEventListener("focus", on); el.addEventListener("mouseleave", off); el.addEventListener("blur", off);
    el.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && n.kind === "candidate") { e.preventDefault(); onSelect && onSelect(n.id); } });
    // drag (pointer events); a press that barely moves is a click
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault(); el.setPointerCapture(e.pointerId); el.classList.add("dragging");
      const m = g.getScreenCTM()?.inverse(); if (!m) return;
      const toSvg = (ev) => { const p = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(m); return [Math.max(12, Math.min(width - 12, p.x)), Math.max(12, Math.min(height - 12, p.y))]; };
      const [sx, sy] = toSvg(e); let moved = false;
      n.fixed = true;
      const move = (ev) => { const [x, y] = toSvg(ev); if (Math.hypot(x - sx, y - sy) > 4) moved = true; n.x = x; n.y = y; n.vx = n.vy = 0; if (!sim()) draw(); };
      const up = () => { el.releasePointerCapture?.(e.pointerId); el.classList.remove("dragging"); el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up);
        n.fixed = false; n.ax = n.x; n.ay = n.y; if (!moved && n.kind === "candidate" && onSelect) onSelect(n.id); sim(); };
      el.addEventListener("pointermove", move); el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
    });
    nodeEls.push(el); g.append(el);
  });
  [["Query", colX[0]], ["Similar train cases", colX[1]], ["Candidates", colX[2]]].forEach(([t, x]) => g.append(svg("text", { x, y: 12, "text-anchor": "middle", style: "font-weight:700;fill:var(--text)" }, t)));
  // physics: springs to the slot and along edges, repulsion inside a column, damping; stops when it settles
  let raf = 0, ticks = 0;
  function step() {
    for (const n of nodes) { if (n.fixed) continue; n.vx += (n.ax - n.x) * 0.03; n.vy += (n.ay - n.y) * 0.03; }
    for (const e of edgeEls) { const dy = (e.b.y - e.a.y) * 0.002; if (!e.a.fixed) e.a.vy += dy; if (!e.b.fixed) e.b.vy -= dy; }
    for (let i = 0; i < nodes.length; i += 1) for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i], b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
      if (d2 > 900 || d2 === 0) continue;
      const f = (900 - d2) / 900 * 0.6, d = Math.sqrt(d2);
      if (!a.fixed) { a.vx += (dx / d) * f; a.vy += (dy / d) * f; } if (!b.fixed) { b.vx -= (dx / d) * f; b.vy -= (dy / d) * f; }
    }
    let energy = 0;
    for (const n of nodes) { if (n.fixed) continue; n.vx *= 0.82; n.vy *= 0.82; n.x = Math.max(12, Math.min(width - 12, n.x + n.vx)); n.y = Math.max(20, Math.min(height - 10, n.y + n.vy)); energy += n.vx * n.vx + n.vy * n.vy; }
    draw();
    ticks += 1;
    if ((energy > 0.002 || nodes.some((n) => n.fixed)) && ticks < 600 && g.isConnected) raf = requestAnimationFrame(step); else raf = 0;
  }
  function sim() { if (reducedMotion()) return false; ticks = 0; if (!raf) raf = requestAnimationFrame(step); return true; }
  if (!reducedMotion()) {   // start a little scattered so the settling is visible
    nodes.forEach((n, i) => { n.x = n.ax + (n.kind === "query" ? -10 : (i % 2 ? 14 : -14)); n.y = n.ay + ((i * 37) % 23) - 11; });
    requestAnimationFrame(() => { draw(); sim(); });
  }
  draw();
  return g;
}
