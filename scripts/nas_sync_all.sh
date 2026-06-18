#!/bin/bash
# nas_sync_all.sh — push snapshots + all track-history to the NAS deep store.
# Run nightly by com.swingtrade.nas-sync (and safe to run manually).
set -uo pipefail
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
/usr/bin/python3 scripts/sync_snapshots_to_nas.py
/usr/bin/python3 scripts/sync_history_to_nas.py
