// Tiny hyperscript helper. Text is always inserted as text nodes (never innerHTML), so API strings cannot inject markup.
export function h(tag, attrs, ...kids) {
  const el = tag === "svg" || tag.startsWith("svg:") ? document.createElementNS("http://www.w3.org/2000/svg", tag.replace("svg:", "")) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "style" && typeof v === "object") { for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith("--")) el.style.setProperty(sk, sv); else el.style[sk] = sv; } }
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "html") throw new Error("html attribute is not allowed");
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, kids);
  return el;
}
export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}
export const svg = (tag, attrs, ...kids) => h("svg:" + tag, attrs, ...kids);
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const debounce = (fn, ms = 200) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
/** Motion is reduced when the OS asks for it OR the Settings switch "Reduce motion" is on (data-motion="reduce" on <html>). */
export const osReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const reducedMotion = () => osReducedMotion() || document.documentElement.getAttribute("data-motion") === "reduce";
export const fmt = (x, d = 4) => (x == null || Number.isNaN(Number(x)) ? "–" : Number(x).toFixed(d));
export const pct = (x, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
export const signed = (x, d = 4) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(d)}`);
