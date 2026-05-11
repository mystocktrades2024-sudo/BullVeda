# SwingTrade · Supabase migration package

Full Supabase Postgres schema for SwingTrade — 103 tables across 18 domains,
RLS enabled on every table, plus Python loaders that lift the existing
SQLite + JSON sidecar data into the new schema.

## Files

```
supabase/
├── apply.py                      # apply every migration in order
├── load_all.py                   # apply + load everything end-to-end
├── README.md                     # this file
├── migrations/
│   ├── 0001_extensions_and_helpers.sql
│   ├── 0002_core.sql              # tickers, runs, regime_history
│   ├── 0003_analysis.sql          # ticker_analyses + narrow tables
│   ├── 0004_tradeplan.sql
│   ├── 0005_technicals.sql        # 14 indicator-family tables
│   ├── 0006_smc.sql
│   ├── 0007_wave.sql              # elliott_wave + theory_confluence
│   ├── 0008_fundamentals.sql      # 7 tables, mostly per-ticker
│   ├── 0009_options.sql
│   ├── 0010_smartmoney.sql        # insider / congressional / 13F / SEC
│   ├── 0011_sentiment.sql         # news_articles m:m + social
│   ├── 0012_zacks_risk_signals.sql
│   ├── 0013_earnings.sql          # FK chain restored
│   ├── 0014_ohlcv.sql
│   ├── 0015_decision.sql          # partitioned decision_log + gates
│   ├── 0016_portfolio.sql         # lift from swingtrade.db
│   ├── 0017_governance.sql        # users / roles / RBAC / open_items
│   ├── 0018_indexes.sql           # composite + BRIN + GIN
│   ├── 0019_rls.sql               # RLS policies (admin / trader / quant / viewer)
│   └── 0020_seed.sql              # default roles + portfolio singleton
└── scripts/
    ├── _client.py                 # env loader + psycopg2 / supabase-py factories
    ├── load_reference.py          # tickers, capability_registry, open_items, config_snapshot
    ├── load_sqlite.py             # data/swingtrade.db + data/fundamentals.db
    ├── load_json.py               # JSON + JSONL sidecars (incl. 33MB decision_log)
    └── verify.py                  # row-count diff: local vs Supabase
```

## Step 1 — Create the Supabase project

1. Go to https://app.supabase.com → New project (free tier is fine for the
   ~50K initial rows; upgrade later as decision_log grows).
2. Project Settings → Database → copy connection info:
   - Host, port, database name, user, **password** (the one you set at create)
3. Project Settings → API → copy:
   - `URL` (Project URL)
   - `service_role` key (NOT the `anon` key — service role bypasses RLS)

## Step 2 — Configure env vars

Add three lines to the **repo-root `.env`** (same file that holds your EODHD /
Alpaca / Slack creds):

```bash
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhb...your-service-role-key
SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.xxxxxxxxxxxx.supabase.co:5432/postgres
```

Where to find them:
- `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` → Supabase dashboard → **Settings → API**
- `SUPABASE_DB_URL` → Supabase dashboard → **Settings → Database → Connection string → URI**
  (use the `service_role` connection if offered, NOT the read-only one)

The loader auto-appends `?sslmode=require` if missing.

Install Python deps:

```bash
pip3 install psycopg2-binary supabase
```

## Step 3 — Apply migrations + load data

**Option A · One shot (recommended for first run):**

```bash
python3 supabase/load_all.py --smoke
```

`--smoke` caps decision_log at 5,000 rows so the first run finishes in <60s.
Drop `--smoke` for the full ~33MB ingest.

**Option B · Step-by-step (preferred for debugging):**

```bash
# 1. DDL
python3 supabase/apply.py

# 2. Reference data (tickers, RBAC, open-items)
python3 supabase/scripts/load_reference.py

# 3. SQLite tables (portfolio, signals, fundamentals)
python3 supabase/scripts/load_sqlite.py

# 4. JSON sidecars (earnings, decision_log, regime)
python3 supabase/scripts/load_json.py

# 5. Sanity check
python3 supabase/scripts/verify.py
```

**Option C · Skip Python, use psql directly:**

```bash
export PGPASSWORD=your-database-password-here
PSQL_OPTS="-h db.xxxxxxxxxxxx.supabase.co -U postgres -d postgres"

for f in supabase/migrations/*.sql; do
  echo "→ $f"
  psql $PSQL_OPTS -f "$f" || break
done
```

Then run loaders as in Option B steps 2–5.

## Step 4 — Create your first user

After migrations, Supabase Auth has no users. To get into the dashboard with
a real role:

1. Supabase dashboard → Authentication → Users → "Invite user" → enter your
   email. You'll receive a magic-link.
