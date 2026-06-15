"""
schwab_auth.py — Schwab Individual Trader API OAuth2 helper + token manager.

One-time setup (interactive):
    python3 schwab_auth.py oauth
    # Opens browser → you log in + approve → paste redirect URL back
    # Writes SCHWAB_REFRESH_TOKEN to .env

Regular use (programmatic):
    from schwab_auth import get_access_token
    token = get_access_token()   # auto-refreshes if expired

Smoke tests:
    python3 schwab_auth.py test           # verify quote endpoint works
    python3 schwab_auth.py user_pref      # pull user preferences (needed for streamer)
    python3 schwab_auth.py entitlement    # report real-time vs delayed status

Schwab OAuth2 flow (authorization_code, PKCE-less):
    1. Redirect user to https://api.schwabapi.com/v1/oauth/authorize?...
    2. User approves → Schwab redirects to callback URL with ?code=...
    3. POST code to /v1/oauth/token → {access_token, refresh_token}
    4. access_token expires in 1800s (30min); refresh for new one
    5. refresh_token expires in 7 days — must be re-OAuth'd after that
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"

AUTH_URL  = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
API_BASE  = "https://api.schwabapi.com"

# Process-local lock for _write_env and token refresh coordination.
# Prevents multiple threads in the same scan process from racing to
# truncate .env (historical corruption: 2026-04-24 07:52).
_ENV_LOCK = threading.RLock()
_REFRESH_LOCK = threading.Lock()


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    # Shared lock on read so we don't observe a partial write in progress.
    try:
        with open(ENV_PATH, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                content = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        content = ENV_PATH.read_text()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def _write_env(updates: dict[str, str]) -> None:
    """Update or add keys in .env — preserves comments & order.

    Thread-safe & crash-safe:
      - threading lock prevents two threads in this process from racing
      - fcntl.flock(LOCK_EX) prevents two processes from racing
      - tempfile + os.replace gives atomic swap (no truncated .env if we crash)
    """
    with _ENV_LOCK:
        # Open/create the file and acquire an exclusive advisory lock. All
        # concurrent readers/writers in this process or others will block
        # behind this section. The lock is auto-released when f is closed.
        ENV_PATH.touch(exist_ok=True)
        with open(ENV_PATH, "r") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            try:
                # Re-read the file inside the lock so we merge against the
                # latest on-disk state, not a stale snapshot from before we
                # acquired the lock.
                lines = lockf.read().splitlines()
                seen = set()
                out = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        out.append(line); continue
                    k = stripped.split("=", 1)[0].strip()
                    if k in updates:
                        out.append(f"{k}={updates[k]}")
                        seen.add(k)
                    else:
                        out.append(line)
                for k, v in updates.items():
                    if k not in seen:
                        out.append(f"{k}={v}")
                # Atomic swap: write to .env.tmp-<pid> then rename over .env.
                # Keeps the file intact if we crash mid-write.
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(ENV_PATH.parent),
                    prefix=".env.tmp.",
                )
                try:
                    with os.fdopen(fd, "w") as tf:
                        tf.write("\n".join(out) + "\n")
                    os.replace(tmp_path, ENV_PATH)
                    os.chmod(ENV_PATH, 0o600)
                except Exception:
                    try: os.unlink(tmp_path)
                    except FileNotFoundError: pass
                    raise
            finally:
                fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def _creds() -> tuple[str, str, str]:
    env = _read_env()
    key    = env.get("SCHWAB_APP_KEY", "")
    secret = env.get("SCHWAB_APP_SECRET", "")
    cb     = env.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    if not key or not secret:
        sys.exit("ERROR: SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in .env")
    return key, secret, cb


def _basic_auth_header(key: str, secret: str) -> str:
    b64 = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return f"Basic {b64}"


# ── One-time OAuth handshake ────────────────────────────────────────────
def oauth_interactive() -> None:
    key, secret, cb = _creds()
    params = {"response_type": "code", "client_id": key, "redirect_uri": cb, "scope": "readonly"}
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("\n" + "=" * 70)
    print("SCHWAB OAUTH — ONE-TIME HANDSHAKE")
    print("=" * 70)
    print("\n1. A browser tab will open.")
    print("2. Log in with your Schwab credentials.")
    print("3. Approve the app.")
    print("4. Your browser will be redirected to a URL starting with:")
    print(f"   {cb}/?code=...")
    print("   (The page will likely show a connection error — that's normal.)")
    print("5. Copy the ENTIRE redirected URL from the address bar.")
    print("6. Paste it below.\n")
    print(f"Auth URL:\n{auth_url}\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    redirected = input("Paste the redirected URL here: ").strip()
    if not redirected:
        sys.exit("ERROR: no URL provided")

    # Extract ?code=... (URL-encoded; sometimes ?code=...&session=...)
    parsed = urllib.parse.urlparse(redirected)
    qs     = urllib.parse.parse_qs(parsed.query)
    code   = qs.get("code", [None])[0]
    if not code:
        sys.exit(f"ERROR: could not find ?code= in URL: {redirected}")

    # Schwab requires the code URL-decoded but wants it passed as-is from the callback.
    # The received code is already decoded by parse_qs.

    print(f"\n✓ Got authorization code ({code[:10]}...{code[-4:]})")
    print("→ Exchanging for access + refresh tokens...")

    r = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(key, secret),
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": cb},
        timeout=15,
    )
    if r.status_code != 200:
        sys.exit(f"ERROR token exchange failed: HTTP {r.status_code}\n{r.text}")

    tok = r.json()
    access  = tok["access_token"]
    refresh = tok["refresh_token"]
    exp_in  = int(tok.get("expires_in", 1800))
    exp_at  = int(time.time()) + exp_in - 60  # 60s buffer

    _write_env({
        "SCHWAB_ACCESS_TOKEN":       access,
        "SCHWAB_REFRESH_TOKEN":      refresh,
        "SCHWAB_TOKEN_EXPIRES_AT":   str(exp_at),
        "SCHWAB_REFRESH_ISSUED_AT":   str(int(time.time())),
    })

    print("\n✅ SUCCESS")
    print(f"   Access token:  {access[:12]}... (expires in {exp_in}s)")
    print(f"   Refresh token: {refresh[:12]}... (valid 7 days)")
    print(f"   Stored in:     .env (mode 600)")
    print("\nNext: python3 schwab_auth.py test")


# ── Programmatic access ─────────────────────────────────────────────────
def _refresh_access_token() -> str:
    key, secret, _ = _creds()
    env = _read_env()
    refresh = env.get("SCHWAB_REFRESH_TOKEN", "")
    if not refresh:
        sys.exit("ERROR: no refresh token. Run: python3 schwab_auth.py oauth")

    r = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(key, secret),
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh},
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"refresh failed (HTTP {r.status_code}): {r.text}\n"
            f"Refresh tokens expire after 7 days — re-run: python3 schwab_auth.py oauth"
        )

    tok = r.json()
    access = tok["access_token"]
    exp_in = int(tok.get("expires_in", 1800))
    exp_at = int(time.time()) + exp_in - 60

    # Schwab may also rotate the refresh token. When they do, reset
    # SCHWAB_REFRESH_ISSUED_AT so check_token_health() tracks the freshest
    # 7-day window from the actual rotation, not the original OAuth.
    updates = {
        "SCHWAB_ACCESS_TOKEN":     access,
        "SCHWAB_TOKEN_EXPIRES_AT": str(exp_at),
    }
    if tok.get("refresh_token"):
        updates["SCHWAB_REFRESH_TOKEN"]    = tok["refresh_token"]
        updates["SCHWAB_REFRESH_ISSUED_AT"] = str(int(time.time()))
    _write_env(updates)
    return access


def get_access_token() -> str:
    """Return a valid access token, refreshing if within 60s of expiry.

    Serialized via _REFRESH_LOCK so parallel scan workers don't each trigger
    a refresh. The first thread to notice expiry refreshes; the rest wait,
    then re-read the freshly written token.
    """
    env = _read_env()
    access = env.get("SCHWAB_ACCESS_TOKEN", "")
    try:
        exp_at = int(env.get("SCHWAB_TOKEN_EXPIRES_AT", "0"))
    except ValueError:
        exp_at = 0
    if access and time.time() < exp_at:
        return access

    # Need a refresh. Only one thread at a time — others wait and re-check.
    with _REFRESH_LOCK:
        env = _read_env()
        access = env.get("SCHWAB_ACCESS_TOKEN", "")
        try:
            exp_at = int(env.get("SCHWAB_TOKEN_EXPIRES_AT", "0"))
        except ValueError:
            exp_at = 0
        if access and time.time() < exp_at:
            # Another thread refreshed while we waited on the lock.
            return access
        return _refresh_access_token()


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}", "Accept": "application/json"}


# ── Smoke tests ─────────────────────────────────────────────────────────
def test_quote(symbol: str = "AAPL") -> None:
    print(f"Pulling live quote for {symbol}...")
    r = requests.get(
        f"{API_BASE}/marketdata/v1/{symbol}/quotes",
        headers=_headers(),
        timeout=10,
    )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500]); return
    data = r.json()
    # Response shape: {"AAPL": {quote: {...}, fundamental: {...}, ...}}
    for tk, blob in data.items():
        q = blob.get("quote", {})
        f = blob.get("fundamental", {})
        print(f"\n✅ {tk} — {blob.get('assetMainType')}/{blob.get('assetSubType')}")
        print(f"   Last: ${q.get('lastPrice')}  Bid: ${q.get('bidPrice')}  Ask: ${q.get('askPrice')}")
        print(f"   Volume: {q.get('totalVolume'):,}  52w: ${f.get('low52')}–${f.get('high52')}")
        mcap = f.get("marketCap")
        mcap_str = f"${mcap:,.0f}" if mcap is not None else "—"
        print(f"   PE: {f.get('peRatio')}  EPS: {f.get('eps')}  Mcap: {mcap_str}")
        print(f"   Beta: {f.get('beta')}  Div yield: {f.get('dividendYield')}%  Delayed: {q.get('quoteTime', 0) > 0 and bool(blob.get('delayed', False))}")


def test_user_pref() -> None:
    """Fetch /userPreference — required for Streamer (gets customerId + correlId)."""
    print("Pulling user preferences (for Streamer setup)...")
    r = requests.get(f"{API_BASE}/trader/v1/userPreference", headers=_headers(), timeout=10)
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500]); return
    data = r.json()
    # Extract streamer config
    streamer_info = data.get("streamerInfo", [])
    if streamer_info:
        info = streamer_info[0]
        print("\n✅ Streamer credentials:")
        print(f"   schwabClientCustomerId: {info.get('schwabClientCustomerId','')}")
        print(f"   schwabClientCorrelId:   {info.get('schwabClientCorrelId','')}")
        print(f"   streamerSocketUrl:      {info.get('streamerSocketUrl','')}")
        print(f"   schwabClientChannel:    {info.get('schwabClientChannel','')}")
        print(f"   schwabClientFunctionId: {info.get('schwabClientFunctionId','')}")
    accounts = data.get("accounts", [])
    print(f"\n✅ {len(accounts)} account(s) visible")
    for a in accounts:
        print(f"   {a.get('accountNumber')}  type={a.get('type')}  primary={a.get('primaryAccount')}  nickname={a.get('nickName')}")


def test_entitlement() -> None:
    """Best proxy for real-time vs delayed: check quote response for `delayed` field."""
    r = requests.get(f"{API_BASE}/marketdata/v1/AAPL/quotes", headers=_headers(), timeout=10)
    if r.status_code != 200:
        print(f"HTTP {r.status_code} — {r.text[:200]}"); return
    data = r.json()
    for tk, blob in data.items():
        delayed = blob.get("quote", {}).get("delayed", blob.get("delayed", None))
        qt = blob.get("quote", {}).get("quoteTime", 0)
        age_s = (time.time() * 1000 - qt) / 1000 if qt else None
        print(f"{tk}: delayed={delayed}, quote age {age_s:.0f}s ago" if age_s is not None else f"{tk}: delayed={delayed}")


# ── Token health probe (2026-05-22) ─────────────────────────────────────
def check_token_health(warn_days: int = 5, dead_days: int = 7) -> dict:
    """Return refresh-token health WITHOUT making a network call.

    Schwab rotates the refresh token on each access-token refresh (~30min
    when the scanner is running). The 7-day expiry resets to that rotation
    timestamp, tracked in SCHWAB_REFRESH_ISSUED_AT (written by
    _refresh_access_token + oauth_interactive). If the scanner stops for >7d
    the refresh token rots and only manual re-OAuth recovers it.

    Returns dict {status, days_since_saved, message, action}:
      status   : 'ok' | 'warn' | 'dead' | 'unknown'
      action   : None | 'reauth_soon' | 'reauth_now'
    """
    env = _read_env()
    refresh = env.get("SCHWAB_REFRESH_TOKEN", "").strip()
    saved   = env.get("SCHWAB_REFRESH_ISSUED_AT", "").strip()
    if not refresh:
        return {"status": "dead", "days_since_saved": None, "action": "reauth_now",
                "message": "No SCHWAB_REFRESH_TOKEN in .env — run: python3 schwab_auth.py oauth"}
    if not saved or not saved.isdigit():
        # Token present but no saved-at timestamp (pre-2026-05-22 install).
        # Treat as unknown — first successful refresh will populate it.
        return {"status": "unknown", "days_since_saved": None, "action": None,
                "message": "Refresh token present but no save timestamp — will populate on next refresh"}
    age_s = int(time.time()) - int(saved)
    age_d = age_s / 86400.0
    if age_d >= dead_days:
        return {"status": "dead", "days_since_saved": round(age_d, 1), "action": "reauth_now",
                "message": f"Refresh token is {age_d:.1f} days old (>{dead_days}d limit) — likely expired. "
                           f"Schwab calls will fail with HTTP 400 'Refresh token invalid'. "
                           f"Run: python3 schwab_auth.py oauth"}
    if age_d >= warn_days:
        return {"status": "warn", "days_since_saved": round(age_d, 1), "action": "reauth_soon",
                "message": f"Refresh token is {age_d:.1f} days old — re-auth before {dead_days}d to avoid downtime. "
                           f"Run: python3 schwab_auth.py oauth"}
    return {"status": "ok", "days_since_saved": round(age_d, 1), "action": None,
            "message": f"Refresh token age {age_d:.1f}d (OK)"}


# ── CLI ─────────────────────────────────────────────────────────────────
def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "oauth":
        oauth_interactive()
    elif cmd == "test":
        symbol = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
        test_quote(symbol)
    elif cmd == "user_pref":
        test_user_pref()
    elif cmd == "entitlement":
        test_entitlement()
    elif cmd == "refresh":
        print(f"New access token: {_refresh_access_token()[:20]}...")
    elif cmd == "health":
        h = check_token_health()
        icon = {"ok":"✅","warn":"🟡","dead":"🔴","unknown":"⚪"}.get(h["status"], "?")
        print(f"{icon}  {h['status'].upper():<8} {h['message']}")
        sys.exit(0 if h['status'] in ('ok','unknown') else 1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
