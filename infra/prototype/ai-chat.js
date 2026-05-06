/**
 * AI Chat Co-pilot — wires #aiPanel to /api/chat (SSE streaming).
 *
 * Context detection:
 *   - elite-detail.html?t=XXX → ticker context
 *   - dashboard.html         → scanner context
 * History stored in localStorage per-page (truncated to last 20 turns).
 */
(function () {
  const HIST_KEY = (() => {
    const t = new URLSearchParams(location.search).get('t');
    return t ? `ai_chat_hist_${t.toUpperCase()}` : 'ai_chat_hist_scanner';
  })();
  const PAGE = location.pathname.includes('elite-detail') ? 'detail' : 'scanner';
  const TICKER = (new URLSearchParams(location.search).get('t') || '').toUpperCase();

  const $ = id => document.getElementById(id);
  const panel = () => $('aiPanel');
  const msgs = () => $('aiMsgs');
  const input = () => $('aiInput');

  function loadHist() {
    try { return JSON.parse(localStorage.getItem(HIST_KEY) || '[]'); } catch (_) { return []; }
  }
  function saveHist(h) {
    try { localStorage.setItem(HIST_KEY, JSON.stringify(h.slice(-20))); } catch (_) {}
  }

  // Minimal markdown — bold, italic, code, lists, links
  function md(s) {
    if (!s) return '';
    s = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    s = s.replace(/```([\s\S]*?)```/g, (_, c) => `<pre><code>${c}</code></pre>`);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    s = s.replace(/\*([^*]+)\*/g, '<i>$1</i>');
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    // Lists
    s = s.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.+<\/li>\n?)+/g, m => `<ul>${m}</ul>`);
    // Paragraphs
    s = s.split(/\n\n+/).map(p => p.startsWith('<') ? p : `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
    return s;
  }

  function renderMsg(role, content, streaming = false) {
    const el = document.createElement('div');
    el.className = `ai-msg ai-msg-${role}` + (streaming ? ' streaming' : '');
    el.innerHTML = `
      <div class="ai-avatar">${role === 'user' ? 'YOU' : 'AI'}</div>
      <div class="ai-body">${role === 'assistant' ? md(content) : content.replace(/[<>]/g, c => c === '<' ? '&lt;' : '&gt;')}</div>`;
    msgs().appendChild(el);
    msgs().scrollTop = msgs().scrollHeight;
    return el;
  }

  function renderHistory() {
    msgs().innerHTML = '';
    const hist = loadHist();
    if (hist.length === 0) {
      renderEmptyState();
      return;
    }
    hist.forEach(h => renderMsg(h.role, h.content));
  }

  function renderEmptyState() {
    const ctxLabel = TICKER
      ? `Ask about <b>${TICKER}</b> — score breakdown, entry plan, why BUY/WAIT.`
      : 'Ask about today\'s scan — top picks, regime, risk, portfolio fit.';
    msgs().innerHTML = `
      <div class="ai-empty">
        <div class="ai-empty-h">Trading Co-pilot</div>
        <div class="ai-empty-sub">${ctxLabel}</div>
        <div class="ai-empty-meta">Pulls live context from today's scan + your open positions.</div>
      </div>`;
  }

  function renderChips() {
    const chipEl = $('aiChips');
    if (!chipEl) return;
    const chips = TICKER ? [
      `Why is ${TICKER} a ${(window.T?.verdict || 'WATCH')}?`,
      `What's the trade plan for ${TICKER}?`,
      `What could go wrong on this trade?`,
      `How does ${TICKER} compare to other BUY signals today?`,
      `Is this size appropriate for my account?`,
    ] : [
      `What's the market regime today?`,
      `Top 3 highest-conviction BUYs and why`,
      `Any tickers with earnings risk this week?`,
      `What's my current portfolio exposure?`,
      `Where's the bottom of the killed list — anything I'm missing?`,
    ];
    chipEl.innerHTML = chips.map(c => `<button class="ai-chip" onclick="aiAsk(this.textContent)">${c}</button>`).join('');
  }

  let _streaming = false;

  async function send(message) {
    if (_streaming) return;
    if (!message || !message.trim()) return;
    _streaming = true;
    const hist = loadHist();
    hist.push({ role: 'user', content: message });
    saveHist(hist);
    // Clear empty state
    if (msgs().querySelector('.ai-empty')) msgs().innerHTML = '';
    renderMsg('user', message);
    input().value = '';
    input().style.height = '';
    $('aiSend').disabled = true;
    $('aiSend').textContent = '…';
    const aEl = renderMsg('assistant', '', true);
    const bodyEl = aEl.querySelector('.ai-body');
    let buf = '';
    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          history: hist.slice(0, -1), // exclude the just-added user msg
          context: { ticker: TICKER, page: PAGE },
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let leftover = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        leftover += dec.decode(value, { stream: true });
        const lines = leftover.split('\n\n');
        leftover = lines.pop() || '';
        for (const line of lines) {
          const m = line.match(/^data:\s*(.+)$/);
          if (!m) continue;
          let d;
          try { d = JSON.parse(m[1]); } catch (_) { continue; }
          if (d.error) {
            bodyEl.innerHTML = `<div class="ai-err">⚠ ${d.error}</div>`;
            _streaming = false;
            $('aiSend').disabled = false; $('aiSend').textContent = '↑';
            return;
          }
          if (d.text) {
            buf += d.text;
            bodyEl.innerHTML = md(buf);
            msgs().scrollTop = msgs().scrollHeight;
          }
          if (d.done) break;
        }
      }
      aEl.classList.remove('streaming');
      hist.push({ role: 'assistant', content: buf });
      saveHist(hist);
    } catch (e) {
      bodyEl.innerHTML = `<div class="ai-err">Network error: ${e.message}</div>`;
    } finally {
      _streaming = false;
      $('aiSend').disabled = false;
      $('aiSend').textContent = '↑';
    }
  }

  // Drag-resize: insert a handle on the left edge of the panel
  function _wireResize() {
    const p = panel();
    if (!p || p.querySelector('.ai-resize')) return;
    const handle = document.createElement('div');
    handle.className = 'ai-resize';
    handle.title = 'Drag to resize';
    p.appendChild(handle);
    // Restore saved width
    const savedW = parseInt(localStorage.getItem('ai_panel_width') || '440', 10);
    if (savedW >= 320 && savedW <= 800) p.style.width = savedW + 'px';
    let dragging = false, startX = 0, startW = 0;
    handle.addEventListener('mousedown', (e) => {
      dragging = true; startX = e.clientX; startW = p.offsetWidth;
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const dx = startX - e.clientX;  // dragging left = wider
      const w = Math.max(320, Math.min(800, startW + dx));
      p.style.width = w + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try { localStorage.setItem('ai_panel_width', p.offsetWidth.toString()); } catch (_) {}
    });
  }

  // Public API
  window.aiOpen = function () {
    panel().classList.add('on');
    _wireResize();
    setTimeout(() => input()?.focus(), 100);
    renderHistory();
    renderChips();
    const lbl = $('aiCtxLabel');
    if (lbl) lbl.textContent = TICKER ? `${TICKER} · context loaded` : 'scanner · live';
  };
  window.aiClose = function () { panel().classList.remove('on'); };
  window.aiClear = function () {
    if (!confirm('Clear conversation?')) return;
    localStorage.removeItem(HIST_KEY);
    renderHistory();
    renderChips();
  };
  window.aiAsk = function (q) { send(q); };
  window.aiSend = function (e) {
    if (e) e.preventDefault();
    send(input().value);
  };
  window.aiKey = function (e) {
    // Auto-grow textarea
    const el = e.target;
    el.style.height = '';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    // Cmd+Enter or Enter (without shift) sends
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(el.value);
    }
  };

  // Global hotkey: ⌘/ or Ctrl+/ toggles the panel
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === '/') {
      e.preventDefault();
      const p = panel();
      if (p.classList.contains('on')) aiClose(); else aiOpen();
    }
    if (e.key === 'Escape' && panel()?.classList.contains('on') && !document.getElementById('kbdModalBg')?.classList.contains('on')) {
      aiClose();
    }
  });
})();
