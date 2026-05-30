#!/usr/bin/env python3
"""
ml_train_with_gate.py — champion-challenger promotion gate around train_historical.

Pipeline:
  1. Move current champion artifacts to cache/ml/_champion_backup/
  2. Run ml/train_historical.py
  3. Read holdout metrics from the new calibration_report_historical.json
  4. Per mode (swing/position/invest): promote only if direction accuracy
     and hit-net AUC do not regress by more than epsilon.
  5. Restore champion artifacts for any rejected mode.
  6. Append decisions to cache/ml/promotion_log.jsonl + update champion_metrics.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_DIR = ROOT / "cache" / "ml"
BACKUP_DIR = ART_DIR / "_champion_backup"
CHAMPION_METRICS = ART_DIR / "champion_metrics.json"
PROMOTION_LOG    = ART_DIR / "promotion_log.jsonl"
CAL_REPORT       = ART_DIR / "calibration_report_historical.json"

MODES = ["swing", "position", "invest"]
ARTIFACTS_PER_MODE = ["direction", "magnitude", "hit_net"]


def _backup_champions():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for mode in MODES:
        for art in ARTIFACTS_PER_MODE:
            src = ART_DIR / f"{mode}_{art}.pkl"
            dst = BACKUP_DIR / f"{mode}_{art}.pkl"
            if src.exists():
                shutil.copy2(src, dst)


def _restore_champion(mode: str, art: str) -> bool:
    src = BACKUP_DIR / f"{mode}_{art}.pkl"
    dst = ART_DIR / f"{mode}_{art}.pkl"
    if src.exists():
        shutil.copy2(src, dst)
        return True
    return False


def _load_champion_metrics() -> dict:
    if CHAMPION_METRICS.exists():
        try:
            return json.loads(CHAMPION_METRICS.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def _save_champion_metrics(metrics: dict) -> None:
    CHAMPION_METRICS.write_text(json.dumps(metrics, indent=2))


def _log_promotion(entry: dict) -> None:
    PROMOTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMOTION_LOG, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def _run_trainer() -> int:
    cmd = [sys.executable, "-m", "ml.train_historical"]
    print(f"[gate] running: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--eps-acc", type=float, default=0.005)
    ap.add_argument("--eps-auc", type=float, default=0.005)
    args = ap.parse_args()

    started = time.time()
    champion = _load_champion_metrics()
    print(f"[gate] champion baseline: {list(champion.get('modes', {}).keys()) or 'NONE (first run)'}")

    _backup_champions()
    rc = _run_trainer()
    if rc != 0:
        print(f"[gate] trainer failed (rc={rc}) — champions untouched")
        sys.exit(rc)

    if not CAL_REPORT.exists():
        print(f"[gate] FATAL: {CAL_REPORT} not produced by trainer")
        sys.exit(1)
    report = json.loads(CAL_REPORT.read_text())
    challenger_modes = report.get("modes", {})

    decisions = []
    new_metrics = {"updated_at": datetime.now(timezone.utc).isoformat(), "modes": {}}

    for mode in MODES:
        if mode not in challenger_modes:
            print(f"[gate · {mode}] no challenger report — skipped")
            continue
        ch = challenger_modes[mode]
        ch_acc = float(ch.get("direction", {}).get("accuracy", 0))
        ch_auc = float(ch.get("hit_net", {}).get("auc", 0))

        cm = champion.get("modes", {}).get(mode, {})
        b_acc = float(cm.get("direction_accuracy", 0))
        b_auc = float(cm.get("hit_net_auc", 0))

        if args.force or not cm:
            verdict = "PROMOTED (forced or first-run)"
            promoted = True
            reason = "no_baseline" if not cm else "force_flag"
        else:
            acc_delta = ch_acc - b_acc
            auc_delta = ch_auc - b_auc
            acc_pass = acc_delta >= -args.eps_acc
            auc_pass = auc_delta >= -args.eps_auc
            if acc_pass and auc_pass:
                verdict = f"PROMOTED (Δacc={acc_delta:+.4f} Δauc={auc_delta:+.4f})"
                promoted = True
                reason = "passed_gate"
            else:
                restored = []
                for art in ARTIFACTS_PER_MODE:
                    if _restore_champion(mode, art):
                        restored.append(art)
                verdict = (f"REJECTED — Δacc={acc_delta:+.4f} (gate {-args.eps_acc:+.4f}) "
                           f"Δauc={auc_delta:+.4f} (gate {-args.eps_auc:+.4f}) "
                           f"— restored {restored}")
                promoted = False
                reason = ("acc_regression" if not acc_pass else "") + \
                         ("|auc_regression" if not auc_pass else "")

        print(f"[gate · {mode}] {verdict}")
        decisions.append({
            "mode": mode,
            "promoted": promoted,
            "reason": reason,
            "challenger": {"direction_accuracy": ch_acc, "hit_net_auc": ch_auc},
            "champion_baseline": {"direction_accuracy": b_acc, "hit_net_auc": b_auc},
        })

        if promoted:
            new_metrics["modes"][mode] = {
                "direction_accuracy": ch_acc,
                "hit_net_auc": ch_auc,
                "log_loss": float(ch.get("direction", {}).get("log_loss", 0)),
                "brier": float(ch.get("hit_net", {}).get("brier", 0)),
                "n_total": int(ch.get("n_total", 0)),
                "date_range": ch.get("date_range"),
                "promoted_at": new_metrics["updated_at"],
            }
        else:
            if mode in champion.get("modes", {}):
                new_metrics["modes"][mode] = champion["modes"][mode]

    _save_champion_metrics(new_metrics)
    _log_promotion({
        "ran_at":     new_metrics["updated_at"],
        "elapsed_s":  round(time.time() - started, 1),
        "decisions":  decisions,
        "force":      args.force,
        "eps_acc":    args.eps_acc,
        "eps_auc":    args.eps_auc,
    })

    rejected = [d["mode"] for d in decisions if not d["promoted"]]
    promoted = [d["mode"] for d in decisions if d["promoted"]]
    print(f"[gate] done in {round(time.time()-started, 1)}s · promoted={promoted} rejected={rejected}")


if __name__ == "__main__":
    main()
