# Fresher Jobs India

A live page of fresher jobs and internships in India.
- Collected every day from public company career-board APIs.
- De-duplicated.
- Tagged by role, city and experience level with an LLM (Gemini or Claude, whichever key is set).
- Searchable in the browser.

**Live page:** https://vibhorsi3733.github.io/gen-ai-project/
**Refresh:** GitHub Actions, daily at 06:00 IST ([workflow](.github/workflows/daily.yml))

---

## Architecture

```
 GitHub Actions cron (06:00 IST)
        │
        ▼
 pipeline/sources.py ── 33 public ATS job boards ─────────────────────────────┐
   Greenhouse · Lever · SmartRecruiters · Workable · Ashby (official, keyless) │  2,200 India posts
   (Adzuna India API supported, off unless a key is set)                     │
        │                                                                     │
        ▼                                                                     │
 India filter → dedup.py (URL → company+title+city key → cross-source fuzzy)  │  1,913 unique
        │                                                                     │
        ▼                                                                     │
 Drop obvious senior titles + "general application" placeholders (regex)      │    754 candidates
        │
        ▼
 tagger.py → Gemini or Claude (llm.py), 10 posts per call, JSON-schema output with enums
             role (14) · cities[] (11) · level (Internship/Fresher/Early career/Experienced)
             content-hash cache → only new or changed posts are sent each day
             every call's token usage is logged → measured cost
        │
        ▼
 city alias map (Bangalore→Bengaluru, Gurgaon→Delhi NCR…) overrides the LLM when the raw string is unambiguous
        │
        ▼
 Guard: < 150 entry-level posts, or a > 40 % drop → keep yesterday's site and fail the run (email)
        │
        ▼
 site/jobs.json + meta.json → committed → GitHub Pages
 site/index.html: vanilla JS search · role / city / level filters · shareable URL params
```

No server and no database. At about 1k rows a static JSON file is faster, free and can't go down. The git history doubles as a daily audit log of what changed.

## Skills insights tab

The **Skills insights** tab (`#insights`) shows which skills employers ask for, so a student can decide what to learn and where to apply.

- **Period:** Weekly (last 7 days), Monthly (last 30 days) or a custom date range. Every number is compared with the previous period of the same length.
- **Filters:** role, level (entry-level / intern + fresher / all) and skill type (technical vs professional).
- **KPIs:** posts in the period, most asked skill, fastest-rising skill, top hiring city.
- **Most asked skills:** share of posts mentioning each skill, with its change versus the previous period.
- **Demand over time:** weekly or monthly share of posts for up to 3 chosen skills.
- **Skills by location:** a heat map of city × skill, showing either the % of that city's posts or the post count. Cities with fewer than 8 posts are left out, because a handful of posts swings the percentages too much.
- **All skills table:** sortable and searchable, with top roles, top cities and the companies asking.
- **Every skill, bar and heat-map cell is clickable.** It opens the Jobs tab filtered to that skill (and city).

How it works:
- **Skills come from reading the JD, not the whole page.** [pipeline/skills.py](pipeline/skills.py) splits the description into sentences and drops company boilerplate ("About us", products, customers, benefits, legal text). It then matches a curated dictionary of about 85 skills, with aliases mapped to one name ("ReactJS" / "React.js" → React). Each skill keeps the sentence it came from.
- **The LLM judges those candidates** in the same call that tags role, city and level. It keeps the skills the job asks for, drops those about the company or with another meaning ("networking" with people), and may add one the scan missed.
- **Two safety rules** (`final_skills`):
  - a technical skill the post never mentions is dropped, so there are no invented skills;
  - if the LLM returns nothing while the scan found two or more skills, the scan's skills are used, because that's an omission rather than a judgment.
- **Without a key**, the dictionary over the JD sentences is used on its own.
- `python -m eval.skills_audit` writes [eval/SKILLS_AUDIT.md](eval/SKILLS_AUDIT.md) and `eval/skills_review.csv`. They cover each sampled post's skills from the old method, the JD scan and the LLM, with the evidence sentence and automatic flags (boilerplate-only, technical skill on a non-technical role). Mark `correct` y/n in the CSV and re-run to get a precision figure.
- SmartRecruiters and Workable list endpoints don't include descriptions, so they're fetched per job (Workable via `?details=true`, SmartRecruiters via the posting endpoint). Results are cached by id.
- `data/archive.json` keeps every post ever published, including closed ones, so trends build up day by day. Tracking started on 16 Nov 2026, so earlier weeks only contain posts that were still open then. The page says so under the trend chart.

## How the design was decided

The design came from two parallel proposals: a data-ingestion plan and an LLM/eval/deploy plan. Each was critiqued against the other before any build. The decisions that changed because of that debate:

