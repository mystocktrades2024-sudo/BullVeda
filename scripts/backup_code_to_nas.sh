#!/bin/bash
# backup_code_to_nas.sh — fast, correct code backup to the NAS CodeBackup share.
# ============================================================================
# Two channels, each using the right tool:
#   A) GIT HISTORY  → a bare mirror repo on the NAS (git push --mirror). Git packs
#      objects and streams them — fast, vs rsync copying thousands of loose objects
#      over SMB one-by-one (which crawls).
#   B) WORKING FILES → rsync (EXCLUDING .git — git handles that). Source, config,
#      data/ (DB + state) and .env, minus regenerable bulk (cache/, node_modules…).
#
# Prereq: mount the share — Finder → ⌘K → smb://192.168.1.25 → CodeBackup
#         (appears at /Volumes/CodeBackup).
#
#   bash scripts/backup_code_to_nas.sh
#
# NOTE: includes .env (API keys + NAS password) so a restore is complete. Add
#       --exclude '.env' to channel B if you don't want secrets on the NAS.
set -uo pipefail

SRC="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
NAS="${1:-/Volumes/CodeBackup}"
[ -d "$NAS" ] || NAS="$(ls -d /Volumes/CodeBackup* 2>/dev/null | head -1)"
if [ -z "${NAS:-}" ] || [ ! -d "$NAS" ]; then
  echo "✗ CodeBackup share not mounted. Finder → ⌘K → smb://192.168.1.25 → CodeBackup, then re-run."
  exit 1
fi

GITMIRROR="$NAS/SwingTrade.git"
FILES="$NAS/SwingTrade"
ts() { date '+%H:%M:%S'; }

echo "[$( ts )] === A) git history → $GITMIRROR ==="
if [ ! -d "$GITMIRROR" ]; then
  git init --bare "$GITMIRROR" >/dev/null && echo "  created bare mirror repo"
fi
# --mirror keeps the NAS repo an exact replica of all local refs (branches+tags).
if git -C "$SRC" push --mirror "$GITMIRROR" 2>&1 | sed 's/^/  /'; then
  echo "  ✓ git history mirrored"
else
  echo "  ⚠ git push had issues (see above)"
fi

echo "[$( ts )] === B) working files → $FILES (rsync, no .git) ==="
mkdir -p "$FILES"
rsync -a --delete --human-readable \
  --exclude '.git/' \
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
  --exclude 'CON.*' --exclude 'PRN.*' --exclude 'AUX.*' --exclude 'NUL.*' \
  "$SRC/" "$FILES/" 2>&1 | tail -3

echo "[$( ts )] === DONE ==="
echo "  git mirror : $(du -sh "$GITMIRROR" 2>/dev/null | cut -f1)  ($GITMIRROR)"
echo "  files      : $(du -sh "$FILES" 2>/dev/null | cut -f1)  ($FILES)"
echo "  restore code: git clone \"$GITMIRROR\" SwingTrade"
