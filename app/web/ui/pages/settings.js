// Settings: theme, density, sidebar, motion and the assistant. Stored in this browser only.
import { h } from "/ui/dom.js";
import { alertBox, button, field, pageHead, segmented, toast } from "/ui/components.js";
import { getSettings, setSetting, session } from "/ui/store.js";
import * as A from "/ui/assistant/state.js";

export default async function settings({ container }) {
  const s = getSettings(), os = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const motionNote = h("div", {});
  const paintMotion = () => { motionNote.replaceChildren(alertBox(os ? "Your system asks for reduced motion, so animations stay off whatever this switch says." : getSettings().reduceMotion ? "Motion is reduced: no gliding cards, chart draw-in, count-up numbers, physics or page transitions." : "Animations are on. They also switch off automatically when your system asks for reduced motion.", "", "info")); };
  const motion = h("label", { class: "switch" }, h("input", { type: "checkbox", checked: !!s.reduceMotion || os, disabled: os || null, "aria-describedby": "motion-note", onChange: (e) => { setSetting("reduceMotion", e.target.checked); paintMotion(); } }), "Reduce motion");
  motionNote.id = "motion-note"; paintMotion();
  const consent = h("span", { class: "small" });
  const paintConsent = () => { consent.textContent = A.consented() ? "You have accepted that your questions and recordings are sent to Sarvam AI (remembered in this browser)." : "Not accepted yet. The assistant asks the first time you use it."; };
  paintConsent();
  container.append(pageHead("Settings", "Stored in this browser only. Nothing is sent to the server."),
    h("section", { class: "card stack" }, h("h2", {}, "Appearance"),
      field("Theme", segmented([{ value: "system", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }], s.theme, (v) => setSetting("theme", v), { label: "Theme" }), { hint: "System follows your operating system." }),
      field("Density", segmented([{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }], s.density, (v) => setSetting("density", v), { label: "Density" }), { hint: "Compact tightens spacing for long result lists." }),
      field("Sidebar", segmented([{ value: "expanded", label: "Expanded" }, { value: "collapsed", label: "Collapsed" }], s.sidebar, (v) => setSetting("sidebar", v), { label: "Sidebar" }), { hint: "Takes effect on the next page load; the sidebar button changes it immediately." }),
      h("div", { class: "stack", style: { gap: "var(--s-2)" } }, h("div", { class: "label" }, "Motion"), motion, motionNote)),
    h("section", { class: "card stack" }, h("h2", {}, "AI assistant (Sarvam)"),
      field("Speak replies", segmented([{ value: "follow", label: "Follow input mode" }, { value: "always", label: "Always" }, { value: "never", label: "Never" }], s.speakReplies || "follow", (v) => setSetting("speakReplies", v), { label: "Speak replies" }),
        { hint: "Follow input mode: a spoken question gets a spoken reply as well as text; a typed question gets text only. The text of every reply is always shown." }),
      h("div", { class: "row" }, consent, A.consented() ? button("Withdraw", { variant: "secondary", size: "sm", onClick: (e) => { A.setConsent(false); paintConsent(); e.currentTarget.remove(); toast("Consent withdrawn. The assistant will ask again.", "ok"); } }) : null),
      h("p", { class: "xs muted" }, "The conversation is kept in this browser tab only and is never stored on the server. Case text and titles are never sent to Sarvam.")),
    h("section", { class: "card stack" }, h("h2", {}, "This session"), h("p", { class: "small" }, `Signed in as ${session.me.username} (${session.me.role}). Data mode: ${session.mode}. Case text is ${session.show_text ? "shown (SHOW_TEXT=1)" : "hidden"}; signing in never changes that.`)));
}
