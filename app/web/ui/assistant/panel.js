// AI assistant (Sarvam): one component used as a floating side panel on every page and as the full page #/assistant.
// Text in -> text reply. Voice in -> text reply + spoken reply (the text is always shown). Settings may override.
// The browser talks only to /api/assistant/*; the server calls Sarvam. Case text is never sent (D42); context is ids and numbers.
import { h, clear, append, $ } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { button, copyText, renderMarkdown, toast } from "/ui/components.js";
import { post, postBinary } from "/ui/api.js";
import { getSettings, parseHash, navigate } from "/ui/store.js";
import * as S from "/ui/assistant/state.js";
import { Recorder, Speaker, canRecord } from "/ui/assistant/audio.js";

const LABEL = "AI assistant (Sarvam)";
const GREETING = "Hello. I am the AI assistant (Sarvam). I explain how this precedent retrieval system works, what its results mean and how it was evaluated. "
  + "I am an AI helper, not legal advice. I only see ids, courts, years, scores and saved aggregate results, never case text. Ask by typing, or press the microphone to speak.";
const SUGGEST = {
  "/search": ["How is the final score of a result combined?", "What does the neighbour score mean?", "Why is the temporal filter on by default?"],
  "/compare": ["Why do tf-idf and Config A rank differently?", "What does tuning BM25 change?", "What do the green dots mean?"],
  "/querylab": ["How does proximity search work here?", "What does Soundex do?", "Why do phrases only search facts and issues?"],
  "/evaluation": ["Why did the leave-one-out audit inflate MAP?", "Is Config A's gain over tf-idf significant?", "Why is P@10 low on this dataset?"],
  "/efficiency": ["Which pruning method keeps the most quality?", "What are champion lists?", "Did the priority crawler beat BFS?"],
  "/how": ["Explain the pipeline in three steps.", "What is leave-one-out and why does it matter?", "What is new in this project?"],
  "/index": ["How is the index compressed?", "What are skip pointers for?"],
  "/about": ["What are the main limitations?", "Which papers does this build on?"],
};
const DEFAULT_SUGGEST = ["What does this system do?", "How was it evaluated?", "What are the main limitations?"];
const STATE_TEXT = { idle: "", recording: "Recording", transcribing: "Transcribing your question…", thinking: "Thinking…", speaking: "Speaking", loading: "Preparing the spoken reply…", blocked: "Your browser blocked playback. Tap to play." };

export const speaker = new Speaker();
let live = null;                        // the mounted component (panel or page)
let panelHost = null;

/** Context for one search result: whitelisted ids and numbers only (never title or snippet). */
export function resultContext(r, { queryId, ranker, temporal, weights } = {}) {
  const comps = {};
  Object.entries(r.components || {}).forEach(([k, v]) => { if (typeof v === "number") comps[k] = v; });
  return { kind: "result", query_id: queryId || undefined, ranker, temporal_filter: temporal, weights: weights || undefined,
    results: [{ doc_id: r.doc_id, rank: r.rank, court: r.meta?.court || r.court, year: String(r.meta?.date || r.year || "").slice(0, 4), score: typeof r.net === "number" ? r.net : r.score, components: comps,
      relevant: typeof r.relevant === "boolean" ? r.relevant : undefined, neighbours: (r.explanation?.neighbours || []).slice(0, 5).map((n) => ({ neighbour_id: n.neighbour_id, similarity: n.similarity })) }] };
}

/** Open the assistant (panel, or the page if it is showing) with an optional pre-filled question and structured context. */
export function openAssistant({ question = "", context = null } = {}) {
  if (!live) { openPanel(); }
  live.prefill(question, context);
}
export function explainResult(r, opts) { openAssistant({ question: `Explain why result ${r.doc_id} is ranked #${r.rank}${opts?.queryId ? ` for dev query ${opts.queryId}` : ""}. What do its score components mean?`, context: resultContext(r, opts) }); }
export function explainMetric({ name, value }) { const page = parseHash().path.replace("/", "") || "this"; openAssistant({ question: `Explain the metric "${name}" on the ${page} page: what it measures and what this value tells us.`, context: { kind: "metric", metric: { name, value: typeof value === "number" ? value : undefined } } }); }

