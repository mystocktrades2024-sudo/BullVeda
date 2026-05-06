"""FastAPI-based SwingTrade server. Port 7432. Auto-reload in dev."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, os, json
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
app = FastAPI(title="SwingTrade", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# -- Serve dashboard.html at / --
@app.get("/", response_class=HTMLResponse)
async def root():
    p = BASE_DIR / "cache" / "dashboard.html"
    return HTMLResponse(p.read_text() if p.exists() else "<h1>Run swing_trade.py first</h1>")

@app.get("/dashboard.css")
async def dashboard_css():
    p = BASE_DIR / "cache" / "dashboard.css"
    if p.exists():
        return HTMLResponse(p.read_text(), media_type="text/css")
    raise HTTPException(404)

@app.get("/dashboard.js")
async def dashboard_js():
    p = BASE_DIR / "cache" / "dashboard.js"
    if p.exists():
        return HTMLResponse(p.read_text(), media_type="application/javascript")
    raise HTTPException(404)

@app.get("/dashboard-data.js")
async def dashboard_data_js():
    p = BASE_DIR / "cache" / "dashboard-data.js"
    if p.exists():
        return HTMLResponse(p.read_text(), media_type="application/javascript")
    raise HTTPException(404)

# -- Portfolio --
@app.post("/api/portfolio/add")
async def portfolio_add(req: Request):
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
        return {"ok": True, "position": pos}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/portfolio/close")
async def portfolio_close(req: Request):
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
async def portfolio_undo(req: Request):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return pt.undo_close(str(body.get("undo_id", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/set_equity")
async def portfolio_set_equity(req: Request):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.set_equity(float(body["equity"]), reason=str(body.get("reason", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/move_stop_be")
async def portfolio_move_stop_be(req: Request):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.move_stop_to_breakeven(str(body["ticker"]).upper())}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/trail_stop")
async def portfolio_trail_stop(req: Request):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.trail_stop(str(body["ticker"]).upper(), float(body.get("atr_mult", 1.5)))}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/partial_close")
async def portfolio_partial_close(req: Request):
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
async def portfolio_adjust_stop(req: Request):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.adjust_stop(str(body["ticker"]).upper(), float(body["new_stop"]))}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/portfolio/update_notes")
async def portfolio_update_notes(req: Request):
    body = await req.json()
    import portfolio_tracker as pt
    try:
        return {"ok": True, **pt.update_notes(str(body["ticker"]).upper(), str(body.get("notes", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))

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

# -- Live / quote / whatif --
@app.get("/api/live/prices")
async def live_prices():
    import time, datetime as _dt
    try:
        import portfolio_tracker as pt
        from data_fetcher import fetch_ohlcv_with_failover
        now_et = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=-5)))
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        in_hours = (now_et.weekday() < 5) and (market_open <= now_et <= market_close)
        summary = pt.get_portfolio_summary()
        positions = summary.get("positions", [])
        if not positions:
            return {"prices": {}, "ts": time.time(), "in_hours": in_hours}
        prices = {}
        for p in positions:
            t = p.get("ticker", "")
            try:
                df, _ = fetch_ohlcv_with_failover(t, days=2)
                if df is not None and not df.empty:
                    prices[t] = round(float(df["Close"].iloc[-1]), 2)
                else:
                    prices[t] = p.get("current_price", p.get("entry_price"))
            except Exception:
                prices[t] = p.get("current_price", p.get("entry_price"))
        return {"prices": prices, "ts": time.time(), "in_hours": in_hours, "count": len(prices)}
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
    from data_fetcher import fetch_ohlcv_with_failover
    try:
        df, tier = fetch_ohlcv_with_failover(ticker.upper(), days=2)
        if df is None or df.empty:
            raise HTTPException(404, f"No data for {ticker}")
        return {"ticker": ticker.upper(), "price": round(float(df["Close"].iloc[-1]), 2), "source": tier}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

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
async def portfolio_clear():
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
