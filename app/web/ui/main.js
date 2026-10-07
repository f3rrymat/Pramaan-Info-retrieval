// Bootstrap: settings, session, routing, error boundaries, expired-session handling.
import { h, clear } from "/ui/dom.js";
import { get, post, bus } from "/ui/api.js";
import { applySettings, session, setRole, navigate, parseHash } from "/ui/store.js";
import { resolve, routeFor, LANDING } from "/ui/router.js";
import { buildShell, installShortcuts } from "/ui/shell.js";
import { errorState, emptyState, skeletonCards, toast, button } from "/ui/components.js";
import { swapPage } from "/ui/motion.js";
import { installProgressBar, sessionDialog, stopWatching } from "/ui/netstate.js";
import { teardownAssistant } from "/ui/assistant/panel.js";

applySettings();
installProgressBar();
const root = document.getElementById("app");
let shell = null, cleanup = [], renderToken = 0, lastPath = null;

async function loadMe() {
  const me = await get("/api/auth/me");
  Object.assign(session, { me: me.user, auth_required: me.auth_required, mode: me.mode, show_text: me.show_text, reason: me.reason, quick_login: !!me.quick_login });
  setRole(me.user ? me.user.role : null);
  return me;
}

async function render() {
  const token = ++renderToken;
  cleanup.forEach((f) => { try { f(); } catch (_) { /* page cleanup must not break navigation */ } });
  cleanup = [];
  let { route, path, params } = resolve();
  document.documentElement.setAttribute("data-route", path);
  if (path === "/" || (!route && !session.me)) { if (session.me) return navigate(LANDING[session.me.role], {}, { replace: true }); if (path !== "/") return navigate("/signin", {}, { replace: true }); }
  if (!session.me && !(route && route.public)) return navigate("/signin", { next: location.hash.slice(1) }, { replace: true });
  if (session.me && route && route.path === "/signin") return navigate(LANDING[session.me.role], {}, { replace: true });
  if (route && route.bare) {
    shell = null;
    clear(root);
    const mod = await route.load();
    if (token !== renderToken) return;
    const done = await mod.default({ container: root, params, session, onSignedIn, onCleanup: (f) => cleanup.push(f) });
    if (typeof done === "function") cleanup.push(done);
    return;
  }
  if (!session.me && route && route.public) { shell = null; }
  if (session.me && (!shell || !root.contains(shell.page))) shell = buildShell(root, session.me, { onSignOut: signOut });
  if (!session.me) { clear(root); shell = { page: root.appendChild(h("main", { class: "page", id: "page" })), setActive() {}, setCrumb() {} }; }
  const page = shell.page;
  if (lastPath && lastPath !== path) { await swapPage(page, () => { clear(page); page.append(skeletonCards(3)); }); if (token !== renderToken) return; }
  lastPath = path;
  clear(page);
  if (!route) { page.append(emptyState("Page not found", `There is no page at ${path}.`, { icon: "search", action: button("Go to the start", { onClick: () => navigate(LANDING[session.me.role]) }) })); shell.setCrumb({ title: "Not found", group: null }); return; }
  if (!route.roles.includes(session.me?.role || "researcher") && !route.public) {
    page.append(emptyState("This page is not part of your role", `The ${session.me.role} role cannot open ${route.title}. Ask an admin to change the role if you need it.`, { icon: "lock", action: button("Go to my start page", { onClick: () => navigate(LANDING[session.me.role]) }) }));
    shell.setCrumb(route); return;
  }
  shell.setActive(route.path); shell.setCrumb(route);
  if (!page.querySelector("[role=status]")) page.append(skeletonCards(3));
  const slow = setTimeout(() => { if (token === renderToken && page.querySelector("[role=status]")) page.append(h("p", { class: "still-loading muted small", role: "status" }, "Still loading. The server is working on it; this page will appear when it answers.")); }, 2000);
  try {
    const mod = await route.load();
    if (token !== renderToken) return;
    clear(page);
    const ctx = { container: page, route, path, params, session, setCrumb: (x) => shell.setCrumb(route, x), onCleanup: (f) => cleanup.push(f), signal: null };
    const done = await mod.default(ctx);
    clearTimeout(slow);
    if (typeof done === "function") cleanup.push(done);
    page.focus({ preventScroll: true });
  } catch (e) {
    clearTimeout(slow);
    if (token !== renderToken) return;
    console.error(e);
    clear(page).append(errorState(e, render));
  }
}

async function onSignedIn(opts = {}) { await loadMe(); const next = parseHash().params.next; if (opts.land) navigate(opts.land, {}, { replace: true }); else if (next && next !== "/signin") location.hash = `#${next.replace(/^#/, "")}`; else navigate(LANDING[session.me.role], {}, { replace: true }); render(); }
async function signOut() { teardownAssistant(); stopWatching(); try { await post("/api/auth/signout", {}); } catch (_) { /* ignore */ } session.me = null; setRole(null); shell = null; navigate("/"); }
document.addEventListener("app:signout", signOut);
bus.addEventListener("auth:lost", (e) => {
  if (!session.me || !session.auth_required) return;
  const expired = e.detail?.code === "session_expired";
  const full = () => { session.me = null; setRole(null); shell = null; teardownAssistant(); stopWatching(); navigate("/signin", { next: location.hash.slice(1).replace(/^\/signin.*/, "") }, { replace: true }); };
  sessionDialog({ username: session.me.username, quick: session.quick_login, roleName: session.me.role, onFull: full,
    onDone: async () => { try { await loadMe(); render(); } catch (_) { full(); } } });
  if (!expired) toast("Please sign in to continue.", "err");
});
document.addEventListener("app:reconnected", () => { if (session.me) render(); });
window.addEventListener("hashchange", render);
window.addEventListener("error", (e) => console.error("uncaught", e.message));

(async () => {
  try { await loadMe(); } catch (e) { clear(root).append(errorState(e, () => location.reload())); return; }
  installShortcuts();
  render();
})();
