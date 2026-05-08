"""FastAPI-based SwingTrade server. Port 7432. Auto-reload in dev."""
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn, os, json, secrets
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
app = FastAPI(title="SwingTrade", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Gzip compression — reduces 28MB → ~3MB transfer
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# -- Basic Auth (file-backed user/role store via auth.py, 2026-05-07 migration) --
_security = HTTPBasic()
import auth as _auth_mod
_auth_mod.ensure_seed()  # creates data/users.json from defaults if missing


# ── Session-idle tracking (Phase 2 — 2026-05-08) ──────────────────────────
# Browser caches Basic Auth indefinitely. Without active expiry, an
# unlocked laptop = open dashboard. We track per-user last-activity
# in-process; when last activity > _SESSION_IDLE_TIMEOUT, we return 401
# (forcing browser to re-prompt for credentials). Frontend has an idle
# timer that warns + reloads to trigger the re-auth.
import time as _time
import threading as _threading
_SESSION_IDLE_TIMEOUT = 30 * 60  # 30 minutes
_session_last_activity: dict[str, float] = {}
_session_lock = _threading.Lock()

def _session_check_and_bump(username: str) -> bool:
    """Returns True if session is fresh (or new). False if expired."""
    now = _time.time()
    with _session_lock:
        last = _session_last_activity.get(username)
        if last is not None and (now - last) > _SESSION_IDLE_TIMEOUT:
            # Expired — caller should reject. Reset so next valid auth bumps fresh.
            _session_last_activity.pop(username, None)
            return False
        _session_last_activity[username] = now
        return True


def _check_auth(credentials: HTTPBasicCredentials = Depends(_security)):
    user = _auth_mod.verify_user(credentials.username, credentials.password)
    if not user:
        from fastapi.responses import Response
        return Response(status_code=401, headers={"WWW-Authenticate": "Basic"},
                        content="Unauthorized")
    # Idle timeout check (skip the bump if the session is already expired —
    # we don't auto-renew without an active request, but each successful
    # request DOES bump the timer).
    if not _session_check_and_bump(credentials.username):
        from fastapi.responses import Response
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": "Basic", "X-Session-Expired": "idle-timeout"},
            content="Session expired (30 min idle). Re-authenticate.",
        )
    # Update last_login timestamp (best-effort, non-blocking on failure)
    try:
        _auth_mod.set_last_login(credentials.username)
    except Exception:
        pass
    return credentials


def _require_admin(credentials: HTTPBasicCredentials = Depends(_security)):
    """Dependency that authenticates AND requires admin role."""
    user = _auth_mod.verify_user(credentials.username, credentials.password)
    if not user:
        from fastapi.responses import Response
        return Response(status_code=401, headers={"WWW-Authenticate": "Basic"},
                        content="Unauthorized")
    if not _session_check_and_bump(credentials.username):
        from fastapi.responses import Response
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": "Basic", "X-Session-Expired": "idle-timeout"},
            content="Session expired (30 min idle). Re-authenticate.",
        )
    if not _auth_mod.is_admin(credentials.username):
        from fastapi.responses import Response
        return Response(status_code=403, content="Admin role required")
    return credentials


def _require_action(action: str):
    """Dependency factory: requires a specific action permission.

    Usage:  Depends(_require_action("submit_trade"))

    Admins always pass. Non-admins must have the action in their role's
    permissions.actions list, OR have wildcard '*'. Returns 403 with the
    action name in the body so the frontend can surface why a click failed.

    Side effect: every call (allow OR deny) is recorded in the audit log
    via audit_log.log_action(). Forensic trail for write actions across
    all users. (Phase 2 — 2026-05-08, role enforcement; 2026-05-08 audit
    log added.)
    """
    def _dep(request: Request, credentials: HTTPBasicCredentials = Depends(_security)):
        from fastapi.responses import Response
        import audit_log as _alog
        user = _auth_mod.verify_user(credentials.username, credentials.password)
        ip = request.client.host if request.client else ""
        ua = request.headers.get("user-agent", "")
        endpoint = request.url.path
        method = request.method
        if not user:
            _alog.log_action(user=credentials.username or "?", action=action,
                              endpoint=endpoint, method=method,
                              ip=ip, user_agent=ua, status="denied",
                              error="Unauthorized")
            return Response(status_code=401, headers={"WWW-Authenticate": "Basic"},
                            content="Unauthorized")
        if not _session_check_and_bump(credentials.username):
            _alog.log_action(user=credentials.username, action=action,
                              endpoint=endpoint, method=method,
                              ip=ip, user_agent=ua, status="denied",
                              error="Session expired (30 min idle)")
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": "Basic", "X-Session-Expired": "idle-timeout"},
                content="Session expired (30 min idle). Re-authenticate.",
            )
        is_adm = _auth_mod.is_admin(credentials.username)
        has_perm = is_adm or _auth_mod.user_has_permission(credentials.username, "actions", action)
        if not has_perm:
            _alog.log_action(user=credentials.username, action=action,
                              endpoint=endpoint, method=method,
                              ip=ip, user_agent=ua, status="denied",
                              error=f"action '{action}' not allowed for role")
            return Response(status_code=403,
                            content=f"Forbidden: action '{action}' not allowed for your role")
        # Audit successful authorization. Note: we log BEFORE the handler runs
        # so even if the handler crashes, we still know the action was attempted.
        _alog.log_action(user=credentials.username, action=action,
                          endpoint=endpoint, method=method,
                          ip=ip, user_agent=ua, status="ok")
        return credentials
    return _dep

# -- Serve prototype (new-design dashboard) at /v2/ behind same auth --
from fastapi.responses import FileResponse, Response
_PROTOTYPE_DIR = BASE_DIR / "infra" / "prototype"
_MIME = {".html":"text/html",".css":"text/css",".js":"application/javascript",
         ".json":"application/json",".svg":"image/svg+xml",".png":"image/png",
         ".jpg":"image/jpeg",".woff":"font/woff",".woff2":"font/woff2"}

@app.api_route("/v2", methods=["GET","HEAD"])
async def _v2_root(auth: HTTPBasicCredentials = Depends(_check_auth)):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/v2/dashboard.html")

@app.api_route("/v2/{path:path}", methods=["GET","HEAD"])
async def _v2_file(path: str, request: Request, auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    # Empty path (trailing slash on /v2/) → redirect to dashboard.html, same as /v2
    if not path:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/v2/dashboard.html")
    full = (_PROTOTYPE_DIR / path).resolve()
    # path traversal guard
    if not str(full).startswith(str(_PROTOTYPE_DIR.resolve())):
        raise HTTPException(403)
    if not full.exists() or not full.is_file():
        raise HTTPException(404)
    suffix = full.suffix.lower()

    import time, hashlib
    mtime = int(full.stat().st_mtime)
    etag = f'W/"{hashlib.md5(f"{full.name}-{mtime}".encode()).hexdigest()[:16]}"'
    last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(mtime))

    # ETag short-circuit — browser sent a hash of what it has cached. If unchanged,
    # return 304 with no body (<100 bytes) instead of re-sending the file.
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        return Response(status_code=304, headers={
            "ETag": etag, "Last-Modified": last_modified,
            "Cache-Control": "private, must-revalidate, max-age=0",
        })

    # JSON files (data.json, tickers.json) only change after a scan once per day.
    # Use ETag revalidation so browser keeps the file and asks "is it stale?" on each
    # load — server replies 304 when unchanged (tiny) instead of re-sending megabytes.
    # HTML/JS/CSS keep no-store so code edits surface instantly without hard-refresh.
    if suffix == ".json":
        headers = {
            "Cache-Control":      "private, must-revalidate, max-age=0",
            "Last-Modified":      last_modified,
            "ETag":                etag,
        }
    else:
        headers = {
            "Cache-Control":      "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma":              "no-cache",
            "Expires":              "0",
            "Last-Modified":       last_modified,
            "ETag":                 etag,
            "CDN-Cache-Control":   "no-store",
            "Cloudflare-CDN-Cache-Control": "no-store",
        }
    # JSON files: read content and return as Response so GZipMiddleware
    # compresses them (~92% on data.json, ~71% on tickers.json). FileResponse
    # uses sendfile() which can bypass middleware; that's fine for HTML/JS/CSS
    # but we want compression on the multi-MB JSON payloads. (2026-05-08)
    if suffix == ".json":
        body = full.read_bytes()
        return Response(content=body, media_type=_MIME.get(suffix, "application/json"), headers=headers)
    return FileResponse(full, media_type=_MIME.get(suffix, "application/octet-stream"), headers=headers)

# -- Redirect / to V2 dashboard (Phase A: legacy cache/dashboard.html retired
#    2026-05-08; V2 at /v2/dashboard.html is the only authoritative surface).
#    Existing bookmarks to / keep working — they just bounce to V2. --
from fastapi.responses import RedirectResponse

@app.get("/")
async def root(auth: HTTPBasicCredentials = Depends(_check_auth)):
    return RedirectResponse(url="/v2/dashboard.html", status_code=302)

_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}

# Phase B (2026-05-08): /dashboard.css, /dashboard.js, /dashboard-data.js
# routes removed. They served legacy assets that haven't been generated
# since Phase A retired html_generator. Anyone hitting these gets a clean
# 404 from FastAPI's default handler.

