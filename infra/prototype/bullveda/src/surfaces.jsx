// surfaces.jsx — secondary main-pane surfaces (Watchlist, Elite Picks, BUY candidates, fallback)

function WatchlistSurface({ onTicker }) {
  return (
    <div className="surface">
      <div className="surf-hdr">
        <div className="surf-title">
          <span className="mono label-cap">Watchlist</span>
          <span className="mono dim2">· {WATCHLIST.length} symbols · auto-rank by score</span>
        </div>
        <div className="surf-tools">
          <div className="seg">
            <button className="seg-btn is-on">Score</button>
            <button className="seg-btn">Setup</button>
            <button className="seg-btn">Mover</button>
          </div>
          <button className="btn btn--sm">+ Add</button>
          <FreshnessPill state="live" age="18s" />
        </div>
      </div>
      <table className="dtable">
        <thead>
          <tr>
            <th className="w-sym">Symbol</th>
            <th>Name</th>
            <th className="r">Price</th>
            <th className="r">1D %</th>
            <th className="r">Score</th>
            <th>Verdict</th>
            <th>Setup</th>
            <th className="r"></th>
          </tr>
        </thead>
        <tbody>
          {WATCHLIST.map(w => (
            <tr key={w.sym} onClick={() => onTicker(w.sym)} className="dtable-row">
              <td className="mono"><b>{w.sym}</b></td>
              <td className="dim">{w.name}</td>
              <td className="r mono tabular">{w.price.toFixed(2)}</td>
              <td className={`r mono tabular ${w.chg >= 0 ? "up" : "dn"}`}>
                {w.chg >= 0 ? "+" : ""}{w.chg.toFixed(2)}%
              </td>
              <td className="r mono tabular"><b>{w.score}</b></td>
              <td>
                <Pill tone={w.verdict === "BUY" ? "gn" : w.verdict === "AVOID" ? "rd" : "amb"} small>
                  {w.verdict}
                </Pill>
              </td>
              <td className="mono dim">{w.setup}</td>
              <td className="r dim">›</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ElitePicksSurface({ onTicker }) {
  const elite = WATCHLIST.filter(w => w.score >= 70).slice(0, 8);
  return (
    <div className="surface">
      <div className="surf-hdr">
        <div className="surf-title">
          <span className="mono label-cap">Elite Picks</span>
          <span className="mono dim2">· Score ≥ 70 · all 5 pillars green · Wilson LB ≥ 50%</span>
        </div>
        <div className="surf-tools">
          <FreshnessPill state="live" age="22s" />
        </div>
      </div>
      <div className="elite-grid">
        {elite.map(e => (
          <button key={e.sym} className="elite-card" onClick={() => onTicker(e.sym)}>
            <div className="elite-card-hdr">
              <div className="mono"><b>{e.sym}</b></div>
              <Pill tone="gn" small dot>{e.verdict}</Pill>
            </div>
            <div className="elite-card-name dim">{e.name}</div>
            <div className="elite-card-row">
              <div className="elite-card-cell">
                <div className="label-cap">Score</div>
                <div className="mono kpi-tone--gn" style={{ fontSize: 22 }}>{e.score}</div>
              </div>
              <div className="elite-card-cell">
                <div className="label-cap">1D %</div>
                <div className={`mono ${e.chg >= 0 ? "up" : "dn"}`} style={{ fontSize: 16 }}>
                  {e.chg >= 0 ? "+" : ""}{e.chg.toFixed(2)}%
                </div>
              </div>
              <div className="elite-card-cell">
                <div className="label-cap">Setup</div>
                <div className="mono dim2">{e.setup}</div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function BuySurface({ onTicker }) {
  const buys = WATCHLIST.filter(w => w.verdict === "BUY");
  return (
    <div className="surface">
      <div className="surf-hdr">
        <div className="surf-title">
          <span className="mono label-cap">BUY Candidates</span>
          <span className="mono dim2">· {buys.length} passed all gates · ranked by R-multiple × Wilson LB</span>
        </div>
        <div className="surf-tools">
          <FreshnessPill state="live" age="18s" />
        </div>
      </div>
      <table className="dtable">
        <thead>
          <tr>
            <th className="w-sym">Symbol</th>
            <th>Name</th>
            <th className="r">Px</th>
            <th className="r">Entry</th>
            <th className="r">Stop</th>
            <th className="r">T1</th>
            <th className="r">R</th>
            <th className="r">Wilson</th>
            <th>Setup</th>
            <th className="r"></th>
          </tr>
        </thead>
        <tbody>
          {buys.map(w => {
            const entry = w.price * 0.995;
            const stop = w.price * 0.946;
            const t1 = w.price * 1.085;
            const r = ((t1 - entry) / (entry - stop)).toFixed(2);
            return (
              <tr key={w.sym} onClick={() => onTicker(w.sym)} className="dtable-row">
                <td className="mono"><b>{w.sym}</b></td>
                <td className="dim">{w.name}</td>
                <td className="r mono tabular">{w.price.toFixed(2)}</td>
                <td className="r mono tabular">{entry.toFixed(2)}</td>
                <td className="r mono tabular dn">{stop.toFixed(2)}</td>
                <td className="r mono tabular up">{t1.toFixed(2)}</td>
                <td className="r mono tabular"><b>{r}</b></td>
                <td className="r mono tabular">{(45 + w.score * 0.25).toFixed(0)}%</td>
                <td className="mono dim">{w.setup}</td>
                <td className="r dim">›</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StubSurface({ id }) {
  const labels = {
    screener: "Screener", industries: "Industries", themes: "Themes",
    leveraged: "Leveraged", crypto: "Crypto", events: "Events · IPO/Splits",
    premarket: "Pre-Market", pairs: "Pairs", strategies: "Strategies",
    performance: "Performance", accuracy: "Accuracy", macro: "Macro · Events",
    "options-flow": "Options Flow", alerts: "Alerts",
    playbook: "Playbook", reference: "Reference / Cheat", thesis: "Thesis Library",
    research: "Research", settings: "Settings", status: "System Status",
    capstudio: "CapStudio · RBAC", audit: "Audit · Change Hx", lab: "Research Lab",
    factor: "Factor Exposure", killed: "Killed / AVOID",
  };
  return (
    <div className="surface surf--stub">
      <div className="stub-card">
        <div className="label-cap">Workspace</div>
        <h1 className="mono">{labels[id] || id}</h1>
        <div className="dim2 mono">
          This surface is part of the L1 information architecture but not built out in this prototype.
        </div>
        <div className="stub-banner">
          <span className="state-banner-icon">⚠</span>
          <span>
            <b>Partial scaffolding</b> — nav reachable, surface not implemented.
            Click any ticker on Market Map / Watchlist / BUY to enter the 14-lens detail panel.
          </span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { WatchlistSurface, ElitePicksSurface, BuySurface, StubSurface });
