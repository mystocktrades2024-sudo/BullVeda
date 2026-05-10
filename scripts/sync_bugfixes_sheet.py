"""
sync_bugfixes_sheet.py — push data/open_items.json directly to the Google Sheet.

URL: https://docs.google.com/spreadsheets/d/1FqGkX-p3QEnSJTx4SxJLyEC6uJ7ilGf5s6yTpXmZLP8/
Tab: "Bug Fixes" (gid=755792742)

Uses gspread + Google Cloud service account credentials. No new license cost
(Google Sheets API has free quota; service accounts are free).

ONE-TIME SETUP (~5 minutes, no cost):

  1. https://console.cloud.google.com/ — create a free project (e.g. "swingtrade")
  2. Enable APIs: Google Sheets API + Google Drive API
  3. Create a Service Account:
       IAM & Admin → Service Accounts → Create
       Name: "swingtrade-sheet-sync"
       Skip role assignment (not needed)
       Done
  4. Generate JSON key:
       Click the service account → Keys → Add Key → JSON → Create
       Save the downloaded JSON to:  config/gcp_service_account.json
       (gitignored — never commit)
  5. SHARE THE SHEET with the service account's email (in the JSON, field client_email):
       Open the sheet → Share → paste the service-account email → Editor → Done
       Untick "Notify people" since service accounts don't read email.
  6. Test: python3 scripts/sync_bugfixes_sheet.py --check

USAGE:
  python3 scripts/sync_bugfixes_sheet.py            # push registry → sheet
  python3 scripts/sync_bugfixes_sheet.py --check    # auth + read sheet only
  python3 scripts/sync_bugfixes_sheet.py --dry-run  # show what would change

GRACEFUL DEGRADATION:
  If config/gcp_service_account.json is missing or invalid, the script exits
  with code 0 and prints instructions — does NOT block the pre-commit hook
  or CI pipeline. The CSV mirror (cache/open_items_for_sheet.csv via
  export_to_bugfixes_sheet.py) is always written regardless.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "open_items.json"
CREDS_PATH = ROOT / "config" / "gcp_service_account.json"

SHEET_ID = "1FqGkX-p3QEnSJTx4SxJLyEC6uJ7ilGf5s6yTpXmZLP8"
SHEET_TAB_NAME = "Bug Fixes"

# Same column order as export_to_bugfixes_sheet.py (single source of truth lives there)
SHEET_COLUMNS = [
    "#", "ID", "Priority", "Section", "Item",
    "What we're trying to fix", "How we're fixing it",
    "Effort", "Risk / Win", "Notes",
    "Status", "Date Fixed", "Commit",
    "How to Test",
]

FIELD_MAP = {
    "id": "ID", "priority": "Priority", "section": "Section", "item": "Item",
    "what": "What we're trying to fix", "how": "How we're fixing it",
    "effort": "Effort", "risk_win": "Risk / Win", "notes": "Notes",
    "status": "Status", "date_fixed": "Date Fixed", "commit": "Commit",
    "how_to_test": "How to Test",
}

STATUS_ORDER = {"OPEN": 0, "IN_PROGRESS": 1, "DONE": 2, "DEFERRED": 3, "REJECTED": 4}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _setup_instructions(reason: str) -> None:
    print()
    print("=" * 70)
    print("Google Sheet sync NOT configured.")
    print(f"Reason: {reason}")
    print("=" * 70)
    print()
    print("To enable (one-time, ~5 min, no cost):")
    print("  1. Create a free Google Cloud project at console.cloud.google.com")
    print("  2. Enable Google Sheets API + Google Drive API")
    print("  3. Create a Service Account → Keys → Add Key → JSON")
    print(f"  4. Save the JSON to {CREDS_PATH}")
    print(f"  5. Share https://docs.google.com/spreadsheets/d/{SHEET_ID}/")
    print("     with the service account email (Editor role)")
    print("  6. Re-run: python3 scripts/sync_bugfixes_sheet.py --check")
    print()
    print("CSV mirror is always written regardless (no Google Sheet needed).")
    print()


def _load_registry() -> list[dict]:
    if not REGISTRY.exists():
        raise FileNotFoundError(f"{REGISTRY} not found")
    data = json.loads(REGISTRY.read_text())
    items = data.get("items", [])

    def sort_key(it):
        return (
            STATUS_ORDER.get(it.get("status", "OPEN"), 9),
            PRIORITY_ORDER.get(it.get("priority", "P3"), 9),
            it.get("date_fixed", "") or "",
            it.get("id", ""),
        )

    return sorted(items, key=sort_key)


def _to_rows(items: list[dict]) -> list[list[str]]:
    rows = [SHEET_COLUMNS]  # header
    for i, it in enumerate(items, start=1):
        row = []
        for col in SHEET_COLUMNS:
            if col == "#":
                row.append(str(i))
            else:
                # Reverse lookup: column → registry field
                src_key = next((k for k, v in FIELD_MAP.items() if v == col), None)
                val = (it.get(src_key) if src_key else "") or ""
                row.append(str(val))
        rows.append(row)
    return rows


def _open_sheet():
    """Returns the worksheet object, or raises with a helpful message."""
    if not CREDS_PATH.exists():
        raise RuntimeError(f"Service account JSON not found at {CREDS_PATH}")

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise RuntimeError(f"gspread / google-auth not installed: {e}")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=scopes)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(SHEET_ID)
    try:
        ws = sheet.worksheet(SHEET_TAB_NAME)
    except gspread.WorksheetNotFound:
        # Find by gid 755792742 fallback
        ws = next((w for w in sheet.worksheets() if str(w.id) == "755792742"), None)
        if ws is None:
            raise RuntimeError(f"Tab '{SHEET_TAB_NAME}' (gid 755792742) not found in sheet")
    return ws


def push() -> tuple[int, int]:
    """Push registry → sheet. Returns (rows_pushed, sheet_rows_after)."""
    items = _load_registry()
    rows = _to_rows(items)

    ws = _open_sheet()

    # Clear + bulk write. Most efficient single API call.
    ws.clear()
    ws.update(values=rows, range_name="A1")

    # Freeze header row
    try:
        ws.freeze(rows=1)
    except Exception:
        pass

    return (len(rows) - 1, ws.row_count)


def check() -> None:
    """Verify auth + read access by fetching first 3 rows."""
    ws = _open_sheet()
    print(f"✓ Connected to: {ws.spreadsheet.title} → tab '{ws.title}' ({ws.row_count} rows × {ws.col_count} cols)")
    rows = ws.get("A1:N3")
    print(f"  First 3 rows preview:")
    for i, r in enumerate(rows[:3]):
        print(f"  {i}: {r[:5]}{'...' if len(r) > 5 else ''}")


def dry_run() -> None:
    items = _load_registry()
    rows = _to_rows(items)
    print(f"Would push {len(rows) - 1} data rows + 1 header = {len(rows)} total")
    print(f"Columns: {SHEET_COLUMNS}")
    print(f"First 3 items (preview):")
    for r in rows[1:4]:
        print(f"  {r[:6]}{'...' if len(r) > 6 else ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Auth check + read first 3 rows; no write")
    ap.add_argument("--dry-run", action="store_true", help="Show what would change; no write")
    args = ap.parse_args()

    try:
        if args.dry_run:
            dry_run()
            return 0

        if args.check:
            check()
            return 0

        n_pushed, n_total = push()
        print(f"✓ Pushed {n_pushed} rows to Bug Fixes sheet (sheet now has {n_total} rows)")
        print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=755792742")
        return 0

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        # Service account not configured — graceful degradation
        _setup_instructions(str(e))
        return 0  # exit 0 so pre-commit hooks don't block


if __name__ == "__main__":
    raise SystemExit(main())
