"""One interface over two LLM providers: Anthropic (Claude) and Google (Gemini).

Either key is optional. Which one is used, decided once per run:
  1. TAG_MODEL, if set and its provider has a key (claude-* -> Anthropic, gemini-* -> Gemini)
  2. LLM_PROVIDER=anthropic|gemini, if set and that provider has a key
  3. otherwise whichever key exists, Anthropic first
  4. no key -> None, and the pipeline uses keyword tags
Both providers get the same system prompt and the same JSON schema, so tags are comparable.
"""
import os
import time

DEFAULTS = {"anthropic": "claude-opus-5-5", "gemini": "gemini-3.6-flash"}
# Tried in order when the chosen Gemini model is overloaded (503/504). On 2026-11-20 gemini-3.8-flash
# and 3.7-flash returned 504/503 for minutes, 3.6-flash flickered, and the lite models answered in 2-4 s. (3.5-flash is deprecated
# and routed to 3.6-flash, so it is not a real fallback.)
WORKERS = {"anthropic": 4, "gemini": 2}   # Gemini free tier has a low requests-per-minute limit
GEMINI_FALLBACKS = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]   # lite: last resort, answered in ~2 s
KEY_VARS = {"anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
EFFORT = os.environ.get("TAG_EFFORT") or "low"   # Claude: output_config.effort; Gemini: thinking_level


def provider_of(model: str) -> str:
    return "gemini" if model.lower().startswith("gemini") else "anthropic"


def has_key(provider: str) -> bool:
    return any(os.environ.get(v) for v in KEY_VARS[provider])


def resolve() -> tuple[str | None, str | None, str]:
    """(provider, model, note) for this run."""
    tm = (os.environ.get("TAG_MODEL") or "").strip()
    forced = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if tm and has_key(provider_of(tm)) and forced in ("", "auto", provider_of(tm)):
        return provider_of(tm), tm, f"TAG_MODEL={tm}"
    order = [forced] if forced in DEFAULTS else ["anthropic", "gemini"]
    for p in order:
        if has_key(p):
            note = f"{p} key found"
            if tm:
                note += f" (TAG_MODEL={tm} ignored: no {provider_of(tm)} key)"
            return p, DEFAULTS[p], note
    if forced in DEFAULTS:
        return None, None, f"LLM_PROVIDER={forced} but no {forced} key"
    return None, None, "no API key (set ANTHROPIC_API_KEY or GEMINI_API_KEY)"


_clients: dict = {}


def _client(provider: str):
    if provider not in _clients:
        if provider == "anthropic":
            import anthropic
            _clients[provider] = anthropic.Anthropic(max_retries=4)
        else:
            from google import genai
            from google.genai import types
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            # 90 s per request and 3 attempts: an overloaded model answers 504 after ~60 s, and the
            # first version (5 attempts, no timeout) stalled a run for minutes per batch.
            _clients[provider] = genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=90_000,
                retry_options=types.HttpRetryOptions(attempts=4, initial_delay=5.0, max_delay=60.0,  # free tier: per-minute limits
                                                     http_status_codes=[408, 429, 500, 502, 503])))
    return _clients[provider]


def pick_available(model: str) -> tuple[str | None, str]:
    """For Gemini: probe the chosen model with a tiny request and fall back along GEMINI_FALLBACKS
    if it is overloaded, so the whole run uses one model that actually answers. Claude: unchanged.
    Returns (model or None, note). Auth/quota errors are raised so the caller treats them as fatal."""
    if provider_of(model) != "gemini":
        return model, ""
    from google import genai
    from google.genai import errors, types
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    probe = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30_000))
    tried = []
    for m in [model] + [f for f in GEMINI_FALLBACKS if f != model]:
        try:
            probe.models.generate_content(model=m, contents="Reply with OK",
                                          config=types.GenerateContentConfig(max_output_tokens=50))
            return m, (f"{', '.join(tried)} unavailable -> using {m}" if tried else "")
        except errors.ServerError as e:      # 5xx: overloaded / deadline -> try the next model
            tried.append(f"{m} ({e.code})")
        except Exception as e:  # noqa: BLE001 - timeouts surface as httpx errors
            if isinstance(e, errors.ClientError):
                raise
            tried.append(f"{m} ({type(e).__name__})")
    return None, f"all Gemini models busy: {', '.join(tried)}"


def generate_json(model: str, system: str, user: str, schema: dict, max_tokens: int = 8000) -> dict:
    """Returns {text, input_tokens, output_tokens, finish, ok}. Output tokens include thinking tokens,
    because both providers bill thinking as output."""
    provider = provider_of(model)
    t0 = time.time()
    if provider == "anthropic":
        resp = _client(provider).messages.create(
            model=model, max_tokens=max_tokens, system=system,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        out = dict(text=text, input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                   finish=resp.stop_reason, ok=resp.stop_reason == "end_turn")
    else:
        from google.genai import types
        resp = _client(provider).models.generate_content(
            model=model, contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
                thinking_config=types.ThinkingConfig(thinking_level=EFFORT.upper()),
                max_output_tokens=max_tokens,
            ),
        )
        u = resp.usage_metadata
        cand = resp.candidates[0] if resp.candidates else None
        finish = cand.finish_reason.name if cand and cand.finish_reason else "NO_CANDIDATE"
        out = dict(text=resp.text or "", input_tokens=u.prompt_token_count or 0,
                   output_tokens=(u.candidates_token_count or 0) + (u.thoughts_token_count or 0),
                   finish=finish, ok=finish == "STOP")
    out["latency_s"] = round(time.time() - t0, 2)
    out["provider"] = provider
    return out


def is_fatal(e: Exception) -> bool:
    """Errors that will fail every call the same way (bad key, no credit, unknown model, daily quota),
    so the run should stop calling the LLM and use keyword tags instead of retrying hundreds of times."""
    msg = str(e).lower()
    try:
        import anthropic
        if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)):
            return True
        if isinstance(e, anthropic.BadRequestError) and "credit" in msg:
            return True
    except ImportError:
        pass
    try:
        from google.genai import errors
        if isinstance(e, errors.ClientError):
            if e.code in (401, 403, 404):
                return True
            if e.code == 400:   # bad key (Gemini answers 400, not 401) or a rejected schema: same for every call
                return True
            # Only a DAILY quota is fatal. Per-minute 429s carry the same "check your plan and billing"
            # text, so matching on "billing" stopped whole runs for a limit that clears in seconds.
            if e.code == 429 and ("perday" in msg.replace(" ", "").replace("_", "") or "daily" in msg):
                return True
    except ImportError:
        pass
    return False
