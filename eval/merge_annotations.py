"""Merge two independent annotations of the 50 eval posts into the gold labels.

Method (stated in eval/ANNOTATION.md and the README):
  * two annotators (independent Claude agents, blind to the tagger's output and to each other)
    labelled role, cities, level, and judged each candidate skill y/n;
  * agreement is reported (raw % and Cohen's kappa);
  * where they agree, that is the gold label; where they disagree, eval/annotations/adjudication.json
    holds the adjudicated answer with a reason;
  * a human can overwrite any row in eval/labels.xlsx afterwards (eval.import_labels).

    python -m eval.merge_annotations            # report agreement + list disagreements
    python -m eval.merge_annotations --write    # also write labels.csv + skills_review.csv
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "eval/annotations"
A = {r["id"]: r for r in json.loads((D / "A.json").read_text())}
B = {r["id"]: r for r in json.loads((D / "B.json").read_text())}
ADJ_PATH = D / "adjudication.json"
ADJ = json.loads(ADJ_PATH.read_text()) if ADJ_PATH.exists() else {}
ids = list(A)


def kappa(xs, ys):
    n = len(xs)
    po = sum(x == y for x, y in zip(xs, ys)) / n
    ca, cb = Counter(xs), Counter(ys)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


fields = {"role": lambda r: r["role"], "cities": lambda r: tuple(sorted(r["cities"])), "level": lambda r: r["level"]}
stats, disagreements = {}, []
for f, get in fields.items():
    xs, ys = [get(A[i]) for i in ids], [get(B[i]) for i in ids]
    stats[f] = (sum(x == y for x, y in zip(xs, ys)), kappa(xs, ys))
    for i, x, y in zip(ids, xs, ys):
        if x != y:
            disagreements.append((i, f, x, y))
sk_pairs = [(A[i]["skills"].get(s), B[i]["skills"].get(s)) for i in ids for s in set(A[i]["skills"]) | set(B[i]["skills"])]
sk_agree = sum(a == b for a, b in sk_pairs)

lines = ["# Annotation agreement (50 posts)\n",
         "| Field | Agreement | Cohen's kappa |", "|---|---|---|"]
for f, (k, kp) in stats.items():
    lines.append(f"| {f} | {k}/50 ({k * 2}%) | {kp:.2f} |")
lines.append(f"| skills (y/n per candidate) | {sk_agree}/{len(sk_pairs)} ({100 * sk_agree / len(sk_pairs):.0f}%) | |")
print("\n".join(lines))
print(f"\n{len(disagreements)} field disagreements; adjudicated: {sum(1 for i, f, *_ in disagreements if f'{i}|{f}' in ADJ)}")
for i, f, x, y in disagreements:
    if f"{i}|{f}" not in ADJ:
        print(f"  {i} | {f} | A={x} | B={y}")

if "--write" in sys.argv:
    missing = [f"{i}|{f}" for i, f, *_ in disagreements if f"{i}|{f}" not in ADJ]
    if missing:
        raise SystemExit(f"adjudicate first: {missing}")
    gold = {}
    for i in ids:
        g = {}
        for f in fields:
            key = f"{i}|{f}"
            g[f] = ADJ[key]["value"] if key in ADJ else A[i][f]
        gold[i] = g
    path = ROOT / "eval/labels.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        g = gold[r["id"]]
        r["gold_role"], r["gold_level"] = g["role"], g["level"]
        r["gold_cities"] = ";".join(sorted(g["cities"]))
        adj = [ADJ[k]["reason"] for k in (f"{r['id']}|{f}" for f in fields) if k in ADJ]
        r["notes"] = "2 independent AI annotators (agreed)" if not adj else "2 AI annotators; adjudicated: " + "; ".join(adj)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    rp = ROOT / "eval/skills_review.csv"
    rev = list(csv.DictReader(open(rp, encoding="utf-8")))
    for r in rev:
        a, b = A[r["id"]]["skills"].get(r["skill"]), B[r["id"]]["skills"].get(r["skill"])
        key = f"{r['id']}|skill|{r['skill']}"
        r["correct"] = ADJ[key]["value"] if key in ADJ else (a if a == b else (a if a == "y" and b is None else ""))
    with open(rp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rev[0].keys()))
        w.writeheader()
        w.writerows(rev)
    unresolved = sum(1 for r in rev if not r["correct"])
    (ROOT / "eval/ANNOTATION.md").write_text("\n".join(lines) + f"""

## Method

The 50 posts were labelled by **two independent annotators**: separate Claude agents, each blind to the
tagger's predictions and to the other annotator, given the same written guideline (the taxonomy definitions
in `pipeline/tagger.py`). Where they agreed, that label is gold. The {len(disagreements)} field
disagreements were adjudicated by reading the job description; each decision and its reason is in
`eval/annotations/adjudication.json` and in the `notes` column of `eval/labels.csv`.

The tagger being evaluated is **Gemini** and the annotators are **Claude**, so the model is not grading itself.
These are AI annotations, not a human hand-check. A human can overwrite any row in `eval/labels.xlsx`
and re-run `eval.import_labels` + `eval.score`.

Skill judgements: {sk_agree} of {len(sk_pairs)} candidate skills got the same y/n from both annotators;
{unresolved} split decisions are left unmarked and excluded from the skills precision figure.
""")
    print("wrote eval/labels.csv, eval/skills_review.csv, eval/ANNOTATION.md")
