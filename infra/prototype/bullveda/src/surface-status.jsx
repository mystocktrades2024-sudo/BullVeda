// surface-status.jsx — System Status · observability dashboard.
// Pipeline flow (EODHD → Schwab → ingest workers → Supabase → app), per-source
// health, throughput/latency sparklines, API quotas, job runs, and incidents.

const { useState: useSt, useEffect: useSte, useMemo: useStm } = React;

// ── seeded jitter so the dashboard feels live ──────────────────
function sJit(seed, n, base, amp) {
  const out = []; let s = seed;
  for (let i = 0; i < n; i++) { s = (s * 1103515245 + 12345) & 0x7fffffff; out.push(base + (s / 0x7fffffff - 0.5) * amp); }
  return out;
}

const ST_NODES = [
  { id: "eodhd", label: "EODHD All-In-One", kind: "source", state: "ok", sub: "EOD · fundamentals · news · calendar", lat: 142, rps: 38, quota: 0.61 },
  { id: "schwab", label: "Schwab API", kind: "source", state: "ok", sub: "quotes · chains · Greeks · minute bars", lat: 88, rps: 51, quota: 0.44 },
  { id: "ingest", label: "Ingest Workers", kind: "compute", state: "ok", sub: "6 launchd jobs · normalize · score", lat: 310, rps: 22 },
  { id: "supabase", label: "Supabase", kind: "store", state: "degraded", sub: "Postgres · row store · realtime", lat: 64, rps: 44, quota: 0.78 },
  { id: "app", label: "Terminal App", kind: "app", state: "ok", sub: "live surfaces · 6s poll", lat: 12, rps: 0 },
];

const ST_FEEDS = [
  { src: "EODHD", feed: "EOD prices", state: "ok", fresh: "2m ago", rows: "11,940", cov: "100%", tone: "gn" },
  { src: "EODHD", feed: "Fundamentals", state: "ok", fresh: "6h ago", rows: "8,210", cov: "98%", tone: "gn" },
  { src: "EODHD", feed: "News / sentiment", state: "ok", fresh: "40s ago", rows: "1,422", cov: "live", tone: "gn" },
  { src: "EODHD", feed: "Earnings calendar", state: "ok", fresh: "1h ago", rows: "612", cov: "100%", tone: "gn" },
  { src: "Schwab", feed: "Real-time quotes", state: "ok", fresh: "6s ago", rows: "live", cov: "100%", tone: "gn" },
  { src: "Schwab", feed: "Options chains", state: "ok", fresh: "6s ago", rows: "live", cov: "94%", tone: "gn" },
  { src: "Schwab", feed: "Minute bars", state: "lag", fresh: "94s ago", rows: "live", cov: "lagging", tone: "amb" },
  { src: "Supabase", feed: "signal_ledger write", state: "degraded", fresh: "retrying", rows: "queue 38", cov: "p95 ↑", tone: "amb" },
];

const ST_JOBS = [
  { job: "eod_ingest", cron: "17:10 ET daily", last: "ok · 02:14", next: "in 19h", tone: "gn" },
  { job: "intraday_quotes", cron: "every 6s", last: "ok · 6s ago", next: "now", tone: "gn" },
  { job: "options_chains", cron: "every 6s", last: "ok · 6s ago", next: "now", tone: "gn" },
  { job: "score_engine", cron: "every 5m", last: "ok · 3m ago", next: "in 2m", tone: "gn" },
  { job: "ledger_score_fwd", cron: "nightly 21:00", last: "ok · 21:00", next: "in 23h", tone: "gn" },
  { job: "supabase_compaction", cron: "weekly Sun", last: "warn · slow", next: "Sun", tone: "amb" },
];

const ST_INCIDENTS = [
  { t: "14:02", sev: "degraded", node: "Supabase", msg: "Write p95 latency 64→210ms · realtime backpressure · queue draining", tone: "amb" },
  { t: "09:31", sev: "resolved", node: "Schwab", msg: "Token refresh hiccup · 2 quote polls dropped · auto-recovered in 12s", tone: "gn" },
  { t: "02:14", sev: "info", node: "EODHD", msg: "Nightly EOD ingest completed · 11,940 symbols · 0 errors", tone: "cy" },
];

