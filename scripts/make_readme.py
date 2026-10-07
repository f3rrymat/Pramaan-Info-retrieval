"""Assemble README.md from docs/ws*.md, docs/research_notes.md and saved runs in results/ (DECISIONS D32, D44: no number is
typed by hand; research notes are data).

Usage: python scripts/make_readme.py [--out README.md]

If results/ is missing on this machine (it is never shipped), the sections that hold numbers (Headline results, Leakage
audit, Efficiency, Index, Negative and marginal results) are carried over unchanged from the existing README.md, which was
generated from results/ on a machine that had them, and the script says so. Everything else is regenerated.
Screenshots listed in docs/research_notes.md that are missing from docs/figures/ui/ are skipped with a warning.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(ROOT / "README.md"))
args = ap.parse_args()
WARN = []


def warn(msg):
    WARN.append(msg)
    print("WARNING:", msg)


def load(n):
    p = R / n
    return json.loads(p.read_text()) if p.exists() else None


dev, test = load("dev_eval.json"), load("test_eval.json")
abl, leak, eff, crawl, dec, wv, cfg = (load(n) for n in ("b2_ablation_dev.json", "leakage_audit.json", "efficiency.json", "crawl_sim.json",
                                                         "decompose_dev.json", "w_variant.json", "config_a_frozen.json"))
bmx, idx, andb, stat = load("bm25_tuning.json"), load("index_report.json"), load("and_benchmark.json"), load("statute_bridge.json")
f = lambda x: "n/a" if x is None else f"{x:.4f}"
ci = lambda d: f"{d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]"
A, AT, T = "Config A (text + neighbour + authority)", "Config A + temporal filter", "tf-idf lnc.ltc"

# ------------------------------------------------------------------ the previous README (for carry-over without results/)
OLD = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""


def old_sections(text):
    out, parts = {}, re.split(r"(?m)^(#{2,3} .+)$", text)
    for i in range(1, len(parts) - 1, 2):
        out.setdefault(parts[i].strip(), parts[i + 1].strip("\n"))
    return out


OS = old_sections(OLD)
SEG = []


def seg(name):
    """Mark where a README section starts in L; the sections are re-ordered at the end (see ORDER)."""
    SEG.append((name, len(L)))


def carried(*titles, level="## "):
    for t in titles:
        for k, v in OS.items():
            if k.startswith(level) and k[len(level):].startswith(t):
                return v.strip()
    return None


def carry(title, *aliases, body_filter=None):
    body = carried(title, *aliases)
    if body is None:
        warn(f"results/ missing and no '{title}' section in the old README: section left out")
        return []
    if body_filter:
        body = body_filter(body)
    warn(f"results/ missing: '{title}' carried over unchanged from the existing README.md (generated earlier from results/)")
    return [f"## {title}", "", body, ""]


def find(run, name):
    return next((m for n, m in run["macro"].items() if n == name or n.startswith(name)), None) if run else None


def headline():
    def table(run):
        rows = ["| system | P@5 | R@5 | P@10 | R@10 | P@20 | R@20 | MAP |", "|---|---|---|---|---|---|---|---|"]
        for label, key in (("random", "random"), ("popularity (train in-degree)", "popularity"), ("tf-idf lnc.ltc", T),
                           ("BM25 tuned", "BM25 tuned"), ("**Config A** (text + neighbour + authority)", A), ("**Config A + temporal filter (headline)**", AT)):
            m = find(run, key)
            rows.append(f"| {label} | " + " | ".join(f(m[k]) if m else "n/a" for k in ("P@5", "R@5", "P@10", "R@10", "P@20", "R@20", "MAP")) + " |")
        return "\n".join(rows)
    out = [f"**Dev, {dev['n_queries']} queries**", "", table(dev)]
    if test:
        out += ["", f"**Test, {test['n_queries']} queries (run once)**", "", table(test)]
    return "\n".join(out)


def sig(run, key, metric="MAP"):
    return ci(run["bootstrap_diff_[mean,lo95,hi95]"]["vs_tfidf"][key][metric]) if run else "n/a"


# ------------------------------------------------------------------ research notes (data)
NOTES = (ROOT / "docs" / "research_notes.md").read_text(encoding="utf-8")


def note_section(title):
    m = re.search(rf"(?ms)^## {re.escape(title)}\n(.*?)(?=^## |\Z)", NOTES)
    if not m:
        warn(f"docs/research_notes.md has no '## {title}' section")
        return ""
    return m.group(1).strip()


def papers():
    out = []
    for block in re.split(r"(?m)^### ", note_section("Papers"))[1:]:
        name, _, body = block.partition("\n")
        d = {"name": name.strip()}
        for line in body.splitlines():
            m = re.match(r"- (\w+): (.*)", line.strip())
            if m:
                d[m.group(1)] = m.group(2).strip()
        for k in ("status", "citation", "short", "did", "take", "differ"):
            if k not in d:
                warn(f"paper '{d['name']}' has no '{k}' line")
                d[k] = ""
        if not d["status"].startswith(("VERIFIED", "RE-CHECK")):
            warn(f"paper '{d['name']}' has an unknown status: {d['status'][:30]}")
        out.append(d)
    return out


def bullets(title):
    return [l for l in note_section(title).splitlines() if l.startswith("- ")]


cell = lambda s: s.replace("|", "\\|")

# ------------------------------------------------------------------ numbers for the contributions (results/ first, carried README second)
def leak_numbers():
    if leak:
        a = leak["a_no_leave_one_out_train_queries"]["config_A"]
        return {"loo_with": f(a["with_LOO"]["MAP"]), "loo_without": f(a["without_LOO"]["MAP"]),
                "leak_b": ci(leak["b_authority_train_plus_dev_links_vs_train_only_scoring_dev"]["config_A"]["inflation_[mean,lo95,hi95]"]["MAP"]),
                "leak_c": ci(leak["c_citation_scrubbing_off_vs_on_dev"]["config_A"]["difference_unscrubbed_minus_scrubbed_[mean,lo95,hi95]"]["MAP"]),
                "leak_d": ci(leak["d_temporal_filter_on_vs_off_dev"]["config_A"]["difference_on_minus_off_[mean,lo95,hi95]"]["MAP"])}
    body = carried("Leakage audit") or ""
    num = r"([+\-][\d.]+ \[[^\]]+\])"
    pats = {"loo": r"inflates Config A MAP from ([\d.]+) to ([\d.]+)", "leak_b": r"links changes dev MAP by " + num,
            "leak_c": r"Citation scrubbing off changes dev MAP of Config A by " + num, "leak_d": r"Temporal filter on vs off, Config A: " + num}
    out = {}
    for k, p in pats.items():
        m = re.search(p, body)
        if k == "loo":
            out["loo_with"], out["loo_without"] = (m.group(1), m.group(2)) if m else ("(see Leakage audit)", "(see Leakage audit)")
        else:
            out[k] = m.group(1) if m else "see Leakage audit"
    if body:
        warn("results/leakage_audit.json missing: contribution numbers taken from the carried 'Leakage audit' section")
    return out


# ------------------------------------------------------------------ assemble
L = ["# Pramaan", "", "**Pramaan: precedent finder for Indian law.** Role-aware, leak-safe prior case retrieval.", "",
     "CSD358 Information Retrieval hackathon, track T6 (vertical search), domain: Indian law. Given the facts and issues of an undecided case, the system ranks "
     "earlier Indian judgments it should cite and explains each result. *Every number below is loaded from files in `results/` by `scripts/make_readme.py`.*", "",
     "## What Pramaan is", "",
     "When a lawyer writes a judgment, they cite earlier judgments (precedents). Pramaan takes the facts and issues of a case that has not been decided yet and ranks the earlier judgments it is most likely to cite, "
     "then shows the reasons for each result: which similar cases cite it, how often it is cited, and how the score is made up. It is a student research prototype built on the IL-PCSR corpus, not legal advice, "
     "and it runs on one machine with no outside services (the AI assistant is optional).", ""]
seg("works")
L += ["## What works", "",
     "- Classical IR, implemented here: per-zone inverted and positional index with gap + variable-byte compression and skip pointers; tf-idf (lnc.ltc) and BM25; Boolean, phrase, proximity, zone, wildcard, spelling and Soundex queries; heap top-K, index elimination, champion lists, authority tiers and cluster pruning; reciprocal rank fusion; a Mercator-style crawl **simulation**.",
     "- **Config A**: tf-idf first stage (top 1000) re-scored with text + neighbour vote + authority (weights frozen from 5-fold CV on train).",
     "- A leakage audit, an efficiency study, paired bootstrap intervals, an API with a Search, Query Lab, Index Inspector, Evaluation, Efficiency and How it works UI.",
     "- An optional **AI assistant (Sarvam)** that explains the system, the results and the evaluation by text or voice; it never sees case text (see *How the assistant works*).", "",
     "### Planned", "",
     "A cited-answer layer, an agentic research flow, Indic and multilingual search, a learned re-ranker and other citation-linked fields are planned; see the Roadmap below. None of them is built.", ""]
seg("results")
if dev:
    L += ["## Headline results", "",
          f"Facts + Issues queries (citation strings scrubbed). Candidates: the full pool of {re.search(r'[0-9]+', dev['candidates']).group(0)} precedents minus the query's own case. "
          f"Dev: {dev['n_queries']} queries" + (f"; test: {test['n_queries']} queries, run once." if test else "; the test split has not been run."), "", headline(), ""]
    if test:
        L += [f"On **test**, Config A + temporal filter vs tf-idf: MAP difference {sig(test, AT)} (paired bootstrap, 1000 resamples); "
              f"Config A without the filter: {sig(test, A)}; the temporal filter alone adds {ci(test['bootstrap_diff_[mean,lo95,hi95]']['ConfigA_temporal_vs_ConfigA']['MAP'])} to Config A. "
              f"Config A vs tuned BM25: {ci(test['bootstrap_diff_[mean,lo95,hi95]']['ConfigA_vs_BM25_tuned']['MAP'])}.", ""]
    n = (test or dev)["notes"]
    cC = next((v for k_, v in (abl or {"rows": {}})["rows"].items() if "C_no_neighbour" in k_), None)
    nb_sentence = (f"the same net score built without it (config C, dev) reaches MAP {cC['MAP']:.4f} versus {find(dev, T)['MAP']:.4f} for tf-idf and {find(dev, A)['MAP']:.4f} for Config A" if cC else "see results/b2_ablation_dev.json")
    gd = find(dev, A)["MAP"] - find(dev, T)["MAP"]
    shift_sentence = (f"Config A beats tf-idf by {gd:+.4f} MAP on dev and by {find(test, A)['MAP'] - find(test, T)['MAP']:+.4f} on test" if test else f"the dev gain is {gd:+.4f} MAP")
    L += ["**How to read this.**", "",
          f"- The neighbour feature (cosine-nearest TRAIN queries voting for the precedents they cite) carries most of the gain: {nb_sentence}. N7 is a combination of known ideas (citation collaborative filtering, nearest-neighbour citation retrieval), not an invention.",
          f"- The pool contains only precedents cited somewhere in the corpus, which favours citation-based signals; neighbour MAP on train exceeds dev, so test may differ: {shift_sentence}.",
          f"- Config A here is the re-frozen three-feature version (`results/config_a_frozen.json`: weights {cfg['weights'] if cfg else 'n/a'}).",
          f"- The temporal filter drops candidates that are not strictly earlier than the query where both dates are known ({n['share_pairs_both_dates_known']:.1%} of pairs); it also removes {n['share_relevant_pairs_removed_by_filter']:.1%} of relevant precedents, which the data itself dates after the query.",
          f"- First-stage recall@1000 is {n['first_stage_recall_at_1000']:.4f}: a ceiling for every reranker. Rows marked REFERENCE (full-judgment query) are in `docs/results_tables.md`; they are not comparable.", ""]
else:
    # an older generator printed this placeholder literally; replace it with a pointer, never with a typed number
    L += carry("Headline results", body_filter=lambda b: b.replace("so test may differ: {shift_sentence}.", "so test may differ (compare the dev and test columns above)."))
if leak:
    a = leak["a_no_leave_one_out_train_queries"]["config_A"]
    L += ["## Leakage audit (dev, and train for the first line)", "",
          f"- Without leave-one-out, scoring train queries inflates Config A MAP from {a['with_LOO']['MAP']} to {a['without_LOO']['MAP']} ({ci(a['inflation_[mean,lo95,hi95]']['MAP'])}).",
          f"- Authority built from train + dev links changes dev MAP by {ci(leak['b_authority_train_plus_dev_links_vs_train_only_scoring_dev']['config_A']['inflation_[mean,lo95,hi95]']['MAP'])}.",
          f"- Citation scrubbing off changes dev MAP of Config A by {ci(leak['c_citation_scrubbing_off_vs_on_dev']['config_A']['difference_unscrubbed_minus_scrubbed_[mean,lo95,hi95]']['MAP'])}.",
          f"- Temporal filter on vs off, Config A: {ci(leak['d_temporal_filter_on_vs_off_dev']['config_A']['difference_on_minus_off_[mean,lo95,hi95]']['MAP'])}.", ""]
else:
    L += carry("Leakage audit (dev, and train for the first line)", "Leakage audit")
if eff:
    ex = eff["text_stage"][0]
    ch = next(x for x in eff["text_stage"] if "r=200" in x["method"])
    cl = next(x for x in eff["cluster_pruning"] if "b=3 (Config A)" in x["method"])
    L += ["## Efficiency (dev)", "",
          f"Exhaustive tf-idf scores {ex['mean_candidates_scored']} documents per query. Champion lists (r=200): {ch['mean_candidates_scored']} candidates, {ch['MAP_retained']:.0%} of MAP kept. "
          f"Cluster pruning of the neighbour search (b=3): {cl['mean_candidates_scored']} of 5017 train queries compared, {cl['MAP_retained']:.0%} of Config A MAP kept. "
          "Index elimination and authority tiers lose much more quality (see `docs/results_tables.md`). Latencies are Python wall times on one machine.", ""]
    if andb:
        L += [f"AND processing order (300 random 3-5 word queries): smallest list first needs {andb['df_order']['comparisons']:,} posting comparisons versus {andb['input_order']['comparisons']:,} as written.", ""]
else:
    L += carry("Efficiency (dev)", "Efficiency")
if idx:
    L += ["## Index", "", f"{idx['n_docs']} documents, {idx['tokens_all_zone']:,} indexed tokens; persisted size {idx['persisted_total']['gap_vbyte_mb']} MB with gap + variable-byte codes versus {idx['persisted_total']['raw_int32_mb']} MB raw.", ""]
else:
    L += carry("Index", body_filter=lambda b: "\n".join(l for l in b.splitlines() if not l.startswith("- **Run.**")).strip())

seg("setup")
L += ["## How to run it", "", "```bash", "git clone <repository-url> && cd <repository-folder>        # your own copy; no data is in the repository", "python3 -m venv .venv && source .venv/bin/activate", "pip install -r requirements.txt     # Python 3.10+", "```", "",
      "### Data (gated, never in this repository)", "",
      "IL-PCSR is released for research use only and is gated on Hugging Face. Create an account, open the IL-PCSR dataset page of the Exploration-Lab authors, accept the conditions (research use only, no commercial use, no redistribution), then download the five parquet files "
      "(`train_queries`, `dev_queries`, `test_queries`, `precedent_candidates`, `statute_candidates`) into `data/ilpcsr/`. Each member uses their own account and token. "
      "`data/`, `results/` and index files are git-ignored and must not be shared.", "",
      "### Run", "", "```bash", "make data      # data checks (aggregates only)", "make index     # build and persist the index", "make eval      # dev baselines, Config A, leakage audit, efficiency, figures",
      "make demo      # API + UI on http://127.0.0.1:8000  (sign-in on by default; AUTH_REQUIRED=0 turns it off; case text hidden unless SHOW_TEXT=1)", "make test      # pytest", "```", "",
      "Optional, for the AI assistant: get your own Sarvam AI key and put it in the environment of the shell that starts the server, without echoing it and without writing it to a file:", "",
      "```bash", "read -rs SARVAM_API_KEY && export SARVAM_API_KEY     # paste the key, press Enter; nothing is shown or saved in history", "make demo", "python scripts/assistant_smoke.py                    # one tiny chat, speech-to-text and text-to-speech call; prints OK or an error class only",
      "unset SARVAM_API_KEY                                 # when you are done", "```", "",
      "Without `SARVAM_API_KEY` the app works exactly as before and the assistant shows \"Assistant not configured\". `.env.example` lists the variables; the app reads the process environment only, never a `.env` file, and `.env` is git-ignored. Never paste the key into the code, a chat, an issue or a screenshot.", "",
      "### Sign-in, roles and the web app", "",
      "The web app asks for a local sign-in by default. Create the three demo accounts once with `python scripts/seed_demo_users.py`: it writes random passwords to `data/demo_credentials.txt` (git-ignored, mode 0600) and prints only that file's path. "
      "Roles: **Researcher** (search, compare, Query Lab, saved and history), **Analyst** (adds the Evaluation, Leakage and Efficiency dashboards) and **Admin** (adds the Index Inspector, system status and the user list). Each role has its own accent colour and navigation. "
      "Set `AUTH_REQUIRED=0` to run without sign-in (for the demo video and tests; `DEMO_ROLE=analyst` picks the role then). Passwords are hashed with scrypt, the session cookie is signed, HttpOnly and SameSite=Lax, and its secret is generated on first run into `data/`. "
      "This sign-in only separates what each role sees; it is **not** access control for the dataset, whose own terms apply.", "",
      "**Quick sign-in (local demo convenience only).** `make demo` sets `DEMO_QUICK_LOGIN=1`, which shows three role cards on the sign-in page; one click signs in as that role with no password and opens Search. The endpoint answers only when the flag is set **and** the request comes from a loopback address (127.0.0.1 or ::1), otherwise it returns 404, and forwarding headers are ignored. Role permissions are still enforced. "
      "It is a convenience, **not access control**: never enable it on a shared or hosted machine (`DEMO_QUICK_LOGIN=0 make demo` turns it off, and the password sign-in then works as before).", "",
      "Case text and titles are hidden unless the server runs with `SHOW_TEXT=1`; signing in never changes that. Saved searches and history store ids, settings and times only. "
      "The front end is plain JavaScript modules and CSS (no framework, no build step, no CDN; fonts are self-hosted in `app/web/fonts`), so it works offline; a Content-Security-Policy with `connect-src 'self'` keeps the browser on this server. Press `Ctrl/Cmd+K` for the command palette (fuzzy matching, recent actions), `Alt+A` for the assistant and `?` for shortcuts; `#/styleguide` shows every component in both themes. "
      "Animations (gliding result cards, chart draw-in, count-up numbers, the live pipeline strip) follow the system's reduced-motion setting and can be switched off in Settings > Reduce motion.", "",
      "Frozen weights and tuning artefacts are produced by `scripts/tune_bm25.py`, `scripts/run_b1.py`, `scripts/run_b2.py`, `scripts/freeze_config_a.py`; the final test run is `python -m irlegal.evaluation.runner --split test --final` (once; `results/final.lock`). See `docs/STATUS.md`.", ""]
seg("components")
L += ["## Components", ""]
for n in (1, 2, 3, 4):
    L += [(ROOT / "docs" / f"ws{n}.md").read_text().strip(), ""]

# (a) Research background
seg("research")
P = papers()
L += ["## Research background", "",
      "What earlier work did, what we take from it and what we do differently. Rows come from `docs/research_notes.md`; a status of RE-CHECK means the reference is not yet confirmed and must be checked before it is cited in the report.", "",
      "| Paper | What it did | What we take from it | What we do differently or add |", "|---|---|---|---|"]
for p in P:
    flag = "" if p["status"].startswith("VERIFIED") and "RE-CHECK" not in p["status"] else (" (RE-CHECK)" if p["status"].startswith("RE-CHECK") else " (part RE-CHECK)")
    L.append(f"| **{cell(p['short'])}**{flag} | {cell(p['did'])} | {cell(p['take'])} | {cell(p['differ'])} |")
def status_short(st):
    if st.startswith("RE-CHECK"):
        return "RE-CHECK"
    base = "VERIFIED, re-checked 2026-10-07" if "re-checked" in st else "VERIFIED"
    return base + ("; part RE-CHECK" if "RE-CHECK" in st else "")


L += ["", "### References", ""] + [f"- {p['citation']} *Status: {status_short(p['status'])}.*" for p in P] + [""]

# (b) Our contributions
seg("contrib")
nums = leak_numbers()
contrib = []
for b in bullets("Our contributions"):
    try:
        contrib.append(b.format(**nums))
    except (KeyError, IndexError) as e:
        warn(f"contribution placeholder {e} has no value; line kept without numbers")
        contrib.append(re.sub(r"\{[^}]+\}", "(see results)", b))
L += ["## Our contributions", "", "Framed honestly: what is ours and what is a known idea applied here. Numbers come from `results/`.", ""] + contrib + [""]

# (c) IR concepts and where they live (paths are checked)
seg("concepts")
rows = [l for l in note_section("IR concepts").splitlines() if l.startswith("|")]
for r in rows[2:]:
    for path in re.findall(r"`([^`]+)`", r.split("|")[3]):
        if not (ROOT / path).exists():
            warn(f"concept table names a missing path: {path}")
L += ["## IR concepts and where they live", "", "Course reference: Manning, Raghavan and Schütze, *Introduction to Information Retrieval* (IIR), unless another source is named. Every path below exists in this repository (checked by `scripts/make_readme.py`).", ""] + rows + [""]

# (d) Screenshots
seg("shots")
shots = [l[2:].split(" | ", 1) for l in note_section("Screenshots").splitlines() if l.startswith("- ") and " | " in l]
present = []
for fn, cap in shots:
    if (ROOT / "docs" / "figures" / "ui" / fn).exists():
        present.append((fn, cap))
    else:
        warn(f"screenshot docs/figures/ui/{fn} is missing; skipped")
L += ["## Screenshots", "", "Curated screenshots from `docs/figures/ui/` (no case text; captions say when the data is the toy corpus or the replies are mocked). The QA scripts write every other screenshot to the git-ignored `docs/figures/ui_all/`.", "",
      "| | |", "|---|---|"]
for i in range(0, len(present), 2):
    pair = present[i:i + 2]
    imgs = [f"![{cap}](docs/figures/ui/{fn})<br>*{cap}*" for fn, cap in pair]
    L.append("| " + " | ".join(imgs + [""] * (2 - len(imgs))) + " |")
slots = [l[2:] for l in note_section("Screenshot slots").splitlines() if l.startswith("- ")]
if slots:
    L += ["", "**Slots for future screenshots** (add the file to `docs/figures/ui/`, list it in `docs/research_notes.md`, re-run this script):", ""] + [f"- [ ] {s}" for s in slots]
L.append("")

# (e) Limitations and negative results
seg("limits")
lim = ["- The pool is made of precedents cited in the corpus; real search would face a much larger, unlabelled candidate set."] + [b for b in bullets("Caveats") if "pool contains only precedents" not in b]
if dev:
    n = (test or dev)["notes"]
    lim += [f"- First-stage recall@1000 is {n['first_stage_recall_at_1000']:.4f}, a hard ceiling for every reranker.",
            f"- The temporal filter removes {n['share_relevant_pairs_removed_by_filter']:.1%} of relevant precedents, which the data dates after their query.",
            f"- Dev ({dev['n_queries']} queries) was used for tuning choices that cross-validation could not make; the single test run is the only untouched estimate."]
else:
    m = re.search(r"Dev: (\d+) queries", carried("Headline results") or "")
    lim.append(f"- Dev{f' ({m.group(1)} queries)' if m else ''} was used for tuning choices that cross-validation could not make; the single test run is the only untouched estimate.")
lim.append("- Case titles and text are never printed by default; the UI shows ids, courts, years and scores. The assistant never receives them.")
L += ["## Limitations and negative results", "", "### Limitations", ""] + lim + ["", "### Negative and marginal results", "", "These were tried, measured with intervals where possible, and kept out of the headline system.", ""]
if wv or abl or dec or crawl:
    if wv:
        L.append(f"- **Learned zone-pair matrix.** Regularised variant (D18) on dev: MAP {ci([wv['dev']['MAP']['diff'], *wv['dev']['MAP']['ci95']])} vs tf-idf; survives the criterion: **{wv['survives_D18_criterion']}**. The first learned matrix also failed on dev (`results/zone_matrix.json`).")
    if abl:
        r = abl["rows"]
        k = next((nm for nm in r if nm.startswith("3 + statute")), None)
        if k:
            L.append(f"- **Statute channel.** Adds {ci(abl['diff_vs_tfidf_[mean,lo95,hi95]'][k]['MAP'])} MAP over tf-idf on dev (marginal). Query text is masked, so statute identities are mostly unavailable on the query side.")
        u = abl["union_recall"]
        L.append(f"- **Union first stage.** Dev recall {u['300']['dev_recall']} at a mean union size of {u['300']['dev_mean_union_size']} versus {u['tfidf_top1000_only']['dev_recall']} for tf-idf top 1000; no MAP gain, so it is not used.")
    if dec:
        r = dec["rows"]["RRF of issue sub-queries only"]
        L.append(f"- **Issue decomposition (N6).** {dec['mean_sub_queries_per_query']} sub-queries per query on average; RRF of sub-queries changes dev MAP by {ci(r['MAP_diff_vs_single_[mean,lo95,hi95]'])}.")
    if crawl:
        c = crawl["share_of_targets_fetched_by_budget"]
        n0, b0 = [k for k in c if k.startswith("priority (")][0], [k for k in c if k.startswith("BFS")][0]
        L.append(f"- **Crawl simulation (N5).** Share of the 200 most-cited documents fetched after 1000 / 3000 fetches: priority crawler {c[n0]['1000']} / {c[n0]['3000']}, BFS {c[b0]['1000']} / {c[b0]['3000']} (simulation, no live traffic; in-link priority did not beat BFS here).")
else:
    old = carried("Negative and marginal results") or carried("Negative and marginal results", level="### ")
    if old:
        L.append("\n".join(l for l in old.splitlines() if l.startswith("- ")))
        warn("results/ missing: negative results carried over unchanged from the existing README.md")
    else:
        warn("results/ missing and no negative results in the old README: list left empty")
L.append("")

# (f) How the assistant works
seg("assistant")
try:
    from app.assistant import config as acfg, languages as alang
    models = f"chat `{acfg.DEFAULT_CHAT_MODEL}`, speech to text `{acfg.DEFAULT_STT_MODEL}` (mode transcribe), text to speech `{acfg.DEFAULT_TTS_MODEL}` (speaker `{acfg.DEFAULT_TTS_SPEAKER}`), language identification `/text-lid`"
    limits = (f"at most {int(acfg.MAX_AUDIO_SECONDS)} s of audio per question (the documented REST limit) and {acfg.MAX_AUDIO_BYTES // 1000} kB; questions up to {acfg.MAX_QUESTION_CHARS} characters; "
              f"speech is synthesised sentence by sentence within the documented {acfg.TTS_LIMITS[acfg.DEFAULT_TTS_MODEL]}-character limit per request; a facts sheet of at most {acfg.FACTS_MAX_CHARS:,} characters; "
              f"per-session rate limits of {acfg.RATE_LIMITS['chat'][0]} questions, {acfg.RATE_LIMITS['stt'][0]} recordings and {acfg.RATE_LIMITS['tts'][0]} speech requests per minute")
    langs = f"replies in {len(alang.CHAT)} languages (English and {len(alang.CHAT) - 1} Indian languages), speech input in {len(alang.STT)}, spoken replies in {len(alang.TTS)}"
except Exception as e:  # the README must always build
    warn(f"could not read app/assistant/config.py ({type(e).__name__}); model list left generic")
    models, limits, langs = "see app/assistant/config.py", "see app/assistant/config.py", "see app/assistant/languages.py"
L += ["## How the assistant works and what it sends to a third party", "", note_section("Assistant"), "",
      f"**Models and limits** (environment variables `SARVAM_CHAT_MODEL`, `SARVAM_TTS_SPEAKER`, `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL` override the defaults): {models}; {langs}; {limits}.", "",
      "**Sent to Sarvam AI** (a third-party service; its own terms apply) only after a one-time consent click that is remembered in the browser:", "",
      "- the question the user typed, or the audio they recorded (as a WAV file);",
      "- the recent turns of the current conversation, which the browser keeps for this tab only (never stored on our server);",
      "- a facts sheet built on the server from whitelisted JSON files in `results/` (numbers only) and sections of `README.md`, `docs/STATUS.md` and `docs/research_notes.md`;",
      "- for \"Explain this result\" and \"Explain this metric\": ids, courts, years, scores, score components and the ids and similarities of the train cases that cite a result;",
      "- the text of a reply when it is read aloud.", "",
      "**Never sent:** case text, case titles or snippets (even when the server runs with `SHOW_TEXT=1`), text pasted into the Search box, passwords, session cookies. The key stays on the server: the browser never sees it and only talks to this server. "
      "Every number the assistant states must come from the facts sheet; if a number is not there it says it does not have it. It is an AI helper, not legal advice.", "",
      "**Code:** `app/assistant/` (service, facts sheet, client with retries on 5xx only, WAV handling, rate limit) and `app/routers/assistant_router.py` (`/api/assistant/status`, `/chat`, `/stt`, `/tts`); the panel is `app/web/ui/assistant/`. "
      "Tests: `tests/app/test_assistant.py` (Sarvam mocked; no key needed) and `scripts/assistant_qa.py` (Playwright with a fake microphone and mocked endpoints).", ""]

seg("roadmap")
ROADMAP = [
    ("1", "Cited answers (retrieval-augmented layer)", "Pramaan writes a short answer in which every statement cites retrieved case ids.", "every statement in a hand-checked set of answers cites at least one retrieved id, and the check is reported with the number of answers read"),
    ("2", "Agentic research flow", "The system plans sub-questions, searches, reads results and reports what it could not find.", "on dev queries, recall@20 of the flow is compared with Config A + temporal filter" + (f" (recall@20 {f(find(dev, AT)['R@20'])} today)" if dev and find(dev, AT) else "") + " with a paired bootstrap interval"),
    ("3", "Indic and multilingual search", "Queries and cases in Hindi and other Indian languages.", "a labelled multilingual query set exists and the same metrics (P@k, R@k, MAP) are reported per language"),
    ("4", "Learned re-ranker", "A trained re-ranker over the current features, kept leak-safe.", "beats Config A + temporal filter on dev MAP" + (f" ({f(find(dev, AT)['MAP'])} today)" if dev and find(dev, AT) else "") + " with an interval that excludes zero, then one run on test"),
    ("5", "Other citation-linked fields", "Scientific papers and patents, which also cite earlier work.", "the same pipeline runs on one such corpus with a leakage audit and the same report tables"),
]
L += ["## Roadmap", "", "Phases and the measurable goal that would finish each one. These are plans, not results; every number quoted in a goal comes from `results/`.", "",
      "| Phase | What | Measurable goal |", "|---|---|---|"] + [f"| {n}. {name} | {what} | {goal} |" for n, name, what, goal in ROADMAP] + [""]
seg("credits")
L += ["## Data credits and licences", "",
      "- **IL-PCSR**: Paul, Ghumare, Goyal, Ghosh, Modi, *IL-PCSR: Legal Corpus for Prior Case and Statute Retrieval*, EMNLP 2025. Licence on its Hugging Face page: CC BY-NC-SA 4.0, research use only. No data is redistributed here.",
      "- Case texts originate from Indian court judgments as compiled by the dataset authors.", "",
      "## AI use", "", "See `AI_USE.md`: which tool wrote which files, who reviewed them, and what the assistant feature sends to Sarvam AI.", "",
      "## Work division", "", "Each member owns, runs and can explain the components below. The work was developed together.", "", "- 2510110008: data loading and Facts+Issues queries with citation scrubbing, tokenizer, evaluation metrics, paired bootstrap, dev and test runner, leakage audit, landing page and evaluation dashboard, README generator.", "- 2410110026: query language (Boolean, phrase, proximity, wildcard, spelling, Soundex), statute bridge, issue decomposition, crawl simulation, server and sign-in, app shell and Query Lab.", "- 2410110246: tf-idf and BM25 baselines and tuning, zone-pair experiments, neighbour vote, authority and net score, Config A freeze, results tables, search API, design system, Search and Compare pages.", "- 2410110420: zone index with compression and skip pointers, efficiency study, Index Inspector and Efficiency pages, Sarvam assistant, packaging, research notes and concept map.", ""]
ORDER = ["head", "works", "setup", "research", "contrib", "concepts", "results", "shots", "limits", "roadmap", "assistant", "components", "credits"]
bounds = [("head", 0)] + SEG + [("end", len(L))]
parts = {}
for (name, a), (_, b) in zip(bounds, bounds[1:]):
    parts[name] = parts.get(name, []) + L[a:b]
missing = [n for n in ORDER if n not in parts]
if missing:
    warn(f"README sections not produced: {missing}")
L = [x for n in ORDER for x in parts.get(n, [])]
Path(args.out).write_text("\n".join(L), encoding="utf-8")
print(f"{Path(args.out).name} written, {len(L)} blocks, {len(WARN)} warning(s)")
