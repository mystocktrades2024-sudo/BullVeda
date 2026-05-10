"""
export_to_bugfixes_sheet.py — produce the Google Sheets-compatible CSV from
data/open_items.json so the user can paste-update the "Bug Fixes" tab in
https://docs.google.com/spreadsheets/d/1FqGkX-p3QEnSJTx4SxJLyEC6uJ7ilGf5s6yTpXmZLP8

Output: cache/open_items_for_sheet.csv

Column order matches the sheet header EXACTLY (verified against sheet read
2026-05-10):
  #, ID, Priority, Section, Item, What we're trying to fix,
  How we're fixing it, Effort, Risk / Win, Notes, Status, Date Fixed, Commit

Usage:
  python3 scripts/export_to_bugfixes_sheet.py             # writes cache/open_items_for_sheet.csv
  python3 scripts/export_to_bugfixes_sheet.py --print     # also prints to stdout
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "open_items.json"
OUTPUT = ROOT / "cache" / "open_items_for_sheet.csv"

# Sheet column order (verified by reading the live sheet 2026-05-10)
# how_to_test column added 2026-05-10 — user-facing manual verification per fix.
SHEET_COLUMNS = [
    "#", "ID", "Priority", "Section", "Item",
    "What we're trying to fix", "How we're fixing it",
    "Effort", "Risk / Win", "Notes",
    "Status", "Date Fixed", "Commit",
    "How to Test",
]

# Map registry field name → sheet column name
FIELD_MAP = {
    "id": "ID",
    "priority": "Priority",
    "section": "Section",
    "item": "Item",
    "what": "What we're trying to fix",
    "how": "How we're fixing it",
    "effort": "Effort",
    "risk_win": "Risk / Win",
    "notes": "Notes",
    "status": "Status",
    "date_fixed": "Date Fixed",
    "commit": "Commit",
    "how_to_test": "How to Test",
}

# Status priority ordering for stable sheet rows (matches sheet's existing order)
STATUS_ORDER = {"OPEN": 0, "IN_PROGRESS": 1, "DONE": 2, "DEFERRED": 3, "REJECTED": 4}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true",
                    help="Also print to stdout (handy for piping or copy-paste)")
    args = ap.parse_args()

    if not REGISTRY.exists():
        print(f"ERROR: {REGISTRY} not found")
        return 1

    data = json.loads(REGISTRY.read_text())
    items = data.get("items", [])

    # Sort: OPEN first (so live work tops the sheet), then by priority, then ID.
    # DONE items sort to the bottom and chronologically (date_fixed desc).
    def sort_key(it):
        return (
            STATUS_ORDER.get(it.get("status", "OPEN"), 9),
            PRIORITY_ORDER.get(it.get("priority", "P3"), 9),
            it.get("date_fixed", "") or "",
            it.get("id", ""),
        )

    items_sorted = sorted(items, key=sort_key)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for i, it in enumerate(items_sorted, start=1):
            row = {col: "" for col in SHEET_COLUMNS}
            row["#"] = i
            for src_key, sheet_col in FIELD_MAP.items():
                val = it.get(src_key)
                if val is None:
                    val = ""
                row[sheet_col] = val
            w.writerow(row)
            rows_written += 1

    print(f"✓ Wrote {rows_written} rows → {OUTPUT.relative_to(ROOT)}")
    print(f"  OPEN: {sum(1 for it in items if it.get('status') == 'OPEN')}")
    print(f"  IN_PROGRESS: {sum(1 for it in items if it.get('status') == 'IN_PROGRESS')}")
    print(f"  DONE: {sum(1 for it in items if it.get('status') == 'DONE')}")
    print(f"  DEFERRED: {sum(1 for it in items if it.get('status') == 'DEFERRED')}")
    print(f"  REJECTED: {sum(1 for it in items if it.get('status') == 'REJECTED')}")
    print()
    print("To update the sheet:")
    print("  1. Open https://docs.google.com/spreadsheets/d/1FqGkX-p3QEnSJTx4SxJLyEC6uJ7ilGf5s6yTpXmZLP8/edit?gid=755792742")
    print("  2. Select the 'Bug Fixes' tab")
    print("  3. Cmd+A → Delete (clear existing rows)")
    print("  4. Click cell A1, then File → Import → Upload → select")
    print(f"     {OUTPUT}")
    print("  5. Choose 'Replace current sheet' + 'Detect automatically' → Import")

    if args.print:
        print()
        print(OUTPUT.read_text())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
