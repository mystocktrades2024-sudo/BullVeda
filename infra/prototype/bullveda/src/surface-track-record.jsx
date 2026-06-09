// surface-track-record.jsx — system-wide signal accountability surface.
// Heatmap (source × horizon) · leaderboard · decay curves · the ledger ·
// AI calibration · regime hit-rate · equity curve. Metric + horizon toggles.

const { useState: useTR, useMemo: useTRm } = React;

const TR_GROUPS = { D: "Daily · D1–D7", W: "Weekly · W1–W8", M: "Monthly · M1–M12" };
const trPct = (v, d = 1) => v == null ? "—" : (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d) + "%";
// green→red diverging cell color by aligned value (±cap %)
function heatColor(v, cap = 4) {
  if (v == null) return "var(--bg-2)";
  const t = Math.max(-1, Math.min(1, v / cap));
  if (t >= 0) return `color-mix(in oklab, var(--gn) ${Math.round(t * 72 + 8)}%, var(--bg-1))`;
  return `color-mix(in oklab, var(--rd) ${Math.round(-t * 72 + 8)}%, var(--bg-1))`;
}

function SurfaceTrackRecord({ onTicker }) {
  const SL = window.SigLedger;
  const [metric, setMetric] = useTR("edge");   // edge | raw
  const [group, setGroup] = useTR("W");          // D | W | M
  const [tab, setTab] = useTR("heatmap");
  const [srcFilter, setSrcFilter] = useTR(null);

  const hzs = useTRm(() => SL.HZ.filter(h => h.group === group), [group]);
  const board = useTRm(() => SL.leaderboard(metric), [metric]);

  return (
    <div className="surface wsx wsx--copper trk">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">TRACK RECORD · SIGNAL ACCOUNTABILITY</div>
          <h1 className="wsx-title mono">Track Record</h1>
          <div className="wsx-sub mono dim2">did our calls work? · {SL.totalCalls} signals · 8 sources · forward returns D1–M12 · direction-aligned</div>
        </div>
        <div className="wsx-hdr-r">
          <div className="trk-toggle">
            <span className="label-cap">Metric</span>
            <button className={metric === "edge" ? "is-on" : ""} onClick={() => setMetric("edge")}>Edge vs SPY</button>
            <button className={metric === "raw" ? "is-on" : ""} onClick={() => setMetric("raw")}>Raw return</button>
          </div>
          <FreshnessPill state={SL.real ? "live" : "stale"} age={SL.real ? "EOD" : "modeled"} />
        </div>
      </div>

      {SL.real ? (
        <div className="trk-banner" style={{ margin: "10px 0 4px", padding: "9px 14px", borderRadius: 10,
          background: "color-mix(in oklab, var(--gn) 9%, var(--bg-1))", border: "1px solid color-mix(in oklab, var(--gn) 30%, transparent)",
          color: "var(--ink-1)", fontSize: 12.5, lineHeight: 1.5 }}>
          <b className="up">Live forward-scored ledger.</b> Every published call is logged at signal time and
          scored forward at each horizon as it matures — direction-aligned, real returns from the append-only
          store (signal_log + audit_ledger, emitted nightly). <b>{SL.totalCalls.toLocaleString()}</b> calls across
          {" "}{SL.SOURCES.length} sources. Younger calls show partial paths labeled <b>maturing</b> until their horizon resolves.
        </div>
      ) : (
        <div className="trk-banner" style={{ margin: "10px 0 4px", padding: "10px 14px", borderRadius: 10,
          background: "color-mix(in oklab, var(--amb) 12%, var(--bg-1))", border: "1px solid color-mix(in oklab, var(--amb) 35%, transparent)",
          color: "var(--ink-1)", fontSize: 12.5, lineHeight: 1.5 }}>
          <b className="amb">Live feed unavailable — showing modeled fallback.</b> /v2/data_leaders.json could not be
          loaded, so the curves below are an illustrative model. Real resolved trades drive the <b>Portfolio</b> and
          <b> Performance</b> surfaces. Reload once the ledger feed is reachable.
        </div>
      )}

      <div className="lab-tabs trk-tabs">
        {[["heatmap", "Heatmap"], ["leaderboard", "Leaderboard"], ["decay", "Decay curves"], ["ledger", "The Ledger"], ["calibration", "AI Calibration"], ["regime", "By Regime"], ["equity", "Equity curve"]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
        {(tab === "heatmap" || tab === "decay") && (
          <div className="trk-grp">
            {Object.entries(TR_GROUPS).map(([g, l]) => <button key={g} className={`trk-grp-btn ${group === g ? "is-on" : ""}`} onClick={() => setGroup(g)} title={l}>{g === "D" ? "Daily" : g === "W" ? "Weekly" : "Monthly"}</button>)}
          </div>
        )}
      </div>

      {tab === "heatmap" && <HeatmapView SL={SL} hzs={hzs} metric={metric} group={group} />}
      {tab === "leaderboard" && <LeaderboardView board={board} metric={metric} onPick={(s) => { setSrcFilter(s); setTab("ledger"); }} />}
      {tab === "decay" && <DecayView SL={SL} hzs={hzs} board={board} metric={metric} group={group} />}
      {tab === "ledger" && <LedgerView SL={SL} metric={metric} srcFilter={srcFilter} setSrcFilter={setSrcFilter} onTicker={onTicker} />}
      {tab === "calibration" && <CalibrationView SL={SL} metric={metric} />}
      {tab === "regime" && <RegimeView SL={SL} metric={metric} />}
      {tab === "equity" && <EquityView SL={SL} metric={metric} />}

      <div className="pf-note mono dim2">
        Every published call is logged at signal time &amp; scored forward — <b>direction-aligned</b> (a short that falls is a win). <b>{metric === "edge" ? "Edge vs SPY" : "Raw return"}</b> shown · only matured horizons enter stats; younger calls show partial paths labeled <b>maturing</b>. {SL.real ? "Live ledger · signal_log + audit_ledger." : "Modeled fallback — live feed unavailable."}
      </div>
    </div>
  );
}

// ── Heatmap: source × horizon ───────────────────────────────────
function HeatmapView({ SL, hzs, metric, group }) {
  const rows = SL.SOURCES.map(src => ({ src, cells: hzs.map(hz => ({ hz, ...SL.aggregate(src.id, hz, metric) })) }));
  return (
    <div className="wsx-body">
      <div className="trk-heat-wrap">
        <table className="trk-heat">
          <thead><tr><th className="trk-heat-corner">Source ↓ / Horizon →</th>{hzs.map(h => <th key={h.id} className="trk-heat-h">{h.label}</th>)}<th className="trk-heat-h trk-heat-opt">Peak</th></tr></thead>
          <tbody>{rows.map(({ src, cells }) => {
            let best = null; cells.forEach(c => { if (c.mean != null && (!best || c.mean > best.mean)) best = c; });
            return (
              <tr key={src.id}>
                <th className="trk-heat-src">{src.label}</th>
                {cells.map(c => (
                  <td key={c.hz.id} className="trk-heat-cell" style={{ background: heatColor(c.mean) }} title={c.n ? `${src.label} ${c.hz.label}: ${trPct(c.mean)} · hit ${c.hit}% · n=${c.n}` : "maturing"}>
                    {c.mean == null ? <span className="trk-mat">·</span> : <><span className="trk-cell-v">{c.mean >= 0 ? "+" : "−"}{Math.abs(c.mean).toFixed(1)}</span><span className="trk-cell-hit">{c.hit}%</span></>}
                  </td>
                ))}
                <td className="trk-heat-cell trk-heat-opt">{best ? <b className="up">{best.hz.label}</b> : "—"}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      <div className="trk-legend mono dim2">
        <span>Each cell: avg {metric === "edge" ? "edge vs SPY" : "return"} (top) · hit-rate (bottom).</span>
        <span className="trk-scale"><span style={{ background: heatColor(-4) }} />−4%<span style={{ background: heatColor(0) }} />0<span style={{ background: heatColor(4) }} />+4%</span>
        <span><b>Peak</b> = horizon of max edge → the optimal holding period for that engine.</span>
      </div>
    </div>
  );
}

// ── Leaderboard ─────────────────────────────────────────────────
function LeaderboardView({ board, metric, onPick }) {
  return (
    <div className="wsx-body">
      <table className="dtable wsx-tbl trk-lb">
        <thead><tr>
          <th>#</th><th>Source</th><th className="r">Hit rate</th><th className="r">Avg {metric === "edge" ? "edge" : "ret"}</th>
          <th className="r">Profit factor</th><th>Optimal hold</th><th>Best call</th><th>Worst call</th><th className="r">Sample</th><th>Significance</th>
        </tr></thead>
        <tbody>{board.map((s, i) => (
          <tr key={s.id} onClick={() => onPick(s.id)} className="trk-lb-row">
            <td className="mono dim2"><b className={i < 3 ? "copper" : ""}>{i + 1}</b></td>
            <td><b>{s.label}</b></td>
            <td className="r tabular"><span className={`trk-hit trk-hit--${s.avgHit >= 55 ? "gn" : s.avgHit >= 48 ? "amb" : "rd"}`}>{s.avgHit}%</span></td>
            <td className={`r tabular ${s.avgEdge >= 0 ? "up" : "dn"}`}><b>{trPct(s.avgEdge)}</b></td>
            <td className={`r tabular ${s.pf >= 1.5 ? "up" : s.pf >= 1 ? "" : "dn"}`}>{s.pf.toFixed(2)}</td>
            <td className="mono">{s.best ? <span className="trk-opt-badge">{s.best.hz} · {trPct(s.best.mean)}</span> : "—"}</td>
            <td className="mono dim2">{s.best1 ? <><b>{s.best1.sym}</b> <span className="up">{trPct(s.best1.v)}</span></> : "—"}</td>
            <td className="mono dim2">{s.worst1 ? <><b>{s.worst1.sym}</b> <span className="dn">{trPct(s.worst1.v)}</span></> : "—"}</td>
            <td className="r tabular dim2">{s.nMatured}/{s.nTotal}</td>
            <td>{s.sig ? <span className="trk-sig trk-sig--ok">t={s.tstat} · real</span> : <span className="trk-sig trk-sig--no">t={s.tstat} · noise</span>}</td>
          </tr>
        ))}</tbody>
      </table>
      <div className="lab-verdict mono dim2">Ranked by avg {metric === "edge" ? "edge vs SPY" : "raw return"} over the swing band (W1–W4). <b>t≥2</b> ≈ the edge is statistically distinguishable from luck at this sample. Click a row → its calls in the Ledger.</div>
    </div>
  );
}

// ── Decay curves ────────────────────────────────────────────────
function DecayView({ SL, hzs, board, metric, group }) {
  const w = 920, h = 300, padL = 44, padR = 16, padT = 16, padB = 28;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const xs = hzs.map((hz, i) => padL + (hzs.length === 1 ? plotW / 2 : (i / (hzs.length - 1)) * plotW));
  const all = board.flatMap(s => s.decay.filter(d => d.group === group && d.n > 0).map(d => d.mean));
  const max = Math.max(2, ...all), min = Math.min(-2, ...all);
  const y = v => padT + plotH - ((v - min) / (max - min)) * plotH;
  const COL = ["var(--copper)", "var(--cy)", "var(--gn)", "var(--violet)", "var(--amb)", "var(--blue)", "var(--rd)", "var(--ink-2)"];
  const [hidden, setHidden] = useTR({});
  return (
    <div className="wsx-body">
      <div className="trk-decay-legend">{board.map((s, i) => (
        <button key={s.id} className={`trk-dl ${hidden[s.id] ? "off" : ""}`} onClick={() => setHidden(h => ({ ...h, [s.id]: !h[s.id] }))}>
          <span className="trk-dl-dot" style={{ background: COL[i % COL.length] }} />{s.label}
        </button>
      ))}</div>
      <div className="pf-chart trk-chart"><svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {[max, (max + min) / 2, 0, min].map((gv, k) => <g key={k}><line x1={padL} y1={y(gv)} x2={w - padR} y2={y(gv)} stroke="var(--line)" strokeDasharray={gv === 0 ? "none" : "1 5"} opacity={gv === 0 ? 0.7 : 0.4} /><text x={padL - 6} y={y(gv) + 3} fontSize="10" textAnchor="end" className="mono" fill="var(--ink-3)">{gv >= 0 ? "+" : ""}{gv.toFixed(1)}</text></g>)}
        {hzs.map((hz, i) => <text key={hz.id} x={xs[i]} y={h - 8} fontSize="10" textAnchor="middle" className="mono" fill="var(--ink-3)">{hz.label}</text>)}
        {board.map((s, si) => { if (hidden[s.id]) return null; const ds = s.decay.filter(d => d.group === group); const pts = ds.map((d, i) => d.n > 0 ? `${xs[i]},${y(d.mean)}` : null).filter(Boolean).join(" "); return (
          <g key={s.id}><polyline points={pts} fill="none" stroke={COL[si % COL.length]} strokeWidth="2" opacity="0.9" />{ds.map((d, i) => d.n > 0 ? <circle key={i} cx={xs[i]} cy={y(d.mean)} r="2.6" fill={COL[si % COL.length]} /> : null)}</g>
        ); })}
      </svg></div>
      <div className="lab-verdict mono dim2">Avg {metric === "edge" ? "edge vs SPY" : "return"} by horizon. Where a line <b>peaks</b> is the engine's best holding period; where it crosses zero is its <b>half-life</b> — hold past that and the edge is gone.</div>
    </div>
  );
}

// ── The Ledger ──────────────────────────────────────────────────
function LedgerView({ SL, metric, srcFilter, setSrcFilter, onTicker }) {
  const [dir, setDir] = useTR("all");
  const [view, setView] = useTR("path"); // path | full
  const [period, setPeriod] = useTR("all"); // 1m|3m|6m|1y|ytd|all
  const [tickerQ, setTickerQ] = useTR(""); // ticker filter (comma/space-separated, substring match)
  const [page, setPage] = useTR(0);
  const PAGE = 25;
  const all = useTRm(() => SL.ledger(metric, srcFilter ? { source: srcFilter } : null).filter(r => dir === "all" || r.dir === dir), [metric, srcFilter, dir]);
  const ytdDays = Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 1).getTime()) / 86400000);
  const maxAge = period === "all" ? Infinity : period === "ytd" ? ytdDays : ({ "1m": 30, "3m": 90, "6m": 180, "1y": 365 }[period]);
  // ticker filter — accepts one or many symbols (space/comma separated); a row matches
  // if its symbol starts with ANY token (so "nv aap" surfaces NVDA + AAPL).
  const tickerTokens = useTRm(() => tickerQ.toUpperCase().split(/[\s,]+/).filter(Boolean), [tickerQ]);
  const rows = useTRm(() => all.filter(r =>
    r.age <= maxAge &&
    (tickerTokens.length === 0 || tickerTokens.some(tok => String(r.sym).toUpperCase().startsWith(tok)))
  ), [all, maxAge, tickerTokens]);
  const PERIODS = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["ytd", "YTD"], ["all", "All"]];
  // sortable: col is "age" | "sym" | "label" | "dir" | "refPrice" | "last" | "maturedN"
  // | "status" | a horizon id (D1…M12, sorted by that horizon's matured value).
  const [srt, setSrt] = useTR({ col: "age", dir: 1 });
  const sortBy = (col) => setSrt(s => s.col === col ? { col, dir: -s.dir } : { col, dir: col === "age" ? 1 : -1 });
  const sortedRows = useTRm(() => {
    const PUSH = srt.dir > 0 ? Infinity : -Infinity; // unmatured horizon cells sort to the end
    const val = (r) => {
      switch (srt.col) {
        case "age": return r.age;
        case "sym": return r.sym;
        case "label": return r.label;
        case "dir": return r.dir;
        case "refPrice": return r.refPrice;
        case "last": return r.last ? r.last.v : PUSH;
        case "maturedN": return r.maturedN;
        case "status": return r.status;
        default: { const p = r.path.find(p => p.hz === srt.col); return (p && p.mature) ? p.v : PUSH; }
      }
    };
    return [...rows].sort((a, b) => {
      const av = val(a), bv = val(b);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * srt.dir;
      return String(av).localeCompare(String(bv)) * srt.dir;
    });
  }, [rows, srt]);
  const pages = Math.max(1, Math.ceil(sortedRows.length / PAGE));
  const pg = Math.min(page, pages - 1);
  const pageRows = sortedRows.slice(pg * PAGE, pg * PAGE + PAGE);
  const pickPeriod = (p) => { setPeriod(p); setPage(0); };
  React.useEffect(() => { setPage(0); }, [dir, srcFilter, view, tickerQ, period]);
  // sortable header cell — arrow shows active column + direction
  const Sh = ({ col, label, r, cls }) => (
    <th className={`${cls || ""} ${r ? "r" : ""} ${srt.col === col ? "is-active" : ""}`.trim()} style={{ cursor: "pointer" }} onClick={() => sortBy(col)}>
      {label}{srt.col === col ? <span className="wsx-arr mono">{srt.dir > 0 ? "▲" : "▼"}</span> : null}
    </th>
  );
  const NH = SL.HZ.length;
  const exportCSV = () => {
    const head = ["Logged date", "Days ago", "Symbol", "Source", "Direction", "Ref price", "Status", "Matured", ...SL.HZ.map(h => h.id)];
    const lines = [head.join(",")];
    rows.forEach(r => {
      const d = new Date(Date.now() - r.age * 86400000).toISOString().slice(0, 10);
      const cells = [d, r.age, r.sym, r.label, r.dir, r.refPrice, r.status, `${r.maturedN}/${NH}`];
      SL.HZ.forEach((h, i) => { const p = r.path[i]; cells.push(p && p.mature ? p.v : ""); });
      lines.push(cells.map(c => typeof c === "string" && c.indexOf(",") >= 0 ? `"${c}"` : c).join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = `track-record_${metric}_${srcFilter || "all"}${tickerTokens.length ? "_" + tickerTokens.join("-") : ""}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const spark = (path) => {
    const mat = path.filter(p => p.mature); if (mat.length < 2) return null;
    const w = 80, h = 22, vs = mat.map(p => p.v), mn = Math.min(0, ...vs), mx = Math.max(0, ...vs);
    const x = i => (i / (mat.length - 1)) * w, y = v => h - ((v - mn) / ((mx - mn) || 1)) * (h - 4) - 2;
    const up = mat[mat.length - 1].v >= 0;
    return <svg width={w} height={h} className="trk-spark"><line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--line)" strokeDasharray="1 3" /><polyline points={mat.map((p, i) => `${x(i)},${y(p.v)}`).join(" ")} fill="none" stroke={`var(--${up ? "gn" : "rd"})`} strokeWidth="1.5" /></svg>;
  };
  return (
    <div className="wsx-body">
      <div className="trk-ledger-bar">
        <div className="trk-chips">
          <button className={`trk-chip ${!srcFilter ? "is-on" : ""}`} onClick={() => setSrcFilter(null)}>All sources</button>
          {SL.SOURCES.map(s => <button key={s.id} className={`trk-chip ${srcFilter === s.id ? "is-on" : ""}`} onClick={() => setSrcFilter(s.id)}>{s.label}</button>)}
        </div>
        <div className="trk-led-acts">
          <div className="trk-ticker-filter">
            <input className="trk-ticker-input mono" type="text" value={tickerQ}
              onChange={e => setTickerQ(e.target.value)}
              placeholder="🔎 ticker…" spellCheck={false} autoCapitalize="characters"
              title="Filter the ledger by symbol — one or many (e.g. NVDA AAPL)" />
            {tickerQ ? <button className="trk-ticker-clear" onClick={() => setTickerQ("")} title="Clear ticker filter">✕</button> : null}
          </div>
          <div className="trk-toggle trk-toggle--sm">
            {PERIODS.map(([id, l]) => <button key={id} className={period === id ? "is-on" : ""} onClick={() => pickPeriod(id)} title={`Show calls from the last ${l}`}>{l}</button>)}
          </div>
          <div className="trk-toggle trk-toggle--sm">
            {["all", "long", "short"].map(d => <button key={d} className={dir === d ? "is-on" : ""} onClick={() => setDir(d)}>{d}</button>)}
          </div>
          <div className="trk-toggle trk-toggle--sm">
            <button className={view === "path" ? "is-on" : ""} onClick={() => setView("path")}>Path</button>
            <button className={view === "full" ? "is-on" : ""} onClick={() => setView("full")}>All horizons</button>
          </div>
          <button className="trk-export" onClick={exportCSV} title="Download every call × every horizon as CSV (opens in Excel)">⤓ Export CSV</button>
        </div>
      </div>
      {view === "path" ? (
        <table className="dtable wsx-tbl trk-led">
          <thead><tr><Sh col="age" label="Logged" /><Sh col="age" label="Date" /><Sh col="sym" label="Symbol" /><Sh col="label" label="Source" /><Sh col="dir" label="Dir" /><Sh col="refPrice" label="Ref px" r /><th>Forward path</th><Sh col="last" label="Latest" r /><Sh col="maturedN" label="Matured" r /><Sh col="status" label="Status" /></tr></thead>
          <tbody>{pageRows.map(r => {
            const d = new Date(Date.now() - r.age * 86400000);
            const dStr = d.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "2-digit" });
            return (
            <tr key={r.id} onClick={() => onTicker && onTicker(r.sym)}>
              <td className="mono dim2">{r.age}d ago</td>
              <td className="mono dim2">{dStr}</td>
              <td><b>{r.sym}</b></td>
              <td className="dim2">{r.label}</td>
              <td><span className={r.dir === "long" ? "up" : "dn"}>{r.dir === "long" ? "LONG" : "SHORT"}</span></td>
              <td className="r tabular dim">${r.refPrice.toFixed(2)}</td>
              <td>{spark(r.path) || <span className="trk-mat-lbl mono dim2">maturing…</span>}</td>
              <td className={`r tabular ${r.last && r.last.v >= 0 ? "up" : "dn"}`}>{r.last ? <b>{trPct(r.last.v)}</b> : "—"}<span className="dim2 mono" style={{ fontSize: 9 }}> {r.last ? r.last.hz || "" : ""}</span></td>
              <td className="r tabular dim2">{r.maturedN}/{NH}</td>
              <td><span className={`trk-status trk-status--${r.status}`}>{r.status}</span></td>
            </tr>
            );
          })}</tbody>
        </table>
      ) : (
        <div className="trk-full-wrap">
          <table className="trk-full">
            <thead><tr>
              <Sh col="age" label="Date" cls="trk-full-sticky" /><Sh col="sym" label="Sym" cls="trk-full-sticky2" /><Sh col="label" label="Src" /><Sh col="dir" label="Dir" />
              {SL.HZ.map(h => <Sh key={h.id} col={h.id} label={h.label} cls="trk-full-hz" />)}
            </tr></thead>
            <tbody>{pageRows.map(r => {
              const dStr = new Date(Date.now() - r.age * 86400000).toLocaleDateString("en-US", { day: "2-digit", month: "short" });
              return (
                <tr key={r.id} onClick={() => onTicker && onTicker(r.sym)}>
                  <td className="trk-full-sticky mono dim2">{dStr}</td>
                  <td className="trk-full-sticky2"><b>{r.sym}</b></td>
                  <td className="dim2" style={{ fontSize: 10 }}>{r.label}</td>
                  <td><span className={`mono ${r.dir === "long" ? "up" : "dn"}`} style={{ fontSize: 10 }}>{r.dir === "long" ? "L" : "S"}</span></td>
                  {r.path.map((p, i) => (
                    <td key={i} className="trk-full-cell" style={{ background: p.mature ? heatColor(p.v, 6) : "var(--bg-2)" }} title={p.mature ? `${SL.HZ[i].label}: ${trPct(p.v)}` : "maturing"}>
                      {p.mature ? (p.v >= 0 ? "+" : "−") + Math.abs(p.v).toFixed(1) : "·"}
                    </td>
                  ))}
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
      <div className="trk-pager">
        <button className="trk-page-btn" disabled={pg <= 0} onClick={() => setPage(pg - 1)}>‹ Prev</button>
        <span className="mono dim2">{rows.length === 0 ? "0 calls" : `${pg * PAGE + 1}–${Math.min(rows.length, pg * PAGE + PAGE)} of ${rows.length}`} · page {pg + 1}/{pages}</span>
        <button className="trk-page-btn" disabled={pg >= pages - 1} onClick={() => setPage(pg + 1)}>Next ›</button>
      </div>
      <div className="lab-verdict mono dim2">{rows.length} calls{tickerTokens.length ? ` · ${tickerTokens.join(", ")}` : ""}{srcFilter ? ` · ${SL.SOURCE_BY[srcFilter].label}` : ""} · {period === "all" ? "all history (≤1y)" : period === "ytd" ? "year-to-date" : "last " + period.toUpperCase()} · {metric === "edge" ? "edge vs SPY" : "raw return"}. <b>⤓ Export CSV</b> downloads the filtered set across all {NH} horizons. Click a row → ticker detail.</div>
    </div>
  );
}

// ── AI Calibration ──────────────────────────────────────────────
function CalibrationView({ SL, metric }) {
  const cal = useTRm(() => SL.calibration(metric), [metric]);
  const w = 360, h = 300, pad = 40, plot = w - pad * 2;
  const x = p => pad + p * plot, y = p => h - pad - p * (h - pad * 2);
  return (
    <div className="pf-expo">
      <div className="lab-card">
        <div className="lab-card-h mono">AI PREDICTIONS · CALIBRATION</div>
        <svg width={w} height={h} className="trk-calib">
          <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--line-2)" /><line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="var(--line-2)" />
          <line x1={pad} y1={h - pad} x2={w - pad} y2={pad} stroke="var(--ink-3)" strokeDasharray="4 4" opacity="0.6" />
          <text x={w / 2} y={h - 8} fontSize="10" textAnchor="middle" className="mono" fill="var(--ink-3)">predicted probability →</text>
          <text x={12} y={h / 2} fontSize="10" textAnchor="middle" className="mono" fill="var(--ink-3)" transform={`rotate(-90 12 ${h / 2})`}>realized hit-rate →</text>
          {cal.map((c, i) => c.realized != null && <g key={i}><line x1={x(c.pred)} y1={y(c.pred)} x2={x(c.pred)} y2={y(c.realized)} stroke="var(--copper)" opacity="0.4" /><circle cx={x(c.pred)} cy={y(c.realized)} r="5" fill="var(--copper)" /><text x={x(c.pred)} y={y(c.realized) - 9} fontSize="9" textAnchor="middle" className="mono" fill="var(--ink-1)">{(c.realized * 100).toFixed(0)}%</text></g>)}
        </svg>
        <div className="lab-verdict mono dim2">Dots on the dashed line = perfectly calibrated (a "70%" call wins 70% of the time). Above = under-confident, below = over-confident.</div>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">CALIBRATION TABLE</div>
        <table className="dtable wsx-tbl"><thead><tr><th>Predicted</th><th className="r">Realized</th><th className="r">n</th><th>Read</th></tr></thead>
          <tbody>{cal.map((c, i) => <tr key={i}><td className="mono">{(c.lo * 100).toFixed(0)}–{(c.hi * 100).toFixed(0)}%</td><td className={`r tabular ${c.realized != null && c.realized >= c.pred ? "up" : "dn"}`}>{c.realized != null ? (c.realized * 100).toFixed(0) + "%" : "—"}</td><td className="r tabular dim2">{c.n}</td><td className="dim2">{c.realized == null ? "—" : c.realized >= c.pred ? "well-calibrated" : "over-confident"}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}

// ── By Regime ───────────────────────────────────────────────────
function RegimeView({ SL, metric }) {
  const rg = useTRm(() => SL.regimeHits(metric), [metric]);
  const C = { bull: "gn", chop: "amb", bear: "rd" };
  return (
    <div className="wsx-body">
      <table className="dtable wsx-tbl trk-regime">
        <thead><tr><th>Source</th>{["bull", "chop", "bear"].map(r => <th key={r} className="r" style={{ textTransform: "capitalize", color: `var(--${C[r]})` }}>{r}</th>)}</tr></thead>
        <tbody>{SL.SOURCES.map((src, i) => (
          <tr key={src.id}><td><b>{src.label}</b></td>{["bull", "chop", "bear"].map(r => { const cell = rg[r][i]; return <td key={r} className="r tabular">{cell.hit == null ? <span className="dim2">—</span> : <span style={{ color: `var(--${cell.hit >= 55 ? "gn" : cell.hit >= 48 ? "amb" : "rd"})`, fontWeight: 700 }}>{cell.hit}%</span>}<span className="dim2 mono" style={{ fontSize: 9 }}> n{cell.n}</span></td>; })}</tr>
        ))}</tbody>
      </table>
      <div className="lab-verdict mono dim2">Hit-rate by market regime (at W2). The honest question: does an engine only work in a bull tape? Sources that hold up in <b>chop</b> and <b>bear</b> carry real, regime-robust edge.</div>
    </div>
  );
}

// ── Equity curve ────────────────────────────────────────────────
function EquityView({ SL, metric }) {
  const [src, setSrc] = useTR("__all");
  const [hz, setHz] = useTR("W2");
  const pts = useTRm(() => SL.equityCurve(src, hz, metric), [src, hz, metric]);
  const w = 920, h = 280, padL = 44, padR = 16, padT = 16, padB = 24;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const vs = pts.map(p => p.v); const mn = Math.min(0, ...vs), mx = Math.max(0, ...vs);
  const x = i => padL + (i / Math.max(1, pts.length - 1)) * plotW, y = v => padT + plotH - ((v - mn) / ((mx - mn) || 1)) * plotH;
  const final = pts[pts.length - 1] ? pts[pts.length - 1].v : 0;
  return (
    <div className="wsx-body">
      <div className="trk-ledger-bar">
        <div className="trk-chips"><button className={`trk-chip ${src === "__all" ? "is-on" : ""}`} onClick={() => setSrc("__all")}>All sources</button>{SL.SOURCES.map(s => <button key={s.id} className={`trk-chip ${src === s.id ? "is-on" : ""}`} onClick={() => setSrc(s.id)}>{s.label}</button>)}</div>
        <div className="trk-toggle trk-toggle--sm">{["W1", "W2", "W4", "M1", "M3"].map(hh => <button key={hh} className={hz === hh ? "is-on" : ""} onClick={() => setHz(hh)}>{hh}</button>)}</div>
      </div>
      <div className="trk-eq-head mono"><span className="dim2">Cumulative {metric === "edge" ? "edge vs SPY" : "return"} following every call · held {hz}</span><span className={`trk-eq-final ${final >= 0 ? "up" : "dn"}`}>{trPct(final, 1)} cumulative</span></div>
      <div className="pf-chart trk-chart"><svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <defs><linearGradient id="trkeq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${final >= 0 ? "gn" : "rd"})`} stopOpacity="0.25" /><stop offset="100%" stopColor={`var(--${final >= 0 ? "gn" : "rd"})`} stopOpacity="0" /></linearGradient></defs>
        {[mx, (mx + mn) / 2, 0, mn].map((gv, k) => <g key={k}><line x1={padL} y1={y(gv)} x2={w - padR} y2={y(gv)} stroke="var(--line)" strokeDasharray={gv === 0 ? "none" : "1 5"} opacity={gv === 0 ? 0.7 : 0.4} /><text x={padL - 6} y={y(gv) + 3} fontSize="10" textAnchor="end" className="mono" fill="var(--ink-3)">{gv >= 0 ? "+" : ""}{gv.toFixed(0)}%</text></g>)}
        <path d={`M ${x(0)},${y(0)} L ${pts.map(p => `${x(p.i)},${y(p.v)}`).join(" L ")} L ${x(pts.length - 1)},${y(0)} Z`} fill="url(#trkeq)" />
        <polyline points={pts.map(p => `${x(p.i)},${y(p.v)}`).join(" ")} fill="none" stroke={`var(--${final >= 0 ? "gn" : "rd"})`} strokeWidth="2" />
      </svg></div>
      <div className="lab-verdict mono dim2">Hypothetical cumulative {metric === "edge" ? "edge" : "return"} if you took every {src === "__all" ? "" : SL.SOURCE_BY[src].label + " "}call and held {hz} — equal-weighted, in signal order. A rising curve = the engine adds value through the cycle.</div>
    </div>
  );
}

window.SurfaceTrackRecord = SurfaceTrackRecord;
