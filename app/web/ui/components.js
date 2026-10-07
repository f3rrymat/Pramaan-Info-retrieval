// Internal component library. Every function returns a DOM node built with h() and styled by components.css.
import { h, svg, clear, reducedMotion, fmt } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { illustration } from "/ui/brand.js";

export const ZONES = ["facts", "issues", "arguments", "reasoning", "decision", "statute_analysis", "precedent_analysis"];
export const zoneLabel = (z) => ({ facts: "Facts", issues: "Issues", arguments: "Arguments", reasoning: "Reasoning", decision: "Decision", statute_analysis: "Statute analysis", precedent_analysis: "Precedent analysis", other: "Other" }[z] || z);
export const FEATURE_LABEL = { text: "Text", neighbour: "Neighbours", authority: "Authority", recency: "Recency", court: "Court", statute: "Statute" };
export const featureColor = (k) => `var(--f-${k})`;

export function button(label, { variant = "", size = "", icon: ic, onClick, type = "button", disabled, title, loading } = {}) {
  const b = h("button", { class: `btn ${variant} ${size} ${ic && !label ? "icon" : ""}`.trim(), type, disabled: disabled || loading, title, "aria-label": !label ? title : null, onClick });
  if (loading) b.append(h("span", { class: "spin" })); else if (ic) b.append(icon(ic, { size: size === "sm" ? 15 : 18 }));
  if (label) b.append(label);
  return b;
}
export const badge = (text, kind = "") => h("span", { class: `badge ${kind}`.trim() }, text);
export const courtBadge = (c) => h("span", { class: `badge court-${c || "OTHER"}`, "data-tip": { SC: "Supreme Court", HC: "High Court", OTHER: "Other court" }[c] || "Court level unknown" }, c || "?");
export const zoneChip = (z) => h("span", { class: "zone-chip", style: { "--zc": `var(--z-${z})` } }, zoneLabel(z));
export function chip(label, { pressed, mono, onClick, onRemove, title } = {}) {
  const c = h(onClick ? "button" : "span", { class: `chip ${mono ? "mono" : ""}`, type: onClick ? "button" : null, "aria-pressed": pressed == null ? null : String(!!pressed), title, onClick }, label);
  if (onRemove) c.append(h("span", { class: "x", role: "button", tabindex: "0", "aria-label": "Remove", onClick: (e) => { e.stopPropagation(); onRemove(); }, onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRemove(); } } }, "×"));
  return c;
}

export function scoreRing(value, { color = "var(--brand)", label } = {}) {
  const r = 20, c = 2 * Math.PI * r;
  const fg = svg("circle", { class: "fg", cx: 24, cy: 24, r, fill: "none", "stroke-width": 5, "stroke-dasharray": c, "stroke-dashoffset": c });
  const val = h("div", { class: "val" }, "0");
  const el = h("div", { class: "ring", style: { "--rc": color }, role: "img" }, svg("svg", { viewBox: "0 0 48 48" }, svg("circle", { class: "bg", cx: 24, cy: 24, r, fill: "none", "stroke-width": 5 }), fg), val);
  let shown = 0;
  /** Animate to a new value (stroke and number together); instant when motion is reduced. */
  el.set = (nv) => {
    const v = Math.max(0, Math.min(1, nv || 0)), from = shown;
    el.setAttribute("aria-label", `${label || "Score"} ${(v * 100).toFixed(0)} out of 100`);
    requestAnimationFrame(() => requestAnimationFrame(() => fg.setAttribute("stroke-dashoffset", String(c * (1 - v)))));
    if (reducedMotion()) { val.textContent = (v * 100).toFixed(0); shown = v; return; }
    const t0 = performance.now(), dur = 520;
    const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); val.textContent = ((from + (v - from) * e) * 100).toFixed(0); if (k < 1) requestAnimationFrame(step); else shown = v; };
    requestAnimationFrame(step);
  };
  el.set(value);
  return el;
}

/** parts: [{key, value, label?}] drawn as proportions; colours come from the feature palette. Widths are set at once; the change is shown by gliding
 *  each segment from its old box to its new one (transform only), so the bar never animates a layout property. */
