# Stocksmith — design baseline & update guide

`infra/prototype/Stocksmith.html` is the **live, served** page (runs in parallel with
`kairos.html`, fed by the same `/v2/*.json` bundle). This folder is the **design baseline**:
the verbatim Claude-Design source the page was built from, kept here so future design
updates can be diffed and re-applied cleanly. Nothing here is served.

Baseline captured: 2026-05-28 · from the "SwingTrade Terminal" Aurora-Glass handoff.

## How updates propagate

| Change type | Effort | How |
|---|---|---|
| **CSS / visual** (color, spacing, new component style, theme) | one command | overwrite the `.css` here → `python3 design/stocksmith/build_stocksmith.py` |
| **Structure** (new card, reorder, new tile) | small port | diff new `src/*.jsx` vs this baseline → copy markup into Stocksmith.html |
| **New data field** | small port + wire | as above, then map the field to a real `/v2` source (FIELD_MAP below) |

Class names in the live page are identical to the design, so CSS changes never need
hand-editing — only re-injection.

## FIELD_MAP — every Home value's real source

Live page binds to `/v2/data.critical.json` (+ sidecars + `/api/news`). Mock data
in the design's `src/data.jsx` and `src/home.jsx` is NOT used.

| Home module (home.jsx) | Live source in Stocksmith.html |
|---|---|
| Hero funnel RANKED/BUY/WATCH/AVOID | `data.critical.json` · `scan_count` / `buy_count` / `watch_count` / `killed_count` |
| Regime · Tape | `regime.regime4`, `regime.vix`, `market_breadth.pct_above_50d`, `regime.max_size_pct` |
| Market Mood (6) | `macro_signals` (risk_signal, put_call.equity_pc, credit.state, dxy.trend) · `market_breadth` · `regime.vix` |
| Index strip (10) | `sector_etf._indices` (QQQ/DIA/IWM/TLT), `sector_etf.SPY`, `sector_etf._ext_macro` (uso/smh), `macro_signals` (gld/dxy), `regime.vix` |
| Top setups | `elite_picks.Swing.BUY` + `.WATCH` → ticker, score_raw, snapshot.{rr,p_target,p_stop}, stage |
| Discovery · 52W HIGH | `data_screener.json` · price ≥ 0.97×`week52_high` |
| Discovery · SQUEEZE | `data_screener.json` · `squeeze_on` |
| Discovery · INSIDER | `data_screener.json` · `insider_buys`>0 & `insider_sells`=0 |
| Discovery · UOA | `data.critical.json` · `options_flow_top30` (status/uoa_calls/put_call_ratio) |
| Discovery · EMERGING | `data_screener.json` · cap_bucket Small/Mid × stage BUY/WATCH × rs_rank |
| Top movers | `data.critical.json` · `market_movers.gainers/losers` (perf_1d is a fraction → ×100) |
| Earnings today | `data_earnings.json` · `earnings_watchlist` (days_to_earnings=0) + `earnings_beat_predictions` + `portfolio.positions` cross-ref |
| Top stories | **live** `/api/news?t=…` (EODHD) for `_news_top_tickers`; sentiment from screener `sent_score` |
| Overnight signals | `data_screener.json` (stage=BUY, insider clusters) + `setup_drift_alerts` + bundle event |
| Account menu NAV/cash | `data.critical.json` · `portfolio.equity` / `portfolio.cash` / `portfolio.positions` |

## User Management (Admin · added 2026-05-28)
Design: `src/surface-users.jsx` + `surface-users.css`. Two views: **Users & Tiers**
(table + tier-count cards + add/edit/delete modal) and **Tier Access · Configure**
(per-surface/lens min-tier pills). Wired in Stocksmith.html to the REAL backend:

| Field / action | Real source |
|---|---|
| User list | `GET /api/users` → `auth.list_users()` (display_name, email, role, last_login, disabled, is_owner) |
| Role / tier dropdown | `GET /api/roles` — design tiers map 1:1 to roles: free=0, starter=1, core=2, pro=3, elite=4, **admin=5** |
| Assign tier | `PATCH /api/users/{username}` `{role}` |
| Add user | `POST /api/users` `{username,password,role,display_name,email}` (added username+temp-password fields — backend requires them) |
| Edit / suspend | `PATCH /api/users/{username}` `{display_name,email,role,disabled}` |
| Reset password | `POST /api/users/{username}/reset-password` |
| Delete | `DELETE /api/users/{username}` (owner/builtin protected server-side) |
| Tier Access · Configure | live `window.SURFACE_TIER` / `LENS_TIER` maps |

**Gaps to fill eventually** (design field has no backing store yet — shown as "—", not faked):
- **MFA** column — add `mfa` to `data/users.json` + auth.py.
- **Trades** column — per-user trade count (join to signal_log by user).
- **Tier Access · Configure** persistence — currently a live session map; wire to `PATCH /api/capability-registry` to persist.
- Design left `users` **ungated** (tier 0); server still enforces admin on every `/api/*` call. Set `SURFACE_TIER.users = 5` if you want the rail item itself hidden below Admin.

## Not yet built (home-first scope)
- 14-lens ticker detail panel (clicking a ticker shows a placeholder)
- Other non-Home rail surfaces (show a tier/placeholder gate)
