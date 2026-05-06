# Prompt: Build an SMC Multi-Timeframe Analysis Matrix

## What To Build

Build a **Smart Money Concepts (SMC) multi-timeframe analysis matrix** — a dense, scannable table where each **row is a timeframe** (30m, 1H, 4H, 1W, 1M) and each **column is an indicator**. The user enters a ticker and instantly sees the structural, momentum, and flow picture across all timeframes in one view.

This is for swing trading (2–10 day holds). The matrix helps the trader:
1. Confirm multi-timeframe alignment before entry
2. Spot structure breaks (CHoCH/BOS) on higher timeframes
3. Find unfilled Fair Value Gaps as entry zones
4. Detect liquidity sweeps and order block levels
5. See squeeze/momentum/divergence confluence at a glance

---

## Indicator Definitions & Calculations

### Table 1: Structure & Liquidity

| Column | Definition | Calculation |
|--------|-----------|-------------|
| **Rating** | Overall bias for this timeframe | Composite of trend + structure + momentum. Show as: `Strong Bullish`, `Bullish`, `Neutral`, `Bearish`, `Strong Bearish` with color coding |
| **Structure** | Market structure state | Detect swing highs/lows using N-bar pivots (default N=5). **BOS (Break of Structure):** price breaks the most recent swing high (bullish) or swing low (bearish) in the direction of the trend. **CHoCH (Change of Character):** price breaks a swing point *against* the prevailing trend — signals potential reversal. **Range:** no clear break in either direction. Show: `BOS (5)` = bullish BOS with strength count, `CHoCH` = character change, `Range` |
| **Order Block** | Last institutional supply/demand zone | Find the last opposing candle before an impulse move (3+ candles in one direction with total body > 2× ATR). **Bullish OB:** last red candle before a bullish impulse. **Bearish OB:** last green candle before a bearish impulse. Show: `Inside` (price is inside OB zone), `Outside` (price is above/below), `Mitigated` (OB already tested and broken) |
| **OB Volume** | Volume at the order block candle | Raw volume of the OB candle. Color green if above 20-period average, red if below. Format: `227.74K`, `1.2M` |
| **FVG** | Fair Value Gap (imbalance zone) | 3-candle pattern: candle[0].high < candle[2].low (bullish FVG) or candle[0].low > candle[2].high (bearish FVG). Show: `Bullish` (unfilled gap below price), `Bearish` (unfilled gap above price), `Mitigated` (gap filled), `None` |
| **P&G Zones** | Premium & Discount zones relative to range | Calculate the 50% level of the current swing range (swing low to swing high). **Premium:** price > 50% (expensive, look to sell). **Discount:** price < 50% (cheap, look to buy). **Equilibrium:** price near 50%. Show: `Above Equilibrium`, `Below Equilibrium`, `At Equilibrium` |
| **Liquidity** | Liquidity grab / sweep detection | Detect price wicking beyond a key level (swing high/low, equal highs/lows) and closing back inside. **Sweep:** wick exceeded level by > 0.2× ATR then reversed. **Grab:** similar but intrabar (wick only, no close beyond). Show: `Bearish` (swept highs = liquidity taken from longs), `Bullish` (swept lows), `None` |
| **EQH/EQL** | Equal Highs / Equal Lows clusters | Find 2+ swing highs within 0.3% of each other (EQH) or 2+ swing lows within 0.3% (EQL). These are liquidity pools. Show: `EQH` (equal highs = sell-side liquidity above), `EQL` (equal lows = buy-side liquidity below), `Both`, `None` |

### Table 2: Momentum & Flow

