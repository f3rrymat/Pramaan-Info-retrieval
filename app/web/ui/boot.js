/* Classic (non-module) script loaded in <head>: apply the saved theme, density and motion setting before first paint
   (no flash). A file rather than an inline script, so the Content-Security-Policy can forbid inline scripts. Storage may be blocked. */
try {
  var s = JSON.parse(localStorage.getItem("irl.settings.v1") || "{}"), r = document.documentElement;
  if (s.theme && s.theme !== "system") r.setAttribute("data-theme", s.theme);
  if (s.density) r.setAttribute("data-density", s.density);
  if (s.reduceMotion === true) r.setAttribute("data-motion", "reduce");
} catch (e) { /* ignore */ }
