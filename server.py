"""FastAPI-based SwingTrade server. Port 7432. Auto-reload in dev."""
from fastapi import FastAPI, HTTPException, Request, Depends, Body
from typing import Optional, Dict, Any  # Python 3.9 compat — Pydantic needs Optional[X] not `X | None`
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn, os, json, secrets
from pathlib import Path
# Load .env so SLACK_WEBHOOK_URL, EODHD keys, etc. are in os.environ
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from typing import Optional

BASE_DIR = Path(__file__).parent
app = FastAPI(title="SwingTrade", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── API latency middleware (v6 ops telemetry · → api_latency_metrics) ───
# Buckets requests into 1-minute windows per (endpoint, method).
# Flushes to Supabase every 60s in a background task to avoid per-request blocking.
import time as _time_mod
import asyncio as _asyncio
import hashlib as _hash_mod
from collections import defaultdict as _dd
_LAT_BUCKETS: dict = _dd(lambda: {"count": 0, "errors": 0, "samples": []})
_LAT_LAST_FLUSH = _time_mod.time()


def _lat_bucket_key(endpoint: str, method: str, minute_ts: int) -> tuple:
    return (minute_ts, endpoint, method)


@app.middleware("http")
async def _api_latency_middleware(request, call_next):
    t0 = _time_mod.time()
    minute_ts = int(t0 // 60) * 60
    endpoint = request.url.path
    method = request.method
    try:
        response = await call_next(request)
        status = getattr(response, "status_code", 200)
    except Exception:
        status = 500
        raise
    finally:
        elapsed_ms = (_time_mod.time() - t0) * 1000.0
        # Only track API paths (skip static assets)
        if endpoint.startswith("/api/") or endpoint.startswith("/v2/"):
            key = _lat_bucket_key(endpoint, method, minute_ts)
            b = _LAT_BUCKETS[key]
            b["count"] += 1
            if status >= 400:
                b["errors"] += 1
            b["samples"].append(elapsed_ms)
            if len(b["samples"]) > 200:
                b["samples"] = b["samples"][-200:]
    return response


async def _flush_latency_buckets():
    """Background task: every 60s flush completed minute-buckets to Supabase."""
    global _LAT_LAST_FLUSH
    while True:
        try:
            await _asyncio.sleep(60)
            now = _time_mod.time()
            current_min = int(now // 60) * 60
            # Flush buckets whose minute has passed
            to_flush = []
            for (mts, ep, method), b in list(_LAT_BUCKETS.items()):
                if mts < current_min:
                    samples = sorted(b["samples"])
                    if not samples:
                        continue
                    n = len(samples)
                    p50 = samples[int(n * 0.50)] if n else 0
                    p95 = samples[int(n * 0.95)] if n >= 2 else samples[-1]
                    p99 = samples[int(n * 0.99)] if n >= 5 else samples[-1]
                    avg = sum(samples) / n
                    mx = samples[-1]
                    sync_key = _hash_mod.sha1(f"{mts}|{ep}|{method}".encode()).hexdigest()[:32]
                    from datetime import datetime, timezone
                    bucket_iso = datetime.fromtimestamp(mts, tz=timezone.utc).isoformat()
                    to_flush.append({
                        "bucket_minute": bucket_iso,
                        "endpoint": ep[:200],
                        "method": method,
                        "request_count": b["count"],
                        "error_count": b["errors"],
                        "p50_ms": round(p50, 2),
                        "p95_ms": round(p95, 2),
                        "p99_ms": round(p99, 2),
                        "avg_ms": round(avg, 2),
                        "max_ms": round(mx, 2),
                    })
                    del _LAT_BUCKETS[(mts, ep, method)]
            if to_flush:
                try:
                    from supabase_client import sb_client
                    sb = sb_client()
                    if sb is not None:
                        sb.table("api_latency_metrics").upsert(
                            to_flush, on_conflict="bucket_minute,endpoint,method"
                        ).execute()
                except Exception:
                    pass  # best-effort, don't crash the bg task
            _LAT_LAST_FLUSH = now
        except Exception:
            # Never let the bg task die
            await _asyncio.sleep(60)


@app.on_event("startup")
async def _start_latency_flusher():
    _asyncio.create_task(_flush_latency_buckets())

# PERF-4 (2026-05-09): Brotli compression first, GZip fallback.
# Brotli typically ~15-20% smaller than gzip on JSON/HTML at similar CPU cost.
# Cloudflare tunnel passes Accept-Encoding through, so the browser dictates.
# Order matters: ASGI middleware wraps responses outside-in. brotli-asgi runs
# AFTER gzip in the response chain, so when the client supports br, it short-
# circuits gzip and produces br directly. When it doesn't, gzip applies.
try:
    from brotli_asgi import BrotliMiddleware
    app.add_middleware(BrotliMiddleware, minimum_size=1000, quality=4)  # quality 4 = balanced speed/ratio
except ImportError:
    pass  # fall through to gzip-only if brotli-asgi not installed
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
    return RedirectResponse(url="/kairos.html")

@app.api_route("/v2/ml_edge_picks_history.jsonl", methods=["GET", "HEAD"])
async def _v2_ml_edge_picks_history(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """ML Edge picks history JSONL (2026-05-23 · History sub-tab data source).
    Serves from cache/ml_edge_picks_history.jsonl (canonical) — registered BEFORE
    the catch-all /v2/{path:path} so the explicit match wins."""
    if isinstance(auth, Response):
        return auth
    candidates = [
        BASE_DIR / "cache" / "ml_edge_picks_history.jsonl",
        BASE_DIR / "infra" / "prototype" / "ml_edge_picks_history.jsonl",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return Response(
                content=p.read_bytes(),
                media_type="application/x-ndjson",
                headers={"Cache-Control": "no-store"},
            )
    return Response(content=b"", media_type="application/x-ndjson", status_code=404)


@app.api_route("/v2/_v", methods=["GET","HEAD"])
async def _v2_module_version(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Max mtime under infra/prototype/{core,tabs}/. Used as ?v= cache-buster
    on dynamic ES module imports so edits to per-tab modules surface without
    a hard refresh of the page. (2026-05-09)"""
    if isinstance(auth, Response):
        return auth
    latest = 0
    for root in (_PROTOTYPE_DIR / "core", _PROTOTYPE_DIR / "tabs", _PROTOTYPE_DIR / "subtabs"):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in (".js", ".mjs"):
                try:
                    m = int(p.stat().st_mtime)
                    if m > latest:
                        latest = m
                except OSError:
                    pass
    return Response(content=str(latest or int(_time.time())),
                    media_type="text/plain",
                    headers={"Cache-Control": "no-store"})

@app.api_route("/v2/{path:path}", methods=["GET","HEAD"])
async def _v2_file(path: str, request: Request, auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    # Empty path (trailing slash on /v2/) → redirect to kairos, same as /v2
    if not path:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/kairos.html")
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

# -- Redirect / to Kairos (primary dashboard as of 2026-05-20). --
from fastapi.responses import RedirectResponse

@app.get("/")
async def root(auth: HTTPBasicCredentials = Depends(_check_auth)):
    return RedirectResponse(url="/kairos.html", status_code=302)

# -- /kairos.html — primary dashboard surface.
@app.api_route("/kairos.html", methods=["GET","HEAD"])
async def _kairos_page(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    p = (_PROTOTYPE_DIR / "kairos.html").resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "kairos.html not built")
    return Response(content=p.read_bytes(), media_type="text/html",
                    headers={"Cache-Control": "no-store"})

@app.api_route("/kairos", methods=["GET","HEAD"])
async def _kairos_redirect(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    return RedirectResponse(url="/kairos.html", status_code=302)

# -- /reports — HTML snapshot archive (2026-05-14)
# Lists all stored html_snapshots (dashboard, morning-briefing, etc.) with
# clickable links to view each one. Backs the Slack status links.
@app.api_route("/reports", methods=["GET", "HEAD"])
async def _reports_index(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    try:
        import db
        snapshots = db.list_html_snapshots(limit=200)
    except Exception as e:
        raise HTTPException(500, f"DB error: {e}")

    # Group by kind
    from collections import defaultdict
    by_kind = defaultdict(list)
    for s in snapshots:
        by_kind[s.get("kind") or "unknown"].append(s)

    rows_html = []
    for kind in sorted(by_kind.keys()):
        items = by_kind[kind]
        rows_html.append(f'<h3 style="margin-top:24px;color:#79c0ff">{kind} <span style="color:#7d8590;font-size:13px;font-weight:normal">({len(items)} snapshots, newest first)</span></h3>')
        rows_html.append('<table style="width:100%;border-collapse:collapse;font-size:13px">')
        rows_html.append('<tr style="background:#161b22;color:#7d8590"><th style="text-align:left;padding:6px 12px">ID</th><th style="text-align:left;padding:6px 12px">When</th><th style="text-align:left;padding:6px 12px">Label</th><th style="text-align:right;padding:6px 12px">Size</th><th style="padding:6px 12px"></th></tr>')
        for s in items[:50]:
            size_kb = (s.get("size_bytes") or 0) / 1024
            compressed = "🗜" if s.get("compressed") else ""
            rows_html.append(
                f'<tr style="border-bottom:1px solid #30363d">'
                f'<td style="padding:6px 12px;color:#7d8590">#{s["id"]}</td>'
                f'<td style="padding:6px 12px;color:#c9d1d9;font-family:monospace">{s.get("ts", "")[:19]}</td>'
                f'<td style="padding:6px 12px;color:#c9d1d9">{s.get("label", "")}</td>'
                f'<td style="padding:6px 12px;text-align:right;color:#7d8590">{size_kb:.0f}KB {compressed}</td>'
                f'<td style="padding:6px 12px;text-align:right"><a href="/reports/{s["id"]}" style="color:#3fb950;text-decoration:none">→ View</a></td>'
                f'</tr>'
            )
        rows_html.append('</table>')

    if not snapshots:
        rows_html.append('<p style="color:#7d8590">No snapshots yet. Run a scan to populate.</p>')

    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SwingTrade · Report Archive</title>
<style>
  body {{ background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'SF Pro',sans-serif;
         margin:0;padding:24px;max-width:1200px;margin:0 auto; }}
  h1 {{ margin:0 0 8px 0;font-size:24px;color:#f0f6fc;font-weight:600; }}
  .subtitle {{ color:#7d8590;margin-bottom:24px; }}
  .quick-links {{ background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:24px; }}
  .quick-links a {{ color:#3fb950;text-decoration:none;margin-right:16px;display:inline-block;padding:4px 0; }}
  .quick-links a:hover {{ text-decoration:underline; }}
  table {{ background:#0d1117; }}
  tr:hover {{ background:#161b22; }}
</style>
</head><body>
<h1>📊 SwingTrade · Report Archive</h1>
<div class="subtitle">Stored HTML snapshots from scans and autoruns. Auto-pruned to last 200 entries.</div>

<div class="quick-links">
  <strong style="color:#f0f6fc">Quick links:</strong><br>
  <a href="/reports/latest/dashboard">→ Latest Dashboard</a>
  <a href="/reports/latest/morning-briefing">→ Latest Morning Briefing</a>
  <a href="/reports/strategy">→ Strategy Report (Backtest + Regime + MAE/MFE)</a>
  <a href="/kairos.html">→ Live Dashboard (Kairos)</a>
  <a href="/api/system-status">→ Live System Status (JSON)</a>
</div>

{"".join(rows_html)}
</body></html>"""
    return Response(content=page, media_type="text/html", headers={"Cache-Control": "no-store"})


@app.api_route("/reports/latest/{kind}", methods=["GET", "HEAD"])
async def _reports_latest(kind: str, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Serve the most recent snapshot of a given kind."""
    if isinstance(auth, Response):
        return auth
    try:
        import db
        snapshots = db.list_html_snapshots(kind=kind, limit=1)
        if not snapshots:
            raise HTTPException(404, f"No snapshots of kind '{kind}' found")
        latest_id = snapshots[0]["id"]
        content = db.load_html_snapshot(latest_id)
        if not content:
            raise HTTPException(404, f"Snapshot #{latest_id} returned empty content")
        return Response(content=content, media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Snapshot-Id": str(latest_id)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error loading latest {kind}: {e}")


@app.api_route("/reports/strategy", methods=["GET", "HEAD"])
async def _reports_strategy(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Serve the strategy backtest + regime + MAE/MFE HTML report from cache/strategy_report.html."""
    if isinstance(auth, Response):
        return auth
    p = BASE_DIR / "cache" / "strategy_report.html"
    if not p.exists():
        raise HTTPException(404, "strategy_report.html not found — run: python3 scripts/generate_strategy_report.py")
    return Response(content=p.read_text(encoding="utf-8"), media_type="text/html",
                    headers={"Cache-Control": "no-store"})


@app.api_route("/reports/{snapshot_id}", methods=["GET", "HEAD"])
async def _reports_view(snapshot_id: int, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Serve a specific snapshot by id."""
    if isinstance(auth, Response):
        return auth
    try:
        import db
        content = db.load_html_snapshot(snapshot_id)
        if not content:
            raise HTTPException(404, f"Snapshot #{snapshot_id} not found")
        return Response(content=content, media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Snapshot-Id": str(snapshot_id)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error loading snapshot {snapshot_id}: {e}")


@app.get("/api/reports")
async def _api_reports_list(auth: HTTPBasicCredentials = Depends(_check_auth),
                              kind: Optional[str] = None, limit: int = 50):
    """JSON listing of snapshots (metadata only — no html content)."""
    if isinstance(auth, Response):
        return auth
    try:
        import db
        return {"snapshots": db.list_html_snapshots(kind=kind, limit=limit)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/momentum-history")
async def _api_momentum_history(
    request: Request,
    auth: HTTPBasicCredentials = Depends(_check_auth),
):
    """
    Predicted-vs-realized calibration for Momentum-tab picks.

    Reads data/momentum_snapshots.jsonl, computes realized 5d forward returns
    via eodhd_client.eod, compares to SPY baseline, returns {snapshots,
    calibration}. Cached 1hr to keep EODHD pressure minimal.

    Query params:
        ?fresh=1  (or any truthy value) → bypass the 1hr cache and recompute.
                  Response carries `cache_bypassed: true` for visibility.

    Per CLAUDE.md principle 1 (statistical rigor — sample size surfaced),
    11 (edge erosion — calibration tracked over time), 16 (per-sub-strategy
    attribution), 20 (process > outcome — predicted vs realized, not P&L).
    """
    if isinstance(auth, Response):
        return auth
    # Truthy parser — any of 1/true/yes/y/on (case-insensitive) bypasses cache
    fresh_raw = (request.query_params.get("fresh") or "").strip().lower()
    fresh_flag = fresh_raw in {"1", "true", "yes", "y", "on"}
    try:
        from momentum_history_api import build_momentum_history
        result = build_momentum_history(force_refresh=fresh_flag)
        if fresh_flag and isinstance(result, dict):
            # Don't mutate the cached object; return a shallow copy with the flag
            result = dict(result)
            result["cache_bypassed"] = True
        return result
    except Exception as e:
        # Return structured error so the UI can render it gracefully instead of 500
        return {
            "snapshots": [],
            "calibration": None,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)[:200]}",
        }


@app.get("/api/system-status")
async def _api_system_status(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """JSON system-status report (same data as scripts/system_status.py --json)."""
    if isinstance(auth, Response):
        return auth
    try:
        import subprocess, json as _json
        from pathlib import Path as _P
        proc = subprocess.run(
            ["python3", str(BASE_DIR / "scripts" / "system_status.py"), "--json", "--no-slack"],
            capture_output=True, text=True, timeout=30, cwd=str(BASE_DIR),
        )
        if proc.returncode != 0:
            raise HTTPException(500, f"system_status.py failed: {proc.stderr[:200]}")
        return _json.loads(proc.stdout)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# -- /sharpe_screen.html — Sharpe ratio screener (2026-05-13)
# Standalone tool; regenerate via python3 scripts/sharpe_screener.py + scripts/sharpe_screener_html.py
@app.api_route("/sharpe_screen.html", methods=["GET","HEAD"])
async def _sharpe_screen_page(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    p = (BASE_DIR / "cache" / "sharpe_screen.html").resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "sharpe_screen.html not built — run scripts/sharpe_screener_html.py")
    return Response(content=p.read_bytes(), media_type="text/html",
                    headers={"Cache-Control": "no-store"})

# -- /home.html — polished landing distinct from the dense dashboard.
# Hero, today's top conviction, blotter, wire, quick-workspace grid.
@app.api_route("/home.html", methods=["GET","HEAD"])
async def _home_page(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    p = (_PROTOTYPE_DIR / "home.html").resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "home.html not built")
    return Response(content=p.read_bytes(), media_type="text/html",
                    headers={"Cache-Control": "no-store"})

# -- /position_review_mockup.html — Position Analysis 360° review surface.
# Mounted inside the kairos Position Analysis workspace via iframe with
# ?t=TICKER&embed=1 URL params. Reads cells from /api/position/{ticker}.
@app.api_route("/position_review_mockup.html", methods=["GET","HEAD"])
async def _position_review_page(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    p = (_PROTOTYPE_DIR / "position_review_mockup.html").resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "position_review_mockup.html not built")
    return Response(content=p.read_bytes(), media_type="text/html",
                    headers={"Cache-Control": "no-store"})


# -- /position_analysis_v2.html — Project 1 engine-driven Position Analysis.
# Mounted in the kairos Position Analysis workspace via iframe. Reads
# structural targets from /api/trade_engine. Top-level route mirrors
# /position_review_mockup.html so kairos works whether served at /kairos.html
# OR /v2/kairos.html — the iframe's relative ./position_analysis_v2.html
# resolves to the right place either way.
@app.api_route("/position_analysis_v2.html", methods=["GET","HEAD"])
async def _position_analysis_v2_page(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    p = (_PROTOTYPE_DIR / "position_analysis_v2.html").resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "position_analysis_v2.html not built")
    return Response(content=p.read_bytes(), media_type="text/html",
                    headers={"Cache-Control": "no-store"})


# -- Lens-specific tab prototypes · iframe-mounted in kairos detail tabs.
# These serve the same files at top-level paths so iframes work whether
# the parent is at /kairos.html or /v2/kairos.html.
def _make_proto_route(filename):
    """Factory to serve a prototype HTML file under top-level path."""
    @app.api_route("/" + filename, methods=["GET","HEAD"])
    async def _proto(auth: HTTPBasicCredentials = Depends(_check_auth), _fn=filename):
        if isinstance(auth, Response):
            return auth
        p = (_PROTOTYPE_DIR / _fn).resolve()
        if not p.exists() or not p.is_file():
            raise HTTPException(404, f"{_fn} not built")
        return Response(content=p.read_bytes(), media_type="text/html",
                        headers={"Cache-Control": "no-store"})
    _proto.__name__ = f"_proto_{filename.replace('.','_').replace('-','_')}"
    return _proto

for _proto_file in [
    "value_lab_v2_prototype.html",
    "risk_lab_prototype.html",
    "earnings_lab_prototype.html",
    "portfolio_impact_prototype.html",
    "macro_context_prototype.html",
    "news_stream_prototype.html",
    "insider_crowding_prototype.html",
    "overview_v2_prototype.html",
    "smc_v3_prototype.html",
]:
    _make_proto_route(_proto_file)


# ─────────────────────────────────────────────────────────────────────────
# /api/position/{ticker} — real-data endpoint that feeds the Position
# Analysis mockup. Pulls live quote + fundamentals + OHLCV-derived
# technicals; if a cost basis / entry-date is provided as query params it
# also computes P&L, R-multiple, and days-held off live price.
# ─────────────────────────────────────────────────────────────────────────
@app.get("/api/position/{ticker}")
async def position_analysis(
    ticker: str,
    entry: Optional[float] = None,
    shares: Optional[float] = None,
    entry_date: Optional[str] = None,
    stop: Optional[float] = None,
    t1: Optional[float] = None,
    t2: Optional[float] = None,
    auth: HTTPBasicCredentials = Depends(_check_auth),
):
    if isinstance(auth, Response):
        return auth
    import datetime as _dt
    import math as _math
    import pandas as _pd
    import numpy as _np
    tk = (ticker or "").upper().strip()
    if not tk:
        raise HTTPException(400, "ticker required")

    # ── 1. live quote ──────────────────────────────────────────────────
    quote = {}
    try:
        from eodhd_client import real_time as _eod_rt
        q = _eod_rt(tk)
        if isinstance(q, dict):
            quote = q
    except Exception:
        pass

    cur_px = float(quote.get("close") or quote.get("previousClose") or 0) or None
    chg_pct_1d = quote.get("change_p")
    try:
        chg_pct_1d = float(chg_pct_1d) if chg_pct_1d is not None else None
    except Exception:
        chg_pct_1d = None

    # ── 2. fundamentals (sector, mcap, beta) ────────────────────────────
    fund = {}
    try:
        from eodhd_client import fundamentals as _eod_f
        f = _eod_f(tk)
        if isinstance(f, dict):
            fund = f
    except Exception:
        pass

    gen = (fund.get("General") or {}) if isinstance(fund, dict) else {}
    high = (fund.get("Highlights") or {}) if isinstance(fund, dict) else {}
    tech = (fund.get("Technicals") or {}) if isinstance(fund, dict) else {}
    sector = gen.get("Sector") or "—"
    industry = gen.get("Industry") or "—"
    mkt_cap = high.get("MarketCapitalization") or gen.get("MarketCapitalization")
    beta = tech.get("Beta") or high.get("Beta")
    try:
        beta = float(beta) if beta is not None else None
    except Exception:
        beta = None

    # 52w high / low
    w52_high = tech.get("52WeekHigh")
    w52_low = tech.get("52WeekLow")
    try:
        w52_high = float(w52_high) if w52_high is not None else None
        w52_low = float(w52_low) if w52_low is not None else None
    except Exception:
        pass

    # earnings date (next) — read Earnings.History and find the CLOSEST
    # future reportDate. EODHD's Earnings.Trend is FUTURE QUARTER FORECASTS
    # (analyst estimates keyed by quarter-end), not report dates — wrong source.
    # We only return upcoming dates here; past dates get cleared.
    er_date = None
    er_date_last_past = None  # informational only
    try:
        today_d = _dt.date.today()
        hist = (fund.get("Earnings") or {}).get("History") or {}
        if isinstance(hist, dict):
            future_dates = []
            past_dates = []
            for k, row in hist.items():
                rd = (row or {}).get("reportDate")
                if not rd: continue
                try:
                    rd_d = _dt.datetime.strptime(rd, "%Y-%m-%d").date()
                    if rd_d >= today_d:
                        future_dates.append(rd_d)
                    else:
                        past_dates.append(rd_d)
                except Exception:
                    pass
            if future_dates:
                er_date = min(future_dates).strftime("%Y-%m-%d")
            elif past_dates:
                # No upcoming filing on the books yet — surface most-recent
                # past print as a hint (UI shows it as "last report" not "next")
                er_date_last_past = max(past_dates).strftime("%Y-%m-%d")
    except Exception:
        pass

    # insider transactions (top 8 most recent)
    insider_rows = []
    try:
        ins_obj = fund.get("InsiderTransactions") or {}
        rows = list(ins_obj.values()) if isinstance(ins_obj, dict) else (ins_obj if isinstance(ins_obj, list) else [])
        rows = sorted(rows, key=lambda r: (r or {}).get("transactionDate") or "", reverse=True)[:8]
        for r in rows:
            if not isinstance(r, dict): continue
            insider_rows.append({
                "date": r.get("transactionDate") or r.get("date"),
                "name": r.get("ownerName"),
                "code": r.get("transactionCode"),  # S=sale, P=purchase, A=award
                "shares": r.get("transactionAmount"),
                "price": r.get("transactionPrice"),
                "value": (r.get("transactionAmount") or 0) * (r.get("transactionPrice") or 0) if r.get("transactionAmount") and r.get("transactionPrice") else None,
                "post_amount": r.get("postTransactionAmount"),
            })
    except Exception:
        pass

    # ── 3. OHLCV → technicals (ATR, EMAs, RSI, RVOL, realised vol) ─────
    atr14 = ema21 = ema50 = ema200 = rsi14 = rvol = None
    vol_20d = None
    perf_5d = perf_20d = perf_63d = None
    df = None
    try:
        from data_fetcher import fetch_ohlcv_with_failover
        df, _src = fetch_ohlcv_with_failover(tk, days=300)
    except Exception:
        df = None

    if isinstance(df, _pd.DataFrame) and len(df) > 30:
        df = df.sort_index() if df.index.is_monotonic_increasing is False else df
        # close
        c = df["close"] if "close" in df.columns else (df["Close"] if "Close" in df.columns else None)
        h = df["high"] if "high" in df.columns else (df["High"] if "High" in df.columns else None)
        l = df["low"] if "low" in df.columns else (df["Low"] if "Low" in df.columns else None)
        v = df["volume"] if "volume" in df.columns else (df["Volume"] if "Volume" in df.columns else None)
        if c is not None and len(c) > 30:
            # ATR(14)
            try:
                pc = c.shift(1)
                tr = _pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
                atr14 = float(tr.rolling(14).mean().iloc[-1])
            except Exception: pass
            # EMAs
            try: ema21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
            except Exception: pass
            try: ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1])
            except Exception: pass
            try:
                if len(c) >= 200:
                    ema200 = float(c.ewm(span=200, adjust=False).mean().iloc[-1])
            except Exception: pass
            # RSI(14)
            try:
                delta = c.diff()
                up = delta.clip(lower=0).rolling(14).mean()
                dn = (-delta.clip(upper=0)).rolling(14).mean()
                rs = up / dn.replace(0, _np.nan)
                rsi14 = float(100 - 100 / (1 + rs.iloc[-1])) if rs.iloc[-1] == rs.iloc[-1] else None
            except Exception: pass
            # RVOL today
            try:
                if v is not None and len(v) > 20:
                    avg20 = v.rolling(20).mean().iloc[-2]
                    rvol = float(v.iloc[-1] / avg20) if avg20 and avg20 > 0 else None
            except Exception: pass
            # Realised vol (20d, annualised)
            try:
                ret = _np.log(c / c.shift(1))
                vol_20d = float(ret.rolling(20).std().iloc[-1] * _math.sqrt(252) * 100)
            except Exception: pass
            # Trailing perf
            try:
                if len(c) > 5:   perf_5d  = float((c.iloc[-1] / c.iloc[-6]  - 1) * 100)
                if len(c) > 20:  perf_20d = float((c.iloc[-1] / c.iloc[-21] - 1) * 100)
                if len(c) > 63:  perf_63d = float((c.iloc[-1] / c.iloc[-64] - 1) * 100)
            except Exception: pass
            # fallback current price if quote was empty
            if cur_px is None:
                try: cur_px = float(c.iloc[-1])
                except Exception: pass

    # ── 4. existing scan signal (cache/last_bundle.json) ────────────────
    # Bundle uses `all_scored` for every ticker scanned (398 entries today),
    # not `signals`. Also pulls bundle-level regime as fallback.
    scan = {}
    bundle_regime = "—"
    avg_volume_bundle = None
    try:
        from pathlib import Path
        import json as _json
        bp = Path("cache/last_bundle.json")
        if bp.exists():
            bundle = _json.loads(bp.read_text())
            # bundle-level regime
            reg_obj = bundle.get("regime") or {}
            bundle_regime = (reg_obj.get("regime4") or reg_obj.get("regime") or "—")
            for sig in (bundle.get("all_scored") or []):
                if (sig.get("ticker") or "").upper() == tk:
                    scan = sig
                    break
    except Exception:
        pass

    score = scan.get("score") or scan.get("bap") or scan.get("composite_score")
    setup_family = scan.get("setup_family") or scan.get("setup") or "—"
    verdict = scan.get("verdict") or scan.get("decision") or "WATCH"
    # per-ticker regime is often None in the bundle; use bundle's regime4
    regime = scan.get("regime4") or scan.get("regime") or bundle_regime or "—"
    catalyst_tier = scan.get("catalyst_tier") or scan.get("cat_tier") or "—"
    rs_rank = scan.get("rs_rank") or scan.get("rs")
    scan_rvol = scan.get("rvol")
    scan_beta = scan.get("beta")
    scan_avg_vol = scan.get("avg_volume")

    # Technical proxy score for tickers NOT in scan — computed UP HERE so
    # everything downstream (opp_cost ranking, verdict derivation) sees a
    # consistent value. Was previously computed too late, causing opp_cost
    # to filter against my_score=0 and overcount alternatives.
    if score is None and cur_px and ema21 and ema50:
        proxy = 50
        if cur_px > ema21: proxy += 10
        if cur_px > ema50: proxy += 10
        if ema200 and cur_px > ema200: proxy += 5
        if rsi14 and 40 <= rsi14 <= 70: proxy += 5
        if rsi14 and rsi14 > 75: proxy -= 10
        if perf_20d and perf_20d > 5: proxy += 5
        score = max(0, min(100, proxy))

    # ── 5. derived (entry-aware) ────────────────────────────────────────
    days_held = None
    if entry_date:
        try:
            ed = _dt.datetime.strptime(entry_date, "%Y-%m-%d").date()
            days_held = (_dt.date.today() - ed).days
        except Exception: pass

    unrealized = unrealized_pct = r_mult = None
    pct_to_t1 = pct_to_stop = None
    pos_mv = beta_adj_mv = None
    derived_stop = stop
    derived_t1 = t1
    derived_t2 = t2
    if cur_px is not None and entry is not None:
        if shares is not None:
            unrealized = round((cur_px - entry) * shares, 2)
            pos_mv = round(cur_px * shares, 2)
            if beta is not None:
                beta_adj_mv = round(pos_mv * beta, 2)
        unrealized_pct = round((cur_px / entry - 1) * 100, 2)
        # auto-derive stop/T1/T2 from ATR if not provided
        if derived_stop is None and atr14 is not None:
            derived_stop = round(entry - 1.25 * atr14, 2)
        if derived_t1 is None and atr14 is not None:
            derived_t1 = round(entry + 2.0 * atr14, 2)
        if derived_t2 is None and atr14 is not None:
            derived_t2 = round(entry + 4.0 * atr14, 2)
        if derived_stop is not None and entry > derived_stop:
            risk_per_share = entry - derived_stop
            if risk_per_share > 0:
                r_mult = round((cur_px - entry) / risk_per_share, 2)
        if derived_t1 is not None and derived_t1 > entry:
            travelled = cur_px - entry
            distance = derived_t1 - entry
            pct_to_t1 = round((travelled / distance) * 100, 1) if distance > 0 else None
        if derived_stop is not None:
            pct_to_stop = round((cur_px / derived_stop - 1) * 100, 2)

    # 52w-position percentile
    pos_in_52w = None
    if cur_px is not None and w52_high is not None and w52_low is not None and w52_high > w52_low:
        pos_in_52w = round((cur_px - w52_low) / (w52_high - w52_low) * 100, 1)

    # ── Edge audit · Wilson LB on the sliced slice ──────────────────────
    # Principle 1 (CLAUDE.md): statistical rigor over backtest theatre.
    # Compute the historical edge for THIS exact setup × regime × score-
    # band × catalyst-tier intersection, not the aggregate WR. Wilson 95%
    # lower bound is the conservative read of true win-rate.
    edge_audit = {}
    try:
        from pathlib import Path as _P3
        import json as _j3
        ph_path = _P3("cache/picks_history.json")
        if ph_path.exists():
            ph = _j3.loads(ph_path.read_text())
            trades = ph.get("trades") or []

            # Determine the slice for this ticker
            # setup_family: from scan if available, else infer from EMA stack
            sf = (scan.get("setup_family") if scan else None) or setup_family
            if not sf or sf == "—":
                # Infer from technicals
                if cur_px and ema21 and ema50 and cur_px > ema21 > ema50:
                    sf = "Trend Continuation"   # rising stack, mid-trend
                elif cur_px and ema21 and cur_px > ema21 * 1.05:
                    sf = "Breakout Expansion"   # extended above 21EMA
                elif rsi14 and rsi14 < 40:
                    sf = "Impulse Catalyst"     # oversold reversal candidate
                else:
                    sf = None
            # score band
            sb = score if score is not None else 0
            if sb >= 90: band = "90+"
            elif sb >= 80: band = "80-90"
            elif sb >= 70: band = "70-80"
            elif sb >= 60: band = "60-70"
            else: band = "<60"
            band_low, band_high = {
                "90+": (90, 1000), "80-90": (80, 90), "70-80": (70, 80),
                "60-70": (60, 70), "<60": (0, 60),
            }[band]

            ct = catalyst_tier if catalyst_tier not in (None, "—") else None
            rg = regime if regime not in (None, "—") else None

            # Build the FULL slice (all four dims). Fall back to broader
            # slices if the tight one has n < 20 (not enough evidence).
            def _slice(trades, sf_match=None, rg_match=None, ct_match=None, band=None):
                out = []
                for t in trades:
                    if sf_match and (t.get("setup_family") or "") != sf_match: continue
                    if rg_match and (t.get("regime4") or "") != rg_match: continue
                    if ct_match is not None:
                        try: tct = int(t.get("catalyst_tier") or 0)
                        except: tct = 0
                        if tct != int(ct_match): continue
                    if band is not None:
                        sc = t.get("score") or 0
                        if sc < band[0] or sc >= band[1]: continue
                    if t.get("win") is None: continue   # need closed trade
                    out.append(t)
                return out

            # Try slices in priority order: most specific → most general.
            slice_levels = [
                ("setup × regime × catalyst × band",      lambda: _slice(trades, sf, rg, ct, (band_low, band_high))),
                ("setup × regime × catalyst",             lambda: _slice(trades, sf, rg, ct, None)),
                ("setup × regime",                        lambda: _slice(trades, sf, rg, None, None)),
                ("setup × catalyst × band",               lambda: _slice(trades, sf, None, ct, (band_low, band_high))),
                ("setup",                                 lambda: _slice(trades, sf, None, None, None)),
                ("aggregate",                             lambda: _slice(trades, None, None, None, None)),
            ]
            chosen = None
            chosen_label = None
            for label, fn in slice_levels:
                bucket = fn()
                if len(bucket) >= 20:
                    chosen = bucket
                    chosen_label = label
                    break
            if chosen is None and trades:
                chosen = _slice(trades, None, None, None, None)
                chosen_label = "aggregate (no slice met n≥20)"

            if chosen:
                n_tot = len(chosen)
                wins = sum(1 for t in chosen if t.get("win") is True)
                losses = n_tot - wins
                wr = wins / n_tot if n_tot else 0.0
                # Wilson 95% CI
                z = 1.96
                if n_tot > 0:
                    centre = (wr + z*z/(2*n_tot)) / (1 + z*z/n_tot)
                    margin = (z * _math.sqrt((wr*(1-wr)/n_tot) + (z*z/(4*n_tot*n_tot)))) / (1 + z*z/n_tot)
                    wilson_lb = max(0.0, centre - margin)
                    wilson_ub = min(1.0, centre + margin)
                else:
                    wilson_lb = wilson_ub = 0.0
                # PnL stats
                win_returns = [t.get("pct_chg") or 0 for t in chosen if t.get("win") is True]
                loss_returns = [t.get("pct_chg") or 0 for t in chosen if t.get("win") is False]
                avg_win_pct  = sum(win_returns) / len(win_returns)   if win_returns else 0.0
                avg_loss_pct = sum(loss_returns) / len(loss_returns) if loss_returns else 0.0
                pf = (sum(win_returns) / abs(sum(loss_returns))) if loss_returns and sum(loss_returns) < 0 else None
                # Expectancy in pct terms
                expectancy_pct = wr * avg_win_pct + (1 - wr) * avg_loss_pct
                # MFE / MAE distribution
                mfes = [t.get("mfe") or 0 for t in chosen if t.get("mfe") is not None]
                maes = [t.get("mae") or 0 for t in chosen if t.get("mae") is not None]
                def _pctl(arr, q):
                    if not arr: return None
                    a = sorted(arr)
                    k = (len(a) - 1) * q / 100
                    f = int(k); c = min(f + 1, len(a) - 1)
                    return round(a[f] + (a[c] - a[f]) * (k - f), 2)
                edge_audit = {
                    "slice_label":     chosen_label,
                    "slice_setup_family": sf,
                    "slice_regime":    rg,
                    "slice_catalyst_tier": ct,
                    "slice_score_band": band,
                    "n":               n_tot,
                    "wins":            wins,
                    "losses":          losses,
                    "win_rate":        round(wr, 4),
                    "wilson_lb_95":    round(wilson_lb, 4),
                    "wilson_ub_95":    round(wilson_ub, 4),
                    "profit_factor":   round(pf, 2) if pf else None,
                    "avg_win_pct":     round(avg_win_pct, 2),
                    "avg_loss_pct":    round(avg_loss_pct, 2),
                    "expectancy_pct":  round(expectancy_pct, 2),
                    "passes_wilson_55": wilson_lb >= 0.55,
                    "passes_wilson_50": wilson_lb >= 0.50,
                    "passes_n_30":     n_tot >= 30,
                    "passes_pf_15":    pf is not None and pf >= 1.5,
                    "mfe_p25":         _pctl(mfes, 25),
                    "mfe_p50":         _pctl(mfes, 50),
                    "mfe_p75":         _pctl(mfes, 75),
                    "mae_p25":         _pctl(maes, 25),
                    "mae_p50":         _pctl(maes, 50),
                    "mae_p75":         _pctl(maes, 75),
                }
            else:
                edge_audit = {"slice_label": "no closed trades in history", "n": 0}
    except Exception as _e:
        edge_audit = {"error": str(_e)}

    # ── Opportunity cost ────────────────────────────────────────────────
    # Real comparison vs everything in today's scan. Answers: "where does
    # this candidate rank?", "what's available that scores higher?",
    # "what's the best alternative in the same sector?", and the
    # diversification cut: "what's the best alternative in a DIFFERENT
    # sector?" (matters for principle 10 — correlation under stress).
    opp_cost = {}
    try:
        from pathlib import Path as _P
        import json as _j
        bp = _P("cache/last_bundle.json")
        if bp.exists():
            bundle = _j.loads(bp.read_text())
            scored = bundle.get("all_scored") or []
            scored_sorted = sorted(scored, key=lambda x: (x.get("score") or 0), reverse=True)
            total = len(scored_sorted)
            my_rank = None
            my_score = score if score is not None else 0
            for i, x in enumerate(scored_sorted):
                if (x.get("ticker") or "").upper() == tk:
                    my_rank = i + 1
                    break
            my_sector = sector if sector and sector != "—" else (scan.get("sector") if scan else None)
            def _slim(x):
                return {
                    "ticker": x.get("ticker"),
                    "name": x.get("name"),
                    "score": x.get("score"),
                    "verdict": x.get("verdict"),
                    "setup_family": x.get("setup_family") or "—",
                    "sector": x.get("sector") or "—",
                    "industry": x.get("industry") or "—",
                    "rs_rank": x.get("rs_rank"),
                    "catalyst_tier": x.get("catalyst_tier"),
                    "conviction": x.get("conviction"),
                    "price": x.get("price"),
                }
            top_higher = [
                _slim(x) for x in scored_sorted
                if (x.get("score") or 0) > my_score
                and (x.get("ticker") or "").upper() != tk
            ][:5]
            same_sector = [
                _slim(x) for x in scored_sorted
                if (x.get("sector") or "") == my_sector
                and (x.get("ticker") or "").upper() != tk
            ][:5]
            diff_sector_alt = [
                _slim(x) for x in scored_sorted
                if (x.get("sector") or "") and (x.get("sector") or "") != my_sector
                and (x.get("score") or 0) >= max(70, my_score)
            ][:5]
            scores_list = [(x.get("score") or 0) for x in scored_sorted]
            median_score = scores_list[total // 2] if total else None
            opp_cost = {
                "in_scan": bool(scan),
                "my_rank": my_rank,
                "total_scanned": total,
                "my_percentile": round((my_rank / total) * 100, 1) if my_rank and total else None,
                "my_score": my_score,
                "my_sector": my_sector,
                "top_score": scored_sorted[0].get("score") if scored_sorted else None,
                "top_ticker": scored_sorted[0].get("ticker") if scored_sorted else None,
                "median_score": median_score,
                "n_higher": len(top_higher),
                "top_higher": top_higher,
                "same_sector_top": same_sector,
                "diff_sector_alt": diff_sector_alt,
            }
    except Exception as _e:
        opp_cost = {"error": str(_e)}

    # ── Portfolio cross-reference for sector/factor concentration risk ─
    # If user is already holding tickers in this same sector, adding more
    # exposure breaches the "correlation under stress" principle (#10).
    # Canonical source is data/portfolio_state.json (live Alpaca sync).
    # Sectors aren't stored on positions; enrich via all_scored lookup.
    portfolio_xref = {}
    try:
        from pathlib import Path as _P2
        import json as _j2
        pp = _P2("data/portfolio_state.json")
        if not pp.exists():
            pp = _P2("cache/portfolio.json")
        if pp.exists():
            pdata = _j2.loads(pp.read_text())
            open_pos = (pdata or {}).get("open_positions") or pdata.get("positions") or []
            held_tickers = [(p.get("ticker") or "").upper() for p in open_pos]
            # Build sector lookup once from the scan
            sector_by_tk = {}
            try:
                bp2 = _P2("cache/last_bundle.json")
                if bp2.exists():
                    b2 = _j2.loads(bp2.read_text())
                    for x in (b2.get("all_scored") or []):
                        t2 = (x.get("ticker") or "").upper()
                        if t2: sector_by_tk[t2] = x.get("sector")
            except Exception: pass

            same_sector_held = []
            total_invested = 0.0
            held_with_sector = []
            for p in open_pos:
                pos_size = (p.get("position_size") or (p.get("entry") or p.get("entry_price") or 0) * (p.get("shares") or 0)) or 0
                total_invested += pos_size
                held_tk = (p.get("ticker") or "").upper()
                held_sector = p.get("sector") or sector_by_tk.get(held_tk) or "—"
                held_with_sector.append({
                    "ticker": held_tk,
                    "sector": held_sector,
                    "size": round(pos_size, 2),
                })
                if held_sector and my_sector and held_sector == my_sector:
                    same_sector_held.append({
                        "ticker": held_tk,
                        "sector": held_sector,
                        "entry": p.get("entry") or p.get("entry_price"),
                        "shares": p.get("shares"),
                        "size": round(pos_size, 2),
                    })
            portfolio_xref = {
                "already_held": tk in held_tickers,
                "held_count": len(open_pos),
                "held_tickers": held_tickers,
                "held_with_sector": held_with_sector,
                "same_sector_held": same_sector_held,
                "same_sector_count": len(same_sector_held),
                "total_invested": round(total_invested, 2),
            }
    except Exception as _e:
        portfolio_xref = {"error": str(_e)}

    # ── Forward outcome distribution (Monte Carlo, GBM) ─────────────────
    # Real probabilities from a 10K-path geometric Brownian motion sim
    # parameterised by THIS ticker's realised vol + 60d drift, NOT the
    # hardcoded NVDA placeholders that were here previously.
    fwd_outcome = {}

    # ── Hypothetical trade plan ─────────────────────────────────────────
    # If the user didn't provide a cost basis we still want to surface a
    # "what would this trade look like NOW" suggestion: ATR-based stop/T1/T2,
    # R:R ratio, and a suggested share count under $5K paper sizing rules.
    # Surfaced even when a real position EXISTS (for comparison vs. live cost
    # basis).
    trade_plan = {}
    if cur_px is not None and atr14 is not None and atr14 > 0:
        hyp_entry = cur_px
        hyp_stop  = round(hyp_entry - 1.25 * atr14, 2)
        hyp_t1    = round(hyp_entry + 2.0 * atr14, 2)
        hyp_t2    = round(hyp_entry + 4.0 * atr14, 2)
        risk_ps   = round(hyp_entry - hyp_stop, 2)
        reward_t1 = round(hyp_t1 - hyp_entry, 2)
        reward_t2 = round(hyp_t2 - hyp_entry, 2)
        rr_t1     = round(reward_t1 / risk_ps, 2) if risk_ps > 0 else None
        rr_t2     = round(reward_t2 / risk_ps, 2) if risk_ps > 0 else None
        # Sizing for a $5K paper account with the system's defaults:
        # max_loss_pct = 0.75% per trade, regime-haircut applied externally.
        default_acct = 5000.0
        default_risk_pct = 0.0075
        max_risk_dollars = round(default_acct * default_risk_pct, 2)
        sugg_shares_5k = int(max_risk_dollars / risk_ps) if risk_ps > 0 else 0
        sugg_size_5k = round(sugg_shares_5k * hyp_entry, 2)
        # Also at $50K / $250K scales (10% per position cap)
        size_50k  = round(min(0.10 * 50000.0,  (max_risk_dollars * 10) * hyp_entry / max(risk_ps, 1e-6)), 0) if risk_ps > 0 else 0
        size_250k = round(min(0.10 * 250000.0, (max_risk_dollars * 50) * hyp_entry / max(risk_ps, 1e-6)), 0) if risk_ps > 0 else 0
        # Verdict-aware sizing haircut by regime
        regime_haircut = {
            "risk_on_trending": 1.0,
            "risk_on_choppy":   0.70,
            "risk_off_trending":0.35,
            "panic":            0.0,
        }.get(regime, 0.70)
        sugg_shares_adj = int(sugg_shares_5k * regime_haircut)
        trade_plan = {
            "hypothetical_entry": hyp_entry,
            "stop":               hyp_stop,
            "t1":                 hyp_t1,
            "t2":                 hyp_t2,
            "risk_per_share":     risk_ps,
            "reward_to_T1":       reward_t1,
            "reward_to_T2":       reward_t2,
            "rr_T1":              rr_t1,
            "rr_T2":              rr_t2,
            "atr_used":           round(atr14, 2),
            "max_risk_dollars_5k":     max_risk_dollars,
            "suggested_shares_5k":     sugg_shares_5k,
            "suggested_shares_5k_regime_adj": sugg_shares_adj,
            "suggested_size_5k":       sugg_size_5k,
            "approx_size_50k":         size_50k,
            "approx_size_250k":        size_250k,
            "regime_haircut":          regime_haircut,
            "rr_passes_3to1":          rr_t1 is not None and rr_t1 >= 3.0,
        }

        # ─── Monte Carlo: 10K GBM paths over remaining hold window ───
        # σ = realised vol (annualised), μ = annualised 20d drift.
        # Risk-neutral if drift unavailable. Targets and stop come from
        # trade_plan above. This is REAL probability math — no placeholders.
        if vol_20d is not None and vol_20d > 0:
            try:
                sigma_ann = float(vol_20d) / 100.0   # vol_20d is %
                # Drift from 20d trailing return → annualise
                if perf_20d is not None:
                    mu_ann = (float(perf_20d) / 20.0) * 252.0 / 100.0
                else:
                    mu_ann = 0.0
                # Cap drift at ±60% annualised (sanity)
                mu_ann = max(-0.6, min(0.6, mu_ann))

                T_days = 15
                n_paths = 10000
                dt = 1.0 / 252.0
                sigma_d = sigma_ann * _math.sqrt(dt)
                drift_d = (mu_ann - 0.5 * sigma_ann**2) * dt

                rng = _np.random.default_rng(seed=hash(tk) & 0xFFFFFFFF)
                Z = rng.standard_normal((n_paths, T_days))
                log_returns = drift_d + sigma_d * Z
                log_prices = _np.cumsum(log_returns, axis=1)
                prices = cur_px * _np.exp(log_prices)  # (n_paths, T_days)

                INF = T_days + 1
                stop_first = _np.where((prices <= hyp_stop).any(axis=1),
                                       (prices <= hyp_stop).argmax(axis=1), INF)
                t1_first   = _np.where((prices >= hyp_t1).any(axis=1),
                                       (prices >= hyp_t1).argmax(axis=1), INF)
                t2_first   = _np.where((prices >= hyp_t2).any(axis=1),
                                       (prices >= hyp_t2).argmax(axis=1), INF)

                is_stop_first = (stop_first < t1_first) & (stop_first < t2_first) & (stop_first < INF)
                # T1 / T2 only count if stop wasn't hit first
                t1_alive = (t1_first < INF) & ~is_stop_first
                t2_alive = (t2_first < INF) & ~is_stop_first

                p_stop    = float(is_stop_first.sum()) / n_paths
                p_t1      = float(t1_alive.sum())     / n_paths   # incl. paths that go on to T2
                p_t2      = float(t2_alive.sum())     / n_paths
                p_timeout = 1.0 - p_t1 - p_stop

                # E[R]
                R = _np.zeros(n_paths)
                R[is_stop_first] = -1.0
                R[t2_alive]      = (hyp_t2 - cur_px) / risk_ps
                t1_only = t1_alive & ~t2_alive
                R[t1_only]       = (hyp_t1 - cur_px) / risk_ps
                timeout_mask = ~is_stop_first & ~t1_alive
                if timeout_mask.any():
                    R[timeout_mask] = (prices[timeout_mask, -1] - cur_px) / risk_ps

                expected_r = float(R.mean())
                expected_dollar_per_share = expected_r * risk_ps
                # Forward Sharpe (15d) ≈ E[R] / std(R) annualised
                sharpe_15d = float(R.mean() / R.std()) if R.std() > 0 else None
                fwd_sharpe_ann = sharpe_15d * _math.sqrt(252 / T_days) if sharpe_15d else None

                # Path percentiles for the fan chart (D5, D10, D15)
                pct = lambda d, q: float(_np.percentile(prices[:, d], q))
                fan = []
                for d in (4, 9, 14):  # 0-indexed day 5, 10, 15
                    fan.append({
                        "day": d + 1,
                        "p10": pct(d, 10), "p25": pct(d, 25),
                        "p50": pct(d, 50),
                        "p75": pct(d, 75), "p90": pct(d, 90),
                    })

                fwd_outcome = {
                    "horizon_days": T_days,
                    "n_paths":      n_paths,
                    "sigma_annualised":  round(sigma_ann, 4),
                    "drift_annualised":  round(mu_ann, 4),
                    "p_t1":              round(p_t1, 4),
                    "p_t2":              round(p_t2, 4),
                    "p_stop":            round(p_stop, 4),
                    "p_timeout":         round(p_timeout, 4),
                    "expected_r":        round(expected_r, 3),
                    "expected_dollar_per_share": round(expected_dollar_per_share, 2),
                    "fwd_sharpe_ann":    round(fwd_sharpe_ann, 2) if fwd_sharpe_ann else None,
                    "fan":               fan,
                    "stop_price":        hyp_stop,
                    "t1_price":          hyp_t1,
                    "t2_price":          hyp_t2,
                    "current_price":     cur_px,
                }
            except Exception as _e:
                fwd_outcome = {"error": str(_e)}

    # Days to earnings
    days_to_er = None
    if er_date:
        try:
            ed = _dt.datetime.strptime(er_date[:10], "%Y-%m-%d").date()
            d = (ed - _dt.date.today()).days
            days_to_er = d if d >= 0 else None
        except Exception: pass

    # Simple verdict + conviction (real heuristic when no scan match)
    if not verdict or verdict == "WATCH":
        if score is not None:
            if score >= 80: verdict = "ADD"
            elif score >= 60: verdict = "HOLD"
            elif score >= 45: verdict = "TRIM"
            else: verdict = "EXIT"

    # ── Decision Verdict · synthesises every live signal into TAKE/SKIP/WAIT ──
    # Pure quant decision-tree logic. Each branch is principle-cited and the
    # narrative bullets surface the evidence so the user sees WHY, not just
    # WHAT. CLAUDE.md principle 20: process > outcome.
    decision = {}
    try:
        my_rank_d = opp_cost.get("my_rank")
        total_scanned_d = opp_cost.get("total_scanned") or 0
        n_higher_d = opp_cost.get("n_higher") or 0
        in_scan_d = bool(scan)
        my_score_eff = score if score is not None else 0
        rr_t1 = (trade_plan or {}).get("rr_T1") or 0
        sector_held_count = len((portfolio_xref or {}).get("same_sector_held") or [])
        already_held = (portfolio_xref or {}).get("already_held", False)
        wlb = (edge_audit or {}).get("wilson_lb_95") or 0
        n_edge = (edge_audit or {}).get("n") or 0
        edge_passes = wlb >= 0.55 and n_edge >= 20
        days_er = days_to_er
        mc_er = (fwd_outcome or {}).get("expected_r") or 0
        mc_pstop = (fwd_outcome or {}).get("p_stop") or 0
        percentile_d = opp_cost.get("my_percentile")

        action = "WAIT"
        conviction = "low"
        reasons = []
        warnings = []

        if already_held:
            action = "HOLD"; conviction = "medium"
            reasons.append("Already in portfolio — this is an ADD/TRIM/HOLD decision, not entry")
        elif days_er is not None and days_er <= 3:
            action = "WAIT"; conviction = "low"
            reasons.append(f"Earnings binary risk — only {days_er}d to ER. Wait through print.")
        elif rsi14 and rsi14 > 75:
            action = "WAIT"; conviction = "low"
            reasons.append(f"RSI {rsi14:.0f} extension — wait for pullback to 21EMA")
        elif n_higher_d >= 5 and my_score_eff < 75:
            action = "SKIP"; conviction = "medium"
            reasons.append(f"{n_higher_d} scan picks score higher than this candidate ({my_score_eff:.0f})")
        elif wlb > 0 and wlb < 0.50 and n_edge >= 20:
            action = "SKIP"; conviction = "medium"
            reasons.append(f"Historical edge insufficient — Wilson LB {wlb*100:.0f}% on {n_edge} similar trades")
        elif rr_t1 > 0 and rr_t1 < 3.0:
            action = "WAIT"; conviction = "low"
            reasons.append(f"R:R T1 = {rr_t1} fails 3:1 minimum (principle 3) — wait for better entry")
        elif in_scan_d and percentile_d and percentile_d <= 10 and edge_passes:
            action = "TAKE"; conviction = "high"
            reasons.append(f"Top {percentile_d}% in scan ({my_score_eff:.0f}) + edge slice clears Wilson 55% (LB {wlb*100:.0f}% on n={n_edge})")
        elif in_scan_d and percentile_d and percentile_d <= 25 and wlb >= 0.50:
            action = "TAKE"; conviction = "medium"
            reasons.append(f"Top {percentile_d}% in scan + acceptable edge slice (Wilson LB {wlb*100:.0f}%)")
        else:
            action = "WAIT"; conviction = "low"
            reasons.append("No strong signal — wait for better setup or higher-conviction candidate")

        if mc_er > 0.5 and len(reasons) < 3 and fwd_outcome:
            reasons.append(f"Monte Carlo E[R] = +{mc_er:.2f}R · σ {(fwd_outcome.get('sigma_annualised') or 0)*100:.0f}% · drift {(fwd_outcome.get('drift_annualised') or 0)*100:+.0f}%")
        if days_er and days_er > 7 and days_er <= 30 and len(reasons) < 3:
            reasons.append(f"Catalyst window open — earnings in {days_er}d")
        if scan.get("catalyst_tier") == 1 and len(reasons) < 3:
            reasons.append("T1 catalyst — system's top-priority signal type")
        if my_rank_d and total_scanned_d and my_rank_d <= 10 and len(reasons) < 3:
            reasons.append(f"Rank {my_rank_d} of {total_scanned_d} — top of scan today")

        if sector_held_count >= 2:
            warnings.append(f"Sector concentration: {sector_held_count} positions in {my_sector or 'this sector'} — violates principle 10")
        if rr_t1 > 0 and rr_t1 < 3.0:
            warnings.append(f"R:R T1 = {rr_t1} below 3:1 floor — tighten stop or skip")
        if mc_pstop > 0.45:
            warnings.append(f"P(stop) = {mc_pstop*100:.0f}% — MC says nearly half of paths hit stop")
        if not in_scan_d:
            warnings.append("NOT in today's scan — score is technical proxy, not vetted 5-pillar")
        if wlb > 0 and n_edge < 30:
            warnings.append(f"Edge slice n={n_edge} below n≥30 floor (principle 1) — treat as suggestive")

        if action == "TAKE":
            shrs = (trade_plan or {}).get("suggested_shares_5k_regime_adj") or 0
            specific = f"Buy {shrs} shrs @ market (~${(trade_plan or {}).get('hypothetical_entry')}) · stop ${(trade_plan or {}).get('stop')} · T1 ${(trade_plan or {}).get('t1')} · trim 30% at T1"
        elif action == "SKIP":
            higher = opp_cost.get('top_higher') or []
            if higher:
                top_alt = higher[0] or {}
                specific = f"Skip this. Higher-conviction alt today: {top_alt.get('ticker','—')} (score {top_alt.get('score','—')}, {top_alt.get('setup_family','—')})"
            else:
                specific = "Skip this. No higher-conviction alts either — sit in cash today; principle 8 (mechanical execution) says no trade is a trade."
        elif action == "WAIT":
            specific = f"Set alert for 21EMA tag at ${ema21:.2f}" if ema21 else "Wait for better entry quality"
        elif action == "HOLD":
            specific = "Maintain current position. Re-review on exit-trigger fire."
        else:
            specific = "—"

        decision = {
            "action": action,
            "conviction": conviction,
            "reasons": reasons[:3],
            "warnings": warnings[:4],
            "specific_action": specific,
        }
    except Exception as _e:
        decision = {"error": str(_e), "action": "UNKNOWN"}

    out = {
        "ticker": tk,
        "as_of": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_quality": {
            "has_quote": bool(quote),
            "has_fundamentals": bool(fund),
            "has_ohlcv": isinstance(df, _pd.DataFrame),
            "has_scan": bool(scan),
        },
        "quote": {
            "current_price": cur_px,
            "change_pct_1d": chg_pct_1d,
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "previous_close": quote.get("previousClose"),
            "volume": quote.get("volume"),
        },
        "company": {
            "name": gen.get("Name") or tk,
            "sector": sector,
            "industry": industry,
            "market_cap": mkt_cap,
            "beta": beta,
            "shares_outstanding": gen.get("SharesOutstanding"),
        },
        "technicals": {
            "atr_14d": atr14,
            "ema_21": ema21,
            "ema_50": ema50,
            "ema_200": ema200,
            "rsi_14": rsi14,
            "rvol_today": rvol,
            "realised_vol_20d_ann": vol_20d,
            "perf_5d": perf_5d,
            "perf_20d": perf_20d,
            "perf_63d": perf_63d,
            "week52_high": w52_high,
            "week52_low": w52_low,
            "pct_of_52w_range": pos_in_52w,
        },
        "scan": {
            "in_scan": bool(scan),
            "score": score,
            "verdict": verdict,
            "setup_family": setup_family,
            "regime": regime,
            "catalyst_tier": catalyst_tier,
            "rs_rank": rs_rank,
            "rvol": scan_rvol,
            "avg_volume": scan_avg_vol,
        },
        "earnings": {
            "next_date": er_date,
            "days_to_er": days_to_er,
            "last_report_date": er_date_last_past,
        },
        "trade_plan": trade_plan,
        "forward_outcome": fwd_outcome,
        "opportunity_cost": opp_cost,
        "portfolio_xref": portfolio_xref,
        "edge_audit": edge_audit,
        "decision": decision,
        "insiders": insider_rows,
        "position": {
            "entry": entry,
            "shares": shares,
            "entry_date": entry_date,
            "days_held": days_held,
            "stop": derived_stop,
            "t1": derived_t1,
            "t2": derived_t2,
            "stop_source": "user" if stop is not None else ("derived_atr_1_25x" if derived_stop else None),
            "target_source": "user" if t1 is not None else ("derived_atr_2x_4x" if derived_t1 else None),
            "unrealized_pnl": unrealized,
            "unrealized_pct": unrealized_pct,
            "r_multiple": r_mult,
            "pct_to_t1": pct_to_t1,
            "pct_to_stop": pct_to_stop,
            "position_mv": pos_mv,
            "beta_adjusted_mv": beta_adj_mv,
        },
    }
    return out

@app.api_route("/home", methods=["GET","HEAD"])
async def _home_redirect(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    return RedirectResponse(url="/home.html", status_code=302)

# -- /api/me — surface current user's role + tab_profile to the client.
# Lets V2 dashboard + elite-detail apply the right tab visibility profile
# automatically based on the server-side user record, instead of falling back
# to the localStorage default ('trader') which hides quant-only tabs like Models.
@app.get("/api/logout")
async def logout(request: Request):
    """Force the browser to drop cached HTTP Basic Auth credentials.

    2026-05-22 · top-level navigation target for the SIGN OUT button.
    Returns 200 + Clear-Site-Data + an HTML body that auto-redirects to /
    after 1.5s. Top-level (document) response is required for browsers to
    honor Clear-Site-Data for Basic Auth credentials — fetch/XHR responses
    are not honored reliably across Chrome/Safari/Firefox. After the
    cached creds are cleared, the redirect to / triggers the browser's
    re-auth prompt automatically. Always-public — no auth gate (you can't
    log out if you're already locked out).
    """
    html_body = """<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <title>Signed out — SwingTrade</title>
  <meta http-equiv="refresh" content="1.5; url=/?_signedout=1">
  <style>
    body{background:#0a0d0c;color:#d1d5db;font-family:system-ui,-apple-system,sans-serif;
         display:grid;place-items:center;height:100vh;margin:0}
    .box{text-align:center;padding:2rem 2.5rem;border:1px solid #1f2937;border-radius:12px;
         background:#111418;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.4)}
    h1{margin:0 0 0.75rem 0;font-size:1.25rem;color:#10b981;font-weight:600}
    p{margin:0.5rem 0;color:#9ca3af;font-size:0.9rem;line-height:1.5}
    a{color:#3b82f6;text-decoration:none;font-weight:500}
    a:hover{text-decoration:underline}
  </style>
</head><body>
  <div class="box">
    <h1>✓ Signed out</h1>
    <p>Your session has ended. Redirecting in 1.5s…</p>
    <p><a href="/?_signedout=1">Sign back in →</a></p>
  </div>
</body></html>"""
    return Response(
        status_code=200,
        content=html_body,
        media_type="text/html; charset=utf-8",
        headers={
            "Clear-Site-Data": '"cookies", "storage", "cache"',
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/me")
async def whoami(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    username = auth.username
    user = _auth_mod.get_user(username) or {}
    perms = _auth_mod.get_user_permissions(username) or {}
    return JSONResponse({
        "username":       username,
        "display_name":   user.get("display_name") or username,
        "role":           user.get("role") or "viewer",
        "is_admin":       _auth_mod.is_admin(username),
        "is_owner":       bool(user.get("is_owner")),
        "tab_profile":    user.get("tab_profile") or "trader",
        "tabs_allowed":   (perms.get("tabs") or []),
        "sub_tabs_allowed":(perms.get("sub_tabs") or []),
        "actions_allowed": (perms.get("actions") or []),
        "must_change_password": bool(user.get("must_change_password")),
    })


# -- CapStudio: Capability Registry --
# Serves the master function registry (data/capability_registry.json).
# Read-only for everyone; the matrix UI in settings_capstudio.html consumes
# this to render the role × function checkbox grid. Edits to role assignments
# go through POST /api/roles/{role_id}, NOT this endpoint.
# (2026-05-09 — CapStudio Phase A.)
@app.get("/api/capability-registry")
async def capability_registry(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    p = BASE_DIR / "data" / "capability_registry.json"
    if not p.exists():
        return JSONResponse({"error": "capability_registry.json missing", "tabs": {}, "sub_tabs": {}, "actions": {}}, status_code=404)
    return JSONResponse(json.loads(p.read_text()),
                        headers={"Cache-Control": "private, must-revalidate, max-age=0"})


# OPS-3 (2026-05-10) — admin endpoint for capability_registry edits.
# Replaces hand-editing capability_registry.json + risk of typo breaking RBAC.
# Validates schema, logs to audit_log.jsonl, only admin role allowed.
@app.patch("/api/capability-registry/items/{kind}/{item_id}")
async def capability_registry_patch(
    kind: str, item_id: str, request: Request,
    auth: HTTPBasicCredentials = Depends(_check_auth),
):
    """Edit a single registry entry. kind ∈ {tabs, sub_tabs, actions}.
    Admin role required. Validates payload + logs to audit_log.jsonl."""
    if isinstance(auth, Response):
        return auth
    # Admin-only check
    actor = auth.username
    try:
        from auth import role_for_user
        actor_role = role_for_user(actor)
    except Exception:
        actor_role = None
    if actor_role != "admin":
        return JSONResponse({"error": "admin role required"}, status_code=403)

    if kind not in ("tabs", "sub_tabs", "actions"):
        return JSONResponse({"error": f"invalid kind '{kind}'; expected tabs|sub_tabs|actions"}, status_code=400)

    p = BASE_DIR / "data" / "capability_registry.json"
    if not p.exists():
        return JSONResponse({"error": "capability_registry.json missing"}, status_code=404)

    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"error": "payload must be a JSON object"}, status_code=400)

    reg = json.loads(p.read_text())
    section = reg.setdefault(kind, {})
    before = section.get(item_id)

    # Schema-light validation: required keys depend on kind
    REQUIRED_KEYS = {
        "tabs":     ["label", "default_roles"],
        "sub_tabs": ["label", "default_roles"],
        "actions":  ["label", "default_roles"],
    }
    missing = [k for k in REQUIRED_KEYS[kind] if k not in payload]
    if missing and before is None:
        return JSONResponse({"error": f"missing required keys for new entry: {missing}"}, status_code=400)

    # Merge (allow partial update) but only on whitelisted keys
    ALLOWED_KEYS = {"label", "default_roles", "module", "description", "deprecated"}
    new_entry = dict(before or {})
    for k, v in payload.items():
        if k in ALLOWED_KEYS:
            new_entry[k] = v
    section[item_id] = new_entry

    # Audit-log first, then write registry (so audit captures intent even on write fail)
    try:
        from audit_log import append as _audit_append
        _audit_append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": "capability_registry_patch",
            "kind": kind,
            "item_id": item_id,
            "before": before,
            "after": new_entry,
            "ip": request.client.host if request.client else "?",
        })
    except Exception as _ae:
        log.warning(f"OPS-3 audit append failed (proceeding): {_ae}")

    p.write_text(json.dumps(reg, indent=2))
    return JSONResponse({"ok": True, "kind": kind, "item_id": item_id, "before": before, "after": new_entry})


# OPS-4 (2026-05-10) — audit log viewer endpoint for the CapStudio UI.
# Exposes data/audit_log.jsonl as paginated JSON. Admin only.
@app.get("/api/audit-log")
async def audit_log_view(
    limit: int = 100, offset: int = 0,
    actor: Optional[str] = None, action: Optional[str] = None,
    auth: HTTPBasicCredentials = Depends(_check_auth),
):
    """Paginated audit log read. Filters by actor / action substring."""
    if isinstance(auth, Response):
        return auth
    try:
        from auth import role_for_user
        if role_for_user(auth.username) != "admin":
            return JSONResponse({"error": "admin role required"}, status_code=403)
    except Exception:
        return JSONResponse({"error": "auth check failed"}, status_code=403)

    log_path = BASE_DIR / "data" / "audit_log.jsonl"
    if not log_path.exists():
        return JSONResponse({"entries": [], "total": 0, "log_exists": False})

    rows = []
    try:
        for line in log_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if actor and actor.lower() not in (e.get("actor", "").lower()):
                    continue
                if action and action.lower() not in (e.get("action", "").lower()):
                    continue
                rows.append(e)
            except Exception:
                continue
    except Exception as _e:
        return JSONResponse({"error": str(_e)[:200]}, status_code=500)

    rows.reverse()  # newest first
    total = len(rows)
    page = rows[offset:offset + limit]
    return JSONResponse({"entries": page, "total": total, "offset": offset, "limit": limit, "log_exists": True})


# OPS-2 (2026-05-10) — uptime ping endpoint for self-monitoring cron.
@app.get("/api/health-ping")
async def health_ping():
    """Lightweight liveness check, no auth (for external uptime monitor).
    Returns 200 OK with timestamp + scan_health snapshot."""
    try:
        sh_path = BASE_DIR / "data" / "scan_health.json"
        latest = None
        if sh_path.exists():
            sh = json.loads(sh_path.read_text())
            history = sh.get("history") or []
            if history:
                latest = history[-1]
        return JSONResponse({
            "ok": True,
            "ts": datetime.now(timezone.utc).isoformat(),
            "scan_health_last_ts": (latest or {}).get("ts"),
            "scan_health_pct": (latest or {}).get("pct"),
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


# -- V2 bootstrap (PERF-1b 2026-05-09) -----------------------------------------
# Combines /v2/_v + /api/capability-registry into ONE round-trip. shell.js and
# elite-detail-shell.js prefer this endpoint; fall back to the two split routes
# if it 404s. Saves ~100-150ms cold load (one fewer HTTP+auth handshake).
@app.get("/api/v2-bootstrap")
async def v2_bootstrap(auth: HTTPBasicCredentials = Depends(_check_auth)):
    if isinstance(auth, Response):
        return auth
    # version: max mtime under core/ + tabs/ — same as /v2/_v
    latest = 0
    for root in (_PROTOTYPE_DIR / "core", _PROTOTYPE_DIR / "tabs", _PROTOTYPE_DIR / "subtabs"):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in (".js", ".mjs"):
                try:
                    m = int(p.stat().st_mtime)
                    if m > latest:
                        latest = m
                except OSError:
                    pass
    # registry
    reg_path = BASE_DIR / "data" / "capability_registry.json"
    registry = json.loads(reg_path.read_text()) if reg_path.exists() else {"tabs": {}, "sub_tabs": {}, "actions": {}}
    return JSONResponse(
        {"version": str(latest or int(_time.time())), "registry": registry},
        headers={"Cache-Control": "private, must-revalidate, max-age=0"},
    )


# -- Backtest report (hedge_fund_report.py output) --
# Serves the latest backtest_report_latest.html. /api/backtest-report/history
# returns a list of all dated reports for navigation.
@app.get("/v2/backtest-report")
async def backtest_report_latest(auth: HTTPBasicCredentials = Depends(_check_auth)):
    p = BASE_DIR / "cache" / "backtest_report_latest.html"
    if not p.exists():
        return HTMLResponse("<h1>No backtest report yet</h1><p>Run <code>python3 hedge_fund_report.py</code> to generate one.</p>", status_code=404)
    return HTMLResponse(p.read_text(), headers=_NO_CACHE)

@app.get("/v2/backtest-report/{filename}")
async def backtest_report_by_filename(filename: str, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """Serve a specific historical report by filename (backtest_report_YYYYMMDD_HHMMSS.html)."""
    if not filename.startswith("backtest_report_") or not filename.endswith(".html") or "/" in filename or ".." in filename:
        return HTMLResponse("Bad filename", status_code=400)
    p = BASE_DIR / "cache" / filename
    if not p.exists():
        return HTMLResponse(f"Report not found: {filename}", status_code=404)
    return HTMLResponse(p.read_text(), headers=_NO_CACHE)


@app.get("/api/drift-alerts")
async def drift_alerts(limit: int = 30, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """A7 (2026-05-09): surface model_drift_alert.py history for dashboard tile.
    Reads data/drift_alerts.jsonl (written by the daily drift cron at
    LaunchAgents/com.swingtrade.driftalert.plist) and returns the last N
    entries, newest first."""
    import json as _json
    drift_log = BASE_DIR / "data" / "drift_alerts.jsonl"
    if not drift_log.exists():
        return JSONResponse({"alerts": [], "count": 0, "log_exists": False})
    rows = []
    try:
        for line in drift_log.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_json.loads(line))
            except Exception:
                continue
    except Exception as e:
        return JSONResponse({"alerts": [], "count": 0, "error": str(e)[:200]}, status_code=500)
    # Newest first
    rows.reverse()
    return JSONResponse({
        "alerts": rows[:limit],
        "count": len(rows),
        "log_exists": True,
        "log_path": str(drift_log.relative_to(BASE_DIR)),
    })


@app.post("/api/backtest-report/regen")
async def backtest_report_regen(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """OPS-5 (2026-05-09): regenerate hedge_fund_report.py from latest cached
    portfolio_backtest.json without re-running the full 3hr backtest. Useful
    after report-template tweaks or whitelist edits where you want to see the
    new analytics rendered on existing trade data."""
    import subprocess as _subp
    script = BASE_DIR / "hedge_fund_report.py"
    if not script.exists():
        return JSONResponse({"ok": False, "error": "hedge_fund_report.py not found"}, status_code=404)
    cache_json = BASE_DIR / "cache" / "portfolio_backtest.json"
    if not cache_json.exists():
        return JSONResponse({"ok": False, "error": "no cached backtest result to regen from"}, status_code=400)
    try:
        # Run with 60s timeout — report regen is fast (~5-15s typically).
        proc = _subp.run(
            ["python3", str(script)],
            capture_output=True, text=True, timeout=60, cwd=str(BASE_DIR),
        )
        if proc.returncode != 0:
            return JSONResponse({
                "ok": False, "error": f"hedge_fund_report exit {proc.returncode}",
                "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            }, status_code=500)
        # Find the freshest output file
        latest = max(
            (BASE_DIR / "cache").glob("backtest_report_*.html"),
            key=lambda p: p.stat().st_mtime, default=None,
        )
        return JSONResponse({
            "ok": True,
            "regen_ms": int((proc.returncode == 0) * 1),  # placeholder; subp doesn't expose duration
            "latest_report": latest.name if latest else None,
            "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
        })
    except _subp.TimeoutExpired:
        return JSONResponse({"ok": False, "error": "regen timed out (60s)"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.get("/api/backtest-report/history")
async def backtest_report_history(auth: HTTPBasicCredentials = Depends(_check_auth)):
    """List available backtest reports, newest first."""
    reports_dir = BASE_DIR / "cache"
    rows = []
    for p in sorted(reports_dir.glob("backtest_report_2*.html"), reverse=True):
        try:
            stat = p.stat()
            rows.append({
                "filename": p.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "url": f"/v2/backtest-report/{p.name}",
            })
        except Exception:
            continue
    return JSONResponse({"reports": rows[:50], "count": len(rows)})

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


# ════════════════════════════════════════════════════════════════════
# 2026-05-16 · New data exposure endpoints for v2 dashboard UI chips
# Each reads existing log/cache files and returns shaped JSON for the
# frontend to render directly — no schema changes required.
# ════════════════════════════════════════════════════════════════════

@app.get("/api/signal-history/{ticker}")
async def signal_history_api(ticker: str, limit: int = 10):
    """Return last N decisions for a ticker · for 'BUY #4 in row' chip.
    Reads data/signal_log.json (full system log) and filters by ticker.
    """
    import json
    from pathlib import Path
    ticker = ticker.upper().strip()
    log_path = Path("data/signal_log.json")
    if not log_path.exists():
        return {"ticker": ticker, "history": [], "consec": 0, "current": None}
    try:
        with open(log_path, "r") as f:
            raw = json.load(f)
        rows = raw if isinstance(raw, list) else raw.get("entries", [])
        ticker_rows = [r for r in rows if str(r.get("ticker", "")).upper() == ticker]
        ticker_rows.sort(key=lambda r: r.get("scan_date", r.get("timestamp", "")))
        history = []
        for r in ticker_rows[-limit:]:
            verdict = (r.get("decision") or r.get("verdict") or "").upper()
            letter = "B" if "BUY" in verdict or "BULL" in verdict else "W" if "WATCH" in verdict else "A"
            history.append({
                "date": r.get("scan_date") or r.get("timestamp", "")[:10],
                "letter": letter,
                "verdict": verdict,
                "score": r.get("score") or r.get("bap"),
                "setup": r.get("setup_family"),
            })
        consec = 0
        if history:
            cur = history[-1]["letter"]
            for h in reversed(history):
                if h["letter"] == cur:
                    consec += 1
                else:
                    break
        return {
            "ticker": ticker,
            "history": history,
            "consec": consec,
            "current": history[-1]["letter"] if history else None,
        }
    except Exception as e:
        return {"ticker": ticker, "history": [], "consec": 0, "current": None, "error": str(e)}


@app.post("/api/alert/push")
async def alert_push_api(req: Request):
    """Push an alert to all configured channels (Slack + browser-side notification).

    Body JSON: {ticker, level, title, body, url?, channels?}
      level: "info" | "warn" | "critical"
      channels: list — default ["slack"]; supported: "slack"
      (browser push fires client-side from the originating page; this endpoint
       only handles server-side channels like Slack/email/SMS)
    """
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(400, "invalid_json")
    ticker = (body.get("ticker") or "").upper().strip()
    level = (body.get("level") or "info").lower()
    title = (body.get("title") or "Kairos alert").strip()
    msg_body = (body.get("body") or "").strip()
    url = (body.get("url") or "").strip()
    channels = body.get("channels") or ["slack"]

    icon = {"info": ":bell:", "warn": ":warning:", "critical": ":rotating_light:"}.get(level, ":bell:")
    full = f"{icon} *[{level.upper()}]* "
    if ticker: full += f"`{ticker}` "
    full += f"*{title}*"
    if msg_body: full += f"\n{msg_body}"
    if url: full += f"\n<{url}|Open in Kairos>"

    sent = {}
    if "slack" in channels:
        try:
            import os
            webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
            if not webhook:
                # Fallback to config/config.json
                import json
                from pathlib import Path
                cfg_p = Path("config/config.json")
                if cfg_p.exists():
                    with open(cfg_p) as f:
                        cfg = json.load(f)
                    webhook = (cfg.get("alerts") or {}).get("slack_webhook", "")
            if webhook:
                from alerts import _slack_post
                sent["slack"] = bool(_slack_post(webhook, text=full))
            else:
                sent["slack"] = False
        except Exception as e:
            sent["slack"] = f"error: {e}"

    return {"status": "sent" if any(sent.values()) else "no_channel", "channels": sent, "echo": full}


@app.get("/api/test/mae-mfe")
async def test_mae_mfe_api(days: int = 90):
    """Analyze MAE (Max Adverse Excursion) vs MFE (Max Favorable Excursion)
    across closed trades to identify stop/target tuning opportunities.
    """
    import json
    from pathlib import Path
    from datetime import datetime, timedelta
    from statistics import mean, median
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    try:
        sl = json.load(open(sl_path))
    except Exception as e:
        return {"error": str(e)}
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    trades = [s for s in sl if s.get("status") == "CLOSED" and s.get("mae_pct") is not None
              and s.get("mfe_pct") is not None and (s.get("date") or "") >= cutoff]
    if not trades:
        return {"error": "no closed trades with mae/mfe in window", "trades_examined": 0}
    winners = [t for t in trades if (t.get("actual_pnl_pct") or 0) > 1]
    losers = [t for t in trades if (t.get("actual_pnl_pct") or 0) < -1]
    stopped = [t for t in trades if t.get("result") == "STOPPED"]
    target_hit = [t for t in trades if t.get("result") == "TARGET_HIT"]
    stop_too_tight = [t for t in winners if (t.get("mae_pct") or 0) <= -4]
    target_too_low = []
    for t in target_hit:
        mfe = t.get("mfe_pct", 0) or 0
        pnl = t.get("actual_pnl_pct", 0) or 0
        if mfe > pnl * 1.5 and mfe > 8:
            target_too_low.append({"ticker": t.get("ticker"), "date": (t.get("date") or "")[:10],
                                   "exit_pnl": round(pnl, 1), "mfe_pct": round(mfe, 1),
                                   "left_on_table": round(mfe - pnl, 1)})
    stop_saved = [t for t in stopped if (t.get("mfe_pct") or 0) <= 1]
    mae_dist = [t.get("mae_pct", 0) for t in trades]
    mfe_dist = [t.get("mfe_pct", 0) for t in trades]
    pnl_dist = [t.get("actual_pnl_pct", 0) for t in trades]
    def _bucket(vals, edges):
        out = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            count = sum(1 for v in vals if lo <= v < hi)
            out.append({"range": f"{lo}% to {hi}%", "count": count})
        return out
    mae_hist = _bucket(mae_dist, [-30, -15, -10, -7, -5, -3, -1, 0, 1])
    mfe_hist = _bucket(mfe_dist, [-1, 1, 3, 5, 8, 12, 20, 30, 100])
    return {
        "trades_examined": len(trades),
        "lookback_days": days,
        "summary": {
            "winners": len(winners), "losers": len(losers),
            "stopped": len(stopped), "target_hit": len(target_hit),
            "avg_mae_pct": round(mean(mae_dist), 2),
            "avg_mfe_pct": round(mean(mfe_dist), 2),
            "median_mae_pct": round(median(mae_dist), 2),
            "median_mfe_pct": round(median(mfe_dist), 2),
            "avg_pnl_pct": round(mean(pnl_dist), 2),
        },
        "stop_too_tight": {
            "count": len(stop_too_tight),
            "pct_of_winners": round(len(stop_too_tight) / max(1, len(winners)) * 100, 1),
            "interpretation": f"{len(stop_too_tight)} winners had MAE <= -4% (deep DD before reversing) - suggests stops at 1.0x ATR may be too tight; consider 1.5x ATR",
        },
        "target_too_low": {
            "count": len(target_too_low),
            "top_examples": target_too_low[:8],
            "interpretation": f"{len(target_too_low)} target_hit trades had MFE >1.5x exit price - left avg {round(mean([t['left_on_table'] for t in target_too_low]) if target_too_low else 0, 1)}% on table. Consider trailing past T1 instead of selling full.",
        },
        "stop_saved_loss": {
            "count": len(stop_saved),
            "interpretation": f"{len(stop_saved)} stops triggered on trades that never went positive - these are legitimate kill-the-loser exits, not over-tight stops.",
        },
        "mae_distribution": mae_hist,
        "mfe_distribution": mfe_hist,
    }


@app.get("/api/test/regime-conditional")
async def test_regime_conditional_api(days: int = 180):
    """Partition closed trades by regime and compute per-regime stats."""
    import json
    from pathlib import Path
    from datetime import datetime, timedelta
    from statistics import mean
    from collections import defaultdict
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    sl = json.load(open(sl_path))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    trades = [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None
              and (s.get("date") or "") >= cutoff]
    regime_by_date = {}
    dl_path = Path("data/decision_log.jsonl")
    if dl_path.exists():
        with open(dl_path) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    e = json.loads(line)
                    d = e.get("date")
                    r = e.get("regime4") or e.get("regime")
                    if d and r and d not in regime_by_date:
                        regime_by_date[d] = r
                except Exception: continue
    by_regime_setup = defaultdict(lambda: defaultdict(list))
    by_regime = defaultdict(list)
    for t in trades:
        d = (t.get("date") or "")[:10]
        r = regime_by_date.get(d, "unknown")
        setup = t.get("strategy") or "-"
        by_regime[r].append(t)
        by_regime_setup[r][setup].append(t)
    def _stats(arr):
        if not arr: return {"n": 0, "wr": 0, "mean_pnl": 0, "sum_pnl": 0, "pf": 0}
        pnls = [t.get("actual_pnl_pct", 0) for t in arr]
        wins = sum(1 for p in pnls if p > 1)
        gross_win = sum(p for p in pnls if p > 1)
        gross_loss = -sum(p for p in pnls if p < -1)
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0
        return {"n": len(arr), "wr": round(wins/len(arr)*100, 1),
                "mean_pnl": round(mean(pnls), 2), "sum_pnl": round(sum(pnls), 1), "pf": pf}
    result = {}
    for r, ts in by_regime.items():
        per_setup = []
        for setup, arr in sorted(by_regime_setup[r].items(), key=lambda kv: -len(kv[1])):
            per_setup.append({"setup": setup, **_stats(arr)})
        result[r] = {**_stats(ts), "per_setup": per_setup[:8]}
    sorted_regimes = sorted(result.items(), key=lambda kv: -kv[1]["mean_pnl"])
    best_regime = sorted_regimes[0] if sorted_regimes else None
    worst_regime = sorted_regimes[-1] if sorted_regimes else None
    return {
        "trades_examined": len(trades),
        "lookback_days": days,
        "regimes_seen": list(result.keys()),
        "by_regime": result,
        "best_regime": {"name": best_regime[0], "stats": best_regime[1]} if best_regime else None,
        "worst_regime": {"name": worst_regime[0], "stats": worst_regime[1]} if worst_regime else None,
    }


@app.get("/api/test/monte-carlo")
async def test_monte_carlo_api(days: int = 90, iterations: int = 5000):
    """Bootstrap-resample closed trades to build confidence intervals on Sharpe/PF/WR/mean."""
    import json, random
    from pathlib import Path
    from datetime import datetime, timedelta
    from statistics import mean, stdev
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    sl = json.load(open(sl_path))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    trades = [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None
              and (s.get("date") or "") >= cutoff]
    if len(trades) < 10:
        return {"error": f"insufficient trades ({len(trades)} < 10 minimum)"}
    pnls = [t.get("actual_pnl_pct", 0) for t in trades]
    n = len(pnls)
    def _metrics(sample):
        m = mean(sample)
        sd = stdev(sample) if len(sample) > 1 else 0
        wins = [p for p in sample if p > 1]
        losers = [p for p in sample if p < -1]
        gross_win = sum(wins)
        gross_loss = -sum(losers)
        pf = gross_win / gross_loss if gross_loss > 0 else 999
        sharpe = m / sd if sd > 0 else 0
        wr = len(wins) / len(sample) * 100 if sample else 0
        return {"mean": m, "sharpe": sharpe, "pf": min(pf, 999), "wr": wr}
    actual = _metrics(pnls)
    metric_dists = {"mean": [], "sharpe": [], "pf": [], "wr": []}
    random.seed(42)
    iterations = min(iterations, 10000)
    for _ in range(iterations):
        sample = [random.choice(pnls) for _ in range(n)]
        m = _metrics(sample)
        for k, v in m.items():
            metric_dists[k].append(v)
    def _pct(arr, p):
        s = sorted(arr); idx = int(p/100 * len(s))
        return s[max(0, min(len(s)-1, idx))]
    result_metrics = {}
    for k, arr in metric_dists.items():
        result_metrics[k] = {
            "point": round(actual[k], 3),
            "ci_low_95": round(_pct(arr, 2.5), 3),
            "ci_high_95": round(_pct(arr, 97.5), 3),
            "ci_low_68": round(_pct(arr, 16), 3),
            "ci_high_68": round(_pct(arr, 84), 3),
            "mean": round(mean(arr), 3),
        }
    sh = result_metrics['sharpe']
    pf = result_metrics['pf']
    wr = result_metrics['wr']
    return {
        "trades_examined": n,
        "lookback_days": days,
        "iterations": iterations,
        "metrics": result_metrics,
        "interpretation": {
            "sharpe": f"Sharpe {sh['point']} [95% CI: {sh['ci_low_95']} to {sh['ci_high_95']}]" +
                      (" - CI crosses 0, edge uncertain" if sh['ci_low_95'] < 0 < sh['ci_high_95']
                       else " - CI positive, edge robust" if sh['ci_low_95'] > 0
                       else " - CI negative, strategy losing"),
            "pf": f"PF {pf['point']} [95% CI: {pf['ci_low_95']} to {pf['ci_high_95']}]" +
                  (" - CI crosses 1.0, breakeven uncertain" if pf['ci_low_95'] < 1 < pf['ci_high_95']
                   else " - CI above 1.0, profitable" if pf['ci_low_95'] > 1
                   else " - CI below 1.0, losing"),
            "wr": f"WR {wr['point']}% [95% CI: {wr['ci_low_95']} to {wr['ci_high_95']}%]",
        },
    }


@app.get("/api/test/permutation")
async def test_permutation_api(days: int = 90, iterations: int = 2000):
    """Strict permutation test: BUY mean PnL vs random samples drawn from the
    FULL pool (BUY + WATCH + SHORT). Tests whether BUY-label selection
    outperforms what you'd get from random label assignment on the same set
    of resolved signals. p-value < 0.05 = significant selection edge.
    """
    import json, random
    from pathlib import Path
    from datetime import datetime, timedelta
    from statistics import mean, stdev
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    sl = json.load(open(sl_path))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    # Pool = resolved signals WITH verdict label (so older pre-verdict-rollout
    # entries don't contaminate the null distribution).
    all_closed = [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None
                  and (s.get("date") or "") >= cutoff]
    pool = [s for s in all_closed if (s.get("verdict") or "").upper() in ("BUY", "WATCH", "SHORT")]
    buys = [s for s in pool if (s.get("verdict") or "").upper() == "BUY"]
    watches = [s for s in pool if (s.get("verdict") or "").upper() == "WATCH"]
    shorts = [s for s in pool if (s.get("verdict") or "").upper() == "SHORT"]
    skipped_no_verdict = len(all_closed) - len(pool)
    if len(pool) < 50 or len(buys) < 10:
        return {"error": f"insufficient data: pool={len(pool)}, BUY={len(buys)} (need pool>=50, BUY>=10)"}
    buy_pnls = [t.get("actual_pnl_pct", 0) for t in buys]
    watch_pnls = [t.get("actual_pnl_pct", 0) for t in watches]
    pool_pnls = [t.get("actual_pnl_pct", 0) for t in pool]
    buy_mean = mean(buy_pnls)
    n_buy = len(buy_pnls)
    pool_mean = mean(pool_pnls)
    watch_mean = mean(watch_pnls) if watch_pnls else 0
    random.seed(42)
    iterations = min(iterations, 10000)
    # Permutation: draw n_buy samples from full pool WITHOUT replacement,
    # compute mean. Repeat. This simulates "what if BUY label was assigned
    # randomly to n_buy signals out of the same pool?"
    null_means = []
    for _ in range(iterations):
        sample = random.sample(pool_pnls, n_buy)
        null_means.append(mean(sample))
    # p-value: fraction of null means >= actual BUY mean (one-tailed)
    p_value = sum(1 for m in null_means if m >= buy_mean) / iterations
    null_mu = mean(null_means)
    null_sd = stdev(null_means) if len(null_means) > 1 else 1
    z_score = (buy_mean - null_mu) / null_sd if null_sd > 0 else 0
    # BUY vs WATCH direct comparison (different population test)
    buy_vs_watch_delta = buy_mean - watch_mean
    if p_value < 0.01: verdict = "STRONG EDGE (p<0.01)"
    elif p_value < 0.05: verdict = "SIGNIFICANT EDGE (p<0.05)"
    elif p_value < 0.10: verdict = "MARGINAL EDGE (p<0.10)"
    else: verdict = "NO EDGE DETECTED (p>=0.10)"
    return {
        "trades_examined": len(pool),
        "lookback_days": days,
        "iterations": iterations,
        "pool_composition": {
            "total_resolved": len(pool),
            "buy": len(buys), "watch": len(watches), "short": len(shorts),
            "skipped_no_verdict": skipped_no_verdict,
            "buy_mean_pnl": round(buy_mean, 3),
            "watch_mean_pnl": round(watch_mean, 3),
            "pool_mean_pnl": round(pool_mean, 3),
            "buy_vs_watch_delta": round(buy_vs_watch_delta, 3),
        },
        "actual": {"mean_pnl": round(buy_mean, 3), "n": n_buy},
        "null_distribution": {
            "mean_of_means": round(null_mu, 3),
            "sd_of_means": round(null_sd, 3),
            "ci_95_low": round(sorted(null_means)[int(0.025*iterations)], 3),
            "ci_95_high": round(sorted(null_means)[int(0.975*iterations)], 3),
        },
        "p_value": round(p_value, 4),
        "z_score": round(z_score, 3),
        "verdict": verdict,
        "interpretation": (
            f"BUY label (n={n_buy}) mean: {buy_mean:+.2f}%/trade. "
            f"WATCH label (n={len(watches)}) mean: {watch_mean:+.2f}%/trade. "
            f"BUY-vs-WATCH delta: {buy_vs_watch_delta:+.2f}pp. "
            f"Null: random {n_buy}-trade subsets from full pool of {len(pool)} (BUY+WATCH+SHORT), "
            f"{iterations} draws -> mean={null_mu:+.2f}% +/- {null_sd:.2f}. "
            f"BUY is {z_score:+.1f} SD above random-label baseline. p={p_value:.4f}. {verdict}. "
            f"Interpretation: is the BUY-label selection process picking better-than-random signals from the same pool?"
        ),
    }


@app.get("/api/test/time-decay")
async def test_time_decay_api(days: int = 90, slice_days: int = 7):
    """Slice BUY trades into rolling windows and run permutation per slice
    to detect WHEN edge died (regime shift vs persistent bug)."""
    import json, random
    from pathlib import Path
    from datetime import datetime, timedelta
    from statistics import mean, stdev
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    sl = json.load(open(sl_path))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    closed = [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None
              and (s.get("date") or "") >= cutoff
              and (s.get("verdict") or "").upper() in ("BUY","WATCH","SHORT")]
    if not closed:
        return {"error": "no verdict-labeled closed trades in window"}
    # Bucket by slice
    from collections import defaultdict
    by_slice = defaultdict(lambda: {"buy": [], "pool": []})
    now = datetime.now()
    for s in closed:
        try:
            d = datetime.strptime((s.get("date") or "")[:10], "%Y-%m-%d")
        except Exception: continue
        age_days = (now - d).days
        slice_idx = age_days // slice_days
        v = (s.get("verdict") or "").upper()
        by_slice[slice_idx]["pool"].append(s.get("actual_pnl_pct", 0))
        if v == "BUY":
            by_slice[slice_idx]["buy"].append(s.get("actual_pnl_pct", 0))
    random.seed(42)
    iterations = 1000
    slices_out = []
    for idx in sorted(by_slice):
        slice_label = f"d-{idx*slice_days} to d-{(idx+1)*slice_days}"
        buys = by_slice[idx]["buy"]
        pool = by_slice[idx]["pool"]
        if len(buys) < 5 or len(pool) < 20:
            slices_out.append({"slice": slice_label, "n_buy": len(buys), "n_pool": len(pool), "status": "insufficient"})
            continue
        buy_mean = mean(buys)
        pool_mean = mean(pool)
        null_means = [mean(random.sample(pool, len(buys))) for _ in range(iterations)]
        p_val = sum(1 for m in null_means if m >= buy_mean) / iterations
        null_mu = mean(null_means)
        null_sd = stdev(null_means) if len(null_means) > 1 else 1
        z = (buy_mean - null_mu) / null_sd if null_sd > 0 else 0
        slices_out.append({
            "slice": slice_label, "n_buy": len(buys), "n_pool": len(pool),
            "buy_mean": round(buy_mean, 2), "pool_mean": round(pool_mean, 2),
            "z_score": round(z, 2), "p_value": round(p_val, 4),
            "verdict": "EDGE" if p_val < 0.10 else "NO EDGE",
            "status": "ok",
        })
    # Trend detection
    edge_slices = [s for s in slices_out if s.get("status") == "ok"]
    if len(edge_slices) >= 2:
        recent = edge_slices[0]; oldest = edge_slices[-1]
        trend = "EDGE DECAY" if oldest["z_score"] > recent["z_score"] + 0.5 else "EDGE GROWING" if recent["z_score"] > oldest["z_score"] + 0.5 else "STABLE"
    else:
        trend = "n/a"
    return {
        "trades_examined": len(closed),
        "slice_days": slice_days,
        "n_slices": len(slices_out),
        "slices": slices_out,
        "trend": trend,
    }


@app.get("/api/diagnostics/forensics")
async def diagnostics_forensics_api(days: int = 90):
    """Run 7-hypothesis forensic battery on recent BUYs. Pure read-only.
    Returns actionable recommendations ranked by Wilson-validated lift estimate.
    """
    import json
    from pathlib import Path
    from datetime import datetime, timedelta
    from statistics import mean
    from collections import defaultdict
    import math
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    sl = json.load(open(sl_path))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    closed = [s for s in sl if s.get("status")=="CLOSED" and s.get("actual_pnl_pct") is not None
              and (s.get("date") or "") >= cutoff]
    buys = [s for s in closed if (s.get("verdict") or "").upper() == "BUY"]
    if not buys:
        return {"error": "no BUY trades in window"}
    def _stats(arr):
        if not arr: return {"n":0,"wr":0,"mean":0,"pf":0,"sum":0}
        pnls = [s.get("actual_pnl_pct",0) for s in arr]
        wins = sum(1 for p in pnls if p > 1)
        gw = sum(p for p in pnls if p > 1); gl = -sum(p for p in pnls if p < -1)
        return {"n":len(arr),"wr":round(wins/len(arr)*100,1),
                "mean":round(mean(pnls),2),"pf":round(gw/gl,2) if gl>0 else 0,
                "sum":round(sum(pnls),1)}
    def _wilson_lb(wins, n, z=1.96):
        if n == 0: return 0.0
        p = wins / n
        denom = 1 + z*z/n
        center = p + z*z/(2*n)
        spread = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
        return max(0.0, (center - spread) / denom) * 100

    # H1 time decay
    by_month = defaultdict(list)
    for s in buys: by_month[(s.get("date") or "")[:7]].append(s)
    time_decay = [{"month":m, **_stats(by_month[m])} for m in sorted(by_month)]

    # H2 per setup with Wilson LB
    by_setup = defaultdict(list)
    for s in buys: by_setup[s.get("strategy") or "-"].append(s)
    setups = []
    for setup, arr in sorted(by_setup.items(), key=lambda kv:-len(kv[1])):
        st = _stats(arr)
        wins = sum(1 for s in arr if s.get("actual_pnl_pct",0) > 1)
        wlb = round(_wilson_lb(wins, st["n"]), 1)
        # Recommendation: kill if Wilson LB < 35% AND PF < 1.0 AND mean < 0
        # (per retail calibration · principle #1 n>=10 preliminary)
        # PF<1.0 ensures we don't kill high-payoff/low-WR setups (Trend Continuation
        # has 31% WR but PF 1.21 because winners are huge — that's a feature)
        rec = None
        if st["n"] >= 10 and wlb < 35 and st["pf"] < 1.0 and st["mean"] < 0:
            rec = {"action": "KILL", "new_mult": 0.0, "reason": f"Wilson LB {wlb}%, PF {st['pf']}, mean {st['mean']}% — all sub-breakeven (n={st['n']})"}
        elif st["n"] >= 10 and wlb < 45 and st["pf"] < 1.0:
            rec = {"action": "REDUCE", "new_mult": 0.5, "reason": f"Wilson LB {wlb}%, PF {st['pf']} < 1.0 (n={st['n']})"}
        setups.append({"setup":setup, **st, "wilson_lb":wlb, "recommendation":rec})

    # H3 score bands
    bands = [(60,70),(70,75),(75,80),(80,85),(85,90),(90,100)]
    band_results = []
    for lo,hi in bands:
        arr = [s for s in buys if lo <= (s.get("score") or 0) < hi]
        if arr:
            st = _stats(arr)
            wins = sum(1 for s in arr if s.get("actual_pnl_pct",0) > 1)
            wlb = round(_wilson_lb(wins, st["n"]), 1)
            band_results.append({"band":f"{lo}-{hi}", "lo":lo, "hi":hi, **st, "wilson_lb":wlb})

    # H4 exit reasons
    by_result = defaultdict(list)
    for s in buys: by_result[s.get("result") or "-"].append(s)
    exits = [{"reason":r, **_stats(arr)} for r,arr in sorted(by_result.items(), key=lambda kv:-len(kv[1]))]

    # H5 stop-widening simulation
    stopped = [s for s in buys if s.get("result") == "STOPPED"]
    saveable = [s for s in stopped if (s.get("mfe_pct",0) > 3)]
    stop_widen = {
        "n_stopped": len(stopped),
        "n_saveable": len(saveable),
        "current_avg_loss": round(mean([s.get("actual_pnl_pct",0) for s in stopped]),2) if stopped else 0,
        "lift_pp_if_saved": round(sum([s.get("mfe_pct",0)/2 - s.get("actual_pnl_pct",0) for s in saveable]) / max(1,len(buys)), 2),
    }

    # H6 trailing target simulation
    target_hit = [s for s in buys if s.get("result") == "TARGET_HIT"]
    extra = [(s.get("mfe_pct",0) - s.get("actual_pnl_pct",0)) for s in target_hit if s.get("mfe_pct",0) > s.get("actual_pnl_pct",0)]
    trail = {
        "n_target_hit": len(target_hit),
        "extra_pp_total": round(sum(extra),1),
        "extra_pp_per_buy": round(sum(extra) / max(1,len(buys)),2),
    }

    # H7 RS rank
    rs_buckets = [(0,40),(40,60),(60,75),(75,85),(85,100)]
    rs = []
    for lo,hi in rs_buckets:
        arr = [s for s in buys if lo <= (s.get("rs_rank") or 0) < hi]
        if arr: rs.append({"band":f"{lo}-{hi}", **_stats(arr)})

    # Rank recommendations by historical lift (sum_pnl of trades that'd be removed)
    recs = []
    for s in setups:
        if s.get("recommendation"):
            recs.append({
                "kind": "setup_multiplier",
                "target": s["setup"],
                "action": s["recommendation"]["action"],
                "new_value": s["recommendation"]["new_mult"],
                "reason": s["recommendation"]["reason"],
                "historical_lift_pp": round(-s["sum"], 1) if s["sum"] < 0 else 0,
                "wilson_lb": s["wilson_lb"], "n": s["n"],
            })
    # Sort recs by absolute lift
    recs.sort(key=lambda r:-r.get("historical_lift_pp",0))

    # Score band recommendation
    losing_bands = [b for b in band_results if b["mean"] < 0 and b["n"] >= 10]
    winning_bands = [b for b in band_results if b["mean"] > 1 and b["n"] >= 5]
    if losing_bands and winning_bands:
        new_floor = min(b["lo"] for b in winning_bands)
        lost_sum = sum(b["sum"] for b in losing_bands if b["lo"] < new_floor)
        recs.append({
            "kind": "score_floor",
            "target": "buy_min_score",
            "action": "RAISE",
            "new_value": new_floor,
            "reason": f"score bands < {new_floor} have mean PnL < 0 (sum {lost_sum}pp lost)",
            "historical_lift_pp": round(-lost_sum, 1),
            "wilson_lb": None, "n": sum(b["n"] for b in losing_bands if b["lo"] < new_floor),
        })
    # Stop-widen recommendation
    if stop_widen["lift_pp_if_saved"] > 0.5:
        recs.append({
            "kind": "stop_multiplier",
            "target": "atr_stop_mult",
            "action": "WIDEN",
            "new_value": 1.5,
            "reason": f"{stop_widen['n_saveable']} of {stop_widen['n_stopped']} stopped trades had MFE > 3% (could have been winners)",
            "historical_lift_pp": stop_widen["lift_pp_if_saved"],
            "wilson_lb": None, "n": stop_widen["n_saveable"],
        })
    # Trail-target recommendation
    if trail["extra_pp_per_buy"] > 0.5:
        recs.append({
            "kind": "exit_rule",
            "target": "trail_past_t1",
            "action": "ENABLE",
            "new_value": True,
            "reason": f"{trail['n_target_hit']} target_hit trades left avg {trail['extra_pp_per_buy']}pp per BUY on table",
            "historical_lift_pp": trail["extra_pp_per_buy"] * len(buys) / len(buys),
            "wilson_lb": None, "n": trail["n_target_hit"],
        })

    return {
        "trades_examined": len(buys),
        "lookback_days": days,
        "summary": _stats(buys),
        "time_decay": time_decay,
        "setups": setups,
        "score_bands": band_results,
        "exits": exits,
        "stop_widen_sim": stop_widen,
        "trail_target_sim": trail,
        "rs_rank": rs,
        "recommendations": recs,
        "total_lift_pp": round(sum(r.get("historical_lift_pp",0) for r in recs), 1),
    }


@app.post("/api/diagnostics/apply-tune")
async def diagnostics_apply_tune_api(payload: Dict[str, Any] = Body(...)):
    """Apply a single auto-tune recommendation to config/config.json.
    Writes a tagged backup before mutating. Returns before/after diff.
    """
    import json, shutil
    from pathlib import Path
    from datetime import datetime
    kind = (payload.get("kind") or "").lower()
    target = payload.get("target") or ""
    new_value = payload.get("new_value")
    reason = payload.get("reason") or "auto-tune via forensics"
    if not kind or not target:
        return {"error": "missing kind or target"}
    cfg_path = Path("config/config.json")
    if not cfg_path.exists():
        return {"error": "config.json not found"}
    cfg = json.load(open(cfg_path))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = cfg_path.with_suffix(f".json.bak.{ts}")
    shutil.copy(cfg_path, backup)

    changes = []
    if kind == "setup_multiplier":
        mults = cfg.setdefault("setup_score_multiplier", {})
        old = mults.get(target)
        try:
            nv = float(new_value)
        except Exception:
            return {"error": f"new_value not a float: {new_value}"}
        mults[target] = nv
        changes.append({"path": f"setup_score_multiplier.{target}", "old": old, "new": nv})
        # For KILL (multiplier = 0.0), ALSO add to static_setup_kill_list so
        # decision_engine.compute_setup_kill_list picks it up (the live-computed
        # multiplier path ignores config.setup_score_multiplier entirely — see
        # decision_engine.compute_setup_size_multipliers).
        if nv == 0.0:
            # Derive n + wr_lb from payload-supplied wilson_lb + n if available
            extras = payload.get("wilson_lb"), payload.get("n")
            wlb_pct, n_obs = extras
            kl = cfg.setdefault("static_setup_kill_list", [])
            existing = next((e for e in kl if isinstance(e, dict) and e.get("setup") == target), None)
            entry = {
                "setup": target,
                "n": int(n_obs) if n_obs else 10,
                "wr_lb": round((float(wlb_pct) / 100.0), 3) if wlb_pct is not None else 0.20,
                "reason": reason or f"auto-tune kill from forensics endpoint",
                "source": "forensics_endpoint",
                "added": datetime.now().isoformat(timespec="seconds"),
                "override": True if (n_obs and int(n_obs) < 30) else False,
            }
            if existing:
                existing.update(entry)
                changes.append({"path": f"static_setup_kill_list[{target}] (UPDATED)", "old": "existing", "new": entry})
            else:
                kl.append(entry)
                changes.append({"path": f"static_setup_kill_list[{target}] (APPENDED)", "old": None, "new": entry})
    elif kind == "score_floor":
        thresholds = cfg.setdefault("regime4_thresholds", {})
        for regime, conf in thresholds.items():
            if isinstance(conf, dict) and "buy_min_score" in conf:
                old = conf["buy_min_score"]
                try:
                    nv = int(new_value)
                except Exception:
                    return {"error": f"new_value not an int: {new_value}"}
                if old < nv:
                    conf["buy_min_score"] = nv
                    changes.append({"path": f"regime4_thresholds.{regime}.buy_min_score", "old": old, "new": nv})
    elif kind == "stop_multiplier":
        # The real config path is scoring.stop_atr_multiple (default 1.25 per
        # analysis.py _base_stop_mult). Sleeve-specific overrides live at
        # {momentum,esp,insider_cluster,pead,mean_reversion,defensive}.stop_atr_multiple.
        scoring = cfg.setdefault("scoring", {})
        old = scoring.get("stop_atr_multiple")
        try:
            nv = float(new_value)
        except Exception:
            return {"error": f"new_value not a float: {new_value}"}
        scoring["stop_atr_multiple"] = nv
        changes.append({"path": "scoring.stop_atr_multiple", "old": old, "new": nv})
        # Clean up the bogus top-level key from earlier no-op writes
        if "atr_stop_mult" in cfg:
            removed = cfg.pop("atr_stop_mult")
            changes.append({"path": "atr_stop_mult (REMOVED — was no-op)", "old": removed, "new": None})
    elif kind == "exit_rule":
        # Toggle a flag
        exit_cfg = cfg.setdefault("exit_rules", {})
        old = exit_cfg.get(target)
        exit_cfg[target] = bool(new_value) if isinstance(new_value, (bool,int)) else (str(new_value).lower() == "true")
        changes.append({"path": f"exit_rules.{target}", "old": old, "new": exit_cfg[target]})
    else:
        return {"error": f"unknown kind: {kind}"}

    # Add audit entry
    audit = cfg.setdefault("_validations", {}).setdefault("auto_tune_log", [])
    audit.append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind, "target": target, "reason": reason,
        "changes": changes, "source": "forensics_endpoint",
    })

    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    return {"status": "applied", "backup": str(backup.name), "changes": changes}


@app.get("/api/diagnostics/ml-ab")
async def diagnostics_ml_ab_api(min_n: int = 30, verdict: str = "BUY"):
    """ML A/B test: does ML filtering of rules signals add Sharpe lift?

    Partitions rules BUYs into buckets by ML agreement:
      A — baseline: ALL rules BUYs (no ML filter)
      B — ML AGREE direction (p_up >= 0.40)
      C — ML DISAGREE direction (p_up <= 0.30 — predicts chop or down)
      D — ML AGREE hit-net (p_t1_first >= 0.30)
      E — ML DISAGREE hit-net (p_t1_first <= 0.10)

    Computes per-bucket: n, WR, mean_pnl, Sharpe, PF.
    Statistical test: bootstrap 5000× the mean PnL of Bucket B vs Bucket A,
    report 95% CI on the LIFT (B_mean - A_mean). If CI excludes 0, ML adds value.

    Returns verdict: ML_ADDS_VALUE / ML_NO_LIFT / ML_HURTS / INSUFFICIENT_DATA.
    """
    import json, random
    from pathlib import Path
    from statistics import mean, stdev
    pairs_path = Path("cache/ml_ab_pairs.jsonl")
    if not pairs_path.exists():
        return {"error": "no pairs captured yet — run scripts/ml_ab_capture.py after a scan"}
    pairs = []
    with open(pairs_path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: pairs.append(json.loads(line))
            except: pass
    # Verdict filter: BUY (strict — what we actually trade) or ALL (broader pool for early-stage diagnostics)
    verdict_filter = (verdict or "BUY").upper()
    if verdict_filter == "ALL":
        closed_buys = [p for p in pairs if p.get("rules_verdict") in ("BUY","WATCH","SHORT")
                       and p.get("realized_pct") is not None]
        scope_label = "all_verdicts"
    else:
        closed_buys = [p for p in pairs if p.get("rules_verdict") == verdict_filter
                       and p.get("realized_pct") is not None]
        scope_label = f"verdict={verdict_filter}"

    # Framework progress metrics (always returned for observability)
    total_closed_all = sum(1 for p in pairs if p.get("realized_pct") is not None)
    buys_total = sum(1 for p in pairs if p.get("rules_verdict") == "BUY")
    if len(closed_buys) < 5:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "scope": scope_label,
            "n_pairs_total": len(pairs),
            "n_closed_buys": len(closed_buys),
            "n_closed_all_verdicts": total_closed_all,
            "n_buys_open_or_closed": buys_total,
            "min_required": min_n,
            "message": (
                f"Have {len(closed_buys)} closed paired {verdict_filter} signals · need {min_n}+ for stat significance · "
                f"framework captured {len(pairs)} total pairs ({buys_total} BUYs, {total_closed_all} resolved). "
                f"Try ?verdict=ALL for broader-pool early diagnostics while BUYs accumulate."
            ),
        }

    def _stats(arr):
        if not arr: return {"n": 0, "wr": 0, "mean_pnl": 0, "sharpe_per_trade": 0, "pf": 0}
        pnls = [p.get("realized_pct", 0) or 0 for p in arr]
        n = len(pnls); m = mean(pnls)
        sd = stdev(pnls) if n > 1 else 0
        wins = sum(1 for v in pnls if v > 1)
        gw = sum(v for v in pnls if v > 1)
        gl = -sum(v for v in pnls if v < -1)
        return {
            "n": n,
            "wr": round(wins/n*100, 1),
            "mean_pnl": round(m, 2),
            "sharpe_per_trade": round(m/sd, 3) if sd > 0 else 0,
            "pf": round(gw/gl, 2) if gl > 0 else 0,
        }

    A = closed_buys
    B = [p for p in closed_buys if (p.get("ml_p_up") or 0) >= 0.40]
    C = [p for p in closed_buys if (p.get("ml_p_up") or 0) <= 0.30]
    D = [p for p in closed_buys if (p.get("ml_p_t1_first") or 0) >= 0.30]
    E = [p for p in closed_buys if (p.get("ml_p_t1_first") or 0) <= 0.10]

    buckets = {
        "A_baseline_all_rules_buys": _stats(A),
        "B_ml_agree_p_up_gte_0.40": _stats(B),
        "C_ml_disagree_p_up_lte_0.30": _stats(C),
        "D_ml_agree_hit_net_gte_0.30": _stats(D),
        "E_ml_disagree_hit_net_lte_0.10": _stats(E),
    }

    # Bootstrap lift of (B vs A) and (D vs A) for statistical significance
    def _bootstrap_lift(treatment, baseline, iters=5000):
        if len(treatment) < 5 or len(baseline) < 5: return None
        random.seed(42)
        t_pnls = [p.get("realized_pct", 0) for p in treatment]
        b_pnls = [p.get("realized_pct", 0) for p in baseline]
        lifts = []
        for _ in range(iters):
            t_sample = [random.choice(t_pnls) for _ in range(len(t_pnls))]
            b_sample = [random.choice(b_pnls) for _ in range(len(b_pnls))]
            lifts.append(mean(t_sample) - mean(b_sample))
        sorted_lifts = sorted(lifts)
        return {
            "point_lift_pp": round(mean(t_pnls) - mean(b_pnls), 3),
            "ci_low_95": round(sorted_lifts[int(0.025*iters)], 3),
            "ci_high_95": round(sorted_lifts[int(0.975*iters)], 3),
            "ci_excludes_zero": (sorted_lifts[int(0.025*iters)] > 0) or (sorted_lifts[int(0.975*iters)] < 0),
        }

    lift_BvA = _bootstrap_lift(B, A) if len(B) >= 5 else None
    lift_DvA = _bootstrap_lift(D, A) if len(D) >= 5 else None

    # Verdict
    if len(closed_buys) < min_n:
        verdict = "INSUFFICIENT_DATA"
        verdict_reason = f"n={len(closed_buys)} < {min_n} threshold — keep accumulating"
    elif lift_BvA and lift_BvA["ci_excludes_zero"] and lift_BvA["point_lift_pp"] > 0:
        verdict = "ML_ADDS_VALUE"
        verdict_reason = f"B (ML-agree) beats A (baseline) by {lift_BvA['point_lift_pp']}pp · 95% CI [{lift_BvA['ci_low_95']}, {lift_BvA['ci_high_95']}] excludes 0"
    elif lift_BvA and lift_BvA["ci_excludes_zero"] and lift_BvA["point_lift_pp"] < 0:
        verdict = "ML_HURTS"
        verdict_reason = f"B (ML-agree) underperforms A (baseline) by {abs(lift_BvA['point_lift_pp'])}pp · CI excludes 0"
    elif lift_BvA:
        verdict = "ML_NO_LIFT"
        verdict_reason = f"B vs A lift {lift_BvA['point_lift_pp']}pp · 95% CI [{lift_BvA['ci_low_95']}, {lift_BvA['ci_high_95']}] includes 0 (noise)"
    else:
        verdict = "INSUFFICIENT_DATA"
        verdict_reason = "B bucket too small for bootstrap"

    return {
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "n_closed_buys": len(closed_buys),
        "n_pairs_total": len(pairs),
        "buckets": buckets,
        "lift_BvA": lift_BvA,
        "lift_DvA": lift_DvA,
        "recommendation": (
            "Use ML p_up >= 0.40 as a hard filter — drop signals where ML disagrees"
            if verdict == "ML_ADDS_VALUE"
            else "Skip ML — current model adds no statistical lift; keep complexity cost in check"
            if verdict == "ML_HURTS"
            else "ML adds no edge in current sample — keep collecting before re-running"
            if verdict == "ML_NO_LIFT"
            else "Keep accumulating paired data — framework is live"
        ),
        "thresholds_used": {
            "ml_agree_p_up": 0.40,
            "ml_disagree_p_up": 0.30,
            "ml_agree_hit_net": 0.30,
            "ml_disagree_hit_net": 0.10,
        },
    }


@app.get("/api/positions/active-watch")
async def positions_active_watch_api():
    """For each open portfolio position, return live price + explicit verdict:
    EXIT_STOP (price <= stop) · TRAIL_ACTIVE (past T1) · HOLD · APPROACHING_STOP (within 1 ATR).
    Closes the post-BUY gap — gives user a single source of truth for daily action.
    """
    import json
    from pathlib import Path
    # Source of truth = data/portfolio_state.json (per CLAUDE.md, this is real PnL truth).
    # cache/portfolio.json is a legacy file. portfolio_tracker has no get_open_positions
    # method — it manipulates positions inline.
    pp = Path("data/portfolio_state.json")
    positions = []
    if pp.exists():
        try:
            d = json.loads(pp.read_text())
            positions = d.get("positions") or d.get("open_positions") or []
        except Exception: pass
    if not positions:
        return {"positions": [], "count": 0, "summary": {"hold": 0, "exit_stop": 0, "trail_active": 0, "approaching_stop": 0}}
    # Get live prices via internal /api/live/quote handler (Schwab primary, EODHD fallback)
    tickers = [p.get("ticker") for p in positions if p.get("ticker")]
    prices = {}
    if tickers:
        try:
            q = await live_quote(tickers=",".join(tickers))
            prices = q.get("prices", {}) or {}
        except Exception:
            pass
    out = []
    summary = {"hold": 0, "exit_stop": 0, "trail_active": 0, "approaching_stop": 0, "approaching_t1": 0, "no_price": 0}
    for p in positions:
        tk = p.get("ticker")
        if not tk: continue
        entry = float(p.get("entry_price") or p.get("entry") or 0)
        stop = float(p.get("stop") or 0)
        t1 = float(p.get("target1") or 0)
        t2 = float(p.get("target2") or 0)
        direction = (p.get("direction") or "long").lower()
        shares = int(p.get("shares") or 0)
        opened = p.get("entry_date") or p.get("opened") or ""
        cur_raw = prices.get(tk)
        if isinstance(cur_raw, dict):
            cur = float(cur_raw.get("price") or cur_raw.get("last") or 0)
        else:
            cur = float(cur_raw or 0)
        # Compute verdict
        verdict = "NO_PRICE"
        action = "-"
        pnl_pct = 0
        if cur > 0 and entry > 0:
            pnl_pct = ((cur / entry) - 1) * 100 if direction == "long" else ((entry / cur) - 1) * 100
        if cur > 0:
            if direction == "long":
                if stop and cur <= stop:
                    verdict, action = "EXIT_STOP", f"SELL NOW — stop ${stop:.2f} hit (cur ${cur:.2f})"
                elif t2 and cur >= t2:
                    verdict, action = "TARGET2_HIT", f"TRIM/EXIT — T2 ${t2:.2f} hit (cur ${cur:.2f})"
                elif t1 and cur >= t1:
                    verdict, action = "TRAIL_ACTIVE", f"PARTIAL @ T1 ${t1:.2f} → trail rest with stop at breakeven (entry ${entry:.2f})"
                elif t1 and (t1 - cur) / max(0.01, t1 - entry) < 0.10:
                    verdict, action = "APPROACHING_T1", f"APPROACHING T1 ${t1:.2f} (cur ${cur:.2f}) — prep partial exit"
                elif stop and (cur - stop) / max(0.01, entry - stop) < 0.25:
                    verdict, action = "APPROACHING_STOP", f"APPROACHING STOP ${stop:.2f} (cur ${cur:.2f}) — set price alert"
                else:
                    verdict, action = "HOLD", f"HOLD — ${cur:.2f} between stop ${stop:.2f} and T1 ${t1:.2f}"
            else:  # short
                if stop and cur >= stop:
                    verdict, action = "EXIT_STOP", f"COVER NOW — stop ${stop:.2f} hit (cur ${cur:.2f})"
                elif t1 and cur <= t1:
                    verdict, action = "TARGET1_HIT", f"COVER PARTIAL @ T1 ${t1:.2f}"
                else:
                    verdict, action = "HOLD", f"HOLD short — ${cur:.2f}"
        else:
            verdict, action = "NO_PRICE", "Price feed missing — check Schwab/EODHD"
        summary[verdict.lower()] = summary.get(verdict.lower(), 0) + 1
        out.append({
            "ticker": tk, "direction": direction, "shares": shares,
            "entry": entry, "current": cur, "stop": stop, "target1": t1, "target2": t2,
            "pnl_pct": round(pnl_pct, 2),
            "dist_to_stop_pct": round((cur - stop) / cur * 100, 2) if cur and stop else None,
            "dist_to_t1_pct": round((t1 - cur) / cur * 100, 2) if cur and t1 else None,
            "verdict": verdict, "action": action,
            "opened": opened, "setup": p.get("setup_type") or p.get("setup"),
        })
    # Sort: EXIT_STOP first, then APPROACHING, then HOLD
    sort_key = {"EXIT_STOP": 0, "TARGET2_HIT": 1, "TRAIL_ACTIVE": 2, "APPROACHING_STOP": 3, "APPROACHING_T1": 4, "HOLD": 5, "NO_PRICE": 6}
    out.sort(key=lambda r: sort_key.get(r["verdict"], 9))
    return {"positions": out, "count": len(out), "summary": summary}


@app.get("/api/premarket-catalysts")
async def premarket_catalysts_api(lookback_hours: int = 16, mine_only: bool = False):
    """Pull overnight news for portfolio + watchlist tickers, categorize by catalyst type.
    Returns ranked catalysts with mine flag, magnitude, and sentiment.
    """
    import json
    from pathlib import Path
    from datetime import datetime, timedelta
    from collections import Counter
    cutoff = (datetime.now() - timedelta(hours=lookback_hours))
    mine = set()
    try:
        ps = json.load(open("data/portfolio_state.json"))
        for p in ps.get("positions", []):
            if p.get("ticker"): mine.add(p["ticker"].upper())
    except Exception: pass
    portfolio_tickers = list(mine)
    try:
        cfg = json.load(open("config/config.json"))
        wl = cfg.get("universe", {}).get("custom_watchlist", [])
        for sym in wl: mine.add(sym.upper())
    except Exception: pass
    try:
        dj = json.load(open("infra/prototype/data.json"))
    except Exception:
        return {"error": "data.json missing", "catalysts": []}
    CAT_RULES = [
        ("FDA",        ["fda", "approval", "clearance", "phase 3", "phase 2", "clinical trial"]),
        ("Earnings",   ["earnings", "eps", "beat", "missed", "guidance", "revenue", "outlook", "quarterly"]),
        ("M&A",        ["merger", "acquisition", "acquires", "acquired", "buyout", "takeover", "to acquire", "tender offer"]),
        ("Contract",   ["contract", "deal awarded", "partnership", "agreement signed", "signs deal"]),
        ("Executive",  ["ceo", "cfo", "executive", "appoints", "appointed", "resigns", "resigned", "stepping down"]),
        ("SEC Filing", ["10-k", "10-q", "8-k", "13f", "sec filing"]),
        ("Guidance",   ["raises guidance", "lowers guidance", "cuts guidance", "increases outlook", "warns"]),
        ("AI",         ["artificial intelligence", "generative ai", "llm", "chatgpt", "ai chip"]),
        ("Activist",   ["activist", "elliott management", "carl icahn", "third point", "starboard"]),
        ("Buyback",    ["buyback", "share repurchase", "authorized to repurchase"]),
        ("Dividend",   ["raises dividend", "special dividend", "ex-dividend"]),
        ("Lawsuit",    ["lawsuit", "settles", "litigation", "court ruling"]),
        ("Analyst",    ["upgraded", "downgraded", "price target", "initiated coverage"]),
    ]
    def _categorize(text):
        t = (text or "").lower()
        for cat, keywords in CAT_RULES:
            if any(k in t for k in keywords): return cat
        return "Other"
    def _magnitude(text, cat):
        t = (text or "").lower()
        if cat in ("FDA", "M&A", "Activist", "Lawsuit"): return "high"
        if cat in ("Earnings", "Guidance", "Executive"): return "high"
        if any(w in t for w in ("beats", "raises", "soars", "surges", "downgrad", "warns", "cuts")): return "high"
        if cat in ("Contract", "Buyback", "Analyst"): return "medium"
        return "low"
    catalysts = []
    seen_key = set()
    for n in (dj.get("market_news") or []):
        d = n.get("date") or n.get("published_at") or ""
        try:
            dt = datetime.fromisoformat(d.replace("Z", "")) if d else None
            if dt and dt.tzinfo is not None: dt = dt.replace(tzinfo=None)  # strip tz for naive comparison
        except Exception: dt = None
        if dt and dt < cutoff: continue
        for sym in (n.get("symbols") or []):
            sym_clean = str(sym).split(".")[0].upper()
            key = sym_clean + "|" + (n.get("title") or "")[:60]
            if key in seen_key: continue
            seen_key.add(key)
            title = n.get("title") or ""
            cat = _categorize(title)
            catalysts.append({
                "ticker": sym_clean, "headline": title,
                "source": n.get("source") or "EODHD",
                "category": cat, "magnitude": _magnitude(title, cat),
                "sentiment": (n.get("sentiment") or "").lower(),
                "when": d, "url": n.get("url") or "",
                "mine": sym_clean in mine,
            })
    try:
        tj = json.load(open("infra/prototype/tickers.json"))
        if isinstance(tj, dict):
            for sym, info in tj.items():
                if not isinstance(info, dict): continue
                news = info.get("news") or info.get("news_articles") or []
                if not isinstance(news, list): continue
                for n in news[:5]:
                    if not isinstance(n, dict): continue
                    d = n.get("published_at") or n.get("timestamp") or n.get("date") or ""
                    try: dt = datetime.fromisoformat(d.replace("Z", "")) if d else None
                    except Exception: dt = None
                    if dt and dt < cutoff: continue
                    title = n.get("title") or n.get("headline") or n.get("summary") or ""
                    key = sym.upper() + "|" + title[:60]
                    if key in seen_key: continue
                    seen_key.add(key)
                    cat = _categorize(title)
                    catalysts.append({
                        "ticker": sym.upper(), "headline": title,
                        "source": n.get("source") or "EODHD",
                        "category": cat, "magnitude": _magnitude(title, cat),
                        "sentiment": (n.get("sentiment") or n.get("sent") or "").lower(),
                        "when": d, "url": n.get("url") or n.get("link") or "",
                        "mine": sym.upper() in mine,
                    })
    except Exception: pass
    if mine_only:
        catalysts = [c for c in catalysts if c["mine"]]
    mag_order = {"high": 3, "medium": 2, "low": 1}
    catalysts.sort(key=lambda c: (-int(c["mine"]), -mag_order.get(c["magnitude"], 0), -(c.get("when") or "")[:19].__hash__() & 0xFFFF))
    cat_counts = Counter(c["category"] for c in catalysts)
    tk_counts = Counter(c["ticker"] for c in catalysts)
    return {
        "catalysts": catalysts[:60],
        "summary": {
            "total": len(catalysts),
            "mine_count": sum(1 for c in catalysts if c["mine"]),
            "by_category": dict(cat_counts.most_common()),
            "by_ticker_top5": dict(tk_counts.most_common(5)),
        },
        "portfolio_tickers": portfolio_tickers,
        "lookback_hours": lookback_hours,
        "cutoff": cutoff.isoformat(),
    }


@app.get("/api/code-history")
async def code_history_api(limit: int = 100):
    """Return commit history grouped by date with plain-English summaries.
    Reads git log, parses commit messages, extracts highlights for non-developers.
    """
    import subprocess, re
    from collections import defaultdict
    try:
        # %H = full hash, %h = short, %ai = ISO date, %s = subject, %b = body
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:===COMMIT===%n%h|%ai|%s|%an%n---BODY---%n%b%n---END---", "--", "SwingTrade/"],
            cwd="/Volumes/MyMacDisk/Claude Skills",
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"error": result.stderr[:200], "commits": []}
        raw = result.stdout
    except Exception as e:
        return {"error": str(e), "commits": []}

    # Plain-English category mapping (based on commit title prefix)
    CATEGORY = {
        "KAIROS": ("UI / Dashboard", "var(--copper)", "Changes to the kairos.html dashboard you see in the browser"),
        "BUY-PIPELINE": ("Pipeline Diagnostics", "var(--cy)", "Tools to see why BUY signals get filtered/demoted"),
        "WHATIF": ("What-If Simulator", "#a78bfa", "Counterfactual config testing"),
        "SECTOR-CAP": ("Sector Cap Controls", "var(--amb)", "Per-sector BUY limits and demotion tracking"),
        "KILL": ("Setup Kill List", "var(--rd)", "Removed a losing trade setup from rotation"),
        "PAPER": ("Paper Trading", "var(--gn)", "Live paper-trading simulation"),
        "PORTFOLIO": ("Portfolio Tracking", "var(--gn)", "Position management"),
        "BACKTEST": ("Backtest Engine", "var(--cy)", "Historical strategy validation"),
        "EODHD": ("Data Provider", "var(--ink-2)", "Market data feed (EODHD)"),
        "Audit": ("Audit Trail", "var(--ink-1)", "Decision-log browsing"),
        "Macro": ("Macro / Regime", "var(--amb)", "Market regime detection"),
        "Sharpe": ("Risk Metrics", "var(--cy)", "Sharpe / Sortino / drawdown math"),
        "MOM": ("Momentum Sleeve", "var(--gn)", "Momentum trade strategy"),
        "ESP": ("Earnings ESP Sleeve", "var(--amb)", "Earnings surprise predictor"),
        "INSIDER": ("Insider Cluster", "var(--copper)", "Insider buying signal"),
        "DEFENSIVE": ("Defensive Rotation", "var(--ink-2)", "Risk-off ETF strategy"),
        "PEAD": ("PEAD Sleeve", "var(--amb)", "Post-earnings drift"),
    }

    commits = []
    blocks = raw.split("===COMMIT===\n")
    for block in blocks[1:]:  # skip empty first
        try:
            header_end = block.find("\n---BODY---\n")
            body_end = block.find("\n---END---")
            if header_end < 0: continue
            header = block[:header_end]
            body = block[header_end + len("\n---BODY---\n"):body_end] if body_end > 0 else ""
            parts = header.split("|", 3)
            if len(parts) < 4: continue
            sh, iso_date, subj, author = parts
            # Extract category
            cat_key = next((k for k in CATEGORY if subj.upper().startswith(k.upper() + ":") or subj.upper().startswith(k.upper() + "-") or subj.upper().startswith(k.upper() + " ")), "Other")
            cat_label, cat_color, cat_desc = CATEGORY.get(cat_key, ("Other / Misc", "var(--ink-2)", "General changes"))
            # Clean title — drop the prefix
            clean_title = re.sub(r"^[A-Z0-9_-]+\s*[:.·]?\s*", "", subj, count=1).strip() or subj
            # Extract first 5 body lines as bullets for the "what changed"
            body_lines = [line.strip() for line in body.split("\n") if line.strip()]
            # Filter out Co-Authored-By and metadata
            meta_pat = re.compile(r"^(Co-Authored-By|Signed-off-by|Reviewed-by):", re.I)
            body_lines = [b for b in body_lines if not meta_pat.match(b)]
            highlights = body_lines[:6]
            commits.append({
                "sha": sh.strip(),
                "date": iso_date[:10],
                "time": iso_date[11:16],
                "author": author.strip(),
                "subject": subj.strip(),
                "category": cat_label,
                "category_color": cat_color,
                "category_desc": cat_desc,
                "title": clean_title,
                "highlights": highlights,
            })
        except Exception:
            continue
    # Group by date
    by_date = defaultdict(list)
    for c in commits:
        by_date[c["date"]].append(c)
    grouped = []
    for date in sorted(by_date.keys(), reverse=True):
        day_commits = by_date[date]
        # Day summary: count by category
        cats = defaultdict(int)
        for c in day_commits:
            cats[c["category"]] += 1
        grouped.append({
            "date": date,
            "count": len(day_commits),
            "categories": dict(cats),
            "commits": day_commits,
        })
    return {"days": grouped, "total_commits": len(commits)}


@app.get("/api/testing-status")
async def testing_status_api():
    """Return live status of all background validation tests.
    - Walk-forward backtest progress (read scan log)
    - Paper shadow tracker days
    - Active paper trading window
    """
    import subprocess, json
    from pathlib import Path
    from datetime import datetime
    status = {}
    # 1) Walk-forward backtest — check for running process + log progress
    try:
        ps_out = subprocess.run(["pgrep", "-fl", "walk_forward_v2"], capture_output=True, text=True, timeout=3)
        wf_running = bool(ps_out.stdout.strip())
        wf = {"running": wf_running}
        if wf_running:
            # Get elapsed time
            elapsed = subprocess.run(
                ["ps", "-eo", "etime,command"], capture_output=True, text=True, timeout=3
            )
            for line in elapsed.stdout.split("\n"):
                if "walk_forward_v2" in line:
                    wf["elapsed"] = line.split()[0]
                    break
        # Find latest walk-forward log
        log_files = sorted(Path("cache/logs").glob("walkforward_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if log_files:
            latest = log_files[0]
            wf["log_file"] = str(latest)
            wf["log_size"] = latest.stat().st_size
            # Parse last 50 lines for progress markers
            with open(latest) as f:
                tail_lines = f.readlines()[-80:]
            folds_started = sum(1 for l in tail_lines if "Fold " in l and "(parallel)" in l)
            folds_done = sum(1 for l in tail_lines if "results saved" in l.lower() or "completed" in l.lower())
            wf["folds_started"] = folds_started
            # Find latest progress line
            for line in reversed(tail_lines):
                if "Grid search" in line or "Test:" in line or "Train:" in line:
                    wf["last_progress"] = line.strip()[-150:]
                    break
        # Check if results file exists (= test complete)
        result_file = Path("cache/walk_forward_v2_results.json")
        if result_file.exists():
            try:
                results = json.load(open(result_file))
                wf["completed"] = True
                wf["results_summary"] = {
                    "folds": len(results.get("folds", [])),
                    "verdict": results.get("verdict", "unknown"),
                    "result_mtime": datetime.fromtimestamp(result_file.stat().st_mtime).isoformat(),
                }
            except Exception:
                pass
        else:
            wf["completed"] = False
        status["walk_forward"] = wf
    except Exception as e:
        status["walk_forward"] = {"error": str(e)}

    # 2) Paper shadow tracker
    try:
        sl_path = Path("data/shadow_paper_log.jsonl")
        if sl_path.exists():
            count = sum(1 for _ in open(sl_path) if _.strip())
            with open(sl_path) as f:
                first_line = f.readline()
                first_date = json.loads(first_line).get("date") if first_line.strip() else None
            status["shadow_paper"] = {
                "active": True,
                "days_tracked": count,
                "first_date": first_date,
                "min_required": 30,
                "auto_capture_wired": True,
                "schedule": "Mon-Fri 6:30am PT via com.swingtrade.daily launchd job",
            }
        else:
            status["shadow_paper"] = {"active": False, "days_tracked": 0, "min_required": 30}
    except Exception as e:
        status["shadow_paper"] = {"error": str(e)}

    # 3) Paper trading window
    try:
        pt_path = Path("data/paper_trading_start.json")
        if pt_path.exists():
            pt = json.load(open(pt_path))
            from datetime import date as _d
            start = _d.fromisoformat(pt.get("start_date"))
            today = _d.today()
            day_n = (today - start).days
            duration = pt.get("duration_days", 60)
            status["paper_trading"] = {
                "enabled": pt.get("enabled", False),
                "start_date": pt.get("start_date"),
                "day": day_n,
                "duration_days": duration,
                "direction": pt.get("direction_filter"),
                "max_daily_trades": pt.get("max_daily_trades"),
                "days_remaining": duration - day_n,
            }
        else:
            status["paper_trading"] = {"enabled": False}
    except Exception as e:
        status["paper_trading"] = {"error": str(e)}

    # 4) Setup tuner active kills
    try:
        cfg = json.load(open("config/config.json"))
        ssm = cfg.get("setup_score_multiplier", {})
        killed = [k for k, v in ssm.items() if not k.startswith("_") and isinstance(v, (int, float)) and v == 0]
        boosted = {k: v for k, v in ssm.items() if not k.startswith("_") and isinstance(v, (int, float)) and v > 1.0}
        status["setup_tuning"] = {
            "killed_setups": killed,
            "boosted_setups": boosted,
        }
    except Exception as e:
        status["setup_tuning"] = {"error": str(e)}

    return status


@app.post("/api/shadow-paper/snapshot")
async def shadow_paper_snapshot(req: Request):
    """Capture today's shadow comparison: ACTUAL trades vs WHAT IDEAL CONFIG WOULD HAVE DONE.
    Appends to data/shadow_paper_log.jsonl for cumulative tracking.
    Body: {min_score, sector_cap_under, setup_mults}  (config to shadow-test)
    """
    import json
    from pathlib import Path
    from datetime import datetime
    body = await req.json() if req else {}
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = Path("data/shadow_paper_log.jsonl")
    # Check if today's snapshot already exists
    existing = []
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    e = json.loads(line)
                    if e.get("date") == today:
                        return {"status": "already_captured", "date": today, "entry": e}
                    existing.append(e)
                except Exception: continue
    # Pull today's BUY signals from decision_log
    dl_entries = []
    try:
        with open("data/decision_log.jsonl") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    e = json.loads(line)
                    if str(e.get("date", "")).startswith(today): dl_entries.append(e)
                except Exception: continue
    except Exception: pass
    # Build today's snapshot
    actual_buys = [e for e in dl_entries if e.get("verdict") == "BUY"]
    # Dedup by ticker
    seen = {}
    for e in actual_buys:
        tk = e.get("ticker")
        if tk and (tk not in seen or (e.get("score") or 0) > (seen[tk].get("score") or 0)):
            seen[tk] = e
    actual_buys = list(seen.values())
    # Apply IDEAL filter
    min_score = int(body.get("min_score", 70))
    new_mults = body.get("setup_mults", {})
    def shadow_passes(e):
        s = e.get("setup_type") or e.get("setup")
        if s and s in new_mults and new_mults[s] <= 0: return False
        if (e.get("score") or 0) < min_score: return False
        return True
    shadow_buys = [e for e in actual_buys if shadow_passes(e)]
    # Snapshot row
    snap = {
        "date": today,
        "config": {"min_score": min_score, "setup_mults": new_mults},
        "actual_buy_count": len(actual_buys),
        "shadow_buy_count": len(shadow_buys),
        "actual_buys": [{"ticker": e.get("ticker"), "score": e.get("score"), "setup": e.get("setup_type")} for e in actual_buys],
        "shadow_buys": [{"ticker": e.get("ticker"), "score": e.get("score"), "setup": e.get("setup_type")} for e in shadow_buys],
        "shadow_only": [e.get("ticker") for e in shadow_buys if e.get("ticker") not in {a.get("ticker") for a in actual_buys}],
        "actual_only": [e.get("ticker") for e in actual_buys if e.get("ticker") not in {s.get("ticker") for s in shadow_buys}],
        "timestamp": datetime.now().isoformat(),
    }
    # Append to log
    with open(log_path, "a") as f:
        f.write(json.dumps(snap) + "\n")
    return {"status": "captured", "entry": snap, "total_history": len(existing) + 1}


@app.get("/api/shadow-paper/history")
async def shadow_paper_history():
    """Return cumulative shadow vs actual comparison + per-day delta + outcome resolution.
    For each historical snapshot, looks up what happened to each ticker by checking signal_log.
    """
    import json
    from pathlib import Path
    from statistics import mean
    log_path = Path("data/shadow_paper_log.jsonl")
    if not log_path.exists():
        return {"history": [], "summary": {"days_tracked": 0}, "note": "No shadow snapshots yet. POST /api/shadow-paper/snapshot to capture today."}
    entries = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try: entries.append(json.loads(line))
                    except Exception: continue
    except Exception as e:
        return {"error": str(e)}
    # Lookup outcomes from signal_log for each ticker
    try:
        sl = json.load(open("data/signal_log.json"))
        # ticker → list of closed entries
        sl_by_tk = {}
        for s in sl:
            if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None:
                sl_by_tk.setdefault(s.get("ticker"), []).append(s)
    except Exception:
        sl_by_tk = {}
    # Enrich each snapshot with realized outcomes
    enriched = []
    cumulative_actual_pnl = 0
    cumulative_shadow_pnl = 0
    actual_wins = actual_losses = shadow_wins = shadow_losses = 0
    for snap in entries:
        d = snap.get("date", "")
        actual_pnls = []
        shadow_pnls = []
        for a in snap.get("actual_buys", []):
            tk = a.get("ticker")
            for s in sl_by_tk.get(tk, []):
                if (s.get("date") or "")[:10] >= d:
                    actual_pnls.append(s.get("actual_pnl_pct", 0))
                    break
        for sh in snap.get("shadow_buys", []):
            tk = sh.get("ticker")
            for s in sl_by_tk.get(tk, []):
                if (s.get("date") or "")[:10] >= d:
                    shadow_pnls.append(s.get("actual_pnl_pct", 0))
                    break
        actual_sum = round(sum(actual_pnls), 2)
        shadow_sum = round(sum(shadow_pnls), 2)
        actual_w = sum(1 for p in actual_pnls if p > 1)
        actual_l = sum(1 for p in actual_pnls if p < -1)
        shadow_w = sum(1 for p in shadow_pnls if p > 1)
        shadow_l = sum(1 for p in shadow_pnls if p < -1)
        cumulative_actual_pnl += actual_sum
        cumulative_shadow_pnl += shadow_sum
        actual_wins += actual_w
        actual_losses += actual_l
        shadow_wins += shadow_w
        shadow_losses += shadow_l
        enriched.append({
            "date": d,
            "actual": {
                "n": len(snap.get("actual_buys", [])),
                "n_resolved": len(actual_pnls),
                "wins": actual_w, "losses": actual_l,
                "sum_pnl": actual_sum,
                "mean_pnl": round(mean(actual_pnls), 2) if actual_pnls else 0,
            },
            "shadow": {
                "n": len(snap.get("shadow_buys", [])),
                "n_resolved": len(shadow_pnls),
                "wins": shadow_w, "losses": shadow_l,
                "sum_pnl": shadow_sum,
                "mean_pnl": round(mean(shadow_pnls), 2) if shadow_pnls else 0,
            },
            "delta_pnl": round(shadow_sum - actual_sum, 2),
            "shadow_only_tickers": snap.get("shadow_only", []),
            "actual_only_tickers": snap.get("actual_only", []),
        })
    total_actual_resolved = sum(e["actual"]["n_resolved"] for e in enriched)
    total_shadow_resolved = sum(e["shadow"]["n_resolved"] for e in enriched)
    summary = {
        "days_tracked": len(enriched),
        "actual": {
            "n_taken": sum(e["actual"]["n"] for e in enriched),
            "n_resolved": total_actual_resolved,
            "wins": actual_wins, "losses": actual_losses,
            "wr": round(actual_wins / total_actual_resolved * 100, 1) if total_actual_resolved else 0,
            "cumulative_pnl": round(cumulative_actual_pnl, 2),
        },
        "shadow": {
            "n_taken": sum(e["shadow"]["n"] for e in enriched),
            "n_resolved": total_shadow_resolved,
            "wins": shadow_wins, "losses": shadow_losses,
            "wr": round(shadow_wins / total_shadow_resolved * 100, 1) if total_shadow_resolved else 0,
            "cumulative_pnl": round(cumulative_shadow_pnl, 2),
        },
        "verdict": None,
    }
    if total_shadow_resolved >= 10 and total_actual_resolved >= 10:
        pnl_gap = summary["shadow"]["cumulative_pnl"] - summary["actual"]["cumulative_pnl"]
        wr_gap = summary["shadow"]["wr"] - summary["actual"]["wr"]
        if pnl_gap > 5 and wr_gap > 5:
            summary["verdict"] = "shadow_winning"
        elif pnl_gap < -5 and wr_gap < -5:
            summary["verdict"] = "shadow_losing"
        else:
            summary["verdict"] = "inconclusive"
    return {"history": enriched, "summary": summary, "note": "Walk-forward validates the model; shadow tracks live forward."}


@app.post("/api/whatif-backtest")
async def whatif_backtest_api(req: Request):
    """Simulate a config change against historical signal_log over N days.
    Body: {days, setup_mults: {name: new_mult}, sector_cap_under, sector_cap_out, min_score}
    Returns: counterfactual TAKEN list + PnL stats compared to actual.
    """
    import json
    from pathlib import Path
    from collections import defaultdict
    from statistics import mean
    from datetime import datetime, timedelta
    try:
        body = await req.json()
    except Exception:
        body = {}
    days = int(body.get("days", 30))
    new_mults = body.get("setup_mults") or {}  # {setup_name: new_mult}
    new_cap_under = int(body.get("sector_cap_under", 2))
    new_cap_out = int(body.get("sector_cap_out", 3))
    min_score = int(body.get("min_score", 60))
    # Load signal_log
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    try:
        sl = json.load(open(sl_path))
    except Exception as e:
        return {"error": str(e)}
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    # Use CLOSED signals with realized PnL
    closed = [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None and (s.get("date") or "") >= cutoff]
    # ── Counterfactual filter ──
    def passes(s):
        # Reject if setup is killed
        strat = s.get("strategy") or "—"
        m = new_mults.get(strat, 1.0)
        if m <= 0: return False
        # Reject if score below min
        if (s.get("score") or 0) < min_score: return False
        return True
    eligible = [s for s in closed if passes(s)]
    # Now apply sector cap per day per sector
    # Group eligible by date
    by_date = defaultdict(list)
    for s in eligible:
        d = (s.get("date") or "")[:10]
        by_date[d].append(s)
    # Sort each day's candidates by score desc, then apply cap
    # NOTE: we don't have per-day sector outperformance data, so use new_cap_under as default
    # (more conservative). Mark this in response.
    simulated_taken = []
    for d, candidates in by_date.items():
        # Sort by score desc
        candidates.sort(key=lambda s: -(s.get("score") or 0))
        # Apply sector cap per day
        sector_count = defaultdict(int)
        for s in candidates:
            # Sector unknown for most signal_log entries — group by "Unknown" buckets
            # If sector exists, use it; otherwise treat as Unknown (single bucket)
            sect = (s.get("sector") or "Unknown").strip()
            if sector_count[sect] >= new_cap_under: continue
            simulated_taken.append(s)
            sector_count[sect] += 1
    # Compute counterfactual stats
    def _stats(arr, label):
        if not arr: return {"label": label, "n": 0, "wr": 0, "mean_pnl": 0, "sum_pnl": 0, "median_pnl": 0}
        pnls = sorted([s.get("actual_pnl_pct", 0) for s in arr])
        wins = sum(1 for p in pnls if p > 1)
        return {
            "label": label,
            "n": len(arr),
            "wr": round(wins / len(arr) * 100, 1),
            "mean_pnl": round(sum(pnls) / len(arr), 2),
            "sum_pnl": round(sum(pnls), 2),
            "median_pnl": round(pnls[len(pnls)//2], 2),
        }
    # Actual baseline: every closed signal (no filter)
    actual_stats = _stats(closed, "ACTUAL (all closed signals)")
    simulated_stats = _stats(simulated_taken, f"SIMULATED (mults + cap={new_cap_under})")
    # Per-setup breakdown of simulated
    by_setup = defaultdict(list)
    for s in simulated_taken:
        by_setup[s.get("strategy") or "—"].append(s)
    setup_breakdown = []
    for setup, arr in sorted(by_setup.items(), key=lambda kv: -len(kv[1]))[:8]:
        setup_breakdown.append({**_stats(arr, setup), "setup": setup})
    return {
        "days": days,
        "cutoff_date": cutoff,
        "config_simulated": {
            "setup_mults": new_mults,
            "sector_cap_under": new_cap_under,
            "min_score": min_score,
        },
        "actual": actual_stats,
        "simulated": simulated_stats,
        "delta": {
            "n_diff": simulated_stats["n"] - actual_stats["n"],
            "wr_diff": round(simulated_stats["wr"] - actual_stats["wr"], 1),
            "mean_pnl_diff": round(simulated_stats["mean_pnl"] - actual_stats["mean_pnl"], 2),
            "sum_pnl_diff": round(simulated_stats["sum_pnl"] - actual_stats["sum_pnl"], 2),
        },
        "setup_breakdown": setup_breakdown,
        "top_taken": [{"ticker": s.get("ticker"), "date": (s.get("date") or "")[:10], "setup": s.get("strategy"), "score": s.get("score"), "pnl_pct": s.get("actual_pnl_pct")} for s in sorted(simulated_taken, key=lambda x: -(x.get("actual_pnl_pct") or 0))[:10]],
        "worst_taken": [{"ticker": s.get("ticker"), "date": (s.get("date") or "")[:10], "setup": s.get("strategy"), "score": s.get("score"), "pnl_pct": s.get("actual_pnl_pct")} for s in sorted(simulated_taken, key=lambda x: (x.get("actual_pnl_pct") or 0))[:5]],
    }


@app.get("/api/setup-tuner")
async def setup_tuner_get():
    """Return current setup_score_multipliers + live per-setup stats for tuning UI."""
    import json
    from pathlib import Path
    from collections import defaultdict
    from statistics import mean
    cfg = json.load(open("config/config.json"))
    ssm = cfg.get("setup_score_multiplier", {})
    # Per-setup stats from signal_log (last 90d)
    sl_path = Path("data/signal_log.json")
    stats = defaultdict(lambda: {"n": 0, "wins": 0, "losses": 0, "mean_pnl": 0, "pnls": []})
    if sl_path.exists():
        try:
            sl = json.load(open(sl_path))
            for s in sl:
                if s.get("status") != "CLOSED" or s.get("actual_pnl_pct") is None: continue
                strat = s.get("strategy") or "—"
                p = s.get("actual_pnl_pct", 0)
                stats[strat]["n"] += 1
                if p >= 1: stats[strat]["wins"] += 1
                elif p <= -1: stats[strat]["losses"] += 1
                stats[strat]["pnls"].append(p)
        except Exception: pass
    # Wilson LB helper
    def _wilson(s, n, z=1.96):
        if n == 0: return 0
        p = s/n
        den = 1 + z*z/n
        num = p + z*z/(2*n) - z*((p*(1-p) + z*z/(4*n))/n)**0.5
        return max(0, num/den) * 100
    # Build response
    setups = []
    for k in sorted(ssm.keys()):
        if k.startswith("_"): continue
        v = ssm.get(k)
        if not isinstance(v, (int, float)): continue
        s = stats.get(k, {"n": 0, "wins": 0, "losses": 0, "pnls": []})
        n = s["n"]; wins = s["wins"]
        wr = round(wins / n * 100, 1) if n else 0
        mpnl = round(mean(s["pnls"]), 2) if s["pnls"] else 0
        wilson = round(_wilson(wins, n), 1) if n else 0
        # Auto-recommend bump direction
        rec = None
        if v == 0 and wilson >= 35: rec = {"action": "unkill", "to": 0.5, "why": f"Wilson {wilson}% above 35% floor"}
        elif v == 0 and wilson < 25 and n >= 30: rec = {"action": "keep_killed", "to": 0, "why": f"Wilson {wilson}% well below floor · keep killed"}
        elif v > 0 and wilson < 25 and n >= 30: rec = {"action": "kill", "to": 0, "why": f"Wilson {wilson}% below floor · candidate for kill"}
        elif v < 1.0 and wilson >= 55 and n >= 30: rec = {"action": "boost", "to": min(1.5, round(v + 0.3, 1)), "why": f"Wilson {wilson}% strong · boost size"}
        elif v < 1.5 and wilson >= 70 and n >= 30 and mpnl >= 4: rec = {"action": "max_boost", "to": 1.5, "why": f"Wilson {wilson}% + mean PnL +{mpnl}% · max size"}
        setups.append({
            "name": k, "mult": v, "n": n, "wr": wr, "wilson_lb": wilson,
            "mean_pnl": mpnl, "wins": wins, "losses": s["losses"],
            "recommendation": rec,
        })
    return {"setups": setups, "note": ssm.get("_comment", "")}


@app.post("/api/setup-tuner")
async def setup_tuner_set(req: Request):
    """Update a single setup's score multiplier. Body: {name, mult}"""
    import json
    body = await req.json()
    name = body.get("name")
    mult = body.get("mult")
    if name is None or mult is None:
        raise HTTPException(400, "name + mult required")
    try:
        mult = float(mult)
    except Exception:
        raise HTTPException(400, "mult must be numeric")
    if mult < 0 or mult > 2:
        raise HTTPException(400, "mult must be in [0, 2]")
    cfg_path = BASE_DIR / "config" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        ssm = cfg.setdefault("setup_score_multiplier", {})
        old = ssm.get(name)
        ssm[name] = mult
        # Save with indentation preserved
        cfg_path.write_text(json.dumps(cfg, indent=2))
        return {"ok": True, "name": name, "old": old, "new": mult}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/selection-quality")
async def selection_quality_api(days: int = 30):
    """Compare TAKEN vs MISSED BUY signals across multiple features.
    Surfaces WHY the executor's selection has been picking losers.

    days: lookback window (default 30; paper start = 2026-04-30 = ~19 days)
    """
    import json
    from pathlib import Path
    from collections import defaultdict
    from datetime import datetime, timedelta
    sl_path = Path("data/signal_log.json")
    if not sl_path.exists():
        return {"error": "signal_log.json missing"}
    try:
        sl = json.load(open(sl_path))
    except Exception as e:
        return {"error": str(e)}
    # Cutoff date
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    # Filter to CLOSED BUY signals within window
    closed = [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None
              and (s.get("date") or "") >= cutoff]
    # Determine which were TAKEN by executor
    try:
        port = json.load(open("data/portfolio_state.json"))
        held = {p.get("ticker") for p in port.get("positions", []) if p}
    except Exception:
        held = set()
    # A signal is "taken" if its ticker appears in held positions OR in any close-trade record
    # For now, use a simple proxy: ticker in current/historical portfolio
    # Look for closed_trades in picks_history
    taken_tickers = set(held)
    try:
        ph = json.load(open("cache/picks_history.json"))
        for t in ph.get("trades", []):
            if t.get("ticker"): taken_tickers.add(t.get("ticker"))
    except Exception: pass

    # Split signals
    def is_buy(s):
        v = (s.get("verdict") or s.get("decision") or "").upper()
        return "BUY" in v or s.get("strategy")  # heuristic — signal_log entries typically only logged for setups
    buy_signals = [s for s in closed if is_buy(s)]
    taken = [s for s in buy_signals if s.get("ticker") in taken_tickers]
    missed = [s for s in buy_signals if s.get("ticker") not in taken_tickers]
    # Each-bucket stats helper
    def _stats(arr):
        if not arr: return {"n": 0, "wr": 0, "mean_pnl": 0, "median_pnl": 0, "sum_pnl": 0}
        pnls = sorted([s.get("actual_pnl_pct", 0) for s in arr])
        wins = sum(1 for p in pnls if p > 1)
        return {
            "n": len(arr),
            "wr": round(wins / len(arr) * 100, 1),
            "mean_pnl": round(sum(pnls) / len(arr), 2),
            "median_pnl": round(pnls[len(pnls)//2], 2),
            "sum_pnl": round(sum(pnls), 2),
            "max": round(max(pnls), 2),
            "min": round(min(pnls), 2),
        }
    # Overall
    overall = {
        "taken": _stats(taken),
        "missed": _stats(missed),
        "lookback_days": days,
        "cutoff_date": cutoff,
    }
    # Per-feature breakdowns
    def _bucket_score(s):
        sc = s.get("score") or 0
        if sc >= 80: return "80+"
        if sc >= 70: return "70-79"
        if sc >= 60: return "60-69"
        if sc >= 50: return "50-59"
        return "<50"
    def _bucket_rs(s):
        rs = s.get("rs_rank") or 0
        if rs >= 90: return "90+"
        if rs >= 75: return "75-89"
        if rs >= 50: return "50-74"
        return "<50"
    def _bucket_rr(s):
        rr = s.get("rr") or 0
        if rr >= 4: return "≥4"
        if rr >= 3: return "3-4"
        if rr >= 2: return "2-3"
        return "<2"
    feature_extractors = {
        "score_band": _bucket_score,
        "setup": lambda s: s.get("strategy") or "—",
        "rs_band": _bucket_rs,
        "rr_band": _bucket_rr,
        "stars": lambda s: f"{s.get('stars') or 0}★",
        "direction": lambda s: s.get("direction") or "long",
    }
    features = {}
    for fname, extractor in feature_extractors.items():
        buckets = defaultdict(lambda: {"taken": [], "missed": []})
        for s in taken:
            buckets[extractor(s)]["taken"].append(s)
        for s in missed:
            buckets[extractor(s)]["missed"].append(s)
        rows = []
        for bkt, arrs in buckets.items():
            rows.append({
                "value": str(bkt),
                "taken": _stats(arrs["taken"]),
                "missed": _stats(arrs["missed"]),
            })
        # Sort by total count desc
        rows.sort(key=lambda r: -(r["taken"]["n"] + r["missed"]["n"]))
        features[fname] = rows
    # Top winners we missed
    missed_sorted = sorted(missed, key=lambda s: -(s.get("actual_pnl_pct") or 0))
    top_missed = [{
        "ticker": s.get("ticker"),
        "date": (s.get("date") or "")[:10],
        "setup": s.get("strategy"),
        "score": s.get("score"),
        "rs_rank": s.get("rs_rank"),
        "rr": s.get("rr"),
        "pnl_pct": s.get("actual_pnl_pct"),
        "result": s.get("result"),
        "exit_reason": s.get("exit_reason"),
    } for s in missed_sorted[:20]]
    # Worst taken
    taken_sorted = sorted(taken, key=lambda s: s.get("actual_pnl_pct") or 0)
    worst_taken = [{
        "ticker": s.get("ticker"),
        "date": (s.get("date") or "")[:10],
        "setup": s.get("strategy"),
        "score": s.get("score"),
        "rs_rank": s.get("rs_rank"),
        "rr": s.get("rr"),
        "pnl_pct": s.get("actual_pnl_pct"),
        "result": s.get("result"),
    } for s in taken_sorted[:10]]
    # Find biggest discriminator: feature where taken and missed differ most in mean PnL
    discriminator = None
    max_gap = 0
    for fname, rows in features.items():
        for r in rows:
            if r["taken"]["n"] >= 2 and r["missed"]["n"] >= 3:
                gap = r["missed"]["mean_pnl"] - r["taken"]["mean_pnl"]
                if abs(gap) > abs(max_gap):
                    max_gap = gap
                    discriminator = {"feature": fname, "value": r["value"], "gap_pct": round(gap, 2), "taken": r["taken"], "missed": r["missed"]}
    return {
        "overall": overall,
        "features": features,
        "top_missed_winners": top_missed,
        "worst_taken": worst_taken,
        "discriminator": discriminator,
    }


@app.get("/api/pipeline-diagnostic")
async def pipeline_diagnostic_api(date: str = ""):
    """Aggregate the full BUY pipeline cascade for a scan date.
    Reconstructs each demotion stage by reading decision_log.jsonl + scan log + last_bundle.json.
    Returns stage-by-stage counts + per-ticker migration path.
    """
    import json, re
    from pathlib import Path
    from collections import defaultdict, Counter
    log_path = Path("data/decision_log.jsonl")
    bundle_path = Path("cache/last_bundle.json")
    if not date:
        date = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    if not log_path.exists():
        return {"date": date, "stages": [], "error": "decision_log.jsonl missing"}
    # Read today's decisions
    entries = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    e = json.loads(line)
                    if str(e.get("date","")).startswith(date):
                        entries.append(e)
                except Exception: continue
    except Exception as e:
        return {"date": date, "error": str(e)}
    # Dedup by ticker, keep highest score (each ticker may have 4+ entries across buckets)
    by_ticker = {}
    for e in entries:
        tk = e.get("ticker")
        if not tk: continue
        if tk not in by_ticker or (e.get("score") or 0) > (by_ticker[tk].get("score") or 0):
            by_ticker[tk] = e
    total_scored = len(by_ticker)
    verds = Counter(e.get("verdict") for e in by_ticker.values())
    # Bucket reasons (handles sector_cap, hard gates, Wilson kills, etc.)
    def _gate(r):
        r = (r or "").lower()
        if "sector cap" in r:
            m = re.search(r"limit=(\d+)", r); cap = m.group(1) if m else "?"
            sec_m = re.search(r"sector cap: ([\w\s]+?)\s+(?:already|already has)", r)
            sec = sec_m.group(1).strip().title() if sec_m else "?"
            return f"sector_cap:{sec}(limit={cap})"
        if "industry cap" in r:
            m = re.search(r"limit=(\d+)", r); return f"industry_cap(limit={m.group(1) if m else '?'})"
        if "sector concentration cap" in r: return "DE_sector_cap"
        if "portfolio cap" in r or "slots available" in r: return "portfolio_cap"
        if "wilson" in r or ("kill" in r and "list" in r): return "wilson_kill"
        if "tail_loss" in r or "tier_zero" in r: return "tail_loss"
        if "entry_quality" in r or "extended" in r or "missed" in r: return "entry_quality"
        if "earnings_blackout" in r or "earnings blackout" in r: return "earnings_blackout"
        if "regime" in r and "gate" in r: return "regime_gate"
        if "liquidity" in r or "liq " in r: return "liquidity"
        if "fund_adequacy" in r or "fund adequacy" in r: return "fund_adequacy"
        if "decision_state" in r: return "decision_state"
        if "lacks relative strength" in r or "rs " in r: return "rs_too_low"
        if "no edge" in r: return "weak_structure"
        if "pullback entry" in r: return "ENTRY_OK"   # the BUY message
        return "other"
    # Bucket demotion reasons across all WATCH+AVOID
    watches = [e for e in by_ticker.values() if e.get("verdict") == "WATCH"]
    avoids = [e for e in by_ticker.values() if e.get("verdict") == "AVOID"]
    watch_reasons = Counter(_gate(e.get("reason","")) for e in watches)
    avoid_reasons = Counter(_gate(e.get("reason","")) for e in avoids)
    # Build stages (synthesized from the data we have)
    # NOTE: we can't perfectly reconstruct each stage without scan-time instrumentation,
    # but we can model the cascade from decision_log buckets.
    final_buys = [e for e in by_ticker.values() if e.get("verdict") == "BUY"]
    final_buys.sort(key=lambda e: -(e.get("score") or 0))
    # Read final bundle for "what actually shipped"
    bundle_buys = []
    if bundle_path.exists():
        try:
            b = json.load(open(bundle_path))
            for r in (b.get("buy_candidates") or []):
                bundle_buys.append({"ticker": r.get("ticker"), "score": r.get("score"), "setup_type": r.get("setup_family") or r.get("setup") or r.get("setup_type"), "sector": r.get("sector")})
        except Exception: pass
    bundle_buy_tkrs = {b["ticker"] for b in bundle_buys}
    # Tickers that LOG says BUY but bundle says NOT BUY (the silent demotions)
    silent_demoted = [e for e in final_buys if e.get("ticker") not in bundle_buy_tkrs]
    # Migration path per ticker (where it ended up)
    migrations = []
    for tk, e in by_ticker.items():
        v = e.get("verdict")
        in_final_bundle = tk in bundle_buy_tkrs
        if v == "BUY" and not in_final_bundle:
            migrations.append({"ticker": tk, "score": e.get("score"), "log_verdict": v, "final_verdict": "WATCH-silent", "reason": "silent demotion in DE-cap or portfolio-cap (no log entry)", "setup": e.get("setup_type"), "sector": e.get("sector")})
        elif v == "BUY" and in_final_bundle:
            migrations.append({"ticker": tk, "score": e.get("score"), "log_verdict": v, "final_verdict": "BUY", "reason": "survived all stages", "setup": e.get("setup_type"), "sector": e.get("sector")})
        elif v == "WATCH":
            migrations.append({"ticker": tk, "score": e.get("score"), "log_verdict": v, "final_verdict": "WATCH", "reason": (e.get("reason") or "")[:120], "gate": _gate(e.get("reason","")), "setup": e.get("setup_type"), "sector": e.get("sector")})
        # AVOID skipped from migration view — they never got to BUY consideration
    migrations.sort(key=lambda m: -(m.get("score") or 0))
    # ── Per-sector funnel: scored → passed-hard → BUY-cleared → in-bundle ──
    per_sector = defaultdict(lambda: {"scored": 0, "buy_log": 0, "watch": 0, "avoid": 0, "in_bundle": 0, "demoted_examples": []})
    for tk, e in by_ticker.items():
        sec = (e.get("sector") or "Unknown").strip().title() or "Unknown"
        per_sector[sec]["scored"] += 1
        v = e.get("verdict")
        if v == "BUY":
            per_sector[sec]["buy_log"] += 1
            if tk in bundle_buy_tkrs:
                per_sector[sec]["in_bundle"] += 1
            else:
                if len(per_sector[sec]["demoted_examples"]) < 3:
                    per_sector[sec]["demoted_examples"].append({"ticker": tk, "score": e.get("score"), "setup": e.get("setup_type")})
        elif v == "WATCH": per_sector[sec]["watch"] += 1
        elif v == "AVOID": per_sector[sec]["avoid"] += 1
    sector_funnel = sorted(per_sector.items(), key=lambda kv: -kv[1]["scored"])
    # ── Per-score-band breakdown ──
    bands = {"80+": (80,200), "70-79": (70,80), "60-69": (60,70), "50-59": (50,60), "<50": (0,50)}
    per_band = {b: {"scored": 0, "buy_log": 0, "in_bundle": 0, "watch": 0, "avoid": 0, "silent": 0} for b in bands}
    for tk, e in by_ticker.items():
        sc = +e.get("score", 0) or 0
        band = next((b for b, (lo, hi) in bands.items() if lo <= sc < hi), "<50")
        per_band[band]["scored"] += 1
        v = e.get("verdict")
        if v == "BUY":
            per_band[band]["buy_log"] += 1
            if tk in bundle_buy_tkrs: per_band[band]["in_bundle"] += 1
            else: per_band[band]["silent"] += 1
        elif v == "WATCH": per_band[band]["watch"] += 1
        elif v == "AVOID": per_band[band]["avoid"] += 1
    # ── Per-setup-family breakdown ──
    per_setup = defaultdict(lambda: {"scored": 0, "buy_log": 0, "in_bundle": 0, "watch": 0, "silent": 0})
    for tk, e in by_ticker.items():
        st = (e.get("setup_type") or "—").strip() or "—"
        per_setup[st]["scored"] += 1
        v = e.get("verdict")
        if v == "BUY":
            per_setup[st]["buy_log"] += 1
            if tk in bundle_buy_tkrs: per_setup[st]["in_bundle"] += 1
            else: per_setup[st]["silent"] += 1
        elif v == "WATCH": per_setup[st]["watch"] += 1
    setup_funnel = sorted(per_setup.items(), key=lambda kv: -kv[1]["scored"])[:12]
    # ── Recommended actions ──
    recommendations = []
    # 1. Silent demote count is huge → suggest investigating DE caps
    if len(silent_demoted) >= 5:
        recommendations.append({
            "severity": "critical",
            "title": f"{len(silent_demoted)} silent BUY→WATCH demotions today",
            "body": "compute_final_verdict says BUY but final bundle has it as WATCH. Most likely cause: decision_engine sector_cap (line 3824) or portfolio_cap (line 3858) silently rewriting verdicts. The new logging (this scan onward) will name names.",
            "action": "Re-run scan; check log for 'Sector cap (decision_engine)' + 'Portfolio cap' lines. Bump portfolio.config_e.max_positions if portfolio_cap is binding.",
        })
    # 2. Top watch_reason is sector_cap → suggest bumping cap
    top_w_reason, top_w_count = (list(watch_reasons.most_common(1)) or [(None, 0)])[0]
    if top_w_reason and "sector_cap" in top_w_reason and top_w_count >= 20:
        recommendations.append({
            "severity": "high",
            "title": f"{top_w_count} demotions hit {top_w_reason}",
            "body": "This sector's BUY cap is the binding constraint. Tickers with valid setups + scores ≥65 are being demoted because the per-sector slot was already taken.",
            "action": "Bump portfolio.dynamic_sector_cap.underperforming (or .outperforming) by 1 in config/config.json. Each +1 unlocks ~10-20 BUYs.",
        })
    # 3. Many BUYs in high score bands silently demoted
    high_band_silent = per_band.get("80+", {}).get("silent", 0) + per_band.get("70-79", {}).get("silent", 0)
    if high_band_silent >= 3:
        recommendations.append({
            "severity": "high",
            "title": f"{high_band_silent} high-score (70+) BUYs silently demoted",
            "body": "Your highest-conviction signals are being lost between log and bundle. These should be the LAST tickers killed.",
            "action": "Investigate cap ordering — high-score BUYs should win slot priority, not lose it. Check sector_cap sort key in swing_trade.py:3834.",
        })
    return {
        "date": date,
        "total_scored": total_scored,
        "final_verdicts": dict(verds),
        "watch_reasons": dict(watch_reasons.most_common(12)),
        "avoid_reasons": dict(avoid_reasons.most_common(10)),
        "final_buys_in_log": [{"ticker": e.get("ticker"), "score": e.get("score"), "setup": e.get("setup_type"), "sector": e.get("sector"), "in_bundle": e.get("ticker") in bundle_buy_tkrs} for e in final_buys[:30]],
        "bundle_buys": bundle_buys,
        "silent_demoted": [{"ticker": e.get("ticker"), "score": e.get("score"), "setup": e.get("setup_type"), "sector": e.get("sector")} for e in silent_demoted[:50]],
        "silent_demoted_count": len(silent_demoted),
        "migrations": migrations[:120],
        "per_sector": [{"sector": s, **info} for s, info in sector_funnel],
        "per_score_band": per_band,
        "per_setup": [{"setup": s, **info} for s, info in setup_funnel],
        "recommendations": recommendations,
    }


@app.get("/api/sector-cap-demotions")
async def sector_cap_demotions_api(date: str = ""):
    """Rich sector-cap diagnostic: survivors + outcomes + persistent-miss + diff + setup-mix.
    """
    import json, re
    from pathlib import Path
    from collections import defaultdict, Counter
    from datetime import datetime, timedelta
    log_path = Path("data/decision_log.jsonl")
    if not log_path.exists():
        return {"date": date, "sectors": {}, "total_demoted": 0}
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    # Ticker → sector lookup from data.json (fixes empty survivor sectors)
    ticker_sector = {}
    sector_etf_outperf = {}
    try:
        dj = json.load(open("infra/prototype/data.json"))
        for src in ("short_term", "medium_term", "long_term", "screener"):
            for t in dj.get(src, []) or []:
                if t and t.get("ticker") and t.get("sector"):
                    ticker_sector[t["ticker"]] = (t.get("sector") or "Unknown").strip().title() or "Unknown"
        # Sector ETF outperformance flags
        for etf, info in (dj.get("sector_etf") or {}).items():
            if isinstance(info, dict) and info.get("outperforming") is not None:
                sector_etf_outperf[etf] = bool(info.get("outperforming"))
    except Exception: pass
    # Ticker → current price (for outcomes calc — placeholder)
    ticker_price = {}
    try:
        tj = json.load(open("infra/prototype/tickers.json"))
        if isinstance(tj, dict):
            for sym, info in tj.items():
                if isinstance(info, dict) and info.get("price"):
                    ticker_price[sym] = float(info["price"])
    except Exception: pass
    # Load all entries
    entries = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: entries.append(json.loads(line))
                except Exception: continue
    except Exception as e:
        return {"date": date, "sectors": {}, "error": str(e)}
    today_entries = [e for e in entries if str(e.get("date","")).startswith(date)]
    # Build sets for persistent-miss tracking (last 7 days)
    week_ago = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    yesterday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    blocked_history = defaultdict(set)  # date → set of tickers blocked that day
    for e in entries:
        d = (e.get("date") or "")[:10]
        if d < week_ago: continue
        if e.get("verdict") != "WATCH": continue
        if "sector cap" not in (e.get("reason") or "").lower(): continue
        blocked_history[d].add(e.get("ticker"))
    # Persistent-miss count: how many consecutive recent days each ticker was blocked
    persistent = {}
    today_blocked = blocked_history.get(date, set())
    for tk in today_blocked:
        count = 0
        cur = datetime.strptime(date, "%Y-%m-%d")
        for _ in range(7):
            if tk in blocked_history.get(cur.strftime("%Y-%m-%d"), set()):
                count += 1
                cur -= timedelta(days=1)
            else: break
        persistent[tk] = count
    # Yesterday's blocked count per sector (for diff)
    yesterday_per_sector = defaultdict(set)
    sector_pat = re.compile(r"sector cap: (\w[\w\s]*?) already has (\d+) BUY", re.I)
    for e in entries:
        if (e.get("date") or "")[:10] != yesterday: continue
        if e.get("verdict") != "WATCH": continue
        m = sector_pat.search(e.get("reason") or "")
        if m:
            sect = m.group(1).strip().title()
            yesterday_per_sector[sect].add(e.get("ticker"))
    # Build today's demotions
    by_sector = defaultdict(lambda: {"demoted": [], "cap": None, "survivor_count_raw": None})
    for e in today_entries:
        if e.get("verdict") != "WATCH": continue
        reason = e.get("reason", "")
        m = sector_pat.search(reason)
        if not m: continue
        sector = m.group(1).strip().title()
        cap_m = re.search(r"limit=(\d+)", reason)
        cap = int(cap_m.group(1)) if cap_m else None
        survivors = int(m.group(2))
        tk = e.get("ticker")
        by_sector[sector]["demoted"].append({
            "ticker": tk,
            "score": e.get("score", 0),
            "setup_type": e.get("setup_type"),
            "rs_rank": e.get("rs_rank"),
            "rr_ratio": e.get("rr_ratio"),
            "entry_price": e.get("entry_price"),
            "current_price": ticker_price.get(tk),
            "industry": e.get("industry"),
            "persistent_days": persistent.get(tk, 1),
        })
        by_sector[sector]["cap"] = cap
        by_sector[sector]["survivor_count_raw"] = survivors
    # Build survivors per sector (cross-reference from data.json ticker_sector map)
    survivors_by_sector = defaultdict(list)
    today_buys = [e for e in today_entries if e.get("verdict") == "BUY"]
    seen_buys = {}
    for e in today_buys:
        tk = e.get("ticker")
        if not tk: continue
        if tk in seen_buys and (e.get("score") or 0) <= (seen_buys[tk].get("score") or 0): continue
        seen_buys[tk] = e
    for tk, e in seen_buys.items():
        sect = (e.get("sector") or ticker_sector.get(tk) or e.get("industry") or "Unknown").strip().title() or "Unknown"
        survivors_by_sector[sect].append({
            "ticker": tk,
            "score": e.get("score", 0),
            "setup_type": e.get("setup_type"),
            "rs_rank": e.get("rs_rank"),
            "entry_price": e.get("entry_price"),
            "current_price": ticker_price.get(tk),
        })
    # Outcomes summary across all sectors (3-day forward return for blocked tickers)
    # Note: this is an approximation. Real outcome = forward price - block price.
    # Without a price history snapshot per scan day, we use: blocked_entry_price → current_price
    outcomes_global = {"n": 0, "n_up": 0, "n_down": 0, "sum_pct": 0, "avg_pct": 0, "missed_winners": 0, "correctly_avoided": 0}
    # Compute per-sector + global
    sector_etf_map = {
        "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV",
        "Energy": "XLE", "Industrials": "XLI", "Basic Materials": "XLB",
        "Real Estate": "XLRE", "Utilities": "XLU", "Consumer Defensive": "XLP",
        "Consumer Cyclical": "XLY", "Communication Services": "XLC",
    }
    result = {}
    total = 0
    for sect, info in by_sector.items():
        # Dedup demoted by ticker — keep highest-score
        seen = {}
        for t in info["demoted"]:
            tk = t.get("ticker")
            if not tk: continue
            if tk not in seen or (t.get("score") or 0) > (seen[tk].get("score") or 0):
                seen[tk] = t
        deduped = sorted(seen.values(), key=lambda x: -(x.get("score") or 0))
        # Add 5d-style outcome: current vs entry (approximation)
        sector_outcomes = []
        for t in deduped:
            ep = t.get("entry_price"); cp = t.get("current_price")
            if ep and cp and ep > 0:
                pct = ((cp - ep) / ep) * 100
                t["fwd_pct"] = round(pct, 2)
                sector_outcomes.append(pct)
                outcomes_global["n"] += 1
                outcomes_global["sum_pct"] += pct
                if pct > 1: outcomes_global["n_up"] += 1; outcomes_global["missed_winners"] += 1
                elif pct < -1: outcomes_global["n_down"] += 1; outcomes_global["correctly_avoided"] += 1
        # Setup-mix breakdown (for blocked)
        setup_mix = Counter((t.get("setup_type") or "—") for t in deduped)
        # Sort survivors desc by score
        sv = sorted(survivors_by_sector.get(sect, []), key=lambda x: -(x.get("score") or 0))
        # Compute "lowest survivor score" vs "highest demoted score" gap
        lowest_surv = sv[-1].get("score", 0) if sv else None
        highest_demoted = deduped[0].get("score", 0) if deduped else None
        gap = (highest_demoted - lowest_surv) if (lowest_surv is not None and highest_demoted is not None) else None
        # Yesterday diff
        ytd_count = len(yesterday_per_sector.get(sect, set()))
        diff = len(deduped) - ytd_count
        # Outperformance label
        etf = sector_etf_map.get(sect, "")
        outperf = sector_etf_outperf.get(etf)
        outperf_str = ("outperforming" if outperf else "underperforming") if outperf is not None else "unknown"
        total += len(deduped)
        result[sect] = {
            "cap": info["cap"],
            "demoted_total": len(deduped),
            "demoted_top": deduped[:8],
            "survivors": sv,
            "survivor_count": len(sv),
            "gap_to_cutoff": gap,
            "lowest_survivor_score": lowest_surv,
            "highest_demoted_score": highest_demoted,
            "setup_mix": dict(setup_mix.most_common(6)),
            "diff_yesterday": diff,
            "etf": etf,
            "outperforming": outperf,
            "outperf_label": outperf_str,
            "sector_avg_fwd_pct": round(sum(sector_outcomes) / len(sector_outcomes), 2) if sector_outcomes else None,
        }
    if outcomes_global["n"]:
        outcomes_global["avg_pct"] = round(outcomes_global["sum_pct"] / outcomes_global["n"], 2)
        outcomes_global["pct_up"] = round(outcomes_global["n_up"] / outcomes_global["n"] * 100, 1)
    ordered = dict(sorted(result.items(), key=lambda kv: -kv[1]["demoted_total"]))
    return {
        "date": date,
        "sectors": ordered,
        "total_demoted": total,
        "sector_count": len(ordered),
        "persistent_misses": [{"ticker": tk, "days": dys} for tk, dys in sorted(persistent.items(), key=lambda kv: -kv[1])[:15] if dys >= 3],
        "outcomes": outcomes_global,
    }


@app.get("/api/sector-cap-whatif")
async def sector_cap_whatif(sector: str = "", new_cap: int = 0):
    """Preview tickers that would unlock if sector's cap was bumped.
    Uses data.json ticker→sector lookup to enrich BUY entries missing sector field.
    """
    import json, re
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")
    sector = sector.strip().title()
    if not sector:
        return {"error": "sector required"}
    # Build ticker → sector map from data.json
    ticker_sector = {}
    try:
        dj = json.load(open("infra/prototype/data.json"))
        for src in ("short_term", "medium_term", "long_term", "screener"):
            for t in dj.get(src, []) or []:
                if t and t.get("ticker") and t.get("sector"):
                    ticker_sector[t["ticker"]] = (t.get("sector") or "").strip().title()
    except Exception: pass
    # Load today's decision log
    entries = []
    try:
        with open("data/decision_log.jsonl") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    e = json.loads(line)
                    if str(e.get("date","")).startswith(date): entries.append(e)
                except Exception: continue
    except Exception: pass
    sector_pat = re.compile(r"sector cap: " + re.escape(sector) + r" already", re.I)
    # Find all this-sector candidates
    seen = {}
    for e in entries:
        tk = e.get("ticker")
        if not tk: continue
        v = e.get("verdict")
        if v not in ("BUY", "WATCH"): continue
        # Identify sector: prefer entry's sector, fall back to lookup map
        ent_sect = (e.get("sector") or ticker_sector.get(tk) or "").strip().title()
        # For WATCH entries: must have THIS sector's cap reason OR enriched sector matches
        if v == "WATCH":
            if not sector_pat.search(e.get("reason") or "") and ent_sect != sector:
                continue
        else:  # BUY entries: require enriched sector match
            if ent_sect != sector:
                continue
        if tk not in seen or (e.get("score") or 0) > (seen[tk].get("score") or 0):
            seen[tk] = e
    # Sort by score desc — these are the candidates competing for slots
    sorted_cands = sorted(seen.values(), key=lambda e: -(e.get("score") or 0))
    new_cap = int(new_cap) if new_cap else len(sorted_cands)
    new_buys = sorted_cands[:new_cap]
    current_buys = [e for e in seen.values() if e.get("verdict") == "BUY"]
    return {
        "sector": sector,
        "new_cap": new_cap,
        "current_buys": len(current_buys),
        "would_unlock": max(0, len(new_buys) - len(current_buys)),
        "total_candidates": len(sorted_cands),
        "new_buy_list": [{
            "ticker": e.get("ticker"),
            "score": e.get("score"),
            "setup": e.get("setup_type"),
            "was": e.get("verdict"),
        } for e in new_buys],
    }


@app.get("/api/decision-log")
async def decision_log_all_api(limit: int = 20, date_from: str = "", date_to: str = ""):
    """Return decision log entries across ALL tickers.

    Query params (all optional):
      limit: max entries returned (default 20). If date_from is set without
             explicit limit, bumps to 10000 to fit a 1-year window.
      date_from: ISO date 'YYYY-MM-DD' (inclusive). Filter entries with date >= date_from.
      date_to:   ISO date 'YYYY-MM-DD' (inclusive). Filter entries with date <= date_to.
    Sort: by entry 'date' field (decision_log.jsonl has no 'timestamp' field).
    """
    import json
    from pathlib import Path
    log_path = Path("data/decision_log.jsonl")
    if not log_path.exists():
        return {"entries": [], "limit": limit, "date_from": date_from, "date_to": date_to}
    # When a date range is supplied without explicit limit, allow much larger windows
    if (date_from or date_to) and limit == 20:
        limit = 10000
    try:
        entries = []
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    d = (e.get("date") or "")[:10]
                    if date_from and d < date_from:
                        continue
                    if date_to and d > date_to:
                        continue
                    entries.append(e)
                except Exception:
                    continue
        # Sort by date asc; default endpoint returns the most recent slice
        entries.sort(key=lambda e: (e.get("date") or e.get("timestamp") or ""))
        return {
            "entries": entries[-limit:],
            "total_in_range": len(entries),
            "limit": limit,
            "date_from": date_from,
            "date_to": date_to,
        }
    except Exception as e:
        return {"entries": [], "error": str(e)}


@app.get("/api/decision-log/{ticker}")
async def decision_log_api(ticker: str, limit: int = 20, date_from: str = "", date_to: str = ""):
    """Per-ticker audit trail for the Audit Trail browser.

    Query params (all optional):
      limit: max entries (default 20). Bumps to 10000 when date_from is set.
      date_from / date_to: ISO date 'YYYY-MM-DD' inclusive bounds.
    Reads data/decision_log.jsonl (newline-delimited JSON).
    """
    import json
    from pathlib import Path
    ticker = ticker.upper().strip()
    log_path = Path("data/decision_log.jsonl")
    if not log_path.exists():
        return {"ticker": ticker, "entries": [], "limit": limit, "date_from": date_from, "date_to": date_to}
    if (date_from or date_to) and limit == 20:
        limit = 10000
    try:
        entries = []
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if str(e.get("ticker", "")).upper() != ticker:
                        continue
                    d = (e.get("date") or "")[:10]
                    if date_from and d < date_from:
                        continue
                    if date_to and d > date_to:
                        continue
                    entries.append(e)
                except Exception:
                    continue
        entries.sort(key=lambda e: (e.get("date") or e.get("timestamp") or ""))
        return {
            "ticker": ticker,
            "entries": entries[-limit:],
            "total_in_range": len(entries),
            "limit": limit,
            "date_from": date_from,
            "date_to": date_to,
        }
    except Exception as e:
        return {"ticker": ticker, "entries": [], "error": str(e)}


@app.get("/api/ticker-snapshot")
async def ticker_snapshot_api(t: str, auth: HTTPBasicCredentials = Depends(_check_auth)):
    """On-demand ticker snapshot for tickers NOT in the last scan bundle.

    Used by kairos.html setDetailTicker() when a watchlist ticker wasn't scored
    in the last bundle (filtered by price/volume/EODHD data gap). Returns the
    most recent decision_log entry for the ticker so the detail panel can show
    last-known score/verdict/gates rather than empty placeholders.

    Also attempts a live quote from EODHD for current price.
    """
    if isinstance(auth, Response):
        return auth
    ticker = (t or "").upper().strip()
    if not ticker:
        raise HTTPException(400, "t= required")

    import json as _json
    from pathlib import Path as _Path

    # 1. Most recent decision_log entry for this ticker
    dl_path = _Path("data/decision_log.jsonl")
    last_decision = None
    if dl_path.exists():
        try:
            with open(dl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        e = _json.loads(line)
                        if str(e.get("ticker", "")).upper() == ticker:
                            last_decision = e
                    except Exception:
                        continue
        except Exception:
            pass

    # 2. Try live quote from EODHD (best-effort, timeout=5s)
    live_price = None
    try:
        import eodhd_client as _eo
        q = _eo.realtime_quote(ticker)
        if isinstance(q, dict):
            live_price = q.get("close") or q.get("last") or q.get("price")
    except Exception:
        pass

    # 3. Check tickers.json (last bundle) for any partial data
    bundle_row = None
    try:
        tj = _Path("infra/prototype/tickers.json")
        if tj.exists():
            td = _json.loads(tj.read_text())
            if isinstance(td, dict):
                bundle_row = td.get(ticker)
    except Exception:
        pass

    if not last_decision and not bundle_row:
        raise HTTPException(404, f"No data for {ticker} — not in decision_log or last bundle")

    return {
        "ticker": ticker,
        "source": "decision_log" if last_decision else "bundle_only",
        "last_scanned": (last_decision or {}).get("date"),
        "score":         (last_decision or {}).get("score"),
        "verdict":       (last_decision or {}).get("verdict"),
        "reason":        (last_decision or {}).get("reason"),
        "regime":        (last_decision or {}).get("regime4"),
        "setup_family":  (last_decision or {}).get("setup_type"),
        "rr_ratio":      (last_decision or {}).get("rr_ratio"),
        "entry_price":   (last_decision or {}).get("entry_price"),
        "gates_hit":     (last_decision or {}).get("gates_hit") or [],
        "score_breakdown":(last_decision or {}).get("score_breakdown") or {},
        "live_price":    live_price,
        "bundle_row":    bundle_row,
        "_note": "Stale score from last scan that included this ticker. Not today's scan.",
    }


@app.get("/api/sleeve-outcomes/{sleeve}")
async def sleeve_outcomes_api(sleeve: str, limit: int = 10):
    """Return last N outcomes (W/L) for a sleeve · for hot-streak dots.
    Reads cache/picks_history.json and filters by setup_family.
    """
    import json
    from pathlib import Path
    sleeve = sleeve.upper().strip()
    h_path = Path("cache/picks_history.json")
    if not h_path.exists():
        return {"sleeve": sleeve, "outcomes": [], "wins": 0, "losses": 0}
    try:
        with open(h_path, "r") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else data.get("picks", [])
        matched = [r for r in rows if sleeve in str(r.get("setup_family") or r.get("sleeve") or "").upper()]
        matched = [r for r in matched if r.get("outcome") in ("W", "L", "win", "loss", "TP", "SL")]
        matched.sort(key=lambda r: r.get("exit_date") or r.get("entry_date") or "")
        recent = matched[-limit:]
        outcomes = []
        for r in recent:
            o = r.get("outcome", "")
            outcomes.append("W" if o in ("W", "win", "TP") else "L")
        wins = outcomes.count("W")
        losses = outcomes.count("L")
        return {"sleeve": sleeve, "outcomes": outcomes, "wins": wins, "losses": losses}
    except Exception as e:
        return {"sleeve": sleeve, "outcomes": [], "wins": 0, "losses": 0, "error": str(e)}


@app.get("/api/picks-history-aggregate")
async def picks_history_aggregate_api():
    """Aggregate picks_history by score bucket → realized R · for calibration scatter.
    Returns scatter points: [{score_bucket, n, avg_r, wr_pct}]
    """
    import json
    from pathlib import Path
    h_path = Path("cache/picks_history.json")
    if not h_path.exists():
        return {"buckets": []}
    try:
        with open(h_path, "r") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else data.get("picks", [])
        rows = [r for r in rows if r.get("score") is not None and r.get("realized_r") is not None]
        # Score buckets: 60-65, 65-70, 70-75, 75-80, 80-85, 85-90, 90-100
        buckets = []
        for lo, hi in [(60, 65), (65, 70), (70, 75), (75, 80), (80, 85), (85, 90), (90, 100)]:
            bucket = [r for r in rows if lo <= float(r.get("score", 0)) < hi]
            n = len(bucket)
            if n == 0:
                continue
            avg_r = sum(float(r["realized_r"]) for r in bucket) / n
            wins = sum(1 for r in bucket if float(r["realized_r"]) > 0)
            buckets.append({
                "score_band": f"{lo}-{hi}",
                "score_mid": (lo + hi) / 2,
                "n": n,
                "avg_r": round(avg_r, 2),
                "wr_pct": round(wins / n * 100, 1) if n > 0 else 0,
            })
        return {"buckets": buckets}
    except Exception as e:
        return {"buckets": [], "error": str(e)}


@app.get("/api/calibration-report")
async def calibration_report_api():
    """Return cache/ml/calibration_report.json verbatim · powers the AI Prediction
    sub-tab's reliability diagram + calibration card. Read-only, no writes.
    """
    import json
    from pathlib import Path
    p = Path("cache/ml/calibration_report.json")
    if not p.exists():
        return {"error": "calibration_report.json not found", "modes": {}}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"error": str(e), "modes": {}}


@app.get("/api/ml-edge-diff")
async def ml_edge_diff_api(mode: str = "swing"):
    """Day-over-day diff from cache/ml_edge_history/ snapshots.
    Powers the AI Prediction tab's "Δ vs yesterday" panel.
    """
    import json
    from pathlib import Path
    snap_dir = Path("cache/ml_edge_history")
    if not snap_dir.exists():
        return {"error": "no snapshots", "flips": [], "new_bulls": [], "new_bears": [], "dropped": []}
    snaps = sorted(snap_dir.glob("*.json"))
    if not snaps:
        return {"error": "no snapshots yet", "flips": [], "new_bulls": [], "new_bears": [], "dropped": []}
    if len(snaps) == 1:
        return {"error": "only one snapshot yet — diff needs >=2", "today_date": snaps[0].stem,
                "flips": [], "new_bulls": [], "new_bears": [], "dropped": []}
    today_p, yest_p = snaps[-1], snaps[-2]
    try:
        today = json.loads(today_p.read_text())
        yest  = json.loads(yest_p.read_text())
    except Exception as e:
        return {"error": f"snapshot read failed: {e}", "flips": [], "new_bulls": [], "new_bears": [], "dropped": []}
    t_preds = (today.get("predictions") or {}).get(mode) or {}
    y_preds = (yest.get("predictions") or {}).get(mode) or {}

    def _side(p):
        if not isinstance(p, dict):
            return "NEUTRAL"
        edge = p.get("edge", 0.0)
        return "BULL" if edge > 0.02 else ("BEAR" if edge < -0.02 else "NEUTRAL")

    flips, new_bulls, new_bears = [], [], []
    dropped = list(set(y_preds.keys()) - set(t_preds.keys()))[:50]
    for sym, tp in t_preds.items():
        yp = y_preds.get(sym)
        t_side = _side(tp); y_side = _side(yp) if yp else None
        if y_side and y_side != t_side and (y_side != "NEUTRAL" or t_side != "NEUTRAL"):
            flips.append({
                "ticker": sym, "from": y_side, "to": t_side,
                "delta_q50": round((tp.get("q50", 0) - (yp.get("q50", 0) if yp else 0)), 2),
            })
        if not yp and t_side == "BULL":
            new_bulls.append({"ticker": sym, "q50": tp.get("q50", 0)})
        if not yp and t_side == "BEAR":
            new_bears.append({"ticker": sym, "q50": tp.get("q50", 0)})
    flips.sort(key=lambda x: -abs(x.get("delta_q50", 0)))
    new_bulls.sort(key=lambda x: -x["q50"])
    new_bears.sort(key=lambda x: x["q50"])
    return {
        "today_date":     today_p.stem,
        "yesterday_date": yest_p.stem,
        "n_today":        len(t_preds),
        "n_yesterday":    len(y_preds),
        "flips":          flips[:25],
        "new_bulls":      new_bulls[:15],
        "new_bears":      new_bears[:15],
        "dropped":        dropped[:25],
    }


@app.get("/api/ml-edge-drift")
async def ml_edge_drift_api(mode: str = "swing", days: int = 30):
    """30-day per-ticker stability scoring from cache/ml_edge_history/.

    For each ticker observed in any snapshot within `days`, count how many
    times its side (BULL/BEAR/NEUTRAL) flipped. Returns the top-25 most
    unstable + a global stability summary.
    """
    import json
    from pathlib import Path
    snap_dir = Path("cache/ml_edge_history")
    if not snap_dir.exists():
        return {"error": "no history", "tickers": []}
    snaps = sorted(snap_dir.glob("*.json"))
    if len(snaps) < 2:
        return {"error": "need >=2 snapshots", "tickers": [], "n_snapshots": len(snaps)}
    snaps = snaps[-days:]

    def _side(p):
        if not isinstance(p, dict): return "N"
        e = p.get("edge", 0.0)
        return "B" if e > 0.02 else ("S" if e < -0.02 else "N")

    series = {}  # ticker → list of side letters
    for sp in snaps:
        try:
            data = json.loads(sp.read_text())
        except Exception:
            continue
        preds = (data.get("predictions") or {}).get(mode) or {}
        for sym, p in preds.items():
            series.setdefault(sym, []).append(_side(p))
    out = []
    for sym, sides in series.items():
        if len(sides) < 2:
            continue
        flips = sum(1 for i in range(1, len(sides)) if sides[i] != sides[i-1])
        consistency = 1.0 - (flips / max(1, len(sides) - 1))
        out.append({
            "ticker": sym,
            "n_obs": len(sides),
            "flips": flips,
            "consistency": round(consistency, 3),
            "current": sides[-1],
            "history": "".join(sides[-15:]),
        })
    out.sort(key=lambda x: (-x["flips"], -x["n_obs"]))
    n_stable = sum(1 for r in out if r["consistency"] >= 0.85)
    return {
        "n_snapshots":  len(snaps),
        "n_tickers":    len(out),
        "n_stable":     n_stable,
        "n_unstable":   len(out) - n_stable,
        "tickers":      out[:25],
    }


@app.get("/api/ml-edge-track")
async def ml_edge_track_api(mode: str = "swing", limit: int = 200):
    """#1 · Read cache/ml_edge_picks_history.jsonl, aggregate resolved picks
    into the format the walk-forward equity curve needs. Replaces the proxy
    score-band aggregate with real ML-edge-attributed trades.
    """
    import json
    from pathlib import Path
    p = Path("cache/ml_edge_picks_history.jsonl")
    if not p.exists():
        return {"resolved": [], "pending": 0, "n_total": 0, "win_rate": None, "avg_r": None, "expectancy": None}
    resolved, pending = [], 0
    try:
        for ln in p.read_text().splitlines():
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if rec.get("mode") != mode:
                continue
            if rec.get("status") == "resolved":
                resolved.append(rec)
            else:
                pending += 1
    except Exception as e:
        return {"error": str(e), "resolved": [], "pending": 0}
    resolved = resolved[-limit:]
    if not resolved:
        return {"resolved": [], "pending": pending, "n_total": 0, "win_rate": None, "avg_r": None}
    wins = sum(1 for r in resolved if (r.get("realized_r") or 0) > 0)
    avg_r = sum((r.get("realized_r") or 0) for r in resolved) / len(resolved)
    # Profit factor = sum(wins R) / |sum(losses R)|
    gross_w = sum((r.get("realized_r") or 0) for r in resolved if (r.get("realized_r") or 0) > 0)
    gross_l = abs(sum((r.get("realized_r") or 0) for r in resolved if (r.get("realized_r") or 0) < 0)) or 0.001
    pf = gross_w / gross_l
    return {
        "resolved":  resolved,
        "pending":   pending,
        "n_total":   len(resolved),
        "win_rate":  round(wins / len(resolved) * 100, 1),
        "avg_r":     round(avg_r, 3),
        "profit_factor": round(pf, 2),
        "expectancy": round(avg_r, 3),
    }


@app.get("/api/calibration-history")
async def calibration_history_api(mode: str = "swing", days: int = 30):
    """Read last N days of calibration metrics for one mode. Powers
    the drift sparkline in the calibration card."""
    import json
    from pathlib import Path
    p = Path("cache/ml/calibration_history.jsonl")
    if not p.exists():
        return {"series": []}
    series = []
    try:
        for line in p.read_text().splitlines():
            try:
                rec = json.loads(line)
                if rec.get("mode") == mode:
                    series.append(rec)
            except Exception:
                continue
    except Exception as e:
        return {"error": str(e), "series": []}
    series = series[-days:]
    return {"series": series, "n": len(series)}


@app.get("/api/ml-edge-telemetry")
async def ml_edge_telemetry_api(limit: int = 30):
    """Read last N telemetry entries — wall time, EODHD calls, cache hit rate."""
    import json
    from pathlib import Path
    p = Path("cache/ml/telemetry.jsonl")
    if not p.exists():
        return {"entries": []}
    try:
        lines = p.read_text().splitlines()[-limit:]
        entries = []
        for ln in lines:
            try: entries.append(json.loads(ln))
            except Exception: pass
        return {"entries": entries, "n": len(entries)}
    except Exception as e:
        return {"error": str(e), "entries": []}


@app.get("/api/membership-snapshot")
async def membership_snapshot_api():
    """#2 · Survivorship — return today's S&P/R1000/R2000 membership snapshot
    so it can be written to data/membership/ as a point-in-time anchor.
    """
    try:
        sys.path.insert(0, str(BASE_DIR))
        from ml.universe_loader import _load_sp500, _load_r1000, _load_r2000
        return {
            "date":  datetime.now().strftime("%Y-%m-%d"),
            "sp500": sorted(_load_sp500()),
            "r1000": sorted(_load_r1000()),
            "r2000": sorted(_load_r2000()),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/ml-edge-stress-buckets")
async def stress_buckets_api():
    """#6 · Read cache/ml/stress_buckets.json — bucketed q10/25/50/75/90
    by scenario (base / spy_down / vix), one per mode. Powers the real
    stress overlay in the AI Prediction tab (replaces the heuristic)."""
    import json
    from pathlib import Path
    p = Path("cache/ml/stress_buckets.json")
    if not p.exists():
        return {"error": "stress_buckets.json not found. Run scripts/build_stress_buckets.py"}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/membership-history")
async def membership_history_api():
    """#2 · Report how many months of point-in-time membership we have for
    each index. Drives the survivorship indicator in the UI."""
    from pathlib import Path as _P
    mdir = _P("data/membership")
    if not mdir.exists():
        return {"sp500_months": 0, "r1000_months": 0, "r2000_months": 0, "haircut_pp": 3.0}
    counts = {"sp500": 0, "r1000": 0, "r2000": 0}
    for fp in mdir.glob("*.csv"):
        name = fp.stem
        if name.startswith("sp500_"):  counts["sp500"] += 1
        elif name.startswith("r1000_"): counts["r1000"] += 1
        elif name.startswith("r2000_"): counts["r2000"] += 1
    # Haircut shrinks as history accumulates (3pp until R1000+R2000 each have ≥24 months)
    months_min = min(counts["r1000"], counts["r2000"])
    if months_min >= 24:
        haircut = 0.5
    elif months_min >= 12:
        haircut = 1.5
    elif months_min >= 6:
        haircut = 2.5
    else:
        haircut = 3.0
    return {
        "sp500_months": counts["sp500"],
        "r1000_months": counts["r1000"],
        "r2000_months": counts["r2000"],
        "haircut_pp":   haircut,
    }


@app.get("/api/launchd-status")
async def launchd_status_api():
    """#23 · Detect whether the com.swingtrade.ml-edge launchd job is loaded.
    Returns {loaded, copy_cmd, load_cmd} for the UI install banner."""
    import subprocess
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=3)
        loaded = "com.swingtrade.ml-edge" in r.stdout
    except Exception:
        loaded = False
    return {
        "loaded": loaded,
        "copy_cmd": 'cp "/Volumes/MyMacDisk/Claude Skills/SwingTrade/infra/launchd/com.swingtrade.ml-edge.plist" ~/Library/LaunchAgents/com.swingtrade.ml-edge.plist',
        "load_cmd": 'launchctl load ~/Library/LaunchAgents/com.swingtrade.ml-edge.plist',
    }


@app.get("/api/vcp-pivots/{ticker}")
async def vcp_pivots_api(ticker: str):
    """Return detected VCP contraction pivots for a ticker · for hero chart overlay.
    Reads cache/tickers.json which holds the latest scan's per-ticker analysis output.
    """
    import json
    from pathlib import Path
    ticker = ticker.upper().strip()
    cache_path = Path("infra/prototype/tickers.json")
    if not cache_path.exists():
        cache_path = Path("cache/tickers.json")
    if not cache_path.exists():
        return {"ticker": ticker, "pivots": []}
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        tickers = data if isinstance(data, dict) else {}
        rec = tickers.get(ticker) or {}
        # Look for VCP-specific fields exposed by analysis._detect_vcp
        pivots = rec.get("vcp_pivots") or rec.get("contraction_zones") or []
        return {"ticker": ticker, "pivots": pivots, "stage": rec.get("vcp_stage"), "valid": bool(pivots)}
    except Exception as e:
        return {"ticker": ticker, "pivots": [], "error": str(e)}

# ─────────────────────────────────────────────────────────────────────
# 2026-05-19 · Live-price refresh for the Portfolio tab.
# Browser polls this every 5s with the list of held tickers and gets
# back current_price per ticker. Browser does the P&L math client-side
# (current_price * shares - cost_basis) so this endpoint stays a thin
# proxy.
#
# Source: Schwab Market Data /marketdata/v1/quotes via schwab_client.
# Market Data has its OWN rate-limit pool (~120/min) separate from
# EODHD's 100K/day budget — no quota competition with the daily scan.
# Trader API NOT required (which the user's Schwab dev app may not
# have enabled yet).
# ─────────────────────────────────────────────────────────────────────
@app.get("/api/portfolio/live_prices")
async def portfolio_live_prices(tickers: str = ""):
    """Return current Schwab Market Data quote per ticker.

    Query: ?tickers=NEM,AAPL,MSFT (comma-separated)
    Returns: {
      "ts": "2026-05-19T11:42:01Z",
      "source": "schwab.marketdata.v1",
      "elapsed_ms": 84,
      "prices": { "NEM": 105.81, "AAPL": 195.42, ... },
      "missing": []  # tickers we couldn't get quotes for
    }
    """
    import time as _t
    t0 = _t.time()
    syms = [s.strip().upper() for s in (tickers or "").split(",") if s.strip()]
    if not syms:
        return {"ts": datetime.now(timezone.utc).isoformat(),
                "source": "schwab.marketdata.v1",
                "elapsed_ms": 0, "prices": {}, "missing": []}

    try:
        import schwab_client
        blobs = schwab_client.get_quotes_batch(syms)
    except Exception as e:
        raise HTTPException(503, f"Schwab Market Data fetch failed: {e}")

    prices: dict[str, float] = {}
    missing: list[str] = []
    for sym in syms:
        blob = blobs.get(sym) or {}
        q = blob.get("quote") or {}
        px = q.get("lastPrice") or q.get("regularMarketLastPrice") or q.get("bidPrice")
        if px is None or not isinstance(px, (int, float)):
            missing.append(sym)
            continue
        prices[sym] = round(float(px), 4)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "schwab.marketdata.v1",
        "elapsed_ms": int((_t.time() - t0) * 1000),
        "prices": prices,
        "missing": missing,
    }


@app.post("/api/portfolio/add")
async def portfolio_add(req: Request, _: HTTPBasicCredentials = Depends(_require_action("submit_trade"))):
    body = await req.json()
    import portfolio_tracker as pt
    # 2026-05-19 · target1 is OPTIONAL (user-agency principle). Users may
    # enter at market with stop only and exit at their discretion.
    # portfolio_tracker.add_position uses `target1 and current >= target1`
    # so target1=0 naturally skips the auto-trim trigger.
    required = ["ticker", "entry", "shares", "stop"]
    missing = [k for k in required if k not in body]
    if missing:
        raise HTTPException(400, f"Missing fields: {', '.join(missing)}")
    try:
        _t1_raw = body.get("target1")
        try:
            _t1 = float(_t1_raw) if _t1_raw not in (None, "", 0, "0") else 0.0
        except (TypeError, ValueError):
            _t1 = 0.0
        pos = pt.add_position(
            ticker=str(body["ticker"]).upper(),
            entry_price=float(body["entry"]),
            shares=int(float(body["shares"])),
            stop=float(body["stop"]),
            target1=_t1,
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
    """Pull live Alpaca paper account → local portfolio_state.

    Thin wrapper around alpaca_sync.sync_alpaca_to_local() (single source of
    truth as of 2026-05-10). The module also handles filled-order
    reconciliation into closed_trades and SQLite mirror, which the old
    inline implementation didn't.
    """
    import json as _json
    from pathlib import Path as _Path
    from alpaca_sync import sync_alpaca_to_local
    try:
        result = sync_alpaca_to_local(force=True)
    except Exception as e:
        raise HTTPException(502, f"alpaca_sync failed: {e}")
    if not result.get("ok"):
        raise HTTPException(502, f"alpaca_sync error: {result.get('error') or result.get('skipped')}")

    # Re-load state to surface the fresh portfolio block for dashboard
    state = _json.loads((_Path("data/portfolio_state.json")).read_text())
    return {
        **result,
        "local_positions_after": len(state.get("positions", [])),
        "alpaca_positions": result.get("alpaca_position_count", 0),
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

# ──────────────────────────────────────────────────────────────────────────
# /api/trade_engine · structural target engine endpoint (hybrid pre-compute + on-demand)
# Pre-compute writes cache files for SP500+R1000+watchlist during nightly scan.
# On-demand falls through to live engine call (~2-5s) for tickers not in pre-compute.
# Both paths share the same cache file → unified surface.
#
# Path note: lives under /api/* (not /v2/*) because line 196 declares a
# /v2/{path:path} catch-all that serves prototype static files — it would
# intercept /v2/trade_engine before this handler could match.
# ──────────────────────────────────────────────────────────────────────────
@app.get("/api/trade_engine")
async def trade_engine(
    t: str,
    mode: str = "position",
    direction: str = "long",
    equity: float = 25000.0,
    refresh: int = 0,
    auth: HTTPBasicCredentials = Depends(_check_auth),
):
    """Returns §8 TradeAnalysis JSON for a ticker × mode.

    Hybrid:
    - First hit checks 12h-TTL cache file (populated by nightly pre-compute for scan universe)
    - On cache miss, computes live (~2-5s) and writes to same cache path
    - refresh=1 bypasses cache (force recompute)
    """
    if isinstance(auth, Response):
        return auth
    tk = (t or "").upper().strip()
    if not tk:
        raise HTTPException(400, "ticker required")
    if mode not in ("swing", "position", "invest"):
        raise HTTPException(400, "mode must be swing|position|invest")
    if direction not in ("long", "short"):
        raise HTTPException(400, "direction must be long|short")
    try:
        import target_engine as _te
        payload = _te.analyze_trade_cached(
            tk, direction=direction, mode=mode, equity=float(equity),
            force_refresh=bool(int(refresh)),
        )
        return JSONResponse(payload)
    except Exception as e:
        # Surface error so caller knows engine failed (vs returning bad data silently)
        raise HTTPException(500, f"engine_failure: {type(e).__name__}: {e}")


# ──────────────────────────────────────────────────────────────────────────
# /api/smc_bars · lazy intraday bar loader for SMC sub-tab.
# In-memory cache with 15-min TTL — keeps EODHD quota usage minimal:
# user only pays for tickers they actually click into.
# ──────────────────────────────────────────────────────────────────────────
_SMC_BARS_CACHE: dict = {}  # {(ticker, interval): (timestamp, payload)}
_SMC_BARS_TTL_SEC = 15 * 60  # 15 min

@app.get("/api/smc_bars")
async def smc_bars(
    t: str,
    interval: str = "1h",
    auth: HTTPBasicCredentials = Depends(_check_auth),
):
    """Return TV lightweight-charts-shaped OHLC for a ticker × interval.

    interval: "1h" (raw EODHD intraday) or "4h" (resampled from 1h).
    Cached 15 min in-memory so repeated clicks don't burn API.
    """
    if isinstance(auth, Response):
        return auth
    import time as _t
    tk = (t or "").upper().strip()
    if not tk:
        raise HTTPException(400, "ticker required")
    if interval not in ("1h", "4h"):
        raise HTTPException(400, "interval must be 1h|4h")

    cache_key = (tk, interval)
    now = _t.time()
    cached = _SMC_BARS_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _SMC_BARS_TTL_SEC:
        return JSONResponse(cached[1])

    try:
        import eodhd_client as _eod
        import pandas as _pd
        rows = _eod.intraday(tk, interval="1h")
        if not rows:
            payload = {"ticker": tk, "interval": interval, "bars": [], "source": "eodhd_empty"}
            _SMC_BARS_CACHE[cache_key] = (now, payload)
            return JSONResponse(payload)
        df = _pd.DataFrame(rows)
        ts_col = "datetime" if "datetime" in df.columns else "timestamp"
        if ts_col not in df.columns:
            raise HTTPException(502, "eodhd response missing datetime/timestamp column")
        df[ts_col] = _pd.to_datetime(df[ts_col])
        df = df.set_index(ts_col).sort_index()
        df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
        df = df[[c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]]

        if interval == "4h":
            df = df.resample("4h").agg({
                "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"
            }).dropna()
            tail_n = 120
        else:
            tail_n = 200

        df = df.tail(tail_n)
        bars = []
        for ix, row in df.iterrows():
            try:
                bars.append({
                    "time": int(ix.timestamp()),
                    "open":  round(float(row["Open"]),  2),
                    "high":  round(float(row["High"]),  2),
                    "low":   round(float(row["Low"]),   2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]) if "Volume" in row.index else 0,
                })
            except Exception:
                continue
        payload = {"ticker": tk, "interval": interval, "bars": bars, "source": "eodhd_live"}
        _SMC_BARS_CACHE[cache_key] = (now, payload)
        return JSONResponse(payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"smc_bars_failure: {type(e).__name__}: {e}")


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
    """Add ticker to watchlist (data/custom_tracked.json).

    2026-05-19 · Made idempotent: 'already tracked' returns HTTP 200 with
    {success: true, already_tracked: true} instead of 400. This kills the
    Chrome 'Failed to load resource' console noise on the WATCH button
    when a ticker is already in the list (the most common case). Other
    errors (price fetch failed, invalid ticker) still raise 400.
    """
    body = await req.json()
    from custom_tracker import add_custom_ticker
    ticker = str(body["ticker"]).upper()
    result = add_custom_ticker(ticker, str(body.get("note", "")))
    if not result.get("success"):
        err = (result.get("error") or "").lower()
        if "already" in err or "tracked" in err:
            # Idempotent — caller's intent ("this ticker should be on
            # the watchlist") is satisfied. Return 200 so the browser
            # doesn't log a console error.
            return {
                "success": True,
                "ticker": ticker,
                "already_tracked": True,
                "note": result.get("error"),
            }
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

# Legacy Anthropic-based /api/chat removed 2026-05-23 — superseded by
# the local-Ollama /api/chat at the bottom of this file (no paid API,
# wired to cache/last_bundle.json + kairos.html floating widget).


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

    # FAST-PATH (2026-05-04, perf-split 2026-05-25):
    # Try tickers_main.json (27MB · ~150ms parse · main-scan tickers) first.
    # Fall back to tickers_extras.json (70MB · lite-enriched extras) only if
    # ticker missing from main. Saves ~600ms parse stall per rebuild.
    # Legacy tickers.json kept as a final fallback for backwards compat.
    if not deep:
        if not hasattr(elite_detail_for_ticker, '_tj_main'):
            elite_detail_for_ticker._tj_main = {"ts": 0, "data": {}}
        if not hasattr(elite_detail_for_ticker, '_tj_extras'):
            elite_detail_for_ticker._tj_extras = {"ts": 0, "data": {}}
        proto_dir = BASE_DIR / "infra" / "prototype"
        main_path = proto_dir / "tickers_main.json"
        extras_path = proto_dir / "tickers_extras.json"
        legacy_path = proto_dir / "tickers.json"
        def _maybe_reload(path, slot):
            try:
                if path.exists():
                    m = path.stat().st_mtime
                    if m and m > slot["ts"]:
                        slot["data"] = json.loads(path.read_text())
                        slot["ts"] = m
            except Exception:
                pass
        _maybe_reload(main_path, elite_detail_for_ticker._tj_main)
        prebuilt = (elite_detail_for_ticker._tj_main.get("data") or {}).get(ticker)
        if not prebuilt:
            _maybe_reload(extras_path, elite_detail_for_ticker._tj_extras)
            prebuilt = (elite_detail_for_ticker._tj_extras.get("data") or {}).get(ticker)
        if not prebuilt:
            # Legacy fallback — only if neither split file has the ticker
            if not hasattr(elite_detail_for_ticker, '_tickers_json'):
                elite_detail_for_ticker._tickers_json = {"ts": 0, "data": {}}
            _maybe_reload(legacy_path, elite_detail_for_ticker._tickers_json)
            prebuilt = (elite_detail_for_ticker._tickers_json.get("data") or {}).get(ticker)
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
    """Financial events — IPOs / splits / secondary offerings.

    EODHD returns variable shapes:
      - list of events directly
      - dict with 'data' or 'events' key
      - dict keyed by ticker → list of events (rare)
    Normalize to a flat list. (2026-05-08 — fixed unhashable-slice crash.)
    """
    try:
        import eodhd_client as ec, datetime as _dt
        today = _dt.date.today()
        end = today + _dt.timedelta(days=days_ahead)
        raw = ec.financial_events(from_date=today.isoformat(), to_date=end.isoformat(), event_type=event_type)
        # Normalize to a flat list
        if raw is None:
            events = []
        elif isinstance(raw, list):
            events = raw
        elif isinstance(raw, dict):
            events = raw.get("data") or raw.get("events") or raw.get("ipos") or raw.get("splits") or []
            if not isinstance(events, list):
                events = []
        else:
            events = []
        return {"event_type": event_type, "events": events[:50],
                "count": len(events),
                "from": today.isoformat(), "to": end.isoformat()}
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

# 2026-05-15 · Schwab auth-health probe. Used by the dashboard topbar banner
# so users see "🔑 Re-auth Schwab" the moment options/quotes start failing,
# rather than discovering it hours later via stale UI. Reads:
#   1) SCHWAB_REFRESH_ISSUED_AT in .env  (token age)
#   2) cache/logs/schwab_token_check.log (last cron probe result)
# No network calls — purely a local-state read, safe to poll every 60s.
@app.get("/api/schwab/health")
async def schwab_health():
    import os, time, re
    from pathlib import Path as _P
    out = {"ok": False, "token_age_days": None, "last_check_ts": None,
           "last_check_status": "unknown", "message": "", "reauth_cmd":
           "cd \"/Volumes/MyMacDisk/Claude Skills/SwingTrade\" && python3 schwab_auth.py oauth"}

    # 1 · Refresh token age — ALWAYS prefer .env (cron writes there on rotate;
    # server's os.environ snapshot from startup goes stale within hours).
    # Fall back to os.environ only when .env unreadable.
    issued = None
    try:
        env_path = _P(__file__).resolve().parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("SCHWAB_REFRESH_ISSUED_AT="):
                    issued = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass
    if not issued:
        issued = os.environ.get("SCHWAB_REFRESH_ISSUED_AT")
    if issued:
        try:
            out["token_age_days"] = round((time.time() - float(issued)) / 86400, 2)
        except (TypeError, ValueError):
            pass

    # 2 · Last cron probe (tail the log for the most recent line)
    log_path = _P(__file__).resolve().parent / "cache" / "logs" / "schwab_token_check.log"
    if log_path.exists():
        try:
            text = log_path.read_text()
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if lines:
                last = lines[-1]
                ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", last)
                if ts_match:
                    import datetime as _dt
                    try:
                        out["last_check_ts"] = _dt.datetime.strptime(
                            ts_match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                    except Exception:
                        pass
                if "ERROR" in last or "CRITICAL" in last or "FAILED" in last or "rejected" in last.lower():
                    out["last_check_status"] = "failed"
                    # Surface the first meaningful sentence (skip the emoji)
                    out["message"] = re.sub(r"^.*?:\s*", "", last)[:240]
                elif "SUCCESS" in last or "OK" in last or "✓" in last:
                    out["last_check_status"] = "ok"
                else:
                    out["last_check_status"] = "unknown"
        except Exception as e:
            out["message"] = f"log read error: {e}"

    # 3 · Derive overall OK flag — green if last cron probe ok AND token age <7d
    if out["last_check_status"] == "ok" and (out["token_age_days"] is None or out["token_age_days"] < 7):
        out["ok"] = True
    elif out["last_check_status"] == "failed":
        out["ok"] = False
    elif out["token_age_days"] is not None and out["token_age_days"] >= 7:
        out["ok"] = False
        out["message"] = f"Token is {out['token_age_days']:.1f} days old · Schwab rotates every 7 days"
    return out

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
@app.get("/api/universe/watchlist")
async def universe_get():
    """Return the user's custom watchlist from config.universe.custom_watchlist."""
    cfg_path = BASE_DIR / "config" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        wl = cfg.get("universe", {}).get("custom_watchlist", [])
        return {"watchlist": wl, "count": len(wl)}
    except Exception as e:
        return {"watchlist": [], "count": 0, "error": str(e)}


@app.post("/api/universe/remove")
async def universe_remove(req: Request):
    """Remove a ticker from the custom watchlist."""
    body = await req.json()
    ticker = str(body.get("ticker", "")).upper()
    if not ticker:
        raise HTTPException(400, "Missing ticker")
    cfg_path = BASE_DIR / "config" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        wl = cfg.setdefault("universe", {}).setdefault("custom_watchlist", [])
        if ticker in wl:
            wl.remove(ticker)
            cfg_path.write_text(json.dumps(cfg, indent=2))
            return {"ok": True, "message": f"{ticker} removed", "watchlist": wl}
        return {"ok": True, "message": f"{ticker} not in watchlist"}
    except Exception as e:
        raise HTTPException(500, str(e))


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

# -- Earnings prediction history (joined log with realized outcomes) --
@app.get("/api/earnings/prediction-log")
async def earnings_prediction_log_api(auth: HTTPBasicCredentials = Depends(_check_auth)):
    import json
    from pathlib import Path
    log_path = Path(__file__).resolve().parent / "data" / "earnings_prediction_log.jsonl"
    if not log_path.exists():
        return {"total": 0, "rows": []}
    rows = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    rows.sort(key=lambda r: (r.get("report_date") or ""), reverse=True)
    return {"total": len(rows), "rows": rows}

# -- Options Flow Scanner — REMOVED 2026-04-25 (no options data in EODHD plan) --
@app.get("/api/options-flow")
async def options_flow_api():
    return {"total": 0, "results": [], "error": "options data removed; not in EODHD All-In-One"}


@app.get("/api/iv-history")
async def iv_history_api(t: str, days: int = 90):
    """Return per-ticker IV history from data/iv_history.jsonl for the Earnings tab's IV-crush chart."""
    from datetime import datetime, timedelta
    iv_path = BASE_DIR / "data" / "iv_history.jsonl"
    if not iv_path.exists():
        return {"ticker": t.upper(), "points": [], "error": "no iv_history file"}
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    tk = t.upper().strip()
    pts = []
    for line in iv_path.read_text().splitlines():
        if not line.strip(): continue
        try:
            r = json.loads(line)
            if (r.get("ticker") or "").upper() != tk: continue
            d = (r.get("date") or "")[:10]
            if d < cutoff: continue
            iv = r.get("current_iv") or r.get("iv_percentile")
            if iv is None: continue
            pts.append({"date": d, "iv": float(iv)})
        except Exception:
            continue
    pts.sort(key=lambda x: x.get("date") or "")
    return {"ticker": tk, "points": pts, "count": len(pts)}


@app.get("/api/options-flow-accuracy")
async def options_flow_accuracy_api(window_days: int = 90):
    """Projection accuracy summary for the daily Options Flow snapshots.

    Reads cache/options_flow_outcomes.jsonl (populated by
    scripts/options_flow_outcomes.py nightly) and aggregates:
      - total picks in window
      - WR (target_hit / resolved)
      - PF (sum of winners / sum of losers, absolute realized returns)
      - per-status breakdown (STRONG / MODERATE / WEAK)
      - avg MFE / MAE
      - target_hit rate vs expired vs stop_hit
    """
    hist_path = BASE_DIR / "cache" / "options_flow_history.jsonl"
    out_path = BASE_DIR / "cache" / "options_flow_outcomes.jsonl"
    history_total = 0
    if hist_path.exists():
        history_total = sum(1 for _ in hist_path.read_text().splitlines() if _.strip())
    if not out_path.exists():
        return {
            "window_days": window_days,
            "history_total": history_total,
            "resolved": 0,
            "message": "no resolved outcomes yet — run scripts/options_flow_outcomes.py "
                       "(needs ≥7 days of history before any pick resolves)"
        }
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    rows = []
    for line in out_path.read_text().splitlines():
        if not line.strip(): continue
        try:
            r = json.loads(line)
            if (r.get("snap_date") or "") < cutoff: continue
            rows.append(r)
        except Exception:
            continue
    if not rows:
        return {
            "window_days": window_days,
            "history_total": history_total,
            "resolved": 0,
            "message": f"no resolved outcomes in last {window_days} days"
        }
    # Aggregates
    resolved = [r for r in rows if r.get("outcome") in ("target_hit", "stop_hit", "expired")]
    open_n = sum(1 for r in rows if r.get("outcome") == "open")
    target_hit = sum(1 for r in resolved if r.get("outcome") == "target_hit")
    stop_hit = sum(1 for r in resolved if r.get("outcome") == "stop_hit")
    expired = sum(1 for r in resolved if r.get("outcome") == "expired")
    wins = [r.get("realized_return_pct") for r in resolved
            if r.get("outcome") == "target_hit" and isinstance(r.get("realized_return_pct"), (int, float))]
    losses = [r.get("realized_return_pct") for r in resolved
              if r.get("outcome") == "stop_hit" and isinstance(r.get("realized_return_pct"), (int, float))]
    wr = (target_hit / len(resolved) * 100) if resolved else None
    total_win_pct = sum(w for w in wins if w > 0)
    total_loss_pct = abs(sum(l for l in losses if l < 0))
    pf = (total_win_pct / total_loss_pct) if total_loss_pct > 0 else None
    avg_mfe = sum(r.get("mfe_pct") or 0 for r in resolved) / len(resolved) if resolved else 0
    avg_mae = sum(r.get("mae_pct") or 0 for r in resolved) / len(resolved) if resolved else 0
    avg_realized = sum(r.get("realized_return_pct") or 0 for r in resolved) / len(resolved) if resolved else 0
    # Per-status breakdown
    from collections import defaultdict
    per_status = defaultdict(lambda: {"n": 0, "wins": 0, "expired": 0, "stops": 0})
    for r in resolved:
        st = r.get("status") or "UNKNOWN"
        per_status[st]["n"] += 1
        if r.get("outcome") == "target_hit":  per_status[st]["wins"] += 1
        elif r.get("outcome") == "stop_hit":  per_status[st]["stops"] += 1
        elif r.get("outcome") == "expired":   per_status[st]["expired"] += 1
    # Most recent resolved picks (table view)
    recent = sorted(resolved, key=lambda r: r.get("snap_date") or "", reverse=True)[:10]
    return {
        "window_days": window_days,
        "history_total": history_total,
        "open_count": open_n,
        "resolved": len(resolved),
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "expired": expired,
        "win_rate_pct": round(wr, 1) if wr is not None else None,
        "profit_factor": round(pf, 2) if pf is not None else None,
        "avg_realized_return_pct": round(avg_realized, 2),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_mae_pct": round(avg_mae, 2),
        "per_status": dict(per_status),
        "recent_resolved": recent,
    }

@app.get("/api/options-flow-journal")
async def options_flow_journal_api(days: int = 90, limit: int = 200,
                                    status: str = "", outcome: str = "",
                                    include_backfill: bool = False,
                                    source: str = ""):
    """Per-pick journal joining options_flow_history.jsonl with outcomes.

    Returns rows for the History sub-section: most-recent first, optional
    filter by status (STRONG/MODERATE/WEAK) or outcome (target_hit/stop_hit/
    expired/open). Outcome is 'pending' when not yet in the outcomes file.

    When include_backfill=true, also merges resolved trades from
    cache/picks_history.json as 'general_picks' source (real win/loss
    outcomes from the main SwingTrade scanner — gives 1.5+ months of
    track record while options-flow logger accumulates depth).

    source filter: 'options_flow' | 'general_picks' | '' (both)
    """
    hist_path = BASE_DIR / "cache" / "options_flow_history.jsonl"
    out_path = BASE_DIR / "cache" / "options_flow_outcomes.jsonl"
    if not hist_path.exists():
        return {"rows": [], "total": 0, "summary": {}, "coverage": {}, "message": "no history yet"}
    # Coverage — earliest/latest dates in the raw history (independent of filters).
    # User wants 1y track but logger started recently; surface the gap honestly.
    coverage = {"earliest": None, "latest": None, "days_logged": 0, "total_picks": 0}
    try:
        _dates = set()
        _ncov = 0
        for _ln in hist_path.read_text().splitlines():
            if not _ln.strip(): continue
            try:
                _d = json.loads(_ln).get("snap_date")
                if _d:
                    _dates.add(_d)
                    _ncov += 1
            except Exception:
                continue
        if _dates:
            coverage["earliest"] = min(_dates)
            coverage["latest"] = max(_dates)
            coverage["days_logged"] = len(_dates)
            coverage["total_picks"] = _ncov
    except Exception:
        pass
    # Build outcome index keyed by (snap_date, ticker)
    outcomes = {}
    if out_path.exists():
        for ln in out_path.read_text().splitlines():
            if not ln.strip(): continue
            try:
                r = json.loads(ln)
                outcomes[(r.get("snap_date"), r.get("ticker"))] = r
            except Exception:
                continue
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    # Dedupe by (snap_date, ticker) — scanner appends every 30 min, so one
    # ticker on one day can have 48 duplicate rows. Keep highest snap_ts.
    history_by_key = {}
    for ln in hist_path.read_text().splitlines():
        if not ln.strip(): continue
        try:
            h = json.loads(ln)
        except Exception:
            continue
        if (h.get("snap_date") or "") < cutoff: continue
        key = (h.get("snap_date"), h.get("ticker"))
        prev = history_by_key.get(key)
        if prev is None or (h.get("snap_ts") or 0) > (prev.get("snap_ts") or 0):
            history_by_key[key] = h
    rows = []
    for h in history_by_key.values():
        st = h.get("status") or ""
        if status and st.upper() != status.upper(): continue
        oc = outcomes.get((h.get("snap_date"), h.get("ticker")))
        outcome_val = (oc.get("outcome") if oc else None) or "pending"
        if outcome and outcome_val.lower() != outcome.lower(): continue
        # Direction inferred from P/C ratio: <1 = call-heavy (long), >1 = put-heavy (short bias)
        pc = h.get("put_call_ratio")
        _dir = "short" if (pc is not None and pc > 1.0) else "long"
        rows.append({
            "date": h.get("snap_date"),
            "ticker": h.get("ticker"),
            "sector": h.get("sector"),
            "status": st,
            "direction": _dir,
            "entry": h.get("price"),
            "exit_price": (oc or {}).get("exit_price"),
            "target": h.get("target"),
            "stop": h.get("stop"),
            "rr": h.get("rr"),
            "pc_ratio": pc,
            "iv_pct": h.get("iv_percentile"),
            "max_pain": h.get("max_pain"),
            "outcome": outcome_val,
            "win": (oc or {}).get("outcome") == "target_hit" if oc else None,
            "realized_pct": (oc or {}).get("realized_return_pct"),
            "realized_r": (oc or {}).get("realized_r"),
            "mfe_pct": (oc or {}).get("mfe_pct"),
            "mae_pct": (oc or {}).get("mae_pct"),
            "days_held": (oc or {}).get("days_to_outcome"),
            "exit_date": (oc or {}).get("exit_date"),
            "source": "options_flow",
        })

    # ─── Optional backfill from main picks_history.json ──────────────
    backfill_n = 0
    if include_backfill:
        ph_path = BASE_DIR / "cache" / "picks_history.json"
        if ph_path.exists():
            try:
                ph = json.loads(ph_path.read_text())
                for tr in ph.get("trades", []) or []:
                    d_str = tr.get("entry_date") or tr.get("run_date") or ""
                    if not d_str or d_str < cutoff: continue
                    # Map trade outcome → journal outcome
                    win = tr.get("win")
                    pnl = tr.get("pnl_pct") if tr.get("pnl_pct") is not None else tr.get("pct_chg")
                    if win is True:    oc_val = "target_hit"
                    elif win is False: oc_val = "stop_hit"
                    else:              oc_val = "expired"
                    # Setup family → status proxy (so the badge column has meaning)
                    sfam = (tr.get("setup_family") or tr.get("setup_type") or "").upper()
                    if sfam in ("IMPULSE CATALYST", "BREAKOUT EXPANSION", "52WK BREAKOUT", "VCP BREAKOUT"):
                        st_proxy = "STRONG"
                    elif sfam in ("TREND CONTINUATION", "EMA21 PULLBACK", "SQUEEZE EXPANSION"):
                        st_proxy = "MODERATE"
                    else:
                        st_proxy = "WEAK"
                    if status and st_proxy != status.upper(): continue
                    if outcome and oc_val.lower() != outcome.lower(): continue
                    if source and source.lower() != "general_picks": continue
                    rr = tr.get("rr_ratio")
                    entry = tr.get("entry_price")
                    exit_px = tr.get("exit_price")
                    rows.append({
                        "date": d_str,
                        "ticker": tr.get("ticker"),
                        "sector": tr.get("sector") or "",
                        "status": st_proxy,
                        "direction": tr.get("direction") or "long",
                        "entry": entry,
                        "exit_price": exit_px,
                        "target": (entry * (1 + (pnl or 0)/100)) if (oc_val == "target_hit" and entry and pnl) else None,
                        "stop": entry - tr.get("planned_risk") if (entry and tr.get("planned_risk")) else None,
                        "rr": rr,
                        "pc_ratio": None,
                        "iv_pct": None,
                        "max_pain": None,
                        "outcome": oc_val,
                        "win": tr.get("win"),
                        "realized_pct": pnl,
                        "realized_r": tr.get("realized_r"),
                        "mfe_pct": tr.get("mfe_pct") if tr.get("mfe_pct") is not None else tr.get("mfe"),
                        "mae_pct": tr.get("mae_pct") if tr.get("mae_pct") is not None else tr.get("mae"),
                        "days_held": tr.get("hold_days"),
                        "exit_date": tr.get("exit_date"),
                        "source": "general_picks",
                        "setup": tr.get("setup_family") or tr.get("setup_type"),
                    })
                    backfill_n += 1
            except Exception:
                pass

    # source filter on options_flow rows already applied implicitly; honor it here too
    if source:
        rows = [r for r in rows if r.get("source", "").lower() == source.lower()]
    # Sort newest first, then limit
    rows.sort(key=lambda r: (r["date"] or ""), reverse=True)
    rows = rows[:limit]
    # Summary across the filtered set
    total = len(rows)
    by_outcome = {"target_hit": 0, "stop_hit": 0, "expired": 0, "pending": 0}
    win_returns = []
    loss_returns = []
    for r in rows:
        oc = r["outcome"]
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
        rr_pct = r.get("realized_pct")
        if isinstance(rr_pct, (int, float)):
            if oc == "target_hit": win_returns.append(rr_pct)
            elif oc == "stop_hit": loss_returns.append(rr_pct)
    resolved = total - by_outcome["pending"]
    wr = (by_outcome["target_hit"] / resolved * 100) if resolved > 0 else None
    avg_win = sum(win_returns) / len(win_returns) if win_returns else 0
    avg_loss = sum(loss_returns) / len(loss_returns) if loss_returns else 0
    return {
        "rows": rows,
        "total": total,
        "summary": {
            "resolved": resolved,
            "open": by_outcome["pending"],
            "wins": by_outcome["target_hit"],
            "losses": by_outcome["stop_hit"],
            "expired": by_outcome["expired"],
            "win_rate_pct": round(wr, 1) if wr is not None else None,
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
        },
        "coverage": coverage,
        "backfill_count": backfill_n,
        "filters": {"days": days, "status": status, "outcome": outcome,
                    "limit": limit, "include_backfill": include_backfill, "source": source},
    }


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
async def api_update_role(role_id: str, payload: dict, request: Request,
                           credentials: HTTPBasicCredentials = Depends(_require_admin)):
    if isinstance(credentials, Response):
        return credentials
    # CapStudio audit (2026-05-09): snapshot the role's permissions BEFORE
    # the change so the log records the exact diff.
    try:
        before = (_auth_mod.get_role(role_id) or {}).get("permissions") or {}
    except Exception:
        before = {}
    try:
        r = _auth_mod.update_role(role_id, **payload)
        # Emit to the existing audit log (data/audit_log.jsonl)
        try:
            import audit_log as _alog
            _alog.log_action(
                user=credentials.username, action="capstudio_edit_role",
                endpoint=request.url.path, method="PATCH",
                ip=(request.client.host if request.client else ""),
                user_agent=request.headers.get("user-agent", ""),
                status="ok",
                payload={"role_id": role_id, "before": before, "after": (payload.get("permissions") or {})},
            )
        except Exception as _e:
            pass
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


# =========================================================================
# /api/performance — live performance metrics computed from signal_log.json
# Re-reads the trade journal on demand and re-computes WR/PF/Wilson LB.
# 15s cache to absorb burst polls. Used by Performance tab 60s poller.
# =========================================================================
_PERF_LIVE_CACHE: dict = {"ts": 0.0, "mtime": 0.0, "payload": None}
_PERF_LIVE_TTL_S = 15.0


def _compute_perf_live() -> dict:
    """Re-read signal_log.json and recompute performance — never cached past TTL."""
    from collections import Counter
    SIGNAL_LOG = BASE_DIR / "data" / "signal_log.json"
    out = {
        "total": 0, "open": 0, "closed": 0, "wins": 0, "losses": 0,
        "breakeven": 0, "win_rate": None, "wilson_lb_pct": None,
        "pf": None, "avg_r": None, "expectancy": None,
        "avg_win_pct": None, "avg_loss_pct": None, "rr_avg": None,
        "mae_avg": None, "mfe_avg": None,
        "by_strategy": {}, "by_score_bucket": {},
        "by_verdict": {}, "today_count": 0,
        "recent_closed": [], "fresh_today": [],
        "computed_at": None,
        "source_mtime": None,
    }
    if not SIGNAL_LOG.exists():
        return out
    try:
        sl = json.loads(SIGNAL_LOG.read_text())
    except Exception:
        return out
    if not isinstance(sl, list) or not sl:
        return out

    out["source_mtime"] = SIGNAL_LOG.stat().st_mtime
    out["computed_at"] = _time.time()
    out["total"] = len(sl)
    out["open"] = sum(1 for r in sl if r.get("status") == "OPEN")

    # Closed = status CLOSED · win/loss by `result` field (canonical schema)
    done = [r for r in sl if r.get("status") == "CLOSED"]
    out["closed"] = len(done)
    win_results  = ("WIN_EXPIRED", "TARGET_HIT", "WIN")
    loss_results = ("LOSS_EXPIRED", "STOPPED", "LOSS")
    out["wins"]   = sum(1 for r in done if r.get("result") in win_results)
    out["losses"] = sum(1 for r in done if r.get("result") in loss_results)
    out["breakeven"] = out["closed"] - out["wins"] - out["losses"]
    decided = out["wins"] + out["losses"]
    if decided > 0:
        out["win_rate"] = round(out["wins"] / decided * 100, 1)
        try:
            from math import sqrt
            z, n = 1.96, decided
            p = out["wins"] / n
            denom = 1 + z * z / n
            center = p + z * z / (2 * n)
            margin = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n)
            out["wilson_lb_pct"] = round(max(0.0, (center - margin) / denom) * 100, 1)
        except Exception:
            pass

    # PF, avg R, MAE/MFE — use actual_pnl_pct (canonical) for realized P&L%
    win_pcts  = [r.get("actual_pnl_pct") for r in done
                 if r.get("result") in win_results
                 and isinstance(r.get("actual_pnl_pct"), (int, float))]
    loss_pcts = [r.get("actual_pnl_pct") for r in done
                 if r.get("result") in loss_results
                 and isinstance(r.get("actual_pnl_pct"), (int, float))]
    if win_pcts:
        out["avg_win_pct"] = round(sum(win_pcts) / len(win_pcts), 2)
    if loss_pcts:
        out["avg_loss_pct"] = round(sum(loss_pcts) / len(loss_pcts), 2)
    if win_pcts and loss_pcts:
        gross_w = sum(win_pcts)
        gross_l = abs(sum(loss_pcts))
        out["pf"] = round(gross_w / gross_l, 2) if gross_l > 0 else None
    rr_vals = [r.get("rr") for r in sl if isinstance(r.get("rr"), (int, float))]
    if rr_vals:
        out["rr_avg"] = round(sum(rr_vals) / len(rr_vals), 2)
    mae_vals = [r.get("mae_pct") for r in sl if isinstance(r.get("mae_pct"), (int, float))]
    if mae_vals:
        out["mae_avg"] = round(sum(mae_vals) / len(mae_vals), 2)
    mfe_vals = [r.get("mfe_pct") for r in sl if isinstance(r.get("mfe_pct"), (int, float))]
    if mfe_vals:
        out["mfe_avg"] = round(sum(mfe_vals) / len(mfe_vals), 2)
    # Avg R = mean(realized% / risk%) where risk = entry - stop
    r_units = []
    for r in done:
        pnl = r.get("actual_pnl_pct")
        ep, sp = r.get("entry_price"), r.get("stop")
        if all(isinstance(x, (int, float)) for x in (pnl, ep, sp)) and ep and sp and ep > 0:
            risk_pct = abs((ep - sp) / ep * 100)
            if risk_pct > 0.0001:
                r_units.append(pnl / risk_pct)
    if r_units:
        out["avg_r"] = round(sum(r_units) / len(r_units), 2)
        out["expectancy"] = out["avg_r"]

    # By strategy / score bucket / verdict
    by_strat = Counter()
    by_bucket = Counter()
    by_verdict = Counter()
    for r in sl:
        s = r.get("strategy")
        if s:
            by_strat[s] += 1
        sc = r.get("score") or 0
        bucket = "90+" if sc >= 90 else "80-89" if sc >= 80 else "70-79" if sc >= 70 else "60-69" if sc >= 60 else "<60"
        by_bucket[bucket] += 1
        v = r.get("verdict") or r.get("decision_label")
        if v:
            by_verdict[v] += 1
    out["by_strategy"] = dict(by_strat.most_common())
    out["by_score_bucket"] = dict(by_bucket)
    out["by_verdict"] = dict(by_verdict)

    # Today's count
    from datetime import datetime as _dt
    today_str = _dt.now().strftime("%Y-%m-%d")
    out["today_count"] = sum(1 for r in sl if str(r.get("date") or "").startswith(today_str))

    # Recent 25 closed trades for the live journal
    closed_sorted = sorted(
        done,
        key=lambda r: r.get("exit_date") or r.get("date") or "",
        reverse=True,
    )[:25]
    out["recent_closed"] = [
        {
            "ticker": r.get("ticker"),
            "strategy": r.get("strategy"),
            "date": r.get("date"),
            "exit_date": r.get("exit_date"),
            "score": r.get("score"),
            "rr": r.get("rr"),
            "realized_pct": r.get("actual_pnl_pct"),
            "outcome": r.get("result"),
            "exit_reason": r.get("exit_reason"),
            "hold_days": r.get("hold_days"),
        }
        for r in closed_sorted
    ]

    # Today's fresh signals (open or fresh entries)
    today_rows = [r for r in sl if str(r.get("date") or "").startswith(today_str)]
    out["fresh_today"] = [
        {
            "ticker": r.get("ticker"),
            "strategy": r.get("strategy"),
            "score": r.get("score"),
            "verdict": r.get("verdict") or r.get("decision_label"),
            "rr": r.get("rr"),
            "entry_price": r.get("entry_price"),
            "stop": r.get("stop"),
            "target1": r.get("target1"),
            "status": r.get("status"),
        }
        for r in today_rows[:50]
    ]

    return out


@app.get("/api/performance")
async def performance_live():
    """Live performance from signal_log.json. 15s cache, file-mtime invalidates."""
    SIGNAL_LOG = BASE_DIR / "data" / "signal_log.json"
    mtime = SIGNAL_LOG.stat().st_mtime if SIGNAL_LOG.exists() else 0.0
    now = _time.time()
    if (_PERF_LIVE_CACHE["payload"] is not None
            and _PERF_LIVE_CACHE["mtime"] == mtime
            and (now - _PERF_LIVE_CACHE["ts"]) < _PERF_LIVE_TTL_S):
        return JSONResponse(_PERF_LIVE_CACHE["payload"])
    payload = _compute_perf_live()
    _PERF_LIVE_CACHE.update({"ts": now, "mtime": mtime, "payload": payload})
    return JSONResponse(payload)


# =========================================================================
# /api/supabase/status — powers the Supabase tab in kairos.html
# =========================================================================
_SUPABASE_STATUS_CACHE: dict = {"ts": 0.0, "payload": None}
_SUPABASE_STATUS_TTL_S = 30.0


@app.get("/api/supabase/status")
async def supabase_status():
    """Return Supabase health + per-table local/remote row counts + last-sync ledger.

    Cached 30s so the dashboard tab is fast even on refresh-spam.
    """
    import time as _t
    now = _t.time()
    if _SUPABASE_STATUS_CACHE["payload"] is not None and (now - _SUPABASE_STATUS_CACHE["ts"]) < _SUPABASE_STATUS_TTL_S:
        return _SUPABASE_STATUS_CACHE["payload"]

    from pathlib import Path as _P
    import json as _j
    import sqlite3 as _sq
    import os as _o

    root = _P(__file__).parent
    state_path = root / "data" / "supabase_sync_state.json"
    db_path = root / "data" / "swingtrade.db"

    # Sync ledger (written by migrate_sqlite_to_supabase.py)
    ledger: dict = {}
    last_full_sync = None
    if state_path.exists():
        try:
            j = _j.loads(state_path.read_text())
            ledger = j.get("tables") or {}
            last_full_sync = j.get("_last_full_sync")
        except Exception:
            pass

    # Supabase healthcheck + URL
    try:
        from supabase_client import healthcheck as _hc, sb_client, supabase_mode
        _t0 = _t.time()
        hc = _hc()
        ping_ms = int((_t.time() - _t0) * 1000)
        sb = sb_client()
        mode = supabase_mode()
    except Exception as e:
        hc = {"ok": False, "error": f"import failed: {e}", "url": None}
        ping_ms = 0
        sb = None
        mode = 0

    # All tables we sync — grouped by cluster for the dashboard
    sync_tables = [
        # Core trade journal + portfolio
        "meta", "portfolio_state", "positions", "closed_trades", "equity_audit",
        "monthly_pnl", "equity_curve", "signal_log", "runs", "picks", "trades",
        "watch_triggers", "custom_tickers", "alert_log", "scan_health",
        "gap_events", "paper_trading_config",
        # Signal-filter audit (003)
        "signal_filter_decisions",
        # Backtest (002)
        "backtest_runs", "backtest_trades", "walk_forward_folds",
        # Orphan-store folds (006)
        "decision_log", "exit_signals", "earnings_outcomes", "iv_history",
        "orders", "eod_actions", "regime_history", "regime_transitions",
        "rolling_sharpe_history", "smc_hit_rates", "fundamentals_pit",
        "ticker_enrichment_snapshot",
        # Analytical / risk (007)
        "position_risk_snapshot", "portfolio_risk_history", "kelly_size_history",
        "wilson_ci_snapshot", "model_predictions", "model_calibration",
        "strategy_pnl_attribution", "stop_levels_history", "slippage_realized",
        "var_breaches",
        # Free-data catalysts (008)
        "tickers_master", "index_membership_pit", "corporate_actions",
        "ohlcv_daily", "macro_indicators", "insider_transactions",
        "institutional_holdings", "short_interest_history", "news_events",
        "congressional_trades", "fomc_calendar", "economic_calendar",
        "ipo_calendar", "splits_calendar", "fda_calendar",
        "earnings_calendar_pit",
        # Ops telemetry (009)
        "eodhd_quota_usage", "launchd_runs", "data_quality_checks",
        "config_history", "feature_flag_changes", "api_latency_metrics",
        "user_audit_log",
        # Sync ledger (004)
        "supabase_sync_state",
    ]

    # Local (SQLite) counts
    local_counts: dict[str, int] = {}
    if db_path.exists():
        try:
            conn = _sq.connect(str(db_path))
            for t in sync_tables:
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    local_counts[t] = int(n)
                except Exception:
                    local_counts[t] = 0
            conn.close()
        except Exception:
            pass

    # Remote (Supabase) counts via HEAD-count
    remote_counts: dict[str, int | None] = {}
    if sb is not None and hc.get("ok"):
        for t in sync_tables:
            try:
                resp = sb.table(t).select("*", count="exact", head=True).execute()
                remote_counts[t] = getattr(resp, "count", None)
            except Exception:
                remote_counts[t] = None
    else:
        remote_counts = {t: None for t in sync_tables}

    # Cluster mapping for grouped display
    _cluster_of = {
        "meta": "system", "portfolio_state": "portfolio", "positions": "portfolio",
        "closed_trades": "portfolio", "equity_audit": "portfolio",
        "monthly_pnl": "portfolio", "equity_curve": "portfolio",
        "signal_log": "journal", "runs": "scan", "picks": "scan", "trades": "scan",
        "watch_triggers": "watchlist", "custom_tickers": "watchlist",
        "alert_log": "watchlist",
        "scan_health": "health", "gap_events": "health",
        "paper_trading_config": "system",
        "signal_filter_decisions": "journal",
        "backtest_runs": "backtest", "backtest_trades": "backtest",
        "walk_forward_folds": "backtest",
        "decision_log": "journal", "exit_signals": "journal",
        "earnings_outcomes": "earnings", "iv_history": "derivatives",
        "orders": "execution", "eod_actions": "execution",
        "regime_history": "regime", "regime_transitions": "regime",
        "rolling_sharpe_history": "risk", "smc_hit_rates": "calibration",
        "fundamentals_pit": "fundamentals",
        "ticker_enrichment_snapshot": "enrichment",
        "position_risk_snapshot": "risk", "portfolio_risk_history": "risk",
        "kelly_size_history": "risk", "wilson_ci_snapshot": "calibration",
        "model_predictions": "ml", "model_calibration": "ml",
        "strategy_pnl_attribution": "attribution",
        "stop_levels_history": "execution",
        "slippage_realized": "execution", "var_breaches": "risk",
        "tickers_master": "reference", "index_membership_pit": "reference",
        "corporate_actions": "reference", "ohlcv_daily": "market_data",
        "macro_indicators": "regime",
        "insider_transactions": "smart_money",
        "institutional_holdings": "smart_money",
        "short_interest_history": "smart_money",
        "news_events": "sentiment", "congressional_trades": "smart_money",
        "fomc_calendar": "calendar", "economic_calendar": "calendar",
        "ipo_calendar": "calendar", "splits_calendar": "calendar",
        "fda_calendar": "calendar", "earnings_calendar_pit": "calendar",
        "eodhd_quota_usage": "ops", "launchd_runs": "ops",
        "data_quality_checks": "ops", "config_history": "ops",
        "feature_flag_changes": "ops", "api_latency_metrics": "ops",
        "user_audit_log": "ops",
        "supabase_sync_state": "system",
    }

    # Per-table assembly
    tables = []
    for t in sync_tables:
        lr = local_counts.get(t, 0)
        rr = remote_counts.get(t)
        led = ledger.get(t) or {}
        if rr is None:
            status = "unknown"
        elif lr == rr:
            status = "in_sync"
        elif lr > rr:
            status = "drift_behind"  # Supabase is missing rows
        else:
            status = "drift_ahead"   # Supabase has extras (unlikely)
        if led.get("failed", 0) > 0:
            status = "error"
        # If we have remote rows but no local source, surface as "remote_only"
        if lr == 0 and (rr or 0) > 0:
            status = "remote_only"
        tables.append({
            "name": t,
            "cluster": _cluster_of.get(t, "other"),
            "local_rows": lr,
            "remote_rows": rr,
            "drift": (None if rr is None else (lr - rr)),
            "status": status,
            "last_sync_at": led.get("last_sync_at"),
            "duration_ms": led.get("duration_ms"),
            "error": led.get("error"),
        })

    # Overall sync health
    n_in_sync = sum(1 for t in tables if t["status"] == "in_sync")
    n_drift = sum(1 for t in tables if t["status"] in ("drift_behind", "drift_ahead"))
    n_error = sum(1 for t in tables if t["status"] == "error")
    n_unknown = sum(1 for t in tables if t["status"] == "unknown")

    payload = {
        "connection": {
            "ok": bool(hc.get("ok")),
            "mode": mode,
            "url": hc.get("url"),
            "error": hc.get("error"),
            "ping_ms": ping_ms,
        },
        "overall": {
            "last_full_sync": last_full_sync,
            "total_tables": len(tables),
            "in_sync": n_in_sync,
            "drift": n_drift,
            "errors": n_error,
            "unknown": n_unknown,
            "total_local_rows": sum(t["local_rows"] for t in tables),
            "total_remote_rows": sum((t["remote_rows"] or 0) for t in tables),
        },
        "tables": tables,
        "generated_at": _t.time(),
    }
    _SUPABASE_STATUS_CACHE["ts"] = now
    _SUPABASE_STATUS_CACHE["payload"] = payload
    return payload


# =========================================================================
# /api/pipelines/mapping — powers the Pipelines tab in kairos.html
# Catalog of every source → target data pipeline (json/jsonl/sqlite/api/computed)
# =========================================================================
_PIPELINES_CATALOG = [
    # ── JSON canonical → Supabase (migrate_sqlite_to_supabase.py) ──
    {"name": "Portfolio singleton",           "source_type": "json",     "source_path": "data/portfolio_state.json",                       "target_table": "portfolio_state",            "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "portfolio"},
    {"name": "Open positions",                "source_type": "json",     "source_path": "data/portfolio_state.json#positions",             "target_table": "positions",                  "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "portfolio"},
    {"name": "Closed trades",                 "source_type": "json",     "source_path": "data/portfolio_state.json#closed_trades",         "target_table": "closed_trades",              "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "portfolio"},
    {"name": "Equity audit",                  "source_type": "json",     "source_path": "data/portfolio_state.json#equity_audit",          "target_table": "equity_audit",               "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "portfolio"},
    {"name": "Equity curve",                  "source_type": "json",     "source_path": "data/portfolio_state.json#equity_curve",          "target_table": "equity_curve",               "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "portfolio"},
    {"name": "Monthly PnL",                   "source_type": "json",     "source_path": "data/portfolio_state.json#monthly_pnl",           "target_table": "monthly_pnl",                "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "portfolio"},
    {"name": "Signal log (live journal)",     "source_type": "json",     "source_path": "data/signal_log.json",                            "target_table": "signal_log",                 "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "journal"},
    {"name": "Custom tickers",                "source_type": "json",     "source_path": "data/custom_tracked.json",                        "target_table": "custom_tickers",             "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "watchlist"},
    {"name": "Alert dedup log",               "source_type": "json",     "source_path": "data/alert_sent_log.json",                        "target_table": "alert_log",                  "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "watchlist"},
    {"name": "Scan health snapshots",         "source_type": "json",     "source_path": "data/scan_health.json#history",                   "target_table": "scan_health",                "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "health"},
    {"name": "Gap events",                    "source_type": "json",     "source_path": "data/gap_events.json",                            "target_table": "gap_events",                 "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "health"},
    {"name": "Paper trading config",          "source_type": "json",     "source_path": "data/paper_trading_start.json",                   "target_table": "paper_trading_config",       "script": "migrate_sqlite_to_supabase.py", "schedule": "com.swingtrade.supabase-sync (30min)", "status": "working", "cluster": "system"},

    # ── JSONL orphan → Supabase (fold_orphan_data.py) ──
    {"name": "Decision log (current + archive)", "source_type": "jsonl", "source_path": "data/decision_log*.jsonl",                        "target_table": "decision_log",               "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "journal"},
    {"name": "Exit signals",                  "source_type": "jsonl",    "source_path": "data/exit_signals.jsonl",                         "target_table": "exit_signals",               "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "journal"},
    {"name": "Earnings outcomes (actuals)",   "source_type": "jsonl",    "source_path": "data/earnings_outcomes.jsonl",                    "target_table": "earnings_outcomes",          "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "earnings"},
    {"name": "Earnings predictions",          "source_type": "jsonl",    "source_path": "data/earnings_prediction_log.jsonl",              "target_table": "earnings_outcomes",          "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "earnings"},
    {"name": "IV rank history",               "source_type": "jsonl",    "source_path": "data/iv_history.jsonl",                           "target_table": "iv_history",                 "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "derivatives"},
    {"name": "Alpaca orders",                 "source_type": "jsonl",    "source_path": "cache/orders.jsonl",                              "target_table": "orders",                     "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "execution"},
    {"name": "EOD actions",                   "source_type": "jsonl",    "source_path": "cache/eod_actions.jsonl",                         "target_table": "eod_actions",                "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "execution"},
    {"name": "Rolling Sharpe (JSONL fold)",   "source_type": "jsonl",    "source_path": "data/rolling_sharpe_history.jsonl",               "target_table": "rolling_sharpe_history",     "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "risk"},
    {"name": "User audit log",                "source_type": "jsonl",    "source_path": "data/audit*.jsonl",                               "target_table": "user_audit_log",             "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "ops"},

    # ── SQLite aux → Supabase ──
    {"name": "Fundamentals snapshot cache",   "source_type": "sqlite",   "source_path": "data/fundamentals.db.fundamentals",               "target_table": "fundamentals_pit",           "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "fundamentals"},
    {"name": "Ticker enrichment cache",       "source_type": "sqlite",   "source_path": "data/enrichment_cache.db.enrichment",             "target_table": "ticker_enrichment_snapshot", "script": "fold_orphan_data.py",          "schedule": "manual (one-shot fold)",               "status": "working", "cluster": "enrichment"},

    # ── cache → scan cluster (backfill_scan_cluster.py) ──
    {"name": "Scan runs",                     "source_type": "json",     "source_path": "cache/picks_history.json#runs",                   "target_table": "runs",                       "script": "backfill_scan_cluster.py",     "schedule": "manual",                               "status": "working", "cluster": "scan"},
    {"name": "Scan picks per run",            "source_type": "json",     "source_path": "cache/picks_history.json#runs[].picks",           "target_table": "picks",                      "script": "backfill_scan_cluster.py",     "schedule": "manual",                               "status": "working", "cluster": "scan"},
    {"name": "Scan trades (sim)",             "source_type": "json",     "source_path": "cache/picks_history.json#trades",                 "target_table": "trades",                     "script": "backfill_scan_cluster.py",     "schedule": "manual",                               "status": "working", "cluster": "scan"},

    # ── Computed (snapshot scripts) ──
    {"name": "Daily rolling Sharpe",          "source_type": "computed", "source_path": "closed_trades + picks_history",                   "target_table": "rolling_sharpe_history",     "script": "snapshot_rolling_sharpe.py",   "schedule": "com.swingtrade.snapshot-sharpe (Mon-Fri 4:35pm PT)", "status": "working", "cluster": "risk"},
    {"name": "Daily portfolio risk",          "source_type": "computed", "source_path": "data/portfolio_state.json",                       "target_table": "portfolio_risk_history",     "script": "snapshot_portfolio_risk.py",   "schedule": "com.swingtrade.snapshot-risk (Mon-Fri 4:40pm PT)",   "status": "working", "cluster": "risk"},
    {"name": "Daily per-position risk",       "source_type": "computed", "source_path": "data/portfolio_state.json#positions",             "target_table": "position_risk_snapshot",     "script": "snapshot_portfolio_risk.py",   "schedule": "com.swingtrade.snapshot-risk (Mon-Fri 4:40pm PT)",   "status": "working", "cluster": "risk"},

    # ── External APIs (scrapers) ──
    {"name": "S&P 500 / NDX membership",      "source_type": "api",      "source_path": "wikipedia.org/wiki/List_of_S&P_500_companies",    "target_table": "index_membership_pit",       "script": "scrapers/index_membership_wikipedia.py", "schedule": "manual / weekly",            "status": "working", "cluster": "reference"},
    {"name": "Macro indicators",              "source_type": "api",      "source_path": "EODHD /eod/{VIX,SPY,QQQ,IWM,HYG,UUP,GLD,US10Y,US2Y}", "target_table": "macro_indicators",         "script": "scrapers/macro_indicators_eodhd.py",     "schedule": "manual / daily",             "status": "working", "cluster": "regime"},
    {"name": "Corporate actions",             "source_type": "api",      "source_path": "EODHD /splits + /div per ticker",                  "target_table": "corporate_actions",          "script": "scrapers/corporate_actions_eodhd.py",    "schedule": "manual / weekly",            "status": "working", "cluster": "reference"},
    {"name": "FOMC meeting calendar",         "source_type": "api",      "source_path": "federalreserve.gov FOMC HTML",                     "target_table": "fomc_calendar",              "script": "scrapers/fomc_ical.py",                  "schedule": "manual / monthly",           "status": "working", "cluster": "calendar"},
    {"name": "Congressional trades",          "source_type": "api",      "source_path": "senate-stock-watcher GH + S3",                     "target_table": "congressional_trades",       "script": "scrapers/congress_trades.py",            "schedule": "manual / weekly",            "status": "broken",  "cluster": "smart_money", "issue": "Both jeremiak/sentate-stock-watcher GH and S3 mirror return 403/404 — Senate Stock Watcher project appears dormant; needs efts.sec.gov direct integration"},

    # ── Empty (schema ready, writer not wired) ──
    {"name": "Backtest runs",                 "source_type": "future",   "source_path": "backtest.py / walk_forward_v2.py",                "target_table": "backtest_runs",              "script": "(needs sb_client write hook)",          "schedule": "ad-hoc",                    "status": "empty",   "cluster": "backtest", "issue": "Requires editing backtest.py to call sb_client.upsert() — production engine path, deferred"},
    {"name": "Backtest trades (per-trade)",   "source_type": "future",   "source_path": "backtest.py simulated trade log",                  "target_table": "backtest_trades",            "script": "(needs sb_client write hook)",          "schedule": "ad-hoc",                    "status": "empty",   "cluster": "backtest", "issue": "Same as backtest_runs — same hook"},
    {"name": "Walk-forward folds",            "source_type": "future",   "source_path": "walk_forward_v2.py per-fold params",               "target_table": "walk_forward_folds",         "script": "(needs sb_client write hook)",          "schedule": "ad-hoc",                    "status": "empty",   "cluster": "backtest", "issue": "Same as backtest_runs — same hook"},
    {"name": "ML Edge predictions",           "source_type": "computed", "source_path": "cache/ml_edge_predictions.json",                   "target_table": "model_predictions",          "script": "snapshot_model_calibration.py --seed",  "schedule": "com.swingtrade.snapshot-model-cal (daily 11:30pm PT)", "status": "working", "cluster": "ml"},
    {"name": "Model calibration",             "source_type": "computed", "source_path": "model_predictions vs realized",                    "target_table": "model_calibration",          "script": "snapshot_model_calibration.py",         "schedule": "com.swingtrade.snapshot-model-cal (daily 11:30pm PT)", "status": "empty",   "cluster": "ml", "issue": "Waiting on realized returns to backfill predictions; first calibration row will appear after 5-20 day horizon"},
    {"name": "Stop level history",            "source_type": "computed", "source_path": "cache/eod_actions.jsonl (sidecar)",                "target_table": "stop_levels_history",        "script": "sync_production_sidecars.py",           "schedule": "manual / nightly",          "status": "working", "cluster": "execution"},
    {"name": "Realized slippage",             "source_type": "future",   "source_path": "executor.py order fills vs expected",             "target_table": "slippage_realized",          "script": "(needs sb_client write hook)",          "schedule": "real-time",                 "status": "empty",   "cluster": "execution", "issue": "Requires editing executor.py — production order path, deferred"},
    {"name": "VaR breaches",                  "source_type": "computed", "source_path": "portfolio_risk_history + equity_curve",            "target_table": "var_breaches",               "script": "snapshot_var_breaches.py",              "schedule": "com.swingtrade.snapshot-var (Mon-Fri 4:55pm PT)",      "status": "empty",   "cluster": "risk", "issue": "Needs at least 2 days of portfolio_risk snapshots; first breach row appears after a real drawdown day"},
    {"name": "Signal filter decisions (A2)",  "source_type": "computed", "source_path": "data/signal_log.json (post-hoc inferred)",         "target_table": "signal_filter_decisions",    "script": "sync_production_sidecars.py",           "schedule": "manual / nightly",          "status": "working", "cluster": "journal"},
    {"name": "Strategy PnL attribution",      "source_type": "computed", "source_path": "picks_history.json#trades by setup_family",        "target_table": "strategy_pnl_attribution",   "script": "snapshot_strategy_attribution.py",      "schedule": "com.swingtrade.snapshot-attribution (Mon-Fri 4:45pm PT)", "status": "working", "cluster": "attribution"},
    {"name": "Wilson CI snapshot",            "source_type": "computed", "source_path": "picks_history.json#trades per cell",               "target_table": "wilson_ci_snapshot",         "script": "snapshot_wilson_ci.py",                 "schedule": "com.swingtrade.snapshot-wilson (Mon-Fri 4:50pm PT)",   "status": "working", "cluster": "calibration"},
    {"name": "Kelly size history",            "source_type": "computed", "source_path": "analysis.py sidecar → cache/kelly_size_log.jsonl",  "target_table": "kelly_size_history",         "script": "sync_production_sidecars.py extract_kelly", "schedule": "per scan + manual sync",  "status": "working", "cluster": "risk"},
    {"name": "SMC hit rates",                 "source_type": "json",     "source_path": "data/smc_hit_rates.json",                          "target_table": "smc_hit_rates",              "script": "fold_orphan_data.py",                   "schedule": "manual",                    "status": "working", "cluster": "calibration"},
    {"name": "Regime transitions",            "source_type": "json",     "source_path": "cache/regime_history.json",                        "target_table": "regime_transitions",         "script": "fold_orphan_data.py",                   "schedule": "manual",                    "status": "working", "cluster": "regime"},
    {"name": "Watch triggers",                "source_type": "computed", "source_path": "tracker.py sidecar → cache/watch_triggers.jsonl",  "target_table": "watch_triggers",             "script": "sync_production_sidecars.py extract_watch", "schedule": "per scan + manual sync",  "status": "working", "cluster": "watchlist"},

    # ── Future scrapers (free data, not yet implemented) ──
    {"name": "Insider transactions (Form 4)", "source_type": "api",      "source_path": "openinsider.com latest-insider-transactions",      "target_table": "insider_transactions",       "script": "scrapers/insider_openinsider.py",       "schedule": "manual / daily",            "status": "working", "cluster": "smart_money"},
    {"name": "13F institutional holdings",    "source_type": "future",   "source_path": "efts.sec.gov 13F filings",                         "target_table": "institutional_holdings",     "script": "scrapers/institutional_13f.py (TODO)",  "schedule": "quarterly",                 "status": "future",  "cluster": "smart_money", "issue": "Same as Form 4 — SEC EDGAR XBRL parsing complexity, deferred"},
    {"name": "Short interest history",        "source_type": "api",      "source_path": "cdn.finra.org regsho daily CNMSshvol",             "target_table": "short_interest_history",     "script": "scrapers/short_interest_finra.py",      "schedule": "daily (T+2)",               "status": "working", "cluster": "smart_money"},
    {"name": "Cold OHLCV storage",            "source_type": "api",      "source_path": "EODHD /eod/{TICKER} for active tickers",           "target_table": "ohlcv_daily",                "script": "scrapers/ohlcv_cold_storage.py",        "schedule": "nightly batch",             "status": "working", "cluster": "market_data"},
    {"name": "Tickers master",                "source_type": "api",      "source_path": "EODHD /exchange-symbol-list/US",                   "target_table": "tickers_master",             "script": "scrapers/tickers_master_eodhd.py",      "schedule": "weekly",                    "status": "working", "cluster": "reference"},
    {"name": "News events",                   "source_type": "api",      "source_path": "EODHD /news per active ticker",                    "target_table": "news_events",                "script": "scrapers/news_events_eodhd.py",         "schedule": "hourly",                    "status": "working", "cluster": "sentiment"},
    {"name": "IPO calendar",                  "source_type": "api",      "source_path": "api.nasdaq.com /api/ipo/calendar",                 "target_table": "ipo_calendar",               "script": "scrapers/ipo_calendar_nasdaq.py",       "schedule": "daily",                     "status": "working", "cluster": "calendar"},
    {"name": "Splits calendar",               "source_type": "computed", "source_path": "derived from corporate_actions WHERE type=split",  "target_table": "splits_calendar",            "script": "scrapers/splits_calendar_derived.py",   "schedule": "daily",                     "status": "empty",   "cluster": "calendar", "issue": "Source corporate_actions has 0 splits — need to expand corporate_actions universe beyond active 9 tickers"},
    {"name": "Economic calendar",             "source_type": "future",   "source_path": "fred.stlouisfed.org API or BLS RSS",               "target_table": "economic_calendar",          "script": "scrapers/economic_calendar.py (TODO)",  "schedule": "daily",                     "status": "future",  "cluster": "calendar", "issue": "FRED API requires (free) API key registration — pending setup"},
    {"name": "FDA PDUFA calendar",            "source_type": "future",   "source_path": "fda.gov + biotech disclosure scrape",              "target_table": "fda_calendar",               "script": "scrapers/fda_calendar.py (TODO)",       "schedule": "weekly",                    "status": "future",  "cluster": "calendar", "issue": "FDA + biotech catalyst aggregation is complex multi-source scrape — deferred"},
    {"name": "Earnings calendar PIT",         "source_type": "future",   "source_path": "Zacks (existing scraper) → vintage layer",         "target_table": "earnings_calendar_pit",      "script": "(needs vintage tracker layer)",         "schedule": "daily",                     "status": "future",  "cluster": "calendar", "issue": "Requires intercepting existing Zacks scraper output + tracking changes over time (vintage layer)"},

    # ── Ops telemetry (needs app-side instrumentation) ──
    {"name": "EODHD quota usage",             "source_type": "computed", "source_path": "eodhd_client.py _ENDPOINT_COUNTER (13 buckets)",   "target_table": "eodhd_quota_usage",          "script": "flush_quota_to_supabase() (auto at scan end)", "schedule": "every scan end + manual flush", "status": "working", "cluster": "ops"},
    {"name": "Launchd run telemetry",         "source_type": "computed", "source_path": "scripts/launchd_wrapper.sh per plist firing",     "target_table": "launchd_runs",               "script": "scripts/launchd_log_to_supabase.py",    "schedule": "every plist firing",        "status": "empty",   "cluster": "ops", "issue": "Wrapper adopted by 16/19 plists — populates on next plist firing"},
    {"name": "Data quality checks",           "source_type": "computed", "source_path": "scripts/dq_checks.py 10 assertions",               "target_table": "data_quality_checks",        "script": "scripts/dq_checks.py",                  "schedule": "com.swingtrade.dq-checks (daily 6am PT)", "status": "working", "cluster": "ops"},
    {"name": "Config history",                "source_type": "computed", "source_path": "git post-commit diff on config/*.json",              "target_table": "config_history",             "script": "scripts/config_history_writer.py",        "schedule": "every commit touching config/*",  "status": "working", "cluster": "ops"},
    {"name": "Feature flag changes",          "source_type": "computed", "source_path": "git post-commit *_enabled flips",                   "target_table": "feature_flag_changes",       "script": "scripts/config_history_writer.py",        "schedule": "every commit touching config/*",  "status": "working", "cluster": "ops"},
    {"name": "API latency metrics",           "source_type": "computed", "source_path": "FastAPI middleware (_api_latency_middleware)",     "target_table": "api_latency_metrics",        "script": "server.py middleware",                  "schedule": "60s flush",                 "status": "empty",   "cluster": "ops", "issue": "Middleware installed — populates on next 60s flush window after server restart"},

    # ── Self-referencing ──
    {"name": "Supabase sync ledger",          "source_type": "computed", "source_path": "migrate_sqlite_to_supabase.py per-run state",      "target_table": "supabase_sync_state",        "script": "migrate_sqlite_to_supabase.py", "schedule": "every sync run",            "status": "working", "cluster": "system"},
    {"name": "Schema version key",            "source_type": "computed", "source_path": "migrations/*.sql INSERT INTO meta",                "target_table": "meta",                       "script": "scripts/apply_supabase_migrations.py", "schedule": "manual",             "status": "working", "cluster": "system"},
]

_PIPELINES_CACHE: dict = {"ts": 0.0, "payload": None}
_PIPELINES_TTL_S = 30.0


@app.get("/api/pipelines/mapping")
async def pipelines_mapping():
    """Return the source→target catalog merged with live state (row counts,
    last sync timestamps from the ledger). Drives the Pipelines tab.
    """
    import time as _t
    now = _t.time()
    if _PIPELINES_CACHE["payload"] is not None and (now - _PIPELINES_CACHE["ts"]) < _PIPELINES_TTL_S:
        return _PIPELINES_CACHE["payload"]

    from pathlib import Path as _P
    import json as _j
    root = _P(__file__).parent
    state_path = root / "data" / "supabase_sync_state.json"
    ledger: dict = {}
    if state_path.exists():
        try:
            ledger = (_j.loads(state_path.read_text()).get("tables") or {})
        except Exception:
            pass

    # Pull remote row counts (one HEAD query per unique target table)
    remote_counts: dict[str, int | None] = {}
    try:
        from supabase_client import sb_client
        sb = sb_client()
        if sb is not None:
            target_tables = {p["target_table"] for p in _PIPELINES_CATALOG}
            for t in target_tables:
                try:
                    resp = sb.table(t).select("*", count="exact", head=True).execute()
                    remote_counts[t] = getattr(resp, "count", None)
                except Exception:
                    remote_counts[t] = None
    except Exception:
        pass

    out = []
    for p in _PIPELINES_CATALOG:
        led = ledger.get(p["target_table"]) or {}
        out.append({
            **p,
            "remote_rows": remote_counts.get(p["target_table"]),
            "last_sync_at": led.get("last_sync_at"),
            "last_pushed": led.get("pushed"),
            "last_failed": led.get("failed"),
            "last_error": led.get("error"),
        })

    n_working = sum(1 for p in out if p["status"] == "working")
    n_empty   = sum(1 for p in out if p["status"] == "empty")
    n_future  = sum(1 for p in out if p["status"] == "future")
    n_broken  = sum(1 for p in out if p["status"] == "broken")
    n_populated = sum(1 for p in out if (p.get("remote_rows") or 0) > 0)

    payload = {
        "overall": {
            "total_pipelines": len(out),
            "working": n_working,
            "empty": n_empty,
            "future": n_future,
            "broken": n_broken,
            "populated": n_populated,
        },
        "pipelines": out,
        "generated_at": now,
    }
    _PIPELINES_CACHE["ts"] = now
    _PIPELINES_CACHE["payload"] = payload
    return payload


# =========================================================================
# /api/pipelines/run — trigger a single pipeline's script in a subprocess
# /api/pipelines/log — tail the stdout/stderr log of a pipeline's script
# =========================================================================
import re as _re

# Whitelist of runnable scripts (no arbitrary paths from client)
_RUNNABLE_SCRIPTS = {
    "migrate_sqlite_to_supabase.py":              ["--apply"],
    "fold_orphan_data.py":                        ["--apply"],
    "backfill_scan_cluster.py":                   ["--apply"],
    "snapshot_rolling_sharpe.py":                 ["--apply"],
    "snapshot_portfolio_risk.py":                 ["--apply"],
    "snapshot_strategy_attribution.py":           ["--apply"],
    "snapshot_wilson_ci.py":                      ["--apply"],
    "snapshot_model_calibration.py":              ["--apply", "--seed"],
    "snapshot_var_breaches.py":                   ["--apply"],
    "scrapers/index_membership_wikipedia.py":     ["--apply"],
    "scrapers/macro_indicators_eodhd.py":         ["--apply"],
    "scrapers/corporate_actions_eodhd.py":        ["--apply"],
    "scrapers/fomc_ical.py":                      ["--apply"],
    "scrapers/congress_trades.py":                ["--apply", "--limit", "500"],
    "scrapers/tickers_master_eodhd.py":           ["--apply"],
    "scrapers/ohlcv_cold_storage.py":             ["--apply", "--max-tickers", "30"],
    "scrapers/splits_calendar_derived.py":        ["--apply"],
    "scrapers/short_interest_finra.py":           ["--apply"],
    "scrapers/ipo_calendar_nasdaq.py":            ["--apply"],
    "scrapers/news_events_eodhd.py":              ["--apply"],
}


def _script_log_path(script: str) -> str:
    """Map script name → its launchd log path (if scheduled) or a generic cache log."""
    from pathlib import Path as _P
    label_map = {
        "migrate_sqlite_to_supabase.py":     "supabase-sync",
        "snapshot_rolling_sharpe.py":        "snapshot-sharpe",
        "snapshot_portfolio_risk.py":        "snapshot-risk",
        "snapshot_strategy_attribution.py":  "snapshot-attribution",
        "snapshot_wilson_ci.py":             "snapshot-wilson",
        "snapshot_model_calibration.py":     "snapshot-model-cal",
        "snapshot_var_breaches.py":          "snapshot-var",
    }
    base = _P(__file__).parent
    label = label_map.get(script)
    if label:
        for ext in (".log", ".err"):
            p = base / "cache" / "logs" / f"{label}{ext}"
            if p.exists():
                return str(p)
    # generic run-log location
    return str(base / "cache" / "logs" / f"pipeline-{script.replace('/', '_').replace('.py','')}.log")


@app.post("/api/pipelines/run")
async def pipelines_run(payload: dict, _=Depends(_check_auth)):
    """Trigger one pipeline script. Body: {script: 'name.py'}."""
    import subprocess as _sp
    from pathlib import Path as _P
    script = (payload or {}).get("script", "")
    if script not in _RUNNABLE_SCRIPTS:
        return {"ok": False, "error": f"script not in whitelist: {script}"}
    args = _RUNNABLE_SCRIPTS[script]
    root = _P(__file__).parent
    log_path = _script_log_path(script)
    try:
        # Capture stdout+stderr to log file, return immediately
        with open(log_path, "a") as lf:
            lf.write(f"\n\n=== triggered via UI at {time.time()} ===\n")
        proc = _sp.Popen(
            ["python3", str(root / "scripts" / script), *args],
            stdout=open(log_path, "a"),
            stderr=_sp.STDOUT,
            cwd=str(root),
            start_new_session=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # Bust pipelines + supabase caches so next poll shows fresh state
    _PIPELINES_CACHE["ts"] = 0.0
    _PIPELINES_CACHE["payload"] = None
    _SUPABASE_STATUS_CACHE["ts"] = 0.0
    _SUPABASE_STATUS_CACHE["payload"] = None
    return {"ok": True, "script": script, "pid": proc.pid, "log": log_path}


@app.get("/api/pipelines/log")
async def pipelines_log(script: str = "", lines: int = 60):
    """Return last N lines of a pipeline's log."""
    from pathlib import Path as _P
    if script not in _RUNNABLE_SCRIPTS:
        return {"ok": False, "error": f"script not in whitelist: {script}", "log": ""}
    log_path = _P(_script_log_path(script))
    if not log_path.exists():
        return {"ok": False, "error": f"no log yet: {log_path}", "log": ""}
    try:
        text = log_path.read_text(errors="ignore").splitlines()
        tail = text[-int(lines):]
        return {"ok": True, "script": script, "log_path": str(log_path), "log": "\n".join(tail), "size": log_path.stat().st_size}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "log": ""}


@app.post("/api/supabase/sync")
async def supabase_sync(_=Depends(_check_auth)):
    """Trigger a fresh sync. Runs migrate_sqlite_to_supabase.py --apply in a
    subprocess and returns the new status payload (cache busted).
    """
    import subprocess as _sp
    from pathlib import Path as _P
    root = _P(__file__).parent
    try:
        proc = _sp.run(
            ["python3", str(root / "migrate_sqlite_to_supabase.py"), "--apply"],
            capture_output=True, text=True, timeout=180, cwd=str(root),
        )
        ok = (proc.returncode == 0)
        tail = (proc.stdout or "").splitlines()[-20:] + (proc.stderr or "").splitlines()[-5:]
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "log": []}

    # Bust the cache so /api/supabase/status reflects fresh sync immediately
    _SUPABASE_STATUS_CACHE["ts"] = 0.0
    _SUPABASE_STATUS_CACHE["payload"] = None
    return {"ok": ok, "log": tail, "returncode": proc.returncode}


# ────────────────────────────────────────────────────────────────────────────
# /api/strategy_regime_matrix — drives the Strategy × Regime tab.
# Aggregates three diagnostic outputs into a single decision-grade payload:
#   1. regime_sharpe_decomp_*.json  — realized per-(setup × regime) Sharpe/WR/PF
#   2. sharpe_setup_trend_*.json    — per-setup 20-trade-window edge-erosion
#   3. backtest_sleeves_*.json      — forward replay of catalyst sleeves
# Cached 60s; re-reads files on cache miss.
# ────────────────────────────────────────────────────────────────────────────
_STRAT_MATRIX_CACHE = {"ts": 0.0, "payload": None}
_STRAT_MATRIX_TTL_S = 60


@app.get("/api/strategy_regime_matrix")
async def strategy_regime_matrix():
    import time as _t
    now = _t.time()
    if _STRAT_MATRIX_CACHE["payload"] is not None and (now - _STRAT_MATRIX_CACHE["ts"]) < _STRAT_MATRIX_TTL_S:
        return _STRAT_MATRIX_CACHE["payload"]

    from pathlib import Path as _P
    import json as _j
    root = _P(__file__).parent
    cache_dir = root / "cache"

    def _latest(prefix):
        files = sorted(cache_dir.glob(f"{prefix}_*.json"), reverse=True)
        for fp in files:
            try:
                return {"path": str(fp.relative_to(root)), "data": _j.loads(fp.read_text())}
            except Exception:
                continue
        return None

    decomp = _latest("regime_sharpe_decomp")
    trend = _latest("sharpe_setup_trend")
    sleeves = _latest("backtest_sleeves")

    def _pct(x):
        """WR is stored as fraction 0-1; renderer expects 0-100."""
        if x is None: return None
        try: return round(float(x) * 100, 1)
        except Exception: return None

    def _norm_decomp(raw):
        """Flatten the decomp JSON into renderer-friendly shape."""
        if not raw:
            return {}
        out = {"by_aggregate": dict(raw.get("aggregate") or {})}
        if "wr" in out["by_aggregate"]:
            out["by_aggregate"]["wr"] = _pct(out["by_aggregate"]["wr"])
            out["by_aggregate"]["wilson_lb"] = _pct(out["by_aggregate"].get("wilson_lb"))

        def _norm_grp(d, key_field):
            rows = []
            for name, stats in (d or {}).items():
                r = dict(stats); r[key_field] = name
                r["wr"] = _pct(r.get("wr"))
                r["wilson_lb"] = _pct(r.get("wilson_lb"))
                rows.append(r)
            # Sort by n desc
            rows.sort(key=lambda x: -(x.get("n") or 0))
            return rows

        out["by_regime"] = _norm_grp(raw.get("by_regime"), "regime")
        out["by_setup_family"] = _norm_grp(raw.get("by_setup_family"), "setup_family")
        out["by_entry_quality"] = _norm_grp(raw.get("by_entry_quality"), "entry_quality")

        # regime_x_setup is flat keyed by "regime|setup" — unflatten to {regime: [rows]}
        mat = {}
        for key, stats in (raw.get("regime_x_setup") or {}).items():
            if "|" not in key:
                continue
            regime, setup = key.split("|", 1)
            r = dict(stats); r["setup_family"] = setup
            r["wr"] = _pct(r.get("wr"))
            r["wilson_lb"] = _pct(r.get("wilson_lb"))
            mat.setdefault(regime, []).append(r)
        for regime in mat:
            mat[regime].sort(key=lambda x: -(x.get("n") or 0))
        out["by_regime_setup"] = mat
        return out

    def _norm_trend(raw):
        if not raw:
            return {}
        by_setup = {}
        for setup, info in (raw.get("per_setup") or {}).items():
            windows = []
            for w in (info.get("windows") or []):
                w2 = dict(w)
                w2["wr"] = _pct(w2.get("wr"))
                w2["sharpe"] = w2.get("sharpe") if w2.get("sharpe") is not None else w2.get("sharpe_per_trade")
                windows.append(w2)
            by_setup[setup] = {
                "total_n": info.get("total_n") or info.get("n"),
                "verdict": info.get("verdict", "stable"),
                "windows": windows,
            }
        return {"by_setup": by_setup}

    def _norm_sleeves(raw):
        if not raw:
            return {}
        summary = []
        for variant_key, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            agg = payload.get("aggregate") or {}
            sleeve_name = payload.get("strategy") or variant_key
            # Parse variant suffix from variant_key after the sleeve prefix
            variant = ""
            for prefix in ("mean_reversion", "momentum", "defensive"):
                if variant_key.startswith(prefix + "_"):
                    variant = variant_key[len(prefix)+1:]
                    break
            if variant_key == "momentum":
                variant = "baseline"
            n = agg.get("n", 0)
            pf = agg.get("pf")
            pf_haircut = agg.get("pf_haircut")
            if pf_haircut is None and pf is not None:
                pf_haircut = round(pf - 0.2, 2)
            verdict = "PASS" if (pf_haircut and pf_haircut >= 1.0 and n >= 30) else "FAIL"
            summary.append({
                "sleeve": sleeve_name,
                "variant": variant,
                "n": n,
                "wr": _pct(agg.get("wr")),
                "wilson_lb": _pct(agg.get("wilson_lb")),
                "pf": pf,
                "pf_haircut": pf_haircut,
                "verdict": verdict,
            })
        summary.sort(key=lambda x: -(x.get("n") or 0))
        return {"summary": summary}

    payload = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "sources": {
            "decomp": decomp.get("path") if decomp else None,
            "trend": trend.get("path") if trend else None,
            "sleeves": sleeves.get("path") if sleeves else None,
        },
        "decomp": _norm_decomp((decomp or {}).get("data")),
        "trend": _norm_trend((trend or {}).get("data")),
        "sleeves": _norm_sleeves((sleeves or {}).get("data")),
        "decisions": [
            {"id": 1, "action": "Keep aggregate rolling-Sharpe kill ON",
             "evidence": "All 3 sleeves degrading concurrently (Trend Cont. -0.34, Breakout Exp. -0.52, Impulse Cat. -0.11 in latest 20-trade window)",
             "confidence": "HIGH", "category": "risk"},
            {"id": 2, "action": "Block Breakout Expansion in risk_on_trending regime",
             "evidence": "PF 0.79, WR 37.4%, Sharpe -0.09 on n=123 (Wilson LB 29.4%)",
             "confidence": "HIGH", "category": "regime"},
            {"id": 3, "action": "Promote MISSED entry quality",
             "evidence": "PF 2.06, Sharpe +0.26, Wilson LB 53.8% on n=379",
             "confidence": "HIGH", "category": "entry"},
            {"id": 4, "action": "Demote FRESH entry quality",
             "evidence": "PF 0.12, Sharpe -0.35 (n=23 — caveat: below Wilson floor)",
             "confidence": "MED", "category": "entry"},
            {"id": 5, "action": "Activate Momentum Continuation as primary sleeve",
             "evidence": "PF 1.67 (post-haircut), WR 57.8%, n=2718",
             "confidence": "HIGH", "category": "sleeve"},
            {"id": 6, "action": "Narrow Defensive Rotation to XLU + GLD only",
             "evidence": "PF 1.01 vs 0.63 on full 6-ETF basket",
             "confidence": "HIGH", "category": "sleeve"},
            {"id": 7, "action": "Mean Reversion only when RSI<15 + RVOL>=1.2",
             "evidence": "Stratified PF 5.58 vs 1.15 unfiltered (n=16 — preliminary)",
             "confidence": "MED", "category": "sleeve"},
            {"id": 8, "action": "Kill 10-Week Pullback sleeve",
             "evidence": "PF 0.59, Sharpe -0.19 on n=37",
             "confidence": "HIGH", "category": "sleeve"},
        ],
    }
    _STRAT_MATRIX_CACHE["payload"] = payload
    _STRAT_MATRIX_CACHE["ts"] = now
    return payload


# ────────────────────────────────────────────────────────────────────────────
# /api/research_roadmap — drives the Research Lab tab.
# Surfaces the P1/P2/P3 edge-research priorities discovered tonight:
#   P1 — True HMM regime classifier (currently Gaussian soft-classifier)
#   P2 — Fama-French factor model (currently absent)
#   P3 — Verify ML lib (CONFIRMED sklearn; LightGBM swap recommended)
# Dynamic state pulled from cache/ml_edge_predictions.json and runtime
# inspection. Static roadmap items defined inline (revise as new gaps emerge).
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/research_roadmap")
async def research_roadmap():
    from pathlib import Path as _P
    import json as _j
    root = _P(__file__).parent

    # Dynamic: pull live ML metadata
    ml_lib = "sklearn (LR + RF + GradientBoosting)"
    ml_model_n = None; ml_auc = None; ml_features = 0; ml_trained_at = None
    try:
        mlp = root / "cache" / "ml_edge_predictions.json"
        if mlp.exists():
            d = _j.loads(mlp.read_text())
            sample = next(iter((d.get("predictions") or {}).get("swing", {}).values()), {})
            mm = sample.get("model_meta", {})
            ml_model_n = mm.get("n_total")
            ml_trained_at = mm.get("trained_at")
            ml_features = len(mm.get("feature_cols", []))
            hit = sample.get("hit_net", {})
            ml_auc = hit.get("model_auc")
    except Exception:
        pass

    # Dynamic: pull current regime + HMM state
    regime_now = None; hmm_now = None
    try:
        b = _j.loads((root / "cache" / "last_bundle.json").read_text())
        regime_now = (b.get("regime") or {}).get("regime4")
        hmm_now = (b.get("regime") or {}).get("hmm_regime")
    except Exception:
        pass

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "live_state": {
            "ml_lib": ml_lib,
            "ml_model_n": ml_model_n,
            "ml_auc": ml_auc,
            "ml_features": ml_features,
            "ml_trained_at": ml_trained_at,
            "regime_classifier": "gaussian_soft_classifier_v1 (per-bar, no transition matrix)",
            "regime_now": regime_now,
            "hmm_now": hmm_now,
            "factor_model": "NOT IMPLEMENTED",
        },
        "priorities": [
            {
                "id": "P1",
                "title": "True HMM regime classifier",
                "priority": "P1",
                "category": "regime",
                "status": "researching",
                "effort_days": "2-3",
                "current_state": "gaussian_soft_classifier_v1 — per-bar Gaussian classification with p_bull/p_neutral/p_bear + confidence, but NO state-transition matrix. Treats each bar independently.",
                "target_state": "Hidden Markov Model with Baum-Welch trained transition probabilities. Regime flip prediction conditioned on prior regime + observation likelihood (proper temporal smoothing).",
                "mechanism_hypothesis": "Markets exhibit regime persistence (bull regimes don't flip to bear in one day). A true HMM captures this with state-transition probabilities, so regime flips require sustained evidence — reduces false flips that cause whipsaw sizing changes.",
                "evidence_for": [
                    "CLAUDE.md principle 5 — regime conditioning IS the strategy",
                    "Article (B. Regime Switching Models) recommends HMM explicitly",
                    "Current Gaussian classifier missed +6 distribution days transition to 'under_pressure' until breadth dropped 13pp (lagging signal)",
                ],
                "evidence_against": [
                    "Only 728/1148 trades happened in risk_on_choppy — we have weak data on regime transitions, so HMM may not be trainable robustly yet",
                    "Adds 1 more layer of state to the system; debuggability cost",
                ],
                "validation_gate": "Out-of-sample regime-flip prediction accuracy must exceed Gaussian baseline by >5pp on 30+ historical regime flips. Wilson 95% LB must be >0.",
                "dependencies": ["hmmlearn", "10+ years SPY OHLCV (already have)"],
                "rollback": "Keep gaussian_soft_classifier_v1 alongside; flag-gate HMM at compute_hmm_regime_safe().",
                "next_actions": [
                    "Spike: train hmmlearn GaussianHMM(n=3) on SPY 10y returns + vol; compare regime labels vs current classifier",
                    "Backtest: re-run scoring with HMM regime vs Gaussian on last 1y, measure Sharpe diff",
                    "If positive: ship behind regime_classifier.use_hmm=false flag",
                ],
            },
            {
                "id": "P2",
                "title": "Fama-French factor model overlay",
                "priority": "P2",
                "category": "attribution",
                "status": "scoping",
                "effort_days": "1-2",
                "current_state": "5-pillar scoring includes RS+Sector (momentum proxy) and Quality Gate. No orthogonal factor decomposition. Cannot answer: 'is our negative Sharpe from poor stock selection OR from being long momentum during a momentum drawdown?'",
                "target_state": "Daily FF5+momentum factor exposure tracked per trade. Each closed trade decomposed into alpha + sum(factor_loadings × factor_returns). Per-(setup × regime) factor attribution.",
                "mechanism_hypothesis": "Returns = alpha + market_beta × market + size × SMB + value × HML + profitability × RMW + investment × CMA + momentum × MOM. Knowing the loadings tells us if we're rewarded for skill (alpha>0) or just compensated for factor exposure (alpha~0). Distinguishes true edge from beta in disguise.",
                "evidence_for": [
                    "Article (C. Factor Models) recommends Fama-French explicitly",
                    "Free factor data from Ken French website (Kenneth French Data Library)",
                    "Current −0.46 portfolio Sharpe is opaque — could be 'system is broken' OR 'momentum factor drew down 8% this month and we're long it'",
                ],
                "evidence_against": [
                    "Decomposition is descriptive, not prescriptive — doesn't directly tell us what to change",
                    "Daily factor returns lag by 1-2 days; live use requires interpolation",
                ],
                "validation_gate": "Factor loadings on a sample of 50 known-momentum stocks must produce MOM loadings > 0.5 (sanity check). Per-trade alpha+factor decomposition must sum to within 1% of realized return.",
                "dependencies": ["pandas-datareader OR direct CSV download from K. French", "no new paid sources"],
                "rollback": "Pure analytics overlay — no trading-decision impact unless we explicitly use loadings to size.",
                "next_actions": [
                    "Download FF5 + MOM daily factor returns from K. French (free)",
                    "Build factor_attribution.py: for each closed trade, regress daily returns vs factors, compute loadings + alpha",
                    "Add 'Factor Attribution' subtab to Performance tab",
                ],
            },
            {
                "id": "P3",
                "title": "Verify + upgrade ML lib (sklearn → LightGBM)",
                "priority": "P3",
                "category": "ml",
                "status": "confirmed_gap",
                "effort_days": "0.5",
                "current_state": f"CONFIRMED: train_mover_predictor_v2.py uses sklearn (LogisticRegression + RandomForestClassifier + GradientBoostingClassifier). Current AUC ~0.77 on {ml_model_n or '?'} samples.",
                "target_state": "LightGBM as primary classifier with isotonic calibration. Expected AUC lift: +0.02-0.05.",
                "mechanism_hypothesis": "Gradient boosting (sklearn GradientBoosting) and LightGBM are same algorithm family, but LightGBM has: histogram-based splits (5-10x faster), leaf-wise growth (slightly better accuracy on tabular data), categorical-feature native support. The article specifically calls out tree models including LightGBM as 'highly recommended' for finance.",
                "evidence_for": [
                    "Article explicitly recommends LightGBM/XGBoost/CatBoost for tabular finance data",
                    "Industry standard for credit risk, anomaly detection, structured prediction",
                    "LightGBM is faster — can retrain weekly instead of monthly",
                ],
                "evidence_against": [
                    "Current sklearn GradientBoosting already covers same algorithmic family — gain may be marginal",
                    "AUC 0.77 is already strong; +0.02-0.05 lift may not translate to live edge",
                ],
                "validation_gate": "Side-by-side training on identical features + folds. LightGBM AUC must exceed sklearn GradientBoosting AUC by ≥0.02 on out-of-fold validation. Probability calibration ECE ≤ 0.05.",
                "dependencies": ["pip install lightgbm (free)"],
                "rollback": "Keep both .pkl models on disk; predict_mover_predictor.py picks better per mode.",
                "next_actions": [
                    "Add LightGBM to train_mover_predictor_v2.py classifier dict",
                    "Run training in parallel — compare AUC + calibration",
                    "If LGBM wins ≥0.02 AUC: swap to LGBM, otherwise document null result",
                ],
            },
        ],
    }


# ────────────────────────────────────────────────────────────────────────────
# /api/factor_exposure — drives the Factor Exposure tab in v2 dashboard
# Reads cache/factor_attribution_*.json (latest) generated by
# scripts/p2_factor_attribution_spike.py
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/factor_exposure")
async def factor_exposure():
    from pathlib import Path as _P
    import json as _j
    import re as _re
    root = _P(__file__).parent
    cache_dir = root / "cache"
    files = sorted(cache_dir.glob("factor_attribution_*.json"), reverse=True)
    if not files:
        return {"error": "no factor_attribution_*.json in cache",
                "hint": "run scripts/p2_factor_attribution_spike.py"}
    latest = files[0]
    try:
        d = _j.loads(latest.read_text())
    except Exception as e:
        return {"error": f"parse failed: {e}"}
    # Augment with per-setup data if not already there
    # The spike saves aggregate only; we re-parse the stdout text via
    # picks_history if needed. For now, return aggregate + source path.
    return {
        "generated_at": d.get("generated_at"),
        "source_file": str(latest.relative_to(root)),
        "n_trades": d.get("n_trades"),
        "factor_source": d.get("factor_source", "EODHD SPY+QQQ proxy"),
        "limitation": d.get("limitation", ""),
        "aggregate": d.get("aggregate") or d.get("aggregate_loadings", {}),
    }


# ────────────────────────────────────────────────────────────────────────────
# /api/chat — Kairos AI chat (local Ollama proxy with dashboard context)
# Gated by AI_CHAT_ENABLED env (default "1"). Model via OLLAMA_MODEL env
# (default "qwen2.5:32b-instruct"). Streams server-sent events back to the
# floating bubble in kairos.html. Pulls regime + active-ticker context from
# cache/last_bundle.json so the model can talk about today's actual scan.
# ────────────────────────────────────────────────────────────────────────────
import httpx as _httpx_chat
from fastapi.responses import StreamingResponse as _StreamingResponse


def _chat_enabled() -> bool:
    return os.environ.get("AI_CHAT_ENABLED", "1").lower() not in ("0", "false", "no", "off")


def _chat_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "qwen2.5:32b-instruct")


def _chat_ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _chat_collect_bundle_tickers(bundle: dict) -> dict:
    """Build a {TICKER: (signal_dict, source_list)} index from the bundle."""
    idx = {}
    for key in ("buy_candidates", "watch_list", "sell_candidates", "all_scored",
                "medium_term_picks", "long_term_picks", "killed"):
        for s in (bundle.get(key) or []):
            t = (s.get("ticker") or "").upper()
            if t and t not in idx:
                idx[t] = (s, key)
    return idx


def _chat_extract_tickers_from_msg(msg: str, valid_tickers: set) -> list:
    """Pull uppercase 1-5 letter tokens from msg, keep only ones in the bundle."""
    import re as _re
    candidates = _re.findall(r"\b[A-Z]{1,5}\b", msg or "")
    # Skip common false-positives even if they happen to be tickers
    SKIP = {"BUY", "SELL", "HOLD", "RSI", "MACD", "ATR", "EMA", "SMA", "VWAP",
            "ADV", "VIX", "SPY", "QQQ", "IWM", "USD", "ETF", "IPO", "PEAD",
            "ESP", "WR", "PF", "AI", "OK", "TLDR", "FYI", "BTW", "ASAP",
            "WATCH", "SHORT", "LONG", "STOP", "ENTRY", "TARGET", "RISK", "FOMC"}
    out = []
    seen = set()
    for c in candidates:
        if c in SKIP or c in seen:
            continue
        if c in valid_tickers:
            out.append(c)
            seen.add(c)
            if len(out) >= 3:
                break
    return out


def _chat_render_ticker_block(t: str, found: dict, source: str) -> str:
    plan = found.get("canonical_trade_plan") or {}
    return (
        f"\n=== TICKER {t} ({source}) ===\n"
        f"Score: {found.get('score')} | "
        f"Decision: {found.get('decision')} | "
        f"Conviction: {found.get('conviction') or plan.get('conviction_tier','-')}\n"
        f"Setup: {found.get('setup_family') or '-'} | "
        f"Catalyst tier: {found.get('catalyst_tier') or '-'} | "
        f"Catalysts: {','.join(found.get('catalyst_tags') or []) or '-'}\n"
        f"Direction: {found.get('direction') or 'long'} | "
        f"Entry quality: {found.get('entry_quality') or '-'} | "
        f"Industry: {found.get('industry') or '-'}\n"
        f"Trade plan: entry={plan.get('entry')} stop={plan.get('stop')} "
        f"T1={plan.get('target1')} T2={plan.get('target2')} "
        f"hold={plan.get('hold_period_days')}d "
        f"size={plan.get('position_size_pct')}%\n"
        f"Risk: {plan.get('risk')}\n"
        f"Gate result: {found.get('gate')} | "
        f"Decision state: {found.get('decision_state')}\n"
        f"Caveats: {found.get('caveats') or '-'}\n"
        f"P(profit): {found.get('mc_p_profit')} | "
        f"ATR%: {found.get('atr_pct')} | Beta: {found.get('beta')}"
    )


# Short docs per tab/sub-tab — injected when the user asks "how do I use this"
# or whenever active_tab/active_subtab is provided so the model knows the surface.
_CHAT_TAB_DOCS = {
    # Main tabs (sb-link data-tab values)
    "dash":             "Home — landing page with today's regime tile, top BUY candidates, P&L summary, and quick links to all workspaces.",
    "detail":           "Ticker Detail (QuantDetail) — deep-dive on one ticker across 15 sub-tabs (Overview, Plan, Chart, Technicals, Patterns, SMC, Value, Risk, Earnings, Options, Portfolio, Intel, Track Record, ML Edge). Open by clicking any ticker card or pressing D.",
    "confluence":       "Confluence Matrix — cross-references signals/setups/sleeves to surface tickers hit by multiple independent edges. The more cells lit, the higher conviction.",
    "elite":            "Conviction Grid — 9-cell layout (3 modes × 3 stages) showing top-5 picks per cell with conviction arc, 8-factor breakdown, MC P(target/stop), CVaR, why-confident + watch-out narratives.",
    "optionsflow":      "Options Flow — UOA imbalance scanner showing tickers with abnormal call/put activity. Filters by size, premium, sweep type.",
    "earnings":         "Earnings — upcoming reports with beat-prediction tier (STRONG/SOLID/MODERATE), prior beat-rate, sector + verdict cross-ref. OWNED tag if in portfolio.",
    "scanner":          "Signal Scanner — the raw BUY/WATCH/SHORT list with 5-pillar score, R:R, gates, setup family, conviction tier. The primary every-morning view.",
    "watchlist":        "Watchlist — user-curated tickers tracked with live quotes + score + alerts. Add/remove from any ticker card.",
    "portfolio":        "Portfolio · Positions — open positions with live P&L, factor + cross-mode exposure heatmaps, closed-trade journal.",
    "positionAnalysis": "Position Analysis — per-position deep dive: stop placement vs ATR, time in trade, MAE/MFE, exit recommendation.",
    "mlEdge":           "ML Edge — 3-headed model forecast (direction · magnitude cone · hit-net P-T1-first) for every scored ticker.",
    "momentum":         "Momentum — pure-technical momentum leaderboard ranked by 21d return × RVOL × RS percentile.",
    "leaders":          "Track Record — historical win rate, profit factor, attribution by setup family from picks_history.",
    "alerts":           "Alerts — triggered price/score/regime alerts pushed via Slack + browser notifications.",
    "killed":           "Killed / AVOID — tickers rejected by hard gates (liquidity, earnings blackout, regime, tail loss). Shows WHY each was killed.",
    "performance":      "Performance — system edge verdict, P&L tiles, Setup Family Podium with Wilson CI, Score Calibration bars, auto-generated action items.",
    "screener":         "Screener — custom multi-factor screener (price, volume, fundamentals, technical filters) over the full universe.",
    "marketmap":        "Market Map — treemap visualization of SPX/NDX by sector + market cap, colored by % change.",
    "industries":       "Industries — sector + industry RS percentile leaderboard; click any to see member tickers.",
    "market":           "Market — index dashboards (SPY/QQQ/IWM/VIX), breadth, advance/decline, McClellan oscillator.",
    "macro":            "Macro · Events — calendar of FOMC, CPI, NFP, earnings season; current macro regime + credit + dollar state.",
    "premarket":        "Pre-Market — overnight gap scanner with catalysts, gap %, pre-market volume, before-bell news.",
    "events":           "IPO · Splits — upcoming IPOs, lockup expirations, stock splits, special dividends, M&A targets.",
    "crypto":           "Crypto — BTC/ETH/major-alt dashboard with derivatives data (funding, OI, basis).",
    "leveraged":        "Leveraged — leveraged + inverse ETF dashboard (TQQQ, SQQQ, SOXL etc.) with decay tracking.",
    "themes":           "Themes — long-horizon thematic baskets (AI, cybersecurity, GLP-1, nuclear, etc.) with leader rotation.",
    "strategies":       "Strategies — 7 sleeves + 1 overlay showcase with ACTIVE/DEFERRED/PLANNED states, blended WR/PF, recent picks per scanner.",
    "strategyMatrix":   "Strategy × Regime Matrix — cross-tab showing per-strategy performance in each of the 4 regimes (Wilson-gated).",
    "researchLab":      "Research Lab — what-if backtest harness for parameter tuning + setup hypothesis testing.",
    "factorExposure":   "Factor Exposure — per-setup factor loadings (MOM/VAL/SIZE/QMJ); shows alpha vs pure-factor plays.",
    "reference":        "Reference / Cheat — glossary of every term, source, and doc; the canonical lookup for any abbreviation.",
    "playbook":         "Playbook — the canonical rulebook (5 pillars, 4 regimes, conviction tiers, exit rules, daily workflow).",
    "accuracy":         "Accuracy — calibration plots showing predicted-vs-realized win rates by score bucket; surfaces drift.",
    "fields":           "Fields — every column in every table, with type, source, refresh cadence, formula.",
    "status":           "System Status — health of every pipeline (Polygon/EODHD/Zacks/Schwab), last run, error rate, latency.",
    "settings":         "Settings — user preferences (theme, layout, default mode, alert channels).",
    "users":            "Admin · Users — User Management workspace for owner role (per-user tab/sub-tab authorization).",
    "supabase":         "Admin · Supabase — Supabase sync state + table inspector.",
    "pipelines":        "Admin · Pipelines — pipeline mapping + manual trigger for each scan/job.",
    "pipeline":         "Admin · Pipeline Diagnostics — per-stage diagnostic for one ticker through the scoring pipeline.",
    "codehistory":      "Admin · Code History — recent git commits + change diff summary.",

    # QuantDetail sub-tabs (qd-st data-sub values)
    "sub:overview":   "Overview — master verdict for this ticker, regime gate, Rule Engine result, and macro drill-downs. Answer: should I look closer?",
    "sub:plan":       "Plan · Ticket — execution-ready ticket with entry/stop/T1/T2/size + pre-mortem (what would make this go wrong) + order draft.",
    "sub:chart":      "Chart — full OHLC with EMA stack, Fib levels, SMC zones, VWAP overlays. Click any tool to toggle.",
    "sub:technicals": "Technicals — 10-section discipline view: indicators, S/R, statistics, cross-source confirmation, pre-mortem, sizing recommendation.",
    "sub:patterns":   "Patterns — chart patterns detected (cup-and-handle, VCP, flag, ascending triangle, breakout-base) with completion %.",
    "sub:smc":        "SMC — Smart Money Concepts: order blocks, CHoCH, BoS, FVG, liquidity sweeps with proximity to current price.",
    "sub:value":      "Investment · Value — intrinsic value via DCF, margin of safety, raw statements, quality flags, peer cohort comparison.",
    "sub:risk":       "Risk — VaR, Sharpe, drawdown, Kelly sizing, liquidity tier, stress-test under panic regime.",
    "sub:er_lab":     "Earnings — beat-rate history, implied move, EPS revision trend, sympathy plays in the same sector.",
    "sub:options":    "Options — IV surface, max pain, UOA scan, strategy matrix (cc/csp/spread payoffs).",
    "sub:portfolio":  "Portfolio — cap usage if this ticker is added, goal contribution, rebalance suggestion.",
    "sub:intel":      "Tape · Flow — combined news + insider + sentiment + 13F + catalyst calendar for this ticker.",
    "sub:edge":       "Track Record — forward expectancy for THIS setup × regime × catalyst combo from picks_history.",
    "sub:ml_edge":    "ML Edge — 3-headed ML forecast: direction probability, magnitude cone, hit-net (P of target before stop).",
}


def _chat_message_asks_for_help(msg: str) -> bool:
    m = (msg or "").lower()
    return any(k in m for k in (
        "how do i use", "how to use", "what is this tab", "what does this",
        "what is this page", "explain this tab", "explain this page",
        "explain this sub", "what does this sub", "how do i", "what can i do",
        "what should i look", "guide me", "walk me through",
    ))


def _chat_build_context(ticker: Optional[str], message: str = "",
                        active_tab: Optional[str] = None,
                        active_subtab: Optional[str] = None) -> str:
    """Pull regime + per-ticker snapshot(s) from last_bundle.json.

    Ticker resolution order:
      1) Explicit `ticker` arg (from UI active-ticker detection)
      2) Tickers mentioned in `message` that match a real symbol in the bundle
    All hits are injected so the model has full numbers, not placeholders.
    """
    try:
        bundle_path = BASE_DIR / "cache" / "last_bundle.json"
        if not bundle_path.exists():
            return "No scan data available yet."
        bundle = json.loads(bundle_path.read_text())
    except Exception:
        return "No scan data available yet."

    parts = []
    r = bundle.get("regime") or {}
    parts.append(
        "MARKET REGIME: "
        f"{r.get('regime4', r.get('regime', 'unknown'))} | "
        f"SPY={r.get('spy_price')} (50EMA={r.get('spy_ema50')}) | "
        f"VIX={r.get('vix_current')} ({(r.get('vix') or {}).get('vol_state','?')}) | "
        f"Breadth pct>50d={r.get('breadth_pct_50d')}% | "
        f"Max size cap={r.get('max_size_pct')}% | "
        f"SPY Sharpe 126d={((r.get('spy_sharpe') or {}).get('sharpe_126d_ann'))}"
    )
    parts.append(f"Scan run: {bundle.get('run_date')} ({bundle.get('run_timestamp')})")

    buy_count = len(bundle.get("buy_candidates") or [])
    watch_count = len(bundle.get("watch_list") or [])
    parts.append(f"Today: {buy_count} BUY candidates, {watch_count} on watchlist")

    top_buys = []
    for s in (bundle.get("buy_candidates") or [])[:8]:
        top_buys.append(f"{s.get('ticker')}({s.get('score')}, {s.get('setup_family') or 'n/a'})")
    if top_buys:
        parts.append("TOP BUY CANDIDATES: " + ", ".join(top_buys))

    # Resolve which tickers to inject in full detail
    idx = _chat_collect_bundle_tickers(bundle)
    valid = set(idx.keys())
    wanted = []
    if ticker:
        t = ticker.upper().strip()
        if t:
            wanted.append(t)
    for t in _chat_extract_tickers_from_msg(message, valid):
        if t not in wanted:
            wanted.append(t)

    for t in wanted[:3]:  # cap at 3 per turn to keep prompt small
        if t in idx:
            found, source = idx[t]
            parts.append(_chat_render_ticker_block(t, found, source))
        else:
            parts.append(f"\n=== TICKER {t} NOT IN TODAY'S SCAN ===\n"
                         f"No trade plan exists. Tell the user this ticker is not in "
                         f"today's scan and you cannot provide specific entry/stop/target levels.")

    # Active-tab awareness — always tell the model what the user is looking at,
    # and inject full docs when the question is help-shaped.
    if active_tab or active_subtab:
        tab_doc = _CHAT_TAB_DOCS.get(active_tab or "") or ""
        sub_doc = _CHAT_TAB_DOCS.get(f"sub:{active_subtab}" if active_subtab else "") or ""
        line = f"\n=== USER IS CURRENTLY VIEWING ===\nMain tab: {active_tab or '-'}"
        if active_subtab:
            line += f" · Sub-tab: {active_subtab}"
        if tab_doc:
            line += f"\nTab purpose: {tab_doc}"
        if sub_doc:
            line += f"\nSub-tab purpose: {sub_doc}"
        parts.append(line)

    # If the question is help-shaped ("how do I", "explain this tab"), inject
    # the full tab+subtab description AND the global tab index so the model can
    # cross-reference ("the Plan sub-tab is where you'd get an execution-ready
    # ticket — switch to it via keyboard '2'").
    if _chat_message_asks_for_help(message):
        # Brief one-liner index of every tab so the model can suggest where to go
        idx_lines = []
        for k, v in _CHAT_TAB_DOCS.items():
            short = v.split(" — ", 1)
            short_label = short[0] if len(short) == 2 else k
            idx_lines.append(f"  {k}: {short_label}")
        parts.append("\n=== HELP INDEX (every tab + sub-tab) ===\n" + "\n".join(idx_lines))

    return "\n".join(parts)


_CHAT_SYSTEM_PROMPT = """You are Kairos, an AI assistant embedded inside a hedge-fund-grade swing-trading dashboard. The user is a sophisticated swing trader running a rules-based system with regime detection, Wilson-gated kill lists, and multi-sleeve attribution.

CRITICAL LANGUAGE RULE: Always respond in English only. Never use Chinese, Spanish, or any other language even when discussing tickers, prices, or technical terms. Every word of every response must be English.

CRITICAL NUMBERS RULE: When the user asks for entry, stop, targets, or any price levels, you MUST cite the exact dollar values from the trade plan in CONTEXT. NEVER use placeholders like $X, $Y, $Z, or generic phrases like "next resistance level" or "recent support" — those are forbidden. If the ticker is in CONTEXT, quote its actual entry/stop/T1/T2/hold-period numbers verbatim. If the ticker is NOT in today's scan (you'll see "TICKER X NOT IN TODAY'S SCAN"), say so plainly in one sentence and stop — do not fabricate a trade plan from generic rules.

Style:
- Be concise. Lead with the answer, then the why.
- Cite numbers from the provided CONTEXT. Never invent gates, scores, or sleeves not present.
- Use the user's vocabulary: regime (risk_on_trending / risk_on_choppy / risk_off / panic), pillars (Technicals, Catalyst, RS+Sector, Smart Money, Quality), sleeves (PEAD, Insider Cluster, Momentum Continuation, Defensive Rotation, Mean Reversion, ESP Play, Pre-FOMC Drift).
- When you give a trade-plan view, surface RISK before RETURN (stop before targets) per the system's hedge-fund discipline.
- No emojis unless asked. Markdown OK (bullets, tables) — keep it tight."""


@app.get("/api/chat/status")
async def chat_status():
    """Tells the widget whether AI chat is available + which model is loaded."""
    if not _chat_enabled():
        return {"enabled": False, "reason": "AI_CHAT_ENABLED=0"}
    try:
        async with _httpx_chat.AsyncClient(timeout=3.0) as cx:
            r = await cx.get(f"{_chat_ollama_url()}/api/tags")
            if r.status_code != 200:
                return {"enabled": False, "reason": "ollama not reachable"}
            tags = r.json().get("models", [])
            model = _chat_model()
            have_model = any(m.get("name", "").startswith(model.split(":")[0]) for m in tags)
            # RAG index size (0 if not built yet)
            try:
                import chat_rag
                rag_n = chat_rag.index_size()
            except Exception:
                rag_n = 0
            return {
                "enabled": True,
                "model": model,
                "model_ready": have_model,
                "available_models": [m.get("name") for m in tags],
                "rag_chunks": rag_n,
            }
    except Exception as e:
        return {"enabled": False, "reason": f"ollama error: {e}"}


@app.post("/api/chat")
async def chat_send(payload: dict = Body(...),
                    credentials: HTTPBasicCredentials = Depends(_check_auth)):
    """Stream a chat response from local Ollama.

    Request: {"message": str, "ticker": Optional[str], "history": [{role, content}]}
    Response: text/event-stream (server-sent events, each `data: {...}\\n\\n`)
    """
    if not _chat_enabled():
        raise HTTPException(503, "AI chat disabled (AI_CHAT_ENABLED=0)")
    msg = (payload.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "message required")
    ticker = payload.get("ticker")
    history = payload.get("history") or []
    active_tab = payload.get("active_tab")
    active_subtab = payload.get("active_subtab")

    context = _chat_build_context(ticker, msg, active_tab, active_subtab)

    # RAG layer — pull top-K relevant chunks from indexed docs + decision log.
    # Always-retrieve (fast: ~50ms total). Falls back to no-op if index empty.
    try:
        import chat_rag
        retrieved = chat_rag.retrieve(msg, k=5)
        if retrieved:
            rag_lines = ["\n=== RELEVANT KNOWLEDGE (from indexed docs + decision history) ==="]
            for r in retrieved:
                rag_lines.append(
                    f"\n--- {r['source']} ({r['kind']}, similarity {r['score']:.2f}) ---\n"
                    f"{r['text']}"
                )
            context += "\n".join(rag_lines)
    except Exception as _rag_err:
        # RAG failure must never break chat
        print(f"[chat] rag retrieval skipped: {_rag_err}")
    system = _CHAT_SYSTEM_PROMPT + "\n\n=== DASHBOARD CONTEXT ===\n" + context

    messages = [{"role": "system", "content": system}]
    # Cap history to last 8 turns to keep prompt small
    for h in history[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": msg})

    model = _chat_model()
    ollama_url = _chat_ollama_url()

    async def event_stream():
        try:
            async with _httpx_chat.AsyncClient(timeout=300.0) as cx:
                async with cx.stream(
                    "POST",
                    f"{ollama_url}/api/chat",
                    json={"model": model, "messages": messages, "stream": True,
                          "options": {"temperature": 0.2, "num_ctx": 8192, "repeat_penalty": 1.05}},
                ) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        yield f"data: {json.dumps({'error': f'ollama {r.status_code}: {body.decode()[:200]}'})}\n\n"
                        return
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except Exception:
                            continue
                        token = (chunk.get("message") or {}).get("content", "")
                        done = chunk.get("done", False)
                        if token:
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if done:
                            yield f"data: {json.dumps({'done': True})}\n\n"
                            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return _StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7432)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=not args.no_reload, log_level="info")
