// Admin pages: Index Inspector, System status, Users. Aggregates and file metadata only.
import { h, clear, fmt, debounce } from "/ui/dom.js";
import { alertBox, badge, button, emptyState, errorState, hbar, kpi, pageHead, skeletonCards, table } from "/ui/components.js";
import { get } from "/ui/api.js";

const mb = (b) => (b / 2 ** 20).toFixed(2);

export default async function admin(ctx) {
  const { path, container } = ctx;
  if (path === "/index") return (await import("/ui/pages/indexinspector.js")).default(ctx);
  if (path === "/users") return users(container);
  return status(container);
}

async function status(container) {
  container.append(pageHead("System status", "What this server is running and which saved results it can serve. File names and sizes only."));
  const body = h("div", { class: "stack" }, skeletonCards(2)); container.append(body);
  let s; try { s = await get("/api/system/status"); } catch (e) { return clear(body).append(errorState(e, () => location.reload())); }
  const flag = (ok, yes, no) => badge(ok ? yes : no, ok ? "ok" : "warn");
  clear(body).append(h("div", { class: "grid cols-4" }, kpi("Users", s.users, { decimals: 0 }), kpi("Saved items", s.saved_items, { decimals: 0 }), kpi("History items", s.history_items, { decimals: 0 }), kpi("Uptime (s)", s.uptime_seconds, { decimals: 0 })),
    h("section", { class: "card stack" }, h("h3", {}, "Configuration"), table(["Setting", "State"], [["Data mode", flag(s.mode === "real", "real index", "toy corpus")], ["Case text and titles", flag(!s.show_text, "hidden (default)", "shown (SHOW_TEXT=1)")], ["Sign-in", flag(s.auth_required, "required", "off (AUTH_REQUIRED=0)")], ["Index files present", flag(s.index_present, `yes, ${s.index_files} files`, "no")], ["Config A frozen", flag(s.config_a_frozen, "yes", "no")], ["Final test run", flag(s.final_test_run_done, "done once (results/final.lock)", "not run")], ["Python", s.python]])),
    h("section", { class: "card stack" }, h("h3", {}, "Saved results"), s.result_files.length ? table(["File", "Size (KB)", "Modified"], s.result_files.map((f) => [f.name, (f.bytes / 1024).toFixed(1), new Date(f.modified * 1000).toLocaleString()]), { numeric: [1] }) : emptyState("No results saved", "Run the evaluation scripts listed in docs/STATUS.md.", { icon: "server" })));
}

async function users(container) {
  container.append(pageHead("Users", "Demo accounts for the three roles. Passwords are hashed with scrypt and never shown."));
  const body = h("div", { class: "stack" }, skeletonCards(1)); container.append(body);
  try { const r = await get("/api/system/users"); clear(body).append(h("section", { class: "card stack" }, table(["Username", "Role", "Created", "Last sign-in"], r.users.map((u) => [u.username, badge(u.role, u.role === "admin" ? "warn" : u.role === "analyst" ? "brand" : "ok"), new Date(u.created_at * 1000).toLocaleString(), u.last_login ? new Date(u.last_login * 1000).toLocaleString() : "never"])),
    alertBox("This sign-in separates what each role sees in the app. It does not control access to the dataset, which is gated and research-use only.", "", "lock"))); } catch (e) { clear(body).append(errorState(e)); }
}
