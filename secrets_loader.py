"""Centralized secrets loader — single import point for API keys.

Priority:
  1. OS environment variable
  2. .env file (loaded once at import time)
  3. config/config.json fallback (backward compat during transition)

Usage:
    from secrets_loader import get_secret
    key = get_secret("POLYGON_API_KEY")

Or explicit with fallback:
    key = get_secret("POLYGON_API_KEY", fallback_path="data_sources.polygon_api_key")
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_ROOT = Path(__file__).parent
_ENV_LOADED = False
_CONFIG_CACHE: dict | None = None


def _load_env_file() -> None:
    """Parse .env into os.environ (idempotent)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # Only set if not already in environment (env wins over .env)
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


def _load_config_cache() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        try:
            _CONFIG_CACHE = json.loads((_ROOT / "config" / "config.json").read_text())
        except Exception:
            _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def get_secret(env_name: str, fallback_path: str | None = None, default: str = "") -> str:
    """Fetch a secret with ENV > .env > config.json fallback chain.

    env_name: environment variable name (e.g. 'POLYGON_API_KEY')
    fallback_path: dot-path in config.json (e.g. 'data_sources.polygon_api_key')
    default: returned if nothing found
    """
    _load_env_file()
    val = os.environ.get(env_name, "").strip()
    if val:
        return val
    if fallback_path:
        cfg = _load_config_cache()
        node = cfg
        for part in fallback_path.split("."):
            if isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
                break
        if isinstance(node, str) and node:
            return node
    return default


# Convenience named getters — call at module scope in data_fetcher etc.
def polygon_key() -> str:
    return get_secret("POLYGON_API_KEY", "data_sources.polygon_api_key")

def finviz_token() -> str:
    return get_secret("FINVIZ_TOKEN", "data_sources.finviz_token")

def alpaca_key() -> str:
    return get_secret("ALPACA_API_KEY", "alpaca.api_key")

def alpaca_secret() -> str:
    return get_secret("ALPACA_SECRET_KEY", "alpaca.secret_key")

def massive_access_key_id() -> str:
    return get_secret("MASSIVE_ACCESS_KEY_ID", "data_sources.massive_access_key_id")

def massive_secret_key() -> str:
    return get_secret("MASSIVE_SECRET_KEY", "data_sources.massive_secret_key")


if __name__ == "__main__":
    # Sanity check
    _load_env_file()
    for name in ("POLYGON_API_KEY", "FINVIZ_TOKEN",
                 "SCHWAB_APP_KEY", "SCHWAB_APP_SECRET",
                 "ALPACA_API_KEY", "ALPACA_SECRET_KEY",
                 "MASSIVE_ACCESS_KEY_ID", "MASSIVE_SECRET_KEY"):
        val = get_secret(name, default="")
        status = "✓" if val else "✗"
        show = f"{val[:6]}...({len(val)} chars)" if val else "NOT SET"
        print(f"  {status} {name}: {show}")
