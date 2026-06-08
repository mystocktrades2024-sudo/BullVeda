# Scope — Local 20-Year OHLCV Bar-Store

**Status:** SCOPED / NOT STARTED · **Owner:** phanirajgarimella · **Created:** 2026-06-08
**Registry:** `BARSTORE-1..6` in `data/open_items.json`

---

## Problem

Every morning the scan re-fetches per-ticker daily OHLCV from EODHD (`eod/{ticker}`,
12h TTL). On 2026-06-08 that path drove **~10,734 of ~17,036 fresh calls (~68%)** and
helped push usage to **95K/100K**, tripping the quota guard. Two direct costs:

1. **Recurring quota burn** — we re-buy the same history daily; the per-minute cap is the
   real binding constraint (see `feedback_eodhd_bottleneck_is_per_minute`).
2. **Backtests are expensive/blocked** — a `walk_forward_v2.py` re-scan re-fetches history
   per ticker per fold (5–15K calls). On 2026-06-08 the validation of the
   `BARSTORE`-dependent BE-in-choppy demote (`project_history_audit_2026_06_08`) was
   **deferred** because quota was tapped.

We have **no local bar store today** — `data/swingtrade.db` has 20 tables, none for OHLCV;
bars live as disposable per-ticker JSON in `cache/eodhd/`.

## Goal

Backfill long history **once**, store locally, and serve scans + backtests from the local
store. Read-from-DB-first; hit EODHD only for the current day's bar and gap-fills.

| | Today | With bar-store |
|---|---|---|
| Morning scan OHLCV | ~10K calls/day | ~0 (DB read) |
| Walk-forward backtest | 5–15K calls (blocked) | 0 (DB read) |
| One-time backfill | — | ~6–8K calls **once** (1/ticker) |
| Daily maintenance | — | **1 `bulk_eod`/day** |

**Economics that make this a slam-dunk:** one `eod(ticker, from_date=2005-01-01)` call
returns that ticker's *entire* history. Backfilling the full universe ≈ one morning's
current budget; ongoing OHLCV cost then drops from ~10K/day to ~1.

## Constraints

- **No new data license** (CLAUDE.md hard constraint). This uses the **existing** EODHD
  subscription more efficiently — fully compliant. (Sharadar SF1 path is `H1` REJECTED.)
- Backfill must respect the **shared per-minute limiter** (`EODHD_SHARED_LIMITER=1`,
  950/min) and run on a **low-quota window** (overnight), never during the morning stack.
- SQLite stays primary (`SWINGTRADE_USE_SQLITE`); no new heavyweight deps in Phase 1.

## Architecture (Phase 1 — SQLite)

New table `daily_bars` in `data/swingtrade.db`:

```
daily_bars(
  ticker TEXT, date TEXT,            -- PK (ticker, date)
  open REAL, high REAL, low REAL, close REAL, volume INTEGER,
  adjusted_close REAL,               -- EODHD-provided, split/div adjusted
  source TEXT DEFAULT 'eodhd',
  ingested_at TEXT
)  -- index on (ticker, date); ~30M rows (6K tickers x 20yr) ~2-4GB
```

- Writer: `eodhd_client.backfill_history()` — pages the universe, 1 call/ticker, paced
  under the limiter, idempotent upserts.
- Reader: `data_fetcher.fetch_ohlcv_with_failover` repointed **DB-first** → EODHD only for
  (a) the current incomplete day, (b) gaps.
- Later option (Phase 2+, if backtest scans feel slow): mirror to Parquet/DuckDB for
  columnar reads. Design the table so this is a straight export.

## Phases

| ID | P | Phase | Scope |
|---|---|---|---|
| BARSTORE-1 | P1 | Schema + read/write | `daily_bars` table, upsert writer, DB reader, unit tests |
| BARSTORE-2 | P1 | One-time backfill | `backfill_history()` — paced 1-call/ticker over current universe; overnight launchd; resumable |
| BARSTORE-3 | P1 | DB-first failover | repoint `fetch_ohlcv_with_failover`; EODHD only for today/gaps; validate parity vs current cache |
| BARSTORE-4 | P2 | Daily incremental | 1 `bulk_eod`/day appends latest bar for whole exchange |
| BARSTORE-5 | P2 | Corporate actions | re-adjust stored history on split/div events (the fiddly part — data-integrity risk lives here) |
| BARSTORE-6 | P2 | Delisted + survivorship | backfill delisted tickers → unblocks audit #1 (point-in-time backtests without survivorship bias) |

## What this does NOT solve

- **Point-in-time fundamentals** — EODHD `fundamentals` is a *current* snapshot, so
  historical-fundamentals backtests (P/E as-of-2019) remain a separate, harder problem.
  The fundamentals pillar in deep backtests keeps its look-ahead caveat
  (`BACKTEST_NO_FUNDAMENTALS=1` is the current mitigation). Tracked separately
  (`DATA-FUTURE-EARNINGS-CAL-PIT`).

## Acceptance criteria

1. A full scan runs with **0 `eod/` calls** when the DB is warm (only the current-day bar
   + gap-fills hit EODHD).
2. `walk_forward_v2.py` over 20yr completes with **0 EODHD calls** (reads `daily_bars`).
3. Parity check: DB bars match the prior `cache/eodhd` bars within float tolerance for a
   100-ticker sample (no silent adjustment drift).
4. Daily incremental keeps the store current at **≤2 EODHD calls/day**.

## Unblocks

- **Free, repeatable walk-forward** → confirm/reject the staged BE-in-choppy demote
  (`project_history_audit_2026_06_08`) and every future accuracy tweak without EODHD cost.
- **Audit #1 survivorship** (Phase 6) — honest backtests on point-in-time membership +
  delisted history.
- Permanently removes the morning OHLCV quota burn.
