// Public landing page (#/). Shown before sign-in and after sign-out. Every number comes from GET /api/public/landing (saved runs in results/),
// and the papers and credits from docs/research_notes.md and README.md through the same API. Nothing is typed by hand.
import { h, clear, fmt, reducedMotion } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { brandMark } from "/ui/brand.js";
import { button, badge, courtBadge, countUp, renderMarkdown, emptyState } from "/ui/components.js";
import { get } from "/ui/api.js";
import { navigate, toggleTheme, effectiveTheme } from "/ui/store.js";
import { navFor, ROLE_LABEL } from "/ui/router.js";
import { ladderOf } from "/ui/evaldata.js";
import { onVisible, revealOnScroll, scrollStory, smoothTo } from "/ui/scrollstory.js";

const ROLE_TEXT = {
  researcher: "Find precedents for a dev query, compare rankers side by side, run Boolean and phrase queries, save searches and keep a history.",
  analyst: "Everything a researcher sees, plus the evaluation dashboard, the leakage audit and the efficiency and crawl study.",
  admin: "Everything an analyst sees, plus the Index Inspector, system status and the user list.",
};
const SECTIONS = [["how", "How it works"], ["roles", "Roles"], ["evidence", "Evidence"], ["builtOn", "Built on"]];
const pct1 = (x) => `${(x * 100).toFixed(1)}%`;

