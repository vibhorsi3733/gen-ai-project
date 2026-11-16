"""Fetchers for public job sources. Each returns a list of normalised post dicts:
{id, source, company, title, location, description, url, posted_at, commitment}

Only official, documented public endpoints are used:
  * Greenhouse Job Board API  - boards-api.greenhouse.io (public, no auth, made for career sites)
  * Lever Postings API        - api.lever.co/v0/postings (public, no auth)
  * SmartRecruiters Posting API - api.smartrecruiters.com/v1/companies/{id}/postings (public)
  * Workable widget API       - apply.workable.com/api/v1/widget/accounts/{slug} (public)
  * Ashby Job Board API       - api.ashbyhq.com/posting-api/job-board/{org} (public)
  * Adzuna India API          - api.adzuna.com/v1/api/jobs/in (official API, free key; optional)
Sites whose robots.txt / ToS forbid automated access (LinkedIn, Naukri, Internshala, Indeed)
are deliberately NOT used.
"""
import html
import json
import os
import re
import time
from pathlib import Path

import requests

UA = "FresherJobsIndia/1.0 (open-source job aggregator; daily, low volume)"
S = requests.Session()
S.headers["User-Agent"] = UA
TIMEOUT = 30

COMPANIES = json.loads((Path(__file__).parent / "companies.json").read_text())

INDIA_WORDS = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|bombay|delhi|gurugram|gurgaon|noida|hyderabad|pune|chennai|kolkata|"
    r"ahmedabad|jaipur|kochi|cochin|coimbatore|indore|chandigarh|thiruvananthapuram|trivandrum|mysore|mysuru|"
    r"nagpur|lucknow|bhubaneswar|vadodara|surat|visakhapatnam|goa|mohali|thane|navi mumbai|secunderabad)\b", re.I)


def strip_html(s: str) -> str:
    s = html.unescape(html.unescape(s or ""))  # Greenhouse double-encodes
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(html.unescape(s).split())


def get(url: str, **kw):
    for attempt in range(3):
        try:
            r = S.get(url, timeout=TIMEOUT, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt * 2)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"gave up on {url}")


def is_india(location: str) -> bool:
    return bool(INDIA_WORDS.search(location or ""))


def greenhouse(slug: str, name: str) -> list[dict]:
    data = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = ", ".join(o.get("name", "") for o in j.get("offices", []) if o.get("name"))
        if not is_india(loc) and is_india(offices):
            loc = offices
        out.append(dict(id=f"gh:{slug}:{j['id']}", source="Greenhouse", company=name, title=j["title"],
                        location=loc, description=strip_html(j.get("content", "")),
                        url=j["absolute_url"], posted_at=j.get("updated_at", "")[:10], commitment=""))
    return out


def lever(slug: str, name: str) -> list[dict]:
    data = get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    out = []
    for j in data:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or [cat.get("location", "")]
        out.append(dict(id=f"lv:{slug}:{j['id']}", source="Lever", company=name, title=j["text"],
                        location=", ".join(x for x in locs if x), description=j.get("descriptionPlain", "")[:3000],
                        url=j["hostedUrl"], posted_at=time.strftime("%Y-%m-%d", time.gmtime(j.get("createdAt", 0) / 1000)),
                        commitment=cat.get("commitment", "")))
    return out


def smartrecruiters(slug: str, name: str) -> list[dict]:
    out, offset = [], 0
    while True:
        data = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                   params={"country": "in", "limit": 100, "offset": offset})
        for j in data.get("content", []):
            l = j.get("location") or {}
            loc = ", ".join(x for x in [l.get("city"), l.get("region"), "India"] if x)
            if l.get("remote"):
                loc = "Remote, India"
            out.append(dict(id=f"sr:{slug}:{j['id']}", source="SmartRecruiters", company=name, title=j["name"],
                            location=loc, description="",  # detail endpoint costs 1 req/post; title is enough
                            url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                            posted_at=(j.get("releasedDate") or "")[:10],
                            commitment=((j.get("typeOfEmployment") or {}).get("label") or "")
                            + " " + ((j.get("experienceLevel") or {}).get("label") or "")))
        offset += 100
        if offset >= data.get("totalFound", 0) or offset >= 500:
            return out


def workable(slug: str, name: str) -> list[dict]:
    data = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    out = []
    for j in data.get("jobs", []):
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
        if j.get("telecommuting"):
            loc = (loc + ", Remote").strip(", ")
        out.append(dict(id=f"wk:{slug}:{j.get('shortcode')}", source="Workable", company=name, title=j["title"],
                        location=loc, description=strip_html(j.get("description", ""))[:3000],
                        url=j.get("url") or j.get("shortlink"), posted_at=(j.get("published_on") or "")[:10],
                        commitment=j.get("employment_type") or ""))
    return out


def ashby(slug: str, name: str) -> list[dict]:
    data = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    out = []
    for j in data.get("jobs", []):
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", []) or []]
        out.append(dict(id=f"ab:{slug}:{j['id']}", source="Ashby", company=name, title=j["title"],
                        location=", ".join(x for x in locs if x), description=(j.get("descriptionPlain") or "")[:3000],
                        url=j["jobUrl"], posted_at=(j.get("publishedAt") or "")[:10],
                        commitment=j.get("employmentType") or ""))
    return out


def adzuna() -> list[dict]:
    """Official Adzuna API. Optional: only runs when ADZUNA_APP_ID/ADZUNA_APP_KEY are set."""
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    out = []
    for what in ["fresher", "intern", "internship", "graduate trainee", "entry level", "junior"]:
        for page in range(1, 4):
            data = get(f"https://api.adzuna.com/v1/api/jobs/in/search/{page}",
                       params={"app_id": app_id, "app_key": app_key, "what": what,
                               "results_per_page": 50, "max_days_old": 30, "content-type": "application/json"})
            for j in data.get("results", []):
                out.append(dict(id=f"az:{j['id']}", source="Adzuna", company=(j.get("company") or {}).get("display_name", "Unknown"),
                                title=strip_html(j["title"]), location=(j.get("location") or {}).get("display_name", ""),
                                description=strip_html(j.get("description", "")), url=j["redirect_url"],
                                posted_at=(j.get("created") or "")[:10], commitment=j.get("contract_time") or ""))
            time.sleep(2.5)  # stay well under Adzuna's rate limit
            if len(data.get("results", [])) < 50:
                break
    return out


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "smartrecruiters": smartrecruiters,
            "workable": workable, "ashby": ashby}


def fetch_all() -> tuple[list[dict], dict]:
    posts, report = [], {}
    for c in COMPANIES:
        key = f"{c['ats']}:{c['slug']}"
        try:
            got = FETCHERS[c["ats"]](c["slug"], c["name"])
            india = [p for p in got if is_india(p["location"])]
            posts += india
            report[key] = {"ok": True, "total": len(got), "india": len(india)}
        except Exception as e:  # noqa: BLE001 - one dead board must not kill the run
            report[key] = {"ok": False, "error": str(e)[:200]}
        time.sleep(0.5)
    try:
        az = [p for p in adzuna() if is_india(p["location"]) or p["location"]]
        posts += az
        report["adzuna"] = {"ok": True, "total": len(az), "india": len(az), "enabled": bool(os.environ.get("ADZUNA_APP_ID"))}
    except Exception as e:  # noqa: BLE001
        report["adzuna"] = {"ok": False, "error": str(e)[:200]}
    return posts, report
