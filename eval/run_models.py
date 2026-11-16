"""Tag the 50 sampled posts with each model (same prompt + schema) and the keyword baseline.
Writes eval/preds_<model>.json and logs real token usage to data/usage.jsonl.

    python -m eval.run_models claude-haiku-5-5 claude-opus-5-5
"""
import json
import sys
import time
from pathlib import Path

import anthropic

from pipeline import tagger
from pipeline.baseline import baseline_tag
from pipeline.taxonomy import cities_from_alias

ROOT = Path(__file__).resolve().parent.parent
sample = json.loads((ROOT / "eval/sample_posts.json").read_text())

base = {}
for p in sample:
    b = baseline_tag(p)
    base[p["id"]] = {"role": b["role"], "cities": b["cities"], "level": None}
(ROOT / "eval/preds_baseline.json").write_text(json.dumps(base, indent=1))

client = anthropic.Anthropic(max_retries=4)
for model in sys.argv[1:]:
    preds, t0 = {}, time.time()
    items = [(p["id"], p) for p in sample]
    for i in range(0, len(items), tagger.BATCH_SIZE):
        batch = items[i:i + tagger.BATCH_SIZE]
        try:
            res = tagger._call(client, batch, model=model)
        except Exception as e:  # noqa: BLE001
            print(f"{model} batch {i} failed: {e}; per-post retry")
            res = {}
            for it in batch:
                res.update(tagger._call(client, [it], model=model))
        for pid, r in res.items():
            alias = cities_from_alias(next(p for p in sample if p["id"] == pid)["location"])
            preds[pid] = {"role": r["role"], "llm_cities": r["cities"], "cities": alias or r["cities"], "level": r["level"]}
    (ROOT / f"eval/preds_{model}.json").write_text(json.dumps(preds, indent=1))
    print(f"{model}: {len(preds)}/{len(sample)} tagged in {time.time() - t0:.0f}s")
