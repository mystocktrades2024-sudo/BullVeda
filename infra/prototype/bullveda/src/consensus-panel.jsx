// consensus-panel.jsx — Cross-engine conviction.
// Ranks the discovery universe by HOW MANY of {6 engines + scanner} surface
// each name. Reads the same data that feeds the Best Ideas board + Scanner
// (window.resolveEngines / window.SCANNER_PICKS) so it never drifts.

const { useMemo: useMemoCns } = React;

const CNS_SHORT = {
  momentum: "MOM", "earnings-ai": "ER", ml: "ML",
  options: "OPT", insider: "INS", smc: "SMC",
};

function buildConsensus() {
  const engines = (window.resolveEngines ? window.resolveEngines() : window.TBE_ENGINES) || [];
  const scanner = window.SCANNER_PICKS || [];
  const map = {};
  const names = {};
  const add = (sym, src) => {
    (map[sym] = map[sym] || { sym, sources: [] }).sources.push(src);
  };
  engines.forEach(e => {
    (e.rows || []).forEach(([sym, v], i) =>
      add(sym, { id: e.id, short: CNS_SHORT[e.id] || e.id, label: e.title, metric: e.metric, value: v, accent: e.accent, surface: e.surface, rank: i + 1 })
    );
  });
  scanner.forEach((r, i) => {
    names[r.sym] = r.name;
    add(r.sym, { id: "scanner", short: "SCAN", label: "Scanner", metric: "score", value: String(r.score), accent: "var(--copper)", surface: "signal-scanner", rank: i + 1, v: r.v });
  });

  const order = [
    ...engines.map(e => ({ id: e.id, short: CNS_SHORT[e.id] || e.id, accent: e.accent, surface: e.surface, label: e.title })),
    { id: "scanner", short: "SCAN", accent: "var(--copper)", surface: "signal-scanner", label: "Scanner" },
  ];
  const total = order.length;
  const rows = Object.values(map)
    .map(m => ({ ...m, count: m.sources.length, name: names[m.sym] || "", avgRank: m.sources.reduce((s, x) => s + x.rank, 0) / m.sources.length }))
    .sort((a, b) => b.count - a.count || a.avgRank - b.avgRank || a.sym.localeCompare(b.sym));
  return { rows, total, order };
}

// A row of fixed-order source dots; lit when this name is in that source.
function ConsensusDots({ order, sources, onSurface, labels }) {
  const has = id => sources.find(s => s.id === id);
  return (
    <div className={`cns-dots ${labels ? "cns-dots--lg" : ""}`}>
      {order.map(o => {
        const hit = has(o.id);
        return (
          <button
            key={o.id}
            className={`cns-dot ${hit ? "is-on" : "is-off"}`}
            style={{ "--dot": o.accent }}
            title={hit ? `${o.label}: ${hit.metric} ${hit.value}` : `${o.label}: not flagged`}
            onClick={(e) => { e.stopPropagation(); onSurface && onSurface(o.surface); }}
          >
            <span className="cns-dot-mark" />
            {labels && <span className="cns-dot-lbl mono">{o.short}</span>}
          </button>
        );
      })}
    </div>
  );
}

function ConsensusPanel({ onTicker, onSurface }) {
  const { rows, total, order } = useMemoCns(() => buildConsensus(), []);
  if (!rows.length) return null;
  const max = rows[0].count;

  return (
    <div className="cns">
      {/* Legend — what each dot means; click to open that engine */}
      <div className="cns-legend">
        <span className="cns-legend-l mono dim2">ENGINES</span>
        {order.map(o => (
          <button key={o.id} className="cns-leg" style={{ "--dot": o.accent }}
            title={`Open ${o.label}`} onClick={() => onSurface && onSurface(o.surface)}>
            <span className="cns-leg-mark" />
            <span className="cns-leg-lbl mono">{o.short}</span>
          </button>
        ))}
      </div>

      {/* One flat list of every name, with its confluence indicator */}
      <div className="cns-list">
        {rows.map(r => {
          const agreeStr = r.sources
            .slice()
            .sort((a, b) => order.findIndex(o => o.id === a.id) - order.findIndex(o => o.id === b.id))
            .map(s => `${s.short} ${s.value}`).join("  ·  ");
          return (
            <div key={r.sym} className={`cns-row ${r.count === max ? "is-top" : ""}`} role="button" tabIndex={0}
              title={`agree: ${agreeStr}`}
              onClick={() => onTicker && onTicker(r.sym)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onTicker && onTicker(r.sym); } }}>
              <span className="cns-row-id">
                <span className="cns-row-sym mono"><b>{r.sym}</b></span>
                {r.name && <span className="cns-row-name mono dim2">{r.name}</span>}
              </span>
              <ConsensusDots order={order} sources={r.sources} onSurface={onSurface} labels />
              <span className={`cns-row-conv cns-row-conv--${r.count >= 5 ? "hi" : r.count >= 3 ? "mid" : "lo"}`}>
                <b>{r.count}</b><i>/{total}</i>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.ConsensusPanel = ConsensusPanel;
window.buildConsensus = buildConsensus;
