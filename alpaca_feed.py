"""
Alpaca Markets live data feed for SwingTrade.
Provides real-time price updates and news via WebSocket.
Falls back gracefully when Alpaca is not configured.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path

log = logging.getLogger("swingtrade.alpaca")

# Global state — written from stream threads, read from HTTP threads.
# Python's GIL provides sufficient safety at this scale.
_price_cache: dict = {}     # {ticker: {price, open, high, low, volume, timestamp}}
_news_cache: list = []      # recent news items (last 50), newest first
_subscribers: list = []     # SSE subscriber queues
_price_stream_running = False
_config: dict | None = None
_config_loaded = False      # distinguish "not yet loaded" from "loaded but None"


def load_alpaca_config(config_path: str | None = None) -> dict | None:
    """Load Alpaca API keys from config. Returns None if not configured."""
    if config_path is None:
        config_path = str(Path(__file__).parent / "config" / "config.json")
    try:
        # AI-2: prefer env / .env via secrets_loader; fall back to config.json
        try:
            from secrets_loader import alpaca_key as _ak, alpaca_secret as _as
            api_key = _ak()
            secret_key = _as()
        except Exception:
            api_key = secret_key = ""
        alpaca: dict = {}
        try:
            cfg = json.loads(Path(config_path).read_text())
            alpaca = cfg.get("alpaca", {})
            if not api_key:
                api_key = alpaca.get("api_key", "")
            if not secret_key:
                secret_key = alpaca.get("secret_key", "")
        except Exception:
            pass
        if not api_key or not secret_key or api_key == "YOUR_API_KEY":
            log.info("Alpaca not configured — live feed disabled")
            return None
        return {
            "api_key": api_key,
            "secret_key": secret_key,
            "paper": alpaca.get("paper", True),
            "feed": alpaca.get("feed", "iex"),  # "iex" (free) or "sip" (paid)
        }
    except Exception as e:
        log.debug(f"Alpaca config load: {e}")
        return None


def is_configured() -> bool:
    """Check if Alpaca credentials are present in config."""
    global _config, _config_loaded
    if not _config_loaded:
        _config = load_alpaca_config()
        _config_loaded = True
    return _config is not None


def get_cached_price(ticker: str) -> dict | None:
    """Get latest cached price for a ticker. Returns None if not available."""
    return _price_cache.get(ticker.upper())


def get_all_prices() -> dict:
    """Get a snapshot of all cached prices."""
    return dict(_price_cache)


def get_recent_news(limit: int = 20) -> list:
    """Get recent news items (newest first)."""
    return _news_cache[:limit]


# ---------------------------------------------------------------------------
# SSE pub/sub
# ---------------------------------------------------------------------------

def subscribe() -> queue.Queue:
    """Subscribe to SSE events. Returns a Queue that yields (event_type, data) tuples."""
    q: queue.Queue = queue.Queue(maxsize=100)
    _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    """Remove an SSE subscriber."""
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def _broadcast(event_type: str, data: dict) -> None:
    """Deliver an event to all live SSE subscribers, pruning stale ones."""
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait((event_type, data))
        except queue.Full:
            # Subscriber is too slow — drop and mark for removal
            dead.append(q)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Price stream
# ---------------------------------------------------------------------------

def start_price_stream(tickers: list) -> None:
    """Start streaming real-time bars for given tickers. Non-blocking.

    Safe to call multiple times — only one stream thread runs at a time.
    """
    global _price_stream_running
    if _price_stream_running:
        log.debug("Price stream already running")
        return
    if not is_configured():
        log.info("Alpaca not configured — skipping price stream")
        return
    if not tickers:
        log.info("No tickers supplied — skipping price stream")
        return

    _price_stream_running = True
    thread = threading.Thread(
        target=_run_price_stream, args=(tickers,), daemon=True, name="alpaca-price"
    )
    thread.start()
    log.info(f"Alpaca price stream started for {len(tickers)} ticker(s): {tickers}")


def _run_price_stream(tickers: list) -> None:
    """Internal: run the Alpaca WebSocket bar stream (blocking inside thread)."""
    global _price_stream_running
    try:
        from alpaca.data.live import StockDataStream  # type: ignore

        stream = StockDataStream(_config["api_key"], _config["secret_key"])

        async def on_bar(bar):
            data = {
                "ticker": bar.symbol,
                "price": float(bar.close),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "volume": int(bar.volume),
                "timestamp": bar.timestamp.isoformat() if hasattr(bar, "timestamp") else "",
            }
            _price_cache[bar.symbol] = data
            _broadcast("price", data)

        stream.subscribe_bars(on_bar, *[t.upper() for t in tickers])
        stream.run()
    except ImportError:
        log.warning("alpaca-py not installed — run: pip install alpaca-py")
    except Exception as e:
        log.error(f"Alpaca price stream error: {e}")
    finally:
        _price_stream_running = False


# ---------------------------------------------------------------------------
# News stream
# ---------------------------------------------------------------------------

def start_news_stream(tickers: list | None = None) -> None:
    """Start streaming real-time news. Pass None for all market news.

    Non-blocking — spawns a daemon thread.
    """
    if not is_configured():
        log.info("Alpaca not configured — skipping news stream")
        return

    thread = threading.Thread(
        target=_run_news_stream, args=(tickers,), daemon=True, name="alpaca-news"
    )
    thread.start()
    log.info(f"Alpaca news stream started (tickers={tickers or 'ALL'})")


def _run_news_stream(tickers: list | None) -> None:
    """Internal: run the Alpaca news WebSocket stream (blocking inside thread)."""
    try:
        from alpaca.data.live import NewsDataStream  # type: ignore

        stream = NewsDataStream(_config["api_key"], _config["secret_key"])

        async def on_news(news):
            data = {
                "headline": getattr(news, "headline", ""),
                "summary": getattr(news, "summary", ""),
                "source": getattr(news, "source", ""),
                "symbols": list(news.symbols) if hasattr(news, "symbols") else [],
                "url": getattr(news, "url", ""),
                "created_at": (
                    news.created_at.isoformat() if hasattr(news, "created_at") else ""
                ),
            }
            _news_cache.insert(0, data)
            if len(_news_cache) > 50:
                _news_cache.pop()
            _broadcast("news", data)

        if tickers:
            stream.subscribe_news(on_news, *[t.upper() for t in tickers])
        else:
            stream.subscribe_news(on_news, "*")
        stream.run()
    except ImportError:
        log.warning("alpaca-py not installed — run: pip install alpaca-py")
    except Exception as e:
        log.error(f"Alpaca news stream error: {e}")


# ---------------------------------------------------------------------------
# REST fallback (single-call, no stream)
# ---------------------------------------------------------------------------

def get_news_alpaca(tickers: list, days: int = 2, limit: int = 20) -> list:
    """Fetch recent news via Alpaca REST API for given tickers.
    Returns list of {headline, source, symbols, url, created_at} dicts.
    """
    if not is_configured():
        return []
    try:
        from alpaca.data.historical.news import NewsClient  # type: ignore
        from alpaca.data.requests import NewsRequest        # type: ignore
        from datetime import datetime, timedelta

        client = NewsClient(_config["api_key"], _config["secret_key"])
        req = NewsRequest(
            symbols=",".join(t.upper() for t in tickers),
            start=datetime.utcnow() - timedelta(days=days),
            limit=limit,
        )
        news = client.get_news(req)
        articles = news.data.get("news", [])
        result = []
        for a in articles:
            result.append({
                "headline":   getattr(a, "headline", ""),
                "summary":    getattr(a, "summary", ""),
                "source":     getattr(a, "source", ""),
                "symbols":    list(getattr(a, "symbols", [])),
                "url":        getattr(a, "url", ""),
                "created_at": str(getattr(a, "created_at", "")),
            })
        _news_cache[:] = result + _news_cache
        if len(_news_cache) > 50:
            del _news_cache[50:]
        return result
    except ImportError:
        log.warning("alpaca-py not installed — run: pip install alpaca-py")
        return []
    except Exception as e:
        log.debug(f"Alpaca news fetch: {e}")
        return []


def get_live_price_alpaca(ticker: str) -> float | None:
    """Fetch real-time price via Alpaca REST API (single call, not streaming).

    Returns None if Alpaca is not configured or the call fails.
    """
    if not is_configured():
        return None
    try:
        from alpaca.data.historical import StockHistoricalDataClient  # type: ignore
        from alpaca.data.requests import StockLatestBarRequest  # type: ignore

        client = StockHistoricalDataClient(_config["api_key"], _config["secret_key"])
        request = StockLatestBarRequest(symbol_or_symbols=ticker.upper())
        bars = client.get_stock_latest_bar(request)
        bar = bars.get(ticker.upper())
        if bar:
            return float(bar.close)
        return None
    except ImportError:
        log.warning("alpaca-py not installed — run: pip install alpaca-py")
        return None
    except Exception as e:
        log.debug(f"Alpaca REST price {ticker}: {e}")
        return None
