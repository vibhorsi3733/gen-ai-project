"""Three-layer de-duplication.

1. Exact URL (canonicalised: lower-case host, tracking params/fragment/trailing slash removed).
2. Exact key: normalised company + normalised title + canonical city set.
3. Near-duplicate (cross-source only): same company, title similarity >= 92 (rapidfuzz token_sort_ratio; token_set_ratio was rejected because a subset title ("Software Engineer" vs "Senior Software Engineer") scores 100)
   and overlapping location -> same opening posted twice (e.g. "SDE Intern" vs
   "SDE Intern - 2026" on an aggregator vs the ATS original). Within one ATS board every req id is a
   distinct opening, so fuzzy matching there merged real jobs (e.g. "Senior SWE (Backend)" vs "(Data Platform)").
The first post seen wins; later ones are recorded in `dupes` so the write-up can show examples.
"""
import re
from urllib.parse import urlsplit

from rapidfuzz import fuzz

from .taxonomy import cities_in

NOISE = re.compile(r"\b(20\d\d|batch|hiring|urgent|opening|immediate joiner|req\s*\d+|job id[:\s]*\w+)\b")


TRACKING = re.compile(r"^(utm_\w+|ref|source|src|lever-\w+|gh_src|trk)$", re.I)


def canon_url(url: str) -> str:
    """Lower-case host, drop fragment and *tracking* params only.
    (Dropping the whole query string was a bug: Databricks job URLs differ only by ?gh_jid=.)"""
    s = urlsplit(url.strip())
    q = "&".join(sorted(kv for kv in s.query.split("&") if kv and not TRACKING.match(kv.split("=")[0])))
    return f"{s.netloc.lower()}{s.path.rstrip('/')}" + (f"?{q}" if q else "")


def norm_company(c: str) -> str:
    c = c.lower()
    c = re.sub(r"\b(pvt|private|ltd|limited|inc|llp|technologies|technology|india)\b\.?", " ", c)
    return re.sub(r"[^a-z0-9]+", "", c)


def norm_title(t: str) -> str:
    t = t.lower()
    # drop bracketed text only when it is a location, e.g. "(Bangalore)"; "(Backend)" is a different team
    t = re.sub(r"[\(\[]([^\)\]]*)[\)\]]", lambda m: " " if cities_in(m.group(1)) or "remote" in m.group(1) else f" {m.group(1)} ", t)
    t = NOISE.sub(" ", t)
    t = re.sub(r"[^a-z0-9+#]+", " ", t)
    return " ".join(t.split())


LEVEL = re.compile(r"\b(i{1,3}|iv|[0-9]+|senior|sr|staff|principal|lead|junior|jr|intern|trainee|associate|head|director|manager)\b")


def same_level(a: str, b: str) -> bool:
    """'Backend Engineer I' vs 'II' (97) or 'Sr. Solutions Architect' vs 'Solutions Architect'
    score high on similarity but are different openings."""
    return set(LEVEL.findall(a)) == set(LEVEL.findall(b))


def dedupe(posts: list[dict]) -> tuple[list[dict], list[dict]]:
    keep: list[dict] = []
    dupes: list[dict] = []
    seen_urls: set[str] = set()
    seen_keys: dict[str, dict] = {}
    by_company: dict[str, list[dict]] = {}

    for p in posts:
        u = canon_url(p["url"])
        comp = norm_company(p["company"])
        title = norm_title(p["title"])
        cities = frozenset(cities_in(p.get("location", ""))) or frozenset(["?"])
        key = f"{comp}|{title}|{','.join(sorted(cities))}"

        reason = None
        if u in seen_urls:
            reason, orig = "url", None
        elif key in seen_keys:
            reason, orig = "key", seen_keys[key]
        else:
            orig = None
            for q in by_company.get(comp, []):
                if q["source"] != p["source"] and (q["_cities"] & cities or "?" in q["_cities"] or "?" in cities) and \
                        same_level(title, q["_ntitle"]) and \
                        fuzz.token_sort_ratio(title, q["_ntitle"]) >= 92:
                    reason, orig = "fuzzy", q
                    break
        if reason:
            dupes.append({"reason": reason, "title": p["title"], "company": p["company"],
                          "source": p["source"], "dup_of": orig["title"] if orig else p["url"]})
            continue

        p["_ntitle"], p["_cities"] = title, cities
        keep.append(p)
        seen_urls.add(u)
        seen_keys[key] = p
        by_company.setdefault(comp, []).append(p)

    for p in keep:
        p.pop("_ntitle", None)
        p.pop("_cities", None)
    return keep, dupes
