# UI audit (Phase G baseline, written before any Phase G change)

Method: read every file under `app/web/`, the router modules under `app/routers/`, and looked at the existing screenshots in `docs/figures/ui_all/`. Scores are my own judgment, not a measurement.

## Pages and components
Pages (`app/web/ui/pages/`): signin, search, compare, querylab, library (saved, history), evaluation, efficiency, admin (index inspector, status, users), assistant, how, about, settings, styleguide. Shell: sidebar (role-specific), top bar (crumbs, palette, mode chip, theme, account menu), command palette, shortcut sheet, toasts, case drawer, assistant dock. Helpers: `components.js`, `charts.js`, `motion.js`, `pipeline.js`, `icons.js`.

## Endpoint to UI table
| Endpoint | UI element that uses it |
|---|---|
| GET /api/health | none (unused by the UI) |
| GET /api/auth/me | boot (`main.js`), role navigation, quick-login flag |
| POST /api/auth/signin, /quick, /signout | sign-in form, role cards, account menu |
| GET /api/public/headline | sign-in hero numbers |
| GET /api/public/pipeline | How it works page |
| GET /api/public/about | About page |
| GET /api/queries, /api/query_meta | Search picker, palette, Compare, Query Lab |
| POST /api/search | Search, Compare |
| POST /api/overlay | Search "Evaluation overlay" |
| GET /api/case_detail/{id} | case drawer |
| GET /api/case/{id} | unused by the UI |
| POST /api/parse, /api/query/run, GET /api/suggest | Query Lab; Index Inspector term suggest |
| GET /api/saved, POST, DELETE; /api/history | Saved, History, Search recent chips |
| GET /api/eval/summary, ablation, leakage, efficiency, zone_matrix | Evaluation, Efficiency |
| GET /api/results/{name} | Efficiency (crawl_sim), Evaluation (w_variant, decompose_dev) |
| GET /api/index/stats, /api/inspect/index | Index Inspector |
| GET /api/system/status, /users | System status, Users |
| GET /api/assistant/status, POST chat, stt, tts | assistant panel and page |

## Ten biggest weaknesses
1. No public landing page: an anonymous visitor lands on a sign-in form with no explanation of the product.
2. The brand is a text glyph ("§") in a square, also used as the favicon; there is no real mark.
3. One typeface for everything; page titles and numbers have no display voice, so hierarchy is flat.
4. Flat page background and one card style: little depth, no clear elevation levels.
5. Search is a side column of small controls; the query picker is not the hero of the page and has no grouped suggestions.
6. The ranker control has three options with no hint of how good each is; "Ours + temporal filter" is hidden in a separate switch and Boolean search lives on another page.
7. Dashboards (Evaluation, Efficiency, Index Inspector, How it works) are mostly static tables and charts: no linked highlighting, no steppers, no explorer.
8. Navigation has no glide indicator, no in-flight progress bar and only a fade-out route transition.
9. The status chip shows the data mode only; it never polls and there is no offline state or retry with backoff.
10. No data provenance on screen (when the numbers were produced) and some empty and error states are text only.

## Rubric (1 to 5) and before-scores
| Criterion | Before | What a 4 means |
|---|---|---|
| Hierarchy | 3 | one clear focal point per screen, three type levels used consistently |
| Consistency | 4 | same component and colour means the same thing everywhere |
| Density | 3 | information fits without scrolling for the main task; no empty bands |
| Motion purpose | 3 | each animation shows cause, order or change; nothing decorative |
| Empty and error states | 3 | designed, actionable, with a drawing or clear next step |
| Dark-mode polish | 4 | same hierarchy and contrast as light, no washed-out surfaces |
| Backend sync | 4 | every control wired to a real endpoint; labels match the data |

After-scores are recorded in the section "Self-critique" at the end of this file (written in the final checks).

## Self-critique (after the Phase G pass; stopped early, so this is partial)
Scored from the new screenshots in docs/figures/ui/ against the rubric above. The full re-score with the complete gate matrix was not run.
| Criterion | Before | After | Note |
|---|---|---|---|
| Hierarchy | 3 | 4 | display face, one focal bar on Search, hero on the overview |
| Consistency | 4 | 4 | role accent, zone/score colours and tokens unchanged |
| Density | 3 | 4 | bento tiles on dashboards; Search filters moved under the hero |
| Motion purpose | 3 | 4 | story steppers, replay, FLIP; legacy width transitions replaced by transforms |
| Empty and error states | 3 | 4 | drawings and offline banner with retry |
| Dark-mode polish | 4 | 4 | checked on landing, search, evaluation |
| Backend sync | 4 | 4 | status polling, session dialog; one fix: search-bar text clipped in dark mode, found in screenshots and fixed |
