// Real in-flight progress bar, status chip that polls /api/health every 30 s, offline banner with exponential backoff, and the expired-session dialog.
import { h, clear, reducedMotion } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { bus, get, post } from "/ui/api.js";
import { button, modal, toast, alertBox } from "/ui/components.js";

// ---------------------------------------------------------------- progress bar (driven by api.js in-flight requests)
export function installProgressBar() {
  if (document.querySelector(".netbar")) return;
  const bar = h("div", { class: "netbar", role: "progressbar", "aria-hidden": "true" }, h("i", {}));
  document.body.append(bar);
  const fill = bar.firstChild;
  let showTimer = 0, hideTimer = 0, on = false;
  bus.addEventListener("net:inflight", (e) => {
    const n = e.detail.n;
    if (n > 0 && !on) {
      clearTimeout(hideTimer);
      showTimer = setTimeout(() => { on = true; bar.classList.add("on"); fill.style.transition = "none"; fill.style.transform = "scaleX(.08)"; void fill.offsetWidth; fill.style.transition = ""; fill.style.transform = "scaleX(.85)"; }, 120);   // not for instant requests
    } else if (n === 0) {
      clearTimeout(showTimer);
      if (on) { fill.style.transform = "scaleX(1)"; hideTimer = setTimeout(() => { bar.classList.remove("on"); on = false; }, reducedMotion() ? 0 : 220); }
    }
  });
}

// ---------------------------------------------------------------- status polling, offline banner with backoff
const state = { online: true, mode: null, text: null, checked: null, poll: 0, retry: 0, attempt: 0, banner: null, chip: null, onBack: null, listeners: new Set() };
export const netStatus = () => ({ online: state.online, checked: state.checked });
const stamp = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

async function check() {
  try {
    const r = await get("/api/health");
    state.checked = stamp(); state.mode = r.mode; state.text = r.show_text;
    if (!state.online) setOnline(true);
    paintChip(); return true;
  } catch (e) {
    state.checked = stamp();
    if (e.status === 0 && state.online) setOnline(false);
    paintChip(); return false;
  }
}
function setOnline(v) {
  state.online = v; paintChip();
  if (v) { clearTimeout(state.retry); state.attempt = 0; state.banner?.remove(); state.banner = null; toast("The server is back.", "ok"); state.onBack && state.onBack(); }
  else { showBanner(); backoff(); }
}
function backoff() {
  clearTimeout(state.retry);
  const wait = Math.min(30, 2 ** (state.attempt + 1));            // 2, 4, 8, 16, 30 s
  state.attempt += 1; let left = wait;
  const tick = () => { if (state.online) return; setBannerText(left); if (left-- <= 0) { check().then((ok) => { if (!ok) backoff(); }); } else state.retry = setTimeout(tick, 1000); };
  tick();
}
function setBannerText(left) { const n = state.banner?.querySelector(".retry-in"); if (n) n.textContent = left > 0 ? `Trying again in ${left} s.` : "Trying now…"; }
function showBanner() {
  if (state.banner) return;
  state.banner = h("div", { class: "offline-banner", role: "alert" }, icon("alert", { size: 18 }), h("div", { class: "grow" }, h("b", {}, "The server is not reachable."), " Your page and filters are kept. ", h("span", { class: "retry-in" }, "")),
    button("Retry now", { size: "sm", variant: "secondary", onClick: () => { state.attempt = 0; clearTimeout(state.retry); setBannerText(0); check().then((ok) => { if (!ok) backoff(); }); } }));
  document.body.prepend(state.banner);
}
function paintChip() {
  const c = state.chip; if (!c) return;
  const real = state.mode === "real";
  c.className = `mode-chip ${!state.online ? "off" : real ? "real" : "toy"}`;
  const dot = c.querySelector(".dot"), txt = c.querySelector(".mode-text");
  dot.style.setProperty("--dc", !state.online ? "var(--err)" : real ? "var(--ok)" : "var(--warn)");
  txt.textContent = !state.online ? "Offline" : real ? `Real data · text ${state.text ? "shown" : "hidden"}` : "Toy data";
  c.setAttribute("data-tip", `${!state.online ? "The server did not answer." : real ? (state.text ? "Real index. Case titles and 200-character snippets are shown (SHOW_TEXT=1)." : "Real index. Case text and titles are hidden; results show ids, courts, years and scores.") : "Toy data: a 20-case fictional corpus. Not real results."} Last checked ${state.checked || "just now"}; checked every 30 s.`);
}
/** Attach the top-bar chip (built by the shell) and start the 30 s poll. onBack runs when the server returns. */
export function watchStatus(chip, { mode, show_text, onBack }) {
  state.chip = chip; state.mode = mode; state.text = show_text; state.onBack = onBack; state.checked = stamp(); paintChip();
  clearInterval(state.poll); state.poll = setInterval(() => { if (!document.hidden) check(); }, 30000);
}
export function stopWatching() { clearInterval(state.poll); clearTimeout(state.retry); state.chip = null; state.banner?.remove(); state.banner = null; state.online = true; state.attempt = 0; }
bus.addEventListener("net:down", () => { if (state.online && state.chip) setOnline(false); });

// ---------------------------------------------------------------- expired session: sign in again without leaving the page
let dlg = null;
export function sessionDialog({ username, quick, roleName, onDone, onFull }) {
  if (dlg) return;
  const pw = h("input", { class: "input", type: "password", autocomplete: "current-password", "aria-label": "Password" });
  const user = h("input", { class: "input", value: username || "", autocomplete: "username", "aria-label": "Username" });
  const err = h("div", { "aria-live": "assertive" });
  const go = async (fn) => { clear(err); try { await fn(); dlg.close(); dlg = null; toast("Signed in again. You are back where you were.", "ok"); onDone(); } catch (e) { clear(err).append(alertBox(e.status === 401 ? "Invalid username or password." : e.message, "err", "alert")); } };
  const form = h("form", { class: "stack", onSubmit: (e) => { e.preventDefault(); go(() => post("/api/auth/signin", { username: user.value, password: pw.value })); } },
    h("p", { class: "small" }, "Your session ended. Sign in again to continue; the page, filters and results you were looking at stay as they are."),
    h("div", { class: "stack", style: { gap: "var(--s-2)" } }, h("label", { class: "label" }, "Username"), user, h("label", { class: "label" }, "Password"), pw), err,
    h("div", { class: "row" }, button("Sign in", { type: "submit" }), quick && roleName ? button(`Continue as ${roleName}`, { variant: "secondary", onClick: () => go(() => post("/api/auth/quick", { role: roleName })) }) : null, h("span", { class: "grow" }), button("Go to the sign-in page", { variant: "ghost", size: "sm", onClick: () => { dlg.close(); dlg = null; onFull(); } })));
  dlg = modal({ title: "Session expired", body: form, className: "session-modal", onClose: () => { dlg = null; } });
  (username ? pw : user).focus();
}
