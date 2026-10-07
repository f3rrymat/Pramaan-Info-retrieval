// App shell: sidebar (grouped, collapsible, role-specific), top bar, command palette, shortcuts sheet, user menu.
import { h, clear, append, $ } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { brandMark } from "/ui/brand.js";
import { badge, button, modal, toast, getNotifications, notificationEvents } from "/ui/components.js";
import { watchStatus, stopWatching } from "/ui/netstate.js";
import { ROUTES, ROLE_LABEL, navFor } from "/ui/router.js";
import { get, post } from "/ui/api.js";
import { session, getSettings, setSetting, toggleTheme, effectiveTheme, navigate } from "/ui/store.js";
import { assistantFab, openPanel, closePanel, teardownAssistant } from "/ui/assistant/panel.js";

const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
export const MOD = isMac ? "⌘" : "Ctrl";

export function buildShell(root, me, { onSignOut }) {
  clear(root);
  const role = me.role;
  const s = getSettings();
  const app = h("div", { class: "app", "data-sidebar": s.sidebar === "collapsed" ? "collapsed" : "expanded", "data-nav-open": "false" });
  const closeNav = () => app.setAttribute("data-nav-open", "false");

  const navInd = h("span", { class: "nav-ind", "aria-hidden": "true" });
  const nav = h("nav", { class: "nav", "aria-label": "Main" }, navInd, navFor(role).map((g) => h("div", { class: "nav-group" }, h("div", { class: "nav-title" }, g.title),
    g.items.map((r) => h("a", { class: "nav-link", href: `#${r.path}`, "data-path": r.path, "data-tip": r.title, onClick: closeNav }, icon(r.icon), h("span", {}, r.title), r.keys && h("span", { class: "kbd-hint xs muted mono" }, r.keys.toUpperCase()))))));
  const collapse = button("", { variant: "ghost", size: "sm", icon: s.sidebar === "collapsed" ? "chevR" : "chevL", title: "Collapse or expand the sidebar", onClick: () => {
    const next = app.getAttribute("data-sidebar") === "collapsed" ? "expanded" : "collapsed"; app.setAttribute("data-sidebar", next); setSetting("sidebar", next); clear(collapse).append(icon(next === "collapsed" ? "chevR" : "chevL")); } });
  const sidebar = h("aside", { class: "sidebar", id: "sidebar" },
    h("a", { class: "app-brand", href: "#/" }, h("div", { class: "app-brand-mark", "aria-hidden": "true" }, brandMark(34)), h("div", { class: "app-brand-name" }, "Pramaan", h("small", {}, "Prior case retrieval"))),
    h("div", { class: "role-pill" }, icon(role === "admin" ? "settings" : role === "analyst" ? "chart" : "search", { size: 15 }), h("span", {}, `${ROLE_LABEL[role]} workspace`)),
    nav, h("div", { class: "sidebar-foot" }, collapse));

  const crumbs = h("div", { class: "crumbs", "aria-label": "Breadcrumb" });
  const modeChip = h("span", { class: `mode-chip ${session.mode === "real" ? "real" : "toy"}`, "data-tip": session.mode === "real" ? (session.show_text ? "Real index. Case titles and 200-character snippets are shown (SHOW_TEXT=1)." : "Real index. Case text and titles are hidden; results show ids, courts, years and scores.") : "Toy data: a 20-case fictional corpus. Not real results." },
    h("span", { class: "dot", style: { "--dc": session.mode === "real" ? "var(--ok)" : "var(--warn)" } }), h("span", { class: "mode-text" }, session.mode === "real" ? `Real data · text ${session.show_text ? "shown" : "hidden"}` : "Toy data"));
  stopWatching();
  const bell = h("button", { class: "btn ghost sm icon bell", type: "button", title: "Notifications", "aria-label": "Notifications", "aria-haspopup": "dialog", onClick: () => openNotifications(bell) }, icon("alert", { size: 17 }), h("i", { class: "bell-dot", hidden: true }));
  const seen = { n: 0 };
  notificationEvents.addEventListener("change", () => { const n = getNotifications().length; bell.querySelector(".bell-dot").hidden = n === seen.n; });
  const themeBtn = button("", { variant: "ghost", size: "sm", icon: effectiveTheme() === "dark" ? "sun" : "moon", title: "Toggle light and dark theme", onClick: () => { toggleTheme(); clear(themeBtn).append(icon(effectiveTheme() === "dark" ? "sun" : "moon")); } });
  const cmd = h("button", { class: "btn secondary sm cmd-btn", type: "button", onClick: openPalette, "aria-label": "Open command palette" }, h("span", { class: "row", style: { gap: "8px" } }, icon("search", { size: 15 }), h("span", { class: "cmd-label" }, "Jump to…")), h("kbd", {}, `${MOD} K`));
  const avatar = h("button", { class: "btn ghost sm", type: "button", "aria-haspopup": "menu", "aria-expanded": "false", title: "Account menu", onClick: () => toggleMenu() }, h("span", { class: "avatar" }, me.username.slice(0, 2)), h("span", { class: "who cmd-label" }, me.username), h("span", { class: "badge role cmd-label" }, ROLE_LABEL[role]));
  const top = h("header", { class: "topbar" }, button("", { variant: "ghost", size: "sm", icon: "menu", title: "Open navigation", onClick: () => app.setAttribute("data-nav-open", "true"), }), crumbs, h("span", { class: "spacer" }), cmd, modeChip, bell, themeBtn, avatar);
  top.firstChild.classList.add("menu-btn");
  watchStatus(modeChip, { mode: session.mode, show_text: session.show_text, onBack: () => document.dispatchEvent(new CustomEvent("app:reconnected")) });
  const page = h("main", { class: "page", id: "page", tabindex: "-1" });
  teardownAssistant();
  app.append(h("a", { class: "skip-link", href: "#page", onClick: (e) => { e.preventDefault(); page.focus(); } }, "Skip to content"), sidebar, h("div", { class: "sidebar-scrim", onClick: closeNav }), h("div", { class: "main" }, top, page), assistantFab());
  root.append(app);

  let menu = null;
  function toggleMenu(force) {
    if (menu) { menu.remove(); menu = null; avatar.setAttribute("aria-expanded", "false"); if (force !== true) return; }
    if (force === false) return;
    menu = h("div", { class: "menu", role: "menu" }, h("div", { class: "menu-head" }, h("span", { class: "avatar big" }, me.username.slice(0, 2)), h("div", { class: "stack", style: { gap: "2px" } }, h("b", {}, me.username), h("span", { class: "badge role" }, ROLE_LABEL[role])), session.auth_required ? null : h("span", { class: "xs muted" }, "sign-in is off")),
      item("settings", "Settings", () => navigate("/settings")), item("keyboard", "Keyboard shortcuts", openShortcuts), item("flask", "Style guide", () => navigate("/styleguide")), h("div", { class: "menu-sep" }),
      session.auth_required ? item("logout", "Sign out", onSignOut) : h("div", { class: "menu-label" }, "Sign-in is switched off (AUTH_REQUIRED=0)."));
    top.append(menu);
    avatar.setAttribute("aria-expanded", "true");
    menu.querySelector("button")?.focus();
    const away = (e) => { if (menu && !menu.contains(e.target) && !avatar.contains(e.target)) { menu.remove(); menu = null; avatar.setAttribute("aria-expanded", "false"); document.removeEventListener("mousedown", away); } };
    document.addEventListener("mousedown", away);
    menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { toggleMenu(); avatar.focus(); } });
    function item(ic, label, fn) { return h("button", { class: "menu-item", type: "button", role: "menuitem", onClick: () => { toggleMenu(); fn(); } }, icon(ic, { size: 16 }), label); }
  }

  return {
    page,
    setActive(path) {
      let cur = null;
      nav.querySelectorAll(".nav-link").forEach((a) => { if (a.getAttribute("data-path") === path) { a.setAttribute("aria-current", "page"); cur = a; } else a.removeAttribute("aria-current"); });
      requestAnimationFrame(() => {                                                   // the indicator glides (transform only) to the active item
        if (!cur || !cur.offsetHeight) { navInd.style.opacity = "0"; return; }
        navInd.style.opacity = "1"; navInd.style.height = `${cur.offsetHeight}px`; navInd.style.transform = `translateY(${cur.offsetTop}px)`;
      });
    },
    setCrumb(route, extra) {
      append(clear(crumbs), [h("span", {}, ROLE_LABEL[role]), route.group ? [icon("chevR", { size: 14 }), h("span", {}, route.group)] : null, icon("chevR", { size: 14 }), h("b", {}, route.title), extra ? [icon("chevR", { size: 14 }), h("b", { class: "mono" }, extra)] : null]);
      document.title = `${route.title}${extra ? " · " + extra : ""} · Pramaan`;
    },
  };
}

