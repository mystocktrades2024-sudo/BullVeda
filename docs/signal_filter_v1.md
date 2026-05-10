# `signal_filter` v1 — declarative whitelist gate (J2)

**Module:** `signal_filter.py`
**Wired in:** `decision_engine.py:626` (after BUY threshold passes, before return)
**Audit table:** `migrations/003_signal_filter_audit.sql` →
`signal_filter_decisions` (Postgres)
**Live state:** `config["signal_filter"]["_enabled"]` — currently `false`

---

## Why it exists

Per the 2026-05-09 750d backtest (n=384, raw WR 27.3%, PF 0.70, total return
−44.9%), the strategy in aggregate loses money. But the holdout slice (recent
15%, n=59) shows **PF 1.41** — meaning sub-strategies in specific contexts
have positive expectancy while the bulk is noise.

`signal_filter` is the gate that **enforces context-conditional entry**:
demote BUY → WATCH for any (setup × regime × score_band × entry_quality)
combination NOT in the validated whitelist.

This is the architectural complement to:
- **Wilson CI gates** (`decision_engine.py:240`, shipped `3418ea745`) —
  prevent killing a setup based on noise
- **`_validations` block** (`config.json`, shipped `7d544c205`) —
  enforce statistical backing before a config change takes effect
- **`canonical_trade_plan`** (shipped `2c9b9f339`) — single source of truth

---

## Schema

```jsonc
"signal_filter": {
  "_enabled": false,
  "_validations": {
    "<rule_id>": {
      "n":              47,           // closed signals matching the rule
      "wr":             0.52,         // point WR (0-1)
      "wr_lb":          0.45,         // Wilson 95% lower bound
      "wr_hi":          0.59,         // Wilson 95% upper bound
      "pf":             1.8,          // profit factor
      "expectancy_pct": 1.5,          // avg PnL %/trade
      "source":         "wf_2026Q1_validated",
      "validated_at":   "2026-05-09",
      "note":           "..."
    }
  },
  "whitelist": [
    {
      "id":             "pp_70_79_fresh_bull",
      "setup_type":     "Pocket Pivot",     // or null = match any
      "regimes":        ["risk_on_trending", "risk_on_choppy"],
      "score_band":     [70, 79],            // inclusive
      "entry_quality":  ["FRESH", "PULLBACK"]
    }
  ]
}
```

---

## Behavior matrix

| Filter state | Whitelist | Match | Validation | Result |
|---|---|---|---|---|
| `_enabled: false` | (any) | (any) | (any) | **allow** (`filter_disabled`) |
| `_enabled: true` | empty `[]` | n/a | n/a | **allow** (`no_whitelist`) — fail-open |
| `_enabled: true` | populated | rule matches | `n≥20 AND wr_lb≥0.40` | **allow** (`whitelisted`) |
| `_enabled: true` | populated | rule matches | NOT validated | **demote to WATCH** (`matched_unvalidated_rule`) |
| `_enabled: true` | populated | no rule matches | n/a | **demote to WATCH** (`no_matching_rule`) |

The `n>=20 AND wr_lb>=0.40` validation gate is **defense against speculative
whitelist edits**. A rule without backing is silently ignored.

---

## Rule-validation requirements (institutional discipline)

For a whitelist rule to take effect, its `_validations[rule_id]` entry must
clear:

1. **`n >= 20`** — minimum sample size for any directional claim
2. **`wr_lb >= 0.40`** — Wilson 95% lower bound clears the break-even-ish
   floor. Even at the bottom of the confidence interval, the setup wins
   ≥40% of the time.
3. **(Recommended)** `pf >= 1.3` — profit factor clears 1.3 (winning trades
   net 30%+ more than losing trades after stop-loss accounting).
4. **(Recommended)** `expectancy_pct > 0` — average per-trade PnL is
   positive (the obvious sanity check).

Source provenance (`source` field) MUST cite either:
- A specific backtest run (`750d_backtest_<git_commit>`)
- A walk-forward fold (`wf_<n>folds_<date>`)
- An A5-style decomposition output

Hand-edited entries without source attribution should be flagged for review.

---

## Retraining cadence

Every quarter (or after any major regime shift), re-validate the whitelist:

1. Run `python3 backtest.py --portfolio --days 750`
2. Run `python3 decompose_catalyst_trades.py` against the result
3. For each existing `whitelist` rule, recompute its stats from the new
   trade set
4. If any rule's `wr_lb` drops below 0.40 OR `n` drops below 20, that rule
   is automatically un-validated and silently inactive on next scan
5. Add NEW rules for newly-discovered alpha buckets, with proper validation
   provenance

This is **continuous evidence-based config management**. No more "edit
multipliers from intuition" — every demotion has Wilson backing.

---

## Audit trail

Every filter decision (allow OR demote) writes a row to `signal_filter_decisions`
in Postgres (migration 003 already applied):

```sql
SELECT setup_type, regime, score_band,
       COUNT(*) AS n_decisions,
       AVG(CASE WHEN allow THEN 1.0 ELSE 0.0 END) AS allow_rate
FROM signal_filter_decisions
WHERE decided_at >= NOW() - INTERVAL '30 days'
GROUP BY setup_type, regime, score_band
ORDER BY allow_rate;
```

Use the rolling `signal_filter_drift_30d` view (in migration 003) for the
A7 drift dashboard tile.

---

## Activation procedure (when ready)

1. Populate `_validations` from a recent decomposition or walk-forward run.
2. Populate `whitelist` with rules that reference those validations.
3. Run a 250d backtest with `--config-override
   '{"signal_filter": {"_enabled": true}}'` to test the impact:
   ```
   echo '{"signal_filter": {"_enabled": true}}' > /tmp/sf.json
   python3 backtest.py --portfolio --days 250 --config-override /tmp/sf.json
   ```
4. Compare to baseline 250d (`_enabled: false`):
   - Trades should drop 60-80%
   - WR should improve by 10+ pp
   - PF should improve to ≥ 1.3
   - Total return should move from negative to flat-or-positive
5. If validation passes, set `_enabled: true` permanently.
6. Monitor `signal_filter_decisions` audit table for the first week.
7. If real-world allow_rate < 5% (filter is too tight) OR > 95% (filter is
   no-op), re-tune.

---

## Current state (2026-05-09)

- `_enabled`: **false** (off)
- `_validations`: 1 entry — `pullback_bull_701_pullback_or_fresh` (DRAFT,
  awaiting per-subtype attribution)
- `whitelist`: 1 entry referencing the above (DRAFT)
- Audit table: empty (filter never invoked)

**Next step before activation:** A5-followup. The pullback meta-pattern
shows PF 1.83 over n=134 in the signal_log, but at meta-family granularity.
The QUANT-1 evidence (`fc76c9ec8`) showed EMA21 Pullback specifically had
WR 11.9% over n=59. These can both be true if the OTHER pullback subtypes
(EMA50 / 10-Week / Bounce-off-Support) carry the alpha. **Need per-subtype
attribution before activating** — composition risk too high otherwise.