| Column | Definition | Calculation |
|--------|-----------|-------------|
| **Signal** | Directional momentum signal | Based on EMA crossover state: EMA8 crosses above EMA21 = `Bullish`, below = `Bearish`, flat = `Neutral`. Add strength: if EMA8 > EMA21 > EMA50 = `Strong Bullish` |
| **RSI** | Relative Strength Index | RSI(14). Show value + color: green > 50, red < 50, bright green > 70 (overbought), bright red < 30 (oversold) |
| **MACD** | MACD histogram direction | MACD(12,26,9). Show: `↑ Bullish` if histogram > 0 and rising, `↓ Bearish` if < 0 and falling, `Turning Up`/`Turning Down` for crossover zones |
| **Squeeze** | Bollinger Band inside Keltner Channel | **On:** BB(20,2.0) is inside KC(20,1.5) — compression, move coming. **Off:** BB expanded outside KC. **Firing:** Squeeze just released + momentum direction. Show: colored dot — red dot = squeeze on, green dot = squeeze off (fired bullish), gray = no squeeze. Plus momentum direction |
| **Money Flow** | Chaikin Money Flow | CMF(20) = sum of MF Volume / sum of Volume over 20 bars. MF Multiplier = ((close-low) - (high-close)) / (high-low). Show: `Inflow` (CMF > 0.05), `Outflow` (CMF < -0.05), `Neutral` |
| **Volume Sent.** | Volume sentiment vs average | RVOL = current volume / 20-period SMA of volume. Show: `High` (RVOL > 1.5), `Low` (RVOL < 0.7), `Normal`. Color green if price up + high vol, red if price down + high vol |
| **Divergence** | RSI vs Price divergence | **Bullish divergence:** price makes lower low but RSI makes higher low. **Bearish divergence:** price makes higher high but RSI makes lower high. Scan last 2 swing points. Show: `Bullish Div`, `Bearish Div`, `None`. Also check MACD histogram divergence as secondary confirmation |
| **Trend Str.** | Trend strength measurement | ADX(14). Show: value + label. `Strong` (ADX > 25), `Weak` (ADX < 20), `Moderate` (20-25). Color: green if trending strongly in EMA direction, orange if weak |
| **Reversals** | Reversal candle patterns | Detect: Engulfing (bull/bear), Pin Bar (hammer/shooting star), Morning/Evening Star. Look at last 3 candles. Show: `Bullish Engulf`, `Pin Bar ↑`, `Evening Star`, `None` |
| **Confluence** | Multi-signal alignment score | Count how many signals agree on direction: Structure + OB + FVG + Momentum + Flow. Score 1-5. Show: `Strong` (4-5 agree), `Moderate` (3), `Weak` (1-2), `Mixed` (conflicting). This is the most important column — bold it |

---

## UI / Visual Specification

### Layout: Dark Theme, Dense Table

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔍 [TICKER INPUT]  [ANALYZE]                            NEM  $42.15  │
│                                                          ▲ +1.23%     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─ STRUCTURE & LIQUIDITY ─────────────────────────────────────────┐   │
│  │ TF    │Rating        │Structure│Order Block│OB Vol │FVG      │..│   │
│  │───────│──────────────│─────────│───────────│───────│─────────│  │   │
│  │ 30m   │ — Neutral    │ Range   │ Outside   │204.5K │Mitigated│  │   │
│  │ 1H    │ — Neutral    │ BOS (1) │ Outside   │485.4K │ None    │  │   │
│  │ 4H    │ ▲ Bullish    │ CHoCH   │ Outside   │  3.0M │ None    │  │   │
│  │ 1W    │ ▲ Bullish    │ BOS (5) │ ▲ Up      │ 58.7M │ None    │  │   │
│  │ 1M    │ ▲▲Str.Bullish│ BOS (3) │ Inside    │245.2M │Bullish  │  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─ MOMENTUM & FLOW ──────────────────────────────────────────────┐    │
│  │ TF    │Signal   │RSI  │Squeeze│Trend Str.│Money Flow│Diverg. │..│   │
│  │───────│─────────│─────│───────│──────────│──────────│────────│  │   │
│  │ 30m   │ Neutral │45.1 │ ⚫    │ Moderate │ Neutral  │ None   │  │   │
│  │ 1H    │▲Bullish │52.8 │ 🟢    │ Moderate │ Inflow   │ None   │  │   │
│  │ 4H    │▲Bullish │61.4 │ ⚫    │ Strong   │ Inflow   │ None   │  │   │
│  │ 1W    │▲Bullish │65.7 │ 🟢    │ Strong   │ Inflow   │ None   │  │   │
│  │ 1M    │▲Bullish │58.3 │ ⚫    │ Strong   │ Inflow   │BearDiv │  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─ CONFLUENCE SUMMARY ───────────────────────────────────────────┐    │
│  │                                                                 │    │
│  │  HTF Bias (W+M):  BULLISH ▲   │  LTF Trigger(30m+1H): MIXED →│    │
│  │  Structure:  BOS on Weekly     │  Squeeze:  Firing on 1H 🟢   │    │
│  │  Key Level:  OB at $41.20      │  Risk:  CHoCH on 30m         │    │
│  │                                                                 │    │
│  │  ★ VERDICT: WAIT for LTF reclaim — HTF bullish but LTF weak   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Color Rules

