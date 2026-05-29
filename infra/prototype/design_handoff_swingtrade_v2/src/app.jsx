// app.jsx — SwingTrade V2 terminal — main React app
// Composition: IconRail · ScanColumn (collapsible) · DetailPanel (fills remaining)
// Default = direction E (Three-Column Pro), focus-mode = direction C.

const { useState: useStateApp, useEffect: useEffectApp, useRef: useRefApp } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme":        "midnight-cyan",
  "mode":         "SWING",
  "scanWidth":    "M",
  "focus":        false,
  "heroStyle":    "radar",
  "headerStyle":  "copper",
  "kpiStyle":     "bare",
  "showTimeAge":  true,
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Active workspace surface + active ticker + active lens
  const [surface, setSurface] = useStateApp("market-map");
  const [ticker, setTicker] = useStateApp(null);  // null = home page
  const [lensId, setLensId] = useStateApp("plan");

  // The detail column fills remaining space — we observe its width.
  const detailRef = useRefApp(null);
  const [detailWidth, setDetailWidth] = useStateApp(900);
  useEffectApp(() => {
    if (!detailRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setDetailWidth(Math.round(e.contentRect.width));
    });
    ro.observe(detailRef.current);
    return () => ro.disconnect();
  }, []);

  // Apply theme to root
  useEffectApp(() => {
    document.documentElement.setAttribute("data-theme", t.theme);
  }, [t.theme]);

  // Kbd shortcuts: 1-7, T, V, R, E, O, P, I, M, F (focus), Esc → home
  useEffectApp(() => {
    const map = {
      "1":"overview","2":"plan","3":"chart","T":"technicals","t":"technicals",
      "4":"patterns","5":"smc","V":"investment","v":"investment",
      "R":"risk","r":"risk","E":"earnings","e":"earnings",
      "O":"options","o":"options","P":"portfolio","p":"portfolio",
      "I":"tape","i":"tape","7":"track","M":"mledge","m":"mledge",
    };
    const onKey = (e) => {
      if (["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const next = map[e.key];
      if (next && ticker) {
        e.preventDefault();
        setLensId(next);
      }
      if (e.key === "f" || e.key === "F") {
        setTweak("focus", !t.focus);
      }
      if (e.key === "Escape") {
        setTicker(null); // back to home
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [t.focus, setTweak, ticker]);

  // Sim live updates — flicker the freshness pill (read-only effect)
  useEffectApp(() => {
    const i = setInterval(() => {
      // increment a counter that the freshness pill renders — currently static for simplicity
    }, 30000);
    return () => clearInterval(i);
  }, []);

  // Surface clicks: ticker-bearing surfaces set ticker; others just switch surface for the scan column
  const handleSurfaceClick = (id) => {
    setSurface(id);
    // Returning to a scan surface goes back to home view
    if (id === "market-map") setTicker(null);
  };
  const handleTickerClick = (sym) => {
    // pull from WATCHLIST if known; else build a stub
    const known = WATCHLIST.find(w => w.sym === sym);
    if (sym === TICKER.symbol) {
      setTicker(TICKER);
    } else if (known) {
      // synthesize a ticker shape from the row + base TICKER pillars (so the lenses still render)
      setTicker({
        ...TICKER,
        symbol: known.sym,
        name: known.name,
        price: known.price,
        chg: known.chg,
        chgAbs: known.price * (known.chg / 100),
        score: known.score,
        verdict: known.verdict,
        setupFamily: known.setup,
        pillars: {
          technical: Math.max(20, Math.min(95, known.score + (Math.sin(known.sym.charCodeAt(0)) * 8))),
          fundamental: Math.max(20, Math.min(95, known.score - 10 + (Math.cos(known.sym.charCodeAt(1) || 0) * 6))),
          catalyst:    Math.max(20, Math.min(95, known.score - 16)),
          risk:        Math.max(20, Math.min(95, 70 - Math.abs(known.chg) * 3)),
          edge:        Math.max(20, Math.min(95, known.score - 6)),
        },
      });
    } else {
      // unknown ticker (e.g. from heatmap with no watchlist row) — synthesize from TICKER
      setTicker({ ...TICKER, symbol: sym });
    }
  };

  const goHome = () => setTicker(null);

  return (
    <div className={`app ${t.focus ? "app--focus" : ""}`}>
      <IconRail activeId={surface} onPick={handleSurfaceClick} />

      <ScanColumn
        activeSurface={surface}
        onSurface={(id) => { setSurface(id); }}
        activeTicker={ticker?.symbol}
        onTicker={handleTickerClick}
        widthCat={t.scanWidth}
        onWidthCat={(w) => setTweak("scanWidth", w)}
        collapsed={t.focus}
      />

      <main className="main" ref={detailRef}>
        <CommandBar
          mode={t.mode}
          onMode={(m) => setTweak("mode", m)}
          surface={surface}
          ticker={ticker}
          focusMode={t.focus}
          onToggleFocus={() => setTweak("focus", !t.focus)}
          onHome={goHome}
        />

        {ticker == null ? (
          <div className="main-home">
            <HomeView onTicker={handleTickerClick} mode={t.mode} surface={surface} />
          </div>
        ) : (
          <DetailPanel
            ticker={ticker}
            lensId={lensId}
            onLensId={setLensId}
            containerWidth={detailWidth}
            mode={t.mode}
            headerStyle={t.headerStyle}
            kpiStyle={t.kpiStyle}
            heroStyle={t.heroStyle}
            focusMode={t.focus}
            onToggleFocus={() => setTweak("focus", !t.focus)}
            onHome={goHome}
          />
        )}
      </main>

      <SwingTweaks t={t} setTweak={setTweak} />
    </div>
  );
}

// ─── Command bar (top-of-detail) ──────────────────────────────────
function CommandBar({ mode, onMode, surface, ticker, focusMode, onToggleFocus, onHome }) {
  return (
    <div className="cmd">
      <div className="cmd-left">
        <button className="cmd-home" onClick={onHome} title="Back to home">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
            <path d="M2 7 L8 2 L14 7 V14 H10 V10 H6 V14 H2 Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          </svg>
        </button>
        <div className="cmd-breadcrumb mono">
          <button className="cmd-bc-link" onClick={onHome}>Home</button>
          <span className="dim">/</span>
          <span className="copper">{surfaceLabel(surface)}</span>
          {ticker && (
            <>
              <span className="dim">/</span>
              <span><b>{ticker.symbol}</b></span>
            </>
          )}
        </div>
      </div>
      <div className="cmd-center">
        <div className="cmd-search">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
            <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.4" />
            <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.4" />
          </svg>
          <input placeholder="Symbol or /command (e.g. /verdict NVRH, /scan breakout)…" />
          <span className="kbd">/</span>
        </div>
      </div>
      <div className="cmd-right">
        <div className="cmd-mode seg">
          {["SWING", "POSITION", "INVESTMENT"].map(m => (
            <button key={m} className={`seg-btn ${mode === m ? "is-on" : ""}`} onClick={() => onMode(m)}>
              {m}
            </button>
          ))}
        </div>
        <div className="cmd-acct mono">
          <span className="label-cap">NAV</span>
          <b>$108,420</b>
          <span className="up">+1.20%</span>
        </div>
      </div>
    </div>
  );
}
function surfaceLabel(id) {
  return {
    "market-map": "Market Map", "watchlist": "Watchlist", "buy": "BUY Candidates",
    "elite": "Elite Picks", "screener": "Screener", "themes": "Themes",
    "strategies": "Strategies", "performance": "Performance", "alerts": "Alerts",
    "playbook": "Playbook", "settings": "Settings", "status": "System Status",
  }[id] || id;
}

// ─── Tweaks panel ─────────────────────────────────────────────────
function SwingTweaks({ t, setTweak }) {
  return (
    <TweaksPanel>
      <TweakSection label="Theme palette" />
      <ThemePicker value={t.theme} onChange={(v) => setTweak("theme", v)} />

      <TweakSection label="Layout" />
      <TweakRadio
        label="Scan column"
        value={t.scanWidth}
        options={["S", "M", "L", "XL"]}
        onChange={(v) => setTweak("scanWidth", v)}
      />
      <TweakToggle
        label="Focus mode"
        value={t.focus}
        onChange={(v) => setTweak("focus", v)}
      />

      <TweakSection label="Trade horizon" />
      <TweakRadio
        label="Mode"
        value={t.mode}
        options={["SWING", "POSITION", "INVESTMENT"]}
        onChange={(v) => setTweak("mode", v)}
      />

      <TweakSection label="Verdict hero" />
      <TweakRadio
        label="Treatment"
        value={t.heroStyle}
        options={["radar", "gauge", "cone"]}
        onChange={(v) => setTweak("heroStyle", v)}
      />

      <TweakSection label="Section grammar" />
      <TweakSelect
        label="Header"
        value={t.headerStyle}
        options={[
          { value: "copper", label: "§N · copper" },
          { value: "minimal", label: "Minimal · thin rule" },
          { value: "sticky-rail", label: "Sticky rail · left mark" },
        ]}
        onChange={(v) => setTweak("headerStyle", v)}
      />
      <TweakSelect
        label="KPI tile"
        value={t.kpiStyle}
        options={[
          { value: "bare", label: "Bare · value-only" },
          { value: "sparkline", label: "Sparkline-led" },
          { value: "delta", label: "Delta-led" },
        ]}
        onChange={(v) => setTweak("kpiStyle", v)}
      />
    </TweaksPanel>
  );
}

// Mount
ReactDOM.createRoot(document.getElementById("root")).render(<App />);
