// Live pipeline strip for the Search page. While a search runs the stages light up in turn (an indeterminate sweep:
// the server answers once, so progress inside the request is not observable); when the answer arrives each stage shows
// the wall time the server measured for it (Server-Timing header). Stages that were not run or not measured say so.
import { h, clear } from "/ui/dom.js";
import { reducedMotion } from "/ui/dom.js";

const STAGES = [
  { key: "query", label: "Query", color: "var(--z-facts)", tip: "Look up the dev query (Facts + Issues) or take the pasted text." },
  { key: "scrub", label: "Scrub", color: "var(--z-issues)", tip: "Remove case-citation strings so the query cannot name its own answer." },
  { key: "first_stage", label: "First stage", color: "var(--f-text)", tip: "tf-idf over the whole pool, pruning and filters, keep the top 1000." },
  { key: "features", label: "Features", color: "var(--f-neighbour)", tip: "Neighbour vote from similar train cases and authority, both leave-one-out." },
  { key: "net", label: "Net score", color: "var(--f-authority)", tip: "Scale each feature to 0–1 in the candidate set and add with the frozen weights." },
  { key: "explain", label: "Explain", color: "var(--z-reasoning)", tip: "Attach components and the train cases that cite each result." },
];
const fmtMs = (x) => (x == null ? "" : x < 1 ? `${x.toFixed(2)} ms` : x < 100 ? `${x.toFixed(1)} ms` : `${Math.round(x)} ms`);

export function pipelineStrip() {
  const cells = STAGES.map((s) => h("div", { class: "pipe-stage", style: { "--pc": s.color }, "data-tip": s.tip, tabindex: "0", "aria-label": s.label }, h("b", {}, s.label), h("span", { class: "ms" }, "–")));
  const foot = h("div", { class: "pipe-foot xs muted" }, "Run a search to see each stage light up with the time the server measured.");
  const el = h("section", { class: "card tight pipe-card", "aria-label": "Search pipeline", style: { padding: 0 } }, h("div", { class: "pipe-strip" }, cells), foot);
  let timer = null, i = 0;
  const reset = () => cells.forEach((c) => { c.classList.remove("active", "done", "skipped", "err", "shared"); c.style.setProperty("--pw", "0"); c.querySelector(".ms").textContent = "–"; });
  return {
    el,
    start() {
      clearInterval(timer); reset(); i = 0;
      clear(foot).append("Searching…");
      const tick = () => { cells.forEach((c, j) => c.classList.toggle("active", j === i % cells.length)); cells.forEach((c, j) => { if (j < i % cells.length) c.classList.add("done"); else c.classList.remove("done"); }); i += 1; };
      tick();
      timer = setInterval(tick, reducedMotion() ? 600 : 240);
    },
    finish(timing, clientMs) {
      clearInterval(timer); reset();
      const by = Object.fromEntries((timing || []).map((t) => [t.name, t]));
      const combined = by.rank;                                       // toy mode: one step covers three stages
      const durs = STAGES.map((s) => by[s.key]?.dur ?? (combined && ["first_stage", "features", "net"].includes(s.key) ? combined.dur : null));
      const max = Math.max(...durs.filter((d) => d != null), 0.001);
      STAGES.forEach((s, j) => {
        const c = cells[j], t = by[s.key], d = durs[j], ms = c.querySelector(".ms");
        const desc = t?.desc || (combined && ["first_stage", "features", "net"].includes(s.key) ? combined.desc : "");
        const show = () => {
          if (d == null && !t && !combined) { c.classList.add("skipped"); ms.textContent = "not reported"; return; }
          if (d == null) { c.classList.add("skipped"); ms.textContent = desc && /not applied/.test(desc) ? "not applied" : "n/a"; }
          else { const shared = combined && ["first_stage", "features", "net"].includes(s.key); c.classList.add("done"); c.classList.toggle("shared", !!shared); ms.textContent = shared ? `${fmtMs(d)} *` : d === 0 && desc ? "at load" : fmtMs(d); c.style.setProperty("--pw", String(Math.max(0.04, d / max))); }
          c.setAttribute("data-tip", `${s.tip}${desc ? ` Server: ${desc}.` : ""}`);
          c.setAttribute("aria-label", `${s.label}: ${ms.textContent}`);
        };
        if (reducedMotion()) show(); else setTimeout(show, j * 70);
      });
      const total = by.total?.dur;
      clear(foot).append(`Server ${total != null ? fmtMs(total) : "time not reported"} · round trip ${fmtMs(clientMs)} · measured for this search (wall time, one machine).${combined ? " * The toy ranker runs first stage, features and net score as one step; that step's time is shown on each." : ""}`);
    },
    fail() { clearInterval(timer); reset(); cells.forEach((c) => c.classList.add("skipped")); clear(foot).append("The search failed; no timings."); },
    destroy() { clearInterval(timer); },
  };
}
