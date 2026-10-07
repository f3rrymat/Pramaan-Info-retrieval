// Pramaan brand mark as inline SVG (also the favicon in index.html) and a few small drawings for empty, error and offline states.
import { svg } from "/ui/dom.js";

/** The mark: a rounded tile, a "P" whose bowl is a citation loop, and a node it points to. Colours come from tokens. */
export function brandMark(size = 32) {
  return svg("svg", { class: "brand-mark", viewBox: "0 0 32 32", width: size, height: size, "aria-hidden": "true", focusable: "false" },
    svg("defs", {}, svg("linearGradient", { id: "pm-g", x1: "0", y1: "0", x2: "1", y2: "1" }, svg("stop", { offset: "0", "stop-color": "var(--brand)" }), svg("stop", { offset: "1", "stop-color": "var(--role, var(--brand))" }))),
    svg("rect", { width: "32", height: "32", rx: "9", fill: "url(#pm-g)" }),
    svg("path", { d: "M11 24V8.5h6.5a4.5 4.5 0 0 1 0 9H11", fill: "none", stroke: "#fff", "stroke-width": "2.4", "stroke-linecap": "round", "stroke-linejoin": "round" }),
    svg("circle", { cx: "17", cy: "13", r: "2", fill: "#fff" }));
}

const D = {
  // magnifier over an empty page
  empty: [["rect", { x: "14", y: "10", width: "38", height: "48", rx: "6" }], ["path", { d: "M22 22h22M22 31h14" }], ["circle", { cx: "44", cy: "46", r: "8" }], ["path", { d: "M50 52l7 7" }]],
  // broken link
  error: [["path", { d: "M26 38l-6 6a8 8 0 0 1-11-11l8-8a8 8 0 0 1 11 0" }], ["path", { d: "M38 26l6-6a8 8 0 0 1 11 11l-8 8a8 8 0 0 1-11 0" }], ["path", { d: "M30 14l-2-6M16 24l-6-2M44 50l2 6M54 40l6 2" }]],
  // unplugged cable
  offline: [["path", { d: "M22 10v14M42 10v14M16 24h32v8a16 16 0 0 1-32 0z" }], ["path", { d: "M32 48v10" }], ["path", { d: "M10 54l44-44" }]],
  // lock
  lock: [["rect", { x: "14", y: "28", width: "36", height: "26", rx: "6" }], ["path", { d: "M22 28v-6a10 10 0 0 1 20 0v6M32 38v6" }]],
};
/** Small line drawing for state panels. kind: empty | error | offline | lock. */
export function illustration(kind = "empty", size = 72) {
  return svg("svg", { class: "illus", viewBox: "0 0 64 64", width: size, height: size, "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" },
    ...(D[kind] || D.empty).map(([t, a]) => svg(t, a)));
}
