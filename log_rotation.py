"""Log rotation helper — compress files older than N days, delete older than M days.
Runs on scan startup (idempotent, fast no-op when nothing to rotate)."""

from pathlib import Path
import gzip
import shutil
import time
from datetime import datetime, timedelta
import logging

log = logging.getLogger("log_rotation")

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "cache" / "logs"
ARCHIVE_DIR = BASE_DIR / "cache" / "logs_archive"

RETENTION_DAYS = 30   # gzip files older than this
DELETE_DAYS = 90      # delete compressed files older than this


def rotate_logs(dry_run: bool = False) -> dict:
    """Compress old logs, delete very-old compressed logs. Returns stats."""
    if not LOG_DIR.exists():
        return {"compressed": 0, "deleted": 0, "errors": 0}

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    compress_cutoff = now - (RETENTION_DAYS * 86400)
    delete_cutoff = now - (DELETE_DAYS * 86400)

    compressed = 0
    deleted = 0
    errors = 0

    # Step 1: compress uncompressed logs older than RETENTION_DAYS
    for f in LOG_DIR.iterdir():
        if not f.is_file():
            continue
        if f.suffix == ".gz":
            continue
        try:
            if f.stat().st_mtime < compress_cutoff:
                target = ARCHIVE_DIR / (f.name + ".gz")
                if target.exists():
                    # Already archived — delete source if duplicate
                    if not dry_run:
                        f.unlink()
                    continue
                if not dry_run:
                    with open(f, "rb") as src, gzip.open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    f.unlink()
                compressed += 1
        except Exception as e:
            log.warning(f"Compress failed for {f.name}: {e}")
            errors += 1

    # Step 2: delete compressed files older than DELETE_DAYS
    for f in ARCHIVE_DIR.iterdir():
        if not f.is_file():
            continue
        try:
            if f.stat().st_mtime < delete_cutoff:
                if not dry_run:
                    f.unlink()
                deleted += 1
        except Exception as e:
            log.warning(f"Delete failed for {f.name}: {e}")
            errors += 1

    if compressed or deleted:
        log.info(f"Log rotation: compressed {compressed}, deleted {deleted}")
    return {"compressed": compressed, "deleted": deleted, "errors": errors}


def get_log_stats() -> dict:
    """Return current log directory sizes + counts for diagnostics."""
    def size_of(d: Path) -> int:
        if not d.exists(): return 0
        return sum(f.stat().st_size for f in d.iterdir() if f.is_file())
    def count_of(d: Path) -> int:
        if not d.exists(): return 0
        return sum(1 for f in d.iterdir() if f.is_file())
    return {
        "active_logs": count_of(LOG_DIR),
        "archived_logs": count_of(ARCHIVE_DIR),
        "active_size_mb": round(size_of(LOG_DIR) / 1024 / 1024, 2),
        "archived_size_mb": round(size_of(ARCHIVE_DIR) / 1024 / 1024, 2),
    }


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    stats = rotate_logs(dry_run=dry)
    print(f"Log rotation {'DRY-RUN' if dry else 'COMPLETE'}: {stats}")
    print(f"Log stats: {get_log_stats()}")
