// Index Inspector (admin): term autosuggest with highlighted matches, postings drawn as blocks with a term-frequency heat, compression before and after
// (this term's postings and the per-zone totals), a skip-pointer jump demonstration on two real posting lists, and statistics cards.
// Only document ids, ordinals and term frequencies are shown; no case text. Everything is read from /api/index/stats and /api/inspect/index.
import { h, clear, fmt, debounce, reducedMotion } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { alertBox, button, emptyState, errorState, kpi, pageHead, skeletonCards, segmented, zoneLabel } from "/ui/components.js";
import { get } from "/ui/api.js";
import { setUrlState } from "/ui/store.js";
import { onVisible } from "/ui/scrollstory.js";

const mb = (b) => (b / 2 ** 20).toFixed(2);
const vbyteLen = (n) => Math.max(1, Math.ceil((Math.floor(Math.log2(Math.max(n, 1))) + 1) / 7));          // variable-byte code: 7 data bits per byte

/** Term input with grouped dictionary suggestions (GET /api/suggest, wildcard), matched prefix highlighted, arrow keys and Enter. */
function termInput({ label, placeholder, value = "", onPick }) {
  const input = h("input", { class: "input", placeholder, "aria-label": label, autocomplete: "off", spellcheck: "false", role: "combobox", "aria-expanded": "false", "aria-autocomplete": "list", value });
  const list = h("div", { class: "combo-list", role: "listbox", hidden: true });
  const el = h("div", { class: "combo" }, input, list);
  let items = [], sel = -1;
  const paint = () => {
    clear(list);
    const q = input.value.trim().toLowerCase().replace(/\*+$/, "");
    if (!items.length) list.append(h("div", { class: "combo-empty" }, "No dictionary term starts with that."));
    items.forEach((t, i) => list.append(h("div", { class: "combo-opt", role: "option", "aria-selected": String(i === sel), onMousedown: (e) => { e.preventDefault(); pick(t); } }, h("span", { class: "mono" }, h("mark", {}, t.slice(0, q.length)), t.slice(q.length)))));
  };
  const pick = (t) => { input.value = t; list.hidden = true; input.setAttribute("aria-expanded", "false"); onPick(t); };
  const suggest = debounce(async () => {
    const v = input.value.trim().toLowerCase().replace(/\*+$/, "");
    if (v.length < 2) { list.hidden = true; return; }
    try { const r = await get(`/api/suggest?term=${encodeURIComponent(v + "*")}`); items = (r.items || []).slice(0, 8); sel = -1; paint(); list.hidden = false; input.setAttribute("aria-expanded", "true"); } catch (_) { list.hidden = true; }
  }, 150);
  input.addEventListener("input", suggest);
  input.addEventListener("blur", () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { if (!items.length) return; e.preventDefault(); list.hidden = false; sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length; paint(); }
    else if (e.key === "Enter") { e.preventDefault(); if (sel >= 0 && !list.hidden) pick(items[sel]); else { list.hidden = true; onPick(input.value.trim()); } }
    else if (e.key === "Escape") list.hidden = true;
  });
  return { el, input, set(v) { input.value = v; } };
}

/** Intersect two sorted ordinal lists, optionally with skip pointers (every round(sqrt(len))-th posting), counting comparisons and recording steps. */
export function intersect(A, B, skips) {
  const sa = Math.max(2, Math.round(Math.sqrt(A.length))), sb = Math.max(2, Math.round(Math.sqrt(B.length)));
  let i = 0, j = 0, cmp = 0; const res = [], steps = [];
  while (i < A.length && j < B.length) {
    cmp++;
    if (A[i] === B[j]) { res.push(A[i]); steps.push({ i, j, t: "match" }); i++; j++; }
    else if (A[i] < B[j]) {
      let jumped = false;
      if (skips) while (i % sa === 0 && i + sa < A.length) { cmp++; if (A[i + sa] <= B[j]) { i += sa; jumped = true; } else break; }
      if (jumped) steps.push({ i, j, t: "skipA" }); else { i++; steps.push({ i, j, t: "stepA" }); }
    } else {
      let jumped = false;
      if (skips) while (j % sb === 0 && j + sb < B.length) { cmp++; if (B[j + sb] <= A[i]) { j += sb; jumped = true; } else break; }
      if (jumped) steps.push({ i, j, t: "skipB" }); else { j++; steps.push({ i, j, t: "stepB" }); }
    }
  }
  return { res, cmp, steps, sa, sb };
}

