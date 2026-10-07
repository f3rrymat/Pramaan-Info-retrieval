// #/assistant: the same assistant component as the side panel, as a full page.
import { h } from "/ui/dom.js";
import { createAssistant } from "/ui/assistant/panel.js";

export default async function assistantPage({ container }) {
  const comp = createAssistant({ mode: "page" });
  container.append(h("div", { class: "as-page-wrap" }, comp.el));
  comp.focus();
  return () => comp.destroy();
}
