# TradingView × SwingTrade — bridge prototype

**Status:** prototype / proof-of-concept (2026-06-07). Not wired into the live pipeline.
**Constraint-safe:** drives your logged-in TradingView Desktop app over Chrome DevTools Protocol
(CDP). No new data license, no scraping. EODHD stays the single source for scoring — TV is a
**visual / authoring layer only**.

Open `art_of_the_possible.html` in a browser for the full capability tour.

---

## What this is

A two-way bridge: Claude can **read** what's on a TradingView chart (symbol, timeframe, studies,
drawings, quote) and **write** onto it (horizontal lines, boxes, text, Pine, replay). It inherits
your paid plan + LuxAlgo Premium because it automates the app you're already logged into.

The underlying bridge is the community project
[`tradesdontlie/tradingview-mcp`](https://github.com/tradesdontlie/tradingview-mcp) (78 tools).
This folder adds SwingTrade-specific glue.

## Files

| File | What |
|---|---|
| `art_of_the_possible.html` | Standalone showcase — proven-live vs buildable vs guardrails. |
| `push_levels.mjs` | Reads `cache/target_engine/{TICKER}_{MODE}.json`, opens its own scratch chart, draws entry/stop/T1/T2 + screenshots. |
| `find_and_push.mjs` | Same draw logic but finds an **already-open** chart by symbol (use when you opened the tab by hand). |
| `shots/` | Screenshots captured by the scripts. `proof_live_lines.png` = real bridge-drawn lines on a live chart. |
| `node_modules` | Symlink → `~/tradingview-mcp/node_modules` (so the `.mjs` scripts resolve `chrome-remote-interface`). |

## Setup

```bash
# 1. install the bridge (one time)
git clone https://github.com/tradesdontlie/tradingview-mcp.git ~/tradingview-mcp
cd ~/tradingview-mcp && npm install

# 2. launch TradingView with the CDP debug port
~/tradingview-mcp/scripts/launch_tv_debug_mac.sh        # → CDP @ localhost:9222

# 3. verify
cd ~/tradingview-mcp && node src/cli/index.js status
```

## Usage

```bash
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

# push levels onto a fresh scratch chart (swing=1D, position=1W, invest=1M)
node infra/prototype/tv_bridge/push_levels.mjs NEM swing

# OR: you opened a tab by hand and typed the ticker — find it by symbol & draw
node infra/prototype/tv_bridge/find_and_push.mjs NEM swing
```

For a persistent Claude Code session, register the MCP instead (recommended — see gotchas):

```bash
claude mcp add tradingview -- node ~/tradingview-mcp/src/server.js
# then in chat:  use tv_health_check
```

## Gotchas learned building this

1. **First-tab targeting.** The bridge CLI spawns a fresh process per call and connects to the
   *first* `tradingview.com/chart` target from `/json/list`. Order is **not stable across processes**,
   so `state` and `screenshot` can hit different tabs — and commands can land on a **saved layout** you
   didn't intend to touch.
   - *Mitigation:* `push_levels.mjs` / `find_and_push.mjs` connect **once** and pin a single target id.
   - *Better:* use the long-running **MCP server** — it holds one stable target for the whole session.

2. **CDP target IDs rotate** on navigation/reload in this Electron build, so diffing IDs before/after
   to find a "new" tab is unreliable. `find_and_push.mjs` matches by **symbol** instead.

3. **`Cmd+T` is swallowed.** Programmatic new-tab (`Input.dispatchKeyEvent`) does nothing in this TV
   build, so a scratch chart must be opened by hand. `push_levels.mjs` attempts it and fails loudly;
   prefer `find_and_push.mjs` after opening a tab yourself.

4. **Horizontal lines need a time anchor.** `createShape` requires a finite `point.time`
   (unix seconds) even for a full-width horizontal line — pass `Math.floor(Date.now()/1000)`.

5. **Restoring a chart you modified** (if you ever write to a saved layout):
   ```js
   api = window.TradingViewApi._activeChartWidgetWV.value()
   api.removeEntity('<entity_id>')      // per drawn shape
   api.setSymbol('BATS:BTDR', {})       // restore original symbol
   api.setResolution('240', {})         // restore original timeframe
   ```

## Guardrails (per CLAUDE.md)

- **Never** route TV quotes / screener / indicators into the 5-pillar scoring path. EODHD is the single
  source of truth.
- This is an **unofficial** community bridge — subject to TradingView's Terms of Use.
- Don't write to charts the user didn't authorize; pin a scratch target.
