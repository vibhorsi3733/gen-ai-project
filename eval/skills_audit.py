"""Audit the skills shown on job cards, for the 50 sampled posts.

For each post it lists the skills from three methods, each skill with the sentence it came from:
  old    dictionary over the whole page (what the site showed before 20 Nov: MongoDB recruiters got Azure)
  rules  dictionary over the JD only, company/benefit boilerplate removed (no-key fallback)
  llm    the LLM reading the JD (eval/preds_<model>.json, written by eval.run_models), grounded in the text
Automatic flags (no human needed):
  boilerplate-only  skill found only in company/legal text, not in the job itself
  off-role          a technical skill on a non-technical role (HR, Sales, Finance, Ops, Support, Content)
Human check (optional): fill the `correct` column (y/n) in eval/skills_review.csv and re-run; the script
then reports precision per method.

    python -m eval.skills_audit
"""
import csv
import json
from pathlib import Path

from pipeline.skills import SKILL_CATEGORY, extract_skills, mentioned_anywhere, skill_evidence

ROOT = Path(__file__).resolve().parent.parent
NON_TECH = {"HR / Recruiting", "Sales / Business Development", "Finance / Accounting", "Operations / Supply Chain",
            "Customer Support / Success", "Content / Writing", "Marketing"}
TECH_CATS = {"Programming", "Web & mobile", "Cloud & DevOps", "Databases"}

sample = json.loads((ROOT / "eval/sample_posts.json").read_text())
cache = ROOT / "data/desc_cache.json"
desc = json.loads(cache.read_text()) if cache.exists() else {}
posts = {p["id"]: p for p in json.loads((ROOT / "data/posts.json").read_text())} if (ROOT / "data/posts.json").exists() else {}
for p in sample:   # use the freshest description the pipeline has for this post
    p["description"] = (posts.get(p["id"]) or {}).get("description") or desc.get(p["id"]) or p.get("description", "")

llm_files = sorted((ROOT / "eval").glob("preds_*.json"))
llm_preds = {f.stem.removeprefix("preds_"): json.loads(f.read_text()) for f in llm_files if f.stem != "preds_baseline"}
llm_name, llm = next(iter(llm_preds.items()), (None, {}))

review_path = ROOT / "eval/skills_review.csv"
old_marks = {}
if review_path.exists():
    for r in csv.DictReader(open(review_path, encoding="utf-8")):
        if r.get("correct", "").strip():
            old_marks[(r["id"], r["skill"])] = r["correct"].strip().lower()[:1]

methods = {"old": {}, "rules": {}}
if llm_name:
    methods["llm"] = {}
rows, lines = [], [f"# Skills audit: {len(sample)} sampled posts\n",
                   f"LLM column: `{llm_name or 'not run yet (python -m eval.run_models)'}`.\n"]
flags = {m: {"boilerplate-only": 0, "off-role": 0, "skills": 0} for m in methods}
for p in sample:
    t, d, co = p["title"], p.get("description", ""), p["company"]
    ev = skill_evidence(t, d, co)                            # skill -> JD sentence (boilerplate excluded)
    anywhere = mentioned_anywhere(t, d)
    role = (llm.get(p["id"]) or {}).get("role") or p.get("role", "")
    methods["old"][p["id"]] = sorted(anywhere, key=list(SKILL_CATEGORY).index)
    methods["rules"][p["id"]] = extract_skills(t, d, co)
    if llm_name:
        methods["llm"][p["id"]] = (llm.get(p["id"]) or {}).get("skills", [])
    lines.append(f"## {t} · {co}\nRole: {role or '?'}\n")
    lines.append("| Skill | old | rules | llm | Evidence in the JD | Flag |\n|---|---|---|---|---|---|")
    union = sorted(set().union(*(m[p["id"]] for m in methods.values())), key=list(SKILL_CATEGORY).index)
    for s in union:
        flag = []
        if s not in ev:
            flag.append("boilerplate-only")
        if role in NON_TECH and SKILL_CATEGORY.get(s) in TECH_CATS:
            flag.append("off-role")
        for m, res in methods.items():
            if s in res[p["id"]]:
                flags[m]["skills"] += 1
                for f in flag:
                    flags[m][f] += 1
        tick = lambda m: "✓" if m in methods and s in methods[m][p["id"]] else ""
        lines.append(f"| {s} | {tick('old')} | {tick('rules')} | {tick('llm')} | {ev.get(s, '—')[:150].replace('|', '/')} | {', '.join(flag)} |")
        rows.append({"id": p["id"], "title": t, "company": co, "role": role, "skill": s,
                     "old": tick("old"), "rules": tick("rules"), "llm": tick("llm"),
                     "evidence": ev.get(s, ""), "flag": ", ".join(flag), "correct": old_marks.get((p["id"], s), "")})
    if not union:
        lines.append("| (no skills from any method) | | | | | |")
    lines.append("")

summary = ["## Summary\n", "| Method | Skills shown | Boilerplate-only | Off-role technical | Reviewer-checked precision |",
           "|---|---|---|---|---|"]
for m, f in flags.items():
    marked = [(pid, s) for pid, res in methods[m].items() for s in res if (pid, s) in old_marks]
    prec = (f"{sum(old_marks[k] == 'y' for k in marked) / len(marked):.0%} of {len(marked)}" if marked else "not marked yet")
    summary.append(f"| {m} | {f['skills']} | {f['boilerplate-only']} | {f['off-role']} | {prec} |")
summary.append("\nBoilerplate-only and off-role counts are automatic signals, not ground truth: open the review sheet "
               "(`eval/skills_review.csv`), mark `correct` y/n, and re-run for a real precision figure.\n")
(ROOT / "eval/SKILLS_AUDIT.md").write_text("\n".join(lines[:2] + summary + lines[2:]))
with open(review_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("\n".join(summary))
print(f"wrote eval/SKILLS_AUDIT.md and {review_path.relative_to(ROOT)} ({len(rows)} post-skill rows)")
