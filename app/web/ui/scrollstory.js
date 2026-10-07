// Scroll helpers shared by the landing page and "How it works": run something when an element becomes visible, and a scroll-driven
// story (steps on the right, a sticky diagram on the left that highlights the current step). Only transform and opacity are animated.
import { h, reducedMotion } from "/ui/dom.js";

/** Call fn once (or on every entry) when el is visible. Falls back to calling it at once without IntersectionObserver. */
export function onVisible(el, fn, { once = true, threshold = 0.25 } = {}) {
  if (typeof IntersectionObserver === "undefined") { fn(); return () => {}; }
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { fn(); if (once) io.disconnect(); } }), { threshold });
  io.observe(el);
  return () => io.disconnect();
}
/** Fade-and-rise every .reveal inside root as it scrolls into view (CSS handles reduced motion). */
export function revealOnScroll(root) {
  const els = [...root.querySelectorAll(".reveal")];
  els.forEach((el, i) => { el.style.transitionDelay = `${Math.min(i % 6, 5) * 40}ms`; onVisible(el, () => el.classList.add("in"), { threshold: 0.12 }); });
}
export const smoothTo = (el) => el?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });

/**
 * steps: [{ id, label, title, text, data, modules }]. data is a line built from saved results; modules are code module names (chips).
 * Returns { el, setActive(i) }. The diagram is a vertical chain; a marker glides (translateY) to the active node.
 */
export function scrollStory(steps, { title = "", onStep, onConcept } = {}) {
  const nodes = steps.map((s, i) => h("li", { class: "story-node", "data-i": i }, h("span", { class: "story-dot" }, i + 1), h("span", { class: "story-label" }, s.label)));
  const marker = h("span", { class: "story-marker", "aria-hidden": "true" });
  const chain = h("ol", { class: "story-chain", "aria-label": title || "Steps" }, marker, nodes);
  const diagram = h("div", { class: "story-diagram" }, h("div", { class: "story-diagram-in card" }, h("div", { class: "xs muted story-kicker" }, title), chain, h("div", { class: "story-progress", "aria-hidden": "true" }, h("i", {}))));
  const panes = steps.map((s, i) => h("section", { class: "story-step", "data-i": i, id: `step-${s.id}`, tabindex: "-1" },
    h("div", { class: "story-step-in" }, h("div", { class: "story-num" }, `Step ${i + 1} of ${steps.length}`), h("h3", {}, s.title), h("p", {}, s.text),
      s.data ? h("p", { class: "story-data" }, h("span", { class: "story-data-tag" }, "From saved runs"), " ", s.data) : null,
      s.extra || null,
      s.modules?.length ? h("p", { class: "story-mods" }, h("span", { class: "xs muted" }, "Code: "), s.modules.map((m) => h("code", { class: "mod-chip", "data-concept": s.label }, m))) : null,
      s.concepts?.length ? h("p", { class: "story-mods" }, h("span", { class: "xs muted" }, "Lecture concepts: "), s.concepts.map(([label, mod]) => h("button", { type: "button", class: "concept-chip", title: `Show ${label} in the table of lecture concepts and code`, onClick: () => onConcept && onConcept(label) }, label, h("code", {}, mod)))) : null)));
  const el = h("div", { class: "story" }, diagram, h("div", { class: "story-steps" }, panes));
  let cur = -1;
  const setActive = (i) => {
    if (i === cur) return; cur = i;
    nodes.forEach((n, j) => { n.classList.toggle("on", j === i); n.classList.toggle("done", j < i); if (j === i) n.setAttribute("aria-current", "step"); else n.removeAttribute("aria-current"); });
    panes.forEach((p, j) => p.classList.toggle("on", j === i));
    const n = nodes[i], k = n ? n.offsetTop : 0;
    marker.style.transform = `translateY(${k}px)`; marker.style.height = `${n ? n.offsetHeight : 0}px`;
    const bar = el.querySelector(".story-progress i"); if (bar) bar.style.transform = `scaleX(${(i + 1) / steps.length})`;
    onStep && onStep(i, steps[i]);
  };
  nodes.forEach((n, i) => n.addEventListener("click", () => smoothTo(panes[i])));
  if (typeof IntersectionObserver !== "undefined") {
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) setActive(+e.target.getAttribute("data-i")); }), { rootMargin: "-42% 0px -48% 0px", threshold: 0 });
    panes.forEach((p) => io.observe(p));
  }
  requestAnimationFrame(() => setActive(0));
  return { el, setActive };
}
