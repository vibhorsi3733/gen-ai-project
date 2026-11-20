"""Copy the hand labels from eval/labels.xlsx back into eval/labels.csv (the file eval.score reads).

    uv run --with openpyxl python -m eval.import_labels
"""
import csv
from pathlib import Path

from openpyxl import load_workbook

from pipeline.taxonomy import CITIES, LEVELS, ROLES

ROOT = Path(__file__).resolve().parent.parent
ws = load_workbook(ROOT / "eval/labels.xlsx", data_only=True)["Labels"]
head = [c.value for c in ws[1]]
got = {}
problems = []
for row in ws.iter_rows(min_row=2, values_only=True):
    r = dict(zip(head, row))
    if not r["id"]:
        continue
    s = lambda k: (r.get(k) or "").strip()
    cities = list(dict.fromkeys(c for c in (s("City 1"), s("City 2"), s("City 3")) if c))
    for v, ok, what in [(s("Role"), ROLES, "role"), (s("Level"), LEVELS, "level")] + [(c, CITIES, "city") for c in cities]:
        if v and v not in ok:
            problems.append(f"#{r['#']} {what} '{v}' is not in the list")
    if not (s("Role") and s("Level") and cities):
        problems.append(f"#{r['#']} {r['Title'][:40]!r}: missing " +
                        ", ".join(k for k, v in [("role", s("Role")), ("city", cities), ("level", s("Level"))] if not v))
    got[r["id"]] = {"gold_role": s("Role"), "gold_cities": ";".join(cities), "gold_level": s("Level"), "notes": s("Notes")}

path = ROOT / "eval/labels.csv"
rows = list(csv.DictReader(open(path, encoding="utf-8")))
fields = list(rows[0].keys())
for r in rows:
    r.update(got.get(r["id"], {}))
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
done = sum(1 for r in rows if r["gold_role"] and r["gold_level"] and r["gold_cities"])
print(f"updated {path}: {done}/{len(rows)} posts fully labelled")
for p in problems:
    print("  ", p)
