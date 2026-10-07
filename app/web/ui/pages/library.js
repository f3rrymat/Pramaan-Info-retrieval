// Saved and History: ids, parameters and timestamps only (never case text).
import { h, clear } from "/ui/dom.js";
import { badge, button, chip, courtBadge, emptyState, errorState, pageHead, skeletonCards, toast, tabs } from "/ui/components.js";
import { get, del } from "/ui/api.js";
import { navigate } from "/ui/store.js";
import { stagger } from "/ui/motion.js";
import { openCaseDrawer } from "/ui/casedrawer.js";

const when = (t) => new Date(t * 1000).toLocaleString();
const paramChips = (p) => [p.ranker && `ranker ${p.ranker}`, p.pruning && p.pruning !== "none" && `pruning ${p.pruning}`, p.temporal_filter && "temporal filter", p.filters?.court?.length && `court ${p.filters.court.join("/")}`, p.filters?.year_from && `from ${p.filters.year_from}`, p.filters?.year_to && `to ${p.filters.year_to}`, p.weights && "custom weights", p.view === "compare" && "compare view"].filter(Boolean);
const searchLink = (ref, p) => (p.view === "compare" ? ["/compare", { q: ref, temporal: p.temporal_filter === false ? "0" : "" }] : ["/search", { q: ref, run: 1, ranker: p.ranker && p.ranker !== "ours" ? p.ranker : "", prune: p.pruning && p.pruning !== "none" ? p.pruning : "", temporal: p.temporal_filter === false ? "0" : "", court: (p.filters?.court || []).join(","), yf: p.filters?.year_from || "", yt: p.filters?.year_to || "",
  w: p.weights ? ["text", "neighbour", "authority"].map((k) => p.weights[k] ?? 0).join(",") : "" }]);

export default async function library({ container, path, params }) {
  const isSaved = path === "/saved";
  container.append(pageHead(isSaved ? "Saved" : "History", isSaved ? "Searches and cases you saved. Only ids and search settings are stored." : "Your recent searches on this server. Only ids, settings and times are stored; pasted text is never kept."));
  const body = h("div", { class: "stack" }, skeletonCards(2)); container.append(body);
  const load = async () => {
    try {
      const r = await get(isSaved ? "/api/saved" : "/api/history?limit=100");
      clear(body);
      if (!r.items.length) return body.append(h("div", { class: "card" }, emptyState(isSaved ? "Nothing saved yet" : "No searches yet", isSaved ? "Use the bookmark on a result, or Save search on the Search page." : "Run a search and it will be listed here.", { icon: isSaved ? "bookmark" : "clock", action: button("Go to Search", { onClick: () => navigate("/search") }) })));
      if (!isSaved) body.append(h("div", { class: "row" }, h("span", { class: "spacer" }), button("Clear history", { variant: "secondary", size: "sm", icon: "trash", onClick: () => {
        // deferred: the list hides at once; the server call happens only if Undo is not pressed within a few seconds
        const nodes = [...body.querySelectorAll("article")]; nodes.forEach((n) => { n.hidden = true; });
        toast("History cleared.", "ok", { action: { label: "Undo", run: () => { nodes.forEach((n) => { n.hidden = false; }); toast("History restored.", ""); } }, onTimeout: async () => { try { await del("/api/history"); } catch (e) { toast(e.message, "err"); } load(); } });
      } })));
      r.items.forEach((it) => {
        const isCase = it.kind === "case";
        body.append(h("article", { class: "card tight row", style: { flexWrap: "nowrap" }, "data-key": `${it.kind}:${it.id}` }, h("div", { class: "grow stack", style: { gap: "6px" } }, h("div", { class: "row", style: { gap: "8px" } }, badge(isCase ? "case" : it.params.view === "compare" ? "compare" : "search", isCase ? "info" : "brand"), h("span", { class: "mono", style: { fontWeight: 650 } }, it.ref), h("span", { class: "xs muted" }, when(it.created_at))), h("div", { class: "row", style: { gap: "6px" } }, paramChips(it.params).map((c) => chip(c)))),
          button(isCase ? "Open" : "Run again", { variant: "secondary", size: "sm", icon: isCase ? "eye" : "play", onClick: () => isCase ? openCaseDrawer({ docId: it.ref }) : navigate(...searchLink(it.ref, it.params)) }),
          isSaved ? button("", { variant: "ghost", size: "sm", icon: "trash", title: "Remove", onClick: (e) => {
            // deferred delete with Undo: the card hides now, the DELETE is sent when the toast expires
            const card = e.currentTarget.closest("article"); card.hidden = true;
            toast(`Removed ${it.ref}.`, "ok", { action: { label: "Undo", run: () => { card.hidden = false; } }, onTimeout: async () => { try { await del(`/api/saved/${it.id}`); } catch (err) { card.hidden = false; toast(err.message, "err"); } } });
          } }) : null));
      });
      stagger(body.querySelectorAll("article"));
    } catch (e) { clear(body).append(errorState(e, load)); }
  };
  load();
}
