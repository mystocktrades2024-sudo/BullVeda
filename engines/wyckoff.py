"""engines/wyckoff.py — Wyckoff adapter for the pattern registry."""
from __future__ import annotations
from wyckoff_engine import detect_from_df

NAME = "wyckoff"
LABEL = "Wyckoff"

def detect(df, meta, ticker):
    return detect_from_df(df, meta, ticker)
