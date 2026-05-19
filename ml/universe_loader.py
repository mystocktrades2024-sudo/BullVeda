"""Universe loader for ML Edge — aggregates S&P 500 + Russell 1000 + Russell 2000
into a single deduped list with membership flags.

Used by run_ml_edge.py when invoked with `--universe NAME` (independent of the
daily scan bundle). Lets the ML Edge workspace tab operate as an autonomous
universe-wide forecaster.

Sources (all via existing paid EODHD subscription — no new licenses):
  - S&P 500   → data_fetcher.get_sp500()        (EODHD index_components "GSPC")
  - R1000     → data_fetcher.get_russell1000()  (EODHD index_components "RUI")
  - R2000     → data_fetcher.get_russell2000()  (EODHD index_components "RUT")

Fallback chain when EODHD is rate-limited or returns an empty list:
  - Read cached `data/universe.json` (built by data_archive.py, refreshed weekly)
  - Read static fixtures in `data/universe_fixtures/` (last-known-good lists)

Output contract:
    load_universe(name) → list[dict]
        Each row: {ticker, name, sector, in_sp500, in_r1000, in_r2000}
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
UNIVERSE_JSON = ROOT / "data" / "universe.json"
FIXTURE_DIR = ROOT / "data" / "universe_fixtures"

# Ensure repo root is importable when this module is run as a script
# (`python3 ml/universe_loader.py`). When imported via `from ml.universe_loader`,
# this is already done by the caller's sys.path.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────
def load_universe(name: str = "all", with_metadata: bool = True) -> list[dict]:
    """Return the universe as a list of ticker dicts.

    Args:
        name: 'sp500' | 'r1000' | 'r2000' | 'all' | 'custom:<filename>' (default)
        with_metadata: when True, includes name + sector via _enrich_metadata.
                       Set False during bulk inference to skip the lookup.

    Returns:
        list of {ticker, name?, sector?, in_sp500, in_r1000, in_r2000}
        Deduplicated by ticker. Sorted alphabetically.
    """
    name = (name or "all").lower()
    # #22 · Custom universes — `custom:<filename>` reads data/universes/<filename>.yml
    if name.startswith("custom:"):
        custom_name = name.split(":", 1)[1]
        return _load_custom_universe(custom_name, with_metadata=with_metadata)
    if name not in {"sp500", "r1000", "r2000", "all"}:
        raise ValueError(f"Unknown universe: {name}. Use sp500|r1000|r2000|all|custom:<name>")

    sp500 = _load_sp500()
    r1000 = _load_r1000()
    r2000 = _load_r2000()

    # Pick the requested slice
    if name == "sp500":
        selected = set(sp500)
    elif name == "r1000":
        selected = set(r1000)
    elif name == "r2000":
        selected = set(r2000)
    else:  # 'all' → union
        selected = set(sp500) | set(r1000) | set(r2000)

    # Build deduped rows with membership flags
    rows = []
    for t in sorted(selected):
        row = {
            "ticker": t,
            "in_sp500": t in sp500,
            "in_r1000": t in r1000,
            "in_r2000": t in r2000,
        }
        rows.append(row)

    if with_metadata:
        _enrich_metadata(rows)

    return rows


def get_universe_stats() -> dict:
    """Return counts per slice + last refreshed timestamps. Used by UI banner."""
    sp500 = _load_sp500()
    r1000 = _load_r1000()
    r2000 = _load_r2000()
    union = set(sp500) | set(r1000) | set(r2000)
    cached_age = _cached_age_hours()
    return {
        "sp500": len(sp500),
        "r1000": len(r1000),
        "r2000": len(r2000),
        "union_total": len(union),
        "cache_age_hours": cached_age,
    }


# ─────────────────────────────────────────────────────────────────────────
#  Source loaders (EODHD primary, cached fallback, fixture fallback)
# ─────────────────────────────────────────────────────────────────────────
def _load_sp500() -> set[str]:
    """S&P 500 constituents · EODHD primary, cache+fixture fallback."""
    try:
        from data_fetcher import get_sp500
        tickers = get_sp500()
        if tickers and len(tickers) >= 400:
            return set(t.upper().strip() for t in tickers if t)
    except Exception as e:
        print(f"[universe_loader] get_sp500 failed: {e}")
    # Fallback: read sp500 slice from cached universe.json
    cached = _cached_universe_tickers()
    if cached:
        # universe.json doesn't tag membership — assume first ~503 are S&P 500
        # (data_archive.py appends R1000 after). Best-effort.
        return set(cached[:503])
    # Final fallback: fixture
    return _fixture_set("sp500.txt")


def _load_r1000() -> set[str]:
    """Russell 1000 (~1000 names, includes S&P 500)."""
    try:
        from data_fetcher import get_russell1000
        tickers = get_russell1000()
        if tickers and len(tickers) >= 800:
            return set(t.upper().strip() for t in tickers if t)
    except Exception as e:
        print(f"[universe_loader] get_russell1000 failed: {e}")
    # Fallback: cached universe.json (S&P 500 ∪ R1000) minus pure R1000 tag = full set
    cached = _cached_universe_tickers()
    if cached and len(cached) >= 800:
        return set(cached)
    return _fixture_set("r1000.txt")


def _load_r2000() -> set[str]:
    """Russell 2000 small-caps (~2000 names, disjoint from R1000)."""
    try:
        from data_fetcher import get_russell2000
        tickers = get_russell2000()
        if tickers and len(tickers) >= 1500:
            return set(t.upper().strip() for t in tickers if t)
    except Exception as e:
        print(f"[universe_loader] get_russell2000 failed: {e}")
    # Cached snapshot
    cache_path = ROOT / "data" / "r2000_cache.json"
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            tickers = data.get("tickers") or []
            if len(tickers) >= 1500:
                return set(t.upper().strip() for t in tickers if t)
        except Exception:
            pass
    return _fixture_set("r2000.txt")


# ─────────────────────────────────────────────────────────────────────────
#  Cache + fixture helpers
# ─────────────────────────────────────────────────────────────────────────
def _cached_universe_tickers() -> Optional[list[str]]:
    if not UNIVERSE_JSON.exists():
        return None
    try:
        data = json.loads(UNIVERSE_JSON.read_text())
        return [t.upper().strip() for t in (data.get("tickers") or []) if t]
    except Exception:
        return None


def _cached_age_hours() -> Optional[float]:
    if not UNIVERSE_JSON.exists():
        return None
    try:
        data = json.loads(UNIVERSE_JSON.read_text())
        updated = data.get("updated") or ""
        # Format observed: "2026-04-13 10:30"
        dt = datetime.strptime(updated[:16], "%Y-%m-%d %H:%M")
        delta = datetime.now() - dt
        return delta.total_seconds() / 3600.0
    except Exception:
        return None


def _fixture_set(filename: str) -> set[str]:
    """Last-known-good fixture. Empty set if missing (don't crash)."""
    fp = FIXTURE_DIR / filename
    if not fp.exists():
        return set()
    try:
        return {line.strip().upper() for line in fp.read_text().splitlines() if line.strip()}
    except Exception:
        return set()


# ─────────────────────────────────────────────────────────────────────────
#  #22 · Custom universes (YAML)
# ─────────────────────────────────────────────────────────────────────────
def _load_custom_universe(custom_name: str, with_metadata: bool = True) -> list[dict]:
    """Read data/universes/<custom_name>.yml or .json.

    Expected shape (yml or json):
        tickers: [AAPL, NVDA, ...]
    OR:
        tickers:
          - {ticker: AAPL, name: "Apple", sector: "Technology"}
    """
    custom_dir = ROOT / "data" / "universes"
    custom_dir.mkdir(parents=True, exist_ok=True)
    for ext in (".yml", ".yaml", ".json"):
        fp = custom_dir / f"{custom_name}{ext}"
        if not fp.exists():
            continue
        try:
            if ext == ".json":
                data = json.loads(fp.read_text())
            else:
                # Minimal YAML parser — handles the simple list format we need
                # without adding a PyYAML dependency for one feature
                data = _parse_simple_yaml(fp.read_text())
        except Exception as e:
            print(f"[universe_loader] custom load failed for {custom_name}: {e}")
            return []
        tickers = data.get("tickers") or []
        rows = []
        for t in tickers:
            if isinstance(t, str):
                rows.append({"ticker": t.upper().strip(), "in_sp500": False, "in_r1000": False, "in_r2000": False})
            elif isinstance(t, dict) and t.get("ticker"):
                row = {
                    "ticker": t["ticker"].upper().strip(),
                    "name":    t.get("name"),
                    "sector":  t.get("sector"),
                    "in_sp500": t.get("in_sp500", False),
                    "in_r1000": t.get("in_r1000", False),
                    "in_r2000": t.get("in_r2000", False),
                }
                rows.append(row)
        if with_metadata:
            _enrich_metadata(rows)
        return rows
    print(f"[universe_loader] no custom universe file {custom_name} (tried .yml/.yaml/.json)")
    return []


def _parse_simple_yaml(text: str) -> dict:
    """Bare-bones YAML for tickers lists. Handles:
       tickers:\n  - AAPL\n  - NVDA
       tickers: [AAPL, NVDA, MSFT]
    """
    out = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1; continue
        if line.startswith("tickers:"):
            rest = line[len("tickers:"):].strip()
            if rest.startswith("[") and rest.endswith("]"):
                # Inline list
                items = [x.strip().strip("'\"") for x in rest[1:-1].split(",") if x.strip()]
                out["tickers"] = items
            else:
                # Block list — read until non-indented line
                items = []
                i += 1
                while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t") or not lines[i].strip()):
                    ln = lines[i].strip()
                    if ln.startswith("- "):
                        items.append(ln[2:].strip().strip("'\""))
                    i += 1
                out["tickers"] = items
                continue
        i += 1
    return out


# ─────────────────────────────────────────────────────────────────────────
#  Metadata enrichment — name + sector
# ─────────────────────────────────────────────────────────────────────────
def _enrich_metadata(rows: list[dict]) -> None:
    """Best-effort: tag name + sector from cached last_bundle / tickers.json.

    Mutates rows in place. Silent on missing data (sector stays None) — the
    UI handles missing-sector tickers by bucketing as "Other".
    """
    if not rows:
        return

    # Source 1: cached last_bundle.json (has name, sector from Finviz enrichment)
    bundle_path = ROOT / "cache" / "last_bundle.json"
    name_map: dict[str, dict] = {}
    if bundle_path.exists():
        try:
            bundle = json.loads(bundle_path.read_text())
            for key in ("all_scored", "buy_candidates", "elite_picks"):
                for r in bundle.get(key) or []:
                    if not isinstance(r, dict):
                        continue
                    sym = (r.get("ticker") or r.get("symbol") or "").upper().strip()
                    if sym and sym not in name_map:
                        name_map[sym] = {
                            "name": r.get("name") or r.get("company") or r.get("security_name"),
                            "sector": r.get("sector") or r.get("gicsSector"),
                        }
        except Exception:
            pass

    # Source 2: tickers.json (per-ticker enrichment cache)
    tickers_path = ROOT / "cache" / "tickers.json"
    if tickers_path.exists():
        try:
            tk = json.loads(tickers_path.read_text())
            if isinstance(tk, dict):
                for sym, rec in tk.items():
                    if not isinstance(rec, dict):
                        continue
                    sym_u = sym.upper().strip()
                    if sym_u not in name_map:
                        name_map[sym_u] = {
                            "name": rec.get("name") or rec.get("company"),
                            "sector": rec.get("sector"),
                        }
                    else:
                        # Fill any missing fields
                        if not name_map[sym_u].get("sector"):
                            name_map[sym_u]["sector"] = rec.get("sector")
                        if not name_map[sym_u].get("name"):
                            name_map[sym_u]["name"] = rec.get("name") or rec.get("company")
        except Exception:
            pass

    # Apply
    for row in rows:
        meta = name_map.get(row["ticker"]) or {}
        if meta.get("name"):
            row["name"] = meta["name"]
        if meta.get("sector"):
            row["sector"] = meta["sector"]


# ─────────────────────────────────────────────────────────────────────────
#  CLI for inspection
# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "all"
    rows = load_universe(name)
    stats = get_universe_stats()
    print(f"Loaded universe '{name}' · {len(rows)} tickers")
    print(f"  S&P 500: {stats['sp500']}")
    print(f"  R1000:   {stats['r1000']}")
    print(f"  R2000:   {stats['r2000']}")
    print(f"  Union:   {stats['union_total']}")
    print(f"  Cache age: {stats['cache_age_hours']}h" if stats['cache_age_hours'] else "  Cache age: n/a")
    print()
    print("First 5 rows:")
    for r in rows[:5]:
        print(f"  {r}")