// ------------------------------------------------------------------ notification history
function openNotifications(anchor) {
  const list = getNotifications();
  const m = modal({ title: "Notifications", className: "notes-modal", body: h("div", { class: "stack" }, list.length ? list.map((n) => h("div", { class: `note ${n.kind}` }, h("span", { class: "dot", style: { "--dc": n.kind === "err" ? "var(--err)" : n.kind === "ok" ? "var(--ok)" : "var(--muted)" } }), h("span", { class: "grow small" }, n.msg), h("span", { class: "xs muted num" }, new Date(n.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }))))
    : h("p", { class: "small muted" }, "Nothing yet. Messages such as \"Search saved\" and errors are kept here for this visit.")) });
  anchor.querySelector(".bell-dot").hidden = true;
}

// ------------------------------------------------------------------ command palette
let qMeta = null;
async function devQueries() {
  if (qMeta) return qMeta;
  try { const r = await get("/api/query_meta"); qMeta = Object.entries(r.items).map(([id, m]) => ({ id, ...m })); } catch (_) { qMeta = []; }
  return qMeta;
}
/** Fuzzy match: query letters in order; bonus for word starts and runs. Returns {score, hits} or null. */
export function fuzzy(q, text) {
  q = q.toLowerCase().replace(/\s+/g, ""); const t = text.toLowerCase();
  if (!q) return { score: 0, hits: [] };
  let ti = 0, score = 0, run = 0; const hits = [];
  for (const ch of q) {
    const i = t.indexOf(ch, ti);
    if (i < 0) return null;
    run = i === ti && hits.length ? run + 1 : 0;
    score += 1 + run * 2 + (i === 0 || /[\s\-_/(]/.test(t[i - 1]) ? 3 : 0) - Math.min(i - ti, 6) * 0.15;
    hits.push(i); ti = i + 1;
  }
  return { score: score - t.length * 0.01, hits };
}
const markHits = (text, hits) => { if (!hits?.length) return text; const set = new Set(hits); return [...text].map((c, i) => (set.has(i) ? h("mark", {}, c) : c)); };
const RECENT = "irl.palette.recent.v1";
const readRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT) || "[]"); } catch (_) { return []; } };
const pushRecent = (it) => { try { const r = [{ label: it.label, key: it.key }, ...readRecent().filter((x) => x.key !== it.key)].slice(0, 6); localStorage.setItem(RECENT, JSON.stringify(r)); } catch (_) { /* ignore */ } };