export default async function landing({ container, onCleanup }) {
  document.title = "Pramaan";
  const cleanups = [];
  const root = h("div", { class: "landing" });
  clear(container).append(root);

  // ------------------------------------------------------------ sticky navigation with a section indicator
  const links = SECTIONS.map(([id, label]) => h("button", { type: "button", class: "lnav-link", "data-sec": id, onClick: () => smoothTo(root.querySelector(`#sec-${id}`)) }, label));
  const indicator = h("span", { class: "lnav-ind", "aria-hidden": "true" });
  const themeBtn = button("", { variant: "ghost", size: "sm", icon: effectiveTheme() === "dark" ? "sun" : "moon", title: "Toggle light and dark theme", onClick: () => { toggleTheme(); clear(themeBtn).append(icon(effectiveTheme() === "dark" ? "sun" : "moon")); } });
  const nav = h("header", { class: "lnav" }, h("div", { class: "lnav-in" },
    h("a", { class: "lnav-brand", href: "#/", "aria-label": "Pramaan home", onClick: (e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" }); } }, brandMark(30), h("span", {}, "Pramaan")),
    h("nav", { class: "lnav-links", "aria-label": "Sections" }, links, indicator), h("span", { class: "spacer" }), themeBtn, button("Sign in", { onClick: () => navigate("/signin") })));
  root.append(nav);
  const moveIndicator = (id) => {
    const l = links.find((x) => x.dataset.sec === id);
    links.forEach((x) => (x === l ? x.setAttribute("aria-current", "true") : x.removeAttribute("aria-current")));
    if (!l) { indicator.style.opacity = "0"; return; }
    indicator.style.opacity = "1"; indicator.style.transform = `translateX(${l.offsetLeft}px) scaleX(${l.offsetWidth / 100})`;
  };

  // ------------------------------------------------------------ hero (live card is filled when the data arrives)
  const liveSlot = h("div", { class: "live-slot" }, h("div", { class: "skel", style: { height: "260px", borderRadius: "var(--r-lg)" } }));
  const hero = h("section", { class: "hero", id: "sec-top", "aria-labelledby": "hero-h" },
    h("div", { class: "hero-copy" },
      h("span", { class: "eyebrow" }, "Prior case retrieval for Indian law"),
      h("h1", { id: "hero-h", class: "hero-h" }, "Find the earlier judgments a case should cite, and see why."),
      h("p", { class: "lede" }, "Give Pramaan the facts and issues of an undecided case. It ranks earlier judgments and shows the reasons for each result: which similar cases cite it, how often it is cited, and how the score splits."),
      h("div", { class: "row hero-cta" }, button("Sign in to try it", { variant: "", size: "lg", icon: "chevR", onClick: () => navigate("/signin") }), button("See how it works", { variant: "secondary", size: "lg", onClick: () => smoothTo(root.querySelector("#sec-how")) })),
      h("p", { class: "xs muted" }, "Research prototype built on the IL-PCSR corpus. Not legal advice.")),
    liveSlot);
  root.append(hero);

  const body = h("div", { class: "landing-body" }, h("div", { class: "skel", style: { height: "120px", borderRadius: "var(--r-lg)" } }));
  root.append(body);

  let d;
  try { d = await get("/api/public/landing"); } catch (e) {
    clear(liveSlot); clear(body).append(emptyState("The numbers could not be loaded", e.status === 0 ? "The server is not reachable. Start it and reload this page." : e.message, { kind: e.status === 0 ? "offline" : "error", action: button("Reload", { variant: "secondary", onClick: () => location.reload() }) }));
    return;
  }
  if (!d.available) {
    clear(liveSlot); clear(body).append(emptyState("No saved evaluation run on this machine yet", "Run the evaluation scripts described in the README, then reload. This page shows only numbers from saved runs.", { kind: "empty" }));
    return;
  }

  // ------------------------------------------------------------ live result card
  clear(liveSlot).append(liveCard(d, cleanups));

  // ------------------------------------------------------------ proof strip
  const rows = Object.fromEntries(d.headline.rows.map((r) => [r.key, r]));
  const proof = [["tfidf", "tf-idf (lnc.ltc)"], ["bm25", "BM25, tuned"], ["config_a", "Ours"], ["config_a_tf", "Ours + temporal filter"]];
  const proofEl = h("section", { class: "proof", "aria-label": "Headline results" }, h("div", { class: "proof-grid" }, proof.map(([k, label]) => {
    const r = rows[k], v = h("div", { class: "proof-num display" }, "0.000");
    const test = r?.test?.MAP;
    const cell = h("div", { class: `proof-cell${k === "config_a_tf" ? " best" : ""}` }, h("div", { class: "proof-label" }, label), v,
      h("div", { class: "xs muted" }, `MAP on dev, ${d.n_dev} queries`), test != null ? h("div", { class: "xs" }, h("span", { class: "muted" }, "Test, run once: "), h("b", { class: "num" }, fmt(test, 3))) : null);
    onVisible(cell, () => countUp(v, r?.dev?.MAP, { decimals: 3, dur: 900 }));
    return cell;
  })), h("p", { class: "xs muted proof-note" }, "MAP is mean average precision over the dev queries; the candidate pool is the 3,183 cases cited in the corpus, so absolute values are not comparable with open-web search."));
  body.replaceChildren(proofEl);

  // ------------------------------------------------------------ pipeline (scroll-driven)
  const w = d.pipeline.config_a?.weights || {};
  const ex = d.examples?.[0];
  const story = scrollStory([
    { id: "query", label: "Query", title: "Start from the facts and issues", text: "The query is the Facts and Issues of an undecided case. Only those two parts are used, as a lawyer would have them before the case is decided.", data: `${d.n_dev} dev queries are evaluated this way.`, modules: ["data/query_builder.py", "data/loader.py"] },
    { id: "scrub", label: "Scrub", title: "Remove citations from the query", text: "Citation strings inside the query text are removed before anything is scored, so a query cannot simply point at its own answer.", data: d.scrub_changed_queries != null ? `Scrubbing changed the text of ${d.scrub_changed_queries} dev queries; the audit measures the effect.` : null, modules: ["data/query_builder.py", "preprocess/tokenizer.py"] },
    { id: "first", label: "First stage", title: "Fetch a thousand candidates with tf-idf", text: "A classical inverted index scored with tf-idf (lnc.ltc) picks the first thousand candidates cheaply. The later stages only re-order these.", data: d.first_stage_recall_at_1000 != null ? `The first thousand contain ${pct1(d.first_stage_recall_at_1000)} of the labelled citations (recall@1000).` : null, modules: ["index/inverted.py", "ranking/vsm.py"] },
    { id: "score", label: "Net score", title: "Combine text, neighbours and authority", text: "Each candidate gets a net score: its text match, a vote from similar training cases that cite it, and a leave-one-out authority score. The weights were frozen from cross-validation on the training queries.", data: w.text != null ? `Frozen weights: text ${pct1(w.text)}, neighbours ${pct1(w.neighbour)}, authority ${pct1(w.authority)}.` : null, modules: ["ranking/netscore.py", "ranking/neighbours.py", "ranking/authority.py"] },
    { id: "explain", label: "Explain", title: "Show why each result is there", text: "Every result lists the similar training cases (ids and similarity) that cite it and splits its score into text, neighbours and authority. No case text is needed to show this.", data: ex ? `Example: dev query ${ex.qid} has ${ex.n_relevant} labelled citations; average precision is ${fmt(ex.systems.find((s) => s.key === "ours_t").AP, 3)} with Ours + temporal filter and ${fmt(ex.systems.find((s) => s.key === "tfidf").AP, 3)} with tf-idf.` : null, modules: ["ranking/explain.py"] },
  ], { title: "How it finds precedents" });
  const how = h("section", { class: "lsec", id: "sec-how", "aria-labelledby": "how-h" }, h("div", { class: "lsec-head reveal" }, h("span", { class: "eyebrow" }, "How it finds precedents"), h("h2", { id: "how-h", class: "display" }, "Five steps from a case to a ranked list")), story.el);
  body.append(how);

  // ------------------------------------------------------------ roles
  const roles = ["researcher", "analyst", "admin"];
  const rolesEl = h("section", { class: "lsec", id: "sec-roles", "aria-labelledby": "roles-h" }, h("div", { class: "lsec-head reveal" }, h("span", { class: "eyebrow" }, "Three roles"), h("h2", { id: "roles-h", class: "display" }, "What each role sees"),
    h("p", { class: "muted" }, "The local sign-in separates the workspaces. It is not access control for the dataset.")),
    h("div", { class: "role-grid" }, roles.map((r) => {
      const pages = navFor(r).flatMap((g) => g.items.map((x) => x.title));
      return h("article", { class: "role-tile reveal", style: { "--rc": `var(--role-${r})` }, tabindex: "0", "aria-label": `${ROLE_LABEL[r]}: pages ${pages.join(", ")}` },
        h("div", { class: "role-tile-top" }, h("span", { class: "role-tile-bar", "aria-hidden": "true" }), h("h3", {}, ROLE_LABEL[r]), h("p", { class: "small" }, ROLE_TEXT[r]), h("span", { class: "xs muted role-hint" }, `${pages.length} pages. Hover or focus to list them.`)),
        h("div", { class: "role-tile-more" }, h("ul", { class: "role-pages" }, pages.map((p) => h("li", {}, p))),
          button(`Continue as ${ROLE_LABEL[r]}`, { size: "sm", icon: "chevR", onClick: () => navigate("/signin", { role: r }) })));
    })));
  body.append(rolesEl);

  // ------------------------------------------------------------ evidence: ablation ladder + leakage audit
  const abl = ladderOf(d.pipeline.ablation || []);
  const maxAbl = Math.max(...abl.map((x) => x.MAP), 0.001), bigJump = abl.reduce((b, x, i) => (i && x.delta > (abl[b].delta ?? 0) ? i : b), 1);
  const ladder = h("div", { class: "card ladder reveal", "aria-label": "Ablation ladder on the dev queries" }, h("h3", {}, "Ablation ladder"), h("p", { class: "small muted" }, "MAP on the dev queries as signals are added to tf-idf, one at a time. The step with the largest gain is highlighted."),
    h("div", { class: "bars" }, abl.map((x, i) => h("div", { class: `bar-row${i === bigJump ? " ours" : ""}`, style: { "--i": Math.min(i, 11) } }, h("span", { class: "bar-label", title: x.label }, x.label), h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: { "--v": x.MAP / maxAbl } })), h("span", { class: "num small bar-val" }, fmt(x.MAP, 3))))));
  const lk = d.leakage.config_A;
  const leak = lk ? h("div", { class: "card leak reveal", "aria-label": "Leakage audit" }, h("div", { class: "row" }, h("h3", { class: "grow" }, "Leakage audit"), button("Replay", { variant: "ghost", size: "sm", icon: "shuffle", onClick: () => replay() })),
    h("p", { class: "small muted" }, `Scoring ${lk.n_queries} training queries with their own citations left in the graph inflates MAP. Leave-one-out removes the inflation.`),
    h("div", { class: "bars leak-bars" },
      [["Without leave-one-out", lk.without, "bad"], ["With leave-one-out", lk.with, "good"]].map(([label, v, kind], i) => h("div", { class: `bar-row leak-row ${kind}`, style: { "--i": i * 6 } }, h("span", { class: "bar-label" }, label), h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: { "--v": v } })), h("span", { class: "num small bar-val" }, fmt(v, 3))))),
    h("p", { class: "xs muted" }, "Metric: MAP of Config A on training queries. Every headline number in this app uses leave-one-out.")) : null;
  function replay() { const c = leak.querySelector(".leak-bars"); c.classList.remove("go"); void c.offsetWidth; requestAnimationFrame(() => c.classList.add("go")); }
  const evidence = h("section", { class: "lsec", id: "sec-evidence", "aria-labelledby": "ev-h" }, h("div", { class: "lsec-head reveal" }, h("span", { class: "eyebrow" }, "Evidence"), h("h2", { id: "ev-h", class: "display" }, "What was measured, including what inflates a score")), h("div", { class: "ev-grid" }, ladder, leak));
  body.append(evidence);
  [ladder, leak].filter(Boolean).forEach((c) => onVisible(c, () => { (c.querySelector(".bars") || c).classList.add("go"); }, { threshold: 0.3 }));

  // ------------------------------------------------------------ built on: papers, credits, scope
  const papers = d.notes?.papers || [];
  let all = false;
  const grid = h("div", { class: "paper-grid" });
  const paintPapers = () => { clear(grid).append(...(all ? papers : papers.slice(0, 6)).map((p) => h("article", { class: "paper" }, h("div", { class: "row" }, h("b", { class: "grow" }, p.short), p.status ? badge(p.status, p.status === "VERIFIED" ? "ok" : "warn") : null), h("p", { class: "small muted" }, p.did), p.take ? h("p", { class: "xs" }, h("b", {}, "We take: "), p.take) : null))); };
  paintPapers();
  const more = papers.length > 6 ? button("", { variant: "secondary", size: "sm", onClick: () => { all = !all; paintPapers(); more.textContent = all ? "Show fewer" : `Show all ${papers.length}`; } }) : null;
  if (more) more.textContent = `Show all ${papers.length}`;
  const scopeBox = h("div", { class: "card scope reveal" }, h("h3", {}, "Scope and limits"), h("div", { class: "stack small" }, h("p", {}, "Pramaan is a student research prototype, not legal advice. The candidate pool contains only precedents that are cited somewhere in the corpus, which favours citation-based signals, and the neighbour vote carries most of the gain. The test split was run once."), h("div", { class: "scope-api" }, h("span", { class: "muted xs" }, "Loading the data notice…"))));
  const builtOn = h("section", { class: "lsec", id: "sec-builtOn", "aria-labelledby": "bo-h" }, h("div", { class: "lsec-head reveal" }, h("span", { class: "eyebrow" }, "Built on"), h("h2", { id: "bo-h", class: "display" }, "Data and the papers behind it"), h("p", { class: "muted" }, "From docs/research_notes.md. Methods are credited to the papers that introduced them.")), grid, more && h("div", { class: "row" }, more), scopeBox);
  body.append(builtOn);

  // ------------------------------------------------------------ footer
  const prov = d.provenance?.updated;
  const foot = h("footer", { class: "lfoot" }, h("div", { class: "lfoot-in" }, h("div", { class: "row" }, brandMark(24), h("b", {}, "Pramaan"), h("span", { class: "muted small" }, "Pramaan: precedent finder for Indian law")),
    h("p", { class: "xs muted data-notice" }, "Data notice: the IL-PCSR corpus is gated and for research use only (CC BY-NC-SA 4.0). No case data is stored in this repository or shown here."),
    h("p", { class: "xs muted", "data-testid": "provenance" }, `Numbers come from saved runs on this machine${prov ? `, updated ${prov}` : ""}.`)));
  root.append(foot);

  // credits and limits text from the README (public endpoint), appended after first paint
  get("/api/public/about").then((a) => {
    const slot = scopeBox.querySelector(".scope-api"); clear(slot);
    const lim = (a.sections?.Limitations || "").split("\n").filter((l) => /^\s*[-*] /.test(l)).slice(0, 3).join("\n");
    const cred = a.sections?.["Data credits and licences"] || "";
    if (lim) slot.append(h("div", {}, h("b", {}, "From the README limitations"), renderMarkdown(lim)));
    if (cred) slot.append(h("div", { style: { marginTop: "var(--s-3)" } }, h("b", {}, "Data credits"), renderMarkdown(cred)));
  }).catch(() => { clear(scopeBox.querySelector(".scope-api")); });

  // ------------------------------------------------------------ scroll behaviour: reveal, section indicator
  revealOnScroll(root);
  const secEls = SECTIONS.map(([id]) => root.querySelector(`#sec-${id}`));
  if (typeof IntersectionObserver !== "undefined") {
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) moveIndicator(e.target.id.replace("sec-", "")); }), { rootMargin: "-40% 0px -55% 0px" });
    secEls.forEach((s) => s && io.observe(s)); io.observe(hero);
    cleanups.push(() => io.disconnect());
  }
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
  window.addEventListener("scroll", onScroll, { passive: true }); onScroll(); cleanups.push(() => window.removeEventListener("scroll", onScroll));
  const onResize = () => { const cur = links.find((x) => x.getAttribute("aria-current")); if (cur) moveIndicator(cur.dataset.sec); };
  window.addEventListener("resize", onResize); cleanups.push(() => window.removeEventListener("resize", onResize));
  return () => cleanups.forEach((f) => { try { f(); } catch (_) { /* ignore */ } });
}

