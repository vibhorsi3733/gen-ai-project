"""LLM tagger: role, cities[], level and skills[] from reading the JD, with schema-enforced enums.

Cost levers:
  * content-hash cache (data/tags_cache.json, key includes model + prompt version)
    -> each daily run only tags NEW or CHANGED posts
  * batching (BATCH_SIZE posts per call) spreads the instruction tokens over the batch
  * JD excerpt: company/benefit boilerplate removed, then opening + level/skill sentences, capped at EXCERPT_CHARS
Every call's token usage is appended to data/usage.jsonl, so cost is measured, not estimated.
"""
import hashlib
import itertools
import json
import os
import re
import threading
import time
from pathlib import Path

from . import llm
from .baseline import baseline_tag
from .skills import ALL_SKILLS, extract_skills, final_skills, jd_sentences
from .taxonomy import CITIES, LEVELS, ROLES, cities_from_alias

PROMPT_VERSION = "v4"   # v4: LLM judges keyword candidates from the JD (v3 free extraction missed SQL/Python)
# Claude or Gemini, whichever key is present (see llm.resolve). None -> keyword tags only.
PROVIDER, MODEL, PROVIDER_NOTE = llm.resolve()
# Gemini free tier allows 20 requests/day per model: 50 posts per request keeps a full run (~750 posts)
# at ~15 requests and a normal day at 1-2. Claude has no such cap, so smaller batches are fine.
BATCH_SIZE = int(os.environ.get("TAG_BATCH_SIZE") or (50 if PROVIDER == "gemini" else 10))
EXCERPT_CHARS = 2400   # skills need the requirements section, not just the opening

# USD per 1M tokens (input, output), list prices Nov 2026. Thinking tokens bill as output on both.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "gemini-3.8-flash": (0.75, 3.75),   # introductory until 2026-12-31; $1.50 / $7.50 from 2027-01-01
    "gemini-3.6-flash": (0.75, 3.75),   # same introductory schedule
    "gemini-3.5-flash-lite": (0.30, 2.50),
}

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA / "tags_cache.json"
USAGE_PATH = DATA / "usage.jsonl"

SYSTEM = f"""You label job postings for an Indian student career platform. For each post return:

role: the job function, one of {ROLES}.
  Pick by what the person will do day to day, not by the company's industry.
  Data/Business/MIS analyst -> Data / Analytics / ML. QA, test, DevOps, SRE, security engineering -> Software Engineering.
  Solutions/sales engineers and pre-sales -> Sales / Business Development. Field sales, telesales, admission counsellor -> Sales / Business Development.
  Core Engineering means non-software engineering (mechanical, electrical, civil, manufacturing, VLSI/hardware).
  Use "Other" only if nothing fits.

cities: every work location named, using {CITIES}.
  Bangalore -> Bengaluru. Gurugram/Gurgaon/Noida/New Delhi -> Delhi NCR. Bombay/Navi Mumbai/Thane -> Mumbai.
  Remote / work from home -> include Remote. An Indian city not in the list -> Other India.
  Only "India" or no city given -> India (unspecified). Use only the location field and the text; never guess.

level, one of {LEVELS}:
  Internship  - an internship or apprenticeship.
  Fresher     - open to new graduates / 0-1 years (trainee, graduate, entry level, "freshers", "0-1 years").
  Early career - asks for up to 2 years, or junior/associate/"Engineer I" with no stated requirement.
  Experienced - asks for 3+ years, or is senior/lead/staff/manager level.

skills: what THIS JOB asks the candidate to know or will use, chosen only from {ALL_SKILLS}.
  Each post comes with "candidate_skills": skills a keyword scan found in its JD. For each candidate:
    KEEP it if the responsibilities or requirements ask for it (required or "nice to have").
    DROP it if the text is about the company, its products, customers or general tech stack (a recruiter at a
    cloud company does NOT need AWS), or if the word means something else ("networking" with people,
    "algorithm" in a mission statement, "presentation" of a product).
  ADD a skill from the list only if the JD clearly asks for it and the scan missed it.
  Include a professional skill (Communication, Negotiation, ...) only if the post asks for it.

Return exactly one item per input id, echoing the id."""

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "role": {"type": "string", "enum": ROLES},
        "cities": {"type": "array", "items": {"type": "string", "enum": CITIES}},
        "level": {"type": "string", "enum": LEVELS},
        "skills": {"type": "array", "items": {"type": "string", "enum": ALL_SKILLS}},
    },
    "required": ["id", "role", "cities", "level", "skills"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": ITEM_SCHEMA}},
    "required": ["items"],
    "additionalProperties": False,
}

