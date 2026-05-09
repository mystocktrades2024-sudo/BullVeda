"""
push_backtest_to_supabase.py — One-shot pusher for backtest results.

Reads cache/portfolio_backtest.json (the file backtest.py writes when run
with --portfolio) and uploads to Supabase backtest_runs + backtest_trades.

Usage:
    python3 push_backtest_to_supabase.py                     # auto: latest run
    python3 push_backtest_to_supabase.py path/to/results.json  # explicit
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ["SUPABASE_MODE"] = "1"
from supabase_client import sb_client, healthcheck  # noqa: E402

ROOT = Path(__file__).parent
DEFAULT_RESULTS_PATH = ROOT / "cache" / "portfolio_backtest.json"
DEFAULT_CONFIG_PATH = ROOT / "config" / "config.json"


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, cwd=str(ROOT)
        ).decode().strip()
        return out or None
    except Exception:
        return None


def _make_run_id(result: dict) -> str:
    """Stable identifier from finish-time + window."""
    finished = result.get("config", {}).get("end_date") or datetime.now(timezone.utc).isoformat()
    days = result.get("config", {}).get("days") or 0
    base = f"{finished}_{days}d_{result.get('total_pnl', 0):.0f}"
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def _row_for_run(result: dict, raw_stdout: str | None = None) -> dict:
    cfg = result.get("config", {})
    run_id = _make_run_id(result)
    config_snapshot = None
    if DEFAULT_CONFIG_PATH.exists():
        try:
            config_snapshot = json.loads(DEFAULT_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {
        "run_id": run_id,
        "started_at": cfg.get("started_at") or datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "mode": "portfolio",
        "days": int(cfg.get("days") or 0),
        "end_date": cfg.get("end_date"),
        "min_score": int(cfg.get("min_score") or 0),
        "min_rs": int(cfg.get("min_rs") or 0),
        "n_trades": result.get("total_trades"),
        "wr_raw": (result.get("win_rate") or 0) / 100,
        "wr_adj": (result.get("win_rate_adj") or result.get("win_rate") or 0) / 100,
        "profit_factor": result.get("profit_factor"),
        "sharpe": result.get("sharpe"),
        "max_drawdown": (result.get("max_drawdown_pct") or 0) / 100,
        "total_pnl": result.get("total_pnl"),
        "starting_equity": result.get("starting_equity"),
        "final_equity": result.get("final_equity"),
        "total_return": (result.get("total_return_pct") or 0) / 100,
        "config_snapshot": config_snapshot,
        "git_commit": _git_commit(),
        "raw_stdout": raw_stdout,
    }


def _trade_rows(result: dict, run_id: str) -> list[dict]:
    out = []
    for t in (result.get("trades") or []):
        out.append({
            "run_id": run_id,
            "ticker": t.get("ticker"),
            "direction": t.get("direction") or "long",
            "entry_date": t.get("entry_date"),
            "exit_date": t.get("exit_date"),
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "shares": t.get("shares"),
            "pnl_dollars": t.get("pnl_dollars"),
            "pnl_pct": t.get("pnl_pct"),
            "win": int(bool(t.get("win") or (t.get("pnl_dollars") or 0) > 0)),
            "setup_family": t.get("setup_family"),
            "setup_type": t.get("setup_type"),
            "score": int(t.get("score") or 0) if t.get("score") is not None else None,
            "rs_rank": t.get("rs_rank"),
            "regime": t.get("regime"),
            "exit_reason": t.get("exit_reason"),
            "hold_days": t.get("hold_days"),
            "mae_pct": t.get("mae_pct") or t.get("mae"),
            "mfe_pct": t.get("mfe_pct") or t.get("mfe"),
            "raw_json": t,
        })
    return out


def push(result_path: Path) -> dict:
    if not result_path.exists():
        return {"ok": False, "error": f"results file not found: {result_path}"}

    hc = healthcheck()
    if not hc.get("ok"):
        return {"ok": False, "error": f"Supabase unavailable: {hc.get('error')}"}

    sb = sb_client()
    result = json.loads(result_path.read_text())
    run_row = _row_for_run(result)
    run_id = run_row["run_id"]

    out = {"ok": True, "run_id": run_id, "errors": []}

    # Upsert backtest_runs
    try:
        sb.table("backtest_runs").upsert(run_row, on_conflict="run_id").execute()
    except Exception as e:
        out["errors"].append(f"backtest_runs: {type(e).__name__}: {str(e)[:200]}")
        out["ok"] = False
        return out

    # Push trades — delete prior + insert (idempotent re-push)
    trade_rows = _trade_rows(result, run_id)
    if trade_rows:
        try:
            sb.table("backtest_trades").delete().eq("run_id", run_id).execute()
            BATCH = 100
            for i in range(0, len(trade_rows), BATCH):
                sb.table("backtest_trades").insert(trade_rows[i:i + BATCH]).execute()
            out["n_trades_pushed"] = len(trade_rows)
        except Exception as e:
            out["errors"].append(f"backtest_trades: {type(e).__name__}: {str(e)[:200]}")
    else:
        out["n_trades_pushed"] = 0

    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RESULTS_PATH
    print(f"Pushing backtest results from {path}")
    r = push(path)
    print(json.dumps(r, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
