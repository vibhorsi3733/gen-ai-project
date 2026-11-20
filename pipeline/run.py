"""Daily pipeline: fetch -> India filter -> de-dup -> LLM tag -> guard -> publish JSON.

Usage:  python -m pipeline.run [--no-llm]
Writes: site/jobs.json, site/meta.json (served by GitHub Pages)
        data/posts.json (last good snapshot), data/state.json (first/last seen),
        data/run_report.json, data/dupes.json, data/tags_cache.json, data/usage.jsonl,
        data/source_health.json (boards currently failing, and since when)
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor

from .dedup import dedupe
from .skills import SKILL_CATEGORY, extract_skills
from .sources import fetch_all, smartrecruiters_description
from .tagger import MODEL, cost_report, tag_posts

ROOT = Path(__file__).resolve().parent.parent
DATA, SITE = ROOT / "data", ROOT / "site"
MIN_ENTRY = 150         # below this, keep yesterday's site instead of publishing a broken one
MAX_DROP = 0.40         # or if the entry-level count falls more than 40% vs the last good run
CARRY_DAYS = 3          # a failing board's posts are kept for this many days, then dropped

SENIOR = re.compile(r"(?<![a-z])(senior|sr\.?|lead|staff|principal|director|head|leader|vp|architect|manager|mgr|tl|stl)\b", re.I)
PLACEHOLDER = re.compile(r"(don.t see|general application|talent (pool|community)|future opportunit|expression of interest|open application)", re.I)
MGMT_TRAINEE = re.compile(r"\b((management|graduate) trainee|associate product manager|apm)\b", re.I)  # fresher roles despite "manager"
YEARS = re.compile(r"\b([3-9]|1[0-9])\s*\+?\s*(-|to)?\s*\d*\s*(years|yrs)", re.I)
FRESH = re.compile(r"\b(intern(ship)?|fresher|graduate|trainee|new grad|apprentice|campus|entry[- ]level|"
                   r"junior|associate|analyst|sde[- ]?(i|1)|engineer[- ](i|1))\b|\b0\s*(-|to)\s*[12]\s*(years|yrs)", re.I)


def rule_fresher(p: dict) -> bool:
    """Regex opinion, stored next to the LLM's so the write-up can report agreement."""
    t = p["title"]
    if SENIOR.search(t) and not MGMT_TRAINEE.search(t):
        return False
    if YEARS.search(p.get("description", "")[:1500]):
        return False
    return bool(FRESH.search(t) or FRESH.search(p.get("description", "")[:800]) or "intern" in p.get("commitment", "").lower())


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def enrich_descriptions(posts: list[dict]) -> None:
    """SmartRecruiters lists come without descriptions (~40% of posts). Fetch them per job,
    only for posts that reached this stage, cached by id so each day only new posts cost a request."""
    cache_path = DATA / "desc_cache.json"
    cache = load(cache_path, {})
    todo = [p for p in posts if p["id"].startswith("sr:") and not p.get("description") and p["id"] not in cache]

    def fetch(p):
        try:
            return p["id"], smartrecruiters_description(p["id"])
        except Exception as e:  # noqa: BLE001 - a missing description only costs us skills for that post
            print(f"  description fetch failed for {p['id']}: {str(e)[:80]}")
            return p["id"], None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for pid, text in pool.map(fetch, todo):
            if text is not None:
                cache[pid] = text
    live = {p["id"] for p in posts}
    cache = {k: v for k, v in cache.items() if k in live}  # forget closed posts so the file stays small
    DATA.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    for p in posts:
        if not p.get("description") and p["id"] in cache:
            p["description"] = cache[p["id"]]
    print(f"descriptions: fetched {len(todo)} new SmartRecruiters descriptions")