| Question | Initial idea | Final decision and why |
|---|---|---|
| Sources | Internshala / Naukri / LinkedIn | **Rejected.** Their robots.txt files disallow job pages (checked) or their ToS prohibit scraping. We use only ATS APIs that companies publish for their own career pages. |
| Regex gate before the LLM | Only regex-matched "fresher" titles go to the LLM | **The LLM sees every non-senior post.** The regex can't see "0–1 years" buried in a plain "Software Engineer" post. Regex only hard-drops obvious senior titles. |
| Description sent to the LLM | First 500 chars | **Opening + experience/qualification sentences.** Greenhouse posts open with company boilerplate, and the experience requirement comes far later. |
| City output | Single city, with "Multiple" | **`cities[]`.** A Bengaluru filter must still find "Bangalore; Hyderabad" posts. |
| Fuzzy dedup | `token_set_ratio ≥ 92` everywhere | **`token_sort_ratio` across sources only, plus a seniority/level guard.** See "What broke". |
| Not enough strict fresher posts | Pad with older posts | **Every post gets a visible level badge.** The page defaults to entry-level (intern / fresher / 0–2 yrs), and the strict intern+fresher count is reported separately. |
| Guard failure | Fail if < 150 posts | **Never overwrite the last good data.** The run still commits the tag cache and the run report. |

## What broke and how it was fixed

1. **Most "obvious" Indian companies aren't on public ATS APIs.** Razorpay, PhonePe, Zomato, Postman, BrowserStack, Atlassian, Dream11 and others returned 404 on Greenhouse, Lever and Ashby: they use Workday or in-house portals. Of 59 extra slugs probed, only 4 worked. The fix was to keep a config list ([companies.json](pipeline/companies.json)) of the 33 boards that are verified to work. A board that 404s is logged and skipped, and doesn't break the run.
2. **Not enough strict fresher posts in mid-November.** About 2,200 India posts produced only about 110 intern/fresher posts by rule, because campus season is over. I handled it with honest labelling (level badges, a default entry-level view, separate counts) rather than padding. Adzuna is wired in as an optional volume source.
3. **Dedup deleted 291 real jobs.** URL canonicalisation stripped the whole query string, but Databricks job URLs differ only by `?gh_jid=`. The fix strips tracking parameters only (`utm_*`, `ref`, `source`…).
4. **Dedup merged different teams.** The title normaliser removed bracketed text, so "Senior SWE (Backend)" equalled "Senior SWE (App-Framework)". Brackets are now dropped only when they contain a location.
5. **Fuzzy matching merged different levels.** "Backend Engineer I" vs "II" scored 97, and "Sr. Solutions Architect" vs "Solutions Architect" also matched. `token_set_ratio` was worse still, because a subset title scores 100. The fixes:
   - switched to `token_sort_ratio`;
   - added a level-token guard (I/II, Sr, Staff, Intern…);
   - limited fuzzy matching to *cross-source* pairs, because on one ATS board every req id is a distinct opening.
6. **Greenhouse HTML is double-encoded** (`&lt;p&gt;`). Fixed with two `html.unescape` passes before stripping tags.
7. **"Internal Auditor" was tagged as an Internship** by the fallback regex (`\bintern`). Fixed with a word boundary: `\bintern(ship)?s?\b`.
8. **Placeholder and team-lead posts got through.** "Don't see what you're looking for?" and "Backend – TL/STL" were caught while drawing the eval sample. I added a placeholder filter and added TL/STL/Head/Mgr to the senior filter. "Associate Product Manager" is exempted, because it's a fresher role.
9. **The guard would have blocked the first LLM run.** The keyword fallback marks every non-senior post entry-level. The first LLM run would mark some of them Experienced, which looks like a > 40 % drop. The drop check now only compares runs tagged the same way.
10. **An empty repo variable broke model selection.** In Actions, an unset `vars.TAG_MODEL` arrives as `""`, not unset. Fixed with `os.environ.get(...) or default`.
11. **Recruiters were shown "Azure".** Skills were matched over the whole page. Every MongoDB post opens with "MongoDB Atlas … available across AWS, Google Cloud, and Microsoft Azure", so every MongoDB recruiter got AWS, Azure and GCP. The fix: skills now come from the JD's own sentences, with boilerplate removed and the LLM judging each candidate. AWS / Azure / GCP lost about 20 false matches each.
12. **The boilerplate filter then deleted real requirements.** HTML was flattened into one line, so a whole bullet list became a single 3,936-character "sentence". It contained "our customers" and was dropped, taking Python and Java with it. The fix: list items and paragraphs are kept as separate segments, and long blocks are never dropped whole.
13. **The first LLM prompt under-extracted.** "Prefer fewer skills" made the lite model drop SQL for a BI Developer. The fix: the LLM judges keyword candidates instead of extracting freely, and an empty answer with 2+ candidates counts as an omission. Bare-word aliases were tightened too: "algorithm" in a mission statement and "a data structure" in a video editor's duties no longer mean DSA.
14. **The Gemini free tier allows 20 requests per day per model.** At 10 posts per request, a full run needs about 75 requests. Gemini now uses 50-post batches (about 15 requests for a full run, 1–2 on a normal day), retries a failed batch in halves, and falls back to another model when one's daily quota or capacity runs out (3.8/3.7-flash returned 503/504 for long stretches).

## Accuracy: 50 hand-checked posts