const ST_STATE = { ok: { c: "gn", l: "Operational" }, degraded: { c: "amb", l: "Degraded" }, lag: { c: "amb", l: "Lagging" }, down: { c: "rd", l: "Down" } };

function SurfaceStatus() {
  const [tick, setTick] = useSt(0);
  const [view, setView] = useSt("pipeline");
  useSte(() => { const t = setInterval(() => setTick(x => x + 1), 3000); return () => clearInterval(t); }, []);
  const overall = ST_NODES.some(n => n.state === "down") ? "down" : ST_NODES.some(n => n.state === "degraded" || n.state === "lag") ? "degraded" : "ok";
  const upPct = 99.95 - (overall === "ok" ? 0 : 0.07);

  return (
    <div className="surface wsx wsx--cy stat-srf">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SYSTEM STATUS · OBSERVABILITY</div>
          <h1 className="wsx-title mono">System Status</h1>
          <div className="wsx-sub mono dim2">data pipeline health · EODHD → Schwab → ingest → Supabase → app · throughput · latency · quotas · incidents</div>
        </div>
        <div className="wsx-hdr-r">
          <span className={`stat-overall stat-overall--${ST_STATE[overall].c}`}><span className="stat-overall-dot" /> {overall === "ok" ? "ALL SYSTEMS OPERATIONAL" : "DEGRADED · 1 service"}</span>
          <FreshnessPill state="live" age="3s" />
        </div>
      </div>

      <div className="lab-tabs stat-viewtabs">
        {[["pipeline", "Pipeline & Feeds"], ["supabase", "Supabase · Data"]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${view === id ? "is-on" : ""}`} onClick={() => setView(id)}>{l}</button>
        ))}
      </div>

      {view === "supabase" ? <SurfaceSupabase embedded /> : (
      <React.Fragment>

      <div className="stat-kpis">
        <StatKpi k="Uptime · 30d" v={`${upPct.toFixed(2)}%`} tone="gn" s="SLA 99.9%" />
        <StatKpi k="Pipeline latency" v="318ms" tone="gn" s="source→app p50" />
        <StatKpi k="Ingest throughput" v="161 rps" tone="cy" s="across 6 workers" />
        <StatKpi k="Active feeds" v="7 / 8" tone="amb" s="1 lagging" />
        <StatKpi k="Open incidents" v="1" tone="amb" s="Supabase degraded" />
        <StatKpi k="Error rate · 1h" v="0.04%" tone="gn" s="12 / 31.2k req" />
      </div>

      {/* pipeline flow */}
      <div className="lab-card">
        <div className="lab-card-h mono">DATA PIPELINE <span className="dim2">· source → ingest → store → app · click a node for detail</span></div>
        <div className="stat-flow">
          {ST_NODES.map((n, i) => (
            <React.Fragment key={n.id}>
              <PipelineNode n={n} tick={tick} />
              {i < ST_NODES.length - 1 && <div className={`stat-arrow stat-arrow--${ST_NODES[i + 1].state === "down" ? "rd" : (n.state !== "ok" || ST_NODES[i + 1].state !== "ok") ? "amb" : "gn"}`}>
                <span className="stat-arrow-flow" /><span className="stat-arrow-head">→</span>
              </div>}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="stat-2col">
        <div className="lab-card">
          <div className="lab-card-h mono">FEED HEALTH <span className="dim2">· freshness · coverage</span></div>
          <table className="dtable wsx-tbl stat-tbl">
            <thead><tr><th>Source</th><th>Feed</th><th>State</th><th className="r">Fresh</th><th className="r">Rows</th><th className="r">Coverage</th></tr></thead>
            <tbody>{ST_FEEDS.map((f, i) => (
              <tr key={i}>
                <td className="mono dim2">{f.src}</td>
                <td className="mono"><b>{f.feed}</b></td>
                <td><span className={`stat-pill stat-pill--${f.tone}`}>{f.state === "ok" ? "OK" : f.state === "lag" ? "LAG" : "DEGRADED"}</span></td>
                <td className="r mono tabular dim2">{f.fresh}</td>
                <td className="r mono tabular">{f.rows}</td>
                <td className={`r mono tabular ${f.tone === "gn" ? "up" : "warn"}`}>{f.cov}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">API QUOTAS <span className="dim2">· daily budget consumed</span></div>
          <div className="stat-quotas">
            {[{ k: "EODHD calls", v: 0.61, n: "61,200 / 100k", tone: "gn" }, { k: "Schwab calls", v: 0.44, n: "init", tone: "gn" }, { k: "Supabase rows", v: 0.78, n: "780k / 1M", tone: "amb" }, { k: "Supabase storage", v: 0.52, n: "4.2 / 8 GB", tone: "gn" }, { k: "Realtime conns", v: 0.33, n: "66 / 200", tone: "gn" }].map((q, i) => (
              <div key={i} className="stat-quota">
                <div className="stat-quota-top"><span className="mono">{q.k}</span><span className="mono dim2">{q.n}</span></div>
                <div className="stat-quota-track"><div className={`stat-quota-fill kpi-tone-bg--${q.tone}`} style={{ width: `${q.v * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="stat-2col">
        <div className="lab-card">
          <div className="lab-card-h mono">SCHEDULED JOBS <span className="dim2">· launchd / cron</span></div>
          <table className="dtable wsx-tbl stat-tbl">
            <thead><tr><th>Job</th><th>Schedule</th><th>Last run</th><th className="r">Next</th></tr></thead>
            <tbody>{ST_JOBS.map((j, i) => (
              <tr key={i}>
                <td className="mono"><span className={`stat-dot stat-dot--${j.tone}`} /><b>{j.job}</b></td>
                <td className="mono dim2">{j.cron}</td>
                <td className={`mono ${j.tone === "gn" ? "up" : "warn"}`}>{j.last}</td>
                <td className="r mono tabular dim2">{j.next}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">INCIDENT FEED <span className="dim2">· last 24h</span></div>
          <div className="stat-incidents">
            {ST_INCIDENTS.map((inc, i) => (
              <div key={i} className="stat-inc">
                <span className="stat-inc-t mono dim2">{inc.t}</span>
                <span className={`stat-pill stat-pill--${inc.tone}`}>{inc.sev.toUpperCase()}</span>
                <span className="stat-inc-body"><b className="mono">{inc.node}</b> <span className="dim2">{inc.msg}</span></span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="pf-note mono dim2">
        Observability for the data layer — <b>EODHD</b> (history · fundamentals · news · calendar) and <b>Schwab</b> (real-time quotes · option chains · Greeks) flow through <b>ingest workers</b> into <b>Supabase</b> and out to the terminal. Metrics are simulated in this prototype; wire to your real status endpoints / Supabase logs &amp; the Schwab + EODHD quota APIs to make it live.
      </div>
      </React.Fragment>
      )}
    </div>
  );
}

function StatKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

function PipelineNode({ n, tick }) {
  const st = ST_STATE[n.state];
  const spark = useStm(() => sJit(n.id.charCodeAt(0) + tick, 16, n.lat, n.lat * 0.5), [tick, n.id]);
  const w = 120, h = 30, mn = Math.min(...spark), mx = Math.max(...spark);
  const pts = spark.map((v, i) => `${(i / (spark.length - 1)) * w},${h - ((v - mn) / ((mx - mn) || 1)) * (h - 4) - 2}`).join(" ");
  return (
    <div className={`stat-node stat-node--${st.c}`}>
      <div className="stat-node-top">
        <span className={`stat-node-dot stat-node-dot--${st.c}`} />
        <span className="stat-node-kind mono dim2">{n.kind}</span>
      </div>
      <div className="stat-node-label">{n.label}</div>
      <div className="stat-node-sub mono dim2">{n.sub}</div>
      <svg className="stat-node-spark" width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"><polyline points={pts} fill="none" stroke={`var(--${st.c})`} strokeWidth="1.4" opacity="0.8" /></svg>
      <div className="stat-node-stats mono">
        <span>{n.lat}ms</span>
        {n.rps > 0 && <span className="dim2">{n.rps} rps</span>}
        {n.quota != null && <span className={n.quota > 0.75 ? "warn" : "dim2"}>{Math.round(n.quota * 100)}% quota</span>}
      </div>
      <div className={`stat-node-state mono kpi-tone--${st.c}`}>{st.l}</div>
    </div>
  );
}

window.SurfaceStatus = SurfaceStatus;
