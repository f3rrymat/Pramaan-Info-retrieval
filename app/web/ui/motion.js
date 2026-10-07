// Motion helpers (D45). Every helper is a no-op when motion is reduced (OS setting or Settings switch "Reduce motion").
// Only transform and opacity are animated, through the Web Animations API, and all layout reads happen before any write.
import { reducedMotion } from "/ui/dom.js";

export const motionOK = () => !reducedMotion() && typeof Element.prototype.animate === "function";
const EASE = "cubic-bezier(.2, .7, .2, 1)";

/** Record the on-screen boxes of keyed elements (data-key) so they can glide to new positions later. */
export function snapshot(root, sel = "[data-key]") {
  const m = new Map();
  if (!root) return m;
  root.querySelectorAll(sel).forEach((el) => m.set(el.getAttribute("data-key"), el.getBoundingClientRect()));
  return m;
}

/** FLIP: elements present in `before` glide from their old box to the new one; new elements rise in with a stagger. */
export function playFlip(root, before, { sel = "[data-key]", duration = 420, stagger = 28, enter = true } = {}) {
  if (!root || !motionOK()) return;
  const els = [...root.querySelectorAll(sel)];
  const after = els.map((el) => el.getBoundingClientRect());              // read everything first
  let n = 0;
  els.forEach((el, i) => {                                                  // then write
    const a = before.get(el.getAttribute("data-key")), b = after[i];
    if (a) {
      const dx = a.left - b.left, dy = a.top - b.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration, easing: EASE });
    } else if (enter && b.top < innerHeight + 200) {
      el.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 320, delay: Math.min(n++, 10) * stagger, easing: EASE, fill: "backwards" });
    }
  });
}

/** Run a DOM mutation with FLIP around it. */
export function flip(root, mutate, opts) { const before = snapshot(root, opts?.sel); mutate(); playFlip(root, before, opts); }

/** Staggered entrance for a list of freshly inserted nodes. */
export function stagger(nodes, { step = 34, max = 10 } = {}) {
  if (!motionOK()) return;
  [...nodes].forEach((el, i) => el.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 340, delay: Math.min(i, max) * step, easing: EASE, fill: "backwards" }));
}

/** Shared-element transition: a ghost of `fromRect` morphs into `toEl` (e.g. a result card into the case drawer). */
export function morph(fromRect, toEl, { duration = 380 } = {}) {
  if (!fromRect || !toEl || !motionOK()) return;
  const to = toEl.getBoundingClientRect();
  if (!to.width || !to.height) return;
  const g = document.createElement("div");
  g.className = "morph-ghost";
  Object.assign(g.style, { left: `${to.left}px`, top: `${to.top}px`, width: `${to.width}px`, height: `${to.height}px` });
  document.body.append(g);
  const sx = fromRect.width / to.width, sy = fromRect.height / to.height, dx = fromRect.left - to.left, dy = fromRect.top - to.top;
  const a = g.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, opacity: 1 }, { transform: "none", opacity: 0.0 }], { duration, easing: EASE });
  toEl.animate([{ opacity: 0 }, { opacity: 0, offset: 0.45 }, { opacity: 1 }], { duration: duration + 80, easing: "ease-out" });
  a.onfinish = a.oncancel = () => g.remove();
}

/** Linked hover: any element with data-series="X" highlights every other [data-series="X"] inside root (charts, tables, legends). */
export function linkHover(root) {
  if (!root || root.__linked) return root;
  root.__linked = true;
  let cur = null;
  const set = (key) => {
    if (key === cur) return;
    cur = key;
    root.classList.toggle("linking", !!key);
    root.querySelectorAll(".linked").forEach((n) => n.classList.remove("linked"));
    if (key) root.querySelectorAll(`[data-series="${CSS.escape(key)}"]`).forEach((n) => n.classList.add("linked"));
  };
  const find = (e) => e.target.closest?.("[data-series]");
  root.addEventListener("pointerover", (e) => { const t = find(e); set(t && root.contains(t) ? t.getAttribute("data-series") : null); });
  root.addEventListener("pointerleave", () => set(null));
  root.addEventListener("focusin", (e) => { const t = find(e); if (t) set(t.getAttribute("data-series")); });
  root.addEventListener("focusout", () => set(null));
  return root;
}

/** A short fade of the outgoing page before a route change (skipped when motion is reduced). */
export function fadeOut(el, ms = 110) {
  if (!el || !motionOK() || !el.firstChild) return Promise.resolve();
  return new Promise((res) => { const a = el.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-4px)" }], { duration: ms, easing: "ease-in", fill: "forwards" }); a.onfinish = a.oncancel = () => { res(); requestAnimationFrame(() => a.cancel()); }; });
}

/** Swap page content: View Transitions API where supported (200 ms cross-fade), the short fade-out helper otherwise. */
export function swapPage(page, mutate) {
  if (typeof document.startViewTransition === "function" && motionOK()) {
    try { return document.startViewTransition(() => { mutate(); }).updateCallbackDone.catch(() => {}); } catch (_) { /* fall through */ }
  }
  return fadeOut(page).then(mutate);
}