2. After clicking the link, your row exists in `auth.users`. Run this in
   the SQL editor:
   ```sql
   insert into public.users (id, email, role, display_name)
   values (
     (select id from auth.users where email='you@example.com'),
     'you@example.com',
     'admin',
     'You'
   );
   ```
3. Your dashboard now has full admin access.

## Migration model

| Concept | Source → Target |
|---|---|
| Identity | `cache/last_bundle.json` (sp500/r1000/r2000) → `tickers` |
| Run | `swingtrade.db::runs` → `runs` |
| Portfolio | `swingtrade.db::portfolio_state`, `positions`, `closed_trades` → identical names |
| Fundamentals | `fundamentals.db::fundamentals` → `ticker_fundamentals` |
| Trade journal | `swingtrade.db::signal_log` → `signal_log` (rename `date` → `observed_at`) |
| Picks history | `cache/picks_history.json` → `runs` + `picks_history_runs` |
| Earnings | `earnings_watchlist.json` + `earnings_beat_predictions.json` + `earnings_outcomes.jsonl` → `earnings_events` (canonical) + `earnings_predictions` + `earnings_outcomes` (FK chain restored) |
| Decision log | `decision_log.jsonl` (33MB) → partitioned `decision_log` |
| Regime | `cache/regime_history.json` → `regime_history` |
| RBAC | `data/capability_registry.json` → `capability_registry` + `role_capabilities` (m:m) |
| Open items | `data/open_items.json` → `open_items` |

### Not yet migrated (require new ETL)

The schema *defines* every analysis sub-table (technicals, SMC, options,
risk, etc.) but **no per-analysis data is loaded yet** because the current
SwingTrade pipeline writes everything into `cache/last_bundle.json` as a
55 MB monolithic dict, not into these tables.

Next step is to add a writer in `swing_trade.py` that, when a scan
finishes, upserts to Supabase via `supabase-py`. Start with this slice:

1. `ticker_analyses` (the header row)
2. `analysis_scoring`, `analysis_verdict`, `analysis_conviction`
3. `trade_plans` + `trade_plan_entries` + `trade_plan_risk`
4. `risk_sizing`

That's enough to render the Elite Picks tab from Supabase.

## RLS notes

Every public table has RLS enabled. The policy summary:

| Role | Read | Write |
|---|---|---|
| `service_role` (Python ETL) | all | all (bypasses RLS) |
| `admin` | all | all |
| `trader` | all | portfolio / positions / closed_trades / watch_triggers / custom_tickers / signal_log |
| `quant` | all | none (read-only) |
| `viewer` | all | none (read-only) |
| `anon` | none | none |

`service_role` is what Python loaders use — never expose this key in
browser code. The Supabase JS client should use the `anon` key + user JWT;
RLS will then enforce the role-based limits.

## Common operations

```bash
# Re-apply just the RLS file (e.g. after policy tweak)
python3 supabase/apply.py --only 0019

# Smoke-load decision_log only (5k rows)
python3 supabase/scripts/load_json.py --only decision_log --decision-log-max 5000

# Re-run only the fundamentals lift (e.g. after refreshing fundamentals.db)
python3 supabase/scripts/load_sqlite.py --only fundamentals

# Verify diffs
python3 supabase/scripts/verify.py
```

## Rollback

Migrations are additive — `create table if not exists` won't drop existing
data. To start fresh:

```sql
-- DANGER: drops every public table
do $$ declare r record;
begin
  for r in select tablename from pg_tables where schemaname='public' loop
    execute format('drop table public.%I cascade', r.tablename);
  end loop;
end $$;
```

Then re-run `python3 supabase/load_all.py`.

## Known limitations

- `decision_log` partition function creates 12 months forward. Wire it to
  a Supabase cron (`select cron.schedule(...)`) so partitions auto-extend.
- `news_articles` provider field accepts only `eodhd`, `yahoo`, `polygon`.
  Add new providers via `alter table … drop constraint … add constraint`.
- The `tickers` master is seeded from `last_bundle.json` — point-in-time
  membership for backtests (audit #1) needs Wikipedia revision scraping,
  which is out of scope for this migration.
- Loaders are idempotent on PK conflict but **do not delete stale rows**.
  If a closed_trade is removed locally, it remains in Supabase. Sync-strict
  mirroring needs a separate `--prune` flag.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `connection refused` | Wrong host/port in `.env` | Re-copy from Supabase dashboard → Database → Connection info |
| `password authentication failed` | Wrong `SUPABASE_DB_PASSWORD` | Reset in Supabase → Settings → Database |
| `permission denied for table users` | Using `anon` key for ETL | Use `service_role` key (bypasses RLS) |
| `decision_log_default partition full` | Out-of-range date | Run `select public.ensure_decision_log_partitions(24)` |
| `relation "tickers" does not exist` | Migrations not applied | `python3 supabase/apply.py` |
