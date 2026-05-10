"""
diagnose_as_of_membership.py — B1 root-cause investigation.

Hypothesis: --as-of-membership returns an as-of-date universe of historical
S&P 500 members, but many of those tickers have NO OHLCV parquet (delisted
companies like FRC, SIVB, BBBY). The backtest silently skips them. Then
min_score / min_rs filters reject the rest. Net: 0 BUYs.

This script tests the hypothesis WITHOUT running a full backtest.
Run: python3 diagnose_as_of_membership.py
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parent
OHLCV_DIR = ROOT / "data" / "ohlcv"

os.environ["AS_OF_MEMBERSHIP"] = "1"

print("=" * 70)
print("B1 diagnostic — --as-of-membership universe vs OHLCV cache")
print("=" * 70)

# 1. List of ticker symbols we have OHLCV for
ohlcv_tickers = {p.stem for p in OHLCV_DIR.glob("*.parquet")}
print(f"\nOHLCV cache: {len(ohlcv_tickers):,} ticker parquets")

# 2. Get the as-of universe for a 2024 date (in the middle of the 750d window)
from data_fetcher import get_universe_as_of
as_of = "2024-01-15"
universe = get_universe_as_of(as_of, include_r1000=True, include_custom=True)
print(f"\nas-of {as_of} universe: {len(universe):,} tickers")
print(f"  First 10: {universe[:10]}")

# 3. Intersection — how many AS-OF tickers actually have OHLCV?
with_data = [t for t in universe if t in ohlcv_tickers]
without_data = [t for t in universe if t not in ohlcv_tickers]
print(f"\n  WITH parquet data: {len(with_data):,} ({len(with_data) / max(len(universe), 1) * 100:.1f}%)")
print(f"  WITHOUT data:      {len(without_data):,} ({len(without_data) / max(len(universe), 1) * 100:.1f}%)")
print(f"  First 10 missing: {without_data[:10]}")

# 4. Same check for a recent date (where current+historical should overlap fully)
universe_now = get_universe_as_of("2025-12-01", include_r1000=True, include_custom=True)
with_data_now = sum(1 for t in universe_now if t in ohlcv_tickers)
print(f"\nas-of 2025-12-01 universe: {len(universe_now):,} tickers, {with_data_now} with OHLCV ({with_data_now / max(len(universe_now), 1) * 100:.1f}%)")

# 5. Now what does the BACKTEST do with the union of monthly snapshots?
# backtest.py line 743-748 unions monthly snapshots across the test window.
# Reproduce that union for a 250d test window ending 2026-03-19:
from datetime import date, timedelta
end = date(2026, 3, 19)
start = end - timedelta(days=int(250 * 1.45))
all_tickers: set = set()
cur = start.replace(day=1)
while cur <= end:
    all_tickers.update(get_universe_as_of(cur.isoformat(), include_r1000=True, include_custom=True))
    if cur.month == 12:
        cur = cur.replace(year=cur.year + 1, month=1)
    else:
        cur = cur.replace(month=cur.month + 1)
union_universe = sorted(all_tickers)
union_with_data = [t for t in union_universe if t in ohlcv_tickers]
print(f"\nUnion-of-monthly-snapshots universe ({start.isoformat()} → {end.isoformat()}):")
print(f"  Total:              {len(union_universe):,}")
print(f"  WITH parquet data:  {len(union_with_data):,} ({len(union_with_data) / max(len(union_universe), 1) * 100:.1f}%)")
print(f"  WITHOUT data:       {len(union_universe) - len(union_with_data):,}")

# 6. Compare to NON-as-of universe (current S&P 500 + R1000 + custom)
del os.environ["AS_OF_MEMBERSHIP"]
from data_fetcher import get_sp500, get_russell1000
sp500_now = get_sp500() or []
r1000_now = []
try:
    r1000_now = get_russell1000() or []
except Exception:
    pass
current_universe = sorted(set(sp500_now) | set(r1000_now))
current_with_data = sum(1 for t in current_universe if t in ohlcv_tickers)
print(f"\nCURRENT (today) universe: {len(current_universe):,} tickers, {current_with_data} with OHLCV ({current_with_data / max(len(current_universe), 1) * 100:.1f}%)")

# 7. Verdict
print("\n" + "=" * 70)
if len(union_with_data) < 100:
    print("✗ HYPOTHESIS CONFIRMED: AS-OF universe has <100 tickers with OHLCV.")
    print("  The backtest is starved of testable data.")
elif len(union_with_data) / max(len(union_universe), 1) < 0.5:
    print("⚠ HYPOTHESIS PARTIAL: many AS-OF tickers lack OHLCV; backtest may")
    print("  be working with a thinned universe but not zero.")
else:
    print("? HYPOTHESIS NOT CONFIRMED: AS-OF universe has plenty of OHLCV-backed tickers.")
    print("  The 0-BUYs bug is somewhere else (filter / scoring / regime).")
print("=" * 70)
