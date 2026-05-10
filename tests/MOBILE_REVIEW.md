# Mobile responsive — audit notes (2026-05-09)

## Summary

The V2 dashboard is **desktop-first**. Layout assumes ≥1080px; degrades poorly below that. Tablet-portrait (768px) and phone (≤480px) are not supported.

## Findings

### Viewport meta — MISSING in both pages
```
$ grep viewport infra/prototype/dashboard.html      → 0 hits
$ grep viewport infra/prototype/elite-detail.html   → 0 hits
```
**Impact**: mobile browsers render at 980px logical width and shrink to fit, producing tiny text and broken click targets. Single `<meta name="viewport" content="width=device-width, initial-scale=1">` would dramatically improve baseline mobile rendering.

### Media queries — desktop-only

| File | @media count | Smallest breakpoint | Notes |
|------|--------------|---------------------|-------|
| `dashboard.html` | 2 | `max-width: 1080px` | Drops sidebar / re-flows tile grid. NO tablet (768) or phone (480) breakpoint. |
| `elite-detail.html` | 9 | `max-width: 1100px` | Mostly grid-template-columns flips. Same — no tablet/phone. |
| `floor.css` | (not checked, separate file) | — | Used by Floor Scanner tab |
| `theme_dell.css` | (not checked) | — | Backtest report theme |

### Click target sizes
- Sidebar links: ~36px tall — borderline (Apple HIG min: 44px)
- Filter chips on Strategies tab: ~28px — too small for thumbs
- Table rows in Audit / Performance: 24-30px — definitely not mobile-tappable

### Horizontal scroll surfaces (problematic on mobile)
- Audit Trail table: 26 columns (D1..D5, W1..W5, M1..M6 + 9 fixed) — must scroll
- Screener: dense table, 22 columns
- Matrix view in CapStudio: NxM grid, scroll required for >5 roles

## Recommended path (if you want mobile)

### Phase 0 — base hygiene (15 min)
1. Add `<meta name="viewport" content="width=device-width, initial-scale=1">` to both HTML files. **One-line fix**, biggest single-win.
2. Add `box-sizing: border-box` global rule (probably already present).

### Phase 1 — usable on tablet portrait (768px) — 4-6 hrs
1. Add `max-width: 800px` breakpoint that:
   - Collapses sidebar to a hamburger drawer
   - Stacks the FLOOR tile grid 2-up (currently 4-up)
   - Hides secondary KPI columns in tables (let user tap-expand a row to see them)
2. Increase tap targets to 44px in the sidebar + chips.
3. Enable touch-scroll on horizontal tables with sticky first column.

### Phase 2 — phone (480px) — 8-12 hrs
1. Single-column tile layout
2. Tab navigation as bottom nav (iOS-style)
3. Replace tables with cards (per-row stacked layout)
4. Modal trade ticket adapts to full-screen sheet
5. `elite-detail.html` becomes a swipe-between-sub-tabs UI

## Decision

If your usage is **always desktop**, do nothing. The desktop UX is already polished.

If you want **occasional tablet usage**, do Phase 0 + Phase 1 (~5 hrs total, low risk).

Phone support is genuinely a multi-day project — only worth it if mobile becomes a core use case.

## Quick test
Open Chrome DevTools → device toolbar → iPad Pro / iPhone 14. Walk through Settings, Portfolio, Elite Picks. Document everything that breaks before deciding scope.
