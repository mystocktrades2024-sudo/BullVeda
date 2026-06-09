# SwingTrade — Universe & Data-Loading Strategy

**Status:** Analysis / proposal · **Date:** 2026-06-09 · **Owner:** phanirajgarimella
**Scope:** Universe assembly (all defined sources + track-record + portfolio), a tiered rate-budgeted loader, and a consolidation of the ~60-job cron fleet.

> **One-line thesis:** Listing and price-ranking the *entire* ~3,500-name universe costs **~150 EODHD units (0.15% of daily budget)**. The cost was never the universe size — it is **deep-enrich depth**, which a tiered loader controls explicitly. The two real defects are (1) the track-record guarantee misses 2 of 3 outcome stores, and (2) ~5 nightly jobs re-walk the same universe with no per-minute coordination.

---

## 1. Target Universe

The universe is the union of the defined index sources plus everything we have ever signaled or held:

| Source | Builder | EODHD index / endpoint | ~count | List cost (units) |
|---|---|---|---|---|
| S&P 500 | `get_sp500()` | `fundamentals/GSPC.INDX` | 500 | 10 |
| Russell 1000 | `get_russell1000()` | `fundamentals/RUI.INDX` | 1,000 | 10 |
| Russell 2000 | `get_russell2000()` | `fundamentals/RUT.INDX` | 1,960 | 10 |
| Russell 3000 | *add `get_russell3000()`* | `fundamentals/RUA.INDX` | 3,000 | 10 |
| NASDAQ (liquid) | `get_nasdaq_all()` | `exchange-symbol-list/NASDAQ` + `bulk_eod` | ~1,000 | 101 |
| S&P MidCap 400 | `get_sp_midcap_400()` | `fundamentals/MID.INDX` | 400 | 10 |
| S&P SmallCap 600 | `get_sp_smallcap_600()` | `fundamentals/SML.INDX` | 600 | 10 |
| **Track record** | *from `audit_ledger`* | local JSON | **832** | 0 |
| **Portfolio** | `portfolio_state.json` | local JSON | 41 | 0 |

**Russell 3000 ≡ Russell 1000 ∪ Russell 2000.** Both are already fetched, so R3000 is already covered; adding `RUA.INDX` only provides one authoritative list. After de-dup, the **net distinct universe ≈ 3,200–3,600 names**.

**Total cost to LIST the entire universe: ~51 units** (index getters are billed on the `fundamentals` class @ 10 units each; `exchange-symbol-list` @ 1 unit; track-record/portfolio are local).

---

## 2. The Five-Layer Cost Model

The cost of "pulling all tickers" scales with **enrich depth**, not universe size:

| Layer | What it does | Cost driver | Cost for all ~3,500 |
|---|---|---|---|
| **0 — Universe** | assemble the ticker list | index@10 ×5–7 + exch@1 | **~51 units** |
| **1 — Price/Rank** | last-day OHLCV for *everything* | **1× `bulk_eod(US)`** | **100 units** |
| **2 — History** | full OHLCV for survivors | `eod`@1 each (archive-first) | hundreds (delta only) |
| **3 — Deep-enrich** | ~14 endpoints, shortlist only | **`fundamentals`@10** dominates | shortlist × ~26 units |
| **4 — Structural** | EW + 4H confluence targets | Schwab 100/min | shortlist × ~6 |

**Layers 0–1 score the entire universe for ~150 units (≈0.15% of the 100K/day budget).** Everything expensive is gated behind the Layer-3 shortlist.

### Why bulk_eod is the highest-leverage primitive
`eod-bulk-last-day/{EXCHANGE}` returns the last bar for **every ticker on an exchange in one call, billed at 100 units**. Per-ticker `eod` for the same ~4,800 names = ~4,800 units. Bulk is **~48× cheaper** for the price/rank pass. (Caveat: bulk returns *last day only*; full history still needs per-ticker `eod` — which the local Parquet archive already serves as a delta cache.)

---

## 3. Track-Record + Portfolio Guarantee

**Goal:** every ticker we have ever signaled or held stays in the scan + bypasses the enrich cap *forever*, so its forward outcomes keep resolving even after it drops off the liquid list.

### The three outcome stores

| Store | Path | Distinct tickers | Canonical for |
|---|---|---|---|
| `picks_history.json` | `cache/` | 482 | tracker feedback / setup-family WR |
| `signal_log.json` | `data/` | 791 | diagnostic journal (incl. WATCH), kill-list, Audit tab |
| `audit_ledger.json` | `cache/` + `infra/prototype/` | **832** | **canonical superset** (merge of the above + resolved D/W/M returns) |
| `portfolio_state.json` | `data/` | 41 | real paper P&L (Alpaca) |

`audit_ledger` (832) = the exact union of `picks_history` + `signal_log`, with forward returns resolved. It is the canonical "every ticker we ever signaled" list.

