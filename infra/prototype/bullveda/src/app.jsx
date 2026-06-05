// app.jsx — SwingTrade V2 terminal — main React app
// Composition: IconRail · ScanColumn (collapsible) · DetailPanel (fills remaining)
// Default = direction E (Three-Column Pro), focus-mode = direction C.

const { useState: useStateApp, useEffect: useEffectApp, useRef: useRefApp, useMemo: useMemoApp } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme":        "midnight-cyan",
  "mode":         "SWING",
  "scanWidth":    "M",
  "focus":        false,
  "heroStyle":    "radar",
  "headerStyle":  "copper",
  "kpiStyle":     "bare",
  "showTimeAge":  true,
  "lensTabs":     "wrap",
  "railExpanded": false,
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Active workspace surface + active ticker + active lens
  const [surface, setSurface] = useStateApp("home");
  const [ticker, setTicker] = useStateApp(null);  // null = home page
  const [lensId, setLensId] = useStateApp("plan");
  const [tier, setTier] = useStateApp(4);  // commercial tier · default ELITE
  // re-render once the deferred heavy feeds (Time table + Track-Record ledger) land
  const [, _bvBump] = useStateApp(0);
  useEffectApp(() => {
    const onReady = () => _bvBump((n) => n + 1);
    window.addEventListener("bv:heavyready", onReady);
    return () => window.removeEventListener("bv:heavyready", onReady);
  }, []);
  window.__tier = tier;
  window.__tmode = t.mode;
  window.__setLens = setLensId;
  window.__setMode = (m) => setTweak("mode", m);
  window.__setSurface = (id) => { setSurface(id); setTicker(null); };

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

  // ── Live section gating ─────────────────────────────────────────
  // Blur/lock any surface section whose effective min-tier is above the
  // viewer's tier (or that's been disabled), using data-* attributes so we
  // never fight React's ownership of className/children. Re-applies on
  // surface/tier change and whenever the surface re-renders (MutationObserver).
  useEffectApp(() => {
    const mainEl = detailRef.current;
    if (!mainEl) return;
    let raf = 0;
    const clear = () => mainEl.querySelectorAll("[data-seclock]").forEach(el => {
      el.removeAttribute("data-seclock");
      el.removeAttribute("data-secmsg");
      el.removeAttribute("data-sectier");
    });
    const apply = () => {
      raf = 0;
      clear();
      if (ticker != null || surface === "users") return; // gate workspace surfaces only
      const groups = (window.surfaceSections ? window.surfaceSections(surface) : null);
      if (!groups) return;
      const tiers = window.TIER_LIST || [];
      const cards = Array.from(mainEl.querySelectorAll(".lab-card, .hc"));
      const headText = (c) => {
        const h = c.querySelector(".lab-card-h, .hc-title");
        return h ? h.textContent.toUpperCase() : "";
      };
      groups.flatMap(g => g.panels).forEach(p => {
        const off = window.sectionOff(surface, p.id);
        const eff = window.sectionTier(surface, p.id);
        if (!off && eff <= tier) return; // visible to this tier
        let nodes = [];
        if (p.sel) nodes = Array.from(mainEl.querySelectorAll(p.sel));
        else if (p.match) {
          const m = p.match.toUpperCase();
          nodes = cards.filter(c => headText(c).includes(m));
        }
        nodes.forEach(n => {
          if (off) {
            n.setAttribute("data-seclock", "off");
            n.setAttribute("data-secmsg", "⊘  SECTION DISABLED");
          } else {
            const td = tiers.find(x => x.id === eff) || {};
            n.setAttribute("data-seclock", "locked");
            n.setAttribute("data-sectier", String(eff));
            n.setAttribute("data-secmsg", `🔒  TIER ${eff} · ${(td.name || "").toUpperCase()} — TAP TO PREVIEW`);
          }
        });
      });
    };
    const schedule = () => { if (raf) clearTimeout(raf); raf = setTimeout(apply, 16); };
    schedule();
    const obs = new MutationObserver(schedule);
    obs.observe(mainEl, { childList: true, subtree: true });
    const onClick = (e) => {
      const lock = e.target.closest('[data-seclock="locked"]');
      if (lock && mainEl.contains(lock)) {
        e.preventDefault(); e.stopPropagation();
        const tt = parseInt(lock.getAttribute("data-sectier"), 10);
        if (!isNaN(tt)) setTier(tt);
      }
    };
    mainEl.addEventListener("click", onClick, true);
    window.__applySectionGates = schedule;
    return () => { obs.disconnect(); mainEl.removeEventListener("click", onClick, true); if (raf) clearTimeout(raf); };
  }, [surface, ticker, tier]);

  // Kbd shortcuts: 1-7, T, V, R, E, O, P, I, M, F (focus), Esc → home
  useEffectApp(() => {
    const map = {
      "1":"overview","2":"plan","3":"chart","T":"technicals","t":"technicals",
      "5":"smc","V":"investment","v":"investment",
      "E":"earnings","e":"earnings",
      "O":"options","o":"options",
      "I":"tape","i":"tape","M":"mledge","m":"mledge","8":"time",
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
    // BULLVEDA: build the full detail from REAL scan row + fundamentals + ML + setup ledger.
    const BV = window.__BV;
    if (BV && BV.ready) {
      // instant: render the scan-row base immediately (no blocking XHR) …
      const base = BV.detailBase ? BV.detailBase(sym) : (BV.detailSync ? BV.detailSync(sym) : null);
      if (base) {
        setTicker(base);
        // … then enrich fundamentals + ML in the background, applying only if still on this name
        if (BV.detailEnrich) BV.detailEnrich(sym).then(full => {
          if (full) setTicker(cur => (cur && cur.symbol === sym ? full : cur));
        }).catch(() => {});
      } else {
        setTicker({ ...TICKER, symbol: sym, name: sym, live: true, _pulledAt: Date.now() });
      }
      return;
    }
    // ── offline fallback (mock) ──
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
          technical: Math.round(Math.max(20, Math.min(95, known.score + (Math.sin(known.sym.charCodeAt(0)) * 8)))),
          fundamental: Math.round(Math.max(20, Math.min(95, known.score - 10 + (Math.cos(known.sym.charCodeAt(1) || 0) * 6)))),
          catalyst:    Math.round(Math.max(20, Math.min(95, known.score - 16))),
          risk:        Math.round(Math.max(20, Math.min(95, 70 - Math.abs(known.chg) * 3))),
          edge:        Math.round(Math.max(20, Math.min(95, known.score - 6))),
        },
      });
    } else {
      // unknown ticker — not in our universe → pull it LIVE (flagged so the
      // detail view shows it was fetched on-demand, not from the seeded universe)
      setTicker({ ...TICKER, symbol: sym, name: sym, live: true, _pulledAt: Date.now() });
    }
  };

  const goHome = () => { setTicker(null); setSurface("home"); };

  // deep-link: ?t=SYM[&lens=overview] opens a ticker's detail on load (shareable URLs)
  useEffectApp(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      const sym = p.get("t") || p.get("ticker");
      if (sym) handleTickerClick(sym.toUpperCase(), p.get("lens") || "overview");
    } catch (e) {}
  }, []);

  return (
    <div className={`app ${t.focus ? "app--focus" : ""} ${t.railExpanded ? "app--rail-open" : ""}`}>
      <IconRail activeId={surface} onPick={handleSurfaceClick} tier={tier}
        expanded={t.railExpanded} onToggleExpand={() => setTweak("railExpanded", !t.railExpanded)} />

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
          onTicker={handleTickerClick}
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
            <SurfaceSignalScanner onTicker={handleTickerClick} onSurface={setSurface} />
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
          ) : surface === "ipos" ? (
            <div className="main-home">
              <SurfaceIPO onTicker={handleTickerClick} />
            </div>
          ) : surface === "crypto" ? (
            <div className="main-home">
              <SurfaceCrypto onTicker={handleTickerClick} />
            </div>
          ) : surface === "sector-etf" ? (
            <div className="main-home">
              <SurfaceETFs onTicker={handleTickerClick} />
            </div>
          ) : surface === "options" ? (
            <div className="main-home">
              <SurfaceOptions onTicker={(s)=>handleTickerClick(s,"options")} />
            </div>
          ) : surface === "news" ? (
            <div className="main-home">
              <SurfaceNews key="sent-news" onTicker={handleTickerClick} />
            </div>
          ) : surface === "social" ? (
            <div className="main-home">
              <SurfaceNews key="sent-social" onTicker={handleTickerClick} initialView="social" />
            </div>
          ) : surface === "insider" ? (
            <div className="main-home">
              <SurfaceInsider onTicker={handleTickerClick} />
            </div>
          ) : surface === "smc-patterns" ? (
            <div className="main-home">
              <SurfaceSMCPatterns onTicker={handleTickerClick} />
            </div>
          ) : surface === "risk" ? (
            <div className="main-home">
              <SurfaceRisk onTicker={handleTickerClick} />
            </div>
          ) : surface === "earnings-ai" ? (
            <div className="main-home">
              <SurfaceEarningsPredictions onTicker={handleTickerClick} />
            </div>
          ) : surface === "macro-cal" || surface === "earnings-cal" ? (
            <div className="main-home">
              <SurfaceMacro onTicker={handleTickerClick} />
            </div>
          ) : surface === "internals" ? (
            <div className="main-home">
              <SurfaceInternals onTicker={handleTickerClick} />
            </div>
          ) : surface === "portfolio-srf" ? (
            <div className="main-home">
              <SurfaceAutomatedTrade onTicker={handleTickerClick} />
            </div>
          ) : surface === "myportfolios" ? (
            <div className="main-home">
              <SurfaceMyPortfolios onTicker={handleTickerClick} />
            </div>
          ) : surface === "book-risk" ? (
            <div className="main-home">
              <SurfaceBookRisk onTicker={handleTickerClick} />
            </div>
          ) : surface === "track-record" ? (
            <div className="main-home">
              <SurfaceTrackRecord onTicker={handleTickerClick} />
            </div>
          ) : surface === "status" ? (
            <div className="main-home">
              <SurfaceStatus />
            </div>
          ) : surface === "help" ? (
            <div className="main-home">
              <SurfaceHelp />
            </div>
          ) : surface === "settings" ? (
            <div className="main-home">
              <SurfaceSettings />
            </div>
          ) : surface === "performance" ? (
            <div className="main-home">
              <SurfacePerformance onTicker={handleTickerClick} />
            </div>
          ) : surface === "strategies" ? (
            <div className="main-home">
              <SurfaceStrategies onTicker={handleTickerClick} />
            </div>
          ) : surface === "themes" ? (
            <div className="main-home">
              <SurfaceThemes onTicker={handleTickerClick} />
            </div>
          ) : surface === "alerts" ? (
            <div className="main-home">
              <SurfaceAlerts onTicker={handleTickerClick} />
            </div>
          ) : surface === "journal" ? (
            <div className="main-home">
              <SurfaceJournal onTicker={handleTickerClick} />
            </div>
          ) : surface === "playbook" ? (
            <div className="main-home">
              <SurfacePlaybook onTicker={handleTickerClick} />
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
            lensTabs={t.lensTabs}
            focusMode={t.focus}
            onToggleFocus={() => setTweak("focus", !t.focus)}
            onHome={goHome}
            tier={tier}
            onTier={setTier}
          />
        );
        })()}
        <footer className="app-disclaimer mono">
          <span className="app-disclaimer-tag">INFORMATIONAL</span>
          <span className="app-disclaimer-txt">{window.SEC_DISCLAIMER}</span>
        </footer>
      </main>

      <SwingTweaks t={t} setTweak={setTweak} />
      <AgentPanel getContext={() => ({
        surface, surfaceLabel: surfaceLabel(surface),
        ticker, lensId, mode: t.mode, lensLabel: ((window.LENSES || []).find(l => l.id === lensId) || {}).label,
        sectionLabels: [...document.querySelectorAll(".dpanel-body .sec-hdr-title, .lens-section .sec-hdr-title")].slice(0, 10).map(e => e.textContent.trim()),
        screenText: ((document.querySelector(".dpanel-body") || document.querySelector(".main-home") || {}).innerText || "").replace(/\s+/g, " ").trim(),
      })} />
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

