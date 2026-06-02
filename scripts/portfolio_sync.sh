#!/bin/bash
# portfolio_sync.sh — keep the paper book in sync with Alpaca AFTER the morning
# fill window (the `fill` job only syncs 6:40am–12:50pm PT). Runs every 5 min so
# the dashboard reflects live positions/equity all day (≤5 min stale), incl. post-close.
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
cd "$ROOT" || exit 1
mkdir -p cache/logs
echo "[$(date)] portfolio sync" >> cache/logs/portfolio_sync.log
/usr/bin/python3 -c "from alpaca_sync import sync_alpaca_to_local; r=sync_alpaca_to_local(force=True); print('synced', (r.get('updated') if isinstance(r,dict) else r))" >> cache/logs/portfolio_sync.log 2>&1