SIGNAL = re.compile(r"(year|yrs|experience|fresher|graduat|degree|b\.?tech|b\.?e\b|mba|intern|stipend|trainee|"
                    r"batch|20\d\d|entry|junior|qualification|eligib|skill|knowledge|proficien|familiar|"
                    r"must|required|requirement|you will|responsib|tools?|experience with)", re.I)


def excerpt(desc: str, company: str = "") -> str:
    """The JD with company/benefit/legal boilerplate removed (jd_sentences), then: the first ~1,200
    characters plus sentences carrying level or skill signals, capped at EXCERPT_CHARS.
    (First version sent the raw first 400 characters: that is mostly "About <company>", which is how
    MongoDB recruiters ended up with AWS/Azure/GCP and why the experience line was often missed.)"""
    sents = jd_sentences(desc, company)
    out, rest = "", []
    for s in sents:
        if len(out) < 1200:
            out += (" " if out else "") + s
        else:
            rest.append(s)
    for s in rest:
        if SIGNAL.search(s) and len(s) < 400:
            if len(out) + len(s) + 3 > EXCERPT_CHARS:
                break
            out += " … " + s
    return out[:EXCERPT_CHARS]


def content_hash(post: dict) -> str:
    key = "|".join([post["title"].strip().lower(), post["company"].strip().lower(),
                    post.get("location", "").strip().lower(), excerpt(post.get("description", ""), post["company"]),
                    PROMPT_VERSION, MODEL or "none"])
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def _load_cache() -> dict:
    return json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}


def _save_cache(cache: dict) -> None:
    DATA.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=0, sort_keys=True))


def _render(batch: list[tuple[str, dict]]) -> str:
    lines = [json.dumps({"id": hid, "title": p["title"], "company": p["company"],
                         "location": p.get("location", ""), "type": p.get("commitment", ""),
                         "description": excerpt(p.get("description", ""), p["company"]),
                         "candidate_skills": extract_skills(p["title"], p.get("description", ""), p["company"])},
                        ensure_ascii=False)
             for hid, p in batch]
    return "Label these posts (one JSON object per line):\n" + "\n".join(lines)


def _call(batch: list[tuple[str, dict]], model: str = None) -> dict[str, dict]:
    model = model or MODEL
    r = llm.generate_json(model, SYSTEM, _render(batch), OUTPUT_SCHEMA, max_tokens=4000 + 250 * len(batch))
    DATA.mkdir(exist_ok=True)
    with USAGE_PATH.open("a") as f:
        f.write(json.dumps({"ts": int(time.time()), "provider": r["provider"], "model": model, "posts": len(batch),
                            "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
                            "latency_s": r["latency_s"], "stop_reason": r["finish"]}) + "\n")
    if not r["ok"]:
        raise ValueError(f"finish={r['finish']}")
    items = {it["id"]: it for it in json.loads(r["text"])["items"]}
    want = {hid for hid, _ in batch}
    if set(items) != want:  # model dropped/duplicated/invented ids -> caller retries per post
        missing = want - set(items)
        if len(batch) > 1 and missing:
            raise ValueError(f"ids mismatch: missing {len(missing)}")
    for it in items.values():
        if not it["cities"]:
            it["cities"] = ["India (unspecified)"]
    return {k: v for k, v in items.items() if k in want}


