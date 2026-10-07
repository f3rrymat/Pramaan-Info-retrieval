// Assistant state kept in the browser only: the conversation lives in sessionStorage (this tab, this session),
// the one-time consent and nothing else in localStorage. Nothing here is ever stored on the server (task 5, D42).
import { get } from "/ui/api.js";

const CONV = "irl.assistant.conv.v1", LANG = "irl.assistant.lang.v1", CONSENT = "irl.assistant.consent.v1";
const read = (store, k, d) => { try { const v = window[store].getItem(k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } };
const write = (store, k, v) => { try { if (v == null) window[store].removeItem(k); else window[store].setItem(k, JSON.stringify(v)); } catch (_) { /* storage blocked: memory only */ } };

export const events = new EventTarget();
let memory = read("sessionStorage", CONV, []);
let statusP = null;

export function status(refresh = false) {
  if (!statusP || refresh) statusP = get("/api/assistant/status").catch((e) => { statusP = null; throw e; });
  return statusP;
}
export const messages = () => memory;
export function setMessages(list) { memory = list.slice(-40); write("sessionStorage", CONV, memory); events.dispatchEvent(new Event("change")); }
export function addMessage(m) { const msg = { id: `m${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, ts: Date.now(), ...m }; setMessages([...memory, msg]); return msg; }
export function updateMessage(id, patch) { setMessages(memory.map((m) => (m.id === id ? { ...m, ...patch } : m))); }
export function removeMessage(id) { setMessages(memory.filter((m) => m.id !== id)); }
export function clearConversation() { setMessages([]); }
/** History for the server: user and assistant turns only, no errors, no notes. */
export const historyForServer = () => memory.filter((m) => (m.role === "user" || m.role === "assistant") && !m.error && m.content).map((m) => ({ role: m.role, content: m.content }));

export const language = () => read("sessionStorage", LANG, "auto");
export function setLanguage(code) { write("sessionStorage", LANG, code); events.dispatchEvent(new Event("lang")); }
export const consented = () => read("localStorage", CONSENT, false) === true;
export function setConsent(v) { write("localStorage", CONSENT, v ? true : null); events.dispatchEvent(new Event("consent")); }
