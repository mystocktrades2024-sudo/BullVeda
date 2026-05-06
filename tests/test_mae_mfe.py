import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_compute_mae_mfe():
    from signal_tracker import compute_mae_mfe
    # AAPL test: entered at some known price, should return valid floats
    mae, mfe = compute_mae_mfe("AAPL", "2025-01-02", 230.0, "long", "2025-01-15")
    assert mae is not None and mfe is not None, f"got {mae}, {mfe}"
    assert mae <= 0 or abs(mae) < 100  # sanity
    assert mfe >= 0 or abs(mfe) < 100


if __name__ == "__main__":
    test_compute_mae_mfe()
    print("PASS")