export async function openPalette() {
  const role = session.me.role;
  const input = h("input", { class: "input", placeholder: "Jump to a page, run a dev query by id, ask the assistant, change theme…", "aria-label": "Command", role: "combobox", "aria-expanded": "true", "aria-controls": "pal-list", autocomplete: "off", spellcheck: "false" });
  const list = h("div", { class: "palette-list", id: "pal-list", role: "listbox" });
  const m = modal({ title: "Command palette", className: "palette", hideHead: true, body: h("div", {}, input, list) });
  const pages = ROUTES.filter((r) => !r.bare && r.roles.includes(role));
  const actions = [
    ...(pages.some((r) => r.path === "/search") ? [{ label: "Run a random dev query", group: "Actions", ic: "shuffle", key: "act:random", run: async () => { const qm = await devQueries(); if (qm.length) navigate("/search", { q: qm[Math.floor(Math.random() * qm.length)].id, run: 1 }); } }] : []),
    { label: "Ask the AI assistant", group: "Actions", ic: "spark", key: "act:assistant", run: openPanel, keys: "Alt A" },
    { label: "Toggle light / dark theme", group: "Actions", ic: "moon", key: "act:theme", run: toggleTheme },
    { label: "Toggle comfortable / compact density", group: "Actions", ic: "layers", key: "act:density", run: () => setSetting("density", getSettings().density === "compact" ? "comfortable" : "compact") },
    { label: "Toggle reduce motion", group: "Actions", ic: "gauge", key: "act:motion", run: () => setSetting("reduceMotion", !getSettings().reduceMotion) },
    { label: "Show keyboard shortcuts", group: "Actions", ic: "keyboard", key: "act:keys", run: openShortcuts, keys: "?" },
    ...(session.auth_required ? [{ label: "Sign out", group: "Actions", ic: "logout", key: "act:signout", run: () => document.dispatchEvent(new CustomEvent("app:signout")) }] : []),
  ];
  let queries = [];                                                     // filled in a moment; the palette is usable at once
  const pageItems = pages.map((r) => ({ label: `Go to ${r.title}`, sub: r.blurb, group: "Pages", ic: r.icon, keys: r.keys, key: `page:${r.path}`, run: () => navigate(r.path) }));
  const queryItem = (x) => ({ label: `Run dev query ${x.id}`, sub: `${x.court || "?"} · ${x.year || "?"}`, group: "Dev queries", ic: "play", key: `q:${x.id}`, run: () => navigate("/search", { q: x.id, run: 1 }) });
  let items = [], sel = 0;
  const build = (q) => {
    const raw = q.trim();
    if (!raw) {
      const byKey = new Map([...pageItems, ...actions].map((x) => [x.key, x]));
      const recent = readRecent().map((r) => byKey.get(r.key) || (r.key.startsWith("q:") && pages.some((p) => p.path === "/search") ? queryItem({ id: r.key.slice(2) }) : null)).filter(Boolean).map((x) => ({ ...x, group: "Recent" }));
      return [...recent, ...pageItems, ...actions];
    }
    const scored = [...pageItems, ...actions].map((x) => {
      const off = x.label.startsWith("Go to ") ? 6 : 0, a = fuzzy(raw, x.label.slice(off));
      if (a) return { x, score: a.score + 2, hits: a.hits.map((i) => i + off) };
      const b = fuzzy(raw, `${x.label} ${x.sub || ""}`);
      return b ? { x, score: b.score, hits: b.hits.filter((i) => i < x.label.length) } : null;
    }).filter(Boolean).sort((a, b) => b.score - a.score);
    const out = scored.map(({ x, hits }) => ({ ...x, hits }));
    if (pages.some((r) => r.path === "/search")) {
      const qq = raw.replace(/^q\s*/i, "").toLowerCase();
      queries.map((x) => ({ x, m: fuzzy(qq, x.id) })).filter((y) => y.m && y.m.hits.length).sort((a, b) => b.m.score - a.m.score).slice(0, 6).forEach(({ x }) => out.push(queryItem(x)));
    }
    return out;
  };
  const paint = () => {
    clear(list);
    if (!items.length) list.append(h("div", { class: "combo-empty" }, "Nothing matches. Try a page name, part of a word, or a dev query id."));
    let last = null;
    items.forEach((it, i) => {
      if (it.group !== last) { list.append(h("div", { class: "palette-group" }, it.group)); last = it.group; }
      list.append(h("div", { class: "palette-item", role: "option", id: `pal-${i}`, "aria-selected": String(i === sel), onMousemove: () => { if (sel === i) return; sel = i; list.querySelectorAll(".palette-item").forEach((n, j) => n.setAttribute("aria-selected", String(j === i))); input.setAttribute("aria-activedescendant", `pal-${i}`); }, onClick: () => run(i) },
        icon(it.ic, { size: 16 }), h("span", {}, markHits(it.label, it.hits)), it.sub && h("span", { class: "muted xs pal-sub" }, it.sub), it.keys && h("span", { class: "kbd-hint" }, ...it.keys.split(" ").map((k) => h("kbd", {}, k)))));
    });
    input.setAttribute("aria-activedescendant", items.length ? `pal-${sel}` : "");
  };
  const run = (i) => { const it = items[i]; if (!it) return; pushRecent(it); m.close(); it.run(); };
  input.addEventListener("input", () => { items = build(input.value); sel = 0; paint(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % Math.max(items.length, 1); paint(); document.getElementById(`pal-${sel}`)?.scrollIntoView({ block: "nearest" }); }
    else if (e.key === "Enter") { e.preventDefault(); run(sel); }
  });
  items = build(""); paint(); input.focus();
  devQueries().then((q) => { queries = q; if (m.el.isConnected) { items = build(input.value); sel = 0; paint(); } });
}

