#!/usr/bin/env bash
# Emergency: cancel all open orders + market-sell all open positions.
# Use ONLY if you need to bail out right now.
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"

echo "⚠️  EMERGENCY CLOSE-ALL — you have 5 seconds to Ctrl-C."
sleep 5

cd "$SCRIPT_DIR"
"$PYTHON" << 'EOF'
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from secrets_loader import alpaca_key, alpaca_secret
c = TradingClient(alpaca_key(), alpaca_secret(), paper=True)

# Step 1: cancel all open orders
try:
    c.cancel_orders()
    print("✓ Canceled all open orders")
except Exception as e:
    print(f"  cancel_orders error: {e}")

# Step 2: market-sell all open positions
positions = c.get_all_positions()
print(f"Closing {len(positions)} open position(s):")
for p in positions:
    qty = abs(int(float(p.qty)))
    side = OrderSide.SELL if float(p.qty) > 0 else OrderSide.BUY  # short → buy to cover
    try:
        req = MarketOrderRequest(symbol=p.symbol, qty=qty, side=side, time_in_force=TimeInForce.DAY)
        resp = c.submit_order(req)
        print(f"  {p.symbol}: {side.name} {qty} → {resp.id}")
    except Exception as e:
        print(f"  {p.symbol}: FAILED — {e}")
EOF

echo ""
echo "Stop automated schedules with:"
echo "  launchctl unload ~/Library/LaunchAgents/com.swingtrade.executor.plist"
echo "  launchctl unload ~/Library/LaunchAgents/com.swingtrade.eod.plist"
echo "  launchctl unload ~/Library/LaunchAgents/com.swingtrade.fill.plist"
