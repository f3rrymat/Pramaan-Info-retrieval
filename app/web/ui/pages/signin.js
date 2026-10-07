// Split-layout sign-in. Left: product statement and headline numbers read from saved runs. Right: validated form.
import { h, clear, fmt } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { alertBox, button, countUp, field } from "/ui/components.js";
import { post, get } from "/ui/api.js";
import { toggleTheme, effectiveTheme, session, navigate } from "/ui/store.js";
import { brandMark } from "/ui/brand.js";

export default async function signin({ container, params, onSignedIn }) {
  const stats = h("div", { class: "hero-stats", "aria-live": "polite" }, [0, 1, 2].map(() => h("div", { class: "hero-stat" }, h("div", { class: "skel", style: { height: "40px" } }))));
  const hero = h("section", { class: "signin-hero", "aria-label": "About this system" },
    h("div", { class: "row" }, h("a", { class: "row", href: "#/", style: { gap: "var(--s-2)", textDecoration: "none", color: "var(--text)" }, "aria-label": "Pramaan overview" }, brandMark(32), h("b", { class: "display", style: { fontSize: "1.2rem" } }, "Pramaan")), h("span", { class: "spacer" }), h("a", { class: "btn ghost sm", href: "#/" }, icon("chevL", { size: 14 }), "Overview")),
    h("div", { class: "stack", style: { gap: "var(--s-4)" } },
      h("h1", {}, "Earlier judgments a case should cite, with the reasons shown."),
      h("p", { class: "lede" }, "Given the facts and issues of an undecided Indian case, the system ranks earlier judgments and explains each result: which similar cases cite it, how authoritative it is, and which score components carried it."),
      stats,
      h("p", { class: "xs muted" }, "Numbers are read from saved evaluation runs on this machine. The test split was run once.")),
    h("p", { class: "xs muted" }, "Research prototype. Built on the IL-PCSR corpus (research use only)."));

  get("/api/public/headline").then((r) => {
    clear(stats);
    if (!r.available) { stats.append(h("div", { class: "hero-stat" }, h("div", { class: "small muted" }, "No saved evaluation run on this machine yet."))); return; }
    const pick = (k) => r.rows.find((x) => x.key === k);
    const split = r.test_run_once ? "test" : "dev", tiles = [["tf-idf baseline", pick("tfidf"), split], ["Config A", pick("config_a"), split], ["Config A + temporal filter", pick("config_a_tf"), split]];
    tiles.forEach(([label, row, split]) => {
      const m = row && (row[split] || row.dev), used = row && row[split] ? split : "dev";
      const v = h("div", { class: "kpi" }, h("div", { class: "l" }, label), h("div", { class: "v" }, "–"), h("div", { class: "xs muted" }, `MAP on ${used} (${used === "test" ? r.test_queries : r.dev_queries} queries)`));
      stats.append(h("div", { class: "hero-stat" }, v));
      if (m) countUp(v.querySelector(".v"), m.MAP, { decimals: 3 });
    });
  }).catch(() => { clear(stats).append(h("div", { class: "hero-stat small muted" }, "Headline numbers are unavailable.")); });

  const user = h("input", { class: "input", name: "username", autocomplete: "username", autocapitalize: "none", spellcheck: "false", required: true });
  const pw = h("input", { class: "input", name: "password", type: "password", autocomplete: "current-password", required: true });
  const eye = button("", { variant: "ghost", size: "sm", icon: "eye", title: "Show or hide the password", onClick: () => { const show = pw.type === "password"; pw.type = show ? "text" : "password"; clear(eye).append(icon(show ? "eyeOff" : "eye")); eye.setAttribute("aria-pressed", String(show)); } });
  const errBox = h("div", { "aria-live": "assertive" });
  const uErr = h("div", {}), pErr = h("div", {});
  const submit = button("Sign in", { variant: "", size: "lg", type: "submit" });
  let timer;
  const setFieldErr = (box, input, msg) => { clear(box); input.setAttribute("aria-invalid", String(!!msg)); if (msg) box.append(h("div", { class: "field-error", role: "alert" }, icon("alert", { size: 14 }), msg)); };
  const form = h("form", { class: "stack", novalidate: true, onSubmit: async (e) => {
    e.preventDefault(); clear(errBox);
    setFieldErr(uErr, user, user.value.trim() ? "" : "Enter your username."); setFieldErr(pErr, pw, pw.value ? "" : "Enter your password.");
    if (!user.value.trim() || !pw.value) return (user.value.trim() ? pw : user).focus();
    submit.disabled = true; clear(submit).append(h("span", { class: "spin" }), "Signing in…");
    try { await post("/api/auth/signin", { username: user.value, password: pw.value }); pw.value = ""; await onSignedIn(); }
    catch (err) {
      submit.disabled = false; clear(submit).append("Sign in");
      if (err.status === 429) { let left = err.body.retry_after || 60; submit.disabled = true; const tick = () => { clear(errBox).append(alertBox(`Too many failed attempts. You can try again in ${left} s.`, "warn", "lock")); if (left-- <= 0) { clearInterval(timer); submit.disabled = false; clear(errBox); } }; tick(); timer = setInterval(tick, 1000); }
      else clear(errBox).append(alertBox(err.status === 401 ? "Invalid username or password." : err.message, "err", "alert"));
      pw.focus(); pw.select();
    }
  } },
    field("Username", user, { id: "su-user" }), uErr, field("Password", h("div", { class: "input-wrap" }, pw, eye), { id: "su-pw" }), pErr, errBox, submit);
  const wantRole = ["researcher", "analyst", "admin"].includes(params.role) ? params.role : null;
  if (wantRole) user.value = wantRole;
  const quick = session.quick_login;
  const ROLE_CARDS = [["researcher", "Researcher", "Search, compare rankers, run queries, save and review your history."], ["analyst", "Analyst", "Everything a researcher sees, plus the Evaluation, leakage and efficiency dashboards."], ["admin", "Admin", "Adds the Index Inspector, system status and the user list."]];
  const quickErr = h("div", { "aria-live": "assertive" });
  const quickBox = quick ? h("div", { class: "stack" },
    h("div", { class: "stack", style: { gap: "var(--s-3)" } }, ROLE_CARDS.map(([role, label, text]) => h("button", { type: "button", class: `role-card${role === wantRole ? " selected" : ""}`, "data-role": role, "aria-pressed": role === wantRole ? "true" : null, style: { "--rc": `var(--role-${role})` }, onClick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true; clear(quickErr);
      try { await post("/api/auth/quick", { role }); await onSignedIn({ land: "/search" }); } catch (err) { btn.disabled = false; clear(quickErr).append(alertBox(err.status === 404 ? "Quick sign-in is not available from this address." : err.message, "err", "alert")); } } },
      h("span", { class: "role-card-bar", "aria-hidden": "true" }), h("span", { class: "role-card-body" }, h("b", {}, label), h("span", { class: "small" }, text)), icon("chevR")))), quickErr,
    alertBox("Local demo quick sign-in is on: it signs in as a role without a password and works only from this machine. It is a convenience, not access control.", "warn", "alert")) : null;
  const expired = params.next ? alertBox("Sign in to open that page.", "", "info") : null;
  const formWrap = h("section", { class: "signin-form-wrap", "aria-label": "Sign in" }, h("div", { class: "signin-card" },
    h("div", { class: "row" }, h("h2", {}, "Sign in"), h("span", { class: "spacer" }), button("", { variant: "ghost", size: "sm", icon: effectiveTheme() === "dark" ? "sun" : "moon", title: "Toggle light and dark theme", onClick: toggleTheme })),
    expired, quickBox, quick ? h("div", { class: "row" }, h("button", { type: "button", class: "btn ghost sm", onClick: (e) => { form.hidden = !form.hidden; e.currentTarget.textContent = form.hidden ? "Use a password instead" : "Hide the password form"; if (!form.hidden) user.focus(); } }, "Use a password instead")) : null, form,
    alertBox("This is a local demo sign-in that separates what each role sees. It is not access control for the dataset: IL-PCSR is gated and research-use only, and its terms apply regardless.", "", "lock"),
    h("p", { class: "xs muted" }, "Demo accounts are created locally by the setup script. Passwords are never shown here.")));
  if (quick) form.hidden = true;
  clear(container).append(h("div", { class: "signin" }, hero, formWrap));
  document.title = "Sign in · Pramaan";
  if (quick && wantRole) container.querySelector(`.role-card[data-role="${wantRole}"]`)?.focus();
  else if (!quick) (wantRole ? pw : user).focus();
}
