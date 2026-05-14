# Deployment

Operational reference for the live deployment, healthcheck, and recovery procedures.

Linked from `CLAUDE.md` Path Layout.

---

## Live URL

**Live at https://trade.mystockholding.com** via Cloudflare named tunnel pointing at `localhost:7432`.

### Auth

Login: `gari` / `Swing2026` (FastAPI Basic auth — capital `S`, password is case-sensitive).

Session has a 30-min idle timeout; re-auth resets the timer.

To reset the password:
```bash
python3 -c "import auth; auth.set_password('gari', 'NEWPW')"
```

---

## Cloudflare tunnel setup

- `cloudflared` runs as a launchd daemon (`/Library/LaunchDaemons/com.cloudflare.cloudflared.plist`).
- Daemon reads `/etc/cloudflared/config.yml` (root-readable copy of `~/.cloudflared/config.yml`).
- Tunnel UUID: `53303b70-4fbb-45e5-aa28-fcfa9b54be87`.
- Credentials JSON: `~/.cloudflared/53303b70-4fbb-45e5-aa28-fcfa9b54be87.json` (mode 0400, root can still read).

## Healthcheck

`infra/healthcheck/tunnel-healthcheck.sh` runs every 5 min via `com.swingtrade.tunnel-healthcheck` user-launchd agent.

- Slack-alerts on 2 consecutive failures
- Debounces re-alerts to 1/hour
- Sends recovery message when domain comes back
- State at `/tmp/tunnel-healthcheck.state`
- Log at `/tmp/tunnel-healthcheck.log`

## Tunnel recovery

If `trade.mystockholding.com` is down (HTTP 1033 / 530), see `docs/tunnel-recovery.md` for the full diagnosis + fix runbook (plist restore, root config restore, FastAPI restart).

All fixes need sudo from a real Terminal — agent shells can't prompt for password.

---

## Active launchd agents

| Plist | Schedule | Purpose |
|---|---|---|
| `com.swingtrade.server.plist` | Boot + keep-alive | FastAPI server on port 7432 |
| `com.swingtrade.tunnel-healthcheck.plist` | Every 5 min | Tunnel uptime check + Slack alerts |
| `com.cloudflare.cloudflared.plist` | Boot | Cloudflare named tunnel |
| `com.swingtrade.morning-briefing.plist` | Mon-Fri 6:30am PT | Daily scan + Slack post |
| `com.swingtrade.weekly-diagnostics.plist` | Sunday 5pm PT | Regime + Sharpe + loss-streak diagnostics |
| `com.swingtrade.ticker-snapshots.plist` | Hourly | Live snapshot cache |
| `com.swingtrade.enrich-nightly.plist` | Nightly | Fundamental enrichment pre-warm |
| `com.swingtrade.prewarm.plist` | Nightly | OHLCV pre-warm |
| `com.swingtrade.uptime-ping.plist` | Periodic | Uptime monitoring |
