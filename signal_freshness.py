"""
signal_freshness.py — Recency decay + stale-data detection.

Per Phase-3 feedback (2026-04-30) items #26, #27, #28, #29:
- UOA recency decay: 0-5d full, 6-10d 50%, 11-15d 25%, >15d ignored
- Insider buying recency: 0-30d full, 31-90d 50%, >90d ignored
- News sentiment time-weighted: 3d high, 14d med, 30d low, >30d ignored
- Every signal carries {signal_date, age_days, is_stale}

The recency-weighted contribution is multiplied with the original signal
strength so old signals don't get full credit in the Smart Money pillar.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional


def _parse_date(d) -> Optional[_dt.date]:
    if d is None:
        return None
    if isinstance(d, _dt.date):
        return d
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, (int, float)):
        try:
            return _dt.datetime.utcfromtimestamp(float(d)).date()
        except Exception:
            return None
    if isinstance(d, str):
        try:
            return _dt.datetime.strptime(d[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def age_days(signal_date, today: Optional[_dt.date] = None) -> Optional[int]:
    sd = _parse_date(signal_date)
    if sd is None:
        return None
    today = today or _dt.date.today()
    return (today - sd).days


# ── UOA decay (0-5d full, 6-10d 50%, 11-15d 25%, >15d 0) ────────────────────
def uoa_decay_weight(signal_date) -> float:
    age = age_days(signal_date)
    if age is None:
        return 1.0  # treat as fresh if no date
    if age < 0:
        return 1.0
    if age <= 5:
        return 1.0
    if age <= 10:
        return 0.5
    if age <= 15:
        return 0.25
    return 0.0


# ── Insider buys (0-30d full, 31-90d 50%, >90d 0) ──────────────────────────
def insider_decay_weight(signal_date) -> float:
    age = age_days(signal_date)
    if age is None:
        return 1.0
    if age < 0:
        return 1.0
    if age <= 30:
        return 1.0
    if age <= 90:
        return 0.5
    return 0.0


# ── News sentiment time-weighted (3d/14d/30d) ──────────────────────────────
def news_decay_weight(signal_date) -> float:
    age = age_days(signal_date)
    if age is None:
        return 1.0
    if age < 0:
        return 1.0
    if age <= 3:
        return 1.0
    if age <= 14:
        return 0.5
    if age <= 30:
        return 0.25
    return 0.0


# ── Stale-data detection ───────────────────────────────────────────────────
def is_stale(signal_date, max_age_days: int = 30) -> bool:
    age = age_days(signal_date)
    if age is None:
        return False  # unknown age != stale
    return age > max_age_days


def annotate(signal: dict, signal_date_field: str = "date",
             stale_threshold_days: int = 30) -> dict:
    """
    Add `signal_date`, `age_days`, `is_stale` fields to a signal dict in-place.
    Returns the same dict.
    """
    sd = signal.get(signal_date_field)
    age = age_days(sd)
    signal["signal_date"] = sd if isinstance(sd, str) else (sd.isoformat() if isinstance(sd, _dt.date) else None)
    signal["age_days"] = age
    signal["is_stale"] = is_stale(sd, stale_threshold_days)
    return signal


# ── Helpers for Smart Money pillar integration ────────────────────────────
def apply_uoa_decay(uoa_signal: dict) -> dict:
    """
    Mutate the UOA signal dict to include `weight` and `decayed` flag based
    on its `date` field (or `published_utc` / `signal_date`).
    """
    if not uoa_signal:
        return uoa_signal
    sd = uoa_signal.get("date") or uoa_signal.get("signal_date") or uoa_signal.get("published_utc")
    w = uoa_decay_weight(sd)
    uoa_signal["weight"] = w
    uoa_signal["age_days"] = age_days(sd)
    uoa_signal["is_stale"] = w == 0
    return uoa_signal


def apply_insider_decay(insider_data: dict) -> dict:
    """
    For insider transactions, derive a weighted net_buy score that decays
    older entries. Expects insider_data with `transactions` list, each with
    `date` field. Returns same dict with `weighted_net_buys` added.
    """
    if not insider_data:
        return insider_data
    txns = insider_data.get("transactions") or []
    if not isinstance(txns, list):
        return insider_data
    weighted = 0.0
    raw = 0.0
    for tx in txns:
        sd = tx.get("date") or tx.get("transaction_date")
        amt = tx.get("net_buy") or tx.get("value") or 0
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            amt = 0
        w = insider_decay_weight(sd)
        weighted += amt * w
        raw += amt
        tx["weight"] = w
        tx["age_days"] = age_days(sd)
    insider_data["weighted_net_buys"] = round(weighted, 2)
    insider_data["raw_net_buys"] = round(raw, 2)
    return insider_data


def apply_news_decay(news_articles: list) -> dict:
    """
    Compute time-weighted aggregate sentiment from a list of news articles.
    Each article should have `published_utc` (ISO string) and `sentiment`
    (dict with `polarity` or label).
    Returns {weighted_polarity, raw_count, recent_count, stale_count}.
    """
    if not news_articles:
        return {"weighted_polarity": 0, "raw_count": 0, "recent_count": 0, "stale_count": 0}
    weighted_sum = 0.0
    weight_sum = 0.0
    recent = 0
    stale = 0
    for n in news_articles:
        sd = n.get("published_utc") or n.get("published") or n.get("date")
        sent = n.get("sentiment")
        polarity = 0.0
        if isinstance(sent, dict):
            polarity = float(sent.get("polarity", 0) or 0)
        elif isinstance(sent, str):
            polarity = {"positive": 0.5, "negative": -0.5, "neutral": 0}.get(sent.lower(), 0)
        elif isinstance(sent, (int, float)):
            polarity = float(sent)
        w = news_decay_weight(sd)
        weighted_sum += polarity * w
        weight_sum += w
        if w >= 0.5:
            recent += 1
        if w == 0:
            stale += 1
        n["age_days"] = age_days(sd)
        n["weight"] = w
    return {
        "weighted_polarity": round(weighted_sum / weight_sum, 3) if weight_sum > 0 else 0,
        "raw_count": len(news_articles),
        "recent_count": recent,
        "stale_count": stale,
        "effective_articles": round(weight_sum, 2),
    }