export function stackBar(parts) {
  const el = h("div", { class: "sbar", role: "img" });
  const segs = {};
  el.set = (ps) => {
    const total = ps.reduce((s, p) => s + Math.max(0, p.value), 0) || 1;
    el.setAttribute("aria-label", ps.map((p) => `${FEATURE_LABEL[p.key] || p.key} ${fmt(p.value, 3)}`).join(", "));
    const before = new Map(Object.entries(segs).map(([k, s]) => [k, s.getBoundingClientRect()]));
    ps.forEach((p) => {
      let sg = segs[p.key];
      if (!sg) { sg = segs[p.key] = h("span", { "data-series": `feature:${p.key}`, style: { "--sc": featureColor(p.key) } }); el.append(sg); }
      sg.setAttribute("data-tip", `${FEATURE_LABEL[p.key] || p.key}: ${fmt(p.value, 3)}`);
      sg.hidden = !(p.value > 0);
      sg.style.width = `${(Math.max(0, p.value) / total) * 100}%`;
    });
    if (el.isConnected && !reducedMotion() && el.animate) {
      Object.entries(segs).forEach(([k, sg]) => {
        const a = before.get(k), b = sg.getBoundingClientRect();
        if (!a || !a.width || !b.width || sg.hidden) return;
        const dx = a.left - b.left, sx = a.width / b.width;
        if (Math.abs(dx) < 0.5 && Math.abs(sx - 1) < 0.01) return;
        sg.animate([{ transform: `translateX(${dx}px) scaleX(${sx})` }, { transform: "none" }], { duration: 320, easing: "cubic-bezier(.2,.7,.2,1)" });
      });
    }
  };
  el.set(parts);
  if (!reducedMotion() && el.animate) el.animate([{ transform: "scaleX(0)" }, { transform: "none" }], { duration: 420, easing: "cubic-bezier(.2,.7,.2,1)" });
  return el;
}

export const legend = (keys) => h("div", { class: "legend" }, keys.map((k) => h("span", { "data-series": `feature:${k}`, tabindex: "0" }, h("i", { style: { "--lc": featureColor(k) } }), FEATURE_LABEL[k] || k)));

export function hbar(label, value, max, { color = "var(--brand)", text } = {}) {
  const fill = h("div", { class: "fill", style: { "--hc": color, transform: `scaleX(${Math.max(0, Math.min(1, value / (max || 1)))})` } });
  return h("div", { class: "hbar" }, h("span", {}, label), h("div", { class: "track" }, fill), h("span", { class: "num", style: { textAlign: "right" } }, text ?? fmt(value, 3)));
}

export function segmented(options, value, onChange, { label } = {}) {
  const root = h("div", { class: "seg", role: "radiogroup", "aria-label": label || null });
  const paint = (v) => root.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.v === v)));
  options.forEach((o) => root.append(h("button", { type: "button", role: "radio", "data-v": o.value, title: o.title || null, onClick: () => { paint(o.value); onChange(o.value); }, onKeydown: (e) => {
    const bs = [...root.querySelectorAll("button")], i = bs.indexOf(e.currentTarget);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); const n = bs[(i + (e.key === "ArrowRight" ? 1 : -1) + bs.length) % bs.length]; n.focus(); n.click(); } } }, o.label)));
  paint(value);
  root.set = paint;
  return root;
}

export function field(label, control, { hint, error, id } = {}) {
  const lid = id || `f${Math.random().toString(36).slice(2, 8)}`;
  if (control.setAttribute && !control.id) control.id = lid;
  return h("div", { class: "field" }, h("label", { for: control.id || lid }, label), control, hint && h("div", { class: "field-hint" }, hint), error && h("div", { class: "field-error", role: "alert" }, icon("alert", { size: 14 }), error));
}

