#!/usr/bin/env python3
"""SwingTrade open-items registry CLI.

Source of truth: data/open_items.json
Output:          cache/open_items_<DATE>.xlsx (regenerated on demand)

Usage:
  python3 scripts/update_open_items.py xlsx                    # rebuild Excel from registry
  python3 scripts/update_open_items.py list                    # list all items (status-grouped)
  python3 scripts/update_open_items.py list --open             # only OPEN items
  python3 scripts/update_open_items.py done <id>               # mark item DONE (auto: today + HEAD commit)
  python3 scripts/update_open_items.py done <id> --commit <hash> --date 2026-05-09
  python3 scripts/update_open_items.py status <id> <STATUS>    # set arbitrary status (OPEN/IN_PROGRESS/DONE/DEFERRED/REJECTED)
  python3 scripts/update_open_items.py add <id> <priority> <section> "<item>" "<what>" "<how>"

Workflow:
  1. Edit data/open_items.json directly to add new items, OR use `add` subcommand.
  2. After every fix:  python3 scripts/update_open_items.py done <id>
  3. Regenerate Excel: python3 scripts/update_open_items.py xlsx
  4. Optional — drop into git pre-push hook so Excel ships with each push.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "open_items.json"
OUT_DIR = ROOT / "cache"


def _load() -> dict:
    with open(REGISTRY) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(REGISTRY, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _today() -> str:
    return dt.date.today().isoformat()


def _head_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT
        ).decode().strip()
    except Exception:
        return ""


def _find(data: dict, item_id: str) -> dict | None:
    for it in data["items"]:
        if it["id"].lower() == item_id.lower():
            return it
    return None


def cmd_list(args: argparse.Namespace) -> int:
    data = _load()
    items = data["items"]
    if args.open_only:
        items = [it for it in items if it["status"] in ("OPEN", "IN_PROGRESS")]

    by_status: dict[str, list[dict]] = {}
    for it in items:
        by_status.setdefault(it["status"], []).append(it)

    for status in ("OPEN", "IN_PROGRESS", "DONE", "DEFERRED", "REJECTED"):
        rows = by_status.get(status, [])
        if not rows:
            continue
        print(f"\n=== {status} ({len(rows)}) ===")
        for it in rows:
            date = it.get("date_fixed") or "—"
            commit = it.get("commit") or "—"
            print(f"  [{it['priority']:>3}] {it['id']:<14} {it['section']:<30} {it['item'][:60]}")
            if status == "DONE":
                print(f"         ↳ {date}  {commit}")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    data = _load()
    it = _find(data, args.id)
    if not it:
        print(f"ERROR: no item with id '{args.id}'", file=sys.stderr)
        return 1
    it["status"] = "DONE"
    it["date_fixed"] = args.date or _today()
    it["commit"] = args.commit or _head_commit()
    _save(data)
    print(f"OK  {it['id']} → DONE  ({it['date_fixed']}  {it['commit']})")
    print(f"    {it['item']}")
    print()
    print("Tip: run `python3 scripts/update_open_items.py xlsx` to regenerate Excel.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    valid = {"OPEN", "IN_PROGRESS", "DONE", "DEFERRED", "REJECTED"}
    if args.new_status.upper() not in valid:
        print(f"ERROR: status must be one of {sorted(valid)}", file=sys.stderr)
        return 1
    data = _load()
    it = _find(data, args.id)
    if not it:
        print(f"ERROR: no item with id '{args.id}'", file=sys.stderr)
        return 1
    it["status"] = args.new_status.upper()
    if it["status"] == "DONE" and not it.get("date_fixed"):
        it["date_fixed"] = _today()
        it["commit"] = _head_commit()
    _save(data)
    print(f"OK  {it['id']} → {it['status']}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    data = _load()
    if _find(data, args.id):
        print(f"ERROR: item '{args.id}' already exists", file=sys.stderr)
        return 1
    new = {
        "id": args.id,
        "priority": args.priority,
        "section": args.section,
        "item": args.item,
        "what": args.what,
        "how": args.how,
        "effort": "",
        "risk_win": "",
        "notes": "",
        "status": "OPEN",
        "date_fixed": None,
        "commit": None,
    }
    data["items"].append(new)
    _save(data)
    print(f"OK  added {new['id']}  [{new['priority']}] {new['section']}: {new['item']}")
    return 0


def cmd_xlsx(args: argparse.Namespace) -> int:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("ERROR: openpyxl not installed. pip3 install openpyxl", file=sys.stderr)
        return 1

    data = _load()
    items = data["items"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"open_items_{_today()}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Open Items"

    headers = ["#", "ID", "Priority", "Section", "Item",
               "What we're trying to fix", "How we're fixing it",
               "Effort", "Risk / Win", "Notes",
               "Status", "Date Fixed", "Commit",
               "How to Test"]   # 2026-05-10: user-facing manual verification per fix
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    for c in ws[1]:
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32

    PRI_COLOR = {"P0": "F4CCCC", "P1": "FFF2CC", "P2": "D9EAD3"}
    STATUS_COLOR = {
        "OPEN":        "FFFFFF",
        "IN_PROGRESS": "FFE9B5",
        "DONE":        "C6EFCE",
        "DEFERRED":    "DDDDDD",
        "REJECTED":    "F2DCDB",
    }
    STATUS_FONT = {
        "OPEN":        ("000000", False),
        "IN_PROGRESS": ("9C5700", True),
        "DONE":        ("006100", True),
        "DEFERRED":    ("555555", False),
        "REJECTED":    ("9C0006", True),
    }

    border = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )

    # Sort: OPEN/IN_PROGRESS first, then DONE/DEFERRED/REJECTED, by priority within
    pri_order = {"P0": 0, "P1": 1, "P2": 2}
    status_order = {"OPEN": 0, "IN_PROGRESS": 1, "DONE": 2, "DEFERRED": 3, "REJECTED": 4}
    sorted_items = sorted(items, key=lambda it: (
        status_order.get(it["status"], 9),
        pri_order.get(it["priority"], 9),
        it["section"],
        it["id"],
    ))

    for idx, it in enumerate(sorted_items, start=1):
        row = [
            idx,
            it["id"],
            it["priority"],
            it["section"],
            it["item"],
            it.get("what", ""),
            it.get("how", ""),
            it.get("effort", ""),
            it.get("risk_win", ""),
            it.get("notes", ""),
            it["status"],
            it.get("date_fixed") or "",
            it.get("commit") or "",
            it.get("how_to_test") or "",   # col 14: how-to-test
        ]
        ws.append(row)
        r = idx + 1

        # Priority cell
        ws.cell(row=r, column=3).fill = PatternFill("solid", fgColor=PRI_COLOR.get(it["priority"], "FFFFFF"))
        ws.cell(row=r, column=3).font = Font(bold=True, size=11)

        # Status cell — color + bold
        s_color, s_bold = STATUS_FONT.get(it["status"], ("000000", False))
        ws.cell(row=r, column=11).fill = PatternFill("solid", fgColor=STATUS_COLOR.get(it["status"], "FFFFFF"))
        ws.cell(row=r, column=11).font = Font(color=s_color, bold=s_bold, size=10)

        # Center for compact columns
        for col in (1, 2, 3, 8, 11, 12, 13):
            ws.cell(row=r, column=col).alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        # Left-align long prose columns (incl. col 14 How to Test)
        for col in (4, 5, 6, 7, 9, 10, 14):
            ws.cell(row=r, column=col).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        # ID + commit monospace
        for col in (2, 13):
            ws.cell(row=r, column=col).font = Font(name="Menlo", size=10)
        # How to Test in monospace too (commands)
        ws.cell(row=r, column=14).font = Font(name="Menlo", size=9)
        # Item bold
        ws.cell(row=r, column=5).font = Font(bold=True, size=10)
        # All borders
        for col in range(1, len(row) + 1):
            ws.cell(row=r, column=col).border = border

        # Row height proportional to longest prose (now includes how_to_test)
        max_len = max(len(it.get(k, "") or "") for k in ("what", "how", "notes", "item", "how_to_test"))
        lines = max(3, min(20, max_len // 80 + 2))
        ws.row_dimensions[r].height = 15 * lines

    ws.freeze_panes = "B2"

    widths = [4, 12, 7, 22, 38, 52, 60, 12, 22, 26, 13, 12, 13, 60]   # 14th = How to Test (wide)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ───── Sheet 2: rollup by status × priority ─────
    ws2 = wb.create_sheet("Rollup")
    ws2.append(["Status", "P0", "P1", "P2", "Total"])
    for c in ws2[1]:
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")
    for status in ("OPEN", "IN_PROGRESS", "DONE", "DEFERRED", "REJECTED"):
        rows = [it for it in items if it["status"] == status]
        if not rows:
            continue
        p0 = sum(1 for it in rows if it["priority"] == "P0")
        p1 = sum(1 for it in rows if it["priority"] == "P1")
        p2 = sum(1 for it in rows if it["priority"] == "P2")
        ws2.append([status, p0, p1, p2, p0 + p1 + p2])
        last = ws2.max_row
        ws2.cell(row=last, column=1).fill = PatternFill("solid", fgColor=STATUS_COLOR.get(status, "FFFFFF"))
        s_color, s_bold = STATUS_FONT.get(status, ("000000", False))
        ws2.cell(row=last, column=1).font = Font(color=s_color, bold=True)
        for col in range(1, 6):
            ws2.cell(row=last, column=col).border = border
            if col > 1:
                ws2.cell(row=last, column=col).alignment = Alignment(horizontal="center")
    # totals
    ws2.append(["TOTAL",
                sum(1 for it in items if it["priority"] == "P0"),
                sum(1 for it in items if it["priority"] == "P1"),
                sum(1 for it in items if it["priority"] == "P2"),
                len(items)])
    last = ws2.max_row
    for col in range(1, 6):
        c = ws2.cell(row=last, column=col)
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.font = Font(bold=True, color="FFFFFF")
        c.border = border
        c.alignment = Alignment(horizontal="center")

    ws2.column_dimensions["A"].width = 14
    for col in "BCDE":
        ws2.column_dimensions[col].width = 8

    # ───── Sheet 3: how-to-update legend ─────
    ws3 = wb.create_sheet("How to Update")
    ws3.append(["Step", "Command", "What it does"])
    for c in ws3[1]:
        c.fill = header_fill
        c.font = header_font
    rows = [
        ("1", "python3 scripts/update_open_items.py list", "Show all items grouped by status"),
        ("2", "python3 scripts/update_open_items.py list --open", "Show only OPEN / IN_PROGRESS"),
        ("3", "python3 scripts/update_open_items.py done <id>", "Mark item DONE (auto-fills today's date + HEAD commit)"),
        ("4", "python3 scripts/update_open_items.py done <id> --commit abc123 --date 2026-05-09", "Mark DONE with explicit commit/date"),
        ("5", "python3 scripts/update_open_items.py status <id> IN_PROGRESS", "Set arbitrary status (OPEN/IN_PROGRESS/DONE/DEFERRED/REJECTED)"),
        ("6", "python3 scripts/update_open_items.py add NEW-ID P1 \"Section\" \"Item title\" \"What\" \"How\"", "Add a new item to the registry"),
        ("7", "python3 scripts/update_open_items.py xlsx", "Regenerate this Excel from data/open_items.json"),
        ("8", "edit data/open_items.json directly, then run xlsx", "Free-form edits — works too"),
    ]
    for s, c, d in rows:
        ws3.append([s, c, d])
        last = ws3.max_row
        ws3.cell(row=last, column=1).font = Font(bold=True, size=12)
        ws3.cell(row=last, column=2).font = Font(name="Menlo", size=10)
        for col in (1, 2, 3):
            ws3.cell(row=last, column=col).border = border
            ws3.cell(row=last, column=col).alignment = Alignment(vertical="top", wrap_text=True)
    ws3.column_dimensions["A"].width = 6
    ws3.column_dimensions["B"].width = 75
    ws3.column_dimensions["C"].width = 60

    wb.save(out)

    n_open = sum(1 for it in items if it["status"] == "OPEN")
    n_prog = sum(1 for it in items if it["status"] == "IN_PROGRESS")
    n_done = sum(1 for it in items if it["status"] == "DONE")
    n_defr = sum(1 for it in items if it["status"] == "DEFERRED")
    n_rej  = sum(1 for it in items if it["status"] == "REJECTED")

    print(f"Wrote {out}")
    print(f"  OPEN={n_open}  IN_PROGRESS={n_prog}  DONE={n_done}  DEFERRED={n_defr}  REJECTED={n_rej}  TOTAL={len(items)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="list items")
    s.add_argument("--open", dest="open_only", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("done", help="mark item DONE")
    s.add_argument("id")
    s.add_argument("--commit", default=None)
    s.add_argument("--date", default=None)
    s.set_defaults(func=cmd_done)

    s = sub.add_parser("status", help="set arbitrary status")
    s.add_argument("id")
    s.add_argument("new_status")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("add", help="add new item")
    s.add_argument("id")
    s.add_argument("priority", choices=["P0", "P1", "P2"])
    s.add_argument("section")
    s.add_argument("item")
    s.add_argument("what")
    s.add_argument("how")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("xlsx", help="regenerate Excel from registry")
    s.set_defaults(func=cmd_xlsx)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
