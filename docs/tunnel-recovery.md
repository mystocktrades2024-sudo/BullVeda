# Cloudflare Tunnel Recovery Runbook

Use when **https://trade.mystockholding.com** is down (HTTP 1033 = tunnel not registered, or 530 = origin error).

---

## Diagnosis — run these to pinpoint

```
ps -p $(pgrep cloudflared 2>/dev/null | head -1) -o command=  # should show: cloudflared --config /etc/cloudflared/config.yml tunnel run
cat /etc/cloudflared/config.yml                                # should NOT be empty
tail -10 /Library/Logs/com.cloudflare.cloudflared.err.log     # check what daemon is complaining about
curl -sI https://trade.mystockholding.com/ | head -3
```

---

## Common failure modes & fixes

All fixes need sudo, run from Terminal.

### 1. Plist corrupted

`cloudflared` running with no args, error log says "Use `cloudflared tunnel run`":

```
sudo cp "/Volumes/MyMacDisk/Claude Skills/SwingTrade/infra/launchd/com.cloudflare.cloudflared.plist" /Library/LaunchDaemons/
sudo launchctl unload /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
sudo launchctl load /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
```

### 2. Root config missing or empty

`/etc/cloudflared/config.yml` doesn't exist:

```
sudo mkdir -p /etc/cloudflared
sudo cp "/Volumes/MyMacDisk/Claude Skills/SwingTrade/infra/cloudflared/config.yml" /etc/cloudflared/config.yml
sudo launchctl unload /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
sudo launchctl load /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
```

### 3. FastAPI server itself down

`localhost:7432` returns nothing — restart `python3 server.py --no-reload`.

---

## Verify recovery

`curl -sI https://trade.mystockholding.com/` should return `HTTP/2 401` (Basic auth challenge from FastAPI = origin reachable).

---

## Pitfalls to avoid

- Don't run `cloudflared service install` — it produces a malformed plist with empty `ProgramArguments`. Always copy the snapshot from `infra/launchd/`.
- Don't run `cloudflared tunnel --url ...` (the old broken `start-tunnel.sh` pattern). That creates an *ephemeral* `*.trycloudflare.com` URL and ignores the named-tunnel config — the public domain stays dead.
- Don't try to fix this from a Claude/agent shell — sudo can't prompt for password through `!` shell prefix. Always real Terminal.

---

## Topology reference

- cloudflared runs as a launchd daemon (`/Library/LaunchDaemons/com.cloudflare.cloudflared.plist`).
- Daemon reads `/etc/cloudflared/config.yml` (root-readable copy of `~/.cloudflared/config.yml`).
- Tunnel UUID: `53303b70-4fbb-45e5-aa28-fcfa9b54be87`.
- Credentials JSON: `~/.cloudflared/53303b70-4fbb-45e5-aa28-fcfa9b54be87.json` (mode 0400, root can still read).
- Healthcheck: `infra/healthcheck/tunnel-healthcheck.sh` runs every 5 min via `com.swingtrade.tunnel-healthcheck` user-launchd agent. Slack-alerts on 2 consecutive failures, debounces re-alerts to 1/hour, sends recovery message when domain comes back. State at `/tmp/tunnel-healthcheck.state`, log at `/tmp/tunnel-healthcheck.log`.