/** Searchable combobox. items: [{value, label, meta?, node?}]. */
export function combobox({ items, value, placeholder = "Search…", onSelect, label = "Choose", emptyText = "No match" }) {
  const id = `cb${Math.random().toString(36).slice(2, 7)}`;
  const input = h("input", { class: "input", role: "combobox", "aria-expanded": "false", "aria-controls": id, "aria-autocomplete": "list", "aria-label": label, placeholder, autocomplete: "off", spellcheck: "false" });
  const list = h("div", { class: "combo-list", id, role: "listbox", hidden: true });
  const root = h("div", { class: "combo" }, input, list);
  let shown = [], active = -1, current = value;
  const render = () => {
    clear(list);
    if (!shown.length) list.append(h("div", { class: "combo-empty" }, emptyText));
    shown.slice(0, 80).forEach((it, i) => list.append(h("div", { class: "combo-opt", role: "option", id: `${id}-${i}`, "aria-selected": String(i === active), onMousedown: (e) => { e.preventDefault(); pick(it); } }, it.node ? it.node() : [h("span", { class: "mono" }, it.label), it.meta && h("span", { class: "muted xs" }, it.meta)])));
    input.setAttribute("aria-activedescendant", active >= 0 ? `${id}-${active}` : "");
  };
  const filter = (q) => { q = q.trim().toLowerCase(); shown = q ? items.filter((i) => `${i.label} ${i.meta || ""}`.toLowerCase().includes(q)) : items; active = shown.length ? 0 : -1; render(); };
  const open = () => { list.hidden = false; input.setAttribute("aria-expanded", "true"); };
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); };
  const pick = (it) => { current = it.value; input.value = it.label; close(); onSelect && onSelect(it); };
  input.addEventListener("focus", () => { input.select(); filter(""); open(); });
  input.addEventListener("input", () => { filter(input.value); open(); });
  input.addEventListener("blur", () => { close(); const it = items.find((i) => i.value === current); input.value = it ? it.label : ""; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); open(); if (!shown.length) return; active = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length; render(); document.getElementById(`${id}-${active}`)?.scrollIntoView({ block: "nearest" }); }
    else if (e.key === "Enter" && active >= 0 && !list.hidden) { e.preventDefault(); pick(shown[active]); }
    else if (e.key === "Escape") { close(); }
  });
  root.setValue = (v) => { current = v; const it = items.find((i) => i.value === v); input.value = it ? it.label : (v || ""); };
  root.input = input;
  root.setValue(value);
  return root;
}

/** Two-handle range (years). */
export function dualRange({ min, max, lo, hi, onChange, label = "Range" }) {
  const a = h("input", { type: "range", min, max, value: lo, "aria-label": `${label} from` }), b = h("input", { type: "range", min, max, value: hi, "aria-label": `${label} to` });
  const fill = h("div", { class: "fill" }), out = h("div", { class: "row small num", style: { justifyContent: "space-between" } });
  const root = h("div", {}, h("div", { class: "dual-range" }, h("div", { class: "track" }), fill, a, b), out);
  const paint = () => { let x = +a.value, y = +b.value; if (x > y) [x, y] = [y, x]; fill.style.left = `${((x - min) / (max - min)) * 100}%`; fill.style.right = `${100 - ((y - min) / (max - min)) * 100}%`; clear(out).append(h("span", {}, x), h("span", { class: "muted" }, "to"), h("span", {}, y)); return [x, y]; };
  const fire = () => { const [x, y] = paint(); onChange && onChange(x, y); };
  a.addEventListener("input", fire); b.addEventListener("input", fire); paint();
  root.set = (x, y) => { a.value = x; b.value = y; paint(); };
  return root;
}

// ------------------------------------------------------------------ overlays
let toastHost;
/** toast(message, kind, { action: { label, run }, duration, onTimeout }). An action (e.g. Undo) gets a button; onTimeout runs only if the toast was not acted on. */
export function toast(msg, kind = "", { action, duration, onTimeout } = {}) {
  recordNotification(msg, kind);
  toastHost = toastHost || document.body.appendChild(h("div", { class: "toasts", role: "status", "aria-live": "polite" }));
  let done = false, timer;
  const close = () => { if (!t.isConnected) return; t.classList.add("leaving"); setTimeout(() => t.remove(), reducedMotion() ? 0 : 220); };
  const act = action ? h("button", { class: "toast-action", type: "button", onClick: () => { if (done) return; done = true; clearTimeout(timer); close(); action.run(); } }, action.label) : null;
  const t = h("div", { class: `toast ${kind}` }, kind === "err" ? icon("alert", { size: 16 }) : kind === "ok" ? icon("check", { size: 16 }) : null, h("span", { class: "grow" }, msg), act,
    action ? h("i", { class: "toast-timer", style: { animationDuration: `${duration || 6000}ms` }, "aria-hidden": "true" }) : null);
  toastHost.append(t);
  timer = setTimeout(() => { if (!done) { done = true; onTimeout && onTimeout(); } close(); }, duration || (action ? 6000 : 4200));
  return { close: () => { clearTimeout(timer); if (!done) { done = true; onTimeout && onTimeout(); } close(); } };
}

/** Notification history: every toast is also kept (last 30) so it can be read again from the bell in the top bar. */
const notes = [];
export const notificationEvents = new EventTarget();
export const getNotifications = () => notes.slice();
function recordNotification(msg, kind) { notes.unshift({ msg: String(msg), kind: kind || "info", ts: Date.now() }); notes.length = Math.min(notes.length, 30); notificationEvents.dispatchEvent(new Event("change")); }

