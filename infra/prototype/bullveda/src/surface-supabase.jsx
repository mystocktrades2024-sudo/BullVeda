// surface-supabase.jsx — Supabase · schema & data health.
// ER diagram (tables + FK relationships) + per-table health: rows, last sync,
// missing-data %, storage, RLS. Observability for the persistence layer.

const { useState: useSb, useMemo: useSbm } = React;

// tables: pos {col,row} on a 4-col grid · fields · fk → target table
const SB_TABLES = [
  { id: "tickers", label: "tickers", rows: 11940, size: "42 MB", sync: "2m ago", miss: 0.4, rls: true, col: 0, row: 0,
    fields: [["symbol", "text PK"], ["name", "text"], ["sector", "text"], ["exchange", "text"], ["mcap", "numeric"]] },
  { id: "prices_eod", label: "prices_eod", rows: 8420000, size: "2.1 GB", sync: "2m ago", miss: 0.1, rls: true, col: 1, row: 0,
    fields: [["id", "bigint PK"], ["symbol", "fk→tickers"], ["date", "date"], ["ohlcv", "jsonb"]], fk: "tickers" },
  { id: "quotes_rt", label: "quotes_rt", rows: 11940, size: "8 MB", sync: "6s ago", miss: 0.0, rls: true, col: 1, row: 1,
    fields: [["symbol", "fk→tickers"], ["last", "numeric"], ["bid_ask", "numeric"], ["ts", "timestamptz"]], fk: "tickers" },
  { id: "fundamentals", label: "fundamentals", rows: 8210, size: "190 MB", sync: "6h ago", miss: 2.1, rls: true, col: 1, row: 2,
    fields: [["symbol", "fk→tickers"], ["statements", "jsonb"], ["ratios", "jsonb"], ["updated", "timestamptz"]], fk: "tickers" },
  { id: "options_chains", label: "options_chains", rows: 1420000, size: "880 MB", sync: "6s ago", miss: 6.0, rls: true, col: 1, row: 3,
    fields: [["id", "bigint PK"], ["symbol", "fk→tickers"], ["strike", "numeric"], ["greeks", "jsonb"], ["iv", "numeric"]], fk: "tickers" },
  { id: "signal_ledger", label: "signal_ledger", rows: 242, size: "1.2 MB", sync: "retrying", miss: 0.0, rls: true, col: 2, row: 0, warn: true,
    fields: [["id", "uuid PK"], ["symbol", "fk→tickers"], ["source", "text"], ["dir", "text"], ["ref_price", "numeric"], ["logged_at", "timestamptz"]], fk: "tickers" },
  { id: "signal_scores", label: "signal_scores", rows: 5566, size: "3 MB", sync: "3m ago", miss: 0.0, rls: true, col: 3, row: 0,
    fields: [["signal_id", "fk→signal_ledger"], ["horizon", "text"], ["edge", "numeric"], ["raw_ret", "numeric"]], fk: "signal_ledger" },
  { id: "portfolios", label: "portfolios", rows: 318, size: "0.6 MB", sync: "live", miss: 0.0, rls: true, col: 2, row: 2,
    fields: [["id", "uuid PK"], ["user_id", "fk→users"], ["name", "text"], ["cash", "numeric"]], fk: "users" },
  { id: "holdings", label: "holdings", rows: 2840, size: "1.1 MB", sync: "live", miss: 0.3, rls: true, col: 3, row: 2,
    fields: [["id", "uuid PK"], ["portfolio_id", "fk→portfolios"], ["symbol", "fk→tickers"], ["qty", "numeric"], ["cost", "numeric"]], fk: "portfolios" },
  { id: "users", label: "users", rows: 214, size: "0.4 MB", sync: "live", miss: 0.0, rls: true, col: 2, row: 3,
    fields: [["id", "uuid PK"], ["email", "text"], ["role", "text"], ["tier", "int"], ["created", "timestamptz"]] },
];

const SB_COLS = 4, SB_CELL_W = 212, SB_GAP_X = 40, SB_ROW_H = 150, SB_GAP_Y = 22, SB_PAD = 12;
function tablePos(t) { return { x: SB_PAD + t.col * (SB_CELL_W + SB_GAP_X), y: SB_PAD + t.row * (SB_ROW_H + SB_GAP_Y) }; }

