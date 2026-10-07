// Routes, navigation by role, hash routing with role gating. One table drives sidebar, palette and breadcrumbs.
import { parseHash } from "/ui/store.js";

const ALL = ["researcher", "analyst", "admin"], AN = ["analyst", "admin"], AD = ["admin"];
export const ROUTES = [
  { path: "/", title: "Pramaan", icon: "scale", roles: ALL, group: null, public: true, bare: true, landing: true, load: () => import("/ui/pages/landing.js") },
  { path: "/search", title: "Search", icon: "search", roles: ALL, group: "Research", load: () => import("/ui/pages/search.js"), keys: "g s", blurb: "Find precedents for a dev query" },
  { path: "/compare", title: "Compare rankers", icon: "compare", roles: ALL, group: "Research", load: () => import("/ui/pages/compare.js"), keys: "g c", blurb: "tf-idf, BM25 and ours side by side" },
  { path: "/querylab", title: "Query Lab", icon: "code", roles: ALL, group: "Research", load: () => import("/ui/pages/querylab.js"), keys: "g q", blurb: "Boolean, phrase and proximity queries" },
  { path: "/saved", title: "Saved", icon: "bookmark", roles: ALL, group: "Library", load: () => import("/ui/pages/library.js"), keys: "g v" },
  { path: "/history", title: "History", icon: "clock", roles: ALL, group: "Library", load: () => import("/ui/pages/library.js"), keys: "g h" },
  { path: "/evaluation", title: "Evaluation", icon: "chart", roles: AN, group: "Analytics", load: () => import("/ui/pages/evaluation.js"), keys: "g e", blurb: "Metrics, ablations, leakage audit" },
  { path: "/efficiency", title: "Efficiency and crawl", icon: "gauge", roles: AN, group: "Analytics", load: () => import("/ui/pages/efficiency.js"), keys: "g f" },
  { path: "/index", title: "Index Inspector", icon: "database", roles: AD, group: "Administration", load: () => import("/ui/pages/admin.js"), keys: "g i" },
  { path: "/status", title: "System status", icon: "server", roles: AD, group: "Administration", load: () => import("/ui/pages/admin.js") },
  { path: "/users", title: "Users", icon: "users", roles: AD, group: "Administration", load: () => import("/ui/pages/admin.js") },
  { path: "/assistant", title: "AI assistant", icon: "spark", roles: ALL, group: "Learn", load: () => import("/ui/pages/assistant.js"), keys: "g a", blurb: "Ask about results, metrics and the system (Sarvam)" },
  { path: "/how", title: "How it works", icon: "layers", roles: ALL, group: "Learn", load: () => import("/ui/pages/how.js"), keys: "g w" },
  { path: "/about", title: "About and data", icon: "info", roles: ALL, group: "Learn", load: () => import("/ui/pages/about.js") },
  { path: "/settings", title: "Settings", icon: "settings", roles: ALL, group: null, load: () => import("/ui/pages/settings.js") },
  { path: "/styleguide", title: "Style guide", icon: "flask", roles: ALL, group: null, public: true, load: () => import("/ui/pages/styleguide.js") },
  { path: "/signin", title: "Sign in", icon: "lock", roles: ALL, group: null, public: true, bare: true, load: () => import("/ui/pages/signin.js") },
];
export const LANDING = { researcher: "/search", analyst: "/evaluation", admin: "/status" };
export const ROLE_LABEL = { researcher: "Researcher", analyst: "Analyst", admin: "Admin" };
export const routeFor = (path) => ROUTES.find((r) => r.path === path);
export const navFor = (role) => {
  const groups = [];
  for (const r of ROUTES.filter((x) => x.group && x.roles.includes(role))) {
    let g = groups.find((x) => x.title === r.group);
    if (!g) groups.push((g = { title: r.group, items: [] }));
    g.items.push(r);
  }
  return groups;
};
export function resolve(hash = location.hash) {
  const { path, params } = parseHash(hash);
  return { route: routeFor(path), path, params };
}
