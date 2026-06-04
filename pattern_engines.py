"""pattern_engines.py — registry + dispatcher for the BullVeda Patterns lens.

Auto-discovers every module in ``engines/`` that exposes ``NAME`` and
``detect(df, meta, ticker)``. Each detector receives REAL, mode-resampled bars
from pattern_data.get_bars (SWING=daily, POSITION=weekly, INVEST=monthly) and
returns a JSON-serializable payload for its React view. One fetch per
(ticker, mode) is shared across a request.

Single dispatch point so the server has one endpoint and the boot adapter one
fetch function — adding a theory is just dropping a file in engines/.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Callable, Dict, List

from pattern_data import get_bars, mode_meta, norm_mode

_REGISTRY: Dict[str, Callable] = {}
_LABELS: Dict[str, str] = {}
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    try:
        import engines
        for m in pkgutil.iter_modules(engines.__path__):
            try:
                mod = importlib.import_module("engines." + m.name)
            except Exception as e:  # pragma: no cover - one bad engine shouldn't kill the rest
                print(f"[pattern_engines] skip {m.name}: {e}")
                continue
            name = getattr(mod, "NAME", m.name)
            if hasattr(mod, "detect"):
                _REGISTRY[name] = mod.detect
                _LABELS[name] = getattr(mod, "LABEL", name.title())
    except Exception as e:  # pragma: no cover
        print(f"[pattern_engines] discovery failed: {e}")
    _loaded = True


def available() -> List[str]:
    _load()
    return sorted(_REGISTRY)


def labels() -> Dict[str, str]:
    _load()
    return dict(_LABELS)


def detect(engine: str, ticker: str, mode: str = "SWING") -> Dict[str, Any]:
    """Dispatch a single (engine, ticker, mode) request. Never raises."""
    _load()
    engine = (engine or "").lower().strip()
    ticker = (ticker or "").upper().strip()
    mode = norm_mode(mode)
    meta = mode_meta(mode)
    if engine not in _REGISTRY:
        return {"ticker": ticker, "engine": engine, "ok": False, "source": "real",
                "message": f"Unknown engine '{engine}'. Available: {', '.join(available())}",
                "meta": meta}
    if not ticker:
        return {"ticker": ticker, "engine": engine, "ok": False, "source": "real",
                "message": "No ticker.", "meta": meta}

    df, tier, meta = get_bars(ticker, mode)
    if df is None:
        return {"ticker": ticker, "engine": engine, "ok": False, "source": "real",
                "message": f"No {meta['tf'].lower()} OHLCV available ({tier}).",
                "tier": tier, "meta": meta}
    try:
        out = _REGISTRY[engine](df, meta, ticker) or {}
    except Exception as e:
        return {"ticker": ticker, "engine": engine, "ok": False, "source": "real",
                "message": f"{engine} engine error: {e}", "tier": tier, "meta": meta}
    if not isinstance(out, dict):
        out = {"ok": False, "message": "engine returned non-dict"}
    out.setdefault("ticker", ticker)
    out["engine"] = engine
    out["tier"] = tier
    out["meta"] = meta
    out.setdefault("source", "real")
    return out


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    eng = sys.argv[1] if len(sys.argv) > 1 else "wyckoff"
    sym = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
    md = sys.argv[3] if len(sys.argv) > 3 else "SWING"
    print("available:", available())
    out = detect(eng, sym, md)
    print(json.dumps({k: v for k, v in out.items() if k != "bars"}, indent=2, default=str)[:2000])
