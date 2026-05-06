#!/bin/zsh
# SwingTrade Cloudflare Tunnel — auto-restart + Slack notification
# Runs the NAMED tunnel from ~/.cloudflared/config.yml so the public hostname
# (trade.mystockholding.com) stays stable across restarts.
LOG="/tmp/cloudflared.log"
URL="https://trade.mystockholding.com"
SLACK_WEBHOOK=$(grep SLACK_WEBHOOK_URL "/Volumes/MyMacDisk/Claude Skills/SwingTrade/.env" 2>/dev/null | cut -d= -f2-)

while true; do
    echo "$(date): Starting named tunnel (trade.mystockholding.com)..." >> "$LOG"
    cloudflared tunnel --config "$HOME/.cloudflared/config.yml" run >> "$LOG" 2>&1 &
    CPID=$!
    sleep 5

    echo "$(date): Tunnel URL: $URL" >> "$LOG"

    # Send to Slack
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -s -X POST "$SLACK_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"🌐 SwingTrade tunnel restarted\\nURL: $URL\\nLogin: gari / swing2026\"}" \
            >> "$LOG" 2>&1
    fi

    # Wait for tunnel to die
    wait $CPID
    echo "$(date): Tunnel died, restarting in 5s..." >> "$LOG"
    sleep 5
done