### The defect
`always_include` (in `swing_trade.py:899-940`) — which bypasses **both** the liquidity filter (`:1128`) **and** the enrich cap (`:1758`) — is built from **`picks_history` (482) + `portfolio_state` (41)** only. It does **not** read `signal_log` or `audit_ledger`, so **~310 historically-signaled tickers are not guaranteed re-scanned** and can stop resolving outcomes.

### The fix (~5 lines)
Source `always_include` from **`audit_ledger` (832) ∪ `portfolio_state` (41)** — the canonical union. Permanent track-record + portfolio guarantee. Cost is ~0 (cap bypass, but those names are price-filtered only when they also fail liquidity, which is the intended behavior).

---

## 4. The Tiered Loader

Replace the scattered cache-warmers with **one orchestrated nightly data-load pipeline**, sequenced under an explicit per-minute + daily budget:

```
NIGHTLY DATA-LOAD  (single job, ~02:00–04:30 PT, budget-owned)
 1. Universe assemble  SP500 ∪ R1000 ∪ R2000 (∪ RUA) ∪ NASDAQ-liquid
                        ∪ audit_ledger(832) ∪ portfolio(41)                    ~51 u
 2. Bulk price         1× bulk_eod(US) → rank all ~3,500 by $-volume           100 u
 3. History delta      archive-first (1,544 Parquet files);
                        EODHD only for missing/stale bars                       ~hundreds u
 4. Prescreen          score all in-memory (0 API);
                        shortlist = top-N ∪ guaranteed(track-record ∪
                        portfolio ∪ index-core ∪ earnings/PEAD window)          0 u
 5. Deep-enrich        shortlist only, ~14 endpoints,
                        paced < 950/min EODHD + 100/min Schwab                  shortlist × ~26 u
 6. Structural + SMC    ONE merged pass (was 2 jobs);
                        weekly/monthly bars via Schwab to spare EODHD           shortlist × ~6
```

### Three efficiency wins
1. **Archive-first for history** — the 1,544 local Parquet files (`data/ohlcv/*.parquet`) already hold full history. Fetch only the daily *delta* from EODHD instead of re-pulling history. (Today the archive is only a *failover* tier; promote it to primary for history.)
2. **Schwab for structural weekly/monthly** — `get_pricehistory(frequency_type=weekly|monthly)` is free; routing the structural engine's per-symbol bars Schwab-first removes ~3K/day off the EODHD quota (per-symbol anyway, no bulk benefit lost).
3. **Merge the duplicate structural passes** — `precompute-prewarm` (target_engine) and `precompute-patterns` (SMC+risk) walk the same ~1,500 tickers and bars; one pass serves both.

### Budget verification
```
Universe + bulk            ~150 u
History delta              ~300–800 u   (archive serves the rest)
Deep-enrich 1,000 × ~26    ~26,000 u
Structural (Schwab-heavy)  ~2,000 u EODHD + Schwab
                           ─────────
TOTAL                      ~28K–29K units  vs 95K soft-limit  →  ~66K headroom
```
Throughput: deep-enrich 1,000 ≈ **~9.5 min EODHD / ~15 min Schwab**; structural ≈ **~30 min Schwab-bound**. Whole load completes well before the 06:30 scan.

---

## 5. Job Fleet — Current State

~60 `com.swingtrade.*` launchd agents. Functional clusters and the redundancy findings:

### Redundancy (the consolidation targets)
- **5 nightly jobs re-walk the same universe fetching the same bars:** `enrich-nightly` (02:15, ~3K EODHD), `archive-sync` (04:00), `precompute-prewarm` (03:00), `precompute-patterns` (07:15), `insider-cluster-weekly` (~3K).
- **Structural precompute split into two jobs** over the same 1,500 tickers/bars (`precompute-prewarm` + `precompute-patterns`).
- **Audit ledger built 4×/day** (`audit-ledger-eod` + `audit-ledger-intraday` ×3), each re-fetching the same forward-return prices.
- **Schwab options polled by 4 jobs** (`optionsflow` 15-min, `options-exit` 30-min, `ivsnapshot`, `options-buy`).
- **Two AM reporting jobs** read the same scan output (`morning-briefing` + `daily-newsletter-morning`).

### Pre-market collision risk (00:00–06:30 PT)
10 EODHD-hitting jobs fire 02:15–05:45 **with no per-minute coordination** — the HEAVY-job guard (`guard_heavy_job.sh`) keys only on **load average > 8 / scan-running**, *not* on the EODHD 950/min or daily quota. Highest risk: the 05:15 heavy scan still running while `corporate-events`, `earnings`, `premarket-scan`, `beatpredict`, `thematic-daily` all fire — the densest EODHD window.

---

## 6. Proposed Job Architecture — ~9 Pipelines