| Element | Bullish | Bearish | Neutral |
|---------|---------|---------|---------|
| Rating text | `#00c853` (green) | `#ff1744` (red) | `#ffab00` (amber) |
| Structure badge | Green bg for BOS up | Red bg for BOS down, Orange for CHoCH | Gray for Range |
| Order Block | Green `Inside` (bullish OB) | Red `Inside` (bearish OB) | Dim for `Outside` |
| FVG | Green for bullish gap | Red for bearish gap | Gray for mitigated/none |
| RSI value | Green gradient > 50 | Red gradient < 50 | — |
| Squeeze dot | `🟢` fired bull, `🔵` fired bear | `🔴` squeeze ON | `⚫` no squeeze |
| Divergence | `#00e5ff` cyan for bullish div | `#ff6f00` orange for bearish div | Dim for none |
| Confluence | Bold green `Strong` | Bold red `Strong bear` | Orange `Mixed` |
| Row highlight | Light green tint on fully bullish rows | Light red tint on fully bearish rows | No tint |

### Row Styling

- **Font:** Aptos, monospace for numbers
- **Row height:** Compact — 32px per row, no padding waste
- **Timeframe column:** Fixed width, bold, slightly brighter text
- **Alternating row backgrounds:** Subtle (#1a1a2e / #16213e) for readability
- **Hover:** Row highlight with slight brightness increase
- **Header:** Sticky, darker background, uppercase small text
- **Table separation:** The two tables (Structure & Momentum) stacked vertically with a small gap
- **Confluence summary:** Card at the bottom with border-left accent color matching the overall bias

### Responsive Behavior

- On wide screens (>1200px): Tables side by side (2 columns)
- On medium screens (800-1200px): Tables stacked, full width
- On mobile (<800px): Horizontal scroll on tables, sticky TF column

### Navigation Arrows (from screenshot)

The screenshot shows `◀ 1 ▶` navigation arrows in the top-right. This allows cycling through multiple tickers if analyzing a batch. Include:
- Left/right arrows to cycle through a list of tickers
- Current position indicator (e.g., "3 of 12")
- Keyboard shortcuts: left/right arrow keys

---

## Confluence Summary Logic

The bottom card should synthesize the matrix into an actionable read:

```python
def compute_confluence_summary(matrix):
    """
    matrix: dict of timeframe -> dict of indicator values
    
    HTF = Weekly + Monthly (macro trend)
    ITF = 4H (swing timeframe)
    LTF = 30m + 1H (entry/trigger timeframe)
    """
    
    htf_bias = aggregate_bias(matrix["1W"], matrix["1M"])   # Weight: 40% — macro trend
    itf_bias = aggregate_bias(matrix["4H"])                 # Weight: 30% — swing timeframe
    ltf_bias = aggregate_bias(matrix["30m"], matrix["1H"])  # Weight: 30% — entry trigger
    
    # Confluence score: how many timeframes agree
    bullish_count = sum(1 for tf in matrix if matrix[tf]["rating"] in ["Bullish", "Strong Bullish"])
    bearish_count = sum(1 for tf in matrix if matrix[tf]["rating"] in ["Bearish", "Strong Bearish"])
    
    # Key findings
    findings = []
    
    # Structure breaks on HTF
    for tf in ["1W", "1M"]:
        if "BOS" in matrix[tf]["structure"]:
            findings.append(f"BOS on {tf}")
        if "CHoCH" in matrix[tf]["structure"]:
            findings.append(f"CHoCH on {tf} — potential reversal")
    
    # Squeeze firing
    for tf in matrix:
        if matrix[tf]["squeeze"] == "firing":
            findings.append(f"Squeeze firing on {tf}")
    
    # Divergences on HTF
    for tf in ["4H", "1W", "1M"]:
        if matrix[tf]["divergence"] != "None":
            findings.append(f"{matrix[tf]['divergence']} on {tf}")
    
    # Order block proximity
    for tf in ["1H", "4H", "1W"]:
        if matrix[tf]["order_block"] == "Inside":
            findings.append(f"Inside {tf} Order Block at ${matrix[tf]['ob_level']}")
    
    # FVG unfilled
    for tf in ["1H", "4H", "1W"]:
        if matrix[tf]["fvg"] in ["Bullish", "Bearish"]:
            findings.append(f"{matrix[tf]['fvg']} FVG unfilled on {tf}")
    
    # Verdict logic
    if htf_bias == "Bullish" and itf_bias == "Bullish" and ltf_bias == "Bullish":
        verdict = "BUY — Full alignment across all timeframes"
    elif htf_bias == "Bullish" and ltf_bias != "Bullish":
        verdict = "WAIT — HTF bullish but LTF not confirmed, wait for reclaim"
    elif htf_bias == "Bearish" and ltf_bias == "Bearish":
        verdict = "SHORT candidate — Full bearish alignment"
    elif htf_bias == "Bearish" and ltf_bias == "Bullish":
        verdict = "FADE RISK — Counter-trend bounce, not a swing entry"
    else:
        verdict = "NO TRADE — Mixed signals, wait for clarity"
    
    return {
        "htf_bias": htf_bias,
        "itf_bias": itf_bias,
        "ltf_bias": ltf_bias,
        "confluence_score": max(bullish_count, bearish_count),
        "findings": findings,
        "verdict": verdict
    }
```

---

## Data Requirements

For each timeframe, you need OHLCV bars:

| Timeframe | Lookback | Min Bars Needed | Source |
|-----------|----------|-----------------|--------|
| 30m | 15 days | 195 bars | Polygon intraday |
| 1H | 30 days | 195 bars | Polygon intraday |
| 4H | 60 days | 195 bars | Polygon intraday |
| 1W | 2 years | 104 bars | Polygon / yfinance |
| 1M | 5 years | 60 bars | Polygon / yfinance |

All indicators are computed from OHLCV — no external indicator feeds needed.

---

## Implementation Notes

1. **Fetch all 5 timeframes in parallel** using ThreadPoolExecutor — total fetch time should be < 2 seconds
2. **Cache aggressively** — 5-minute TTL for intraday (30m-1H), 30-minute for 4H, 24-hour for W/M
3. **Compute all indicators server-side** — return a flat JSON matrix to the frontend
4. **Frontend is pure HTML/CSS/JS** — no React/Vue, just template literals and DOM manipulation
5. **Color every cell** — the power of this view is instant pattern recognition through color, not reading text
6. **Swing high/low detection** uses N=5 pivots for HTF (W/M), N=3 for LTF (30m/1H) — configurable
7. **Order block detection** looks back max 50 candles — beyond that, OBs are likely mitigated
8. **FVG scan** looks back max 20 candles — only recent gaps are tradeable
9. **The confluence summary is the most valuable part** — it's the "so what" that tells the trader what to do

---

## Example API Response Shape

```json
{
  "ticker": "NEM",
  "price": 42.15,
  "change_pct": 1.23,
  "timeframes": {
    "30m": {
      "rating": "Bearish",
      "structure": "CHoCH",
      "order_block": "Outside",
      "ob_volume": 75370,
      "ob_level": 41.80,
      "fvg": "Mitigated",
      "pg_zone": "Above Equilibrium",
      "liquidity": "Bearish",
      "eqhl": "EQL",
      "signal": "Bearish",
      "rsi": 38.2,
      "macd": "Bearish",
      "squeeze": "on",
      "squeeze_momentum": "negative",
      "money_flow": -0.12,
      "money_flow_label": "Outflow",
      "volume_sentiment": "Low",
      "rvol": 0.65,
      "divergence": "None",
      "trend_strength": 15.3,
      "trend_strength_label": "Weak",
      "reversals": "None",
      "confluence": 2,
      "confluence_label": "Weak"
    },
    "1H": { ... },
    "4H": { ... },
    "1W": { ... },
    "1M": { ... }
  },
  "summary": {
    "htf_bias": "Bullish",
    "itf_bias": "Bullish",
    "ltf_bias": "Bearish",
    "confluence_score": 4,
    "findings": [
      "BOS on 1D",
      "Squeeze firing on 1H",
      "Bullish Divergence on 15m",
      "Inside 4H Order Block at $41.20"
    ],
    "verdict": "WAIT — HTF bullish but LTF not confirmed, wait for reclaim"
  }
}
```
