"""Comprehensive tests for portfolio_tracker state machine.

All tests use a temp state file via monkeypatched STATE_PATH so they never
touch production data/portfolio_state.json. No network calls are made.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import portfolio_tracker as pt  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────

def _fresh_state(equity: float = 10_000) -> dict:
    return {
        "equity": equity,
        "cash": equity,
        "positions": [],
        "closed_trades": [],
        "monthly_pnl": {},
        "margin_reserved": 0,
        "equity_curve": [{"date": "2026-04-14", "equity": equity}],
    }


@pytest.fixture
def temp_state(monkeypatch, tmp_path):
    """Redirect STATE_PATH to a temp file seeded with a clean $10K portfolio."""
    state_file = tmp_path / "portfolio_state.json"
    state_file.write_text(json.dumps(_fresh_state(10_000)))
    monkeypatch.setattr(pt, "STATE_PATH", state_file)
    # Ensure exclude_setups doesn't block our test setups
    monkeypatch.setitem(pt.CFG, "exclude_setups", ["52wk Breakout"])
    monkeypatch.setitem(pt.CFG, "max_positions", 4)
    return state_file


def _read(path) -> dict:
    return json.loads(path.read_text())


# ── Open/close LONG ─────────────────────────────────────────────────────────

def test_open_long_deducts_cash(temp_state):
    pt.add_position(ticker="AAPL", entry_price=200, shares=10,
                    stop=190, target1=220, setup_type="Pullback")
    state = _read(temp_state)
    assert state["cash"] == 8_000, f"expected $8000 cash, got {state['cash']}"
    assert len(state["positions"]) == 1
    assert state["positions"][0]["direction"] == "long"


def test_open_long_insufficient_cash(temp_state):
    with pytest.raises(ValueError, match="Insufficient cash"):
        pt.add_position(ticker="AAPL", entry_price=1100, shares=10,
                        stop=1000, target1=1200, setup_type="Pullback")


def test_open_short_reserves_margin(temp_state):
    pt.add_position(ticker="TSLA", entry_price=240, shares=5,
                    stop=250, target1=220, setup_type="Breakdown",
                    direction="short")
    state = _read(temp_state)
    # Short moves NO cash on open, reserves 50% of notional as margin
    assert state["cash"] == 10_000, f"short open shouldn't move cash, got {state['cash']}"
    assert state["margin_reserved"] == 600.0, (
        f"expected $600 margin (50% of 240*5=1200), got {state['margin_reserved']}"
    )


def test_open_short_insufficient_margin(temp_state, monkeypatch):
    # Set cash to tiny amount so margin requirement exceeds it
    state = _fresh_state(10_000)
    state["cash"] = 100  # only $100 available for margin
    state["margin_reserved"] = 0
    temp_state.write_text(json.dumps(state))

    with pytest.raises(ValueError, match="Insufficient margin"):
        pt.add_position(ticker="TSLA", entry_price=240, shares=5,
                        stop=250, target1=220, setup_type="Breakdown",
                        direction="short")


def test_close_long_credits_cash(temp_state):
    pt.add_position(ticker="AAPL", entry_price=200, shares=10,
                    stop=190, target1=220, setup_type="Pullback")
    # cash is now 8000
    pt.close_position("AAPL", exit_price=210)
    state = _read(temp_state)
    # Proceeds = 210*10 = 2100, cash = 8000 + 2100 = 10100
    assert state["cash"] == 10_100, f"expected $10100 cash after close, got {state['cash']}"
    assert len(state["positions"]) == 0
    assert len(state["closed_trades"]) == 1
    assert state["closed_trades"][0]["pnl_dollars"] == 100


def test_close_short_credits_pnl_only(temp_state):
    pt.add_position(ticker="TSLA", entry_price=240, shares=5,
                    stop=250, target1=220, setup_type="Breakdown",
                    direction="short")
    pt.close_position("TSLA", exit_price=230)
    state = _read(temp_state)
    # short profit = (240-230)*5 = $50 credited to cash, margin released
    assert state["cash"] == 10_050, f"expected $10050, got {state['cash']}"
    assert state["margin_reserved"] == 0, (
        f"margin should be released, got {state['margin_reserved']}"
    )
    assert state["closed_trades"][0]["pnl_dollars"] == 50


def test_close_short_loss(temp_state):
    pt.add_position(ticker="TSLA", entry_price=240, shares=5,
                    stop=260, target1=220, setup_type="Breakdown",
                    direction="short")
    pt.close_position("TSLA", exit_price=250)
    state = _read(temp_state)
    # short loss = (240-250)*5 = -$50
    assert state["cash"] == 9_950, f"expected $9950 after short loss, got {state['cash']}"
    assert state["closed_trades"][0]["pnl_dollars"] == -50
    assert state["margin_reserved"] == 0


def test_close_nonexistent_raises(temp_state):
    with pytest.raises(ValueError, match="No open position"):
        pt.close_position("FAKE", 100)


def test_max_positions_enforced(temp_state, monkeypatch):
    monkeypatch.setitem(pt.CFG, "max_positions", 4)
    # Seed a $100K portfolio so cash isn't the limiter
    state = _fresh_state(100_000)
    temp_state.write_text(json.dumps(state))

    for i, tk in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        pt.add_position(ticker=tk, entry_price=10, shares=100,
                        stop=9, target1=12, setup_type="Pullback")

    with pytest.raises(ValueError, match="Max .* concurrent positions"):
        pt.add_position(ticker="EEE", entry_price=10, shares=100,
                        stop=9, target1=12, setup_type="Pullback")


# ── set_equity ──────────────────────────────────────────────────────────────

def test_set_equity_adjusts_cash_correctly(temp_state):
    # $10K start, no positions; set equity = $15K → cash should become $15K
    result = pt.set_equity(15_000, reason="deposit")
    state = _read(temp_state)
    assert state["equity"] == 15_000
    assert state["cash"] == 15_000, f"expected cash=$15000, got {state['cash']}"
    assert result["invested"] == 0


def test_set_equity_less_than_invested_raises(temp_state):
    # Invest $2K in AAPL
    pt.add_position(ticker="AAPL", entry_price=200, shares=10,
                    stop=190, target1=220, setup_type="Pullback")
    with pytest.raises(ValueError, match="less than invested"):
        pt.set_equity(500)


def test_set_equity_creates_audit_entry(temp_state):
    pt.set_equity(12_000, reason="deposit 1")
    pt.set_equity(14_000, reason="deposit 2")
    log = pt.get_equity_audit_log()
    assert len(log) == 2, f"expected 2 audit entries, got {len(log)}"


def test_set_equity_negative_raises(temp_state):
    with pytest.raises(ValueError, match="positive"):
        pt.set_equity(-100)


def test_set_equity_zero_raises(temp_state):
    with pytest.raises(ValueError, match="positive"):
        pt.set_equity(0)


# ── Behavior & schema ───────────────────────────────────────────────────────

def test_direction_defaults_to_long(temp_state):
    pt.add_position(ticker="AAPL", entry_price=200, shares=10,
                    stop=190, target1=220, setup_type="Pullback")
    state = _read(temp_state)
    assert state["positions"][0]["direction"] == "long"


def test_get_portfolio_summary_shape(temp_state):
    summary = pt.get_portfolio_summary()
    required = {"equity", "cash", "positions", "closed_trades",
                "margin_reserved", "invested"}
    missing = required - set(summary.keys())
    assert not missing, f"summary missing keys: {missing}"
    # short_exposure should also exist
    assert "short_exposure" in summary


def test_open_close_roundtrip_reconciles(temp_state):
    pt.add_position(ticker="AAPL", entry_price=100, shares=10,
                    stop=95, target1=115, setup_type="Pullback")
    # cash: 10000 -> 9000
    state = _read(temp_state)
    assert state["cash"] == 9_000

    trade = pt.close_position("AAPL", exit_price=110)
    state = _read(temp_state)
    # Cash back: 9000 + 110*10 = 10100. Net +$100
    assert trade["pnl_dollars"] == 100, f"realized pnl should be $100, got {trade['pnl_dollars']}"
    assert state["cash"] == 10_100, f"cash should net +$100, got {state['cash']}"


def test_long_and_short_together_equity_consistent(temp_state):
    # Open a long and a short; verify summary totals are internally consistent
    pt.add_position(ticker="AAPL", entry_price=100, shares=10,
                    stop=95, target1=115, setup_type="Pullback")  # long: $1000 cash
    pt.add_position(ticker="TSLA", entry_price=200, shares=5,
                    stop=210, target1=180, setup_type="Breakdown",
                    direction="short")  # short: $500 margin reserved

    summary = pt.get_portfolio_summary()
    state = _read(temp_state)

    # Cash: 10000 - 1000 (long buy) = 9000
    assert state["cash"] == 9_000, f"cash={state['cash']}"
    # Invested (longs only) = 1000
    assert summary["invested"] == 1_000, f"invested={summary['invested']}"
    # Short exposure = 200*5 = 1000
    assert summary["short_exposure"] == 1_000, f"short_exposure={summary['short_exposure']}"
    # Margin reserved = 50% of 1000 = 500
    assert summary["margin_reserved"] == 500, f"margin_reserved={summary['margin_reserved']}"


# ── Bonus coverage ──────────────────────────────────────────────────────────

def test_backfill_legacy_no_direction(temp_state):
    # Write a position that predates the 'direction' field
    state = _fresh_state(10_000)
    state["cash"] = 9_000  # pretend we already paid for it
    state["positions"] = [{
        "ticker": "LEGACY",
        "entry_date": "2026-04-01",
        "entry_price": 100.0,
        "shares": 10,
        "position_size": 1_000.0,
        "stop": 95.0,
        "trail_stop": 95.0,
        "trail_active": False,
        "highest_price": 100.0,
        "setup_type": "Pullback",
        "target1": 110.0,
        "target2": None,
        # NOTE: no "direction" key
        "allocation_pct": 10.0,
        "notes": "",
    }]
    temp_state.write_text(json.dumps(state))

    trade = pt.close_position("LEGACY", exit_price=110)
    # Treated as long: pnl = (110-100)*10 = 100, cash += 1100
    assert trade["pnl_dollars"] == 100
    after = _read(temp_state)
    assert after["cash"] == 10_100, f"legacy close should credit full proceeds, got {after['cash']}"


def test_cannot_open_excluded_setup(temp_state, monkeypatch):
    monkeypatch.setitem(pt.CFG, "exclude_setups", ["52wk Breakout"])
    with pytest.raises(ValueError, match="excluded"):
        pt.add_position(ticker="AAPL", entry_price=100, shares=5,
                        stop=95, target1=110, setup_type="52wk Breakout")


def test_equity_audit_log_newest_first(temp_state):
    pt.set_equity(11_000, reason="first")
    pt.set_equity(12_000, reason="second")
    pt.set_equity(13_000, reason="third")
    log = pt.get_equity_audit_log()
    assert len(log) == 3
    assert log[0]["reason"] == "third", f"newest should be first, got {log[0]['reason']}"
    assert log[-1]["reason"] == "first"


@pytest.mark.parametrize("exit_price,expected_pnl", [
    (110, 100),   # $1 gain * 10 shares (per-share entry=100) actually (110-100)*10=100
    (100, 0),    # breakeven
    (90, -100),  # $1 loss * 10 shares (90-100)*10=-100
])
def test_long_pnl_parametrized(temp_state, exit_price, expected_pnl):
    pt.add_position(ticker="AAPL", entry_price=100, shares=10,
                    stop=85, target1=120, setup_type="Pullback")
    trade = pt.close_position("AAPL", exit_price=exit_price)
    assert trade["pnl_dollars"] == expected_pnl, (
        f"exit={exit_price} expected pnl={expected_pnl}, got {trade['pnl_dollars']}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
