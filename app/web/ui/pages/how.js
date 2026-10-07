// How it works: a scroll-driven pipeline and the lecture-to-code concept map. Numbers come from /api/public/*.
import { h, clear, fmt } from "/ui/dom.js";
import { alertBox, badge, emptyState, hbar, legend, pageHead, skeletonCards, stackBar, table, FEATURE_LABEL } from "/ui/components.js";
import { get } from "/ui/api.js";
import { barsCI } from "/ui/charts.js";
import { scrollStory } from "/ui/scrollstory.js";
import { reducedMotion } from "/ui/dom.js";

const CONCEPTS = [
  ["Boolean retrieval, query optimisation", "AND smallest posting list first, with skip pointers", "query/boolean.py, index/skips.py"],
  ["Vocabulary, postings, positions", "tokeniser, Porter stemmer, per-zone inverted and positional index", "preprocess/*, index/inverted.py"],
  ["Tolerant retrieval", "3-gram wildcards, edit-distance suggestions, Soundex", "query/tolerant.py"],
  ["Index compression", "gap encoding with variable-byte codes", "index/compress.py"],
  ["tf-idf and the vector space model", "SMART lnc.ltc cosine; BM25 as a tuned baseline", "ranking/vsm.py, ranking/bm25.py"],
  ["Static quality and the net score", "authority from citation in-degree, weighted by random search", "ranking/authority.py, ranking/netscore.py"],
  ["Efficient scoring", "heap top-K, index elimination, champion lists, authority tiers, cluster pruning", "efficiency/*"],
  ["Evaluation", "P, R, F1, MAP, MRR, nDCG, PR curves, paired bootstrap, leakage audit", "evaluation/*"],
  ["Rank fusion (beyond the syllabus)", "reciprocal rank fusion of issue sub-queries", "query/decompose.py"],
  ["Crawling", "front and back queues, politeness clock, URL normalisation, shingle duplicates (simulation)", "crawl/*"],
];

