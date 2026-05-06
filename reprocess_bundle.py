"""
reprocess_bundle.py — Re-route today's bundle through decision_engine.

Reads cache/last_bundle.json, runs compute_final_verdict() against every ticker
in buy_candidates / watch_list / all_scored, updates verdict/reject_reason/
caveats/gates_evaluated/audit_trail, and re-routes BUY-listed tickers that
fail hard gates into watch_list.

Idempotent — safe to re-run.
"""
from __future__ import annotations
import json
from pathlib import Path
from copy import deepcopy
from decision_engine import compute_final_verdict

ROOT = Path(__file__).parent
BUNDLE_PATH = ROOT / "cache" / "last_bundle.json"
CFG_PATH = ROOT / "config" / "config.json"


def main():
    cfg = json.loads(CFG_PATH.read_text())
    thresholds = cfg.get("regime4_thresholds") or {}
    bundle = json.loads(BUNDLE_PATH.read_text())
    regime = (bundle.get("regime") or {}).get("regime4") or "risk_on_choppy"

    # Walk EVERY top-level list section that contains ticker dicts.
    # build_data.py reads from many sources (buy_candidates, watch_list,
    # all_scored, medium_term_picks, long_term_picks, extended_leaders, ...)
    # and falls back to score-based stage when decision.verdict is missing.
    # We must overwrite verdict in every section to prevent ghost BUYs.
    sections = []
    for k, v in bundle.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "ticker" in v[0]:
            sections.append(k)
    print(f"Reprocessing sections: {sections}")
    apply_count = 0
    for sec in sections:
        rows = bundle.get(sec) or []
        for r in rows:
            if not isinstance(r, dict):
                continue
            res = compute_final_verdict(r, regime=regime, thresholds=thresholds)
            r["verdict"] = res["verdict"]
            r["reject_reason"] = res["reason"] if res["verdict"] != "BUY" else ""
            r["caveats"] = res["caveats"]
            r["gates_evaluated"] = res["gates_evaluated"]
            # Also write nested decision.* so legacy readers (build_data.py:1139)
            # see consistent verdict — single source of truth, two locations.
            dec = r.setdefault("decision", {})
            if isinstance(dec, dict):
                dec["verdict"] = res["verdict"]
                dec["reason"] = res["reason"]
            r["audit_trail"] = {
                "ticker": r.get("ticker"),
                "verdict": res["verdict"],
                "reason": res["reason"],
                "hard_gates_passed": all(g["passed"] for g in res["gates_evaluated"]),
                "gate_failures": [g["name"] for g in res["gates_evaluated"] if not g["passed"]],
                "caveats": res["caveats"],
                "decided_by": "decision_engine.compute_final_verdict",
            }
            apply_count += 1

    # Re-route: BUYs that failed gates → watch_list
    new_buy: list = []
    new_watch: list = list(bundle.get("watch_list") or [])
    rerouted = 0
    for r in bundle.get("buy_candidates") or []:
        if isinstance(r, dict) and r.get("verdict") == "BUY":
            new_buy.append(r)
        else:
            new_watch.append(r)
            rerouted += 1
    # Dedupe watch list by ticker (BUY -> WATCH may collide with existing watch entry)
    seen: set = set()
    deduped: list = []
    for r in new_watch:
        if not isinstance(r, dict):
            continue
        tk = r.get("ticker")
        if tk in seen:
            continue
        seen.add(tk)
        deduped.append(r)
    bundle["buy_candidates"] = new_buy
    bundle["watch_list"] = deduped

    # Mark provenance
    bundle["decision_engine_version"] = "1.0"
    bundle["reprocessed_at"] = bundle.get("run_timestamp")

    BUNDLE_PATH.write_text(json.dumps(bundle, indent=2, default=str))
    print(f"Reprocessed {apply_count} ticker entries across {sections}")
    print(f"BUY: {len(new_buy)}  WATCH: {len(deduped)}")
    print(f"Rerouted from BUY → WATCH: {rerouted}")
    if new_buy:
        print("\nFinal BUY list:")
        for r in new_buy:
            cv = f" [{'; '.join(r.get('caveats') or [])}]" if r.get("caveats") else ""
            print(f"  {r.get('ticker'):6s}  score={r.get('score')}  setup={r.get('setup_family') or r.get('setup')}{cv}")


if __name__ == "__main__":
    main()
