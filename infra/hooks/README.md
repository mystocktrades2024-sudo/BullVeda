# Git hooks (portable copies)

`.git/hooks/` is local to each clone and not tracked. This folder holds
re-installable copies. To install on a fresh clone:

```bash
cp infra/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## pre-commit

Two responsibilities:

1. **Open-items Excel auto-rebuild** — when a commit touches
   `data/open_items.json` or `scripts/update_open_items.py`, regenerates
   `cache/open_items_<DATE>.xlsx` and stages it so the Excel ships in the
   same commit. Trigger is the registry edit, not every commit.

2. **F11 schema drift check** — when a commit touches `data/*.json`,
   `migrations/*.sql`, or `db.py`, blocks if NEW JSON keys appear without
   matching Postgres columns. Pre-existing drift is documented tech debt,
   not a commit-blocker.

Bypass either: `git commit --no-verify`.
