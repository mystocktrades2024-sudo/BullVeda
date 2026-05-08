"""
audit_log.py — append-only JSONL log of state-changing API actions.

Every write endpoint (gated by _require_action in server.py) calls
log_action() so we have a forensic trail of who did what, when. Append-only
JSONL is the simplest crash-safe format; one line per event, keep forever.

Storage:
  data/audit_log.jsonl   — production log (rotated weekly when >50MB)

Schema:
  {ts, user, action, endpoint, method, payload, ip, user_agent, status, error}

  ts          ISO8601 UTC
  user        username from credentials
  action      semantic action key ("submit_trade", "close_position", ...)
  endpoint    request path
  method      POST / PUT / DELETE
  payload     request body (truncated at 2KB; passwords masked)
  ip          client IP
  user_agent  truncated to 100 chars
  status      "ok" | "denied" | "error"
  error       optional message on failure

Reads:
  list_recent(limit, user, action, since_iso)  for /api/audit_log endpoint
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_LOG_PATH = Path(__file__).resolve().parent / "data" / "audit_log.jsonl"
_MAX_PAYLOAD_BYTES = 2048
_ROTATE_AT_BYTES = 50 * 1024 * 1024  # 50MB


def _scrub_payload(payload: Any) -> Any:
    """Mask credential-shaped fields. Truncate to size cap."""
    if not isinstance(payload, dict):
        s = str(payload)
        return s[:_MAX_PAYLOAD_BYTES] + ("…" if len(s) > _MAX_PAYLOAD_BYTES else "")
    out = {}
    for k, v in payload.items():
        kl = k.lower()
        if any(s in kl for s in ("password", "token", "secret", "api_key", "webhook")):
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _scrub_payload(v)
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    s = json.dumps(out, default=str)
    if len(s) > _MAX_PAYLOAD_BYTES:
        return {"_truncated": True, "_size": len(s), "_head": s[:_MAX_PAYLOAD_BYTES]}
    return out


def _maybe_rotate() -> None:
    if not _LOG_PATH.exists():
        return
    if _LOG_PATH.stat().st_size < _ROTATE_AT_BYTES:
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rotated = _LOG_PATH.with_suffix(f".{ts}.jsonl")
    _LOG_PATH.rename(rotated)
    log.info(f"audit_log rotated: {rotated.name}")


def log_action(*, user: str, action: str, endpoint: str, method: str = "POST",
               payload: Any = None, ip: str = "", user_agent: str = "",
               status: str = "ok", error: Optional[str] = None) -> None:
    """Write one event to the audit log. Never raises (best-effort write)."""
    try:
        _maybe_rotate()
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts":         datetime.now(timezone.utc).isoformat(),
            "user":       user or "?",
            "action":     action,
            "endpoint":   endpoint,
            "method":     method,
            "payload":    _scrub_payload(payload) if payload is not None else None,
            "ip":         ip,
            "user_agent": (user_agent or "")[:100],
            "status":     status,
            "error":      error,
        }
        with _LOG_PATH.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        log.warning(f"audit_log write failed (non-fatal): {e}")


def list_recent(limit: int = 100, user: Optional[str] = None,
                action: Optional[str] = None,
                since_iso: Optional[str] = None) -> list[dict]:
    """Tail the log file, newest first. Filtered + capped."""
    if not _LOG_PATH.exists():
        return []
    out: list[dict] = []
    try:
        # Read tail efficiently — mmap-style would be ideal; fine to fully scan
        # while file is <50MB (we rotate before that).
        with _LOG_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if user and e.get("user") != user:
                    continue
                if action and e.get("action") != action:
                    continue
                if since_iso and e.get("ts", "") < since_iso:
                    continue
                out.append(e)
    except Exception as e:
        log.warning(f"audit_log read failed: {e}")
        return []
    return list(reversed(out))[:limit]
