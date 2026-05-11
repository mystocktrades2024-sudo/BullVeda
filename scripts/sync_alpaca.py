#!/usr/bin/env python3
"""scripts/sync_alpaca.py — CLI shim for alpaca_sync.sync_alpaca_to_local().

Usage:
    python3 scripts/sync_alpaca.py              # rate-limited (30s min interval)
    python3 scripts/sync_alpaca.py --force      # bypass rate limit
    python3 scripts/sync_alpaca.py --quiet      # suppress info log

For cron/launchd scheduling:
    */15 * * * 1-5 9-16  cd /path/to/SwingTrade && python3 scripts/sync_alpaca.py --quiet
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alpaca_sync import sync_alpaca_to_local  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Sync Alpaca paper account → local state")
    p.add_argument("--force", action="store_true", help="bypass 30s rate-limit")
    p.add_argument("--quiet", action="store_true", help="suppress info log")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = sync_alpaca_to_local(force=args.force, verbose=not args.quiet)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
