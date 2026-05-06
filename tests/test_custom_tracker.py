"""Smoke test for custom_tracker — add, list, remove."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_smoke():
    from custom_tracker import add_custom_ticker, get_custom_tickers, remove_custom_ticker
    r1 = add_custom_ticker("AAPL", "smoke test")
    assert r1.get("success"), r1
    lst = get_custom_tickers()
    assert any(t["ticker"] == "AAPL" for t in lst)
    r2 = remove_custom_ticker("AAPL")
    assert r2.get("success")


if __name__ == "__main__":
    test_smoke()
    print("PASS")
