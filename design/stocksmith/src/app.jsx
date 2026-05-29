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
  const [surface, setSurface] = useStateApp("home");
  const [ticker, setTicker] = useStateApp(null);  // null = home page
  const [lensId, setLensId] = useStateApp("plan");
  const [tier, setTier] = useStateApp(4);  // commercial tier · default ELITE
  window.__tier = tier;

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
    // Any workspace surface click returns to the workspace view (no detail panel).
    setTicker(null);
  };
  const handleTickerClick = (sym, lens) => {
    setLensId(lens || "overview");
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

  const goHome = () => { setTicker(null); setSurface("home"); };

  return (
    <div className={`app ${t.focus ? "app--focus" : ""}`}>
      <IconRail activeId={surface} onPick={handleSurfaceClick} tier={tier} />

      {ticker != null && !t.focus && (
        <ScanColumn
          activeSurface={surface}
          onSurface={(id) => { setSurface(id); }}
          activeTicker={ticker?.symbol}
          onTicker={handleTickerClick}
          widthCat={t.scanWidth}
          onWidthCat={(w) => setTweak("scanWidth", w)}
          collapsed={t.focus}
        />
      )}

      <main className="main" ref={detailRef}>
        <CommandBar
          mode={t.mode}
          onMode={(m) => setTweak("mode", m)}
          surface={surface}
          ticker={ticker}
          focusMode={t.focus}
          onToggleFocus={() => setTweak("focus", !t.focus)}
          onHome={goHome}
          theme={t.theme}
          onTheme={(v) => setTweak("theme", v)}
          tier={tier}
          onTier={setTier}
        />

        {(() => {
          const sTier = (window.SURFACE_TIER || {})[surface] ?? 0;
          if (ticker == null && sTier > tier) {
            return <UpgradeGate kind="surface" name={surfaceLabel(surface)} minTier={sTier} onTier={setTier} />;
          }
          return ticker == null ? (
          surface === "ai-predict" ? (
            <SurfaceAIPredictions onTicker={handleTickerClick} />
          ) : surface === "signal-scanner" ? (
            <SurfaceSignalScanner onTicker={handleTickerClick} />
          ) : surface === "home" ? (
            <div className="main-home">
              <HomeView onTicker={handleTickerClick} onSurface={setSurface} mode={t.mode} surface={surface} />
            </div>
          ) : surface === "watchlist" ? (
            <div className="main-home">
              <SurfaceWatchlist onTicker={handleTickerClick} />
            </div>
          ) : surface === "lab" ? (
            <div className="main-home">
              <SurfaceLab onTicker={handleTickerClick} />
            </div>
          ) : surface === "momentum" ? (
            <div className="main-home">
              <SurfaceMomentum onTicker={handleTickerClick} />
            </div>
          ) : surface === "premarket" ? (
            <div className="main-home">
              <SurfacePreMarket onTicker={handleTickerClick} />
            </div>
          ) : surface === "sector-etf" ? (
            <div className="main-home">
              <SurfaceETFs onTicker={handleTickerClick} />
            </div>
          ) : surface === "etf-screener" ? (
            <div className="main-home">
              <SurfaceETFs onTicker={handleTickerClick} />
            </div>
          ) : surface === "options-flow" ? (
            <div className="main-home">
              <SurfaceOptionsFlow onTicker={(s)=>handleTickerClick(s,"options")} />
            </div>
          ) : surface === "options-ideas" ? (
            <div className="main-home">
              <SurfaceOptionsIdeas onTicker={(s)=>handleTickerClick(s,"options")} />
            </div>
          ) : surface === "news" ? (
            <div className="main-home">
              <SurfaceNews onTicker={handleTickerClick} />
            </div>
          ) : surface === "users" ? (
            <div className="main-home">
              <SurfaceUsers />
            </div>
          ) : (
            <div className="main-home">
              <WorkspaceSurface id={surface} onTicker={handleTickerClick} />
            </div>
          )
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
            tier={tier}
            onTier={setTier}
          />
        );
        })()}
      </main>

      <SwingTweaks t={t} setTweak={setTweak} />
    </div>
  );
}

// ─── Upgrade gate (shown for locked surfaces / lenses) ──────────
function UpgradeGate({ kind, name, minTier, onTier }) {
  const tiers = window.TIER_LIST || [];
  const tdef = tiers.find(t => t.id === minTier) || {};
  return (
    <div className="upgate">
      <div className="upgate-card">
        <div className="upgate-lock">🔒</div>
        <div className="upgate-tier mono">TIER {minTier} · {tdef.name?.toUpperCase()}</div>
        <h2 className="upgate-title">{name}</h2>
        <p className="upgate-sub mono">
          This {kind === "surface" ? "workspace" : "lens"} unlocks at <b>{tdef.name}</b> ({tdef.price}/mo).
          {tdef.tag ? ` ${tdef.tag}` : ""}
        </p>
        <button className="upgate-btn mono" onClick={() => onTier(minTier)}>
          ⚡ PREVIEW AS {tdef.name?.toUpperCase()}
        </button>
        <div className="upgate-note mono dim2">Demo control — switches the tier selector to unlock this surface.</div>
      </div>
    </div>
  );
}
window.UpgradeGate = UpgradeGate;