export function openPanel() {
  if (live && live.mode === "page") { live.focus(); return; }
  if (panelHost) { live.focus(); return; }
  const fab = $(".as-fab");
  fab && fab.setAttribute("aria-expanded", "true");
  panelHost = h("div", { class: "as-host" });
  document.body.append(panelHost);
  const comp = createAssistant({ mode: "panel", onClose: closePanel });
  panelHost.append(comp.el);
  comp.focus();
}
export function closePanel() {
  if (!panelHost) return;
  const comp = live; live = null;
  comp && comp.destroy();
  const host = panelHost; panelHost = null;
  const fab = $(".as-fab");
  if (fab) { fab.setAttribute("aria-expanded", "false"); fab.focus(); }
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches && document.documentElement.getAttribute("data-motion") !== "reduce" && host.firstChild?.animate) {
    const a = host.firstChild.animate([{ transform: "none", opacity: 1 }, { transform: "translateX(24px)", opacity: 0 }], { duration: 160, easing: "ease-in" });
    a.onfinish = () => host.remove();
  } else host.remove();
}
/** Floating button for every page (added by the shell). */
export function assistantFab() {
  const b = h("button", { class: "as-fab", type: "button", "aria-label": `Open the ${LABEL}`, "aria-expanded": "false", title: `${LABEL} (Alt+A)`, onClick: () => (panelHost ? closePanel() : openPanel()) }, icon("spark", { size: 22 }), h("span", { class: "as-fab-label" }, "Ask"));
  return b;
}
export function teardownAssistant() { speaker.stop(); if (panelHost) { live?.destroy(); panelHost.remove(); panelHost = null; } live = null; }