Collapse the sprawl into budget-sequenced, dependency-ordered pipelines:

| # | Pipeline | Absorbs | When (PT) |
|---|---|---|---|
| 1 | **Universe-Layers** | thematic, insider-cluster, congressional, membership | 01:30 |
| 2 | **Data-Load** (the §4 loader) | enrich-nightly, archive-sync, precompute-prewarm, precompute-patterns, time-anatomy | 02:00 |
| 3 | **Scan** | the `daily` heavy run | 05:00 (after load) |
| 4 | **Catalysts** | earnings → earnposcheck → beatpredict → beatalert | 05:30 |
| 5 | **Reporting-AM** | morning-briefing + daily-newsletter (merged) | 06:30 |
| 6 | **Options/IV** (Schwab, in-session) | optionsflow, options-exit, ivsnapshot, options-buy | session |
| 7 | **Portfolio** (paper) | executor, fill, portfolio-sync, positionwatch | session |
| 8 | **ML** | predict, close-loop → accuracy, retrain, drift | eve/weekly |
| 9 | **Reporting-PM + Audit** | eod-summary, audit-ledger (1×), digests, diagnostics | EOD/weekly |

**Keep as-is:** free-source jobs (congress, retail-sentiment, x-signal, edgar-fundamentals) and infra (server, tunnel-healthcheck, uptime-ping, schwabtoken, supabase-sync, eodhd-quota-snapshot, dq-checks).

**Add:** one **budget owner** so the pre-market pipelines (1→2→3→4) run strictly in dependency order rather than colliding on 950/min.

---

## 7. Phased Build Plan

| Phase | Work | Risk | Effort |
|---|---|---|---|
| **P0 — Quick wins** | (a) `get_russell3000()` (RUA.INDX); (b) track-record guarantee → `always_include` from `audit_ledger ∪ portfolio`; (c) merge the two structural precompute jobs | Low | ~1 day |
| **P1 — Tiered loader** | Promote archive to history-primary (delta-only EODHD); Schwab-first for structural weekly/monthly; single Data-Load pipeline | Med | 2–3 days |
| **P2 — Budget owner** | Cross-job pre-market sequencer honoring 950/min + daily quota | Med | 1–2 days |
| **P3 — Fleet consolidation** | Collapse ~60 agents → 9 pipelines; retire redundant plists | Med | 2–3 days |

Each phase is independently shippable and reversible (config-flagged where it touches scan behavior).

---

## Appendix A — Rate Limits & Billing

**EODHD** (`eodhd_client.py`): `_RATE_PER_SEC=17`, `_RATE_PER_MIN=950`, `_RATE_PER_DAY=95,000` (sliding-window token buckets, cross-process shared via `cache/_ratelimit_shared.json` + flock). Billed-unit quota guard (`config.eodhd_quota`): `daily_limit=100,000`, `soft_limit=95,000`, `throttle_pct=85` (→ `SCAN_MODE=light`), `abort_pct=97` (→ skip scan).

**Billing weights** (units/request): `eod`/`news`/`splits`/`dividends`/`real_time`/`exchange_symbols`/`calendar`/`sentiment` = **1**; `intraday`/`technical`/`screener` = **5**; `fundamentals`/`options` = **10**; `eod-bulk-last-day` = **100**.

**Schwab** (`schwab_client.py`): ~100/min (`_MIN_GAP_S=0.55`), 429 backoff; **no daily cap**. `get_pricehistory` supports daily/weekly/monthly/minute. Used as failover (EODHD → Schwab → archive) and sole intraday/4H source.

## Appendix B — Throughput Math

- Last-day OHLCV, all ~4,800 US: **1 bulk call, ~4s, 100 units.**
- Per-ticker full history, 4,800: 4,800 ÷ 950/min = **~5 min**, 4,800 units.
- Deep-enrich N=1,000: ~9,000 EODHD req ÷ 950 = **~9.5 min** (~26K units) + Schwab ~15 min.
- Structural-prewarm N=1,500 × 3 modes: ~9K EODHD + ~3K Schwab → **~30 min Schwab-bound** (serial today; parallelizable).

## Appendix C — Key File References

- Universe builders: `data_fetcher.py:369–474`
- Scan assembly + filters: `swing_trade.py:723–1156`
- Two-stage enrich cap: `swing_trade.py:1670–1836` (`max_enrichment_tickers=1000`, `deep_enrichment_top_n=500`)
- Track-record guarantee: `swing_trade.py:899–940`
- Rate limiter + quota guard: `eodhd_client.py:142–303, 468–479, 603–672`
- Structural engine: `target_engine.py:50–123, 1683–1779`; `scripts/precompute_targets.py`
- Local archive: `data_archive.py` (1,544 Parquet files in `data/ohlcv/`)
- Audit ledger builder: `infra/prototype/build_audit_ledger.py`
