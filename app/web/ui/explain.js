// "Explain" chip for dashboard cards: opens the AI assistant with the card's name (and a number when given). The assistant sees ids and numbers only.
import { h } from "/ui/dom.js";
import { icon } from "/ui/icons.js";
import { explainMetric } from "/ui/assistant/panel.js";

export function explainChip(name, value) {
  return h("button", { class: "chip-btn spark explain-chip", type: "button", title: `Ask the AI assistant to explain: ${name}`, "aria-label": `Explain: ${name}`, onClick: () => explainMetric({ name, value }) }, icon("spark", { size: 14 }), "Explain");
}
