// Tiny state: settings persisted in localStorage (every access guarded), session info held in memory.
const KEY = "irl.settings.v1";
const defaults = { theme: "system", density: "comfortable", sidebar: "expanded", reduceMotionNote: false, reduceMotion: false, speakReplies: "follow" };
let settings = { ...defaults };
try { settings = { ...defaults, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch (_) { /* storage blocked */ }

export const session = { me: null, auth_required: true, mode: "unknown", show_text: false };
export const getSettings = () => ({ ...settings });
export function setSetting(k, v) {
  settings[k] = v;
  try { localStorage.setItem(KEY, JSON.stringify(settings)); } catch (_) { /* ignore */ }
  applySettings();
}
export function applySettings() {
  const root = document.documentElement;
  if (settings.theme === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", settings.theme);
  root.setAttribute("data-density", settings.density);
  if (settings.reduceMotion === true) root.setAttribute("data-motion", "reduce"); else root.removeAttribute("data-motion");
}
export function effectiveTheme() { return document.documentElement.getAttribute("data-theme") || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
export function toggleTheme() { setSetting("theme", effectiveTheme() === "dark" ? "light" : "dark"); }
export function setRole(role) { if (role) document.documentElement.setAttribute("data-role", role); else document.documentElement.removeAttribute("data-role"); }

/** URL state: #/path?a=1&b=2 */
export function parseHash(hash = location.hash) {
  let s = hash.replace(/^#/, "");
  if (s && !s.startsWith("/")) s = "/" + s;
  const [path, q = ""] = s.split("?");
  const params = Object.fromEntries(new URLSearchParams(q));
  return { path: path || "/", params };
}
export function buildHash(path, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null && v !== false)).toString();
  return `#${path}${q ? "?" + q : ""}`;
}
export const navigate = (path, params, { replace = false } = {}) => {
  const h = buildHash(path, params);
  if (replace) { history.replaceState(null, "", h); window.dispatchEvent(new HashChangeEvent("hashchange")); } else location.hash = h;
};
/** Update the URL without re-rendering the page (search state lives here so a result view is shareable). */
export const setUrlState = (path, params) => history.replaceState(null, "", buildHash(path, params));
