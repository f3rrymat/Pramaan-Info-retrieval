// Helpers that turn saved-run JSON (as served by the API) into the shapes the dashboards draw. No numbers are created here.
export const SYS_SHORT = (name) => name.replace(/^REFERENCE .*?: ?/, "ref: ").replace(/ \(k1=.*\)$/, "").replace(" (text + neighbour + authority)", "").replace(/ lnc\.ltc/, " (lnc.ltc)");

/** The cumulative ablation ladder from rows [{row, MAP, ...}]: steps 1, 3, 4, 5, 6, 7 (frozen Config A) and the temporal filter on top.
 *  Side branches (single-signal rows, the two worse step-7 configs) are excluded from the ladder and shown elsewhere. */
export function ladderOf(rows) {
  const label = (r) => (/^1 /.test(r) ? "tf-idf, first stage" : /^3 /.test(r) ? "+ statute channel" : /^4 /.test(r) ? "+ authority" : /^5 /.test(r) ? "+ neighbour vote" : /^6 /.test(r) ? "+ recency and court"
    : /temporal filter$/.test(r) ? "+ temporal filter" : "+ union first stage, frozen weights");
  const keep = rows.filter((x) => /^1 /.test(x.row) || /^[3-6] \+/.test(x.row) || /^7 \+ union first stage, frozen config A_best_cv( \+ temporal filter)?$/.test(x.row));
  return keep.map((x, i) => ({ ...x, label: label(x.row), delta: i ? x.MAP - keep[i - 1].MAP : null }));
}
/** One-sentence narration of ladder step i, generated from the numbers. */
export function narrate(steps, i) {
  const s = steps[i], f = (v) => v.toFixed(3);
  if (!i) return `Start: tf-idf alone reaches a MAP of ${f(s.MAP)} on the dev queries.`;
  const d = s.delta, big = Math.max(...steps.map((x) => Math.abs(x.delta ?? 0)));
  const verb = Math.abs(d) < 0.003 ? "changes it by" : d > 0 ? "adds" : "loses";
  return `${s.label[0] === "+" ? "Adding" : "Using"} ${s.label.replace(/^\+ /, "")} ${verb} ${Math.abs(d).toFixed(3)}, to a MAP of ${f(s.MAP)}${Math.abs(d) === big && big > 0.01 ? "; this is the largest step on the ladder" : Math.abs(d) < 0.003 ? "; that is within noise of the previous step" : ""}.`;
}