// ─── Command bar (top-of-detail) ──────────────────────────────────
function CommandBar({ mode, onMode, surface, ticker, focusMode, onToggleFocus, onHome, theme, onTheme, tier, onTier }) {
  const [now, setNow] = useStateApp(() => new Date());
  useEffectApp(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const time = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const date = now.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });

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
          {surface !== "home" && (
            <>
              <span className="dim">/</span>
              <span className="copper">{surfaceLabel(surface)}</span>
            </>
          )}
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
        {ticker && (
          <div className="cmd-mode seg">
            {["SWING", "POSITION", "INVESTMENT"].map(m => (
              <button key={m} className={`seg-btn ${mode === m ? "is-on" : ""}`} onClick={() => onMode(m)}>
                {m}
              </button>
            ))}
          </div>
        )}

        <ThemeQuickPick value={theme} onChange={onTheme} />
        <TierPicker value={tier} onChange={onTier} />

        <div className="cmd-time" title={date}>
          <span className="cmd-time-pulse" />
          <span className="cmd-time-v mono">{time}</span>
          <span className="cmd-time-tz mono dim">ET</span>
        </div>

        <UserMenu />
      </div>
    </div>
  );
}

function UserMenu() {
  const [open, setOpen] = useStateApp(false);
  const ref = useRefApp(null);
  useEffectApp(() => {
    const onClick = (e) => {
      if (ref.current && ref.current.contains(e.target)) return;
      if (e.target.closest(".user-menu")) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  return (
    <div className="user" ref={ref}>
      <button className="user-btn" onClick={() => setOpen(o => !o)} title="Account">
        <span className="user-avatar mono">JK</span>
        <span className="user-info">
          <span className="user-name">J. Kairos</span>
          <span className="user-acct mono dim">PAPER · $108,420 <span className="up">+1.20%</span></span>
        </span>
        <span className="user-caret">▾</span>
      </button>
      {open && ReactDOM.createPortal((
        <div className="user-menu">
          <div className="user-menu-hdr">
            <div className="user-avatar mono user-avatar--lg">JK</div>
            <div>
              <div className="user-menu-name">Jules Kairos</div>
              <div className="user-menu-email mono dim">jules@kairos.fund</div>
            </div>
          </div>
          <div className="user-menu-acct">
            <div className="um-row">
              <span className="label-cap">Account</span>
              <Pill tone="amb" small>PAPER</Pill>
            </div>
            <div className="um-row">
              <span className="label-cap">NAV</span>
              <span className="mono"><b>$108,420</b> <span className="up">+1.20%</span></span>
            </div>
            <div className="um-row">
              <span className="label-cap">Cash</span>
              <span className="mono">$90,628</span>
            </div>
            <div className="um-row">
              <span className="label-cap">Session</span>
              <span className="mono dim2">since 08:31 ET</span>
            </div>
          </div>
          <div className="user-menu-list">
            <button className="um-item">⚙ Settings & preferences</button>
            <button className="um-item">🔑 API keys · EODHD · Schwab</button>
            <button className="um-item">🛡 Risk & sizing policy</button>
            <button className="um-item">⌘ Keyboard shortcuts</button>
            <button className="um-item">📓 Journal · trade log</button>
          </div>
          <div className="user-menu-foot">
            <button className="um-signoff">⏻ Sign off</button>
          </div>
        </div>
      ), document.body)}
    </div>
  );
}
function surfaceLabel(id) {
  return {
    "home": "Home",
    "signal-scanner": "Signal Scanner",
    "market-map": "Market Map", "watchlist": "Watchlist", "buy": "BUY Candidates",
    "elite": "Elite Picks", "screener": "Screener", "themes": "Themes",
    "momentum": "Momentum", "ai-predict": "AI Predictions", "options-flow": "Options Flow", "options-ideas": "Options Ideas",
    "premarket": "Pre-Market · Options", "sector-etf": "ETFs", "etf-screener": "ETFs", "social": "Social Sentiment",
    "portfolio-srf": "Portfolio", "journal": "Trade Journal", "insider": "Insider Trading",
    "news": "News · Sentiment",
    "strategies": "Strategies", "performance": "Performance", "alerts": "Alerts",
    "playbook": "Playbook", "settings": "Settings", "status": "System Status", "users": "User Management",
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
