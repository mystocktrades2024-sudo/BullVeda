"""
check_schema_drift.py — detects JSON ↔ Postgres schema divergence.

Problem (per elite_research_note 2026-05-09): when a developer adds a field
to portfolio_state.json without also adding the column to the Postgres
schema, the dual-write to Supabase silently fails (caught by sync.py's
try/except). Eventually the two stores diverge and Mode 2 cutover breaks.

Solution: lint at CI time. Compare:
  - Sample row keys from data/portfolio_state.json (and other canonical JSON)
  - Postgres column lists from migrations/*.sql + db.py CREATE TABLEs
  - Report any JSON-only keys (will fail Supabase upsert)
  - Report any Postgres-only columns (informational; might be intentional)

Usage:
    python3 check_schema_drift.py            # report only
    python3 check_schema_drift.py --strict   # exit 1 on any drift (CI mode)

Exit codes:
    0 — no drift, or drift in informational categories only
    1 — JSON has fields Postgres doesn't (will silently fail upsert)
    2 — error reading sources
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
MIGRATIONS_DIR = ROOT / "migrations"
DB_PY = ROOT / "db.py"
DATA_DIR = ROOT / "data"

# Canonical JSON files → which Postgres table they correspond to
JSON_TO_TABLE: list[tuple[Path, str, str]] = [
    # (json_path, postgres_table, sample_extractor_path_in_json)
    # extractor: dot-path into the JSON to get a sample row dict;
    # 'list[0]' = first element of top-level list
    (DATA_DIR / "portfolio_state.json", "portfolio_state", "."),  # singleton
    (DATA_DIR / "portfolio_state.json", "positions", "positions[0]"),
    (DATA_DIR / "portfolio_state.json", "closed_trades", "closed_trades[0]"),
    (DATA_DIR / "signal_log.json", "signal_log", "list[0]"),
    (DATA_DIR / "scan_health.json", "scan_health", "history[0]"),
    (DATA_DIR / "gap_events.json", "gap_events", "list[0]"),
    (DATA_DIR / "alert_sent_log.json", "alert_log", "._key_value_pairs"),
    (DATA_DIR / "custom_tracked.json", "custom_tickers", "tickers[0]"),
    (DATA_DIR / "paper_trading_start.json", "paper_trading_config", "."),
]

# Fields that are intentionally JSON-only (UI metadata, internal flags)
KNOWN_JSON_ONLY = {
    # global
    "_schema_version", "_last_saved", "_last_alpaca_sync", "_reset_note",
    "schema_version", "starting_equity",
    # portfolio_state.json top-level lists/dicts that map to OTHER tables
    "positions", "closed_trades", "equity_curve", "equity_audit", "monthly_pnl",
    "buying_power", "alpaca_account", "last_alpaca_sync", "last_reset",
    # gap_events.json
    "source",
    # paper_trading
    "max_daily_trades",
    # signal entries
    "_meta",
    # 2026-05-17 · computed/derived attributes on signal closes
    # (kept in JSON for tracker analytics; not first-class Postgres columns)
    "alpha_vs_spy", "exit_reason", "is_new_buy", "spy_return_over_hold",
}


def get_postgres_columns(table: str) -> set[str]:
    """Extract column names for a table from db.py + migrations/*.sql."""
    sources = []
    if DB_PY.exists():
        sources.append(DB_PY.read_text())
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sources.append(sql_file.read_text())

    cols: set[str] = set()
    for src in sources:
        # Match CREATE TABLE [IF NOT EXISTS] tablename ( ... )
        pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + re.escape(table) +
            r"\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL
        )
        for body in pattern.findall(src):
            for line in body.splitlines():
                line = line.strip().rstrip(",")
                # Skip constraints / indexes
                if not line or line.upper().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN",
                                                          "UNIQUE", "CHECK", "INDEX", "KEY",
                                                          "--", "/*")):
                    continue
                # First word is the column name
                m = re.match(r"^[\"`']?(\w+)[\"`']?\s+", line)
                if m:
                    cols.add(m.group(1).lower())
    # Always strip the synthetic id col from the comparison if present
    return cols


def get_sample_row(json_path: Path, extractor: str) -> dict | None:
    """Extract a sample row dict from a JSON file using a dot-path extractor."""
    if not json_path.exists():
        return None
    try:
        d = json.loads(json_path.read_text())
    except Exception:
        return None

    if extractor == ".":
        return d if isinstance(d, dict) else None
    if extractor == "list[0]":
        if isinstance(d, list) and d:
            return d[0] if isinstance(d[0], dict) else None
        return None
    if extractor == "._key_value_pairs":
        # alert_sent_log: {alert_key: date_str} — synthesize a row
        if isinstance(d, dict) and d:
            k, v = next(iter(d.items()))
            return {"alert_key": k, "last_sent_date": v}
        return None
    if extractor.endswith("[0]"):
        key = extractor[:-3]
        if isinstance(d, dict) and isinstance(d.get(key), list) and d[key]:
            first = d[key][0]
            if isinstance(first, dict):
                return first
            elif isinstance(first, str):
                # custom_tracked.json: tickers can be strings
                return {"ticker": first}
        return None
    return None


def diff_keys(json_keys: set[str], pg_cols: set[str], table: str) -> dict:
    """Return {json_only, pg_only, common}."""
    json_keys_lower = {k.lower() for k in json_keys}
    json_only = json_keys_lower - pg_cols - {k.lower() for k in KNOWN_JSON_ONLY}
    pg_only = pg_cols - json_keys_lower - {"id", "raw_json"}  # id is autogen, raw_json is fallback
    common = json_keys_lower & pg_cols
    return {"json_only": sorted(json_only), "pg_only": sorted(pg_only),
            "common_count": len(common), "table": table}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any json-only fields (CI mode)")
    args = parser.parse_args()

    print("=" * 70)
    print("Schema drift check — JSON canonical vs Postgres")
    print("=" * 70)

    any_critical = False
    n_tables = 0
    for json_path, table, extractor in JSON_TO_TABLE:
        sample = get_sample_row(json_path, extractor)
        if sample is None:
            print(f"\n  {table:25s}  (no sample available — JSON empty or missing)")
            continue
        n_tables += 1

        pg_cols = get_postgres_columns(table)
        if not pg_cols:
            print(f"\n  {table:25s}  ✗ Postgres table not found in db.py or migrations")
            any_critical = True
            continue

        json_keys = set(sample.keys()) if isinstance(sample, dict) else set()
        diff = diff_keys(json_keys, pg_cols, table)

        if diff["json_only"]:
            print(f"\n  {table:25s}  ✗ JSON fields with no Postgres column:")
            for k in diff["json_only"]:
                print(f"     - {k}")
            any_critical = True
        elif diff["pg_only"]:
            print(f"\n  {table:25s}  ⚠ Postgres columns not in JSON sample:")
            for k in diff["pg_only"]:
                print(f"     - {k}  (informational; may be intentional)")
        else:
            print(f"\n  {table:25s}  ✓ aligned ({diff['common_count']} common cols)")

    print()
    print("=" * 70)
    print(f"Checked {n_tables} table↔JSON pairs.")
    if any_critical:
        print("✗ Schema drift detected. Add Postgres columns or whitelist via KNOWN_JSON_ONLY.")
        return 1 if args.strict else 0
    print("✓ No critical drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
