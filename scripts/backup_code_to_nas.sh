#!/bin/bash
# backup_code_to_nas.sh — robust SSH-based code backup to the NAS.
# ============================================================================
# Mount-proof: backs up the whole repo (source + config + data + FULL .git history)
# in one rsync OVER SSH — no SMB mount to go stale, no git binary needed on the NAS.
# .git is packed, so it transfers as a few big files (fast); rsync sends only deltas
# on later runs. Excludes the regenerable bulk (cache/, node_modules/, data/ohlcv…).
#
# Auth: passwordless SSH key (gamphaniraj@192.168.1.25). Set up once via ssh-copy-id
# + Synology home-perm fix. Falls back with a CLEAR error (never a silent no-op).
#
#   bash scripts/backup_code_to_nas.sh
#
# Restore:  git clone ssh://gamphaniraj@192.168.1.25/volume1/CodeBackup/SwingTrade/.git
# NOTE: includes .env (API keys + NAS pw) so a restore is complete.
set -uo pipefail

SRC="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
NAS_USER="gamphaniraj"
NAS_HOST="192.168.1.25"
DEST="/volume1/CodeBackup/SwingTrade"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"
# macOS ships `openrsync` (protocol 29) at /usr/bin/rsync, which is INCOMPATIBLE
# with the NAS's rsync 3.x (protocol 31/32) — "unexpected end of file". Use the
# Homebrew rsync 3.x explicitly (it's PATH-shadowed by /usr/bin/rsync).
RSYNC="/opt/homebrew/bin/rsync"; [ -x "$RSYNC" ] || RSYNC="rsync"
ts() { date '+%H:%M:%S'; }

# ── Pre-check: SSH reachable + target share present (fail loud, not silent) ──
if ! $SSH "$NAS_USER@$NAS_HOST" "test -d /volume1/CodeBackup" 2>/dev/null; then
  echo "[$(ts)] ✗ ABORT — NAS unreachable over SSH or /volume1/CodeBackup missing."
  echo "        (check: ssh $NAS_USER@$NAS_HOST · key auth · CodeBackup shared folder)"
  exit 1
fi
$SSH "$NAS_USER@$NAS_HOST" "mkdir -p '$DEST'" 2>/dev/null

echo "[$(ts)] === rsync ($($RSYNC --version | head -1)) over SSH → $NAS_HOST:$DEST ==="
# --rsync-path=/bin/rsync: the NAS's default `rsync` is a Synology wrapper that
# refuses ("rsync service is no running", code 43) unless the rsync DAEMON service
# is enabled. /bin/rsync is the real binary and works over plain ssh.
"$RSYNC" -az --delete --human-readable -e "$SSH" --rsync-path=/bin/rsync \
  --exclude 'cache/' \
  --exclude 'node_modules/' \
  --exclude '.git.bak-*' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'infra/prototype/tickers*.json' \
  --exclude 'infra/prototype/data.json' \
  --exclude 'infra/build/node_modules/' \
  --exclude 'data/ohlcv/' \
  "$SRC/" "$NAS_USER@$NAS_HOST:$DEST/" 2>&1 | tail -4

rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then
  echo "[$(ts)] ✗ rsync exited $rc — backup may be incomplete"; exit "$rc"
fi
echo "[$(ts)] === DONE ==="
# Success marker — written ONLY on a genuine completion (a 0s/aborted run never
# reaches here). The freshness watchdog reads this file's mtime, so an exit=0 but
# do-nothing run can't masquerade as a healthy backup.
mkdir -p cache/logs && touch cache/logs/.nas_code_backup_ok
echo "  size on NAS: $($SSH "$NAS_USER@$NAS_HOST" "du -sh '$DEST' 2>/dev/null" | cut -f1)"
# Restore (NAS has no git, so NOT `git clone ssh://`):
#   1) pull the tree back:  rsync -az -e ssh --rsync-path=/bin/rsync \
#        gamphaniraj@192.168.1.25:/volume1/CodeBackup/SwingTrade/ ./SwingTrade/
#      → ./SwingTrade is then a complete working repo (.git intact).
#   2) or via SMB mount:    git clone /Volumes/CodeBackup/SwingTrade/.git SwingTrade
echo "  restore: rsync -az -e ssh --rsync-path=/bin/rsync $NAS_USER@$NAS_HOST:$DEST/ ./SwingTrade/"