export default async function how({ container }) {
  container.append(pageHead("How it works", "From the facts and issues of a case to a ranked, explained list of earlier judgments. Scroll to walk through the pipeline."));
  let p = { available: false };
  const sk = skeletonCards(2); container.append(sk);
  try { p = await get("/api/public/pipeline"); } catch (_) { /* the explanation still works without numbers */ }
  sk.remove();
  const w = p.config_a?.weights, steps = [
    ["Query", "The facts and issues of the case are the query. Case-citation strings (AIR, SCC, SCR, SCALE and “party v. party (year)”) are removed first, so the query cannot point at its own answer.", h("div", { class: "row", style: { gap: "6px" } }, ["AIR 1973 SC 1461", "(2005) 3 SCC 112", "State v. Name (1990)"].map((t) => h("span", { class: "chip mono", style: { textDecoration: "line-through", opacity: ".7" } }, t)), badge("removed", "ok"))],
    ["Analyse", "Words are lower-cased, stop words dropped and stems taken (Porter). Statute references such as s.302 and art.21 stay whole. The dataset masks entities in query text, so those placeholders are stripped.", h("div", { class: "row", style: { gap: "6px" } }, ["the accused were convicted under Section 302", "→", "accus  convict  s.302"].map((t, i) => h("span", { class: i === 1 ? "muted" : "chip mono" }, t)))],
    ["First stage", `tf-idf (SMART lnc.ltc) over the whole text of every precedent in the pool${p.index ? ` (${p.index.n_docs.toLocaleString()} documents)` : ""} keeps the top 1000 candidates.`, p.dev ? alertBox(`Dev recall at 1000: ${fmt(p.dev.first_stage_recall_at_1000, 3)}. Every later stage can only reorder these, so this is a ceiling.`, "", "target") : null],
    ["Three signals", "For every candidate: the text score; a neighbour vote (the train cases most similar to the query vote for the precedents they cite); and authority (log of how often the case is cited, never counting the query itself).", w ? h("div", { class: "stack" }, stackBar(["text", "neighbour", "authority"].map((k) => ({ key: k, value: w[k] }))), legend(["text", "neighbour", "authority"]), h("p", { class: "xs muted" }, `Frozen weights from 5-fold cross-validation on ${p.config_a.train_queries.toLocaleString()} train queries: ${["text", "neighbour", "authority"].map((k) => `${FEATURE_LABEL[k]} ${(w[k] * 100).toFixed(0)}%`).join(", ")}. Neighbours: k = ${p.config_a.neighbour.k}, similarity power p = ${p.config_a.neighbour.p}.`)) : null],
    ["Net score", "Each signal is scaled to 0–1 within the candidate set and combined with the frozen weights. An optional temporal filter drops candidates that are not strictly earlier than the query where both dates are known.", p.ablation ? h("div", {}, h("div", { class: "label" }, "Dev MAP as each piece is added"), barsCI(p.ablation.filter((r) => !r.row.startsWith("7 +") || r.row.includes("config A_")).slice(0, 8).map((r) => ({ label: r.row.replace(/\(candidates.*?\)/, "").trim(), value: r.MAP, color: r.MAP > 0.15 ? "var(--f-neighbour)" : "var(--bar-muted)" })), { left: 300, width: 700, rowH: 26 })) : null],
    ["Explain", "Every result lists which signals carried it, the ids and similarities of the train cases that cite it, and shared statutes. Nothing is a black box, and no case text is shown unless the server runs with SHOW_TEXT=1.", p.leave_one_out ? alertBox(`Leave-one-out matters: scoring train queries without it would inflate MAP from ${fmt(p.leave_one_out.with, 3)} to ${fmt(p.leave_one_out.without, 3)}. The shipped system never lets a query vote for itself.`, "warn", "alert") : null],
  ];
  const CONCEPT_OF = [
    [["Tokenisation, stems", "preprocess/tokenizer.py"], ["Citation scrubbing", "data/query_builder.py"]],
    [["Vocabulary, postings", "index/inverted.py"], ["Positions", "index/positional.py"]],
    [["tf-idf (lnc.ltc)", "ranking/vsm.py"], ["Heap top-K", "efficiency/heap.py"]],
    [["Neighbour vote", "ranking/neighbours.py"], ["Authority, leave-one-out", "ranking/authority.py"]],
    [["Net score", "ranking/netscore.py"], ["Temporal filter", "query/temporal.py"]],
    [["Explanations", "ranking/explain.py"], ["Evaluation", "evaluation/metrics.py"]],
  ];
  const story = scrollStory(steps.map(([t, text, extra], i) => ({ id: `s${i}`, label: t, title: t, text, extra, concepts: CONCEPT_OF[i] })), { title: "From a case to a ranked list", onConcept: (label) => {
    const row = container.querySelector(`tr[data-concept="${CSS.escape(label)}"]`) || container.querySelector(`tr[data-module*="${CSS.escape(label.split(" ")[0].toLowerCase())}"]`);
    const tbl = container.querySelector(".concept-table"); (row || tbl)?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
    if (row) { row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1600); }
  } });
  container.append(story.el);
  container.append(h("section", { class: "card stack" }, h("h2", {}, "Lecture topic to code"), (() => { const tb = table(["Lecture concept", "What was built", "Module"], CONCEPTS.map(([a, b, c]) => [a, b, h("code", {}, c)])); tb.classList.add("concept-table"); tb.querySelectorAll("tbody tr").forEach((tr, i) => { tr.setAttribute("data-module", CONCEPTS[i][2].toLowerCase()); tr.setAttribute("data-concept", CONCEPTS[i][0]); }); return tb; })(),
    p.index ? h("p", { class: "small muted" }, `Index: ${p.index.n_docs.toLocaleString()} documents, ${p.index.tokens.toLocaleString()} indexed tokens, ${p.index.compressed_mb} MB with gap and variable-byte codes against ${p.index.raw_mb} MB raw.`) : null,
    h("p", { class: "small muted" }, "Role-based queries are not our idea (TraceRetriever did that). The neighbour feature combines known ideas (citation collaborative filtering and nearest-neighbour citation retrieval); it is not a new method. The pool holds only precedents cited somewhere in the corpus, which favours citation-based signals.")));
}