function SurfaceSupabase({ embedded }) {
  const [sel, setSel] = useSb(null);
  const [tab, setTab] = useSb("schema");
  const byId = useSbm(() => Object.fromEntries(SB_TABLES.map(t => [t.id, t])), []);

  const totalRows = SB_TABLES.reduce((a, t) => a + t.rows, 0);
  const maxRow = Math.max(...SB_TABLES.map(t => t.row));
  const svgW = SB_PAD * 2 + SB_COLS * SB_CELL_W + (SB_COLS - 1) * SB_GAP_X;
  const svgH = SB_PAD * 2 + (maxRow + 1) * SB_ROW_H + maxRow * SB_GAP_Y;
  const tableH = t => 30 + t.fields.length * 17 + 8;

  // FK connectors: from child table left-center → parent table right-center
  const edges = SB_TABLES.filter(t => t.fk).map(t => {
    const c = tablePos(t), p = tablePos(byId[t.fk]);
    const x1 = c.x, y1 = c.y + tableH(t) / 2;
    const x2 = p.x + SB_CELL_W, y2 = p.y + tableH(byId[t.fk]) / 2;
    const mx = (x1 + x2) / 2;
    return { id: t.id + "-" + t.fk, d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`, active: sel === t.id || sel === t.fk };
  });

  return (
    <div className={embedded ? "sb-srf sb-srf--embedded" : "surface wsx wsx--gn sb-srf"}>
      {!embedded && (
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SUPABASE · SCHEMA &amp; DATA HEALTH</div>
          <h1 className="wsx-title mono">Supabase</h1>
          <div className="wsx-sub mono dim2">ER diagram · {SB_TABLES.length} tables · {(totalRows / 1e6).toFixed(1)}M rows · last-sync · missing-data · storage · RLS</div>
        </div>
        <div className="wsx-hdr-r">
          <span className="sb-conn mono"><span className="sb-conn-dot" /> Postgres 15 · connected</span>
          <FreshnessPill state="live" age="6s" />
        </div>
      </div>
      )}

      <div className="sb-kpis">
        <SbKpi k="Tables" v={SB_TABLES.length} tone="cy" s="public schema" />
        <SbKpi k="Total rows" v={`${(totalRows / 1e6).toFixed(2)}M`} tone="gn" s="across all tables" />
        <SbKpi k="Storage" v="3.2 GB" tone="amb" s="of 8 GB · 78% quota" />
        <SbKpi k="RLS enabled" v={`${SB_TABLES.filter(t => t.rls).length}/${SB_TABLES.length}`} tone="gn" s="row-level security" />
        <SbKpi k="Missing data" v="1.0%" tone="amb" s="weighted avg" />
        <SbKpi k="Sync issues" v="1" tone="rd" s="signal_ledger retrying" />
      </div>

      <div className="lab-tabs sb-tabs">
        {[["schema", "ER Diagram"], ["health", "Table Health"]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
      </div>

      {tab === "schema" ? (
        <div className="lab-card">
          <div className="lab-card-h mono">ENTITY-RELATIONSHIP DIAGRAM <span className="dim2">· click a table to trace its foreign keys</span></div>
          <div className="sb-er-wrap">
            <svg className="sb-er" width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
              <defs><marker id="sb-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0 L7 4 L0 8 z" fill="var(--cy)" /></marker></defs>
              {edges.map(e => <path key={e.id} d={e.d} fill="none" stroke={e.active ? "var(--cy)" : "var(--line-2)"} strokeWidth={e.active ? 2 : 1.2} markerEnd="url(#sb-arrow)" opacity={sel && !e.active ? 0.3 : 0.85} />)}
              {SB_TABLES.map(t => {
                const p = tablePos(t), h = tableH(t), active = sel === t.id;
                return (
                  <g key={t.id} transform={`translate(${p.x},${p.y})`} className="sb-node" onClick={() => setSel(active ? null : t.id)} style={{ cursor: "pointer" }}>
                    <rect width={SB_CELL_W} height={h} rx="6" fill="var(--bg-1)" stroke={active ? "var(--cy)" : t.warn ? "var(--amb)" : "var(--line-2)"} strokeWidth={active ? 2 : 1.2} />
                    <rect width={SB_CELL_W} height="26" rx="6" fill={t.warn ? "var(--amb-bg)" : "var(--bg-3)"} />
                    <rect y="20" width={SB_CELL_W} height="6" fill={t.warn ? "var(--amb-bg)" : "var(--bg-3)"} />
                    <text x="10" y="17" fontSize="12" fontWeight="700" fill={t.warn ? "var(--amb)" : "var(--cy)"} className="mono">{t.label}</text>
                    <text x={SB_CELL_W - 10} y="17" fontSize="9" textAnchor="end" fill="var(--ink-3)" className="mono">{t.rows >= 1e6 ? (t.rows / 1e6).toFixed(1) + "M" : t.rows >= 1e3 ? (t.rows / 1e3).toFixed(1) + "k" : t.rows}</text>
                    {t.fields.map((f, i) => (
                      <g key={i} transform={`translate(0,${30 + i * 17})`}>
                        <text x="10" y="9" fontSize="9.5" fill="var(--ink-1)" className="mono">{f[0]}</text>
                        <text x={SB_CELL_W - 10} y="9" fontSize="8.5" textAnchor="end" fill={f[1].includes("fk") ? "var(--cy)" : f[1].includes("PK") ? "var(--copper)" : "var(--ink-3)"} className="mono">{f[1]}</text>
                      </g>
                    ))}
                  </g>
                );
              })}
            </svg>
          </div>
          <div className="sb-er-legend mono dim2"><span><b className="copper">PK</b> primary key</span><span><b className="cy">fk→</b> foreign key</span><span><span className="sb-leg-amb" /> sync warning</span><span>click a table to highlight relationships</span></div>
        </div>
      ) : (
        <div className="lab-card">
          <div className="lab-card-h mono">TABLE HEALTH <span className="dim2">· rows · last sync · missing data · storage</span></div>
          <table className="dtable wsx-tbl sb-tbl">
            <thead><tr><th>Table</th><th className="r">Rows</th><th className="r">Size</th><th className="r">Last sync</th><th className="r">Missing</th><th>RLS</th><th>Status</th></tr></thead>
            <tbody>{[...SB_TABLES].sort((a, b) => b.rows - a.rows).map(t => {
              const synced = !t.warn && t.sync !== "retrying";
              return (
                <tr key={t.id}>
                  <td className="mono"><b className={t.warn ? "warn" : "cy"}>{t.label}</b></td>
                  <td className="r mono tabular">{t.rows.toLocaleString()}</td>
                  <td className="r mono tabular dim2">{t.size}</td>
                  <td className={`r mono tabular ${synced ? "dim2" : "warn"}`}>{t.sync}</td>
                  <td className="r mono tabular"><span className={t.miss > 5 ? "dn" : t.miss > 1 ? "warn" : "up"}>{t.miss.toFixed(1)}%</span></td>
                  <td>{t.rls ? <span className="sb-rls on">● on</span> : <span className="sb-rls off">○ off</span>}</td>
                  <td><span className={`stat-pill stat-pill--${t.warn ? "amb" : "gn"}`}>{t.warn ? "RETRYING" : "HEALTHY"}</span></td>
                </tr>
              );
            })}</tbody>
          </table>
          <div className="lab-verdict mono dim2">⚠ <b className="warn">signal_ledger</b> writes are retrying (realtime backpressure) — 38 rows queued, draining. <b className="warn">options_chains</b> shows 6% missing (illiquid strikes with no quote). Everything else is healthy and in sync.</div>
        </div>
      )}

      <div className="pf-note mono dim2">
        Schema introspection for the <b>Supabase</b> persistence layer — tables, foreign keys, row counts, freshness, missing-data and storage. Wire to <b>pg_catalog</b> / Supabase's metadata API + your sync-job timestamps to make counts and last-sync live.
      </div>
    </div>
  );
}

function SbKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

window.SurfaceSupabase = SurfaceSupabase;