// ------------------------------------------------------------------ the component
export function createAssistant({ mode = "panel", onClose } = {}) {
  if (live) { live.destroy(); if (panelHost) { panelHost.remove(); panelHost = null; const f = $(".as-fab"); f && f.setAttribute("aria-expanded", "false"); } }
  const page = () => parseHash().path;
  let status = null, ctx = null, rec = null, state = "idle", pending = null, lastDetected = null, destroyed = false, wantFocus = false;
  const off = [];

  // header
  const langBtn = h("button", { class: "as-lang", type: "button", "aria-haspopup": "listbox", "aria-expanded": "false", title: "Reply language" });
  const langMenu = h("div", { class: "as-lang-menu", role: "listbox", "aria-label": "Reply language", hidden: true });
  const head = h("header", { class: "as-head" },
    h("div", { class: "as-title" }, h("span", { class: "as-logo", "aria-hidden": "true" }, icon("spark", { size: 18 }), h("i"), h("i"), h("i"), h("i"), h("i")), h("div", {}, h("h2", { id: `as-t-${mode}` }, LABEL), h("small", {}, "Explains the system and its results · not legal advice"))),
    h("div", { class: "as-head-actions" }, h("div", { class: "as-lang-wrap" }, langBtn, langMenu),
      button("", { variant: "ghost", size: "sm", icon: "trash", title: "Clear conversation", onClick: () => { speaker.stop(); S.clearConversation(); toast("Conversation cleared (it was kept in this browser tab only).", "ok"); } }),
      mode === "panel" ? button("", { variant: "ghost", size: "sm", icon: "layers", title: "Open as a full page", onClick: () => { closePanel(); navigate("/assistant"); } }) : null,
      mode === "panel" ? button("", { variant: "ghost", size: "sm", icon: "x", title: "Close the assistant (Esc)", onClick: () => onClose && onClose() }) : null));
  const notice = h("div", { class: "as-notice" });
  const log = h("div", { class: "as-log", role: "log", "aria-live": "polite", "aria-relevant": "additions", tabindex: "0", "aria-label": "Conversation" });
  const typing = h("div", { class: "as-msg assistant as-typing", hidden: true, "aria-hidden": "true" }, h("div", { class: "as-bubble" }, h("i"), h("i"), h("i")));
  const suggest = h("div", { class: "as-suggest", role: "group", "aria-label": "Suggested questions" });
  const ctxChip = h("div", { class: "as-ctx", hidden: true });
  const speakBar = h("div", { class: "as-speakbar", hidden: true, role: "status" });
  const live_ = h("div", { class: "sr-only", "aria-live": "assertive" });

  // composer
  const input = h("textarea", { class: "textarea as-input", rows: 1, placeholder: "Ask about the results, the metrics or how the system works…", "aria-label": "Your question", maxlength: 1000 });
  const send = h("button", { class: "btn as-send", type: "submit", title: "Send (Enter)", "aria-label": "Send" }, icon("send", { size: 17 }));
  const mic = h("button", { class: "as-mic", type: "button", "aria-label": "Speak your question", title: "Speak your question", "data-state": "idle" }, h("span", { class: "as-mic-ring", "aria-hidden": "true" }), icon("mic", { size: 22 }));
  const canvas = h("canvas", { class: "as-wave", width: 480, height: 56, "aria-hidden": "true" });
  const secs = h("span", { class: "as-secs num" }, "30");
  const recBox = h("div", { class: "as-rec", hidden: true }, h("span", { class: "as-rec-dot", "aria-hidden": "true" }), canvas, h("span", { class: "as-rec-time" }, secs, h("small", {}, " s left")),
    button("Stop and send", { size: "sm", icon: "send", onClick: () => finishRecording() }), button("", { size: "sm", variant: "ghost", icon: "x", title: "Cancel recording (Esc)", onClick: () => cancelRecording() }));
  const stateLine = h("div", { class: "as-state xs muted", "aria-hidden": "true" });
  const form = h("form", { class: "as-compose", onSubmit: (e) => { e.preventDefault(); const t = input.value.trim(); if (t) { input.value = ""; autosize(); send_(t, { inputMode: "text" }); } } },
    recBox, h("div", { class: "as-row" }, mic, h("div", { class: "as-input-wrap" }, input), send), stateLine);
  const el = h("section", { class: `as as-${mode}`, "data-mode": mode, "data-state": "idle", role: mode === "panel" ? "dialog" : "region", "aria-modal": mode === "panel" ? "false" : null, "aria-labelledby": `as-t-${mode}` },
    head, notice, log, suggest, ctxChip, speakBar, form, live_);

  // ---------------------------------------------------------------- rendering
  function setState(s, extra = "") {
    state = s; el.setAttribute("data-state", s); mic.setAttribute("data-state", s);
    const t = STATE_TEXT[s] ? `${STATE_TEXT[s]}${extra}` : "";
    stateLine.textContent = t; if (t) live_.textContent = t;
    mic.setAttribute("aria-label", s === "recording" ? "Stop recording and send" : s === "speaking" || s === "loading" || s === "blocked" ? "Stop speaking and record a new question" : "Speak your question");
    mic.setAttribute("aria-pressed", String(s === "recording"));
    const busy = s === "transcribing" || s === "thinking";
    send.disabled = busy || !status?.configured; input.disabled = !status?.configured;
    mic.disabled = busy || !status?.configured;
    typing.hidden = s !== "thinking";
    if (s === "thinking") scrollEnd();
  }
  function langLabel() {
    const forced = S.language();
    const list = status?.languages?.chat || [];
    const nm = (c) => list.find((x) => x.code === c)?.name || c;
    clear(langBtn).append(icon("globe", { size: 15 }), h("span", {}, forced !== "auto" ? nm(forced) : lastDetected ? `${nm(lastDetected)} · auto` : "Auto-detect"), icon("chevD", { size: 14 }));
    langBtn.setAttribute("aria-label", `Reply language: ${forced !== "auto" ? nm(forced) : "detected automatically"}. Change`);
  }
  function paintLangMenu() {
    const cur = S.language();
    const opts = [{ code: "auto", name: "Auto-detect", native: "" }, ...(status?.languages?.chat || [])];
    clear(langMenu).append(...opts.map((o, i) => h("div", { class: "as-lang-opt", role: "option", tabindex: "-1", id: `as-lo-${mode}-${i}`, "aria-selected": String(o.code === cur), "data-code": o.code,
      onClick: () => pickLang(o.code) }, h("span", {}, o.name), o.native && o.native !== o.name ? h("span", { class: "muted" }, o.native) : null)),
      h("p", { class: "xs muted as-lang-note" }, "Chat replies support these languages. Speech input understands more; spoken replies follow the same list. The rest of the app stays in English."));
  }
  function pickLang(code) { S.setLanguage(code); closeLangMenu(); langLabel(); langBtn.focus(); }
  function openLangMenu() { paintLangMenu(); langMenu.hidden = false; langBtn.setAttribute("aria-expanded", "true"); (langMenu.querySelector('[aria-selected="true"]') || langMenu.firstChild)?.focus(); }
  function closeLangMenu() { langMenu.hidden = true; langBtn.setAttribute("aria-expanded", "false"); }
  langBtn.addEventListener("click", () => (langMenu.hidden ? openLangMenu() : closeLangMenu()));
  langMenu.addEventListener("keydown", (e) => {
    const items = [...langMenu.querySelectorAll(".as-lang-opt")], i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus(); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); document.activeElement?.click(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeLangMenu(); langBtn.focus(); }
  });
  const away = (e) => { if (!langMenu.hidden && !langMenu.contains(e.target) && !langBtn.contains(e.target)) closeLangMenu(); };
  document.addEventListener("mousedown", away); off.push(() => document.removeEventListener("mousedown", away));

  function renderReply(text) {
    const t = text.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, "$1 ($2)").replace(/^#{1,6}\s+(.+)$/gm, "**$1**");
    return renderMarkdown(t);
  }
  function msgNode(m) {
    if (m.role === "user") return h("div", { class: "as-msg user", "data-id": m.id }, h("div", { class: "as-bubble" }, m.mode === "voice" ? h("span", { class: "as-via", title: "Asked by voice" }, icon("mic", { size: 13 })) : null, h("span", {}, m.content)));
    if (m.error) return h("div", { class: "as-msg assistant err", "data-id": m.id, role: "alert" }, h("div", { class: "as-bubble" }, h("div", { class: "row", style: { gap: "6px" } }, icon("alert", { size: 15 }), h("b", {}, "Could not answer")), h("p", { class: "small" }, m.content),
      m.retryText ? button("Retry", { size: "sm", variant: "secondary", icon: "refresh", onClick: () => { S.removeMessage(m.id); send_(m.retryText, { inputMode: m.inputMode || "text", voiceLang: m.voiceLang, retry: true }); } }) : null));
    const listen = button("Listen", { size: "sm", variant: "ghost", icon: "volume", title: "Read this answer aloud", onClick: () => speakMessage(m) });
    listen.classList.add("as-listen");
    return h("div", { class: "as-msg assistant", "data-id": m.id },
      h("div", { class: "as-bubble" }, renderReply(m.content), (m.notes || []).map((n) => h("p", { class: "xs muted as-note" }, n))),
      h("div", { class: "as-tools" }, m.langName ? h("span", { class: "as-tag xs" }, m.langName) : null, m.spoken ? h("span", { class: "as-tag xs" }, icon("volume", { size: 12 }), "spoken") : null,
        listen, button("Copy", { size: "sm", variant: "ghost", icon: "copy", title: "Copy this answer", onClick: async () => { try { await copyText(m.content); toast("Answer copied.", "ok"); } catch (_) { toast("Copy is not available here.", "err"); } } })));
  }
  function paint() {
    const list = S.messages();
    clear(log).append(h("div", { class: "as-msg assistant greeting" }, h("div", { class: "as-bubble" }, h("p", {}, GREETING))), ...list.map(msgNode), typing);
    paintSuggest();
    scrollEnd();
  }
  function appendOne(m) {
    const n = msgNode(m); log.insertBefore(n, typing);
    if (!(matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.getAttribute("data-motion") === "reduce") && n.animate) n.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 240, easing: "cubic-bezier(.2,.7,.2,1)" });
    paintSuggest(); scrollEnd();
  }
  function paintSuggest() {
    const qs = SUGGEST[page()] || DEFAULT_SUGGEST;
    clear(suggest);
    if (!status?.configured) return;
    if (S.messages().length > 4) return;
    suggest.append(...qs.map((q) => h("button", { class: "chip as-chip", type: "button", onClick: () => send_(q, { inputMode: "text" }) }, q)));
  }
  function scrollEnd() { requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; }); }
  function paintCtx() {
    clear(ctxChip);
    ctxChip.hidden = !ctx;
    if (!ctx) return;
    const what = ctx.kind === "metric" ? `metric "${ctx.metric?.name}"` : ctx.results?.length ? `result ${ctx.results[0].doc_id}${ctx.query_id ? ` for ${ctx.query_id}` : ""}` : "current view";
    ctxChip.append(icon("link", { size: 14 }), h("span", { class: "xs" }, `Context attached: ${what}. Only ids and numbers are sent.`), h("button", { class: "btn ghost sm icon", type: "button", title: "Remove the context", "aria-label": "Remove the context", onClick: () => { ctx = null; paintCtx(); } }, icon("x", { size: 14 })));
  }
  function autosize() { input.style.height = "auto"; input.style.height = `${Math.min(140, input.scrollHeight)}px`; }
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });

  function paintNotice() {
    clear(notice);
    if (!status) return;
    if (!status.configured) {
      notice.append(h("div", { class: "as-card as-unconfigured", role: "status" }, h("div", { class: "row", style: { gap: "8px" } }, icon("lock", { size: 16 }), h("b", {}, "Assistant not configured")),
        h("p", { class: "small muted" }, "This server has no SARVAM_API_KEY, so the assistant is off. Everything else in the app works as before.")));
      return;
    }
    if (pending && !S.consented()) {
      notice.append(h("div", { class: "as-card as-consent", role: "alertdialog", "aria-labelledby": `as-cons-${mode}` }, h("b", { id: `as-cons-${mode}` }, "Before you ask: what is sent to Sarvam AI"),
        h("p", { class: "small" }, status.privacy), h("p", { class: "xs muted" }, "Sarvam AI is a third-party service. This choice is remembered in this browser only."),
        h("div", { class: "row" }, button("Accept and continue", { icon: "check", onClick: () => { S.setConsent(true); const p = pending; pending = null; paintNotice(); p && p(); } }),
          button("Not now", { variant: "ghost", onClick: () => { pending = null; paintNotice(); input.focus(); } }))));
      notice.querySelector(".as-consent .btn")?.focus();
    }
  }
  function ready(action) {
    if (!status?.configured) { paintNotice(); return false; }
    if (!S.consented()) { pending = action; paintNotice(); return false; }
    return true;
  }

  // ---------------------------------------------------------------- talking
  async function send_(text, { inputMode = "text", voiceLang = null, retry = false } = {}) {
    if (!ready(() => send_(text, { inputMode, voiceLang, retry }))) { if (inputMode === "text" && !retry) input.value = text; return; }
    if (state === "thinking" || state === "transcribing") return;
    speaker.stop();
    const history = S.historyForServer();
    if (!retry) appendFromState({ role: "user", content: text, mode: inputMode });
    const usedCtx = ctx; ctx = null; paintCtx();
    setState("thinking");
    try {
      const r = await post("/api/assistant/chat", { message: text, history, input_mode: inputMode, speak_pref: getSettings().speakReplies || "follow", language: S.language(), voice_language: voiceLang, context: usedCtx, page: page() });
      if (destroyed) return;
      if (r.language) lastDetected = r.language; langLabel();
      const m = appendFromState({ role: "assistant", content: r.reply, lang: r.language, langName: r.language_name, notes: r.notes, spoken: !!r.speak, ttsLang: r.tts_language });
      setState("idle");
      if (r.speak) speakMessage(m, voiceLang);
    } catch (e) {
      if (destroyed) return;
      setState("idle");
      if (e.code === "not_configured") { status = { ...status, configured: false }; paintNotice(); setState("idle"); }
      appendFromState({ role: "assistant", error: true, content: e.message || String(e), retryText: text, inputMode, voiceLang });
    }
  }
  let painting = false;
  /** Store a message and append just its node (the store's change event must not trigger a full repaint here). */
  function appendFromState(m) { painting = true; let msg; try { msg = S.addMessage(m); } finally { painting = false; } appendOne(msg); return msg; }
  function ttsLangFor(m, fallback) {
    const tts = (status?.languages?.tts || []).map((x) => x.code);
    return [m.ttsLang, m.lang, fallback, S.language() !== "auto" ? S.language() : null, "en-IN"].find((c) => c && tts.includes(c));
  }
  function speakMessage(m, fallback) {
    if (!ready(() => speakMessage(m, fallback))) return;
    const lang = ttsLangFor(m, fallback);
    speaker.speak(m.content, lang, { msgId: m.id });
  }

  // speaker state -> UI
  const onSpeaker = (e) => {
    const { state: st, msgId, message } = e.detail;
    log.querySelectorAll(".as-msg.speaking").forEach((n) => n.classList.remove("speaking"));
    if (st === "speaking" || st === "loading" || st === "blocked") {
      if (rec) return;
      setState(st);
      const n = log.querySelector(`[data-id="${msgId}"]`); n && n.classList.add("speaking");
      append(clear(speakBar), [h("span", { class: "as-eq", "aria-hidden": "true" }, h("i"), h("i"), h("i"), h("i")), h("span", { class: "small" }, st === "blocked" ? "Playback was blocked by the browser." : st === "loading" ? "Preparing speech…" : "Speaking. The text stays above."),
        st === "blocked" ? button("Tap to play", { size: "sm", icon: "play", onClick: () => speaker.resume() }) : null,
        button("Stop speaking", { size: "sm", variant: "danger", icon: "stop", onClick: () => { speaker.stop(); input.focus(); } }), h("kbd", { class: "as-esc" }, "Esc")]);
      speakBar.hidden = false;
      if (st === "blocked") speakBar.querySelector(".btn")?.focus();
    } else {
      speakBar.hidden = true;
      if (state === "speaking" || state === "loading" || state === "blocked") setState("idle");
      if (st === "error") toast(`The spoken reply could not be played: ${message}. The text is shown above.`, "err");
    }
  };
  speaker.addEventListener("state", onSpeaker); off.push(() => speaker.removeEventListener("state", onSpeaker));

  // ---------------------------------------------------------------- voice input
  let paintLevelColor = null;
  function drawLevel(data) {
    const g = canvas.getContext("2d"), W = canvas.width, H = canvas.height;
    paintLevelColor = paintLevelColor || getComputedStyle(el).getPropertyValue("--role").trim() || getComputedStyle(el).color;
    g.clearRect(0, 0, W, H);
    const bars = 48, step = Math.floor(data.length / bars);
    g.fillStyle = paintLevelColor;
    for (let i = 0; i < bars; i += 1) {
      let peak = 0; for (let j = 0; j < step; j += 1) peak = Math.max(peak, Math.abs(data[i * step + j] - 128));
      const bh = Math.max(3, (peak / 128) * H * 1.6);
      g.fillRect(i * (W / bars) + 1, (H - Math.min(H, bh)) / 2, W / bars - 3, Math.min(H, bh));
    }
  }
  async function startRecording() {
    if (!ready(() => startRecording())) return;
    if (!canRecord()) { toast("Recording is not supported in this browser. Type your question instead.", "err"); return; }
    speaker.stop();
    const max = status?.limits?.max_audio_seconds || 30;
    rec = new Recorder({ maxSeconds: max - 0.5, onLevel: drawLevel, onTick: (_, left) => { const s = Math.ceil(left); if (secs.textContent !== String(s)) { secs.textContent = String(s); if (s % 10 === 0 || s <= 5) live_.textContent = `${s} seconds left`; } }, onAutoStop: () => finishRecording() });
    try { await rec.start(); }
    catch (e) { rec = null; setState("idle"); toast(e && e.name === "NotAllowedError" ? "Microphone access was denied. Allow it in the browser to speak your question." : `The microphone could not start (${e?.message || e}).`, "err"); return; }
    secs.textContent = String(Math.floor(max)); recBox.hidden = false; setState("recording");
  }
  async function finishRecording() {
    if (!rec) return;
    const r = rec; rec = null; recBox.hidden = true; setState("transcribing");
    try {
      const out = await r.stop();
      if (!out || out.seconds < 0.3) { setState("idle"); toast("That was too short. Hold the microphone a little longer.", "err"); return; }
      const lang = S.language();
      const t = await postBinary(`/api/assistant/stt?language=${encodeURIComponent(lang)}`, out.wav);
      if (destroyed) return;
      setState("idle");
      if (!t.transcript) { toast("I did not catch that. Try again a little closer to the microphone.", "err"); return; }
      if (t.language) lastDetected = t.language; langLabel();
      send_(t.transcript, { inputMode: "voice", voiceLang: t.language });
    } catch (e) { if (!destroyed) { setState("idle"); appendFromState({ role: "assistant", error: true, content: e.message || String(e) }); } }
  }
  function cancelRecording() { if (!rec) return; rec.cancel(); rec = null; recBox.hidden = true; setState("idle"); live_.textContent = "Recording cancelled"; }
  mic.addEventListener("click", () => {
    if (state === "recording") return finishRecording();
    if (speaker.speaking) { speaker.stop(); }
    startRecording();
  });

  // ---------------------------------------------------------------- keys, lifecycle
  const keys = (e) => {
    if (e.key !== "Escape") return;
    if (speaker.speaking) { e.preventDefault(); e.stopPropagation(); speaker.stop(); return; }
    if (rec) { e.preventDefault(); e.stopPropagation(); cancelRecording(); return; }
    if (mode === "panel" && el.contains(document.activeElement) && langMenu.hidden) { e.preventDefault(); onClose && onClose(); }
  };
  document.addEventListener("keydown", keys, true); off.push(() => document.removeEventListener("keydown", keys, true));
  const onChange = () => { if (!painting) paint(); };
  S.events.addEventListener("change", onChange); off.push(() => S.events.removeEventListener("change", onChange));
  const onHash = () => paintSuggest();
  addEventListener("hashchange", onHash); off.push(() => removeEventListener("hashchange", onHash));

  const comp = {
    el, mode,
    focus() { if (!status) { wantFocus = true; input.focus(); return; } (status.configured ? input : el.querySelector("button"))?.focus(); },
    prefill(q, c) { if (q) { input.value = q; autosize(); } ctx = c || null; paintCtx(); comp.focus(); input.setSelectionRange?.(input.value.length, input.value.length); },
    destroy() { destroyed = true; if (rec) { rec.cancel(); rec = null; } speaker.stop(); off.forEach((f) => f()); if (live === comp) live = null; },
  };
  live = comp;
  paint(); langLabel(); setState("idle");
  S.status().then((s) => { if (destroyed) return; status = s; paintNotice(); langLabel(); paintSuggest(); setState("idle"); if (wantFocus) { wantFocus = false; comp.focus(); } })
    .catch((e) => { if (destroyed) return; status = { configured: false }; clear(notice).append(h("div", { class: "as-card", role: "alert" }, h("b", {}, "The assistant is unavailable"), h("p", { class: "small muted" }, e.message || String(e)))); setState("idle"); });
  return comp;
}
