"""Score every eval/preds_*.json against the hand labels in eval/labels.csv.

Reports, per arm: role / cities / level / role+cities accuracy with Wilson 95% CIs,
paired discordant counts vs the baseline (McNemar-style), cost per 1,000 posts from
logged usage, and every disagreement (for the write-up). Writes eval/RESULTS.md.

    python -m eval.score
"""
import csv
import json
import math
from pathlib import Path

from pipeline.tagger import USAGE_PATH, PRICES

ROOT = Path(__file__).resolve().parent.parent


def wilson(k: int, n: int) -> str:
    if not n:
        return "n/a"
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{100 * p:.0f}% [{100 * (c - h):.0f}-{100 * (c + h):.0f}]"


def cost_per_1k(model: str, n_posts: int) -> str:
    """Cost of the eval run itself for this model (last n_posts logged for it)."""
    if not USAGE_PATH.exists():
        return "n/a"
    rows = [json.loads(l) for l in USAGE_PATH.read_text().splitlines()]
    rows = [r for r in rows if r["model"] == model]
    got, cost, tin, tout = 0, 0.0, 0, 0
    for r in reversed(rows):
        if got >= n_posts:
            break
        pin, pout = PRICES[model]
        cost += r["input_tokens"] / 1e6 * pin + r["output_tokens"] / 1e6 * pout
        tin += r["input_tokens"]
        tout += r["output_tokens"]
        got += r["posts"]
    if not got:
        return "n/a"
    return f"${cost / got * 1000:.3f} (in {tin / got:.0f} / out {tout / got:.0f} tok per post)"


gold = {}
with (ROOT / "eval/labels.csv").open() as f:
    for r in csv.DictReader(f):
        if not r["gold_role"].strip():
            raise SystemExit(f"row {r['id']} has no gold_role - finish hand labelling first")
        gold[r["id"]] = {"role": r["gold_role"].strip(), "level": r["gold_level"].strip(),
                         "cities": sorted(c.strip() for c in r["gold_cities"].split(";") if c.strip()),
                         "title": r["title"], "location": r["location"]}

arms = {p.stem.removeprefix("preds_"): json.loads(p.read_text()) for p in sorted((ROOT / "eval").glob("preds_*.json"))}
n = len(gold)
lines = [f"# Tagging accuracy on {n} hand-labelled posts\n",
         "Accuracy with Wilson 95% confidence interval. `cities` must match the gold set exactly.\n",
         "| Arm | Role | Cities | Role + cities | Level | Cost / 1,000 posts |", "|---|---|---|---|---|---|"]
correct = {}
for arm, preds in arms.items():
    rc = cc = bc = lc = ln = 0
    correct[arm] = {}
    for pid, g in gold.items():
        pr = preds.get(pid, {})
        r_ok = pr.get("role") == g["role"]
        c_ok = sorted(pr.get("cities") or []) == g["cities"]
        rc += r_ok
        cc += c_ok
        bc += r_ok and c_ok
        if pr.get("level") is not None and g["level"]:
            ln += 1
            lc += pr["level"] == g["level"]
        correct[arm][pid] = (r_ok, c_ok)
    cost = "free" if arm == "baseline" else cost_per_1k(arm, n)
    lines.append(f"| {arm} | {wilson(rc, n)} | {wilson(cc, n)} | {wilson(bc, n)} | "
                 f"{wilson(lc, ln) if ln else 'n/a'} | {cost} |")

if "baseline" in arms:
    lines += ["", "## Paired comparison on role (posts where exactly one arm is right)", ""]
    for arm in arms:
        if arm == "baseline":
            continue
        only_llm = sum(correct[arm][i][0] and not correct["baseline"][i][0] for i in gold)
        only_base = sum(correct["baseline"][i][0] and not correct[arm][i][0] for i in gold)
        lines.append(f"- {arm} right & baseline wrong: **{only_llm}**; baseline right & {arm} wrong: **{only_base}**")

for arm, preds in arms.items():
    if arm == "baseline":
        continue
    lines += ["", f"## Disagreements: {arm}", "", "| Title | Location | Gold | Predicted |", "|---|---|---|---|"]
    for pid, g in gold.items():
        pr = preds.get(pid, {})
        bad = []
        if pr.get("role") != g["role"]:
            bad.append(("role", g["role"], pr.get("role")))
        if sorted(pr.get("cities") or []) != g["cities"]:
            bad.append(("cities", "; ".join(g["cities"]), "; ".join(pr.get("cities") or [])))
        if g["level"] and pr.get("level") and pr["level"] != g["level"]:
            bad.append(("level", g["level"], pr["level"]))
        for field, gv, pv in bad:
            lines.append(f"| {g['title'][:60]} | {g['location'][:40]} | {field}: {gv} | {pv} |")

out = "\n".join(lines) + "\n"
(ROOT / "eval/RESULTS.md").write_text(out)
print(out)
