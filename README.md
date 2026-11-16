# Fresher Jobs India

A live page of fresher jobs and internships in India.
- Collected every day from public company career-board APIs.
- De-duplicated.
- Tagged by role, city and experience level with an LLM (Claude).
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
 tagger.py → Claude, 10 posts per call, JSON-schema output with enums
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
- [pipeline/skills.py](pipeline/skills.py) matches each post's title and description against a curated dictionary of about 100 skills, with aliases mapped to one name ("ReactJS" / "React.js" → React).
- A dictionary, rather than the LLM, keeps names canonical and countable. It's also free and works without an API key.
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

## Accuracy: 50 hand-checked posts

Method ([eval/](eval/)):
1. `python -m eval.sample` draws 50 posts, stratified round-robin across the 33 company boards (seed 42). It writes `eval/labels.csv` with **empty** gold columns, so the labeller never sees model output.
2. I labelled role, cities and level by hand in `labels.csv`.
3. `python -m eval.run_models claude-opus-5-5` tags the same 50 posts. The keyword baseline is also scored, to show what the LLM adds.
4. `python -m eval.score` writes [eval/RESULTS.md](eval/RESULTS.md). It reports accuracy with Wilson 95% CIs, the cases where only the LLM or only the baseline is right, every disagreement, and cost per 1,000 posts from logged token usage.

> **Results:** _pending. Filled in from eval/RESULTS.md after the labelled run._

## Cost per 1,000 posts

Cost is **measured, not estimated**. Every API call appends `input_tokens` and `output_tokens` to `data/usage.jsonl`. The thinking tokens Opus 5.5 always uses are billed as output and included. `cost_report()` multiplies by list prices (Opus 5.5: $4 / $20 per million input / output tokens).

> **Measured:** _pending first LLM run._ The page footer shows the live figure.

Daily marginal cost is far lower than the per-1,000 figure suggests. The content-hash cache means only new or changed posts are sent, so a typical day sends a few dozen posts, not 750.

## Run it yourself

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...           # without it the pipeline falls back to keyword tags
python -m pipeline.run                 # writes site/jobs.json + site/meta.json
python -m http.server -d site 8000     # open http://localhost:8000
```

Repo secrets for the daily workflow: `ANTHROPIC_API_KEY` (required for LLM tags). `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` are optional. The repo variable `TAG_MODEL` is optional (default `claude-opus-5-5`).

## Files

| Path | What |
|---|---|
| [pipeline/sources.py](pipeline/sources.py) | Fetchers for Greenhouse, Lever, SmartRecruiters, Workable, Ashby and Adzuna |
| [pipeline/dedup.py](pipeline/dedup.py) | Three-layer dedup |
| [pipeline/tagger.py](pipeline/tagger.py) | Claude tagging, cache, usage logging, cost |
| [pipeline/taxonomy.py](pipeline/taxonomy.py) | Role, city and level label sets plus the city alias map |
| [pipeline/baseline.py](pipeline/baseline.py) | Keyword tagger (eval baseline and no-key fallback) |
| [pipeline/run.py](pipeline/run.py) | Orchestration, filters, guard, publish |
| [eval/](eval/) | Sampling, model runs, scoring |
| `data/` | Run report, duplicates log, tag cache, usage log, first-seen state |
