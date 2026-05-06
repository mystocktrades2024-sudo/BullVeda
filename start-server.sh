#!/bin/bash
# SwingTrade Server Launcher
# Start the portfolio/timeframe API server on port 7432
# Auto-restarts on crash, keeps running in background

cd "$(dirname "$0")"

# Kill any existing server
pkill -f "python3 server.py" 2>/dev/null

# Start in background with auto-restart on crash
while true; do
  echo "[$(date +'%H:%M:%S')] Starting SwingTrade server on http://localhost:7432"
  python3 server.py
  echo "[$(date +'%H:%M:%S')] Server stopped. Restarting in 3 seconds..."
  sleep 3
done &

SERVER_PID=$!
echo "Server started (PID: $SERVER_PID)"
echo ""
echo "Dashboard: http://localhost:7432/dashboard"
echo "Portfolio API: http://localhost:7432/api/portfolio"
echo "Timeframe API: http://localhost:7432/api/timeframe/{TICKER}"
echo ""
echo "To stop: pkill -f 'python3 server.py'"
echo ""

# Keep script alive
wait $SERVER_PID
