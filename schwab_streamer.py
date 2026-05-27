"""
schwab_streamer.py · Real-time Schwab Streamer WebSocket client.

Wraps the Schwab Streaming API for LEVELONE_OPTIONS (NBBO) + OPTIONS (T&S).
Uses the existing brokerage refresh token — free, no extra subscription.

Architecture:
  1. start_stream(symbols) — call /v1/userpreference, open WS, LOGIN,
     SUBS to LEVELONE_OPTIONS for the given OCC symbols.
  2. Incoming messages parsed and pushed onto an asyncio.Queue.
  3. Server's SSE endpoint pulls from the queue and streams to browsers.

Protocol (Schwab Trader API v1, post-2024-03 migration):
  Login frame:
    {"requests":[{"service":"ADMIN","command":"LOGIN","SchwabClientCustomerId":"...",
     "SchwabClientCorrelId":"...","parameters":{"Authorization":"<bearer>",
     "SchwabClientChannel":"...","SchwabClientFunctionId":"..."}}]}
  Subscribe frame:
    {"requests":[{"service":"LEVELONE_OPTIONS","command":"SUBS",
     "SchwabClientCustomerId":"...","SchwabClientCorrelId":"...",
     "parameters":{"keys":"AAPL  240517C00200000,...","fields":"0,1,2,..."}}]}
  Heartbeat: server sends {"notify":[{"heartbeat":"<epoch_ms>"}]} every ~30s.

Service field map (LEVELONE_OPTIONS):
  0 = symbol, 1 = description, 2 = bid, 3 = ask, 4 = last,
  5 = high, 6 = low, 7 = close, 8 = total_volume, 9 = open_interest,
  10 = volatility, 11 = money_intrinsic_value, 12 = expiration_year,
  13 = multiplier, 14 = digits, 15 = open_price, 16 = bid_size,
  17 = ask_size, 18 = last_size, 19 = net_change, 20 = strike_price,
  21 = contract_type, 22 = underlying, 23 = expiration_month,
  24 = deliverables, 25 = time_value, 26 = expiration_day, 27 = days_to_exp,
  28 = delta, 29 = gamma, 30 = theta, 31 = vega, 32 = rho,
  33 = security_status, 34 = theoretical, 35 = underlying_price,
  36 = uv_expiration_type, 37 = mark, 38 = quote_time, 39 = trade_time,
  40 = exchange, 41 = exchange_name, 42 = last_trading_day,
  43 = settlement_type, 44 = net_pct_change, 45 = mark_pct_change

This module exposes:
  · start_stream(symbols, on_tick) — entry point used by FastAPI
  · stop_stream() — clean teardown
  · subscribe(symbols), unsubscribe(symbols) — dynamic mgmt
  · _stream_status() — for /api/options-stream/status endpoint
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
import uuid
from typing import Awaitable, Callable, Iterable

log = logging.getLogger("schwab_streamer")

# In-memory state — single connection per process
_state = {
    "ws":              None,
    "connected":       False,
    "logged_in":       False,
    "last_heartbeat":  None,
    "subscribed":      set(),  # OCC symbols
    "queue":           None,   # asyncio.Queue for SSE bridge
    "task":            None,
    "streamer_info":   None,
    "request_id":      0,
}

# Schwab LEVELONE_OPTIONS field map — the 46 fields we want streamed.
# Comma-separated string of field indices.
_FIELDS_LEVELONE = ",".join(str(i) for i in range(46))


def _request_id() -> str:
    _state["request_id"] += 1
    return str(_state["request_id"])


async def _fetch_streamer_info() -> dict | None:
    """Hit /v1/userpreference and extract streamerInfo[0] block.

    Returns dict with streamerSocketUrl, schwabClientCustomerId,
    schwabClientCorrelId, schwabClientChannel, schwabClientFunctionId.
    """
    try:
        import schwab_auth
        access = schwab_auth.refresh_access_token()
        if not access:
            log.warning("No Schwab access token — cannot fetch streamer info")
            return None
        import urllib.request
        req = urllib.request.Request(
            "https://api.schwabapi.com/trader/v1/userPreference",
            headers={"Authorization": f"Bearer {access}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        streamer = (data.get("streamerInfo") or [{}])[0]
        if not streamer:
            log.warning("userPreference returned no streamerInfo")
            return None
        _state["streamer_info"] = streamer
        _state["_access_token"] = access
        log.info(f"Streamer URL: {streamer.get('streamerSocketUrl', '')[:60]}...")
        return streamer
    except Exception as e:
        log.error(f"_fetch_streamer_info failed: {e}")
        return None


def _correl_ids() -> dict:
    si = _state.get("streamer_info") or {}
    return {
        "SchwabClientCustomerId": si.get("schwabClientCustomerId"),
        "SchwabClientCorrelId":   si.get("schwabClientCorrelId"),
    }


def _login_payload() -> dict:
    si = _state.get("streamer_info") or {}
    access = _state.get("_access_token")
    return {
        "requests": [{
            "service":  "ADMIN",
            "command":  "LOGIN",
            "requestid": _request_id(),
            **_correl_ids(),
            "parameters": {
                "Authorization":          access,
                "SchwabClientChannel":    si.get("schwabClientChannel"),
                "SchwabClientFunctionId": si.get("schwabClientFunctionId"),
            },
        }]
    }


def _subs_payload(symbols: Iterable[str], command: str = "SUBS") -> dict:
    keys = ",".join(symbols)
    return {
        "requests": [{
            "service":   "LEVELONE_OPTIONS",
            "command":   command,    # SUBS | ADD | UNSUBS
            "requestid": _request_id(),
            **_correl_ids(),
            "parameters": {
                "keys":   keys,
                "fields": _FIELDS_LEVELONE,
            },
        }]
    }


def _parse_levelone_msg(msg: dict, queue: asyncio.Queue) -> None:
    """Decode a LEVELONE_OPTIONS data frame and enqueue normalized ticks.

    Schwab sends compact field-id maps: {"1": value, "2": value, ...}.
    We translate to named fields for the SSE bridge.
    """
    if "data" not in msg: return
    for envelope in msg["data"]:
        if envelope.get("service") != "LEVELONE_OPTIONS": continue
        for row in envelope.get("content", []):
            tick = {
                "symbol":      row.get("key") or row.get("0"),
                "description": row.get("1"),
                "bid":         row.get("2"),
                "ask":         row.get("3"),
                "last":        row.get("4"),
                "vol":         row.get("8"),
                "oi":          row.get("9"),
                "iv":          row.get("10"),
                "delta":       row.get("28"),
                "gamma":       row.get("29"),
                "theta":       row.get("30"),
                "vega":        row.get("31"),
                "mark":        row.get("37"),
                "underlying":  row.get("22"),
                "underlying_price": row.get("35"),
                "ts":          time.time(),
            }
            try:
                queue.put_nowait(tick)
            except asyncio.QueueFull:
                # Drop oldest if queue saturates (256-cap on SSE bridge)
                try: queue.get_nowait()
                except Exception: pass
                queue.put_nowait(tick)


async def _stream_loop(initial_symbols: list[str]) -> None:
    """Open WS, LOGIN, SUBS, then read messages forever (with reconnect)."""
    try:
        import websockets
    except ImportError:
        log.error("websockets package not installed: pip3 install websockets")
        return
    queue = _state["queue"] or asyncio.Queue(maxsize=256)
    _state["queue"] = queue
    backoff = 1
    while True:
        try:
            si = await _fetch_streamer_info()
            if not si:
                log.warning(f"streamer info unavailable — retrying in {backoff}s")
                await asyncio.sleep(backoff); backoff = min(backoff*2, 60); continue
            url = si["streamerSocketUrl"]
            log.info(f"Connecting to streamer at {url[:60]}...")
            async with websockets.connect(url, max_size=2**22) as ws:
                _state["ws"] = ws
                _state["connected"] = True
                # LOGIN
                await ws.send(json.dumps(_login_payload()))
                # SUBS for initial symbols
                if initial_symbols:
                    await ws.send(json.dumps(_subs_payload(initial_symbols, "SUBS")))
                    _state["subscribed"].update(initial_symbols)
                backoff = 1
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    # Response frames: {"response":[{...}]}
                    if "response" in msg:
                        for r in msg["response"]:
                            if r.get("command") == "LOGIN":
                                code = (r.get("content") or {}).get("code")
                                if code == 0:
                                    _state["logged_in"] = True
                                    log.info("Streamer LOGIN OK")
                                else:
                                    log.error(f"Streamer LOGIN failed: {r}")
                            elif r.get("command") in ("SUBS","ADD","UNSUBS"):
                                log.debug(f"Service {r.get('service')} {r.get('command')} → {r.get('content')}")
                    # Heartbeat
                    elif "notify" in msg:
                        for n in msg["notify"]:
                            if "heartbeat" in n:
                                _state["last_heartbeat"] = int(n["heartbeat"])
                    # Data
                    elif "data" in msg:
                        _parse_levelone_msg(msg, queue)
        except Exception as e:
            log.warning(f"Streamer loop error: {e} — reconnecting in {backoff}s")
            _state["connected"] = False
            _state["logged_in"] = False
            await asyncio.sleep(backoff)
            backoff = min(backoff*2, 60)
        finally:
            _state["ws"] = None
            _state["connected"] = False


def start_stream(symbols: list[str]) -> dict:
    """Public entry — kicks off the WS loop on the running event loop.

    Idempotent: returns current status if already running.
    """
    if _state.get("task") and not _state["task"].done():
        # Already running — just subscribe new symbols
        if symbols:
            asyncio.create_task(_subscribe_more(symbols))
        return {"status": "already_running", "subscribed_count": len(_state["subscribed"])}
    if _state.get("queue") is None:
        _state["queue"] = asyncio.Queue(maxsize=256)
    _state["task"] = asyncio.create_task(_stream_loop(list(symbols)))
    return {"status": "starting", "symbols_requested": len(symbols)}


async def _subscribe_more(symbols: list[str]) -> None:
    ws = _state.get("ws")
    if not ws or not _state.get("logged_in"): return
    new = [s for s in symbols if s not in _state["subscribed"]]
    if not new: return
    await ws.send(json.dumps(_subs_payload(new, "ADD")))
    _state["subscribed"].update(new)


def stop_stream() -> dict:
    task = _state.get("task")
    if task and not task.done():
        task.cancel()
    _state["task"] = None
    _state["connected"] = False
    _state["logged_in"] = False
    _state["subscribed"].clear()
    return {"status": "stopped"}


def get_status() -> dict:
    return {
        "connected":   _state.get("connected", False),
        "logged_in":   _state.get("logged_in", False),
        "subscribed":  len(_state.get("subscribed", set())),
        "subscribed_symbols": list(_state.get("subscribed", set())),
        "queue_depth": _state["queue"].qsize() if _state.get("queue") else 0,
        "last_heartbeat": _state.get("last_heartbeat"),
        "uptime_ok":  _state.get("last_heartbeat") is not None
                      and (int(time.time()*1000) - (_state.get("last_heartbeat") or 0)) < 60_000,
    }


def get_queue() -> asyncio.Queue | None:
    return _state.get("queue")


# Helper: build OCC symbol from (ticker, exp, side, strike)
# Schwab uses 21-char OCC: "TICKER " padded to 6 chars + YYMMDD + C/P + 8-digit strike × 1000
def build_occ(ticker: str, exp_yyyy_mm_dd: str, side: str, strike: float) -> str:
    tk = ticker.upper().ljust(6)
    exp = exp_yyyy_mm_dd.replace("-", "")[2:]  # YYMMDD
    side_code = "C" if side.lower().startswith("c") else "P"
    strike_int = int(round(strike * 1000))
    return f"{tk}{exp}{side_code}{strike_int:08d}"