Method ([eval/](eval/)):
1. `python -m eval.sample` draws 50 posts, stratified round-robin across the 33 company boards (seed 42). It writes `eval/labels.csv` with **empty** gold columns, so the labeller never sees model output.
2. I labelled role, cities and level by hand. `uv run --with openpyxl python -m eval.make_sheet` builds `eval/labels.xlsx` with dropdowns limited to the same values the LLM can choose; `python -m eval.import_labels` (same `uv run` prefix) checks the answers and writes them back to `labels.csv`.
3. `python -m eval.run_models` tags the same 50 posts with whichever model the key selects (or name one: `gemini-3.8-flash`, `claude-opus-5-5`). The keyword baseline is also scored, to show what the LLM adds.
4. `python -m eval.score` writes [eval/RESULTS.md](eval/RESULTS.md). It reports accuracy with Wilson 95% CIs, the cases where only the LLM or only the baseline is right, every disagreement, and cost per 1,000 posts from logged token usage.

> **Results:** _pending. Filled in from eval/RESULTS.md after the labelled run._

## Cost per 1,000 posts

Cost is **measured, not estimated**. Every API call appends `input_tokens` and `output_tokens` to `data/usage.jsonl`. Thinking tokens are billed as output on both providers and are included. `cost_report()` multiplies by list prices per million input / output tokens: Gemini 3.8 Flash $0.75 / $3.75 (introductory until 31 Dec 2026, then $1.50 / $7.50), Claude Opus 5.5 $4 / $20.

> **Measured:** _pending first LLM run._ The page footer shows the live figure.

Daily marginal cost is far lower than the per-1,000 figure suggests. The content-hash cache means only new or changed posts are sent, so a typical day sends a few dozen posts, not 750.

## Run it yourself

Needs Python 3.11+ (CI uses 3.12).

```bash
pip install -r requirements.txt
cp .env.example .env                   # optional: put ANTHROPIC_API_KEY in .env
python -m pipeline.run                 # writes site/jobs.json + site/meta.json
python -m http.server -d site 8000     # open http://localhost:8000
```

### LLM on or off

Two providers are supported through [pipeline/llm.py](pipeline/llm.py), with the same prompt and the same JSON schema. **Both keys are optional; one is enough.** The pipeline decides on every run:

| Keys set | What happens |
|---|---|
| `GEMINI_API_KEY` only | Gemini tags new or changed posts (default `gemini-3.8-flash`, thinking level low). |
| `ANTHROPIC_API_KEY` only | Claude tags them (default `claude-opus-5-5`, effort low). |
| Both | Claude, unless `LLM_PROVIDER=gemini` or `TAG_MODEL=gemini-…`. |
| Neither | Keyword tags. No API calls and no cost. |
| Key invalid, no credit, unknown model, or daily quota used up | One call fails, the run logs `LLM unavailable`, and every remaining post gets keyword tags. Posts tagged by keywords aren't cached, so the LLM tries them again once the key works. |

Cached tags are keyed by model, so switching provider re-tags each post once.

`data/run_report.json` records which case applied (`tagging.llm_status`), and the page footer shows which tagger produced the data.

Where the key goes:
- **Locally:** in `.env` (git-ignored; template in [.env.example](.env.example)). Variables already set in your shell take priority over `.env`.
- **Daily workflow:** as a repository secret. Run `gh secret set GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`), or use Settings → Secrets and variables → Actions. `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` are optional. The repo variables `LLM_PROVIDER` and `TAG_MODEL` are optional.

### Dependencies

[requirements.in](requirements.in) lists the direct dependencies. [requirements.txt](requirements.txt) is the fully pinned lock that CI installs. To upgrade, edit `requirements.in`, then run `uv pip compile requirements.in -o requirements.txt --python-version 3.12`.

### When a job board goes down

If a board fails on a run (timeout, 404, 5xx), its posts from the last good run are kept, because an outage doesn't mean the jobs closed. That lasts **3 days** (`CARRY_DAYS` in [run.py](pipeline/run.py)). After that, the board's posts are dropped, so a renamed slug or a company that changed ATS can't keep stale jobs on the page. `data/source_health.json` and the run report list every failing board, its error, and how many days it has been down.

## Files

| Path | What |
|---|---|
| [pipeline/sources.py](pipeline/sources.py) | Fetchers for Greenhouse, Lever, SmartRecruiters, Workable, Ashby and Adzuna |
| [pipeline/dedup.py](pipeline/dedup.py) | Three-layer dedup |
| [pipeline/llm.py](pipeline/llm.py) | Provider layer: picks Gemini or Claude from the keys, one call shape for both, fatal-error detection |
| [pipeline/tagger.py](pipeline/tagger.py) | LLM tagging, cache, usage logging, cost |
| [pipeline/taxonomy.py](pipeline/taxonomy.py) | Role, city and level label sets plus the city alias map |
| [pipeline/baseline.py](pipeline/baseline.py) | Keyword tagger (eval baseline and no-key fallback) |
| [pipeline/run.py](pipeline/run.py) | Orchestration, filters, guard, publish |
| [eval/](eval/) | Sampling, model runs, scoring |
| `data/` | Run report, duplicates log, tag cache, usage log, first-seen state, failing-source health, archive |
