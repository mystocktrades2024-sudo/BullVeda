# Backtest Variant Playbook

Pre-built `--config-override` files for the candidate fixes from Q1-step5 diagnosis (2026-05-10).

| File | Fix | Hypothesis | Predicted PF |
|------|-----|------------|--------------|
| `A_fresh_entries_only.json` | entry_quality=FRESH only | Cuts late-entry whipsaws | 1.1-1.3 |
| `E2_regime_plus_wider_stops.json` | Variant F + 1.5× ATR stops | Combines kill + stop relief | 1.2-1.5 |
| `G_combined.json` | Variant F + FRESH-only | Most aggressive cut | 1.4-1.8 (target) |
| `H_score_band_per_regime.json` | Per-regime score-band gates | — | — |
| `I_regime_entry_rules.json` | Per-regime entry-quality gates | — | — |

## How to run

```bash
python3 backtest.py --portfolio --days 250 --config-override config/variants/<file>.json
```

Use `--smoke` first for sanity (won't tell you the real PF — too few trades — but catches config errors in 60s).

## Notes

- Counterfactual analysis (Agent 3, 2026-05-10) showed wider stops alone don't lift PF (the losers are sustained adverse moves, not whipsaws). Don't bother running a "wider stops alone" variant.
- Variant F = `setup_score_multiplier_by_regime` config block (commit f0a66543e).
