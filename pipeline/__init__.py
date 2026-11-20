"""Load a local .env (if present) before any module reads the environment.

Real environment variables always win, so the GitHub Actions secret is used in CI and
the .env file is only a convenience for running locally. No extra dependency needed.
"""
import os
from pathlib import Path

_ENV = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = _ENV) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.removeprefix("export ").split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key and val and not os.environ.get(key):
            os.environ[key] = val


load_env()
