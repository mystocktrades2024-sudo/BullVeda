"""Daily state backup for critical JSON state files.
Runs on scan startup; idempotent - one snapshot per day."""

from pathlib import Path
from datetime import datetime, date, timedelta
import shutil
import logging

log = logging.getLogger("state_backup")
BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "data" / "backups"
RETENTION_DAYS = 7

# Files to snapshot
STATE_FILES = [
    BASE_DIR / "data" / "portfolio_state.json",
    BASE_DIR / "data" / "signal_log.json",
    BASE_DIR / "data" / "signal_log.meta.json",
    BASE_DIR / "cache" / "picks_history.json",
    BASE_DIR / "data" / "custom_tracked.json",
    BASE_DIR / "data" / "alert_sent_log.json",
    BASE_DIR / "data" / "equity_audit.json",  # if exists
    BASE_DIR / "data" / "scan_health.json",
    BASE_DIR / "data" / "gap_events.json",
]


def backup_state(force: bool = False) -> dict:
    """Create today's snapshot if not exists. Cleans old backups. Idempotent."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    today_dir = BACKUP_DIR / today

    if today_dir.exists() and not force:
        return {"status": "skipped", "reason": "already_backed_up_today", "date": today}

    today_dir.mkdir(exist_ok=True)
    copied = []
    errors = []
    for src in STATE_FILES:
        if not src.exists():
            continue
        try:
            dst = today_dir / src.name
            shutil.copy2(src, dst)
            copied.append(src.name)
        except Exception as e:
            errors.append({"file": src.name, "error": str(e)})

    # Cleanup old backups
    cutoff = date.today() - timedelta(days=RETENTION_DAYS)
    removed = []
    for d in BACKUP_DIR.iterdir():
        if not d.is_dir():
            continue
        try:
            d_date = date.fromisoformat(d.name)
            if d_date < cutoff:
                shutil.rmtree(d)
                removed.append(d.name)
        except (ValueError, Exception):
            pass  # not a date-named dir, skip

    log.info(f"State backup {today}: {len(copied)} files snapshotted, {len(removed)} old dirs removed")
    return {
        "status": "ok",
        "date": today,
        "backed_up": copied,
        "removed_old": removed,
        "errors": errors,
    }


def restore_from_backup(backup_date: str) -> dict:
    """Restore state files from a specific backup date. BE CAREFUL - overwrites current."""
    src_dir = BACKUP_DIR / backup_date
    if not src_dir.exists():
        return {"error": f"No backup found for {backup_date}"}

    restored = []
    errors = []
    for f in src_dir.iterdir():
        if not f.is_file():
            continue
        # Find target location in STATE_FILES
        target = None
        for sf in STATE_FILES:
            if sf.name == f.name:
                target = sf
                break
        if target:
            try:
                shutil.copy2(f, target)
                restored.append(f.name)
            except Exception as e:
                errors.append({"file": f.name, "error": str(e)})

    log.warning(f"RESTORED {len(restored)} files from backup {backup_date}")
    return {"status": "ok", "restored": restored, "errors": errors}


def list_backups() -> list:
    """Return list of available backup dates."""
    if not BACKUP_DIR.exists():
        return []
    backups = []
    for d in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        try:
            date.fromisoformat(d.name)
            files = [f.name for f in d.iterdir() if f.is_file()]
            size_kb = sum(f.stat().st_size for f in d.iterdir() if f.is_file()) / 1024
            backups.append({
                "date": d.name,
                "file_count": len(files),
                "size_kb": round(size_kb, 1),
            })
        except ValueError:
            continue
    return backups


if __name__ == "__main__":
    import sys
    if "--list" in sys.argv:
        print("Available backups:")
        for b in list_backups():
            print(f"  {b['date']}: {b['file_count']} files, {b['size_kb']} KB")
    elif "--force" in sys.argv:
        print(backup_state(force=True))
    else:
        print(backup_state())