// ─── Universe ticker search (autocomplete + live-pull fallback) ───
function TickerSearch({ onTicker }) {
  const [q, setQ] = useStateApp("");
  const [open, setOpen] = useStateApp(false);
  const [hi, setHi] = useStateApp(0);
  const ref = useRefApp(null);
  const inputRef = useRefApp(null);

  useEffectApp(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  // ⌘K / Ctrl-K / "/" focuses the search
  useEffectApp(() => {
    const h = (e) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && document.activeElement !== inputRef.current && !/input|textarea/i.test((document.activeElement || {}).tagName || ""))) {
        e.preventDefault(); inputRef.current && inputRef.current.focus(); setOpen(true);
      }
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, []);

  const universe = window.TICKER_UNIVERSE || [];
  const raw = q.trim();
  const query = raw.replace(/^\//, "").replace(/^(verdict|scan|chart|quote)\s+/i, "").trim();
  const ql = query.toLowerCase();
  const looksTicker = /^[A-Za-z]{1,5}(\.[A-Za-z])?$/.test(query);

  const matches = useMemoApp(() => {
    if (!ql) return [];
    const starts = [], contains = [], byName = [];
    universe.forEach(u => {
      const s = u.sym.toLowerCase(), n = (u.name || "").toLowerCase();
      if (s === ql) starts.unshift(u);
      else if (s.startsWith(ql)) starts.push(u);
      else if (s.includes(ql)) contains.push(u);
      else if (n.includes(ql)) byName.push(u);
    });
    return [...starts, ...contains, ...byName].slice(0, 8);
  }, [ql]);

  const exact = matches.find(m => m.sym.toLowerCase() === ql);
  const showLive = looksTicker && !exact;     // valid symbol shape, not in universe → live pull
  const items = [...matches.map(m => ({ type: "u", ...m })), ...(showLive ? [{ type: "live", sym: query.toUpperCase() }] : [])];

  useEffectApp(() => { setHi(0); }, [ql]);

  const choose = (it) => {
    if (!it) return;
    onTicker && onTicker(it.sym.toUpperCase());
    setQ(""); setOpen(false);
  };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi(h => Math.min(h + 1, Math.max(0, items.length - 1))); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi(h => Math.max(0, h - 1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (items[hi]) choose(items[hi]);
      else if (looksTicker) choose({ sym: query.toUpperCase() });   // bare symbol → live pull
    } else if (e.key === "Escape") { setOpen(false); setQ(""); }
  };

  return (
    <div className="cmd-search-wrap" ref={ref}>
      <div className={`cmd-search ${open && items.length ? "is-open" : ""}`}>
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
          <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.4" />
          <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.4" />
        </svg>
        <input ref={inputRef} placeholder="Search any ticker or company…  ⌘K"
               value={q}
               onChange={e => { setQ(e.target.value); setOpen(true); }}
               onFocus={() => setOpen(true)}
               onKeyDown={onKey} />
        <span className="kbd">/</span>
      </div>
      {open && (items.length > 0 || ql) && (
        <div className="tks-menu">
          {items.length === 0 && ql && !looksTicker && (
            <div className="tks-empty mono dim2">No match. Type a symbol (1–5 letters) to pull it live.</div>
          )}
          {items.map((it, i) => it.type === "live" ? (
            <button key="live" className={`tks-row tks-row--live ${hi === i ? "is-hi" : ""}`} onMouseEnter={() => setHi(i)} onClick={() => choose(it)}>
              <span className="tks-live-ico">⚡</span>
              <span className="tks-row-main"><b className="mono">{it.sym}</b> <span className="dim2">— pull live</span></span>
              <span className="tks-row-tag mono">not in universe · fetch on-demand</span>
            </button>
          ) : (
            <button key={it.sym} className={`tks-row ${hi === i ? "is-hi" : ""}`} onMouseEnter={() => setHi(i)} onClick={() => choose(it)}>
              <span className="tks-sym mono">{it.sym}</span>
              <span className="tks-row-main">{it.name || it.sym}</span>
              <span className="tks-row-meta mono dim2">{it.sector || ""}{it.verdict ? ` · ${it.verdict}` : ""}</span>
            </button>
          ))}
          <div className="tks-foot mono dim2">↑↓ navigate · ↵ open · {showLive ? "live-pull for off-universe symbols" : `${universe.length} in universe`}</div>
        </div>
      )}
    </div>
  );
}

// ─── Command bar (top-of-detail) ──────────────────────────────────
function CommandBar({ mode, onMode, surface, ticker, focusMode, onToggleFocus, onHome, theme, onTheme, tier, onTier, onTicker }) {
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
        <TickerSearch onTicker={onTicker} />
      </div>
      <div className="cmd-right">
        <ThemeQuickPick value={theme} onChange={onTheme} />

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
          <span className="user-acct mono dim">PAPER · {(window.__BV && window.__BV.navStr()) || "$108,420"} {window.__BV && window.__BV.navDayPct != null ? <span className={window.__BV.navDayPct >= 0 ? "up" : "dn"}>{window.__BV.navDayPct >= 0 ? "+" : ""}{window.__BV.navDayPct}%</span> : null}</span>
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
              <span className="mono"><b>{(window.__BV && window.__BV.navStr()) || "$108,420"}</b> {window.__BV && window.__BV.navDayPct != null ? <span className={window.__BV.navDayPct >= 0 ? "up" : "dn"}>{window.__BV.navDayPct >= 0 ? "+" : ""}{window.__BV.navDayPct}%</span> : <span className="up">+1.20%</span>}</span>
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
    "market-map": "Market Map", "watchlist": "Watchlist", "buy": "Bullish Candidates",
    "elite": "Elite Picks", "screener": "Screener", "themes": "Themes",
    "momentum": "Momentum", "ai-predict": "ML Predictions", "options-flow": "Options Flow", "options-ideas": "Options Ideas", "options": "Options",
    "premarket": "Pre-Market · Options", "ipos": "Upcoming IPOs", "crypto": "Crypto Market", "sector-etf": "ETFs", "etf-screener": "ETFs", "social": "Social Sentiment",
    "portfolio-srf": "Automated Trade", "myportfolios": "My Portfolios", "book-risk": "Book Risk", "track-record": "Track Record", "journal": "Trade Journal", "insider": "Insider Trading",
    "news": "News · Sentiment",
    "strategies": "Strategies", "performance": "Performance", "alerts": "Alerts",
    "risk": "Risk · Exposure", "earnings-cal": "Calendar", "macro-cal": "Calendar", "internals": "Market Internals",
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
      <TweakToggle
        label="Expand nav rail"
        value={t.railExpanded}
        onChange={(v) => setTweak("railExpanded", v)}
      />

      <TweakSection label="Lens tabs" />
      <TweakSelect
        label="Presentation"
        value={t.lensTabs}
        options={[
          { value: "wrap", label: "Wrap · multi-row (no scroll)" },
          { value: "compact", label: "Compact · icons, active label" },
          { value: "minimal", label: "Minimal · text + underline" },
          { value: "scroll", label: "Scroll · single row (legacy)" },
        ]}
        onChange={(v) => setTweak("lensTabs", v)}
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