export default async function indexInspector({ container, params }) {
  container.append(pageHead("Index Inspector", "Look inside the inverted index: document frequency and idf, a term's postings as blocks coloured by term frequency, how compression shrinks them, and how skip pointers jump along real postings."));
  const body = h("div", { class: "stack" }, skeletonCards(2)); container.append(body);
  let st; try { st = await get("/api/index/stats"); } catch (e) { return clear(body).append(errorState(e, () => location.reload())); }
  const out = h("div", { class: "stack" }), skipBox = h("div", { class: "stack" });
  let cur = null, curB = null, zone = "all";

  const A = termInput({ label: "Term", placeholder: "Start typing a word, e.g. dowry or murd", value: params.term || "", onPick: (t) => lookup(t) });
  const B = termInput({ label: "Second term for the AND demo", placeholder: "Second term, e.g. murder", value: params.and || "", onPick: (t) => lookupB(t) });
  const finder = h("section", { class: "tile accent stack" }, h("h2", {}, "Term lookup"), h("div", { class: "row", style: { flexWrap: "nowrap" } }, h("div", { class: "grow" }, A.el), button("Look up", { icon: "search", onClick: () => lookup(A.input.value) })), out);

  async function fetchTerm(term) { return get(`/api/inspect/index?term=${encodeURIComponent(term)}&limit=500`); }
  async function lookup(term) {
    term = term.trim(); if (!term) return;
    setUrlState("/index", { term, and: curB?.term || "" }); clear(out).append(skeletonCards(1));
    try { cur = await fetchTerm(term); cur.term = term; } catch (e) { return clear(out).append(errorState(e, () => lookup(term))); }
    const zs = Object.entries(cur.zones).filter(([, v]) => v.df > 0).map(([z]) => z);
    if (!zs.includes(zone)) zone = zs.includes("all") ? "all" : zs[0] || "all";
    drawTerm(); drawSkips();
  }
  async function lookupB(term) {
    term = term.trim(); if (!term) return;
    try { curB = await fetchTerm(term); curB.term = term; } catch (e) { return clear(skipBox).append(errorState(e)); }
    setUrlState("/index", { term: cur?.term || "", and: term }); drawSkips();
  }
  const postingsOf = (r, z) => ((r?.zones?.[z]?.postings_preview) || (r?.zones?.[z]?.postings || []).map(([d, tf], k) => ({ doc_id: d, tf, ord: k }))).map((p) => ({ ...p, ord: p.ord ?? 0 })).sort((a, b) => a.ord - b.ord);

  function blocks(ps, cap = 240) {
    const maxTf = Math.max(...ps.map((p) => p.tf), 1), shown = ps.slice(0, cap);
    const grid = h("div", { class: "pblocks", role: "list", "aria-label": "Postings, one block per document" }, shown.map((p) => {
      const heat = Math.log1p(p.tf) / Math.log1p(maxTf);
      return h("span", { class: "pblock", role: "listitem", tabindex: "-1", style: { "--heat": `${Math.round(18 + heat * 82)}%` }, "data-tip": `doc ${p.doc_id} · ordinal ${p.ord} · tf ${p.tf}` });
    }));
    return h("div", { class: "stack", style: { gap: "var(--s-2)" } }, grid, h("div", { class: "row xs muted heat-legend" }, "term frequency", h("span", { class: "heat-bar", "aria-hidden": "true" }), `1 → ${maxTf}`, ps.length > cap ? h("span", {}, ` · first ${cap} of ${ps.length} postings shown`) : null));
  }
  function compression(ps, df) {
    // bytes per posting: raw = int32 doc id + int32 tf; coded = variable-byte of the gap and of the tf
    let prev = 0, coded = 0; ps.forEach((p) => { coded += vbyteLen(p.ord - prev || p.ord + 1) + vbyteLen(p.tf); prev = p.ord; });
    const raw = ps.length * 8;
    const mk = (label, bytes, color, cls) => h("div", { class: "bar-row", style: { gridTemplateColumns: "160px minmax(0,1fr) 90px" } }, h("span", { class: "bar-label" }, label), h("div", { class: "bar-track" }, h("div", { class: `bar-fill ${cls}`, style: { "--v": bytes / raw, background: color } })), h("span", { class: "num small bar-val" }, `${bytes.toLocaleString("en-US")} B`));
    const el = h("div", { class: "bars comp" }, mk("raw int32 pairs", raw, "var(--bar-muted)", "raw"), mk("gap + variable-byte", coded, "var(--brand)", "coded"));
    onVisible(el, () => el.classList.add("go"), { threshold: 0.2 });
    const gaps = ps.slice(0, 8).map((p, i) => (i ? p.ord - ps[i - 1].ord : p.ord));
    return h("div", { class: "stack" }, el, h("p", { class: "small" }, `${ps.length} postings${ps.length < df ? ` (the first ${ps.length} of ${df})` : ""}: ${raw.toLocaleString("en-US")} bytes as two int32 per posting, ${coded.toLocaleString("en-US")} bytes as gaps and variable-byte codes (${(raw / Math.max(coded, 1)).toFixed(1)}× smaller). `, h("span", { class: "muted" }, `First ordinals ${ps.slice(0, 8).map((p) => p.ord).join(", ")}; first gaps ${gaps.join(", ")}.`)));
  }
  function drawTerm() {
    const r = cur, zs = Object.entries(r.zones).filter(([, v]) => v.df > 0);
    const z = r.zones[zone] || zs[0]?.[1], ps = postingsOf(r, zone);
    const seg = zs.length ? segmented(zs.map(([k, v]) => ({ value: k, label: `${k === "all" ? "whole text" : k === "fi" ? "facts+issues" : zoneLabel(k)} · ${v.df}` })), zone, (v) => { zone = v; drawTerm(); drawSkips(); }, { label: "Zone" }) : null;
    clear(out).append(...[r.source === "toy" ? alertBox("Toy index: postings only.", "warn") : null,
      h("div", { class: "row" }, h("span", { class: "small" }, "Indexed form "), h("code", {}, r.indexed_form || r.term), h("span", { class: "muted small" }, `${r.n_docs || "?"} documents`), z?.idf_log10 != null ? h("span", { class: "badge info" }, `idf (log10) ${z.idf_log10}`) : null, z ? h("span", { class: "badge" }, `df ${z.df}`) : null, z ? h("span", { class: "badge" }, z.positions_kept ? "positions kept" : "no positions") : null),
      !zs.length ? emptyState("No document contains this term", "Try another spelling; the dictionary is stemmed.", { icon: "search" }) : h("div", { class: "stack" }, seg, h("h3", {}, "Postings as blocks"), blocks(ps), h("h3", {}, "Compression for this term, before and after"), compression(ps, z.df))].filter(Boolean));
  }

  function drawSkips() {
    clear(skipBox);
    if (!cur) return skipBox.append(h("p", { class: "small muted" }, "Look up a term first."));
    const a = postingsOf(cur, zone).map((p) => p.ord);
    skipBox.append(h("div", { class: "row", style: { flexWrap: "nowrap" } }, h("div", { class: "grow" }, B.el), button("Run AND", { icon: "play", onClick: () => lookupB(B.input.value) })));
    if (!curB) return skipBox.append(h("p", { class: "small muted" }, `Pick a second term to intersect with ${cur.term} (posting list of ${a.length}) and watch the pointers jump.`));
    const b = postingsOf(curB, zone).map((p) => p.ord);
    if (!a.length || !b.length) return skipBox.append(h("p", { class: "small muted" }, "One of the lists is empty in this zone."));
    const plain = intersect(a, b, false), skip = intersect(a, b, true), VIEW = 80;
    const row = (list, name, sk) => h("div", { class: "skiprow" }, h("span", { class: "skiplabel mono xs" }, name), h("div", { class: "skiptrack" }, list.slice(0, VIEW).map((v, i) => h("span", { class: `sb${i % sk === 0 && i + sk < list.length ? " has-skip" : ""}`, "data-i": i, "data-tip": `ordinal ${v}${i % sk === 0 && i + sk < list.length ? ` · skip pointer to position ${i + sk}` : ""}` }))));
    const ra = row(a, cur.term, skip.sa), rb = row(b, curB.term, skip.sb);
    const trackA = ra.querySelector(".skiptrack"), trackB = rb.querySelector(".skiptrack");
    const markA = h("span", { class: "skipmark", "aria-hidden": "true" }), markB = h("span", { class: "skipmark b", "aria-hidden": "true" });
    trackA.append(markA); trackB.append(markB);
    const cnt = h("div", { class: "ex-readouts" }, [["Comparisons without skips", plain.cmp], ["Comparisons with skips", skip.cmp], ["Documents in both", skip.res.length]].map(([l, v]) => h("div", { class: "ex-tile" }, h("div", { class: "xs muted" }, l), h("b", { class: "num ex-big" }, v.toLocaleString("en-US")))));
    let k = 0, timer = 0;
    const status = h("p", { class: "small", "aria-live": "polite" });
    const place = (step) => {
      const W = 18; markA.style.transform = `translateX(${Math.min(step.i, VIEW - 1) * W}px)`; markB.style.transform = `translateX(${Math.min(step.j, VIEW - 1) * W}px)`;
      [trackA, trackB].forEach((t, q) => { const idx = q ? step.j : step.i; t.parentElement.scrollLeft = Math.max(0, idx * W - 200); });
      const kind = { match: "match found", skipA: `jumped ahead along ${cur.term} with a skip pointer`, skipB: `jumped ahead along ${curB.term} with a skip pointer`, stepA: `advanced ${cur.term} by one`, stepB: `advanced ${curB.term} by one` }[step.t];
      status.textContent = `Step ${k} of ${skip.steps.length}: ${kind}.`;
      if (step.t === "match") { trackA.children[Math.max(0, step.i - 1)]?.classList.add("hit"); trackB.children[Math.max(0, step.j - 1)]?.classList.add("hit"); }
      if (step.t === "skipA") trackA.children[Math.min(step.i, VIEW - 1)]?.classList.add("landed"); if (step.t === "skipB") trackB.children[Math.min(step.j, VIEW - 1)]?.classList.add("landed");
    };
    const stop = () => { clearInterval(timer); timer = 0; playBtn.textContent = "Play"; };
    const reset = () => { stop(); k = 0; [...trackA.children, ...trackB.children].forEach((n) => n.classList?.remove("hit", "landed")); status.textContent = "Press Play or Step to watch the intersection with skip pointers."; markA.style.transform = markB.style.transform = "translateX(0)"; };
    const stepOnce = () => { if (k >= skip.steps.length) return stop(); place(skip.steps[k++]); };
    const playBtn = button("Play", { icon: "play", size: "sm", onClick: () => { if (timer) return stop(); if (k >= skip.steps.length) reset(); playBtn.textContent = "Pause"; if (reducedMotion()) { while (k < skip.steps.length) stepOnce(); stop(); return; } timer = setInterval(stepOnce, 260); } });
    skipBox.append(cnt, h("div", { class: "skipwrap" }, ra, rb), h("div", { class: "row" }, playBtn, button("Step", { variant: "secondary", size: "sm", onClick: () => { stop(); stepOnce(); } }), button("Reset", { variant: "ghost", size: "sm", onClick: reset })), status,
      h("p", { class: "xs muted" }, `Real postings from the index (${zone === "all" ? "whole text" : zone}). Skip pointers sit every round(√length) postings (${skip.sa} and ${skip.sb} here); the first ${VIEW} postings of each list are drawn. Lists are short, so the extra skip checks can cost as many comparisons as they save, as the saved benchmark below also shows.`));
    reset();
  }

  clear(body);
  if (st.source === "toy") { body.append(alertBox("The real index is not built on this machine; this is the toy corpus.", "warn", "alert"), finder); if (params.term) lookup(params.term); return; }
  const c = st.compression, zones = Object.entries(c.per_zone).filter(([, v]) => v.raw_bytes > 0), mx = Math.max(...zones.map(([, v]) => v.raw_bytes));
  const zoneBars = h("div", { class: "bars comp" }, zones.flatMap(([z, v], i) => [
    h("div", { class: "bar-row", style: { "--i": i, gridTemplateColumns: "150px minmax(0,1fr) 80px" } }, h("span", { class: "bar-label" }, `${z === "all" ? "whole text" : z} · raw`), h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: { "--v": v.raw_bytes / mx } })), h("span", { class: "num small bar-val" }, `${mb(v.raw_bytes)} MB`)),
    h("div", { class: "bar-row", style: { "--i": i, gridTemplateColumns: "150px minmax(0,1fr) 80px" } }, h("span", { class: "bar-label" }, `${z === "all" ? "whole text" : z} · coded`), h("div", { class: "bar-track" }, h("div", { class: "bar-fill coded", style: { "--v": v.compressed_bytes / mx } })), h("span", { class: "num small bar-val" }, `${mb(v.compressed_bytes)} MB`))]));
  onVisible(zoneBars, () => zoneBars.classList.add("go"), { threshold: 0.1 });
  body.append(h("div", { class: "bento" },
    ...[kpi("Documents", st.n_docs, { decimals: 0 }), kpi("Indexed tokens (whole text)", st.tokens_whole_text, { decimals: 0 }), kpi("Raw size (MB)", c.raw_int32_mb, { decimals: 1, hint: "int32 postings" }), kpi("Compressed (MB)", c.gap_vbyte_mb, { decimals: 1, hint: `gap + variable-byte, ${(c.raw_int32_mb / c.gap_vbyte_mb).toFixed(1)}× smaller` })].map((k) => h("div", { class: "b3" }, k))),
    finder,
    h("section", { class: "tile stack" }, h("h2", {}, "Skip-pointer jump on real postings"), skipBox),
    h("section", { class: "tile stack" }, h("h2", {}, "Compression before and after, per zone"), h("p", { class: "small muted" }, "Raw int32 arrays against gap-encoded variable-byte codes, as stored on disk (from the saved index report)."), zoneBars),
    st.skip_benchmark ? h("section", { class: "tile stack" }, h("h2", {}, "Skip pointers: saved benchmark"), h("div", { class: "ex-readouts" }, [["plain", st.skip_benchmark.plain], ["skip", st.skip_benchmark.skip]].map(([k, v]) => h("div", { class: "ex-tile" }, h("div", { class: "xs muted" }, `${k}: posting comparisons`), h("b", { class: "num ex-big" }, v.comparisons.toLocaleString("en-US")), h("div", { class: "xs muted" }, `${v.seconds} s`)))),
      h("p", { class: "small muted" }, `${st.skip_benchmark.pairs} random pairs of posting lists with df ≥ 50. Skips save ${(100 * (1 - st.skip_benchmark.skip.comparisons / st.skip_benchmark.plain.comparisons)).toFixed(0)}% of comparisons here; lists are short (at most the pool size), so the gain is small.`)) : null,
    h("section", { class: "tile stack" }, h("h2", {}, "Memory"), h("div", { class: "bars" }, Object.entries(st.in_memory_mb || {}).map(([z, v]) => h("div", { class: "bar-row go", style: { gridTemplateColumns: "150px minmax(0,1fr) 70px" } }, h("span", { class: "bar-label" }, z), h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: { "--v": v / Math.max(...Object.values(st.in_memory_mb)), background: "var(--info)" } })), h("span", { class: "num small bar-val" }, `${v} MB`))))));
  if (params.term) { lookup(params.term).then(() => { if (params.and) lookupB(params.and); }); } else drawSkips();
}