def tag_posts(posts: list[dict], use_llm: bool = True, workers: int = 4) -> dict:
    """Mutates posts in place with tag fields. Returns run stats."""
    from concurrent.futures import ThreadPoolExecutor

    global MODEL
    cache = _load_cache()

    def pending():
        out = []
        for p in posts:
            p["_hash"] = content_hash(p)
            if p["_hash"] not in cache:
                out.append((p["_hash"], p))
        return out

    todo = pending()
    note, probe_error = PROVIDER_NOTE, None
    if use_llm and PROVIDER and todo:
        # Gemini: make sure the model answers before tagging; fall back if it is overloaded.
        try:
            chosen, why = llm.pick_available(MODEL)
        except Exception as e:  # noqa: BLE001 - bad key etc.: handled like any fatal error below
            chosen, why, probe_error = MODEL, "", e
        if chosen is None:
            probe_error = RuntimeError(why)
        elif chosen != MODEL:
            print(f"model switch: {why}")
            MODEL, note = chosen, f"{note}; {why}"
            todo = pending()  # cache is keyed by model
    stats = {"total": len(posts), "cache_hits": len(posts) - len(todo), "llm_tagged": 0, "fallback": 0,
             "batch_retries": 0}

    stats["llm_status"] = ("disabled (--no-llm)" if not use_llm else note if not PROVIDER
                           else "nothing new to tag" if not todo else f"ok: {MODEL} ({note})")
    stats["model"] = MODEL
    if probe_error is not None and (llm.is_fatal(probe_error) or isinstance(probe_error, RuntimeError)):
        stats["llm_status"] = f"unavailable: {str(probe_error)[:160]}"
        print(f"LLM unavailable ({str(probe_error)[:160]}); using keyword tags for this run")
        use_llm = False
    client = use_llm and bool(todo) and PROVIDER is not None
    unavailable = threading.Event()  # set on a bad key / no credit / unknown model -> stop calling

    def run_batch(batch):
        if unavailable.is_set():
            return {}, 0
        try:
            return _call(batch), 0
        except Exception as e:  # noqa: BLE001 - split and retry, then fall back
            if llm.is_fatal(e):
                if not unavailable.is_set():
                    unavailable.set()
                    stats["llm_status"] = f"unavailable: {str(e)[:160]}"
                    print(f"LLM unavailable ({str(e)[:160]}); using keyword tags for the rest of this run")
                return {}, 0
            # Retry as two halves (recursively), not one post at a time: with 50-post batches a
            # per-post retry would spend 50 requests, more than a free key's whole daily quota.
            print(f"batch of {len(batch)} failed ({str(e)[:120]}); retrying in halves")
            if len(batch) == 1:
                return {}, 1
            mid = len(batch) // 2
            (r1, _), (r2, _) = run_batch(batch[:mid]), run_batch(batch[mid:])
            return {**r1, **r2}, 1

    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    if client:
        # First batch alone: a bad key or empty balance fails here once, not hundreds of times.
        first = [(batches[0], run_batch(batches[0]))]
        rest = batches[1:] if not unavailable.is_set() else []
        with ThreadPoolExecutor(max_workers=min(workers, llm.WORKERS.get(PROVIDER, workers))) as pool:
            results = itertools.chain(first, zip(rest, pool.map(run_batch, rest)))  # lazy: checkpoints still fire
            for n, (batch, (res, retried)) in enumerate(results):
                stats["batch_retries"] += retried
                for hid, _ in batch:
                    if hid in res:
                        r = res[hid]
                        cache[hid] = {"role": r["role"], "llm_cities": r["cities"], "level": r["level"],
                                      "llm_skills": r.get("skills", []), "tagged_by": MODEL}
                        stats["llm_tagged"] += 1
                if n % 5 == 4:
                    _save_cache(cache)  # checkpoint
                    print(f"  tagged {stats['llm_tagged']}/{len(todo)}")
        _save_cache(cache)

    for p in posts:
        if p["_hash"] in cache:
            p.update(cache[p["_hash"]])
        else:  # keyword fallback; not cached, so the LLM retries it on the next run
            b = baseline_tag(p)
            p.update({"role": b["role"], "llm_cities": None, "level": None, "tagged_by": "rules"})
            stats["fallback"] += 1
        # skills: the LLM's reading of the JD, grounded: a technical skill the post never mentions is
        # dropped (no invented skills). Without LLM tags, keep the keyword skills run.py computed.
        p["skills"], p["skills_source"] = final_skills(p.get("llm_skills"), p["title"], p.get("description", ""),
                                                       p["company"])
        # deterministic alias map wins when the raw location names known cities
        alias = cities_from_alias(p.get("location", ""))
        p["cities"] = alias or p.get("llm_cities") or ["India (unspecified)"]
        p["city_source"] = "alias" if alias else ("llm" if p.get("llm_cities") else "default")
        p.pop("_hash", None)
    return stats


def cost_report(model: str | None = None) -> dict:
    """Actual cost from logged API usage (optionally for one model)."""
    if not USAGE_PATH.exists():
        return {}
    tot_in = tot_out = posts = 0
    cost = 0.0
    for line in USAGE_PATH.read_text().splitlines():
        r = json.loads(line)
        if model and r["model"] != model:
            continue
        pin, pout = PRICES.get(r["model"], (0, 0))
        cost += r["input_tokens"] / 1e6 * pin + r["output_tokens"] / 1e6 * pout
        tot_in += r["input_tokens"]
        tot_out += r["output_tokens"]
        posts += r["posts"]
    return {"posts_sent": posts, "input_tokens": tot_in, "output_tokens": tot_out, "total_usd": round(cost, 4),
            "usd_per_1000_posts": round(cost / posts * 1000, 4) if posts else None}