function trap(root, onClose) {
  const prev = document.activeElement;
  const keys = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose(); }
    if (e.key === "Tab") { const f = [...root.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")].filter((x) => !x.disabled && x.offsetParent !== null); if (!f.length) return; const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } }
  };
  root.addEventListener("keydown", keys);
  return () => { root.removeEventListener("keydown", keys); prev && prev.focus && prev.focus(); };
}
export function modal({ title, body, className = "", labelledBy, onClose, hideHead }) {
  const scrim = h("div", { class: "scrim" });
  const m = h("div", { class: `modal ${className}`, role: "dialog", "aria-modal": "true", "aria-label": title }, hideHead ? null : h("div", { class: "modal-head" }, h("h2", {}, title), h("span", { class: "spacer" }), button("", { variant: "ghost", size: "sm", icon: "x", title: "Close", onClick: () => close() })), h("div", { class: hideHead ? "" : "modal-body" }, body));
  let release;
  const close = () => { release && release(); scrim.remove(); m.remove(); onClose && onClose(); };
  scrim.addEventListener("click", close);
  document.body.append(scrim, m);
  release = trap(m, close);
  (m.querySelector("input, button, [tabindex]") || m).focus();
  return { close, el: m };
}
export function drawer({ title, body, onClose, actions }) {
  const scrim = h("div", { class: "scrim" });
  const d = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": title }, h("div", { class: "drawer-head" }, h("h2", {}, title), h("span", { class: "spacer" }), actions, button("", { variant: "ghost", size: "sm", icon: "x", title: "Close", onClick: () => close() })), h("div", { class: "drawer-body" }, body));
  let release;
  const close = () => { release && release(); scrim.remove(); d.remove(); onClose && onClose(); };
  scrim.addEventListener("click", close);
  document.body.append(scrim, d);
  release = trap(d, close);
  (d.querySelector(".drawer-head button") || d).focus();
  return { close, el: d, body: d.querySelector(".drawer-body") };
}

// ------------------------------------------------------------------ states
export const skeleton = (w = "100%", hgt = "14px") => h("div", { class: "skel", style: { width: w, height: hgt }, "aria-hidden": "true" });
export function skeletonChart(hgt = "220px") { return h("div", { class: "card stack", role: "status", "aria-label": "Loading" }, skeleton("40%", "18px"), h("div", { class: "skel skel-chart", style: { height: hgt }, "aria-hidden": "true" })); }
export function skeletonCards(n = 4) { return h("div", { class: "stack", role: "status", "aria-label": "Loading" }, Array.from({ length: n }, () => h("div", { class: "card tight" }, h("div", { class: "stack" }, skeleton("30%", "16px"), skeleton("90%"), skeleton("65%"))))); }
export function emptyState(title, text, { icon: ic = "search", action, kind } = {}) { return h("div", { class: "state" }, illustration(kind || (ic === "lock" ? "lock" : "empty")), h("h3", {}, title), text && h("p", {}, text), action); }
export function errorState(err, retry) {
  const offline = err?.code === "network" || err?.status === 0;
  return h("div", { class: "state err", role: "alert" }, illustration(offline ? "offline" : "error"), h("h3", {}, offline ? "The server is not reachable" : "Something went wrong"),
    h("p", {}, offline ? "Check that the app server is still running on this machine. Your place on the page is kept; try again when it is back." : String(err?.message || err)), retry && button("Try again", { variant: "secondary", onClick: retry }));
}
export const alertBox = (text, kind = "", ic = "info") => h("div", { class: `alert ${kind}`, role: kind === "err" ? "alert" : null }, icon(ic, { size: 18 }), h("div", {}, text));