export function openShortcuts() {
  const rows = [[`${MOD} K`, "Command palette"], ["?", "This sheet"], ["/", "Focus the dev-query picker"], ["G then S", "Go to Search"], ["G then C", "Go to Compare"], ["G then Q", "Go to Query Lab"], ["G then V", "Go to Saved"], ["G then H", "Go to History"], ["G then E", "Go to Evaluation (analyst, admin)"],
    ["G then W", "Go to How it works"], ["G then A", "Go to the AI assistant page"], ["Alt A", "Open or close the AI assistant panel"], ["Esc", "Stop speaking; close a dialog, drawer or the assistant"], ["← →", "Move inside a segmented control"], ["↑ ↓ Enter", "Move and choose in lists and the palette"]];
  modal({ title: "Keyboard shortcuts", body: h("div", { class: "stack" }, rows.map(([k, d]) => h("div", { class: "row" }, h("span", { class: "grow" }, d), h("span", { class: "row", style: { gap: "4px" } }, k.split(" ").map((x) => (x === "then" ? h("span", { class: "muted xs" }, "then") : h("kbd", {}, x))))))) });
}

export function installShortcuts() {
  let g = 0;
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if (session.me) openPalette(); return; }
    if (e.altKey && !e.ctrlKey && !e.metaKey && (e.code === "KeyA" || e.key.toLowerCase() === "a") && session.me) { e.preventDefault(); if (document.querySelector(".as-host")) closePanel(); else openPanel(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || !session.me) return;
    if (e.key === "?") { e.preventDefault(); openShortcuts(); return; }
    if (e.key === "/") { const t = document.querySelector("[data-focus-search] input, [data-focus-search]"); if (t) { e.preventDefault(); t.focus(); } return; }
    if (g && Date.now() - g < 1200) {
      const r = ROUTES.find((x) => x.keys === `g ${e.key.toLowerCase()}` && x.roles.includes(session.me.role));
      g = 0;
      if (r) { e.preventDefault(); navigate(r.path); }
      return;
    }
    if (e.key.toLowerCase() === "g") g = Date.now();
  });
}
