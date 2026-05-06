/**
 * ws-live.js — EODHD WebSocket real-time price feed
 * Connects to wss://ws.eodhd.com/ws/us for sub-second US equity ticks.
 * Falls back to HTTP polling if WS is unavailable.
 *
 * Usage:
 *   <script src="./ws-live.js"></script>
 *   WS_LIVE.subscribe(['AAPL','MSFT'], (ticker, price, change) => { ... });
 */

const WS_LIVE = (() => {
  let ws = null;
  let apiKey = null;
  let _pollIntervalId = null;
  let subscribed = new Set();
  const handlers = [];
  let lastPrices = {};
  let reconnectDelay = 2000;
  let statusEl = null;
  let usePoll = false;

  function setStatus(text, ok = true) {
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = ok ? 'var(--pass, #22c55e)' : 'var(--warn, #f59e0b)';
    }
  }

  async function getApiKey() {
    // Server-side token endpoint keeps API key out of JS
    try {
      const r = await fetch('/api/live/ws-token', { signal: AbortSignal.timeout(3000) });
      if (r.ok) {
        const d = await r.json();
        return d.token || d.api_key || d.key;
      }
    } catch (_) {}
    return null;
  }

  // EODHD WebSocket is a separate paid add-on (~$30/mo) NOT included in
  // All-In-One. After 1 failed attempt we permanently switch to polling
  // to silence console spam. Set wsAttempted=false to retry on a session.
  let wsAttempted = false;
  let wsFailedPermanently = false;

  function connect() {
    if (usePoll || wsFailedPermanently || !apiKey || subscribed.size === 0) return;
    if (ws && ws.readyState === WebSocket.CONNECTING) return;
    if (wsAttempted) return;  // one attempt per page load
    wsAttempted = true;

    const url = `wss://ws.eodhd.com/ws/us?api_token=${apiKey}`;
    try {
      ws = new WebSocket(url);
    } catch (_) {
      wsFailedPermanently = true;
      usePoll = true;
      setStatus('Polling (WS unavailable)', false);
      pollFallback();
      if (!_pollIntervalId) _pollIntervalId = setInterval(pollFallback, 5000);
      return;
    }
    setStatus('Connecting…', true);

    ws.onopen = () => {
      reconnectDelay = 2000;
      setStatus('LIVE ●', true);
      subscribed.forEach(sym => {
        try { ws.send(JSON.stringify({ action: 'subscribe', symbols: sym })); } catch (_) {}
      });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.s && data.p != null) {
          const ticker = data.s;
          const price = parseFloat(data.p);
          const prev = lastPrices[ticker];
          lastPrices[ticker] = price;
          const chgPct = prev ? ((price - prev) / prev * 100) : 0;
          handlers.forEach(h => h(ticker, price, chgPct, data));
        }
      } catch (_) {}
    };

    ws.onerror = () => {
      // Fail silently — EODHD WS requires separate subscription. Switch to
      // polling permanently for this session to avoid noisy reconnect loop.
      wsFailedPermanently = true;
      usePoll = true;
      setStatus('Polling (WS not subscribed)', false);
      try { ws.close(); } catch (_) {}
      pollFallback();
      // Critical fix: set up RECURRING polling, not just one-shot
      if (!_pollIntervalId) _pollIntervalId = setInterval(pollFallback, 5000);
    };

    ws.onclose = () => {
      if (!usePoll && !wsFailedPermanently) {
        setStatus(`Reconnecting in ${reconnectDelay/1000}s…`, false);
        setTimeout(() => { reconnectDelay = Math.min(30000, reconnectDelay * 1.5); connect(); }, reconnectDelay);
      }
    };
  }

  // HTTP polling fallback — 15s per symbol batch
  async function pollFallback() {
    if (!subscribed.size) return;
    try {
      const syms = [...subscribed].join(',');
      const r = await fetch(`/api/live/quote?tickers=${encodeURIComponent(syms)}`, { signal: AbortSignal.timeout(5000) });
      if (!r.ok) return;
      const d = await r.json();
      if (!d.in_hours) { setStatus('Market closed', false); return; }
      Object.entries(d.prices || {}).forEach(([ticker, price]) => {
        const prev = lastPrices[ticker];
        lastPrices[ticker] = price;
        const chgPct = prev ? ((price - prev) / prev * 100) : 0;
        handlers.forEach(h => h(ticker, price, chgPct, { s: ticker, p: price }));
      });
      setStatus(`Poll ${new Date().toLocaleTimeString('en-US', {hour12:false}).slice(0,5)}`, true);
    } catch (_) {}
  }

  return {
    /**
     * Attach a tick handler: fn(ticker, price, chgPct, rawData)
     */
    onTick(fn) {
      handlers.push(fn);
    },

    /**
     * Set the DOM element that shows live status text.
     */
    setStatusElement(el) {
      statusEl = el;
    },

    /**
     * Subscribe to real-time ticks for a list of tickers.
     * Returns a cleanup function to unsubscribe.
     */
    subscribe(tickers) {
      tickers.forEach(t => { if (t) subscribed.add(t.toUpperCase()); });

      // If already connected via WS, subscribe new tickers live
      if (ws && ws.readyState === WebSocket.OPEN) {
        tickers.forEach(sym => {
          ws.send(JSON.stringify({ action: 'subscribe', symbols: sym.toUpperCase() }));
        });
      }

      return () => {
        tickers.forEach(t => {
          subscribed.delete(t.toUpperCase());
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'unsubscribe', symbols: t.toUpperCase() }));
          }
        });
      };
    },

    /**
     * Start the live feed. Tries WebSocket first, falls back to HTTP polling.
     */
    async start() {
      apiKey = await getApiKey();
      if (apiKey) {
        connect();
      } else {
        usePoll = true;
        setStatus('Polling (no WS token)', false);
        pollFallback();
        setInterval(pollFallback, 5000);
      }
    },

    /** Current cached prices */
    getPrice(ticker) { return lastPrices[ticker.toUpperCase()]; },
    getAllPrices() { return { ...lastPrices }; },
  };
})();