export function countUp(el, to, { decimals = 4, dur = 700, prefix = "", suffix = "" } = {}) {
  const set = (v) => { el.textContent = `${prefix}${v.toFixed(decimals)}${suffix}`; };
  if (reducedMotion() || to == null) { set(to ?? 0); if (to == null) el.textContent = "–"; return el; }
  const t0 = performance.now();
  const step = (t) => { const k = Math.min(1, (t - t0) / dur); set(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
  return el;
}
export function kpi(label, value, { decimals = 4, delta, hint, suffix = "", onExplain } = {}) {
  const v = h("div", { class: "v" }, "0");
  countUp(v, value, { decimals, suffix });
  return h("div", { class: "card tight kpi", "data-series": `metric:${label}` }, h("div", { class: "kpi-top" }, h("div", { class: "l" }, label),
    onExplain ? h("button", { class: "btn ghost sm icon explain-btn", type: "button", title: "Explain this metric", "aria-label": `Explain this metric: ${label}`, onClick: () => onExplain({ name: label, value }) }, icon("spark", { size: 15 })) : null),
    v, delta != null && h("div", { class: `d ${delta >= 0 ? "" : ""}` }, delta), hint && h("div", { class: "xs muted" }, hint));
}
export function tabs(items, active, onChange) {
  const root = h("div", { class: "tabs", role: "tablist" });
  const paint = (id) => root.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.id === id)));
  items.forEach((t) => root.append(h("button", { type: "button", role: "tab", "data-id": t.id, onClick: () => { paint(t.id); onChange(t.id); } }, t.label)));
  paint(active);
  return root;
}
export function table(headers, rows, { numeric = [], highlight, rowKey } = {}) {
  return h("div", { class: "table-wrap" }, h("table", { class: "table" }, h("thead", {}, h("tr", {}, headers.map((x, i) => h("th", { class: numeric.includes(i) ? "n" : "" }, x)))),
    h("tbody", {}, rows.map((r, ri) => h("tr", { class: highlight && highlight(ri, r) ? "hl" : "", "data-series": rowKey ? rowKey(r, ri) : null }, r.map((c, i) => h("td", { class: numeric.includes(i) ? "n" : "" }, c)))))));
}
export function pageHead(title, sub, actions) { return h("div", { class: "page-head" }, h("div", { class: "grow" }, h("h1", {}, title), sub && h("p", {}, sub)), actions); }
export function copyText(text) { return navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject(new Error("clipboard unavailable")); }
export function downloadBlob(name, blob) { const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
export const toCsv = (rows) => rows.map((r) => r.map((c) => { const s = String(c ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(",")).join("\n");

/** Save an inline SVG chart as a PNG: computed styles are inlined so theme variables resolve outside the page. */
export function exportSvgPng(svgEl, name = "chart.png") {
  const clone = svgEl.cloneNode(true), src = [svgEl, ...svgEl.querySelectorAll("*")], dst = [clone, ...clone.querySelectorAll("*")];
  const props = ["fill", "stroke", "stroke-width", "stroke-dasharray", "opacity", "font-family", "font-size", "font-weight", "text-anchor", "stroke-linejoin"];
  src.forEach((n, i) => { const cs = getComputedStyle(n); props.forEach((p) => dst[i].style.setProperty(p, cs.getPropertyValue(p))); });
  const vb = svgEl.viewBox.baseVal, w = vb.width || svgEl.clientWidth, hgt = vb.height || svgEl.clientHeight;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg"); clone.setAttribute("width", w); clone.setAttribute("height", hgt);
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas"); c.width = w * 2; c.height = hgt * 2;
    const g = c.getContext("2d"); g.fillStyle = getComputedStyle(document.body).backgroundColor; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
    c.toBlob((b) => { downloadBlob(name, b); URL.revokeObjectURL(url); });
  };
  img.src = url;
}

/** Minimal Markdown for README sections: paragraphs, bullets, **bold**, `code`, [links](url). Built from nodes, never innerHTML. */
export function renderMarkdown(text) {
  const inline = (s) => {
    const out = [], re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*]+\*)/g;
    let last = 0, m;
    while ((m = re.exec(s))) {
      if (m.index > last) out.push(s.slice(last, m.index));
      const t = m[0];
      if (t.startsWith("**")) out.push(h("b", {}, t.slice(2, -2))); else if (t.startsWith("`")) out.push(h("code", {}, t.slice(1, -1)));
      else if (t.startsWith("[")) { const [, lab, url] = /\[([^\]]+)\]\(([^)]+)\)/.exec(t); out.push(/^https?:/.test(url) ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, lab) : lab); }
      else out.push(h("em", {}, t.slice(1, -1)));
      last = m.index + t.length;
    }
    if (last < s.length) out.push(s.slice(last));
    return out;
  };
  const root = h("div", { class: "stack", style: { gap: "var(--s-2)" } });
  let list = null;
  for (const line of text.split("\n")) {
    if (/^\s*[-*] /.test(line)) { if (!list) { list = h("ul", { style: { margin: 0, paddingLeft: "1.2rem" } }); root.append(list); } list.append(h("li", {}, inline(line.replace(/^\s*[-*] /, "")))); }
    else if (line.trim() === "") list = null;
    else if (/^```/.test(line)) { /* code fences are skipped in the About page */ }
    else { list = null; root.append(h("p", {}, inline(line.trim()))); }
  }
  return root;
}
