# SwingTrade iPad Shell

iPad-optimized PWA shell for the SwingTrade dashboard. **Reuses every existing
sub-tab module** via iframe of `/kairos.html` — no module duplication.

## Open

- Local: `http://localhost:7432/v2/ipad/dashboard.html`
- Public: `https://trade.mystockholding.com/v2/ipad/dashboard.html`

## Add to Home Screen (iPad)

1. Open the URL in Safari on iPad.
2. Tap Share → "Add to Home Screen".
3. SwingTrade icon appears like a native app.
4. Launches in full-screen (no Safari chrome) with PWA manifest.

## Layout

| Orientation | Layout |
|---|---|
| Landscape (≥1024×768) | Split view — list left (38%), detail right (62%) |
| Portrait (<1024×768) | Stacked — full-width list; tap row → detail slides in from right |
| iPad Pro 11" landscape | List 32%, detail 68% (more breathing room) |

## Bottom tab bar (5 tabs, iOS HIG max)

1. **Scanner** — top BUY + WATCH from today's scan (default)
2. **Watchlist** — your saved + custom tickers
3. **Portfolio** — open positions
4. **Elite** — top picks by EV score
5. **Settings** — equity, config snapshot, link to desktop view

## Files

| File | Purpose |
|---|---|
| `dashboard.html` | Main shell (top bar, split panes, tab bar) |
| `ipad.css` | iPad-specific layout — split-view, portrait stack, safe-area-insets, 44pt taps |
| `ipad.js` | Controller — data loading, list render, tab switch, detail iframe, pull-to-refresh |
| `manifest.json` | PWA manifest for "Add to Home Screen" |
| `icon-180.png` etc. | (Optional) home-screen icons — currently missing, system uses default |

## Data flow

- Boots from `/v2/data.critical.json` (~1.5 MB) — same chunk desktop uses
- Per-ticker detail: lazy `<iframe src="/kairos.html?t=TICKER">`
- This means every Overview, Plan, Technicals, etc. update in the existing
  desktop modules **automatically appears in the iPad detail pane** with no
  duplication or porting.

## What's NOT here yet

- Native iOS push notifications (would need Service Worker + push subscription)
- Offline mode (Service Worker for caching)
- Swipe-to-action on rows (left swipe → quick add to portfolio etc.)
- Bottom-sheet modals for editing
- Apple-style segmented controls
- Real home-screen icons (PNG files) — using browser default until added
- Explicit Apple Pencil hover state (would need pen events handler)

These are good Phase 2 items. Phase 1 (current) is structural correctness:
split-view, bottom tab bar, touch-first sizing, PWA install path.

## Testing

1. Open in Safari on actual iPad
2. Verify landscape shows 2-pane split, portrait shows list-only with detail-on-tap
3. Verify tap targets feel comfortable (≥44×44 pt)
4. Add to Home Screen, verify it launches full-screen
5. Pull-to-refresh on list should fire `refreshData()`
6. URL `/v2/ipad/dashboard.html?t=NVDA` should auto-open NVDA detail