/** The "live result" card: cycles the three example queries; only ids, courts, years and scores are shown. */
function liveCard(d, cleanups) {
  const ex = d.examples || [];
  if (!ex.length) return h("aside", { class: "live-card" }, emptyState("No per-query results saved", "The evaluation run has no per-query file on this machine.", { kind: "empty" }));
  let i = 0, paused = reducedMotion(), timer = null;
  const body = h("div", { class: "live-body" });
  const dots = h("div", { class: "live-dots", role: "tablist", "aria-label": "Example queries" }, ex.map((e, j) => h("button", { type: "button", role: "tab", class: "live-dot", "aria-label": `Example ${j + 1}: dev query ${e.qid}`, onClick: () => { go(j); } })));
  const pauseBtn = button("", { variant: "ghost", size: "sm", icon: paused ? "play" : "pause", title: paused ? "Resume cycling" : "Pause cycling", onClick: () => { paused = !paused; paintPause(); schedule(); } });
  pauseBtn.setAttribute("aria-pressed", String(paused));
  const paintPause = () => { clear(pauseBtn).append(icon(paused ? "play" : "pause", { size: 15 })); pauseBtn.title = paused ? "Resume cycling" : "Pause cycling"; pauseBtn.setAttribute("aria-label", pauseBtn.title); pauseBtn.setAttribute("aria-pressed", String(paused)); };
  const paint = (animate) => {
    const e = ex[i];
    const view = h("div", { class: "live-view" },
      h("div", { class: "row live-q" }, h("span", { class: "muted xs" }, "Dev query"), h("b", { class: "mono" }, e.qid), courtBadge(e.court), h("span", { class: "muted small" }, e.year || "year ?"), h("span", { class: "xs muted" }, `${e.n_relevant} labelled citations`)),
      h("div", { class: "bars live-bars go" }, e.systems.map((s, k) => h("div", { class: `bar-row${s.key === "ours_t" ? " ours" : ""}`, style: { "--i": k * 3 } }, h("span", { class: "bar-label" }, s.label), h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: { "--v": s.AP } })),
        h("span", { class: "num small bar-val" }, fmt(s.AP, 3))))),
      h("div", { class: "live-meta xs muted" }, e.systems.map((s) => h("span", {}, `${s.label.split(" ")[0]} R@10 `, h("b", { class: "num" }, fmt(s["R@10"], 2))))));
    if (animate && !reducedMotion()) { const old = body.firstChild; if (old) old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, fill: "forwards" }).onfinish = () => { clear(body).append(view); view.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 200, easing: "ease-out" }); }; else clear(body).append(view); }
    else clear(body).append(view);
    [...dots.children].forEach((b, j) => { b.setAttribute("aria-selected", String(j === i)); });
  };
  const go = (j) => { i = (j + ex.length) % ex.length; paint(true); schedule(); };
  const schedule = () => { clearTimeout(timer); if (!paused && !document.hidden) timer = setTimeout(() => go(i + 1), 5200); };
  cleanups.push(() => clearTimeout(timer));
  paint(false); schedule();
  return h("aside", { class: "live-card", "aria-label": "Live result from a saved run" },
    h("div", { class: "row live-head" }, h("span", { class: "live-pulse", "aria-hidden": "true" }), h("b", { class: "grow" }, "Live from a saved run"), pauseBtn),
    body, h("div", { class: "row live-foot" }, dots, h("span", { class: "xs muted grow", style: { textAlign: "right" } }, "Bars are average precision (AP) for one query.")),
    h("p", { class: "xs muted" }, d.example_rule));
}
