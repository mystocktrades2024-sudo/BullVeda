# SMC Sub-Tab — How to Read It

**For:** Vinod (and any tester) — open any ticker in https://trade.mystockholding.com/kairos.html, switch to the **💎 SMC** sub-tab.

**Design intent:** mechanism-honest. Most public SMC content over-promises. This view shows the same patterns retail traders watch (order blocks, FVGs, breakers, BSL/SSL liquidity, premium/equilibrium/discount) but every empirical claim is bounded by a **Wilson 95% lower-confidence bound** computed from this ticker's last 6 months of price action. If the lower bound is below the breakeven win rate (~35% on 3:1 R:R), the pattern barely works standalone — and the UI says so.

---

## Page layout (top to bottom)

### 1. Hero banner
- Ticker, last price, regime badge.
- KPIs: nearest zone distance, dealing-range quartile (Q1–Q4), pending point-of-interest countdown.

### 2. Decision card (4 columns)
- **WHY** — the mechanism for this ticker right now (e.g., "Bull OB at $X.XX — institutional reload zone").
- **ENTER WHEN** — exact tag price + confirmation rule (e.g., "tag $X.XX then close above $Y").
- **EXIT WHEN** — invalidation level (close below zone bottom).
- **SIZE** — Wilson-LB-adjusted size guidance. If LB < breakeven, this reads "informational only — do not size off this alone."

### 3. Range quarters (Q1 / Q2 / Q3 / Q4)
- Finer than the classic Premium / Equilibrium / Discount split.
- Q1 = bottom 25% of 60-day range (deep discount), Q4 = top 25% (deep premium).
- Direction bias: longs in Q1/Q2, shorts in Q3/Q4, no edge in mid-range.

### 4. Chart panel (Price / RSI / MACD / Volume tabs)
- Built on TradingView lightweight-charts.
- TF toggle: **1H · 4H · DAILY · WEEKLY**.
  - 1H and 4H tabs require intraday bars. Top-250 qualified tickers each scan have them (post 2026-05-17 cap increase). If a ticker's tab falls back to daily, that ticker wasn't in the top-250 qualified set this scan.
- Zones overlaid as colored boxes; structure events (BoS / CHoCH) as labeled markers.

### 5. Ten detail sections — read each as "this pattern, this ticker, here's the historical edge"

| Section | What it shows | Wilson LB to look for |
|---|---|---|
| **Multi-TF Order Block Layering** | Bull/bear OBs across Daily/4H/1H — stacking implies institutional confluence | OB WL on this ticker; flag must be ≥ INSTITUTIONAL_FLOOR (n≥30) |
| **Inducement Liquidity** | BSL above swing high / SSL below swing low — where stops cluster | Distance to nearest sweep; price below SSL = stop-hunt likely first |
| **Volume Profile (HVN / LVN / POC)** | High-volume nodes = magnets; LVNs = fast-traverse zones | POC location relative to current price |
| **Range State** | Current premium/equilibrium/discount | Position-bias map |
| **POI Countdown** | Nearest unfilled zone & expected tag date | Time to tag based on average daily range |
| **Macro Confluence** | SPY/QQQ regime alignment, sector RS, IV percentile | Confluence count (more = stronger setup) |
| **FVGs (Fair Value Gaps)** | Unfilled gaps — magnets for price | FVG WL on this ticker |
| **Breaker Blocks** | Failed OB that flipped polarity | Brk WL on this ticker |
| **Structure events (BoS / CHoCH)** | Most recent break-of-structure or change-of-character | Trend direction confirmation |
| **Sample-size badges** | Every Wilson LB is tagged with one of: |  |

### Sample-size flags (look for these next to every win-rate)

| Flag | Meaning | How to read |
|---|---|---|
| `INSTITUTIONAL_FLOOR` | n ≥ 30 trades | Statistically usable — trust the Wilson LB |
| `BELOW_FLOOR` | 10 ≤ n < 30 | Directional but noisy — halve size or wait for more data |
| `INSUFFICIENT` | n < 10 | Don't trade off this number — treat as informational |

**Breakeven win rate**: on a 3:1 R:R trade plan, you break even at 25% WR. With slippage + commissions, real breakeven is closer to 30–35%. So a Wilson LB below ~35% means the pattern barely works standalone for this ticker.

---

## What the win rates have been showing (sample, 2026-05)

After backfilling 82 tickers, most Bull Order Blocks land **below 35% breakeven** on their own. Best performers:

| Ticker | OB WL | n |
|---|---|---|
| ICE | 41.0% | n ≥ 30 |
| NTRS | 39.0% | n ≥ 30 |
| SBAC | 38.6% | n ≥ 30 |

That confirms the mechanism-honest framing: **crowded retail SMC patterns barely beat breakeven standalone**. Edge comes from stacking confluence (multi-TF OB + range quarter + macro alignment + volume profile), not from any single zone.

---

## Known limitations

1. **1H/4H tabs**: only fetched for top-250 qualified tickers per scan. Lower-ranked tickers show daily fallback.
2. **Hit-rate horizon**: 10 trading days. Longer holds use different statistics — don't apply these WLs to a 30-day swing.
3. **Wilson LB is a floor, not a forecast**. The true win rate could be higher; the LB is the most pessimistic value consistent with the observed sample at 95% confidence.
4. **No survivorship adjustment yet** on hit-rate cache. Tickers delisted in the 6mo window aren't in the sample. Live tickers only.

---

## Reporting bugs back

When something looks wrong, capture:
1. Ticker symbol
2. Sub-section that's broken (e.g., "Decision card SIZE row is blank")
3. Browser console log if any errors
4. Whether 1H tab loaded real candles or fell back to daily

Send to Phani or drop into the same channel.

---

**Updated:** 2026-05-17 · Backed by `smc_engine.py` + `data/smc_hit_rates.json` (82 tickers cached, expanding nightly).
