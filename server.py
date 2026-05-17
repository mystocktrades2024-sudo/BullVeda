"""FastAPI-based SwingTrade server. Port 7432. Auto-reload in dev."""
from fastapi import FastAPI, HTTPException, Request, Depends
from typing import Optional  # Python 3.9 compat — Pydantic needs Optional[X] not `X | None`
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
    return RedirectResponse(url="/v2/dashboard.html")

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

# -- /kairos.html — V3 next-gen surface served at the root.
# V2 dashboard.html remains the canonical landing (the / redirect above).
# /kairos.html is the upgrade path — currently incomplete; once parity is
# reached the / redirect flips to /kairos.html.
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
  <a href="/v2/dashboard.html">→ Live V2 Dashboard</a>
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


@app.get("/api/decision-log")
async def decision_log_all_api(limit: int = 20):
    """Return the most recent N decision log entries across ALL tickers (Home Activity feed)."""
    import json
    from pathlib import Path
    log_path = Path("data/decision_log.jsonl")
    if not log_path.exists():
        return {"entries": []}
    try:
        entries = []
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
        entries.sort(key=lambda e: e.get("timestamp", ""))
        return {"entries": entries[-limit:]}
    except Exception as e:
        return {"entries": [], "error": str(e)}


@app.get("/api/decision-log/{ticker}")
async def decision_log_api(ticker: str, limit: int = 20):
    """Return the audit trail of decisions for a ticker · for Audit Trail browser.
    Reads data/decision_log.jsonl (newline-delimited JSON).
    """
    import json
    from pathlib import Path
    ticker = ticker.upper().strip()
    log_path = Path("data/decision_log.jsonl")
    if not log_path.exists():
        return {"ticker": ticker, "entries": []}
    try:
        entries = []
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if str(e.get("ticker", "")).upper() == ticker:
                        entries.append(e)
                except Exception:
                    continue
        entries.sort(key=lambda e: e.get("timestamp", ""))
        return {"ticker": ticker, "entries": entries[-limit:]}
    except Exception as e:
        return {"ticker": ticker, "entries": [], "error": str(e)}


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

    # 1 · Refresh token age (from .env or environ)
    issued = os.environ.get("SCHWAB_REFRESH_ISSUED_AT")
    if not issued:
        try:
            env_path = _P(__file__).resolve().parent / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("SCHWAB_REFRESH_ISSUED_AT="):
                        issued = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
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
    {"name": "Stop level history",            "source_type": "future",   "source_path": "executor.py stop adjustments",                    "target_table": "stop_levels_history",        "script": "(needs sb_client write hook)",          "schedule": "real-time",                 "status": "empty",   "cluster": "execution", "issue": "Requires editing executor.py — production order path, deferred"},
    {"name": "Realized slippage",             "source_type": "future",   "source_path": "executor.py order fills vs expected",             "target_table": "slippage_realized",          "script": "(needs sb_client write hook)",          "schedule": "real-time",                 "status": "empty",   "cluster": "execution", "issue": "Requires editing executor.py — production order path, deferred"},
    {"name": "VaR breaches",                  "source_type": "computed", "source_path": "portfolio_risk_history + equity_curve",            "target_table": "var_breaches",               "script": "snapshot_var_breaches.py",              "schedule": "com.swingtrade.snapshot-var (Mon-Fri 4:55pm PT)",      "status": "empty",   "cluster": "risk", "issue": "Needs at least 2 days of portfolio_risk snapshots; first breach row appears after a real drawdown day"},
    {"name": "Signal filter decisions (A2)",  "source_type": "future",   "source_path": "signal_filter.py per-decision audit",              "target_table": "signal_filter_decisions",    "script": "(needs sb_client write hook)",          "schedule": "daily scan",                "status": "empty",   "cluster": "journal", "issue": "Requires editing signal_filter.py — production scan path, deferred"},
    {"name": "Strategy PnL attribution",      "source_type": "computed", "source_path": "picks_history.json#trades by setup_family",        "target_table": "strategy_pnl_attribution",   "script": "snapshot_strategy_attribution.py",      "schedule": "com.swingtrade.snapshot-attribution (Mon-Fri 4:45pm PT)", "status": "working", "cluster": "attribution"},
    {"name": "Wilson CI snapshot",            "source_type": "computed", "source_path": "picks_history.json#trades per cell",               "target_table": "wilson_ci_snapshot",         "script": "snapshot_wilson_ci.py",                 "schedule": "com.swingtrade.snapshot-wilson (Mon-Fri 4:50pm PT)",   "status": "working", "cluster": "calibration"},
    {"name": "Kelly size history",            "source_type": "future",   "source_path": "analysis.kelly_position_size() inputs",            "target_table": "kelly_size_history",         "script": "(needs sb_client write hook)",          "schedule": "per-entry",                 "status": "empty",   "cluster": "risk", "issue": "Requires editing analysis.py — production scan path, deferred"},
    {"name": "SMC hit rates",                 "source_type": "json",     "source_path": "data/smc_hit_rates.json",                          "target_table": "smc_hit_rates",              "script": "fold_orphan_data.py",                   "schedule": "manual",                    "status": "working", "cluster": "calibration"},
    {"name": "Regime transitions",            "source_type": "json",     "source_path": "cache/regime_history.json",                        "target_table": "regime_transitions",         "script": "fold_orphan_data.py",                   "schedule": "manual",                    "status": "working", "cluster": "regime"},
    {"name": "Watch triggers",                "source_type": "future",   "source_path": "watch alert engine output",                        "target_table": "watch_triggers",             "script": "(needs sb_client write hook)",          "schedule": "real-time",                 "status": "empty",   "cluster": "watchlist", "issue": "Requires watch alert engine to emit events — engine doesn't currently fire/persist these"},

    # ── Future scrapers (free data, not yet implemented) ──
    {"name": "Insider transactions (Form 4)", "source_type": "future",   "source_path": "efts.sec.gov EDGAR full-text search",              "target_table": "insider_transactions",       "script": "scrapers/insider_form4.py (TODO)",      "schedule": "daily",                     "status": "future",  "cluster": "smart_money", "issue": "SEC EDGAR full-text API + Form 4 XBRL/XML parsing is non-trivial — deferred"},
    {"name": "13F institutional holdings",    "source_type": "future",   "source_path": "efts.sec.gov 13F filings",                         "target_table": "institutional_holdings",     "script": "scrapers/institutional_13f.py (TODO)",  "schedule": "quarterly",                 "status": "future",  "cluster": "smart_money", "issue": "Same as Form 4 — SEC EDGAR XBRL parsing complexity, deferred"},
    {"name": "Short interest history",        "source_type": "api",      "source_path": "cdn.finra.org regsho daily CNMSshvol",             "target_table": "short_interest_history",     "script": "scrapers/short_interest_finra.py",      "schedule": "daily (T+2)",               "status": "working", "cluster": "smart_money"},
    {"name": "Cold OHLCV storage",            "source_type": "api",      "source_path": "EODHD /eod/{TICKER} for active tickers",           "target_table": "ohlcv_daily",                "script": "scrapers/ohlcv_cold_storage.py",        "schedule": "nightly batch",             "status": "working", "cluster": "market_data"},
    {"name": "Tickers master",                "source_type": "api",      "source_path": "EODHD /exchange-symbol-list/US",                   "target_table": "tickers_master",             "script": "scrapers/tickers_master_eodhd.py",      "schedule": "weekly",                    "status": "working", "cluster": "reference"},
    {"name": "News events",                   "source_type": "api",      "source_path": "EODHD /news per active ticker",                    "target_table": "news_events",                "script": "scrapers/news_events_eodhd.py",         "schedule": "hourly",                    "status": "working", "cluster": "sentiment"},
    {"name": "IPO calendar",                  "source_type": "api",      "source_path": "api.nasdaq.com /api/ipo/calendar",                 "target_table": "ipo_calendar",               "script": "scrapers/ipo_calendar_nasdaq.py",       "schedule": "daily",                     "status": "broken",  "cluster": "calendar", "issue": "NASDAQ API timing out — needs proxy or different headers; intermittent"},
    {"name": "Splits calendar",               "source_type": "computed", "source_path": "derived from corporate_actions WHERE type=split",  "target_table": "splits_calendar",            "script": "scrapers/splits_calendar_derived.py",   "schedule": "daily",                     "status": "empty",   "cluster": "calendar", "issue": "Source corporate_actions has 0 splits — need to expand corporate_actions universe beyond active 9 tickers"},
    {"name": "Economic calendar",             "source_type": "future",   "source_path": "fred.stlouisfed.org API or BLS RSS",               "target_table": "economic_calendar",          "script": "scrapers/economic_calendar.py (TODO)",  "schedule": "daily",                     "status": "future",  "cluster": "calendar", "issue": "FRED API requires (free) API key registration — pending setup"},
    {"name": "FDA PDUFA calendar",            "source_type": "future",   "source_path": "fda.gov + biotech disclosure scrape",              "target_table": "fda_calendar",               "script": "scrapers/fda_calendar.py (TODO)",       "schedule": "weekly",                    "status": "future",  "cluster": "calendar", "issue": "FDA + biotech catalyst aggregation is complex multi-source scrape — deferred"},
    {"name": "Earnings calendar PIT",         "source_type": "future",   "source_path": "Zacks (existing scraper) → vintage layer",         "target_table": "earnings_calendar_pit",      "script": "(needs vintage tracker layer)",         "schedule": "daily",                     "status": "future",  "cluster": "calendar", "issue": "Requires intercepting existing Zacks scraper output + tracking changes over time (vintage layer)"},

    # ── Ops telemetry (needs app-side instrumentation) ──
    {"name": "EODHD quota usage",             "source_type": "future",   "source_path": "data_fetcher.py rate-limit counters",              "target_table": "eodhd_quota_usage",          "script": "(needs middleware hook)",               "schedule": "real-time",                 "status": "future",  "cluster": "ops", "issue": "Requires patching data_fetcher.py to count requests per endpoint — production data path, deferred"},
    {"name": "Launchd run telemetry",         "source_type": "future",   "source_path": "wrapper around launchd plists",                    "target_table": "launchd_runs",               "script": "(needs wrapper script)",                "schedule": "every plist firing",        "status": "future",  "cluster": "ops", "issue": "Requires shell wrapper around every plist's ProgramArguments — touches all 25 plists, deferred"},
    {"name": "Data quality checks",           "source_type": "future",   "source_path": "scripts/dq_checks.py (TODO)",                       "target_table": "data_quality_checks",        "script": "scripts/dq_checks.py (TODO)",           "schedule": "daily",                     "status": "future",  "cluster": "ops", "issue": "DQ rule definition + scoring pending — needs design pass on what to check"},
    {"name": "Config history",                "source_type": "future",   "source_path": "git diff on config/*.json",                         "target_table": "config_history",             "script": "(needs git hook)",                      "schedule": "on commit",                 "status": "future",  "cluster": "ops", "issue": "Requires post-commit git hook + jsondiffpatch — small but touches dev workflow, deferred"},
    {"name": "Feature flag changes",          "source_type": "future",   "source_path": "config/config.json _enabled flips",                "target_table": "feature_flag_changes",       "script": "(needs git hook)",                      "schedule": "on commit",                 "status": "future",  "cluster": "ops", "issue": "Same git hook as config_history"},
    {"name": "API latency metrics",           "source_type": "future",   "source_path": "FastAPI middleware",                                "target_table": "api_latency_metrics",        "script": "(needs middleware)",                    "schedule": "real-time",                 "status": "future",  "cluster": "ops", "issue": "Requires FastAPI middleware emitting per-request latency to Supabase — touches server.py request path, deferred for perf"},

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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7432)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=not args.no_reload, log_level="info")