# -- Portfolio --
@app.get("/api/ohlcv/{ticker}")
async def ohlcv_api(ticker: str, days: int = 120, tf: str = "1D"):
    """Return OHLCV + Supertrend + EMA series for charting.
    tf: 1H, 4H, 1D, 1W"""
    ticker = ticker.upper().strip()
    try:
        import numpy as np, pandas as pd
        df = None
        if tf == "1H":
            from data_fetcher import get_polygon_ohlcv
            df = get_polygon_ohlcv(ticker, days=min(days, 30), timespan="hour", multiplier=1)
        elif tf == "4H":
            from data_fetcher import get_polygon_ohlcv
            df = get_polygon_ohlcv(ticker, days=min(days, 60), timespan="hour", multiplier=4)
        elif tf == "1W":
            from data_fetcher import get_polygon_ohlcv
            df = get_polygon_ohlcv(ticker, days=min(days, 730), timespan="week", multiplier=1)
        if df is None or (hasattr(df, 'empty') and df.empty):
            from data_fetcher import fetch_ohlcv_with_failover
            # Intraday (1H/4H) via EODHD intraday endpoint
            if tf in ("1H", "4H"):
                try:
                    import eodhd_client as _eod_intra
                    _interval = "1h"  # EODHD supports 1m, 5m, 1h
                    rows = _eod_intra.intraday(ticker, interval=_interval)
                    if rows:
                        df = pd.DataFrame(rows)
                        if "datetime" in df.columns:
                            df["datetime"] = pd.to_datetime(df["datetime"])
                            df = df.set_index("datetime").sort_index()
                        df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
                        if tf == "4H" and not df.empty:
                            df = df.resample("4h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
                except Exception:
                    pass
            if df is None or (hasattr(df, 'empty') and df.empty):
                df, _ = fetch_ohlcv_with_failover(ticker, days=days)
        if df is None or df.empty:
            raise HTTPException(404, f"No OHLCV data for {ticker}")
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()
        # EMAs
        ema5 = c.ewm(span=5, adjust=False).mean()
        ema13 = c.ewm(span=13, adjust=False).mean()
        ema21 = c.ewm(span=21, adjust=False).mean()
        ema50 = c.ewm(span=50, adjust=False).mean()
        # Supertrend (10, 3)
        atr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1).rolling(10).mean()
        hl2 = (h + l) / 2
        ub = hl2 + 3 * atr
        lb = hl2 - 3 * atr
        fub, flb = ub.copy(), lb.copy()
        st_dir = pd.Series(1, index=df.index)
        st_val = flb.copy()
        for i in range(11, len(df)):
            if pd.isna(fub.iloc[i-1]) or pd.isna(flb.iloc[i-1]):
                continue
            fub.iloc[i] = ub.iloc[i] if (ub.iloc[i] < fub.iloc[i-1] or c.iloc[i-1] > fub.iloc[i-1]) else fub.iloc[i-1]
            flb.iloc[i] = lb.iloc[i] if (lb.iloc[i] > flb.iloc[i-1] or c.iloc[i-1] < flb.iloc[i-1]) else flb.iloc[i-1]
        for i in range(11, len(df)):
            if pd.isna(flb.iloc[i]) or pd.isna(fub.iloc[i]):
                continue
            if st_dir.iloc[i-1] == 1:
                if c.iloc[i] < flb.iloc[i]:
                    st_dir.iloc[i] = -1; st_val.iloc[i] = fub.iloc[i]
                else:
                    st_dir.iloc[i] = 1; st_val.iloc[i] = flb.iloc[i]
            else:
                if c.iloc[i] > fub.iloc[i]:
                    st_dir.iloc[i] = 1; st_val.iloc[i] = flb.iloc[i]
                else:
                    st_dir.iloc[i] = -1; st_val.iloc[i] = fub.iloc[i]
        import math
        def _ts(idx):
            if hasattr(idx, 'timestamp'):
                return int(idx.timestamp())
            return int(pd.Timestamp(idx).timestamp())
        # VWAP (cumulative)
        vol = df["Volume"].squeeze()
        cum_vol = vol.cumsum()
        cum_pv = (c * vol).cumsum()
        vwap_series = cum_pv / cum_vol.replace(0, np.nan)

        # Bollinger Bands (20, 2)
        bb_mid = c.rolling(20).mean()
        bb_std = c.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std

        # RSI (14)
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs_ratio = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs_ratio))

        # MACD (12, 26, 9)
        macd_line = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal

        # 5/13 EMA crossover arrows
        cross_buy = []
        cross_sell = []
        for i in range(1, len(df)):
            e5_prev, e5_cur = float(ema5.iloc[i-1]), float(ema5.iloc[i])
            e13_prev, e13_cur = float(ema13.iloc[i-1]), float(ema13.iloc[i])
            if e5_prev <= e13_prev and e5_cur > e13_cur:
                cross_buy.append({"time": _ts(df.index[i]), "price": round(float(l.iloc[i]) * 0.995, 2)})
            elif e5_prev >= e13_prev and e5_cur < e13_cur:
                cross_sell.append({"time": _ts(df.index[i]), "price": round(float(h.iloc[i]) * 1.005, 2)})

        candles = []
        vol_data = []
        st_bull = []
        st_bear = []
        vwap_data = []
        bb_upper_data = []
        bb_lower_data = []
        rsi_data = []
        macd_line_data = []
        macd_signal_data = []
        macd_hist_data = []
        ema_data = {"ema5": [], "ema13": [], "ema21": [], "ema50": []}
        for i in range(len(df)):
            ts = _ts(df.index[i])
            _o = round(float(df["Open"].iloc[i]), 2)
            _c = round(float(c.iloc[i]), 2)
            _h = round(float(h.iloc[i]), 2)
            _l = round(float(l.iloc[i]), 2)
            candles.append({"time": ts, "open": _o, "high": _h, "low": _l, "close": _c})
            # Volume bars (colored by candle direction)
            _v = float(vol.iloc[i])
            vol_data.append({"time": ts, "value": _v, "color": "rgba(34,197,94,0.4)" if _c >= _o else "rgba(239,68,68,0.3)"})
            # Supertrend
            sv = float(st_val.iloc[i])
            if not (math.isnan(sv) or math.isinf(sv)):
                if st_dir.iloc[i] == 1:
                    st_bull.append({"time": ts, "value": round(sv, 2)})
                else:
                    st_bear.append({"time": ts, "value": round(sv, 2)})
            # VWAP
            _vw = float(vwap_series.iloc[i]) if not pd.isna(vwap_series.iloc[i]) else None
            if _vw and not math.isinf(_vw):
                vwap_data.append({"time": ts, "value": round(_vw, 2)})
            # Bollinger Bands
            _bbu = float(bb_upper.iloc[i]) if not pd.isna(bb_upper.iloc[i]) else None
            _bbl = float(bb_lower.iloc[i]) if not pd.isna(bb_lower.iloc[i]) else None
            if _bbu and not math.isinf(_bbu):
                bb_upper_data.append({"time": ts, "value": round(_bbu, 2)})
            if _bbl and not math.isinf(_bbl):
                bb_lower_data.append({"time": ts, "value": round(_bbl, 2)})
            # RSI
            _rsi = float(rsi_series.iloc[i]) if not pd.isna(rsi_series.iloc[i]) else None
            if _rsi and not math.isinf(_rsi):
                rsi_data.append({"time": ts, "value": round(_rsi, 1)})
            # MACD
            for _ms, _md in [(macd_line, macd_line_data), (macd_signal, macd_signal_data), (macd_hist, macd_hist_data)]:
                _mv = float(_ms.iloc[i])
                if not (math.isnan(_mv) or math.isinf(_mv)):
                    _md.append({"time": ts, "value": round(_mv, 4)})
            # EMAs
            for name, series in [("ema5", ema5), ("ema13", ema13), ("ema21", ema21), ("ema50", ema50)]:
                v = float(series.iloc[i])
                if not (math.isnan(v) or math.isinf(v)):
                    ema_data[name].append({"time": ts, "value": round(v, 2)})
        # Volume Profile — histogram of volume at each price level
        vp_bins = 40
        price_min, price_max = float(l.min()), float(h.max())
        price_range = price_max - price_min
        if price_range > 0:
            bin_size = price_range / vp_bins
            vp_hist = []
            for b in range(vp_bins):
                bin_low = price_min + b * bin_size
                bin_high = bin_low + bin_size
                bin_mid = (bin_low + bin_high) / 2
                # Sum volume where price traded through this level
                mask = (l <= bin_high) & (h >= bin_low)
                vol = float(df["Volume"][mask].sum()) if mask.any() else 0
                vp_hist.append({"price": round(bin_mid, 2), "volume": vol})
            total_vol = sum(b["volume"] for b in vp_hist)
            # POC = price level with highest volume
            poc_bin = max(vp_hist, key=lambda b: b["volume"])
            poc_price = poc_bin["price"]
            # Value Area (70% of volume centered on POC)
            sorted_bins = sorted(vp_hist, key=lambda b: b["volume"], reverse=True)
            va_vol = 0
            va_prices = []
            for b in sorted_bins:
                va_vol += b["volume"]
                va_prices.append(b["price"])
                if va_vol >= total_vol * 0.7:
                    break
            vah = max(va_prices)
            val_ = min(va_prices)
            # Normalize volumes to percentages
            for b in vp_hist:
                b["pct"] = round(b["volume"] / max(total_vol, 1) * 100, 2)
            vp_data = {"bins": vp_hist, "poc": round(poc_price, 2),
                       "vah": round(vah, 2), "val": round(val_, 2)}
        else:
            vp_data = {"bins": [], "poc": 0, "vah": 0, "val": 0}

        # Support/Resistance from fractals (simple pivot highs/lows)
        sr_levels = []
        if len(c) >= 20:
            try:
                _last = float(c.iloc[-1])
                # Find recent swing highs/lows (5-bar pivots)
                for i in range(-3, -min(60, len(c)), -1):
                    _h = float(h.iloc[i])
                    _l = float(l.iloc[i])
                    if i > -len(c)+2 and i < -2:
                        if _h >= float(h.iloc[i-1]) and _h >= float(h.iloc[i-2]) and _h >= float(h.iloc[i+1]) and _h >= float(h.iloc[i+2]):
                            sr_levels.append({"price": round(_h, 2), "type": "resistance" if _h > _last else "support"})
                        if _l <= float(l.iloc[i-1]) and _l <= float(l.iloc[i-2]) and _l <= float(l.iloc[i+1]) and _l <= float(l.iloc[i+2]):
                            sr_levels.append({"price": round(_l, 2), "type": "support" if _l < _last else "resistance"})
                sr_levels = sr_levels[:8]
            except Exception:
                pass

        # Price Action Concepts — Order Blocks + Fair Value Gaps
        order_blocks = []
        fvg_zones = []
        try:
            for i in range(2, len(df) - 1):
                _o = float(df["Open"].iloc[i])
                _c_i = float(c.iloc[i])
                _h_i = float(h.iloc[i])
                _l_i = float(l.iloc[i])
                _c_prev = float(c.iloc[i-1])
                _c_prev2 = float(c.iloc[i-2])
                # Bullish Order Block: down candle followed by strong up move
                if _c_prev < float(df["Open"].iloc[i-1]) and _c_i > _c_prev and _c_i > _c_prev2:
                    order_blocks.append({"time": _ts(df.index[i-1]), "high": round(float(df["Open"].iloc[i-1]), 2),
                                         "low": round(float(l.iloc[i-1]), 2), "type": "bull"})
                # Bearish Order Block: up candle followed by strong down move
                if _c_prev > float(df["Open"].iloc[i-1]) and _c_i < _c_prev and _c_i < _c_prev2:
                    order_blocks.append({"time": _ts(df.index[i-1]), "high": round(float(h.iloc[i-1]), 2),
                                         "low": round(float(df["Open"].iloc[i-1]), 2), "type": "bear"})
                # Fair Value Gap: gap between bar[i-2] and bar[i]
                if float(l.iloc[i]) > float(h.iloc[i-2]):
                    fvg_zones.append({"time": _ts(df.index[i-1]), "high": round(float(l.iloc[i]), 2),
                                      "low": round(float(h.iloc[i-2]), 2), "type": "bull"})
                elif float(h.iloc[i]) < float(l.iloc[i-2]):
                    fvg_zones.append({"time": _ts(df.index[i-1]), "high": round(float(l.iloc[i-2]), 2),
                                      "low": round(float(h.iloc[i]), 2), "type": "bear"})
            order_blocks = order_blocks[-10:]  # Keep last 10
            fvg_zones = fvg_zones[-10:]
        except Exception:
            pass

        # Previous day high/low/close + 52-week high/low
        prev_day = {}
        if len(df) >= 2:
            prev_day = {"high": round(float(h.iloc[-2]), 2), "low": round(float(l.iloc[-2]), 2),
                        "close": round(float(c.iloc[-2]), 2)}
        w52 = {"high": round(float(h.max()), 2), "low": round(float(l.min()), 2)}

        return {"ticker": ticker, "candles": candles, "volume": vol_data,
                "supertrend_bull": st_bull, "supertrend_bear": st_bear,
                "vwap": vwap_data, "bb_upper": bb_upper_data, "bb_lower": bb_lower_data,
                "rsi": rsi_data, "macd_line": macd_line_data, "macd_signal": macd_signal_data,
                "macd_hist": macd_hist_data, "cross_buy": cross_buy, "cross_sell": cross_sell,
                "volume_profile": vp_data, "sr_levels": sr_levels,
                "prev_day": prev_day, "week52": w52,
                "order_blocks": order_blocks, "fvg_zones": fvg_zones, **ema_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/portfolio")
async def portfolio_get():
    """Return current portfolio summary + positions for live rendering."""
    import portfolio_tracker as pt
    summary = pt.get_portfolio_summary()
    return summary

@app.post("/api/portfolio/add")
async def portfolio_add(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import portfolio_tracker as pt
    required = ["ticker", "entry", "shares", "stop", "target1"]
    missing = [k for k in required if k not in body]
    if missing:
        raise HTTPException(400, f"Missing fields: {', '.join(missing)}")
    try:
        pos = pt.add_position(
            ticker=str(body["ticker"]).upper(),
            entry_price=float(body["entry"]),
            shares=int(float(body["shares"])),
            stop=float(body["stop"]),
            target1=float(body["target1"]),
            target2=float(body["target2"]) if body.get("target2") else None,
            setup_type=str(body.get("setup", "")),
            direction=str(body.get("direction", "long")),
            allocation_pct=float(body.get("allocation_pct", 7.5)),
            notes=str(body.get("notes", "")),
            entry_date=body.get("entry_date"),
        )
        # Trigger dashboard regen so portfolio tab reflects the new position
        try:
            import subprocess
            _regen_log = open(BASE_DIR / "cache" / "logs" / "regen.log", "w")
            subprocess.Popen(
                ["python3", str(BASE_DIR / "swing_trade.py"), "regen"],
                cwd=str(BASE_DIR), stdout=_regen_log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            pass
        return {"ok": True, "position": pos}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/portfolio/close")
async def portfolio_close(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import portfolio_tracker as pt
    if "ticker" not in body or "exit_price" not in body:
        raise HTTPException(400, "Missing ticker or exit_price")
    try:
        result = pt.close_position(
            ticker=str(body["ticker"]).upper(),
            exit_price=float(body["exit_price"]),
            exit_reason=str(body.get("reason", "manual"))
        )
        return {"ok": True, "closed": result, "undo_id": result.get("undo_id"), "pnl_pct": result.get("pnl_pct")}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/portfolio/undo_close")
async def portfolio_undo(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return pt.undo_close(str(body.get("undo_id", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/set_equity")
async def portfolio_set_equity(req: Request, _: HTTPBasicCredentials = Depends(_require_action("edit_sizing"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.set_equity(float(body["equity"]), reason=str(body.get("reason", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/move_stop_be")
async def portfolio_move_stop_be(req: Request, _: HTTPBasicCredentials = Depends(_require_action("move_stops"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.move_stop_to_breakeven(str(body["ticker"]).upper())}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/trail_stop")
async def portfolio_trail_stop(req: Request, _: HTTPBasicCredentials = Depends(_require_action("move_stops"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.trail_stop(str(body["ticker"]).upper(), float(body.get("atr_mult", 1.5)))}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/partial_close")
async def portfolio_partial_close(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.partial_close(
            str(body["ticker"]).upper(),
            pct=float(body.get("pct", 0.5)),
            exit_price=float(body["exit_price"]) if body.get("exit_price") else None
        )}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/adjust_stop")
async def portfolio_adjust_stop(req: Request, _: HTTPBasicCredentials = Depends(_require_action("move_stops"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.adjust_stop(str(body["ticker"]).upper(), float(body["new_stop"]))}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/close_on_alpaca")
async def portfolio_close_on_alpaca(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    """Close an Alpaca paper position by submitting a market order to flatten.

    For LONG positions: market SELL the qty.
    For SHORT positions: market BUY the qty (buy-to-cover).
    Then update local portfolio_state.json to reflect the closed position.

    Body: {ticker: str}
    """
    body = await req.json()
    ticker = (body.get("ticker") or "").upper().strip()
    if not ticker:
        raise HTTPException(400, "ticker required")

    import json as _json
    from urllib.request import Request as _UReq, urlopen as _uopen
    from urllib.error import HTTPError, URLError
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    import portfolio_tracker as pt

    try:
        from secrets_loader import alpaca_key, alpaca_secret
        key = (alpaca_key() or "").strip()
        sec = (alpaca_secret() or "").strip()
    except Exception:
        import os as _os
        key = _os.environ.get("ALPACA_API_KEY", "").strip()
        sec = _os.environ.get("ALPACA_SECRET_KEY", "").strip()
    if not key or not sec or "YOUR_" in key:
        raise HTTPException(412, "Alpaca credentials not configured in .env")

    import os as _os
    base = _os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    hdrs = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Content-Type": "application/json"}

    # Fetch current position
    try:
        req_pos = _UReq(f"{base}/v2/positions/{ticker}", headers=hdrs)
        pos = _json.loads(_uopen(req_pos, timeout=10).read())
    except HTTPError as e:
        if e.code == 404:
            raise HTTPException(404, f"No open Alpaca position for {ticker}")
        raise HTTPException(502, f"Alpaca {e.code}: {e.read().decode()[:200]}")

    qty = abs(int(float(pos.get("qty") or 0)))
    side = (pos.get("side") or "long").lower()
    if qty == 0:
        raise HTTPException(400, f"{ticker}: zero qty, nothing to close")

    # Submit closing order
    close_side = "sell" if side == "long" else "buy"   # buy-to-cover for short
    order_body = _json.dumps({
        "symbol": ticker, "qty": str(qty), "side": close_side,
        "type": "market", "time_in_force": "day"
    }).encode()
    try:
        req_close = _UReq(f"{base}/v2/orders", headers=hdrs, data=order_body, method="POST")
        order = _json.loads(_uopen(req_close, timeout=10).read())
    except HTTPError as e:
        raise HTTPException(502, f"Alpaca close-order rejected ({e.code}): {e.read().decode()[:200]}")

    # Update local — record closed (use current_price as exit, sync will refine after fill)
    try:
        exit_px = float(pos.get("current_price") or pos.get("avg_entry_price") or 0)
        pt.close_position(ticker, exit_px, f"alpaca_close_{close_side}")
    except Exception:
        pass

    return {
        "ok": True,
        "ticker": ticker,
        "closed_side": close_side,
        "qty": qty,
        "submitted_order_id": order.get("id"),
        "status": order.get("status"),
        "message": f"Submitted market {close_side} {qty} {ticker} ({'flat long' if side == 'long' else 'buy-to-cover short'}). Refresh sync after fill to update local state.",
    }


@app.post("/api/portfolio/sync_alpaca")
async def portfolio_sync_alpaca(_: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    """Pull live Alpaca paper positions and mirror them into local portfolio_state.

    Strategy:
      1. Fetch /v2/account → cash, equity, buying_power
      2. Fetch /v2/positions → live open positions
      3. For each local position: if not in Alpaca → mark closed (Alpaca closed it)
      4. For each Alpaca position: if not in local → insert with defaults
      5. For all matches: update current_price + unrealized_pnl in-place
    """
    import json as _json
    from urllib.request import Request as _UReq, urlopen as _uopen
    from urllib.error import URLError, HTTPError
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    import portfolio_tracker as pt

    # Resolve creds via secrets_loader (reads .env directly)
    try:
        from secrets_loader import alpaca_key, alpaca_secret
        key = (alpaca_key() or "").strip()
        sec = (alpaca_secret() or "").strip()
    except Exception:
        import os as _os
        key = _os.environ.get("ALPACA_API_KEY", "").strip()
        sec = _os.environ.get("ALPACA_SECRET_KEY", "").strip()
    if not key or not sec or "YOUR_" in key:
        raise HTTPException(412, "Alpaca credentials not configured in .env")

    import os as _os
    base = _os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")

    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}

    def _alpaca_get(path: str):
        req = _UReq(f"{base}{path}", headers=headers)
        return _json.loads(_uopen(req, timeout=10).read())

    try:
        account = _alpaca_get("/v2/account")
        positions = _alpaca_get("/v2/positions")
    except HTTPError as e:
        raise HTTPException(502, f"Alpaca {e.code}: {e.read().decode()[:200]}")
    except URLError as e:
        raise HTTPException(502, f"Alpaca network error: {e}")

    # Load local state
    state_p = _Path("data/portfolio_state.json")
    state = _json.loads(state_p.read_text())
    local_positions = state.get("positions", [])
    local_by_ticker = {p["ticker"]: p for p in local_positions}
    alpaca_by_ticker = {p["symbol"]: p for p in positions}

    today = _dt.now().date().isoformat()
    closed = []
    updated = []
    inserted = []

    # 1. Local-only → mark closed (Alpaca closed it externally)
    for tk, lp in list(local_by_ticker.items()):
        if tk not in alpaca_by_ticker:
            try:
                # Use last known price as exit; if missing default to entry
                exit_px = float(lp.get("current_price") or lp.get("entry_price") or 0)
                pt.close_position(tk, exit_px, "alpaca_external_close")
                closed.append(tk)
            except Exception:
                pass

    # Reload after closes
    state = _json.loads(state_p.read_text())
    local_positions = state.get("positions", [])
    local_by_ticker = {p["ticker"]: p for p in local_positions}

    # 2. Alpaca-only → insert into local with defaults
    # 3. Both sides → update current_price + unrealized_pnl
    for sym, ap in alpaca_by_ticker.items():
        avg_entry = float(ap.get("avg_entry_price") or 0)
        cur_price = float(ap.get("current_price") or 0)
        qty = abs(int(float(ap.get("qty") or 0)))
        side = (ap.get("side") or "long").lower()
        if sym in local_by_ticker:
            # Update in place
            lp = local_by_ticker[sym]
            lp["current_price"] = round(cur_price, 2)
            lp["unrealized_pnl_dollars"] = round(float(ap.get("unrealized_pl") or 0), 2)
            lp["unrealized_pnl_pct"] = round(float(ap.get("unrealized_plpc") or 0) * 100, 2)
            lp["last_updated"] = today
            updated.append(sym)
        else:
            # Insert — use sane stop/target defaults (3% / 5%)
            stop = round(avg_entry * (0.97 if side == "long" else 1.03), 2)
            target = round(avg_entry * (1.05 if side == "long" else 0.95), 2)
            try:
                pt.add_position(
                    ticker=sym, entry_price=avg_entry, shares=qty,
                    stop=stop, target1=target, target2=None,
                    setup_type="alpaca_sync", direction=side,
                    allocation_pct=round(qty * avg_entry / max(1, float(account.get("equity") or 100000)) * 100, 1),
                    notes="Synced from Alpaca paper account",
                )
                inserted.append(sym)
            except Exception as e:
                pass

    # Sync equity/cash from Alpaca
    state = _json.loads(state_p.read_text())
    state["equity"] = round(float(account.get("equity") or 0), 2)
    state["cash"] = round(float(account.get("cash") or 0), 2)
    state["buying_power"] = round(float(account.get("buying_power") or 0), 2)
    state["last_alpaca_sync"] = _dt.now().isoformat()
    state["alpaca_account"] = (account.get("account_number") or "")[:6] + "***"
    state_p.write_text(_json.dumps(state, indent=2))

    # Return the fresh portfolio block so the dashboard can update DATA.portfolio
    # without waiting for a full data.json rebuild.
    return {
        "ok": True,
        "synced_at": state["last_alpaca_sync"],
        "alpaca_account": state["alpaca_account"],
        "equity": state["equity"],
        "cash": state["cash"],
        "buying_power": state["buying_power"],
        "alpaca_positions": len(positions),
        "local_positions_after": len(state.get("positions", [])),
        "closed": closed,
        "updated": updated,
        "inserted": inserted,
        "portfolio": {
            "equity": state.get("equity"),
            "cash": state.get("cash"),
            "buying_power": state.get("buying_power"),
            "positions": state.get("positions", []),
            "closed": state.get("closed_trades", []),
        },
    }


@app.post("/api/portfolio/update_notes")
async def portfolio_update_notes(req: Request, _: HTTPBasicCredentials = Depends(_require_action("edit_watchlist"))):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.update_notes(str(body["ticker"]).upper(), str(body.get("notes", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))

# -- Position tracker (actual trades) --
@app.post("/api/positions/open")
async def positions_open(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import position_tracker as pt
    required = ["ticker", "entry_price", "shares", "stop", "target1"]
    missing = [k for k in required if k not in body]
    if missing:
        raise HTTPException(400, f"Missing fields: {', '.join(missing)}")
    result = pt.open_position(
        ticker=str(body["ticker"]).upper(),
        entry_price=float(body["entry_price"]),
        shares=int(float(body["shares"])),
        stop=float(body["stop"]),
        target1=float(body["target1"]),
        target2=float(body["target2"]) if body.get("target2") else None,
        setup_type=str(body.get("setup_type", "")),
        notes=str(body.get("notes", "")),
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed"))
    return result

@app.post("/api/positions/close")
async def positions_close(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import position_tracker as pt
    if "ticker" not in body or "exit_price" not in body:
        raise HTTPException(400, "Missing ticker or exit_price")
    result = pt.close_position(
        ticker=str(body["ticker"]).upper(),
        exit_price=float(body["exit_price"]),
        notes=str(body.get("notes", "")),
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed"))
    return result

@app.get("/api/positions/open")
async def positions_list_open():
    import position_tracker as pt
    return {"positions": pt.get_open_positions()}

@app.get("/api/positions/closed")
async def positions_list_closed():
    import position_tracker as pt
    return pt.get_closed_positions()

@app.get("/api/positions/stops")
async def positions_check_stops():
    import position_tracker as pt
    stopped = pt.check_stops()
    return {"stopped": stopped, "count": len(stopped)}

@app.get("/api/positions/summary")
async def positions_summary():
    import position_tracker as pt
    return pt.get_summary()

# -- Custom tickers --
@app.get("/api/custom/list")
async def custom_list():
    from custom_tracker import get_custom_tickers
    return {"tickers": get_custom_tickers()}

@app.post("/api/custom/add")
async def custom_add(req: Request):
    body = await req.json()
    from custom_tracker import add_custom_ticker
    result = add_custom_ticker(str(body["ticker"]).upper(), str(body.get("note", "")))
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Unknown"))
    return result

@app.post("/api/custom/remove")
async def custom_remove(req: Request):
    body = await req.json()
    from custom_tracker import remove_custom_ticker
    result = remove_custom_ticker(str(body["ticker"]).upper())
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "Not found"))
    return result


# -- Custom Tracking: on-demand analyze + persistent cache --
from datetime import datetime, timezone
_CUSTOM_CACHE = BASE_DIR / "cache" / "custom_analyzed.json"

def _load_custom_cache() -> dict:
    if not _CUSTOM_CACHE.exists():
        return {}
    try:
        return json.loads(_CUSTOM_CACHE.read_text())
    except Exception:
        return {}

def _save_custom_cache(data: dict) -> None:
    _CUSTOM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_CACHE.write_text(json.dumps(data, default=str, indent=2))

def _row_for_screener(r: dict, zacks_r1_scores: Optional[dict] = None) -> dict:
    """Flatten analyze_ticker result → screener row dict. Mirrors _row_json in html_generator."""
    zacks = (r.get("zacks_vgm") or (zacks_r1_scores or {}).get(r.get("ticker", "")) or {})
    vgm = {
        "value":    zacks.get("value")    or r.get("grade_value",    "—"),
        "growth":   zacks.get("growth")   or r.get("grade_growth",   "—"),
        "momentum": zacks.get("momentum") or r.get("grade_momentum", "—"),
        "vgm":      zacks.get("vgm")      or r.get("grade_vgm",      "—"),
    }
    ind = (r.get("technicals", {}) or {}).get("indicators", {}) or {}
    v = (r.get("decision") or {}).get("verdict", "AVOID")
    direction = r.get("direction", "long")
    bear_sc = r.get("bear_setup", {}).get("score", 0) or 0
    if direction == "short" or v == "SHORT":
        rtype = "SHORT"
    elif bear_sc >= 7 and v not in ("BUY", "WATCH"):
        rtype = "SHORT"
    else:
        rtype = v.upper()
    return {
        "ticker":   r.get("ticker", ""),
        "name":     r.get("name", r.get("ticker", "")),
        "price":    r.get("price", 0),
        "score":    r.get("score", 0),
        "rtype":    rtype,
        "direction": direction,
        "fund":     r.get("fundamentals",  {}).get("score", 0),
        "tech":     r.get("technicals",    {}).get("score", 0),
        "opt":      r.get("optionality",   {}).get("score", 0),
        "sent":     r.get("sentiment",     {}).get("score", 0),
        "rr":       r.get("trade_plan",    {}).get("rr_ratio", 0),
        "sector":   r.get("sector", ""),
        "industry": r.get("industry", ""),
        "rs_rank":  r.get("rs_rank", ind.get("rs_rank")),
        "setup":    (r.get("trade_plan") or {}).get("setup_type", "") or r.get("setup_family", ""),
        "rvol":     ind.get("rvol"),
        "rsi":      ind.get("rsi"),
        "catalysts": r.get("catalyst_tags") or [],
        "val":      vgm.get("value"),
        "gro":      vgm.get("growth"),
        "mom":      vgm.get("momentum"),
        "vgm":      vgm.get("vgm"),
        "reject_reason": "; ".join(r.get("gate", {}).get("reasons", [])) or (r.get("decision") or {}).get("reason", ""),
        "source":   "custom",
        "projected_short": False,
        "kpi":      r.get("kpi") or {},
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

@app.get("/api/custom/bundle")
async def custom_bundle():
    """Return all custom-analyzed tickers for rendering in the Custom Tracking sub-tab."""
    cache = _load_custom_cache()
    return {"rows": list(cache.values()), "count": len(cache)}

@app.post("/api/custom/analyze")
async def custom_analyze(req: Request):
    """Run full deep-dive on a ticker and persist for Custom Tracking view."""
    body = await req.json()
    ticker = str(body.get("ticker", "")).upper().strip()
    if not ticker:
        raise HTTPException(400, "Missing ticker")
    save_to_config = bool(body.get("save_for_next_run", True))

    try:
        from swing_trade import run_deep_dive
        result = run_deep_dive(ticker)
    except Exception as e:
        raise HTTPException(500, f"analyze failed for {ticker}: {e}")
    if not result:
        raise HTTPException(404, f"No data for {ticker}")

    row = _row_for_screener(result)
    cache = _load_custom_cache()
    cache[ticker] = row
    _save_custom_cache(cache)

    # Also add to custom_tracked.json so next scan includes it
    if save_to_config:
        try:
            from custom_tracker import add_custom_ticker
            add_custom_ticker(ticker, str(body.get("note", "")))
        except Exception:
            pass

    return {"ok": True, "ticker": ticker, "row": row, "cached_count": len(cache)}

@app.post("/api/custom/delete_analyzed")
async def custom_delete_analyzed(req: Request):
    """Remove a ticker from the custom-analyzed cache (doesn't remove from config)."""
    body = await req.json()
    ticker = str(body.get("ticker", "")).upper().strip()
    cache = _load_custom_cache()
    if ticker in cache:
        del cache[ticker]
        _save_custom_cache(cache)
    return {"ok": True, "cached_count": len(cache)}

# -- Config read endpoint --
@app.get("/api/config")
async def get_config(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Return current config.json values for the Settings tab."""
    try:
        cfg_path = BASE_DIR / "config" / "config.json"
        if not cfg_path.exists():
            raise HTTPException(404, "config.json not found")
        import json as _json
        cfg = _json.loads(cfg_path.read_text())
        # Remove any credential fields
        for sensitive in ['api_key', 'token', 'password', 'secret', 'key']:
            cfg.pop(sensitive, None)
        return JSONResponse(cfg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# -- WebSocket token endpoint — serves EODHD API key securely --
@app.post("/api/chat")
async def ai_chat(payload: dict, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Trading co-pilot. Streams Claude responses with SwingTrade context.

    Payload: {
      message: str,                # user input
      history: [{role, content}],  # prior turns (last 10 max)
      context: {                   # optional context from current page
        ticker?: str,              # if on detail page
        page?: 'scanner' | 'detail' | 'portfolio',
      }
    }
    Streams: text/event-stream with `data: <chunk>\\n\\n` lines.
    """
    import os, json as _json
    from fastapi.responses import StreamingResponse
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        async def _err():
            yield f"data: {_json.dumps({'error': 'ANTHROPIC_API_KEY not set in .env. Add the key and restart the server.'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")
    try:
        import anthropic
    except ImportError:
        async def _err():
            yield f"data: {_json.dumps({'error': 'anthropic SDK not installed. Run: pip3 install anthropic'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    user_msg = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    ctx = payload.get("context") or {}
    if not user_msg:
        raise HTTPException(400, "message required")

    # ---- Build context-aware system prompt ----
    sys_parts = [
        "You are a hedge-fund-grade swing-trading co-pilot embedded inside the SwingTrade dashboard.",
        "Help the user reason through trade setups, scoring, regime, and risk — using the data injected below.",
        "Be concise (≤200 words unless asked). Use specific numbers from the context. No fluff.",
        "When you cite a level (entry, stop, target), pull from the actual data — never invent.",
        "If the user asks something the data doesn't answer, say 'not in current bundle' and suggest where to look.",
        "",
        "## SwingTrade Methodology",
        "- 5-pillar score (0-100): Tech (35) + Catalyst (20) + RS+Sector (20) + Smart Money (15) + Quality Gate (10)",
        "- Conviction tiers: T1 (≥88, full size) | T2 (≥78, 30-60%) | T3 (≥70, 15-30%) | WATCH (60-69, monitor)",
        "- Setup families: Impulse Catalyst (5-8d) · Breakout Expansion (7-21d) · Trend Continuation (7-21d) · Special Situation (5-15d)",
        "- Entry quality: FRESH (within 0.75 ATR) | PULLBACK (1.25 ATR EMA) | VALID | EXTENDED (1.25-2 ATR) | MISSED (>2 ATR)",
        "- 4 regimes: Risk-On Trending (BUY≥65) | Risk-On Choppy (≥72) | Risk-Off Trending (≥78) | Panic (no longs)",
        "- Hard gates: liquidity ≥$10M ADV, no earnings within 3d, regime ≠ panic, R:R ≥ 3:1",
    ]

    # Inject scan context (always available from data.json)
    try:
        import json as _json2
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "infra", "prototype", "data.json")) as f:
            d = _json2.load(f)
        regime = d.get("regime") or {}
        breadth = d.get("market_breadth") or {}
        st = d.get("short_term") or []
        buys = [r for r in st if r.get("stage") == "BUY"][:8]
        watches = [r for r in st if r.get("stage") == "WATCH"][:8]
        shorts = [r for r in st if r.get("stage") == "SELL"][:5]
        sys_parts += [
            "",
            "## Today's Scan Context",
            f"Run: {d.get('run_timestamp','—')}",
            f"Regime: {regime.get('regime4','—')} · VIX {regime.get('vix') if not isinstance(regime.get('vix'), dict) else regime.get('vix',{}).get('vix_current','—')}",
            f"Breadth: {breadth.get('pct_above_50d','—')}% above 50d ({breadth.get('label_50','—')})",
            f"Universe scanned: {d.get('scan_count',0)} · Killed by gates: {d.get('killed_count',0)}",
        ]
        if buys:
            sys_parts.append("\n### Top BUY signals today")
            for r in buys:
                sys_parts.append(f"- {r['ticker']} ({r.get('sector','—')[:25]}): score {r.get('score','—')} · RR {r.get('rr','—')} · setup {r.get('setup','—')}")
        if watches:
            sys_parts.append("\n### WATCH signals")
            for r in watches[:5]:
                sys_parts.append(f"- {r['ticker']}: score {r.get('score','—')} · setup {r.get('setup','—')}")
        if shorts:
            sys_parts.append("\n### SHORT signals")
            for r in shorts:
                sys_parts.append(f"- {r['ticker']}: score {r.get('score','—')} · setup {r.get('setup','—')}")
        # Portfolio
        pf = d.get("portfolio") or {}
        if pf.get("positions"):
            sys_parts.append(f"\n### Open Positions ({len(pf['positions'])})")
            for p in pf["positions"][:8]:
                sys_parts.append(f"- {p.get('ticker')}: {p.get('shares')} sh @ ${p.get('entry')} · stop ${p.get('stop')} · unreal ${p.get('unrealized_pnl_dollars',0):.0f}")
            sys_parts.append(f"Cash: ${pf.get('cash',0):,.0f} · Equity: ${pf.get('equity',0):,.0f}")
    except Exception as e:
        sys_parts.append(f"\n(scan data unavailable: {e})")

    # Inject ticker-specific context if on detail page
    ticker = (ctx.get("ticker") or "").upper().strip()
    if ticker:
        try:
            with open(os.path.join(here, "infra", "prototype", "tickers.json")) as f:
                ticks = _json2.load(f)
            T = ticks.get(ticker)
            if T:
                sys_parts += [
                    "",
                    f"## Current Ticker: {ticker}",
                    f"Price: ${T.get('price','—')} · {T.get('pct_chg',0):+.2f}% today",
                    f"Verdict: {T.get('verdict','—')} · Score {T.get('score',0)}/100 · R:R {T.get('rr_ratio',0):.1f}:1",
                    f"Pillars: Tech {T.get('tech_score',0)}/{T.get('tech_max',35)} · Fund {T.get('fund_score',0)}/{T.get('fund_max',10)} · Sent {T.get('sent_score',0)}/{T.get('sent_max',15)} · SMC {T.get('smc_score',0)}/10",
                    f"Setup: {T.get('setup_family','—')} · Entry quality: {T.get('entry_quality','—')} · Conviction: {T.get('conviction_tier','—')}",
                    f"Trade plan: entry ${T.get('entry_low','—')}–${T.get('entry_high','—')} · stop ${T.get('stop','—')} · T1 ${T.get('target1','—')} · T2 ${T.get('target2','—')}",
                    f"Indicators: RSI {T.get('rsi','—')} · RVOL {T.get('rvol','—')}× · ATR {T.get('atr_pct','—')}% · RS {T.get('rs_rank','—')}",
                    f"Regime: {T.get('regime','—')} · MC P(profit): {T.get('mc_p_profit','—')}",
                ]
                if T.get('earn_days') is not None and T['earn_days'] <= 14:
                    sys_parts.append(f"⚠ Earnings in {T['earn_days']} days")
        except Exception:
            pass

    system_prompt = "\n".join(sys_parts)

    # Build messages — keep last 10 turns
    msgs = []
    for h in (history[-10:] if isinstance(history, list) else []):
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": h["content"][:4000]})
    msgs.append({"role": "user", "content": user_msg[:4000]})

    # Stream from Claude
    client = anthropic.Anthropic(api_key=api_key)
    async def stream():
        try:
            with client.messages.stream(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                system=system_prompt,
                messages=msgs,
            ) as s:
                for chunk in s.text_stream:
                    yield f"data: {_json.dumps({'text': chunk})}\n\n"
                yield f"data: {_json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/forex/quote")
async def forex_quote(pair: str = "DXY"):
    """Forex/index quote. Defaults to DXY. Cached 4h via eodhd_client._request."""
    try:
        import eodhd_client as ec
        if pair.upper() == "DXY":
            sym = "DXY.INDX"
        elif "USD" in pair.upper() or "EUR" in pair.upper():
            sym = pair.upper() + ".FOREX"
        else:
            sym = pair
        # 4h cache for FX/index quotes — they don't tick fast and don't need fresh-every-load
        bars = ec.eod(sym, cache_ttl=14400) or []
        if not bars or len(bars) < 2:
            return {"pair": pair, "price": None, "chg_pct": None}
        last = bars[-1]
        prev = bars[-2]
        price = float(last.get("close") or last.get("adjusted_close") or 0)
        prev_p = float(prev.get("close") or prev.get("adjusted_close") or 0)
        chg = (price - prev_p) / prev_p * 100 if prev_p else 0
        return {"pair": pair, "price": round(price, 4), "chg_pct": round(chg, 2)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/search")
async def search_tickers(q: str = "", limit: int = 10):
    """Ticker autocomplete via EODHD search. Usage: /api/search?q=apple&limit=10"""
    q = (q or "").strip()
    if len(q) < 1:
        return {"results": []}
    try:
        import eodhd_client as ec
        out = ec.search(q, limit=limit) or []
        # Normalize EODHD response
        results = []
        for r in out[:limit]:
            results.append({
                "ticker": (r.get("Code") or r.get("code") or "").upper(),
                "name": r.get("Name") or r.get("name") or "",
                "exchange": r.get("Exchange") or r.get("exchange") or "US",
                "type": r.get("Type") or r.get("type") or "",
                "country": r.get("Country") or "",
            })
        return {"results": results}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/macro/events")
async def macro_events(days_ahead: int = 14):
    """Economic events calendar (FOMC/CPI/NFP/PMI). Usage: /api/macro/events?days_ahead=14"""
    try:
        import eodhd_client as ec, datetime as _dt
        today = _dt.date.today()
        end = today + _dt.timedelta(days=days_ahead)
        events = ec.economic_events(from_date=today.isoformat(), to_date=end.isoformat(), country="US") or []
        return {"events": events[:50], "from": today.isoformat(), "to": end.isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/exchange/hours")
async def exchange_hours(exchange: str = "US"):
    """Exchange trading hours + current open/closed status."""
    import datetime as _dt
    try:
        import eodhd_client as ec
        det = ec.exchange_details(exchange) or {}
        trading_hours = det.get("TradingHours") or det.get("trading_hours") or {}
        # Compute current status (US Eastern Time)
        utc_now = _dt.datetime.utcnow()
        is_dst = 3 <= utc_now.month <= 10
        now_et = utc_now + _dt.timedelta(hours=(-4 if is_dst else -5))
        is_weekday = now_et.weekday() < 5
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        pre_open = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        post_close = now_et.replace(hour=20, minute=0, second=0, microsecond=0)
        if not is_weekday:
            status, next_event, next_at = "closed", "Opens Mon 9:30 ET", market_open + _dt.timedelta(days=(7 - now_et.weekday()))
        elif now_et < pre_open:
            status, next_event, next_at = "closed", "Pre-market opens", pre_open
        elif now_et < market_open:
            status, next_event, next_at = "pre_market", "Opens", market_open
        elif now_et < market_close:
            status, next_event, next_at = "open", "Closes", market_close
        elif now_et < post_close:
            status, next_event, next_at = "post_market", "After-hours ends", post_close
        else:
            tomorrow = now_et + _dt.timedelta(days=1)
            if tomorrow.weekday() >= 5:
                tomorrow += _dt.timedelta(days=(7 - tomorrow.weekday()))
            status, next_event, next_at = "closed", "Pre-market opens", tomorrow.replace(hour=4, minute=0, second=0, microsecond=0)
        seconds_until = max(0, int((next_at - now_et).total_seconds()))
        return {
            "status": status,
            "next_event": next_event,
            "next_at_et": next_at.strftime("%Y-%m-%d %H:%M ET"),
            "seconds_until": seconds_until,
            "trading_hours": trading_hours,
            "exchange": det.get("Name", "NYSE Arca"),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/elite/{ticker}")
async def elite_detail_for_ticker(ticker: str, deep: bool = False):
    """
    On-demand elite-detail payload for ANY ticker (even outside the current scan
    universe). Returns the same shape as `tickers.json[TICKER]`.

    Default: FAST-LANE via `run_quick_dive` (~15-25s) — skips Finviz bulk,
    social scrapers, decommissioned fallbacks. Suitable for UI on-demand search.

    Pass `?deep=true` for full enrichment via `run_deep_dive` (~60-90s).

    Cached 30 min in-memory per ticker+mode.
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 8:
        raise HTTPException(400, "Invalid ticker")

    import time as _time
    if not hasattr(elite_detail_for_ticker, '_cache'):
        elite_detail_for_ticker._cache = {}
    cache = elite_detail_for_ticker._cache
    cache_key = f"{ticker}_{'deep' if deep else 'quick'}"
    now = _time.time()
    if cache_key in cache and (now - cache[cache_key]['ts']) < 1800:
        return cache[cache_key]['data']

    # FAST-PATH (2026-05-04): for tickers in the latest scan, return the pre-built
    # rich_row from tickers.json instantly — saves the 6.6s cold-call cost.
    # Only applies to quick-mode (deep=False); ?deep=true always re-computes.
    if not deep:
        if not hasattr(elite_detail_for_ticker, '_tickers_json'):
            elite_detail_for_ticker._tickers_json = {"ts": 0, "data": {}}
        tj = elite_detail_for_ticker._tickers_json
        tj_path = BASE_DIR / "infra" / "prototype" / "tickers.json"
        try:
            mtime = tj_path.stat().st_mtime if tj_path.exists() else 0
            if mtime and mtime > tj["ts"]:
                tj["data"] = json.loads(tj_path.read_text())
                tj["ts"] = mtime
        except Exception:
            pass
        prebuilt = (tj.get("data") or {}).get(ticker)
        if prebuilt:
            cache[cache_key] = {'ts': now, 'data': prebuilt}
            return prebuilt

    try:
        if deep:
            from swing_trade import run_deep_dive as _runner
        else:
            from swing_trade import run_quick_dive as _runner
        result = _runner(ticker)

        # 2026-05-04: Foreign-ticker recovery (Q-1 follow-up).
        # If the ticker has no US data, try EODHD search to see if there's a US ADR
        # under a different symbol (e.g., WIPRO → WIT, INFY routes to .US already).
        if not result:
            try:
                import eodhd_client as _e
                hits = _e.search(ticker, limit=8, prefer_us=True) or []
                # Find first US-listed match with a different code
                us_match = next((h for h in hits
                                 if (h.get("Exchange") or "").upper() in ("US","NYSE","NASDAQ","AMEX","BATS","ARCA")
                                 and (h.get("Code") or "").upper() != ticker), None)
                if us_match:
                    suggested = us_match.get("Code", "").upper()
                    name = us_match.get("Name", "")
                    raise HTTPException(404, (
                        f"No US data for {ticker}. Did you mean "
                        f"<b>{suggested}</b> ({name} · ADR on {us_match.get('Exchange')})? "
                        f"Try /elite-detail.html?t={suggested}"
                    ))
                # No US listing — show all candidates so user can pick foreign listing if intentional
                if hits:
                    foreign = ", ".join(f"{h.get('Code')}:{h.get('Exchange')}" for h in hits[:5])
                    raise HTTPException(404,
                        f"No US data for {ticker}. Foreign listings exist: {foreign}. "
                        f"This system trades US-listed only.")
            except HTTPException:
                raise
            except Exception:
                pass
            raise HTTPException(404, f"No data for {ticker}")
        from infra.prototype.build_data import rich_row
        rich = rich_row(result, {})
        cache[cache_key] = {'ts': now, 'data': rich}
        return rich
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(500, f"{'Deep' if deep else 'Quick'} dive failed for {ticker}: {e}\n{traceback.format_exc()[-400:]}")


@app.get("/api/insider/{ticker}")
async def insider_for_ticker(ticker: str, days: int = 90):
    """Insider Form 4 transactions with dollar values for a ticker."""
    try:
        import eodhd_client as ec, datetime as _dt
        end = _dt.date.today()
        start = end - _dt.timedelta(days=days)
        rows = ec.insider_transactions(ticker.upper(), from_date=start.isoformat(), to_date=end.isoformat()) or []
        cleaned = []
        for r in (rows or [])[:100]:
            shares = r.get("transactionAmount") or r.get("shares") or 0
            price = r.get("transactionPrice") or r.get("price") or 0
            value = float(shares or 0) * float(price or 0)
            cleaned.append({
                "date": r.get("transactionDate") or r.get("date") or "",
                "name": r.get("ownerName") or r.get("name") or "",
                "title": r.get("ownerTitle") or r.get("title") or "",
                "type": r.get("transactionCode") or r.get("type") or "",
                "shares": int(shares or 0),
                "price": float(price or 0),
                "value": round(value, 0),
            })
        return {"ticker": ticker.upper(), "transactions": cleaned, "count": len(cleaned)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/sentiment/{ticker}")
async def sentiment_series(ticker: str, days: int = 14):
    """Sentiment time series for a ticker (for sparkline)."""
    try:
        import eodhd_client as ec, datetime as _dt
        end = _dt.date.today()
        start = end - _dt.timedelta(days=days)
        data = ec.sentiments([ticker.upper()], from_date=start.isoformat(), to_date=end.isoformat()) or {}
        # Find the ticker key (EODHD adds .US suffix)
        series = []
        for k, v in (data or {}).items():
            if k.upper().startswith(ticker.upper()):
                series = v if isinstance(v, list) else []
                break
        return {"ticker": ticker.upper(), "series": series, "count": len(series)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/etf/{ticker}")
async def etf_holdings(ticker: str):
    """ETF holdings + AUM + expense ratio."""
    try:
        import eodhd_client as ec
        f = ec.etf_fundamentals(ticker.upper())
        if not f:
            return {"is_etf": False, "ticker": ticker.upper()}
        etf = f.get("ETF_Data") or {}
        gen = f.get("General") or {}
        # Holdings comes back as a dict {symbol: {Code, Name, Sector, Industry, Country, Region, Assets_%}}
        holdings_raw = etf.get("Holdings") or {}
        holdings = []
        if isinstance(holdings_raw, dict):
            for sym, h in holdings_raw.items():
                holdings.append({
                    "ticker": h.get("Code") or sym,
                    "name": h.get("Name") or "",
                    "sector": h.get("Sector") or "",
                    "weight_pct": float(h.get("Assets_%") or 0),
                })
        elif isinstance(holdings_raw, list):
            for h in holdings_raw:
                holdings.append({
                    "ticker": h.get("Code") or h.get("ticker") or "",
                    "name": h.get("Name") or "",
                    "sector": h.get("Sector") or "",
                    "weight_pct": float(h.get("Assets_%") or h.get("weight") or 0),
                })
        holdings.sort(key=lambda x: x["weight_pct"], reverse=True)
        return {
            "is_etf": True,
            "ticker": ticker.upper(),
            "name": gen.get("Name") or "",
            "issuer": etf.get("Company_Name") or "",
            "aum": etf.get("Total_Assets") or etf.get("NetAssets"),
            "expense_ratio": etf.get("NetExpenseRatio"),
            "yield_pct": etf.get("Yield"),
            "holdings_count": etf.get("Holdings_Count") or len(holdings),
            "top_holdings": holdings[:10],
            "sector_weights": etf.get("Sector_Weights") or [],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/events/financial")
async def financial_events_endpoint(event_type: str = "ipos", days_ahead: int = 30):
    """Financial events — IPOs / splits / secondary offerings."""
    try:
        import eodhd_client as ec, datetime as _dt
        today = _dt.date.today()
        end = today + _dt.timedelta(days=days_ahead)
        events = ec.financial_events(from_date=today.isoformat(), to_date=end.isoformat(), event_type=event_type) or []
        # Normalize various EODHD shapes
        if isinstance(events, dict) and "data" in events:
            events = events["data"]
        return {"event_type": event_type, "events": events[:50], "from": today.isoformat(), "to": end.isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/premarket/movers")
async def premarket_movers(min_gap_pct: float = 2.0, limit: int = 30):
    """Top pre-market gappers from current scan universe."""
    try:
        import json as _json, os
        bundle_path = os.path.join(os.path.dirname(__file__), "cache", "last_bundle.json")
        if not os.path.exists(bundle_path):
            return {"movers": [], "note": "no bundle"}
        with open(bundle_path) as f:
            b = _json.load(f)
        # Pull pre-market gap from all_scored rows (premarket dict per ticker)
        movers = []
        for r in (b.get("all_scored") or []):
            pm = r.get("premarket") or {}
            gap = pm.get("price_chg_pct") or pm.get("gap_pct") or 0
            vol_ratio = pm.get("vol_ratio") or 0
            if abs(float(gap or 0)) >= min_gap_pct:
                movers.append({
                    "ticker": r.get("ticker"),
                    "name": r.get("name") or r.get("ticker"),
                    "sector": r.get("sector") or "",
                    "price": r.get("price"),
                    "gap_pct": round(float(gap), 2),
                    "vol_ratio": round(float(vol_ratio or 1), 2),
                    "score": r.get("score") or 0,
                })
        movers.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
        return {"movers": movers[:limit], "count": len(movers)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/orders/submit")
async def submit_order(payload: dict, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Submit a paper-trade order via Alpaca. Requires paper trading active.

    Payload: {
      ticker, side ("LONG"/"SHORT"), shares (int),
      order_type ("MKT"/"LMT"/"STP"), limit (float, optional),
      stop (float, optional), target (float, optional),
      bracket (bool), tif ("DAY"/"GTC"/"IOC"),
      dry_run (bool, default true)
    }
    Response: { ok, order_id, message, dry_run }
    """
    try:
        # Always start in dry-run mode unless explicitly disabled
        dry_run = bool(payload.get("dry_run", True))
        ticker = (payload.get("ticker") or "").upper().strip()
        # 2026-05-04: accept both UI-level ('LONG'/'SHORT') and broker-level
        # ('buy'/'sell') for `side`. Previously only LONG/SHORT was understood;
        # 'buy' coming in was silently filtering to SELL via the else-branch.
        _side_raw = (payload.get("side") or "LONG").upper().strip()
        if _side_raw in ("BUY", "LONG"):
            side = "LONG"
        elif _side_raw in ("SELL", "SHORT"):
            side = "SHORT"
        else:
            side = _side_raw  # unknown — let downstream reject loudly
        qty = int(payload.get("shares") or 0)
        ord_type = (payload.get("order_type") or "MKT").upper()
        limit_px = payload.get("limit")
        stop_px = payload.get("stop")
        target_px = payload.get("target")
        bracket = bool(payload.get("bracket"))
        tif = (payload.get("tif") or "DAY").upper()
        if not ticker or qty < 1:
            raise HTTPException(400, "ticker + shares (>=1) required")
        if dry_run:
            return {
                "ok": True,
                "order_id": f"DRY-{ticker}-{qty}",
                "message": (
                    f"DRY-RUN — would submit {side} {qty} {ticker} "
                    f"({ord_type}{' @$' + format(limit_px, '.2f') if limit_px else ''}) "
                    f"{'+ bracket OCO' if bracket else ''}"
                ),
                "dry_run": True,
            }
        # Live submit path
        import executor, os, time
        try:
            from portfolio_tracker import is_paper_trading_enabled
            ok, why = is_paper_trading_enabled()
            if not ok:
                raise HTTPException(412, f"Paper trading not active: {why}. Run `python3 executor.py --activate`.")
        except ImportError:
            pass

        # ── LOCAL PAPER MODE (no Alpaca creds required) ──────────────────────
        # If Alpaca credentials are missing/placeholder, write the trade
        # directly to portfolio_tracker (internal paper book). Lets user
        # trade without signing up for Alpaca paper account.
        # 2026-05-04: read via secrets_loader (which reads .env file directly)
        # so server.py doesn't need .env-in-os.environ on startup.
        try:
            from secrets_loader import alpaca_key as _ak_loader
            _alpaca_key = (_ak_loader() or "").strip()
        except Exception:
            _alpaca_key = os.environ.get("ALPACA_API_KEY", "").strip()
        _alpaca_unset = (not _alpaca_key) or "YOUR_" in _alpaca_key
        if _alpaca_unset:
            try:
                from portfolio_tracker import add_position
                # Use limit_px as entry, fall back to live quote if missing
                if limit_px:
                    entry_px = float(limit_px)
                else:
                    # Pull live price for market order
                    try:
                        result = _try_schwab_quotes([ticker]) or _try_eodhd_quotes([ticker], True, 5)
                        entry_px = float((result[0].get(ticker) or 0)) if result else 0.0
                    except Exception:
                        entry_px = 0.0
                if entry_px <= 0:
                    raise HTTPException(400, "Could not determine entry price for market order")
                pos = add_position(
                    ticker=ticker, entry_price=entry_px, shares=qty,
                    stop=float(stop_px or entry_px * 0.97),
                    target1=float(target_px or entry_px * 1.05),
                    target2=None,
                    setup_type=payload.get("setup_type") or "swing",
                    direction="long" if side == "LONG" else "short",
                    allocation_pct=payload.get("allocation_pct") or 7.5,
                    notes=payload.get("notes") or "",
                )
                return {
                    "ok": True,
                    "order_id": f"LOCAL-{ticker}-{int(time.time())}",
                    "message": f"{side} {qty} {ticker} @ ${entry_px:.2f} → tracked in local portfolio (no Alpaca)",
                    "dry_run": False,
                    "mode": "local_paper",
                    "position": {"ticker": ticker, "shares": qty, "entry": entry_px,
                                 "stop": pos.get("stop"), "target1": pos.get("target1")},
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, f"Local paper write failed: {e}")

        # ── ALPACA PATH (when credentials are configured) ────────────────────
        # _make_client() returns (client, account) — unpack the tuple.
        client, _account = executor._make_client()
        if bracket and stop_px and target_px and limit_px:
            ok, msg = executor.submit_bracket(client, {
                "ticker": ticker, "qty": qty,
                "entry_limit": float(limit_px),
                "stop": float(stop_px),
                "target": float(target_px),
            })
            return {"ok": ok, "order_id": msg, "message": "Bracket order submitted." if ok else f"Failed: {msg}", "dry_run": False}
        # Plain market/limit single-leg
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        side_enum = OrderSide.BUY if side == "LONG" else OrderSide.SELL
        tif_enum = {"DAY": TimeInForce.DAY, "GTC": TimeInForce.GTC, "IOC": TimeInForce.IOC}.get(tif, TimeInForce.DAY)
        if ord_type == "MKT":
            req = MarketOrderRequest(symbol=ticker, qty=qty, side=side_enum, time_in_force=tif_enum)
        elif ord_type == "LMT":
            req = LimitOrderRequest(symbol=ticker, qty=qty, side=side_enum, time_in_force=tif_enum, limit_price=float(limit_px or 0))
        else:
            req = StopOrderRequest(symbol=ticker, qty=qty, side=side_enum, time_in_force=tif_enum, stop_price=float(limit_px or 0))
        resp = client.submit_order(req)
        return {"ok": True, "order_id": str(getattr(resp, "id", "submitted")), "message": f"{side} {qty} {ticker} submitted.", "dry_run": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/live/ws-token")
async def live_ws_token(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Return the EODHD API key for WebSocket connection (behind auth)."""
    try:
        import eodhd_client as ec
        key = ec._load_api_key()
        if not key:
            raise HTTPException(503, "EODHD API key not configured")
        return {"token": key, "url": "wss://ws.eodhd.com/ws/us"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# -- Live / quote / whatif --
# In-memory cache to suppress repeated provider calls when polling tightens.
# Each entry: {prices, quotes, source, ts, in_hours}. TTL 30s during market
# hours (real-time updates), 30min after-hours.
_LIVE_QUOTE_CACHE: dict = {}

# Provider degradation tracker — auto-skip a provider after 2 failures in 60s
_PROVIDER_FAILS: dict = {"schwab": [], "eodhd": []}

def _provider_skip(name: str, window: float = 60.0, threshold: int = 2) -> bool:
    """True if provider had >= threshold failures in last `window` seconds."""
    import time as _t
    now = _t.time()
    fails = _PROVIDER_FAILS.get(name, [])
    fails = [t for t in fails if now - t < window]
    _PROVIDER_FAILS[name] = fails
    return len(fails) >= threshold

def _provider_failed(name: str) -> None:
    import time as _t
    _PROVIDER_FAILS.setdefault(name, []).append(_t.time())


def _try_schwab_quotes(syms: list):
    """Try Schwab batch quotes. Returns (prices, quotes) or None on failure."""
    try:
        import schwab_client as _sc
        data = _sc.get_quotes_batch(syms[:500])
        if not data:
            return None
        prices: dict[str, float] = {}
        quotes: dict[str, dict] = {}
        for sym, blob in data.items():
            if not isinstance(blob, dict):
                continue
            q = blob.get("quote") or {}
            last = q.get("lastPrice")
            if last is None:
                continue
            try:
                prices[sym] = round(float(last), 2)
                pc = q.get("closePrice")
                quotes[sym] = {
                    "price":      round(float(last), 2),
                    "prev_close": round(float(pc), 2) if pc is not None else None,
                    "change_p":   round(float(q.get("netPercentChange", 0)), 3),
                    "bid":        round(float(q.get("bidPrice")), 4) if q.get("bidPrice") is not None else None,
                    "ask":        round(float(q.get("askPrice")), 4) if q.get("askPrice") is not None else None,
                    "volume":     int(q.get("totalVolume") or 0),
                }
            except (TypeError, ValueError):
                pass
        if not prices:
            return None
        return prices, quotes
    except Exception:
        return None


def _try_eodhd_quotes(syms: list, in_hours: bool, ttl: int):
    """Try EODHD real_time (in-hours) or bulk_eod (after-hours)."""
    try:
        import eodhd_client as _ec
        prices: dict[str, float] = {}
        quotes: dict[str, dict] = {}
        if in_hours:
            rt = _ec.real_time(syms[:200]) or []
            if isinstance(rt, dict):
                rt = [rt]
            for rec in rt:
                if not isinstance(rec, dict): continue
                code = (rec.get("code") or "").split(".")[0].upper()
                if not code: continue
                cl = rec.get("close")
                pc = rec.get("previousClose")
                chg_p = rec.get("change_p")
                if cl is None or cl == "NA": continue
                try:
                    prices[code] = round(float(cl), 2)
                    quotes[code] = {
                        "price":      round(float(cl), 2),
                        "prev_close": round(float(pc), 2) if pc not in (None, "NA") else None,
                        "change_p":   round(float(chg_p), 3) if chg_p not in (None, "NA") else None,
                    }
                except (TypeError, ValueError):
                    pass
        if len(prices) < len(syms[:200]):
            bulk = _ec.bulk_eod(exchange="US", cache_ttl=ttl) or []
            idx = {(r.get("code") or "").upper(): r for r in bulk if isinstance(r, dict)}
            for sym in syms[:200]:
                if sym in prices: continue
                rec = idx.get(sym)
                if rec and rec.get("close") is not None:
                    prices[sym] = round(float(rec["close"]), 2)
                    quotes[sym] = {
                        "price":      round(float(rec["close"]), 2),
                        "prev_close": None,
                        "change_p":   None,
                    }
        if not prices:
            return None
        return prices, quotes
    except Exception:
        return None


@app.get("/api/live/quote")
async def live_quote(tickers: str = ""):
    """Live quote for any ticker(s). Usage: /api/live/quote?tickers=AAPL,MSFT

    Hybrid strategy (2026-04-30): Schwab primary (real-time + bid/ask, $0),
    EODHD fallback (1000/min cap, 15-min delayed). Auto-degrade on failures.

    Response: {prices, quotes, source: 'schwab'|'eodhd'|'cache', ts, in_hours}
    """
    import time, datetime as _dt
    syms = [s.strip().upper() for s in (tickers or "").split(",") if s.strip()]
    if not syms:
        return {"prices": {}, "ts": time.time(), "in_hours": False, "source": "none"}
    cache_key = ",".join(sorted(syms[:500]))
    cached = _LIVE_QUOTE_CACHE.get(cache_key)
    _utc_now = _dt.datetime.utcnow()
    _is_dst = 3 <= _utc_now.month <= 10
    now_et = _utc_now + _dt.timedelta(hours=(-4 if _is_dst else -5))
    market_open  = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    in_hours = (now_et.weekday() < 5) and (market_open <= now_et <= market_close)
    # 5s cache during market hours — matches frontend 5s polling and Schwab's
    # ~2-5s update cadence. Suppresses simultaneous tab requests. After-hours: 30min.
    ttl = 5 if in_hours else 1800
    if cached and (time.time() - cached["ts"]) < ttl:
        return {**cached, "cached": True}

    # Provider routing — Schwab primary, EODHD fallback. Skip a provider that
    # failed twice in last 60s.
    prices: dict = {}
    quotes: dict = {}
    source: str = "none"

    if not _provider_skip("schwab"):
        result = _try_schwab_quotes(syms)
        if result:
            prices, quotes = result
            source = "schwab"
        else:
            _provider_failed("schwab")

    if not prices and not _provider_skip("eodhd"):
        result = _try_eodhd_quotes(syms, in_hours, ttl)
        if result:
            prices, quotes = result
            source = "eodhd"
        else:
            _provider_failed("eodhd")

    if not prices:
        # Both providers failed — return stale cache if any
        if cached:
            return {**cached, "cached": True, "stale": True, "source": "cache"}
        return {"prices": {}, "quotes": {}, "ts": time.time(),
                "in_hours": in_hours, "count": 0, "source": "none",
                "error": "both providers failed"}

    out = {"prices": prices, "quotes": quotes, "ts": time.time(),
           "in_hours": in_hours, "count": len(prices), "source": source}
    _LIVE_QUOTE_CACHE[cache_key] = out
    return out

_LIVE_PRICES_CACHE: dict = {}

@app.get("/api/live/prices")
async def live_prices():
    """Live prices for open positions. Uses bulk_eod (1 EODHD call) instead of N
    per-ticker fetches. Cached 90s during market hours, 30min after-hours."""
    import time, datetime as _dt
    try:
        import portfolio_tracker as pt
        _utc_now = _dt.datetime.utcnow()
        _month = _utc_now.month
        _is_dst = 3 <= _month <= 10
        _et_offset = -4 if _is_dst else -5
        now_et = _utc_now + _dt.timedelta(hours=_et_offset)
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        in_hours = (now_et.weekday() < 5) and (market_open <= now_et <= market_close)
        summary = pt.get_portfolio_summary()
        positions = summary.get("positions", [])
        if not positions:
            return {"prices": {}, "ts": time.time(), "in_hours": in_hours}
        ttl = 90 if in_hours else 1800
        cache_key = ",".join(sorted({p.get("ticker", "") for p in positions if p.get("ticker")}))
        cached = _LIVE_PRICES_CACHE.get(cache_key)
        if cached and (time.time() - cached["ts"]) < ttl:
            return {**cached, "cached": True}
        prices: dict[str, float] = {}
        try:
            import eodhd_client as _ec
            bulk = _ec.bulk_eod(exchange="US", cache_ttl=ttl) or []
            idx = {(r.get("code") or "").upper(): r for r in bulk if isinstance(r, dict)}
            for p in positions:
                t = (p.get("ticker") or "").upper()
                rec = idx.get(t)
                if rec and rec.get("close") is not None:
                    prices[t] = round(float(rec["close"]), 2)
                else:
                    prices[t] = p.get("current_price", p.get("entry_price"))
        except Exception:
            for p in positions:
                t = p.get("ticker", "")
                prices[t] = p.get("current_price", p.get("entry_price"))
        out = {"prices": prices, "ts": time.time(), "in_hours": in_hours, "count": len(prices)}
        _LIVE_PRICES_CACHE[cache_key] = out
        return out
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/live/status")
async def live_status():
    try:
        from alpaca_feed import get_live_status
        return get_live_status()
    except Exception:
        return {"configured": False, "active_tickers": 0, "status": "offline"}

@app.get("/api/quote")
async def quote(ticker: str = ""):
    if not ticker:
        raise HTTPException(400, "Missing ticker")
    ticker = ticker.upper()
    result = {"ticker": ticker, "price": 0, "source": "none"}
    # EODHD real-time + fundamentals
    try:
        import eodhd_client as _eod
        rt = _eod.real_time(ticker)
        f  = _eod.fundamentals(ticker) or {}
        H  = (f.get("Highlights") or {}) if isinstance(f, dict) else {}
        G  = (f.get("General")    or {}) if isinstance(f, dict) else {}
        T  = (f.get("Technicals") or {}) if isinstance(f, dict) else {}
        SD = (f.get("SplitsDividends") or {}) if isinstance(f, dict) else {}
        px = None
        if isinstance(rt, dict):
            px = rt.get("close") or rt.get("previousClose")
        if px and px != "NA":
            result = {
                "ticker": ticker,
                "price": float(px),
                "name": G.get("Name") or ticker,
                "pe": H.get("PERatio"),
                "eps": H.get("EarningsShare") or H.get("DilutedEpsTTM"),
                "mcap": G.get("MarketCapitalization"),
                "beta": T.get("Beta"),
                "high52": T.get("52WeekHigh"),
                "low52":  T.get("52WeekLow"),
                "div_yield": H.get("DividendYield") or SD.get("ForwardAnnualDividendYield"),
                "source": "eodhd",
            }
            return result
    except Exception:
        pass
    # Fallback to archive
    try:
        from data_fetcher import fetch_ohlcv_with_failover
        df, tier = fetch_ohlcv_with_failover(ticker, days=2)
        if df is not None and not df.empty:
            result["price"] = round(float(df["Close"].iloc[-1]), 2)
            result["source"] = tier
    except Exception:
        pass
    if result["price"] <= 0:
        raise HTTPException(404, f"No data for {ticker}")
    return result

@app.get("/api/whatif")
async def whatif(ticker: str = "", entry_date: str = "", entry_price: float = 0, direction: str = "long"):
    if not ticker or not entry_date or entry_price <= 0:
        raise HTTPException(400, "Missing params")
    from data_fetcher import fetch_ohlcv_with_failover
    import pandas as pd
    try:
        df, _ = fetch_ohlcv_with_failover(ticker.upper(), days=60)
        if df is None or df.empty:
            raise HTTPException(404, "No price data")
        ts = pd.Timestamp(entry_date)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        sub = df[df.index >= ts]
        if len(sub) < 2:
            raise HTTPException(404, "Not enough data post-entry")
        PERIODS = [("D1",1),("D2",2),("D3",3),("D4",4),("D5",5),("W1",5),("W2",10),("M1",21)]
        results = []
        for label, days in PERIODS:
            if days < len(sub):
                close = float(sub["Close"].iloc[days])
                pnl = (close - entry_price) / entry_price * 100 if direction == "long" else (entry_price - close) / entry_price * 100
                results.append({"label": label, "close_price": round(close,2), "pnl_pct": round(pnl, 2)})
            else:
                results.append({"label": label, "close_price": None, "pnl_pct": None})
        return {"periods": results, "ticker": ticker.upper()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# -- Universe --
@app.post("/api/universe/add")
async def universe_add(req: Request):
    body = await req.json()
    ticker = str(body.get("ticker", "")).upper()
    if not ticker:
        raise HTTPException(400, "Missing ticker")
    cfg_path = BASE_DIR / "config" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        wl = cfg.setdefault("universe", {}).setdefault("custom_watchlist", [])
        if ticker in wl:
            return {"ok": True, "message": f"{ticker} already in watchlist"}
        wl.append(ticker)
        cfg_path.write_text(json.dumps(cfg, indent=2))
        return {"ok": True, "message": f"{ticker} added to watchlist", "watchlist": wl}
    except Exception as e:
        raise HTTPException(500, str(e))

# -- Portfolio clear --
@app.post("/api/portfolio/clear")
async def portfolio_clear(_: HTTPBasicCredentials = Depends(_require_admin)):
    import portfolio_tracker as pt
    try:
        state = pt._load_state()
        state["positions"] = []
        state["closed_trades"] = []
        state["monthly_pnl"] = {}
        pt._save_state(state)
        return {"ok": True, "cleared": True}
    except Exception as e:
        raise HTTPException(500, str(e))

# -- Settings (env + config.json) --
@app.post("/api/settings/env")
async def settings_update_env(req: Request):
    """Update .env file with SCORING_MODE, TRADING_STYLE, SLIPPAGE_MODEL, BACKTEST_NO_FUNDAMENTALS."""
    body = await req.json()
    if not isinstance(body, dict) or not body:
        raise HTTPException(400, "Body must be a non-empty JSON object of key:value env pairs")
    env_path = BASE_DIR / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    # Parse into ordered structure preserving comments / blank lines
    parsed = []  # list of ('kv', key, value) | ('raw', line)
    keys_seen = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            parsed.append(["kv", k, v])
            keys_seen[k] = len(parsed) - 1
        else:
            parsed.append(["raw", line])
    for k, v in body.items():
        v_str = str(v)
        if k in keys_seen:
            parsed[keys_seen[k]] = ["kv", k, v_str]
        else:
            parsed.append(["kv", k, v_str])
    out_lines = []
    for item in parsed:
        if item[0] == "kv":
            out_lines.append(f"{item[1]}={item[2]}")
        else:
            out_lines.append(item[1])
    env_path.write_text("\n".join(out_lines) + ("\n" if out_lines and not out_lines[-1].endswith("\n") else ""))
    # Audit
    _settings_audit_append({"type": "env", "keys": list(body.keys()), "values": {k: str(v) for k, v in body.items()}})
    return {"ok": True, "message": "Env updated — restart server to apply", "keys": list(body.keys())}


def _settings_audit_append(entry: dict):
    import json as _j
    from datetime import datetime as _dt
    audit_path = BASE_DIR / "data" / "settings_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit = []
    if audit_path.exists():
        try:
            audit = _j.loads(audit_path.read_text())
            if not isinstance(audit, list):
                audit = []
        except Exception:
            audit = []
    audit.append({"ts": _dt.now().isoformat(), **entry})
    audit_path.write_text(_j.dumps(audit[-500:], indent=2))


def _validate_setting(dotted_key: str, value):
    """Server-side validation — raises ValueError on invalid."""
    k = dotted_key
    if k.startswith("regime_thresholds.") and k.endswith(".buy_min_score"):
        if not (isinstance(value, int) and 0 <= value <= 100):
            raise ValueError(f"{k} must be int 0-100")
    if k.startswith("regime_thresholds.") and k.endswith(".watch_min_score"):
        if not (isinstance(value, int) and 0 <= value <= 100):
            raise ValueError(f"{k} must be int 0-100")
    if k.startswith("regime_thresholds.") and k.endswith(".rs_min"):
        if not (isinstance(value, int) and 0 <= value <= 100):
            raise ValueError(f"{k} must be int 0-100")
    if k.startswith("regime_thresholds.") and k.endswith(".rr_min"):
        if not (isinstance(value, (int, float)) and value >= 1.0):
            raise ValueError(f"{k} must be >= 1.0")
    if k == "portfolio.config_e.pct_per_trade" and not (0.01 <= float(value) <= 0.5):
        raise ValueError("pct_per_trade must be 0.01-0.5")
    if k == "portfolio.config_e.max_positions" and not (1 <= int(value) <= 20):
        raise ValueError("max_positions must be 1-20")
    if k == "gates.extended_atr_gate" and not (1.0 <= float(value) <= 4.0):
        raise ValueError("extended_atr_gate must be 1.0-4.0")


@app.post("/api/settings/config")
async def settings_update_config(req: Request):
    """Update config/config.json with dotted-path values."""
    body = await req.json()
    if not isinstance(body, dict) or not body:
        raise HTTPException(400, "Body must be a non-empty JSON object of dotted_path:value pairs")
    cfg_path = BASE_DIR / "config" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception as e:
        raise HTTPException(500, f"config.json unreadable: {e}")

    # Pre-validate
    for dk, val in body.items():
        try:
            _validate_setting(dk, val)
        except ValueError as ve:
            raise HTTPException(400, str(ve))

    # Cross-field validation: buy_min > watch_min per regime
    for regime in ("bull", "neutral", "bear"):
        buy_k = f"regime_thresholds.{regime}.buy_min_score"
        watch_k = f"regime_thresholds.{regime}.watch_min_score"
        buy_v = body.get(buy_k, cfg.get("regime_thresholds", {}).get(regime, {}).get("buy_min_score"))
        watch_v = body.get(watch_k, cfg.get("regime_thresholds", {}).get(regime, {}).get("watch_min_score"))
        if buy_v is not None and watch_v is not None and not (buy_v > watch_v):
            raise HTTPException(400, f"{regime}: buy_min_score ({buy_v}) must be > watch_min_score ({watch_v})")

    changes = []
    for dotted_key, value in body.items():
        keys = dotted_key.split(".")
        ref = cfg
        for k in keys[:-1]:
            if not isinstance(ref.get(k), dict):
                ref[k] = {}
            ref = ref[k]
        old_val = ref.get(keys[-1])
        ref[keys[-1]] = value
        changes.append({"path": dotted_key, "old": old_val, "new": value})

    cfg_path.write_text(json.dumps(cfg, indent=2))
    _settings_audit_append({"type": "config", "changes": changes})
    return {"ok": True, "message": f"{len(changes)} settings updated", "changes": changes}


@app.get("/api/settings/current")
async def settings_get_current():
    """Return all current env + config values for Settings tab to read."""
    env = {
        "SCORING_MODE": os.environ.get("SCORING_MODE", "swing_optimized"),
        "TRADING_STYLE": os.environ.get("TRADING_STYLE", "swing"),
        "SLIPPAGE_MODEL": os.environ.get("SLIPPAGE_MODEL", "realistic"),
        "BACKTEST_NO_FUNDAMENTALS": os.environ.get("BACKTEST_NO_FUNDAMENTALS", "0"),
    }
    cfg_path = BASE_DIR / "config" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception:
        cfg = {}
    return {"env": env, "config": cfg}


@app.get("/api/settings/audit")
async def settings_audit():
    audit_path = BASE_DIR / "data" / "settings_audit.json"
    if not audit_path.exists():
        return {"entries": []}
    try:
        return {"entries": json.loads(audit_path.read_text())}
    except Exception:
        return {"entries": []}


@app.post("/api/settings/reset")
async def settings_reset():
    """Backup current config.json (reset-to-defaults not implemented — no template stored)."""
    import shutil
    from datetime import datetime as _dt
    cfg_path = BASE_DIR / "config" / "config.json"
    backup = BASE_DIR / "config" / f"config.backup.{_dt.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        shutil.copy2(cfg_path, backup)
    except Exception as e:
        raise HTTPException(500, f"Backup failed: {e}")
    return {"ok": False, "message": f"Reset not implemented — backup created at {backup.name}", "backup": str(backup)}


@app.post("/api/settings/paper_trading")
async def settings_paper_trading(req: Request):
    """Activate or disable paper trading window."""
    body = await req.json()
    action = str(body.get("action", "")).lower()
    try:
        import portfolio_tracker as pt
    except Exception as e:
        raise HTTPException(500, f"portfolio_tracker unavailable: {e}")
    if action == "activate":
        duration = int(body.get("duration_days", 60))
        result = pt.activate_paper_trading(duration_days=duration)
        _settings_audit_append({"type": "paper_trading", "action": "activate", "duration_days": duration})
        return {"ok": True, "status": result}
    elif action == "disable":
        result = pt.disable_paper_trading()
        _settings_audit_append({"type": "paper_trading", "action": "disable"})
        return {"ok": True, "status": result}
    else:
        raise HTTPException(400, "action must be 'activate' or 'disable'")


# -- Profile Manager API (rendered inside main dashboard's Settings tab; no standalone page) --
import profile_manager as _pm

@app.get("/api/profiles/list")
async def profiles_list():
    items = []
    if _pm.PROFILES_DIR.exists():
        for p in sorted(_pm.PROFILES_DIR.glob("*.json")):
            data = json.loads(p.read_text())
            items.append({
                "name": data.get("_profile_name", p.stem),
                "description": data.get("_description", ""),
                "tradeoffs": data.get("_tradeoffs", ""),
                "backtest": data.get("_backtest"),
            })
    return {"profiles": items, "active": _pm._current_profile_name()}

@app.get("/api/profiles/diff")
async def profiles_diff(name: str):
    try:
        cfg = _pm._load_config()
        profile = _pm._load_profile(name)
    except SystemExit as e:
        raise HTTPException(404, str(e))
    rows = _pm._collect_diff(cfg, profile)
    return {"changes": [{"key": k, "before": b, "after": a} for (k, b, a) in rows]}

@app.post("/api/profiles/switch")
async def profiles_switch(req: Request):
    body = await req.json()
    name = body.get("name")
    note = body.get("note", "")
    if not name:
        raise HTTPException(400, "Missing 'name'")
    if not (_pm.PROFILES_DIR / f"{name}.json").exists():
        raise HTTPException(404, f"Profile '{name}' not found")
    # Use manager's switch logic
    cfg = _pm._load_config()
    profile = _pm._load_profile(name)
    rows = _pm._collect_diff(cfg, profile)
    if not rows:
        return {"ok": True, "changed": 0, "message": f"Profile '{name}' already matches current config"}
    _pm.switch(name, note)
    return {"ok": True, "changed": len(rows), "profile": name}

@app.get("/api/profiles/history")
async def profiles_history(limit: int = 50):
    if not _pm.HISTORY_JSONL.exists():
        return {"history": []}
    lines = _pm.HISTORY_JSONL.read_text().splitlines()
    entries = [json.loads(l) for l in lines[-limit:]]
    return {"history": list(reversed(entries))}  # newest first


# -- Profile P&L attribution + unified audit tail --
import audit as _audit

@app.get("/api/profiles/attribution")
async def profiles_attribution():
    return {"rows": _audit.profile_attribution()}

@app.get("/api/audit/tail")
async def audit_tail(limit: int = 200, type: Optional[str] = None):
    return {"entries": list(reversed(_audit.tail(limit=limit, type_filter=type)))}


# -- Audit 360 (system health) --

_audit_360_cache: dict = {}
_AUDIT_360_TTL = 300  # 5 min — dashboard polls badge on every page load

@app.get("/api/audit_360")
async def audit_360_run(quick: bool = True, force: bool = False):
    """
    Run audit_360 on demand and return structured JSON.
    `quick=true` (default) skips network probes (~0.4s vs ~2.2s).
    Cached 5 min per quick-mode flag — pass `force=true` to bypass.
    """
    import time as _time
    import audit_360 as _a360
    from dataclasses import asdict as _asdict

    cache_key = f"quick={quick}"
    now = _time.time()
    cached = _audit_360_cache.get(cache_key)
    if cached and not force and (now - cached["ts"]) < _AUDIT_360_TTL:
        return cached["data"]

    results: list = []
    for name, fn, opts in _a360.CHECKS:
        if "quick" in opts:
            wrapped = (lambda f=fn: f(quick=quick))
        else:
            wrapped = (lambda f=fn: f())
        results.append(_a360._run(name, wrapped))
    overall = round(sum(r.score() for r in results) / max(1, len(results)))
    payload = {
        "timestamp": datetime.now().isoformat(),
        "overall_score": overall,
        "health_label": "HEALTHY" if overall >= 85 else ("DEGRADED" if overall >= 60 else "UNHEALTHY"),
        "pass_count": sum(1 for r in results if r.status == "PASS"),
        "warn_count": sum(1 for r in results if r.status == "WARN"),
        "fail_count": sum(1 for r in results if r.status == "FAIL"),
        "checks": [_asdict(r) for r in results],
    }
    _audit_360_cache[cache_key] = {"ts": now, "data": payload}
    return payload


# -- Tab visibility admin --

_TAB_DEFAULTS_PATH = BASE_DIR / "data" / "tab_defaults.json"
_ADMIN_USERNAMES = {"gari"}  # gari is the admin

def _load_tab_defaults() -> dict:
    """Return current admin defaults; safe-default if file missing."""
    if not _TAB_DEFAULTS_PATH.exists():
        return {
            "default_profile": "trader",
            "force_hidden_tabs": [],
            "locked_essential_tabs": ["settings", "cheatsheet"],
            "updated_by": None,
            "updated_at": None,
        }
    try:
        return json.loads(_TAB_DEFAULTS_PATH.read_text())
    except Exception:
        return {"default_profile": "trader", "force_hidden_tabs": [], "locked_essential_tabs": ["settings"]}


@app.get("/api/admin/tab_defaults")
async def get_tab_defaults():
    """Anyone can read the defaults — they're applied to all users on load."""
    return _load_tab_defaults()


@app.post("/api/admin/tab_defaults")
async def set_tab_defaults(payload: dict, credentials: HTTPBasicCredentials = Depends(_check_auth)):
    """Only gari (admin) can write."""
    if isinstance(credentials, Response):
        return credentials
    if credentials.username not in _ADMIN_USERNAMES:
        raise HTTPException(403, "Admin only")
    valid_profiles = {"beginner", "trader", "quant", "all"}
    profile = payload.get("default_profile", "trader")
    if profile not in valid_profiles:
        raise HTTPException(400, f"default_profile must be one of {valid_profiles}")
    force_hidden = payload.get("force_hidden_tabs") or []
    locked = payload.get("locked_essential_tabs") or ["settings", "cheatsheet"]
    if not isinstance(force_hidden, list) or not isinstance(locked, list):
        raise HTTPException(400, "force_hidden_tabs and locked_essential_tabs must be arrays")
    out = {
        "default_profile": profile,
        "force_hidden_tabs": [str(t) for t in force_hidden],
        "locked_essential_tabs": [str(t) for t in locked],
        "updated_by": credentials.username,
        "updated_at": datetime.now().isoformat(),
    }
    _TAB_DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TAB_DEFAULTS_PATH.write_text(json.dumps(out, indent=2))
    return {"ok": True, "saved": out}


@app.get("/api/admin/whoami")
async def whoami(credentials: HTTPBasicCredentials = Depends(_check_auth)):
    """Tell the dashboard if the current user is admin."""
    if isinstance(credentials, Response):
        return credentials
    return {
        "username": credentials.username,
        "is_admin": credentials.username in _ADMIN_USERNAMES,
    }


@app.get("/audit_360.html", response_class=HTMLResponse)
async def audit_360_html():
    """Return the most recent saved HTML report (or a stub if none)."""
    latest = BASE_DIR / "cache" / "audit_360_latest.html"
    if latest.exists():
        try:
            return HTMLResponse(latest.read_text())
        except Exception:
            pass
    # fall back to most-recent dated file
    candidates = sorted((BASE_DIR / "cache").glob("audit_360_*.html"), reverse=True)
    if candidates:
        return HTMLResponse(candidates[0].read_text())
    return HTMLResponse(
        "<h2 style='font-family:Aptos'>No audit_360 report yet.</h2>"
        "<p>Run <code>python3 audit_360.py</code> to generate one,"
        " or hit <code>/api/audit_360?quick=true</code> for live JSON.</p>"
    )


# -- Bundle time-travel --
import bundle_archive as _ba

def _picks_outcome_index() -> dict:
    """Return {(ticker, run_date): {pct_chg, win, exit_date}} from picks_history."""
    idx: dict = {}
    try:
        ph = json.loads((BASE_DIR / "cache" / "picks_history.json").read_text())
    except Exception:
        return idx
    for t in (ph.get("trades") or []):
        key = (t.get("ticker"), t.get("run_date") or t.get("entry_date"))
        if key[0] and key[1]:
            idx[key] = {
                "pct_chg":  t.get("pct_chg"),
                "win":      t.get("win"),
                "exit_date": t.get("exit_date"),
                "hold_days": t.get("hold_days"),
            }
    return idx

@app.get("/api/bundles/list")
async def bundles_list():
    snaps = _ba.list_snapshots()
    return {"snapshots": snaps}

@app.get("/api/bundles/{date}")
async def bundles_get(date: str, include_outcomes: bool = True):
    snap = _ba.load_snapshot(date)
    if snap is None:
        raise HTTPException(404, f"No snapshot for {date}")
    if include_outcomes:
        idx = _picks_outcome_index()
        for r in snap.get("all_scored", []):
            t = r.get("ticker")
            if t:
                oc = idx.get((t, date))
                if oc:
                    r["outcome"] = oc
    return snap

@app.get("/api/bundles/compare/ab")
async def bundles_compare(a: str, b: str, verdict: Optional[str] = None):
    """Compare two snapshots. verdict filter: 'BUY' | 'WATCH' | 'SHORT' | None."""
    sa = _ba.load_snapshot(a)
    sb = _ba.load_snapshot(b)
    if sa is None or sb is None:
        raise HTTPException(404, f"Missing snapshot: a={sa is None}, b={sb is None}")

    def _tickers(snap, vfilter):
        rows = snap.get("all_scored", [])
        if vfilter:
            rows = [r for r in rows if (r.get("decision") or {}).get("verdict") == vfilter]
        return {r.get("ticker"): r for r in rows if r.get("ticker")}

    ta = _tickers(sa, verdict)
    tb = _tickers(sb, verdict)
    shared    = sorted(set(ta) & set(tb))
    only_a    = sorted(set(ta) - set(tb))
    only_b    = sorted(set(tb) - set(ta))

    idx = _picks_outcome_index()
    def _enrich(tickers, snap_date, src):
        out = []
        for t in tickers:
            r = src[t]
            oc = idx.get((t, snap_date))
            out.append({
                "ticker":  t,
                "score":   r.get("score"),
                "verdict": (r.get("decision") or {}).get("verdict"),
                "setup":   r.get("setup_type"),
                "rs_rank": r.get("rs_rank"),
                "outcome": oc,
            })
        return out

    return {
        "a": {"date": a, "meta": {k: sa.get(k) for k in ("regime","regime4","profile","spy_price","vix","breadth_50","counts")}},
        "b": {"date": b, "meta": {k: sb.get(k) for k in ("regime","regime4","profile","spy_price","vix","breadth_50","counts")}},
        "shared": _enrich(shared, a, ta),
        "only_a": _enrich(only_a, a, ta),
        "only_b": _enrich(only_b, b, tb),
    }


# -- Scan trigger + status --
import subprocess
import signal as _sig

_SCAN_LOG = BASE_DIR / "cache" / "logs" / "scan_ui.log"
_SCAN_PID = BASE_DIR / "cache" / "logs" / "scan_ui.pid"

def _scan_is_running() -> tuple[bool, Optional[int]]:
    if not _SCAN_PID.exists():
        return False, None
    try:
        pid = int(_SCAN_PID.read_text().strip())
        # Check process alive (signal 0)
        os.kill(pid, 0)
        return True, pid
    except (ProcessLookupError, ValueError, PermissionError):
        try:
            _SCAN_PID.unlink()
        except Exception:
            pass
        return False, None

@app.post("/api/scan/start")
async def scan_start():
    running, pid = _scan_is_running()
    if running:
        raise HTTPException(409, f"Scan already running (PID {pid})")
    _SCAN_LOG.parent.mkdir(parents=True, exist_ok=True)
    # Launch detached
    logf = open(_SCAN_LOG, "w")
    proc = subprocess.Popen(
        ["python3", str(BASE_DIR / "swing_trade.py")],
        cwd=str(BASE_DIR),
        stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _SCAN_PID.write_text(str(proc.pid))
    return {"ok": True, "pid": proc.pid, "log": str(_SCAN_LOG)}

@app.get("/api/scan/status")
async def scan_status(tail_lines: int = 40):
    running, pid = _scan_is_running()
    log_tail = ""
    step = ""
    if _SCAN_LOG.exists():
        try:
            txt = _SCAN_LOG.read_text(errors="replace")
            lines = [l for l in txt.splitlines() if l.strip()]
            log_tail = "\n".join(lines[-tail_lines:])
            # Extract latest step marker
            for l in reversed(lines):
                if "Step " in l and "INFO" in l:
                    step = l.split("INFO:")[-1].strip() if "INFO:" in l else l
                    break
                if "Done!" in l:
                    step = "Done"
                    break
        except Exception:
            pass
    return {"running": running, "pid": pid, "step": step, "log_tail": log_tail}

@app.post("/api/scan/cancel")
async def scan_cancel():
    running, pid = _scan_is_running()
    if not running:
        return {"ok": False, "message": "No scan running"}
    try:
        os.kill(pid, _sig.SIGTERM)
        return {"ok": True, "message": f"Sent SIGTERM to PID {pid}"}
    except Exception as e:
        raise HTTPException(500, str(e))



# -- Tech Matrix + SMC Matrix (for SMC+ tab) --
def _schwab_multi_timeframe(ticker: str) -> dict:
    """[name kept for compat] Fetch 1H, 4H, Daily, Weekly via EODHD."""
    import pandas as pd
    import eodhd_client as _eod
    out = {}

    # 1H intraday
    try:
        rows = _eod.intraday(ticker, interval="1h")
        if rows:
            df = pd.DataFrame(rows)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()
            df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
            if not df.empty:
                out["1H"] = df[["Open","High","Low","Close","Volume"]]
    except Exception:
        pass

    # 4H — resample 1H
    if "1H" in out:
        try:
            df_4h = out["1H"].resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"
            }).dropna()
            if not df_4h.empty:
                out["4H"] = df_4h
        except Exception:
            pass

    # Daily + Weekly
    from datetime import date as _d, timedelta as _td
    today = _d.today()
    for tf, period_arg, lookback_days in [("Daily", "d", 365), ("Weekly", "w", 730)]:
        try:
            from_dt = (today - _td(days=lookback_days)).isoformat()
            rows = _eod.eod(ticker, from_date=from_dt, period=period_arg)
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                df = df.rename(columns={"open":"Open","high":"High","low":"Low","adjusted_close":"Close","volume":"Volume"})
                if not df.empty:
                    out[tf] = df[["Open","High","Low","Close","Volume"]]
        except Exception:
            pass

    return out

def _compute_tf_indicators(df):
    """Compute technical indicators directly from OHLCV DataFrame."""
    import numpy as np
    c = df["Close"].squeeze()
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    v = df["Volume"].squeeze() if "Volume" in df.columns else None
    price = float(c.iloc[-1])

    def _ema(s, n):
        return float(s.ewm(span=n, adjust=False).mean().iloc[-1]) if len(s) >= n else None

    ema5  = _ema(c, 5)
    ema8  = _ema(c, 8)
    ema13 = _ema(c, 13)
    ema20 = _ema(c, 20)
    ema21 = _ema(c, 21)
    ema50 = _ema(c, 50)
    ema200 = _ema(c, 200) if len(c) >= 200 else None

    # EMA stack: bull if price > ema8 > ema21 > ema50
    stack = "N/A"
    if ema8 and ema21 and ema50:
        if price > ema8 > ema21 > ema50:
            stack = "Bull"
        elif price < ema8 < ema21 < ema50:
            stack = "Bear"
        else:
            stack = "Mixed"

    # RSI (14)
    rsi = None
    if len(c) >= 15:
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_s = 100 - (100 / (1 + rs))
        rsi = round(float(rsi_s.iloc[-1]), 1) if not np.isnan(rsi_s.iloc[-1]) else None

    # MACD (12, 26, 9)
    macd_signal = "N/A"
    if len(c) >= 26:
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        if float(hist.iloc[-1]) > 0 and float(hist.iloc[-2]) <= 0:
            macd_signal = "GOLDEN CROSS"
        elif float(hist.iloc[-1]) < 0 and float(hist.iloc[-2]) >= 0:
            macd_signal = "DEATH CROSS"
        elif float(hist.iloc[-1]) > 0:
            macd_signal = "BULLISH"
        else:
            macd_signal = "BEARISH"

    # ADX (14)
    adx_val = None
    adx_trend = "N/A"
    if len(c) >= 28:
        try:
            tr = np.maximum(h - l, np.maximum(abs(h - c.shift(1)), abs(l - c.shift(1))))
            atr14 = tr.rolling(14).mean()
            plus_dm = np.where((h.diff() > 0) & (h.diff() > -l.diff()), h.diff(), 0)
            minus_dm = np.where((-l.diff() > 0) & (-l.diff() > h.diff()), -l.diff(), 0)
            plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr14)
            minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr14)
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
            adx_s = dx.rolling(14).mean()
            adx_val = round(float(adx_s.iloc[-1]), 1) if not np.isnan(adx_s.iloc[-1]) else None
            if adx_val:
                adx_trend = "Strong" if adx_val >= 25 else "Weak"
        except Exception:
            pass

    # VWAP (if volume available)
    vwap = None
    vwap_above = None
    if v is not None and len(v) > 0:
        cum_vol = v.cumsum()
        cum_pv = (c * v).cumsum()
        if float(cum_vol.iloc[-1]) > 0:
            vwap = round(float(cum_pv.iloc[-1] / cum_vol.iloc[-1]), 2)
            vwap_above = price > vwap

    # ATR (14)
    atr = None
    if len(c) >= 15:
        tr = np.maximum(h - l, np.maximum(abs(h - c.shift(1)), abs(l - c.shift(1))))
        atr = round(float(tr.rolling(14).mean().iloc[-1]), 2)

    # Volume trend
    vol_trend = None
    if v is not None and len(v) >= 20:
        v20 = float(v.rolling(20).mean().iloc[-1])
        vol_trend = round(float(v.iloc[-1]) / v20, 2) if v20 > 0 else None

    # Ichimoku cloud (simplified — conversion/base lines)
    cloud = "N/A"
    tk_cross = "None"
    if len(c) >= 52:
        conv = (h.rolling(9).max() + l.rolling(9).min()) / 2
        base = (h.rolling(26).max() + l.rolling(26).min()) / 2
        span_a = ((conv + base) / 2).shift(26)
        span_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
        sa = float(span_a.iloc[-1]) if not np.isnan(span_a.iloc[-1]) else None
        sb = float(span_b.iloc[-1]) if not np.isnan(span_b.iloc[-1]) else None
        if sa and sb:
            if price > max(sa, sb):
                cloud = "Above"
            elif price < min(sa, sb):
                cloud = "Below"
            else:
                cloud = "Inside"
        cv = float(conv.iloc[-1])
        bv = float(base.iloc[-1])
        if cv > bv:
            tk_cross = "Bull"
        elif cv < bv:
            tk_cross = "Bear"

    # Supertrend (simplified — ATR-based)
    supertrend = None
    if atr and ema21:
        upper = price + 2 * atr
        lower = price - 2 * atr
        supertrend = price > (ema21 - atr)

    return {
        "close": round(price, 2),
        "ema5": round(ema5, 2) if ema5 else None,
        "ema8": round(ema8, 2) if ema8 else None,
        "ema13": round(ema13, 2) if ema13 else None,
        "ema20": round(ema20, 2) if ema20 else None,
        "ema21": round(ema21, 2) if ema21 else None,
        "ema50": round(ema50, 2) if ema50 else None,
        "ema200": round(ema200, 2) if ema200 else None,
        "ema_stack": stack,
        "rsi": rsi,
        "macd_signal": macd_signal,
        "adx": adx_val,
        "adx_trend": adx_trend,
        "vwap": vwap,
        "vwap_above": vwap_above,
        "atr": atr,
        "vol_trend": vol_trend,
        "cloud": cloud,
        "tk_cross": tk_cross,
        "supertrend_bull": supertrend,
    }

@app.get("/api/tech-matrix/{ticker}")
async def tech_matrix(ticker: str):
    try:
        import pandas as pd
        mtf = _schwab_multi_timeframe(ticker.upper())
        if not mtf:
            return {"error": "No multi-timeframe data available"}
        result = {}
        for tf, df in mtf.items():
            if df is not None and not df.empty and len(df) >= 20:
                try:
                    result[tf] = _compute_tf_indicators(df)
                except Exception as e:
                    result[tf] = {"error": str(e)}
        return {"ticker": ticker.upper(), "timeframes": result}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/smc-matrix/{ticker}")
async def smc_matrix(ticker: str):
    try:
        from analysis import score_smc
        mtf = _schwab_multi_timeframe(ticker.upper())
        if not mtf:
            return {"error": "No multi-timeframe data available"}
        result = {}
        for tf, df in mtf.items():
            if df is not None and not df.empty and len(df) >= 20:
                try:
                    price = float(df["Close"].iloc[-1]) if "Close" in df.columns else 0
                    smc = score_smc(df, price, {})
                    if isinstance(smc, dict):
                        result[tf] = smc
                    else:
                        result[tf] = {"score": smc}
                except Exception as e:
                    result[tf] = {"error": str(e)}
        return {"ticker": ticker.upper(), "timeframes": result}
    except Exception as e:
        return {"error": str(e)}


# -- Movers — REMOVED 2026-04-25 (Schwab decommissioned) --
# Could be replaced with EODHD screener API call for sorted-by-change list.
@app.get("/api/schwab/movers")
async def schwab_movers(index: str = "$SPX", direction: str = "up"):
    return {"movers": [], "index": index, "direction": direction,
            "error": "movers endpoint deprecated; use /api/screener instead"}


# -- Live single-ticker analysis (search Go button) --
@app.get("/api/analyze/{ticker}")
async def analyze_ticker_api(ticker: str):
    """Run full deep-dive on a ticker — same as Custom Tracking analyze."""
    ticker = ticker.upper().strip()
    if not ticker:
        raise HTTPException(400, "Missing ticker")
    try:
        from swing_trade import run_deep_dive
        result = run_deep_dive(ticker)
        if not result:
            # Fallback: return at least an EODHD quote so the dashboard can show something
            try:
                import eodhd_client as _eod
                rt = _eod.real_time(ticker)
                f  = _eod.fundamentals(ticker) or {}
                H  = (f.get("Highlights") or {}) if isinstance(f, dict) else {}
                G  = (f.get("General")    or {}) if isinstance(f, dict) else {}
                px = None
                if isinstance(rt, dict):
                    px = rt.get("close") or rt.get("previousClose")
                if px and px != "NA":
                    px = float(px)
                    return {
                        "ticker": ticker,
                        "name": G.get("Name", ticker),
                        "price": px,
                        "score": 0,
                        "decision": {"verdict": "N/A", "reason": "No OHLCV data available — quote only", "color": "#94a3b8"},
                        "fundamentals": {"score": 0, "details": {"pe": H.get("PERatio"), "eps": H.get("EarningsShare"), "mcap": G.get("MarketCapitalization")}},
                        "technicals": {"score": 0, "indicators": {}},
                        "trade_plan": {"entry": px, "stop": 0, "target1": 0, "rr_ratio": 0},
                        "rs_rank": 0,
                        "sector": G.get("Sector", "Unknown"),
                        "_partial": True,
                        "_error": "Quote-only data from EODHD; no scoring available.",
                    }
            except Exception:
                pass
            raise HTTPException(404, f"No data for {ticker}")
        import json as _j
        import math
        def _clean(obj):
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_clean(v) for v in obj]
            return obj
        return json.loads(_j.dumps(_clean(result), default=str))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# -- Pullback Scanner --
@app.get("/api/pullback-scanner")
async def pullback_scanner_api():
    try:
        from pullback_scanner import scan_from_archive
        results = scan_from_archive()
        triggered = [r for r in results if r["status"] == "TRIGGERED"]
        waiting = [r for r in results if r["status"] == "WAITING"]
        watching = [r for r in results if r["status"] == "WATCHING"]
        return {
            "total": len(results),
            "triggered": len(triggered),
            "waiting": len(waiting),
            "watching": len(watching),
            "results": results,
        }
    except Exception as e:
        return {"error": str(e), "results": []}


# -- Earnings Drift Scanner --
@app.get("/api/earnings-drift")
async def earnings_drift_api():
    try:
        from earnings_drift_scanner import scan_from_archive
        results = scan_from_archive()
        return {"total": len(results), "results": results}
    except Exception as e:
        return {"error": str(e), "results": []}

# -- Options Flow Scanner — REMOVED 2026-04-25 (no options data in EODHD plan) --
@app.get("/api/options-flow")
async def options_flow_api():
    return {"total": 0, "results": [], "error": "options data removed; not in EODHD All-In-One"}

# -- Individual scanner APIs --
@app.get("/api/insider-clusters")
async def insider_clusters_api():
    try:
        from insider_cluster_scanner import scan_from_archive
        return {"total": len(r := scan_from_archive()), "results": r}
    except Exception as e:
        return {"error": str(e), "results": []}

@app.get("/api/sector-rotation")
async def sector_rotation_api():
    try:
        from sector_rotation_scanner import scan_from_archive
        return {"total": len(r := scan_from_archive()), "results": r}
    except Exception as e:
        return {"error": str(e), "results": []}

@app.get("/api/squeeze-setups")
async def squeeze_setups_api():
    try:
        from squeeze_scanner import scan_from_archive
        return {"total": len(r := scan_from_archive()), "results": r}
    except Exception as e:
        return {"error": str(e), "results": []}

# -- Today's Signals (unified across ALL 6 strategies) --
@app.get("/api/signals/today")
async def todays_signals():
    signals = []
    scanners = [
        ("pullback_scanner", "scan_from_archive", ["TRIGGERED", "WAITING"], "Pullback", "\U0001f3af"),
        ("earnings_drift_scanner", "scan_from_archive", ["FRESH", "ACTIVE"], "Earnings Drift", "\U0001f4c8"),
        ("insider_cluster_scanner", "scan_from_archive", ["STRONG", "MODERATE"], "Insider Cluster", "\U0001f454"),
        ("sector_rotation_scanner", "scan_from_archive", ["LEADING", "IMPROVING"], "Sector Rotation", "\U0001f504"),
        ("squeeze_scanner", "scan_from_archive", ["SETUP", "BUILDING"], "Short Squeeze", "\U0001f680"),
    ]
    for mod_name, fn_name, statuses, strategy, icon in scanners:
        try:
            mod = __import__(mod_name)
            fn = getattr(mod, fn_name)
            for r in fn():
                if r.get("status") in statuses:
                    r["strategy"] = strategy
                    r["icon"] = icon
                    signals.append(r)
        except Exception:
            pass
    # Add PULLBACK_WAIT tickers from last bundle
    try:
        b = json.loads((BASE_DIR / "cache" / "last_bundle.json").read_text())
        for r in b.get("all_scored", []):
            state = r.get("state") or {}
            if state.get("action") == "PULLBACK_WAIT" and state.get("proximity") != "dropped":
                signals.append({
                    "ticker": r.get("ticker"),
                    "price": r.get("price"),
                    "score": r.get("score"),
                    "rs_rank": r.get("rs_rank"),
                    "status": state.get("proximity", "patient").upper(),
                    "strategy": "Pullback Wait",
                    "icon": "\u23f3",
                    "rr": (r.get("trade_plan") or {}).get("rr_ratio", 0),
                    "stop": (r.get("trade_plan") or {}).get("stop"),
                    "target": (r.get("trade_plan") or {}).get("target1"),
                    "distance_to_entry_pct": state.get("distance_to_entry_pct"),
                    "entry_zone": state.get("zones", {}).get("primary_zone"),
                    "phase": state.get("phase"),
                    "dashboard_message": state.get("dashboard_message"),
                    "sector": r.get("sector"),
                })
    except Exception:
        pass

    signals.sort(key=lambda x: -x.get("rr", 0))
    return {"total": len(signals), "signals": signals}

# -- Live MTM (Performance tab auto-refresh) --
@app.get("/api/mtm")
async def get_mtm():
    """Live mark-to-market: D1-D5, W1, W2, M1 returns for all picks with live Schwab prices."""
    try:
        # Update archive with today's bars first (Schwab-instant)
        try:
            from data_archive import delta_update
            delta_update()
        except Exception:
            pass
        from tracker import mark_to_market
        mtm = mark_to_market()
        import json as _j
        return JSONResponse(_j.loads(_j.dumps(mtm, default=str)))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# -- Live price (lightweight, for UI polling) --
@app.get("/api/price/{ticker}")
async def get_live_price(ticker: str):
    """Live price from EODHD real-time (15-min delayed) for UI auto-refresh."""
    try:
        import eodhd_client as _eod
        rt = _eod.real_time(ticker.upper())
        if isinstance(rt, dict):
            px = rt.get("close") or rt.get("previousClose")
            prev = rt.get("previousClose")
            if px and px != "NA":
                px = float(px)
                chg_pct = round((px - float(prev)) / float(prev) * 100, 2) if prev and float(prev) > 0 else 0
                return {"price": round(px, 2), "change_pct": chg_pct, "source": "eodhd"}
    except Exception:
        pass
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker.upper())
        if df is not None and not df.empty:
            return {"price": round(float(df["Close"].iloc[-1]), 2), "change_pct": 0, "source": "archive"}
    except Exception:
        pass
    return {"price": None, "change_pct": 0, "source": "none"}

# -- Rules reference --
@app.get("/rules", response_class=HTMLResponse)
async def rules_page():
    p = BASE_DIR / "cache" / "rules.html"
    return HTMLResponse(p.read_text() if p.exists() else "<h1>Rules not generated</h1>")

# -- Stop / Target Alerts --
@app.get("/api/alerts/check")
async def alerts_check():
    """Check all open positions for stop/target proximity alerts.

    Returns a list of alert objects:
      - type: 'stop_hit' | 'stop_approaching' | 't1_hit'
      - ticker, message, color, current_price, threshold
    Price source: Schwab quote -> Polygon snapshot -> portfolio current_price fallback.
    """
    import time
    try:
        import portfolio_tracker as pt
        summary = pt.get_portfolio_summary()
        positions = summary.get("positions", [])
        if not positions:
            return {"alerts": [], "ts": time.time(), "count": 0}

        alerts = []
        for p in positions:
            ticker = str(p.get("ticker", "")).upper()
            if not ticker:
                continue
            entry = float(p.get("entry_price") or 0)
            stop_px = float(p.get("stop") or 0)
            t1 = float(p.get("target1") or p.get("t1") or 0)
            direction = str(p.get("direction", "long")).lower()

            # Fetch current price via EODHD real-time
            current = None
            try:
                import eodhd_client as _eod
                rt = _eod.real_time(ticker)
                if isinstance(rt, dict):
                    px = rt.get("close") or rt.get("previousClose")
                    if px and px != "NA":
                        current = float(px)
            except Exception:
                pass
            if not current:
                try:
                    from data_fetcher import fetch_ohlcv_with_failover
                    df, _ = fetch_ohlcv_with_failover(ticker, days=2)
                    if df is not None and not df.empty:
                        current = float(df["Close"].iloc[-1])
                except Exception:
                    pass
            if not current:
                current = float(p.get("current_price") or entry)

            current = float(current)
            if current <= 0 or entry <= 0:
                continue

            # T1 hit check (long: price >= T1, short: price <= T1)
            if t1 > 0:
                t1_hit = (current >= t1) if direction == "long" else (current <= t1)
                if t1_hit:
                    alerts.append({
                        "type": "t1_hit",
                        "ticker": ticker,
                        "message": f"Move stop to breakeven for {ticker} — T1 ${t1:.2f} reached",
                        "color": "#22c55e",
                        "current_price": round(current, 2),
                        "threshold": round(t1, 2),
                    })

            # Stop proximity / hit checks
            if stop_px > 0:
                if direction == "long":
                    dist_pct = (current - stop_px) / current * 100 if current > 0 else 999
                    if current <= stop_px:
                        alerts.append({
                            "type": "stop_hit",
                            "ticker": ticker,
                            "message": f"STOP HIT for {ticker}! Price ${current:.2f} <= stop ${stop_px:.2f}",
                            "color": "#ef4444",
                            "current_price": round(current, 2),
                            "threshold": round(stop_px, 2),
                        })
                    elif dist_pct <= 2.0:
                        alerts.append({
                            "type": "stop_approaching",
                            "ticker": ticker,
                            "message": f"Stop approaching for {ticker} — {dist_pct:.1f}% away (${current:.2f} vs ${stop_px:.2f})",
                            "color": "#fbbf24",
                            "current_price": round(current, 2),
                            "threshold": round(stop_px, 2),
                        })
                else:  # short
                    dist_pct = (stop_px - current) / current * 100 if current > 0 else 999
                    if current >= stop_px:
                        alerts.append({
                            "type": "stop_hit",
                            "ticker": ticker,
                            "message": f"STOP HIT for {ticker}! Price ${current:.2f} >= stop ${stop_px:.2f}",
                            "color": "#ef4444",
                            "current_price": round(current, 2),
                            "threshold": round(stop_px, 2),
                        })
                    elif dist_pct <= 2.0:
                        alerts.append({
                            "type": "stop_approaching",
                            "ticker": ticker,
                            "message": f"Stop approaching for {ticker} — {dist_pct:.1f}% away (${current:.2f} vs ${stop_px:.2f})",
                            "color": "#fbbf24",
                            "current_price": round(current, 2),
                            "threshold": round(stop_px, 2),
                        })

        # Sort: stop_hit first, then stop_approaching, then t1_hit
        priority = {"stop_hit": 0, "stop_approaching": 1, "t1_hit": 2}
        alerts.sort(key=lambda a: priority.get(a["type"], 9))
        return {"alerts": alerts, "ts": time.time(), "count": len(alerts)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── User & Role Management API (2026-05-07) ──────────────────────────────
# Admin-only endpoints for managing users and custom roles.

@app.get("/api/whoami")
async def api_whoami(credentials: HTTPBasicCredentials = Depends(_check_auth)):
    """Return the current authenticated user + their role permissions."""
    if isinstance(credentials, Response):
        return credentials
    u = _auth_mod.get_user(credentials.username) or {}
    perms = _auth_mod.get_user_permissions(credentials.username)
    role = _auth_mod.get_role(u.get("role") or "viewer") or {}
    return {
        "user": u,
        "role": role,
        "permissions": perms,
        "is_admin": _auth_mod.is_admin(credentials.username),
    }


@app.get("/api/users")
async def api_list_users(credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    return {"users": _auth_mod.list_users()}


@app.post("/api/users")
async def api_create_user(payload: dict, credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        u = _auth_mod.create_user(
            username     = payload.get("username", "").lower().strip(),
            password     = payload.get("password", ""),
            role         = payload.get("role", "viewer"),
            display_name = payload.get("display_name", ""),
            email        = payload.get("email", ""),
            disabled     = bool(payload.get("disabled", False)),
        )
        return {"ok": True, "user": u}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.patch("/api/users/{username}")
async def api_update_user(username: str, payload: dict,
                           credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        u = _auth_mod.update_user(username, **payload)
        return {"ok": True, "user": u}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.delete("/api/users/{username}")
async def api_delete_user(username: str,
                           credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        ok = _auth_mod.delete_user(username)
        return {"ok": ok}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.post("/api/users/{username}/reset-password")
async def api_reset_password(username: str, payload: dict,
                              credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        ok = _auth_mod.change_password(username, payload.get("new_password", ""))
        return {"ok": ok}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.post("/api/users/me/change-password")
async def api_self_change_password(payload: dict,
                                    credentials: HTTPBasicCredentials = Depends(_security)):
    """Self-service password change. Verifies old password, updates to new,
    clears must_change_password. (Phase 2 — 2026-05-08)"""
    user = _auth_mod.verify_user(credentials.username, credentials.password)
    if not user:
        return Response(status_code=401, headers={"WWW-Authenticate": "Basic"},
                        content="Unauthorized")
    old_pw = payload.get("old_password", "")
    new_pw = payload.get("new_password", "")
    if not _auth_mod.verify_user(credentials.username, old_pw):
        return Response(status_code=400, content="Old password is incorrect")
    if len(new_pw) < 8:
        return Response(status_code=400, content="New password must be at least 8 characters")
    try:
        _auth_mod.change_password(credentials.username, new_pw)
        return {"ok": True}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.get("/api/audit_log")
async def api_audit_log(limit: int = 100, user: Optional[str] = None,
                         action: Optional[str] = None, since_iso: Optional[str] = None,
                         credentials: HTTPBasicCredentials = Depends(_require_admin)):
    """Admin-only: tail the write-action audit log (newest first).

    Query params:
      limit       max entries to return (default 100)
      user        filter to one username
      action      filter to one action key (submit_trade, move_stops, ...)
      since_iso   only entries after this ISO timestamp
    """
    if isinstance(credentials, Response):
        return credentials
    import audit_log as _alog
    return {"entries": _alog.list_recent(limit=limit, user=user, action=action,
                                            since_iso=since_iso)}


@app.get("/api/roles")
async def api_list_roles(credentials: HTTPBasicCredentials = Depends(_check_auth)):
    """Anyone authenticated can read roles (needed for V2 to show role names).
    Mutating endpoints below require admin."""
    if isinstance(credentials, Response):
        return credentials
    return {"roles": _auth_mod.list_roles()}


@app.post("/api/roles")
async def api_create_role(payload: dict,
                           credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        r = _auth_mod.create_role(
            role_id     = payload.get("id", "").lower().strip(),
            name        = payload.get("name", ""),
            description = payload.get("description", ""),
            color       = payload.get("color", "info"),
            tabs        = payload.get("permissions", {}).get("tabs") or payload.get("tabs"),
            actions     = payload.get("permissions", {}).get("actions") or payload.get("actions"),
        )
        return {"ok": True, "role": r}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.patch("/api/roles/{role_id}")
async def api_update_role(role_id: str, payload: dict,
                           credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        r = _auth_mod.update_role(role_id, **payload)
        return {"ok": True, "role": r}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


@app.delete("/api/roles/{role_id}")
async def api_delete_role(role_id: str,
                           credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    try:
        ok = _auth_mod.delete_role(role_id)
        return {"ok": ok}
    except ValueError as e:
        return Response(status_code=400, content=str(e))


# -- Health check --
@app.get("/health")
async def health():
    return {"status": "ok", "server": "fastapi", "version": app.version}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7432)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=not args.no_reload, log_level="info")
