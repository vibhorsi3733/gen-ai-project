"""Tag the 50 sampled posts with each model (same prompt + schema) and the keyword baseline.
Writes eval/preds_<model>.json and logs real token usage to data/usage.jsonl.
Works with Claude or Gemini model names; each needs its provider's key.

    python -m eval.run_models claude-opus-5-5
    python -m eval.run_models gemini-3.8-flash
    python -m eval.run_models            # no args: the model the pipeline would use (tagger.MODEL)
"""
import json
import sys
import time
from pathlib import Path

from pipeline import llm, tagger
from pipeline.baseline import baseline_tag
from pipeline.taxonomy import cities_from_alias
from pipeline.skills import final_skills

ROOT = Path(__file__).resolve().parent.parent
sample = json.loads((ROOT / "eval/sample_posts.json").read_text())
# SmartRecruiters posts were sampled before their descriptions were fetched; use the same cached
# descriptions production uses, so the eval sees what the pipeline sees.
_desc = ROOT / "data/desc_cache.json"
_desc = json.loads(_desc.read_text()) if _desc.exists() else {}
for p in sample:
    if not p.get("description") and p["id"] in _desc:
        p["description"] = _desc[p["id"]]

base = {}
for p in sample:
    b = baseline_tag(p)
    base[p["id"]] = {"role": b["role"], "cities": b["cities"], "level": None}
(ROOT / "eval/preds_baseline.json").write_text(json.dumps(base, indent=1))

models = sys.argv[1:] or ([tagger.MODEL] if tagger.MODEL else [])
if not models:
    raise SystemExit("No LLM key found. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env (baseline written).")
for model in models:
    if not llm.has_key(llm.provider_of(model)):
        print(f"skip {model}: no {llm.provider_of(model)} key"); continue
    preds, t0 = {}, time.time()
    items = [(p["id"], p) for p in sample]
    for i in range(0, len(items), tagger.BATCH_SIZE):
        batch = items[i:i + tagger.BATCH_SIZE]
        try:
            res = tagger._call(batch, model=model)
        except Exception as e:  # noqa: BLE001
            if llm.is_fatal(e):
                raise SystemExit(f"{model}: {str(e)[:300]}")
            print(f"{model} batch {i} failed: {e}; per-post retry")
            res = {}
            for it in batch:
                res.update(tagger._call([it], model=model))
        for pid, r in res.items():
            alias = cities_from_alias(next(p for p in sample if p["id"] == pid)["location"])
            post = next(p for p in sample if p["id"] == pid)
            skills, _ = final_skills(r.get("skills", []), post["title"], post.get("description", ""), post["company"])
            preds[pid] = {"role": r["role"], "llm_cities": r["cities"], "cities": alias or r["cities"], "level": r["level"],
                          "skills": skills}
    (ROOT / f"eval/preds_{model}.json").write_text(json.dumps(preds, indent=1))
    print(f"{model}: {len(preds)}/{len(sample)} tagged in {time.time() - t0:.0f}s")