def update_archive(posts: list[dict], today: str, fetched_ids: set[str]) -> list[dict]:
    """Every post ever published, kept after it closes, so weekly/monthly skill trends build up
    over time. Without it, history would only contain posts that happen to still be open."""
    path = DATA / "archive.json"
    arch = load(path, {})
    published = {p["id"] for p in posts}
    # Still listed by its board but now filtered out (e.g. a rule change) -> not a closed job, remove it.
    arch = {k: v for k, v in arch.items() if k in published or k not in fetched_ids}
    for p in posts:
        arch[p["id"]] = {
            "id": p["id"], "company": p["company"], "title": p["title"], "url": p["url"],
            "role": p["role"], "cities": p["cities"], "level": p["level"], "skills": p["skills"],
            "posted": p.get("posted_at") or p["first_seen"], "first_seen": p["first_seen"], "last_seen": today,
        }
    path.write_text(json.dumps(arch, ensure_ascii=False, indent=0, sort_keys=True))
    return list(arch.values())


def main(use_llm: bool = True) -> int:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    raw, report = fetch_all()

    # A source that errored this run keeps its previous posts (an outage is not an expiry).
    prev = load(DATA / "posts.json", [])
    failed_sources = {k for k, v in report.items() if not v.get("ok")}
    # ...but only for a few days: a board that stays down (slug renamed, company moved ATS)
    # must not keep showing its old, possibly closed, jobs forever.
    health = load(DATA / "source_health.json", {})
    health = {k: v for k, v in health.items() if k in failed_sources}  # recovered -> reset
    for k in failed_sources:
        health.setdefault(k, {"failing_since": today})
        health[k]["error"] = report[k].get("error", "")
        health[k]["days_failing"] = (now.date() - datetime.strptime(health[k]["failing_since"], "%Y-%m-%d").date()).days
    expired = {k for k, v in health.items() if v["days_failing"] >= CARRY_DAYS}
    carried = [p for p in prev if p.get("_board") in failed_sources - expired]
    DATA.mkdir(exist_ok=True)
    (DATA / "source_health.json").write_text(json.dumps(health, indent=1, sort_keys=True))
    if expired:
        print(f"sources down for {CARRY_DAYS}+ days, their posts are dropped: {sorted(expired)}")
    for p in raw:
        p["_board"] = p["id"].split(":")[0] + ":" + p["id"].split(":")[1] if not p["id"].startswith("az:") else "adzuna"
    # normalise board key to match report keys
    ats_name = {"gh": "greenhouse", "lv": "lever", "sr": "smartrecruiters", "wk": "workable", "ab": "ashby"}
    for p in raw:
        if p["_board"] != "adzuna":
            pre, slug = p["_board"].split(":")
            p["_board"] = f"{ats_name[pre]}:{slug}"
    raw += carried

    # ATS records first so they win over aggregator copies of the same opening
    raw.sort(key=lambda p: (p["source"] == "Adzuna", p["company"], p["title"]))
    posts, dupes = dedupe(raw)
    print(f"fetched {len(raw)} India posts ({len(carried)} carried over), {len(posts)} after de-dup, {len(dupes)} dupes")

    # Hard pre-filter: obvious senior titles never reach the LLM (near-zero risk, cuts volume ~60%).
    placeholder = [p for p in posts if PLACEHOLDER.search(p["title"])]
    senior = [p for p in posts if SENIOR.search(p["title"]) and not MGMT_TRAINEE.search(p["title"])]
    drop = {id(p) for p in placeholder + senior}
    posts = [p for p in posts if id(p) not in drop]
    print(f"dropped {len(senior)} senior titles + {len(placeholder)} placeholder posts; {len(posts)} go to the tagger")

    enrich_descriptions(posts)
    for p in posts:
        p["skills"] = extract_skills(p["title"], p.get("description", ""))

    stats = tag_posts(posts, use_llm=use_llm)
    stats["senior_title_dropped"] = len(senior)
    stats["placeholder_dropped"] = len(placeholder)
    print("tagging:", stats)

    state = load(DATA / "state.json", {})
    for p in posts:
        p["rule_fresher"] = rule_fresher(p)
        if p.get("level") is None:  # LLM unavailable -> regex opinion
            p["level"] = ("Internship" if re.search(r"\bintern(ship)?s?\b", p["title"], re.I)
                          else "Fresher" if p["rule_fresher"] else "Early career")
        s = state.setdefault(p["id"], {"first_seen": today})
        s["last_seen"] = today
        p["first_seen"] = s["first_seen"]

    entry = [p for p in posts if p["level"] != "Experienced"]
    strict = [p for p in posts if p["level"] in ("Internship", "Fresher")]
    model_label = MODEL if stats["fallback"] < len(posts) else "keyword rules (LLM unavailable)"
    last_meta = load(SITE / "meta.json", {})
    # Only compare like with like: a rules-tagged run marks every non-senior post entry-level,
    # so the first LLM run after it would look like a big "drop" and wrongly trip the guard.
    last_n = last_meta.get("entry_posts", 0) if last_meta.get("model") == model_label else 0
    guard_msg = None
    if len(entry) < MIN_ENTRY:
        guard_msg = f"only {len(entry)} entry-level posts (< {MIN_ENTRY})"
    elif last_n and len(entry) < last_n * (1 - MAX_DROP):
        guard_msg = f"entry-level posts fell {last_n} -> {len(entry)} (> {int(MAX_DROP * 100)}% drop)"

    DATA.mkdir(exist_ok=True)
    (DATA / "run_report.json").write_text(json.dumps({"at": now.isoformat(), "sources": report, "tagging": stats,
                                                      "entry_level": len(entry), "intern_or_fresher": len(strict),
                                                      "published": len(posts),
                                                      "carried_over": len(carried), "failing_sources": health,
                                                      "guard": guard_msg}, indent=1))
    (DATA / "dupes.json").write_text(json.dumps(dupes, indent=1, ensure_ascii=False))
    if guard_msg:
        print(f"GUARD TRIPPED: {guard_msg}. Keeping the last good site/jobs.json.")
        return 1

    public_fields = ["id", "source", "company", "title", "location", "url", "posted_at", "role", "cities",
                     "city_source", "level", "skills", "rule_fresher", "tagged_by", "first_seen"]
    out = [{k: p.get(k) for k in public_fields} for p in posts]
    rank = {"Internship": 0, "Fresher": 1, "Early career": 2, "Experienced": 3}
    out.sort(key=lambda p: (rank[p["level"]], p["first_seen"], p["company"]))
    SITE.mkdir(exist_ok=True)
    (SITE / "jobs.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    cost = cost_report()
    sources = sorted({p["source"] for p in posts})
    (SITE / "meta.json").write_text(json.dumps({
        "updated_at": now.isoformat(), "total_posts": len(posts), "entry_posts": len(entry),
        "intern_or_fresher_posts": len(strict),
        "sources": sources, "boards": sum(1 for v in report.values() if v.get("ok") and v.get("india")),
        "model": model_label,
        "usd_per_1000_posts": cost.get("usd_per_1000_posts"),
    }, indent=1))
    # Skills insights: every post ever published (open + closed), compact keys to keep the file small.
    archive = update_archive(posts, today, {p["id"] for p in raw})
    insights = {
        "archive_start": min(a["first_seen"] for a in archive),
        "categories": SKILL_CATEGORY,
        "posts": [{"co": a["company"], "t": a["title"], "u": a["url"], "r": a["role"], "c": a["cities"], "l": a["level"],
                   "s": a["skills"], "d": a["posted"], "open": a["last_seen"] == today} for a in archive],
    }
    (SITE / "insights.json").write_text(json.dumps(insights, ensure_ascii=False, separators=(",", ":")))
    # Same data as a script, so index.html also works when opened from disk (file:// blocks fetch).
    meta = json.loads((SITE / "meta.json").read_text())
    (SITE / "data.js").write_text("window.JOB_DATA = " + json.dumps({"jobs": out, "meta": meta, "insights": insights},
                                                                     ensure_ascii=False, separators=(",", ":")) + ";\n")
    (DATA / "posts.json").write_text(json.dumps(posts, ensure_ascii=False))
    (DATA / "state.json").write_text(json.dumps(state, indent=0, sort_keys=True))
    print(f"published {len(out)} posts: {len(entry)} entry-level, {len(strict)} intern/fresher")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="keyword tags only (no API key needed)")
    sys.exit(main(use_llm=not ap.parse_args().no_llm))
