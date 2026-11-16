"""Draw a stratified sample of 50 published posts for hand-labelling.

Writes eval/labels.csv with EMPTY gold columns (gold_role, gold_cities, gold_level).
Model predictions are deliberately NOT written into this file, so the labeller isn't anchored.
Stratified by source board so one big board (e.g. Bosch) doesn't dominate.

    python -m eval.sample [--n 50] [--seed 42]
"""
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=50)
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()

posts = json.loads((ROOT / "data/posts.json").read_text())
random.seed(args.seed)
by_company = defaultdict(list)
for p in posts:
    by_company[p["company"]].append(p)
for v in by_company.values():
    random.shuffle(v)

# round-robin across companies until n are drawn
sample, companies = [], sorted(by_company)
random.shuffle(companies)
while len(sample) < args.n:
    for c in companies:
        if by_company[c] and len(sample) < args.n:
            sample.append(by_company[c].pop())

out = ROOT / "eval/labels.csv"
if out.exists():
    raise SystemExit(f"{out} exists; refusing to overwrite hand labels. Delete it first if you mean to.")
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "company", "title", "location", "url", "description_excerpt",
                "gold_role", "gold_cities", "gold_level", "notes"])
    for p in sample:
        w.writerow([p["id"], p["company"], p["title"], p["location"], p["url"],
                    " ".join(p.get("description", "").split())[:600], "", "", "", ""])
(ROOT / "eval/sample_posts.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1))
print(f"wrote {out} ({len(sample)} posts from {len({p['company'] for p in sample})} companies)")
print("Fill gold_role / gold_cities (separate with ';') / gold_level by hand, using the label lists in pipeline/taxonomy.py.")
