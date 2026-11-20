"""Build eval/labels.xlsx from eval/labels.csv: one row per sampled post, dropdowns for the answers.

    uv run --with openpyxl python -m eval.make_sheet      # then label in Excel / LibreOffice / Google Sheets
    uv run --with openpyxl python -m eval.import_labels   # writes the answers back into eval/labels.csv
"""
import csv
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from pipeline.taxonomy import CITIES, LEVELS, ROLES

ROOT = Path(__file__).resolve().parent.parent
rows = list(csv.DictReader(open(ROOT / "eval/labels.csv", encoding="utf-8")))
# SmartRecruiters rows were sampled before descriptions were fetched; fill them in so level can be judged.
desc = {}
for f in ("data/desc_cache.json",):
    p = ROOT / f
    if p.exists():
        desc.update(json.loads(p.read_text()))
for p in json.loads((ROOT / "data/posts.json").read_text()) if (ROOT / "data/posts.json").exists() else []:
    desc.setdefault(p["id"], p.get("description", ""))

F = "Arial"
HEAD = PatternFill("solid", fgColor="1F2937")
INPUT = PatternFill("solid", fgColor="FFF59D")
wb = Workbook()

ins = wb.active
ins.title = "Instructions"
lines = [
    ("How to label (about 30 minutes)", True),
    ("1. Go to the Labels tab. For each post, read the title, location and description (or open the link).", False),
    ("2. Fill only the yellow cells, using the dropdowns: Role, City 1 (City 2 and City 3 only if the post names more), Level.", False),
    ("3. Label what the post says, not what the model might say. Use Notes for anything unclear.", False),
    ("4. Save, then run:  uv run --with openpyxl python -m eval.import_labels", False),
    ("", False),
    ("Level rules (same definitions the LLM gets)", True),
    ("Internship: an internship or apprenticeship.", False),
    ("Fresher: open to new graduates / 0-1 years (trainee, graduate, entry level, 'freshers', '0-1 years').", False),
    ("Early career: asks for up to 2 years, or junior/associate/'Engineer I' with no stated requirement.", False),
    ("Experienced: asks for 3+ years, or is senior/lead/staff/manager level.", False),
    ("", False),
    ("City rules", True),
    ("Bangalore = Bengaluru. Gurugram/Gurgaon/Noida/New Delhi = Delhi NCR. Bombay/Navi Mumbai/Thane = Mumbai.", False),
    ("Remote / work from home: add Remote. An Indian city not in the list: Other India. Only 'India' or no city: India (unspecified).", False),
    ("", False),
    ("Role rule: pick by what the person does day to day, not the company's industry. Data/Business/MIS analyst = Data / Analytics / ML; QA, DevOps, SRE, security = Software Engineering; solutions/pre-sales engineers = Sales / Business Development.", False),
    ("", False),
    ("Example row (format only, not a real post)", True),
]
for i, (t, b) in enumerate(lines, 1):
    c = ins.cell(row=i, column=1, value=t)
    c.font = Font(name=F, bold=b, size=12 if b else 11)
    c.alignment = Alignment(wrap_text=True, vertical="top")
ex_r = len(lines) + 1
for j, (h, v) in enumerate([("Title", "Data Analyst Intern"), ("Location", "Gurugram, Haryana, India"),
                            ("Role", "Data / Analytics / ML"), ("City 1", "Delhi NCR"), ("City 2", ""),
                            ("Level", "Internship")]):
    ins.cell(row=ex_r, column=1 + j, value=h).font = Font(name=F, bold=True)
    ins.cell(row=ex_r + 1, column=1 + j, value=v).font = Font(name=F)
ins.column_dimensions["A"].width = 110
for col in "BCDEF":
    ins.column_dimensions[col].width = 22

lists = wb.create_sheet("Lists")
for j, (name, vals) in enumerate([("Role", ROLES), ("City", CITIES), ("Level", LEVELS)], 1):
    lists.cell(row=1, column=j, value=name).font = Font(name=F, bold=True)
    for i, v in enumerate(vals, 2):
        lists.cell(row=i, column=j, value=v).font = Font(name=F)
lists.sheet_state = "hidden"

ws = wb.create_sheet("Labels", 1)
heads = ["#", "id", "Company", "Title", "Location", "Link", "Description (excerpt)",
         "Role", "City 1", "City 2", "City 3", "Level", "Notes"]
widths = [5, 14, 16, 34, 24, 10, 80, 30, 20, 20, 20, 16, 30]
for j, (h, w) in enumerate(zip(heads, widths), 1):
    c = ws.cell(row=1, column=j, value=h)
    c.font = Font(name=F, bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.column_dimensions[c.column_letter].width = w
ws.freeze_panes = "D2"

n = len(rows)
for i, r in enumerate(rows, 2):
    old = [x.strip() for x in r.get("gold_cities", "").split(";") if x.strip()]
    text = (r["description_excerpt"] or desc.get(r["id"], ""))[:1500]
    vals = [i - 1, r["id"], r["company"], r["title"], r["location"], "open", text,
            r.get("gold_role", ""), *(old + ["", "", ""])[:3], r.get("gold_level", ""), r.get("notes", "")]
    for j, v in enumerate(vals, 1):
        c = ws.cell(row=i, column=j, value=v)
        c.font = Font(name=F, size=10)
        c.alignment = Alignment(wrap_text=j in (4, 7, 13), vertical="top")
        if 8 <= j <= 12:
            c.fill = INPUT
    link = ws.cell(row=i, column=6)
    link.hyperlink = r["url"]
    link.font = Font(name=F, size=10, color="0563C1", underline="single")
    ws.row_dimensions[i].height = 110

for col, ref in [("H", f"Lists!$A$2:$A${len(ROLES) + 1}"), ("I", f"Lists!$B$2:$B${len(CITIES) + 1}"),
                 ("J", f"Lists!$B$2:$B${len(CITIES) + 1}"), ("K", f"Lists!$B$2:$B${len(CITIES) + 1}"),
                 ("L", f"Lists!$C$2:$C${len(LEVELS) + 1}")]:
    dv = DataValidation(type="list", formula1=f"={ref}", allow_blank=True, showErrorMessage=True,
                        errorTitle="Pick from the list", error="Choose a value from the dropdown.")
    ws.add_data_validation(dv)
    dv.add(f"{col}2:{col}{n + 1}")

out = ROOT / "eval/labels.xlsx"
wb.save(out)
print(f"wrote {out} ({n} posts, {sum(1 for r in rows if not r['description_excerpt'] and desc.get(r['id']))} descriptions filled in)")
