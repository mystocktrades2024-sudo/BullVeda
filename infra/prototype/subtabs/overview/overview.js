// subtabs/overview/overview.js — engine-driven Overview (rebuilt 2026-05-13).
//
// 14 sections (verdict strip + A B C C·b C·c C·d C·e D E F G H I) ported
// from cache/overview_v2_prototype.html · qov-* CSS prefix to integrate
// with the QuantDetail/elite-detail-shell module system.
//
// Synchronous initial paint from T (the pre-loaded ticker payload),
// progressive enhancement via /api/trade_engine × 3 modes + /api/portfolio.
// All fetch failures fall back to "—" placeholders — never fabricates.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);
const _D = () => (window.DATA && typeof window.DATA === 'object') ? window.DATA
                : (window.__getData ? window.__getData() : {});

// ─── number / format helpers ─────────────────────────────────────────────
const num = (v, d = NaN) => (v == null || v === '' || isNaN(+v)) ? d : +v;
const fmtPx = v => (typeof v === 'number' && !isNaN(v)) ? '$' + v.toFixed(2) : '—';
const fmtPct = (v, d = 1) => (typeof v === 'number' && !isNaN(v))
                              ? ((v >= 0 ? '+' : '') + v.toFixed(d) + '%') : '—';
const fmtR = v => (typeof v === 'number' && !isNaN(v))
                  ? ((v >= 0 ? '+' : '') + v.toFixed(1) + 'R') : '—';
const escapeHtml = s => String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const safeStr = v => (v == null || typeof v === 'object') ? '' : String(v);

function wilsonLB(p, n) {
  if (!n || n <= 0) return 0;
  const z = 1.96;
  const z2n = z * z / n;
  const phat = p;
  return Math.max(0, (phat + z2n / 2 - z * Math.sqrt((phat * (1 - phat) + z2n / 4) / n)) / (1 + z2n));
}

const REGIME_FLOOR = {
  'risk_on_trending':  65,
  'risk_on_choppy':    72,
  'risk_off_trending': 78,
  'risk_off':          78,
  'panic':             999,
};

const MODE_MAP    = { SWING:'swing', POSITION:'position', INVESTMENT:'invest' };
const BEHAVIOR_CLS = { MAGNET:'mag', REJECTION:'rej', MIXED:'mix', STRUCTURAL:'struct' };
const SRC_COLOR = { BSL:'#F472B6', HVN:'#FCD34D', SWING:'#A78BFA', VAH:'#22D3EE',
                    AVWAP_52:'#3DDC97', AVWAP_EARN:'#3DDC97', FVG:'#F97316',
                    ROUND:'#94A3B8', FIB:'#64748B', ANALYST_PT:'#B794F4' };

// ─── module-level state for current ticker's async data ──────────────────
const STATE = { ticker:null, payloads:{}, portfolio:null, mounted:false, activeStrategy:'SWING' };

// Active-mode payload selector — mode-dependent sections read through this so
// they stay in sync with the SWING/POSITION/INVEST toggle. Falls back to any
// loaded payload (preserving the prior POSITION-first fallback order) so a
// section never goes blank when the active mode's engine call returned null.
const _activeP = () => STATE.payloads[STATE.activeStrategy]
                    || STATE.payloads.POSITION
                    || STATE.payloads.SWING
                    || STATE.payloads.INVESTMENT;

// Human label for the active strategy (used in dynamic section copy).
const _activeLabel = () => ({ SWING:'SWING', POSITION:'POSITION', INVESTMENT:'INVEST' }[STATE.activeStrategy] || 'SWING');

// ─── embedded scoped CSS (idempotent inject) ─────────────────────────────
const QOV_CSS = `
.qov-root {
  --gn:#5be57c; --gn-bg:rgba(91,229,124,0.08);
  --am:#ffb95c; --am-bg:rgba(255,185,92,0.06);
  --rd:#ff6b5b; --rd-bg:rgba(255,107,91,0.06);
  --cy:#5ec8d8; --lead:#B794F4;
  --src-bsl:#F472B6; --src-hvn:#FCD34D; --src-swing:#A78BFA;
  --src-vah:#22D3EE; --src-avwap:#3DDC97; --src-fvg:#F97316;
  --src-round:#94A3B8; --src-fib:#64748B;
  --qbg:#000; --qbg-1:#0a0d0c; --qbg-2:#0f1311; --qbg-3:#141816;
  --qline:#1d2520; --qline-2:#2a352e;
  --qink:#d8d6cc; --qink-1:#b0aea3; --qink-2:#80847a; --qink-3:#545851;
  --qmono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
  color:var(--qink-1); font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
  font-size:13px; font-variant-numeric:tabular-nums;
  background:var(--qbg); padding:6px 4px 60px;
}
.qov-root * { box-sizing:border-box; }
.qov-mono { font-family:var(--qmono); }

/* sticky verdict strip */
.qov-strip{position:sticky;top:0;z-index:50;background:var(--qbg-1);
  border:1px solid var(--qline);border-radius:4px;padding:12px 16px;margin-bottom:12px;
  display:grid;grid-template-columns:280px 1fr 280px;gap:18px;align-items:center;
  box-shadow:0 4px 20px rgba(0,0,0,.4)}
.qov-tk{font:800 26px var(--qmono);color:var(--lead);letter-spacing:.02em;line-height:1}
.qov-nm{font:500 11px sans-serif;color:var(--qink-2);margin-top:4px}
.qov-px{font:800 20px var(--qmono);color:var(--qink)}
.qov-chg{font:600 12px var(--qmono);margin-left:6px}
.qov-mid{display:flex;gap:14px;align-items:center;justify-content:center}
.qov-vd{font:800 17px var(--qmono);padding:10px 22px;border-radius:4px;letter-spacing:.08em;text-align:center}
.qov-vd.buy{background:rgba(91,229,124,.12);color:var(--gn);border:1.5px solid var(--gn)}
.qov-vd.watch{background:rgba(255,185,92,.12);color:var(--am);border:1.5px solid var(--am)}
.qov-vd.avoid{background:rgba(255,107,91,.12);color:var(--rd);border:1.5px solid var(--rd)}
.qov-conv{font:500 10.5px var(--qmono);color:var(--qink-2);margin-top:4px;letter-spacing:.10em;text-transform:uppercase}
.qov-hor{display:flex;gap:8px}
.qov-h{padding:7px 11px;border-radius:3px;background:var(--qbg-2);border:1px solid var(--qline);text-align:center;min-width:90px}
.qov-h .lbl{font:700 9px var(--qmono);color:var(--qink-3);letter-spacing:.12em}
.qov-h .val{font:800 11.5px var(--qmono);margin-top:2px}
.qov-h.gn .val{color:var(--gn)} .qov-h.am .val{color:var(--am)} .qov-h.rd .val{color:var(--rd)}
.qov-h.on{border-color:var(--lead);box-shadow:0 0 0 1px var(--lead) inset}
.qov-h.on .lbl{color:var(--lead)}
.qov-stamp{font:500 10px var(--qmono);color:var(--qink-3);text-align:right;line-height:1.6}

/* panel */
.qov-panel{background:var(--qbg-1);border:1px solid var(--qline);border-radius:5px;padding:16px 20px;margin-bottom:12px}
.qov-h2{font:700 12.5px var(--qmono);color:var(--qink);letter-spacing:.10em;text-transform:uppercase;margin-bottom:12px;display:flex;align-items:center;gap:10px}
.qov-h2 .num{color:var(--lead);font:800 13px var(--qmono);min-width:24px}
.qov-h2 .sub{font:500 11px sans-serif;color:var(--qink-3);letter-spacing:.02em;text-transform:none;margin-left:auto;flex:1}
.qov-h2 .tag{background:var(--qbg-2);color:var(--qink-2);font:700 9.5px var(--qmono);padding:3px 9px;border-radius:3px;letter-spacing:.10em}

/* banner */
.qov-banner{padding:9px 13px;border-radius:3px;font:600 11px var(--qmono);letter-spacing:.04em;margin-bottom:12px}
.qov-banner.info{background:rgba(94,161,255,.10);border-left:3px solid #5EA1FF;color:#5EA1FF}
.qov-banner.warn{background:rgba(255,185,92,.10);border-left:3px solid var(--am);color:var(--am)}

/* A · Strategy Fit cards */
.qov-fit{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.qov-fc{background:var(--qbg-2);border:1.5px solid var(--qline);border-radius:4px;padding:12px 14px;position:relative}
.qov-fc.best{border-color:var(--gn)}
.qov-fc.active{box-shadow:0 0 0 1.5px var(--lead) inset, 0 0 12px rgba(183,148,244,.18)}
.qov-fc.swing{border-left:3px solid var(--am)}
.qov-fc.position{border-left:3px solid #5EA1FF}
.qov-fc.investment{border-left:3px solid var(--lead)}
.qov-best-badge{position:absolute;top:-9px;right:14px;background:var(--qbg-1);padding:2px 8px;font:800 9.5px var(--qmono);color:var(--gn);border:1px solid var(--gn);border-radius:3px;letter-spacing:.12em}
.qov-fc-mode{font:800 10.5px var(--qmono);color:var(--qink-2);letter-spacing:.14em}
.qov-fc-hold{font:500 9.5px var(--qmono);color:var(--qink-3);margin-bottom:8px}
.qov-fc-verdict{font:800 20px var(--qmono);margin:7px 0 5px;letter-spacing:.05em}
.qov-fc-verdict.gn{color:var(--gn)} .qov-fc-verdict.am{color:var(--am)} .qov-fc-verdict.rd{color:var(--rd)}
.qov-fc-reason{font:500 11.5px sans-serif;color:var(--qink-1);line-height:1.45;margin-bottom:8px;min-height:30px}
.qov-fc-tgts{padding:7px 9px;background:var(--qbg-1);border-radius:3px;font:500 11px var(--qmono);color:var(--qink);line-height:1.55}
.qov-fc-tgts b{color:var(--qink-2);font-weight:700}

/* B · decision matrix */
.qov-dm{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.qov-dm-col{background:var(--qbg-2);border-radius:4px;padding:12px 14px;border-top:3px solid var(--qline)}
.qov-dm-col.buy{border-top-color:var(--gn)}
.qov-dm-col.watch{border-top-color:var(--am)}
.qov-dm-col.avoid{border-top-color:var(--rd)}
.qov-dm-head{font:800 10.5px var(--qmono);letter-spacing:.14em;margin-bottom:8px}
.qov-dm-head.gn{color:var(--gn)} .qov-dm-head.am{color:var(--am)} .qov-dm-head.rd{color:var(--rd)}
.qov-dm-list{list-style:none;padding:0;margin:0}
.qov-dm-list li{font:500 11.5px sans-serif;color:var(--qink-1);padding:5px 0;line-height:1.45;border-bottom:1px solid var(--qline)}
.qov-dm-list li:last-child{border-bottom:0}
.qov-dm-list li .b{font-weight:700;color:var(--qink)}
.qov-dm-falsify{margin-top:10px;padding:7px 9px;background:rgba(255,107,91,.06);border-left:2px solid var(--rd);border-radius:3px;font:500 11px sans-serif;color:var(--qink-1);line-height:1.5}

/* C · engine targets · price-line map */
.qov-map{background:var(--qbg-2);padding:16px 20px;border-radius:4px;border:1px solid var(--qline);margin-bottom:12px}
.qov-map-row{display:grid;grid-template-columns:90px 1fr 80px;gap:12px;align-items:center;padding:9px 0;border-bottom:1px solid var(--qline)}
.qov-map-row:last-child{border-bottom:0}
.qov-map-lbl{font:800 10.5px var(--qmono);letter-spacing:.14em}
.qov-map-lbl.t1{color:var(--lead)} .qov-map-lbl.t2{color:#22D3EE}
.qov-map-lbl.entry{color:var(--qink-2)} .qov-map-lbl.stop{color:var(--rd)}
.qov-map-track{height:22px;background:var(--qbg-1);border-radius:3px;position:relative;overflow:hidden}
.qov-map-fill{position:absolute;top:0;bottom:0;left:0}
.qov-map-px{font:800 13px var(--qmono);text-align:right}
.qov-map-px.t1{color:var(--lead)} .qov-map-px.t2{color:#22D3EE}
.qov-map-px.entry{color:var(--qink)} .qov-map-px.stop{color:var(--rd)}

/* C · engine targets · T1/T2 cards */
.qov-et{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.qov-et-card{background:var(--qbg-2);border:1px solid var(--qline);border-radius:4px;padding:12px 14px}
.qov-et-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.qov-et-label{font:800 11px var(--qmono);letter-spacing:.14em}
.qov-et-label.t1{color:var(--lead)} .qov-et-label.t2{color:#22D3EE}
.qov-et-price{font:800 20px var(--qmono);color:var(--qink)}
.qov-et-r{font:600 11.5px var(--qmono);color:var(--gn);margin-left:8px}
.qov-et-row{display:flex;gap:10px;align-items:center;padding:3px 0}
.qov-et-row-k{font:700 9px var(--qmono);color:var(--qink-3);letter-spacing:.12em;min-width:90px}
.qov-et-row-v{font:500 11px var(--qmono);color:var(--qink);line-height:1.4}
.qov-et-pill{display:inline-block;padding:2px 8px;border-radius:3px;font:700 9px var(--qmono);letter-spacing:.10em}
.qov-et-pill.mag{background:rgba(252,211,77,.15);color:var(--src-hvn)}
.qov-et-pill.rej{background:rgba(34,211,238,.15);color:var(--src-vah)}
.qov-et-pill.mix{background:rgba(167,139,250,.18);color:var(--src-swing)}
.qov-et-pill.struct{background:rgba(183,148,244,.18);color:var(--lead)}
.qov-et-sources{display:flex;flex-wrap:wrap;gap:5px;margin-top:3px}
.qov-et-src{font:600 9.5px var(--qmono);padding:2px 7px;border-radius:3px;background:var(--qbg-1);border:1px solid var(--qline);color:var(--qink-1)}
.qov-et-src .dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px;vertical-align:middle}

/* C·b · intrinsic value */
.qov-val{display:grid;grid-template-columns:repeat(6,1fr);gap:7px}
.qov-v{background:var(--qbg-2);border:1px solid var(--qline);border-top:2px solid var(--lead);border-radius:3px;padding:10px 12px}
.qov-v.gn{border-top-color:var(--gn)}
.qov-v.am{border-top-color:var(--am)}
.qov-v.rd{border-top-color:var(--rd)}
.qov-v-k{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em}
.qov-v-v{font:800 15px var(--qmono);margin:3px 0 2px;color:var(--qink)}
.qov-v-v.gn{color:var(--gn)} .qov-v-v.am{color:var(--am)} .qov-v-v.rd{color:var(--rd)} .qov-v-v.lead{color:var(--lead)}
.qov-v-sub{font:500 9.5px var(--qmono);color:var(--qink-3);line-height:1.4}
.qov-buffett{margin-top:12px;padding:11px 14px;background:var(--qbg-2);border-left:3px solid var(--lead);border-radius:3px}
.qov-buffett .q{font:700 10.5px var(--qmono);color:var(--lead);letter-spacing:.10em;text-transform:uppercase}
.qov-buffett .a{font:500 12px sans-serif;color:var(--qink-1);line-height:1.55;margin-top:6px}

/* C·c earnings */
.qov-er-head{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:12px}
.qov-er-cell{background:var(--qbg-2);border:1px solid var(--qline);border-radius:3px;padding:8px 10px}
.qov-er-cell .k{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em}
.qov-er-cell .v{font:800 12.5px var(--qmono);margin-top:4px;color:var(--qink)}
.qov-er-cell .v.gn{color:var(--gn)} .qov-er-cell .v.am{color:var(--am)}
.qov-er-mid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.qov-er-implied{background:var(--qbg-2);padding:13px 16px;border-radius:4px;border:1px solid var(--qline)}
.qov-er-implied .label{font:700 9.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em}
.qov-er-implied .move{font:800 26px var(--qmono);color:var(--am);margin:6px 0 2px}
.qov-er-implied .sub{font:500 10.5px var(--qmono);color:var(--qink-3)}
.qov-er-rev{background:var(--qbg-2);padding:13px 16px;border-radius:4px;border:1px solid var(--qline)}
.qov-er-rev .label{font:700 9.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em;margin-bottom:7px}
.qov-er-rev-row{display:grid;grid-template-columns:60px 1fr 30px;gap:8px;align-items:center;padding:4px 0}
.qov-er-rev-row .k{font:700 9.5px var(--qmono);color:var(--qink-3)}
.qov-er-rev-row .v{font:800 12px var(--qmono);text-align:right}
.qov-er-rev-row .v.gn{color:var(--gn)} .qov-er-rev-row .v.rd{color:var(--rd)}
.qov-er-tbl{width:100%;border-collapse:collapse}
.qov-er-tbl th{font:700 9px var(--qmono);color:var(--qink-3);letter-spacing:.12em;padding:7px 9px;text-align:left;border-bottom:1px solid var(--qline)}
.qov-er-tbl td{font:500 11px var(--qmono);padding:6px 9px;border-bottom:1px solid var(--qline);color:var(--qink-1)}
.qov-er-tbl td.gn{color:var(--gn)} .qov-er-tbl td.rd{color:var(--rd)} .qov-er-tbl td.am{color:var(--am)}

/* C·d position */
.qov-pos{display:grid;grid-template-columns:repeat(6,1fr);gap:7px}
.qov-ps{background:var(--qbg-2);border:1px solid var(--qline);border-radius:3px;padding:10px 12px;border-top:2px solid #5EA1FF}
.qov-ps.gn{border-top-color:var(--gn)} .qov-ps.rd{border-top-color:var(--rd)} .qov-ps.am{border-top-color:var(--am)}
.qov-ps-k{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em}
.qov-ps-v{font:800 15px var(--qmono);margin:3px 0 2px;color:var(--qink)}
.qov-ps-v.gn{color:var(--gn)} .qov-ps-v.rd{color:var(--rd)} .qov-ps-v.am{color:var(--am)}
.qov-ps-sub{font:500 9.5px var(--qmono);color:var(--qink-3)}
.qov-pos-tax{margin-top:11px;padding:9px 12px;background:var(--qbg-2);border-radius:3px;border:1px solid var(--qline);font:500 11px sans-serif;color:var(--qink-1);line-height:1.55}

/* C·e mtf */
.qov-mtf-tbl{width:100%;border-collapse:collapse;background:var(--qbg-2);border-radius:4px;overflow:hidden}
.qov-mtf-tbl th{font:800 9.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em;padding:10px 12px;text-align:left;background:var(--qbg-1);border-bottom:1px solid var(--qline)}
.qov-mtf-tbl td{font:500 11px var(--qmono);padding:10px 12px;border-bottom:1px solid var(--qline);color:var(--qink-1)}
.qov-mtf-tbl tr:last-child td{border-bottom:0}
.qov-mtf-cell{display:inline-flex;align-items:center;gap:6px}
.qov-mtf-cell .dot{width:7px;height:7px;border-radius:50%}
.qov-mtf-cell .dot.bull{background:var(--gn)}
.qov-mtf-cell .dot.bear{background:var(--rd)}
.qov-mtf-cell .dot.neut{background:var(--qink-3)}
.qov-mtf-tf{font:800 11.5px var(--qmono);color:var(--qink)}
.qov-mtf-sum{margin-top:11px;padding:9px 12px;background:var(--qbg-2);border-left:3px solid;border-radius:3px;font:500 11.5px sans-serif;line-height:1.5}
.qov-pill{padding:2px 7px;border-radius:3px;font:700 9.5px var(--qmono);letter-spacing:.06em}
.qov-pill.gn{background:rgba(91,229,124,.15);color:var(--gn)}
.qov-pill.rd{background:rgba(255,107,91,.15);color:var(--rd)}
.qov-pill.am{background:rgba(255,185,92,.18);color:var(--am)}

/* D · setup quality strip */
.qov-pq{display:grid;grid-template-columns:repeat(10,1fr);gap:5px}
.qov-pq-cell{background:var(--qbg-2);border:1px solid var(--qline);border-radius:3px;padding:9px 11px}
.qov-pq-k{font:700 8px var(--qmono);color:var(--qink-3);letter-spacing:.13em}
.qov-pq-v{font:800 14px var(--qmono);margin:4px 0 2px;color:var(--qink)}
.qov-pq-v.gn{color:var(--gn)} .qov-pq-v.am{color:var(--am)} .qov-pq-v.rd{color:var(--rd)} .qov-pq-v.lead{color:var(--lead)}
.qov-pq-sub{font:500 9px var(--qmono);color:var(--qink-3);line-height:1.3}

/* E · risk profile */
.qov-rp{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.qov-rp-cell{background:var(--qbg-2);border:1px solid var(--qline);border-radius:4px;padding:11px 13px;border-top:2px solid var(--rd)}
.qov-rp-cell.gn{border-top-color:var(--gn)} .qov-rp-cell.am{border-top-color:var(--am)}
.qov-rp-k{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.12em}
.qov-rp-v{font:800 16px var(--qmono);margin:4px 0}
.qov-rp-v.gn{color:var(--gn)} .qov-rp-v.am{color:var(--am)} .qov-rp-v.rd{color:var(--rd)}
.qov-rp-sub{font:500 9.5px var(--qmono);color:var(--qink-3)}

/* F · news pulse */
.qov-ns{display:grid;grid-template-columns:260px 1fr;gap:10px}
.qov-ns-gauge{background:var(--qbg-2);padding:13px 16px;border-radius:4px;text-align:center;border:1px solid var(--qline)}
.qov-ns-gauge-v{font:800 30px var(--qmono);margin:10px 0 4px}
.qov-ns-gauge-v.gn{color:var(--gn)} .qov-ns-gauge-v.rd{color:var(--rd)} .qov-ns-gauge-v.am{color:var(--am)}
.qov-ns-gauge-sub{font:500 10.5px var(--qmono);color:var(--qink-3)}
.qov-ns-feed{background:var(--qbg-2);padding:6px 0;border-radius:4px;border:1px solid var(--qline);max-height:200px;overflow-y:auto}
.qov-news-row{display:grid;grid-template-columns:54px 70px 1fr 70px;gap:8px;align-items:center;padding:7px 12px;border-bottom:1px solid var(--qline);font:500 11.5px sans-serif;color:var(--qink-1)}
.qov-news-row:last-child{border-bottom:0}
.qov-news-day{font:600 10px var(--qmono);color:var(--qink-3)}
.qov-news-src{font:700 9.5px var(--qmono);color:var(--qink-2);letter-spacing:.08em;text-transform:uppercase}
.qov-news-body{color:var(--qink);line-height:1.4}
.qov-news-sent{text-align:right}

/* G · forward outcomes */
.qov-fo{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.qov-fo-bar-row{display:grid;grid-template-columns:90px 1fr 50px;gap:10px;align-items:center;padding:7px 0}
.qov-fo-bar-k{font:700 10px var(--qmono);color:var(--qink-3);letter-spacing:.10em}
.qov-fo-bar-track{height:13px;background:var(--qbg-2);border-radius:2px;overflow:hidden}
.qov-fo-bar-fill{height:100%}
.qov-fo-bar-v{font:800 11.5px var(--qmono);text-align:right}
.qov-fo-grid{background:var(--qbg-2);padding:13px;border-radius:4px;border:1px solid var(--qline)}
.qov-fo-grid > div{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.qov-fo-cell .k{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.12em}
.qov-fo-cell .v{font:800 13px var(--qmono);margin-top:4px;color:var(--qink)}

/* H · pre-flight */
.qov-pf{display:grid;grid-template-columns:repeat(5,1fr);gap:7px}
.qov-pf-cell{background:var(--qbg-2);border:1px solid var(--qline);border-radius:3px;padding:8px 11px;display:flex;gap:7px;align-items:center}
.qov-pf-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.qov-pf-dot.pass{background:var(--gn)}
.qov-pf-dot.fail{background:var(--rd)}
.qov-pf-dot.warn{background:var(--am)}
.qov-pf-k{font:600 10.5px var(--qmono);color:var(--qink);line-height:1.3}

/* I · action triggers */
.qov-trig{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.qov-trig-card{background:var(--qbg-2);border:1px solid var(--qline);border-top:3px solid var(--qline);border-radius:4px;padding:12px 14px}
.qov-trig-card.swing{border-top-color:var(--am)}
.qov-trig-card.position{border-top-color:#5EA1FF}
.qov-trig-card.investment{border-top-color:var(--lead)}
.qov-trig-card.active{box-shadow:0 0 0 1.5px var(--lead) inset, 0 0 12px rgba(183,148,244,.18)}
.qov-trig-mode{font:800 10.5px var(--qmono);letter-spacing:.14em;margin-bottom:8px}
.qov-trig-mode.am{color:var(--am)} .qov-trig-mode.blue{color:#5EA1FF} .qov-trig-mode.lead{color:var(--lead)}
.qov-trig-rule{padding:8px 0;border-bottom:1px dashed var(--qline)}
.qov-trig-rule:last-child{border-bottom:0}
.qov-trig-rule .label{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.13em;margin-bottom:4px}
.qov-trig-rule .ruleBody{font:500 11px var(--qmono);color:var(--qink);line-height:1.55}
.qov-trig-rule .ruleBody .when{color:var(--qink-1)}
.qov-trig-rule .ruleBody .then{color:var(--lead);font-weight:700}
.qov-trig-rule .ruleBody .and{color:var(--qink-3)}
.qov-trig-rule .ruleBody .neg{color:var(--rd);font-weight:700}

/* Strategy switcher */
.qov-strat-bar{display:flex;gap:8px;align-items:center;margin-bottom:10px;padding:10px 14px;background:var(--qbg-1);border:1px solid var(--qline);border-radius:4px}
.qov-strat-lbl{font:700 9.5px var(--qmono);color:var(--qink-3);letter-spacing:.14em}
.qov-strat-btn{background:transparent;border:1px solid var(--qline);color:var(--qink-3);font:700 10.5px var(--qmono);padding:7px 14px;border-radius:3px;cursor:pointer;letter-spacing:.08em;transition:all .15s}
.qov-strat-btn.on{background:var(--qbg-2);border-color:var(--lead);color:var(--lead)}
.qov-strat-btn:hover{border-color:var(--qink-2);color:var(--qink)}
.qov-strat-meta{font:500 10px var(--qmono);color:var(--qink-3);margin-left:auto}

/* Cross-lens votes */
.qov-xlens{background:var(--qbg-1);border:1px solid var(--qline);border-radius:4px;padding:10px 16px;margin-bottom:10px}
.qov-xlens-votes{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.qov-xlens-vote{display:flex;align-items:center;gap:5px}
.qov-xlens-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.qov-xlens-dot.gn{background:var(--gn)}
.qov-xlens-dot.am{background:var(--am)}
.qov-xlens-dot.rd{background:var(--rd)}
.qov-xlens-nm{font:700 9px var(--qmono);color:var(--qink-2);letter-spacing:.10em}
.qov-xlens-lb{font:700 10px var(--qmono);color:var(--qink);margin-left:3px}
.qov-xlens-conflict{font:500 11px sans-serif;color:var(--am);border-left:2px solid var(--am);padding-left:8px;line-height:1.5;margin-top:4px}

/* Exec brief */
.qov-exec{background:var(--qbg-2);border:1px solid var(--lead);border-radius:5px;padding:16px 20px;margin-bottom:10px}
.qov-exec-hdr{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.qov-exec-badge{background:var(--lead);color:var(--qbg);font:800 11px var(--qmono);padding:3px 10px;border-radius:3px;letter-spacing:.10em}
.qov-exec-title{font:800 12px var(--qmono);color:var(--qink);letter-spacing:.08em}
.qov-exec-sub{font:500 10px sans-serif;color:var(--qink-3);margin-left:auto}
.qov-exec-body{display:grid;grid-template-columns:180px 1fr 120px;gap:16px;align-items:start;margin-bottom:12px}
.qov-exec-vbox{text-align:center;padding:12px;background:var(--qbg-1);border-radius:4px}
.qov-exec-v{font:800 18px var(--qmono);letter-spacing:.05em}
.qov-exec-v.gn{color:var(--gn)} .qov-exec-v.am{color:var(--am)} .qov-exec-v.rd{color:var(--rd)}
.qov-exec-stars{font:500 11px var(--qmono);color:var(--am);margin-top:4px}
.qov-exec-thesis{font:500 12.5px sans-serif;color:var(--qink-1);line-height:1.6}
.qov-exec-dq{text-align:center}
.qov-exec-dq .k{font:700 8px var(--qmono);color:var(--qink-3);letter-spacing:.12em}
.qov-exec-dq .v{font:800 14px var(--qmono);color:var(--gn);margin-top:2px}
.qov-exec-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px}
.qov-exec-kpi{background:var(--qbg-1);border:1px solid var(--qline);border-radius:3px;padding:8px 10px;text-align:center}
.qov-exec-kpi .k{font:700 8.5px var(--qmono);color:var(--qink-3);letter-spacing:.12em}
.qov-exec-kpi .v{font:800 13px var(--qmono);margin:3px 0 2px}
.qov-exec-kpi .v.gn{color:var(--gn)} .qov-exec-kpi .v.am{color:var(--am)} .qov-exec-kpi .v.rd{color:var(--rd)}
.qov-exec-kpi .s{font:500 9px var(--qmono);color:var(--qink-3);line-height:1.3}
.qov-exec-row{display:flex;gap:12px;align-items:baseline;padding:5px 0;border-bottom:1px solid var(--qline)}
.qov-exec-row:last-child{border-bottom:0}
.qov-exec-row-k{font:700 9px var(--qmono);color:var(--qink-3);letter-spacing:.12em;min-width:90px}
.qov-exec-row-v{font:500 11.5px sans-serif;color:var(--qink-1);line-height:1.4;flex:1}
.qov-exec-call{margin-top:12px;padding:10px 14px;background:var(--qbg-1);border-left:3px solid var(--lead);border-radius:3px}
.qov-exec-call-v{font:800 11px var(--qmono);color:var(--lead);letter-spacing:.10em}
.qov-exec-call-r{font:500 12px sans-serif;color:var(--qink-1);margin-top:4px;line-height:1.5}
.qov-exec-call-t{font:600 10.5px var(--qmono);color:var(--am);margin-top:4px}

/* Divider */
.qov-divider{font:600 9px var(--qmono);color:var(--qink-3);letter-spacing:.08em;text-align:center;margin:14px 0}

/* Detail controls */
.qov-detail-ctrls{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.qov-detail-ctrls button{background:var(--qbg-1);border:1px solid var(--qline);color:var(--qink-2);font:700 10px var(--qmono);padding:5px 12px;border-radius:3px;cursor:pointer;letter-spacing:.06em}
.qov-detail-ctrls button:hover{border-color:var(--qink-2);color:var(--qink)}
.qov-open-count{font:500 10px var(--qmono);color:var(--qink-3);margin-left:auto}

/* Collapsible panels */
.qov-collapsible .qov-panel-head{cursor:pointer;display:flex;align-items:center;gap:8px;user-select:none}
.qov-collapsible .qov-chev{font:700 10px var(--qmono);color:var(--qink-3);transition:transform .15s;min-width:12px}
.qov-collapsible.open .qov-chev{transform:rotate(90deg)}
.qov-collapsible .qov-panel-body{display:none;margin-top:12px}
.qov-collapsible.open .qov-panel-body{display:block}

/* Sparkline */
svg.qov-spark polyline{fill:none;stroke-width:1.5}
svg.qov-spark polyline.gn{stroke:var(--gn)}
svg.qov-spark polyline.am{stroke:var(--am)}
svg.qov-spark polyline.rd{stroke:var(--rd)}
`;

function _ensureStyle() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('qov-style')) return;
  const s = document.createElement('style');
  s.id = 'qov-style';
  s.textContent = QOV_CSS;
  document.head.appendChild(s);
}

// ─── fetchers ───────────────────────────────────────────────────────────
async function loadEngine(t, modeUi) {
  const mode = MODE_MAP[modeUi] || 'swing';
  try {
    const r = await fetch(`/api/trade_engine?t=${encodeURIComponent(t)}&mode=${mode}`,
                          { credentials: 'same-origin' });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
}
async function loadPortfolio(t) {
  try {
    const r = await fetch(`/api/portfolio`, { credentials: 'same-origin' });
    if (!r.ok) return null;
    const pf = await r.json();
    const positions = pf.positions || pf.open || [];
    return positions.find(p => (p.ticker || '').toUpperCase() === t.toUpperCase()) || null;
  } catch (e) { return null; }
}

// ─── shell HTML (built once, then sections fill in) ─────────────────────
function _shellHTML() {
  return `<div class="qov-root" id="qovRoot">
  <!-- Strategy switcher -->
  <div class="qov-strat-bar">
    <span class="qov-strat-lbl">STRATEGY ·</span>
    <button class="qov-strat-btn on" id="qovBtnSwing" onclick="window.__qovSetStrat('SWING')">⚡ SWING <span style="color:var(--qink-3);font-weight:500">2–10d</span></button>
    <button class="qov-strat-btn" id="qovBtnPosition" onclick="window.__qovSetStrat('POSITION')">📈 POSITION <span style="color:var(--qink-3);font-weight:500">2wk–6mo</span></button>
    <button class="qov-strat-btn" id="qovBtnInvestment" onclick="window.__qovSetStrat('INVESTMENT')">🏛 INVEST <span style="color:var(--qink-3);font-weight:500">1–5yr</span></button>
    <span id="qovStratMeta" class="qov-strat-meta"></span>
  </div>

  <!-- Banner (loading state) -->
  <div class="qov-banner info" id="qovBanner">Loading engine data…</div>

  <!-- Cross-lens votes -->
  <div class="qov-xlens" id="qovXlens"></div>

  <!-- Exec brief -->
  <div class="qov-exec" id="qovExec"></div>

  <!-- Divider -->
  <div class="qov-divider">━━━━━━━━━ DETAILED EVIDENCE BELOW · click section headers to drill ━━━━━━━━━</div>

  <!-- Detail controls -->
  <div class="qov-detail-ctrls">
    <button onclick="window.__qovExpandAll()">▼ Expand all</button>
    <button onclick="window.__qovCollapseAll()">▸ Collapse all</button>
    <span class="qov-open-count" id="qovOpenCount">0 of 0 open</span>
  </div>

  <!-- Section A: Strategy Fit -->
  <div class="qov-panel qov-collapsible open" id="qovPanelA">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelA')">
      <span class="qov-chev">▸</span><span class="num">A</span>Strategy Fit · Engine Targets per Lens
      <span class="sub">— structural T1/T2 + verdict from /api/trade_engine × 3 modes</span>
      <span class="tag">STRUCTURAL ENGINE</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-fit" id="qovFitGrid"></div>
      <div id="qovSysRec" style="margin-top:10px;padding:9px 12px;background:var(--qbg-2);border-radius:3px;font:500 11.5px sans-serif;color:var(--qink-1);line-height:1.5"></div>
    </div>
  </div>

  <!-- Section B: Decision Matrix -->
  <div class="qov-panel qov-collapsible" id="qovPanelB">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelB')">
      <span class="qov-chev">▸</span><span class="num">B</span>Decision Matrix · Why Buy / Wait / Avoid
      <span class="sub">— 3-column adversarial analysis · WHY BUY · WHY WAIT · WHY AVOID</span>
      <span class="tag">ADVERSARIAL</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-dm" id="qovDMGrid"></div>
    </div>
  </div>

  <!-- Section C: Engine Targets -->
  <div class="qov-panel qov-collapsible" id="qovPanelC">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelC')">
      <span class="qov-chev">▸</span><span class="num">C</span>Engine Targets · Price Map + Confluence
      <span class="sub">— structural T1/T2 · behavior · source breakdown</span>
      <span class="tag">TARGET ENGINE</span>
    </div>
    <div class="qov-panel-body">
      <div id="qovTargetMap" style="margin-bottom:12px"></div>
      <div class="qov-et" id="qovEtGrid"></div>
    </div>
  </div>

  <!-- Section C·b: Intrinsic Value -->
  <div class="qov-panel qov-collapsible" id="qovPanelCb">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelCb')">
      <span class="qov-chev">▸</span><span class="num">C·b</span>Intrinsic Value · Graham–Buffett Lens
      <span class="sub">— margin of safety · owner earnings · moat · 10-year test</span>
      <span class="tag">VALUE</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-val" id="qovValGrid"></div>
      <div id="qovBuffett" class="qov-buffett" style="margin-top:12px"></div>
    </div>
  </div>

  <!-- Section C·c: Earnings -->
  <div class="qov-panel qov-collapsible" id="qovPanelCc">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelCc')">
      <span class="qov-chev">▸</span><span class="num">C·c</span>Earnings · PEAD Window + Beat History
      <span class="sub">— days to ER · implied move · beat rate · revision trend</span>
      <span class="tag">CATALYST</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-er-head" id="qovErHead"></div>
      <div class="qov-er-mid" id="qovErMid"></div>
      <table class="qov-er-tbl"><thead><tr><th>QUARTER</th><th>EPS ACT / EST</th><th>SURPRISE</th><th>REV ACT / EST</th><th>GAP %</th><th>+5d DRIFT</th><th>NOTE</th></tr></thead><tbody id="qovErTbody"></tbody></table>
      <div class="qov-banner info" id="qovErStatsBanner" style="margin:11px 0 0">—</div>
    </div>
  </div>

  <!-- Section C·d: My Position -->
  <div class="qov-panel qov-collapsible" id="qovPanelCd">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelCd')">
      <span class="qov-chev">▸</span><span class="num">C·d</span>My Position · Live P&amp;L
      <span class="sub">— current holding · unrealized P&amp;L · stop distance · add zone</span>
      <span class="tag">PORTFOLIO</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-pos" id="qovPosGrid"></div>
      <div id="qovPosTax" class="qov-pos-tax" style="margin-top:10px"></div>
    </div>
  </div>

  <!-- Section C·e: MTF -->
  <div class="qov-panel qov-collapsible" id="qovPanelCe">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelCe')">
      <span class="qov-chev">▸</span><span class="num">C·e</span>Multi-Timeframe · Trend Alignment
      <span class="sub">— Monthly / Weekly / Daily / 4H · bias + momentum</span>
      <span class="tag">TECHNICALS</span>
    </div>
    <div class="qov-panel-body">
      <table class="qov-mtf-tbl"><thead><tr><th>TIMEFRAME</th><th>TREND</th><th>MOMENTUM</th><th>VOLUME / RVOL</th><th>BIAS</th></tr></thead><tbody id="qovMtfBody"></tbody></table>
      <div class="qov-mtf-sum" id="qovMtfSummary">—</div>
    </div>
  </div>

  <!-- Section D: Setup Strip -->
  <div class="qov-panel qov-collapsible" id="qovPanelD">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelD')">
      <span class="qov-chev">▸</span><span class="num">D</span>Setup Quality Strip · 10 Signal Cells
      <span class="sub">— entry quality · RVOL · momentum · pattern · S/R alignment</span>
      <span class="tag">SETUP</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-pq" id="qovPqGrid"></div>
    </div>
  </div>

  <!-- Section E: Risk Profile -->
  <div class="qov-panel qov-collapsible" id="qovPanelE">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelE')">
      <span class="qov-chev">▸</span><span class="num">E</span>Risk Profile · Kelly · Position Sizing
      <span class="sub">— max loss · stop distance · ATR · Kelly fraction · regime haircut</span>
      <span class="tag">RISK</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-rp" id="qovRpGrid"></div>
    </div>
  </div>

  <!-- Section F: News Pulse -->
  <div class="qov-panel qov-collapsible" id="qovPanelF">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelF')">
      <span class="qov-chev">▸</span><span class="num">F</span>News Pulse · Sentiment Signal
      <span class="sub">— headline sentiment · source quality · insider cross-check</span>
      <span class="tag">SENTIMENT</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-ns" id="qovNsGrid"></div>
    </div>
  </div>

  <!-- Section G: Forward Outcomes -->
  <div class="qov-panel qov-collapsible" id="qovPanelG">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelG')">
      <span class="qov-chev">▸</span><span class="num">G</span>Forward Outcomes · Scenario Matrix
      <span class="sub">— bull / base / bear · P(reach) · regime-conditional distribution</span>
      <span class="tag">SCENARIOS</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-fo" id="qovFoGrid"></div>
    </div>
  </div>

  <!-- Section H: Pre-Flight Checklist -->
  <div class="qov-panel qov-collapsible" id="qovPanelH">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelH')">
      <span class="qov-chev">▸</span><span class="num">H</span>Pre-Flight Checklist · Entry Gates
      <span class="sub">— 10 entry gates · PASS / FAIL / N/A · regime + liquidity + RR</span>
      <span class="tag">GATES</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-pf" id="qovPfGrid"></div>
      <div class="qov-banner info" id="qovPfBanner" style="margin:11px 0 0">—</div>
    </div>
  </div>

  <!-- Section I: Action Triggers -->
  <div class="qov-panel qov-collapsible" id="qovPanelI">
    <div class="qov-panel-head qov-h2" onclick="window.__qovToggle('qovPanelI')">
      <span class="qov-chev">▸</span><span class="num">I</span>Action Triggers · Conditional Rules Per Lens
      <span class="sub">— specific IF/THEN rules · mechanical execution</span>
      <span class="tag">RULES ENGINE</span>
    </div>
    <div class="qov-panel-body">
      <div class="qov-trig" id="qovTrigGrid"></div>
    </div>
  </div>
</div>`;
}

// ─── helpers ────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const setHTML = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };
const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };

function _deriveVerdict(p) {
  if (!p || p.decision === 'reject') return { label:'NO TRADE', cls:'rd' };
  if (p.invest_stub) return { label:'INTERIM · PT', cls:'am' };
  if (p.is_etf) return { label:'ETF · WIDE', cls:'am' };
  const w = p.warnings || [];
  const t1c = p.t1?.confluence || 0;
  const t1r = p.t1?.r_multiple || 0;
  const p1 = p.t1?.p_reach || 0;
  if (w.some(x => /choch/i.test(x))) return { label:'TIGHTEN STOP', cls:'am' };
  if (t1c >= 5 && p1 >= 0.45 && t1r >= 2.5) return { label:'BUY · ENTER', cls:'gn' };
  if (t1c >= 4 && p1 >= 0.30 && t1r >= 2.0)  return { label:'HOLD · ADD DIP', cls:'gn' };
  if (t1c < 3 || t1r < 1.5) return { label:'WEAK · SKIP', cls:'rd' };
  if (p1 < 0.20) return { label:'LOW P(reach)', cls:'rd' };
  return { label:'REVIEW', cls:'am' };
}

// ─── sparkline helper ───────────────────────────────────────────────────
function _sparkSvg(arr, cls) {
  if (!arr || arr.length < 2) return '';
  const W = 60, H = 16, pad = 1;
  const mn = Math.min(...arr), mx = Math.max(...arr);
  const rng = (mx - mn) || 1;
  const pts = arr.map((v, i) => {
    const x = (pad + (i / (arr.length - 1)) * (W - 2 * pad)).toFixed(1);
    const y = (pad + (1 - (v - mn) / rng) * (H - 2 * pad)).toFixed(1);
    return x + ',' + y;
  }).join(' ');
  return `<svg class="qov-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><polyline class="${cls}" points="${pts}"/></svg>`;
}

// ─── exec brief derivation ───────────────────────────────────────────────
function _computeExecBrief(strategy) {
  const T = _T() || {};
  const { payloads, portfolio } = STATE;
  const sw = payloads.SWING, ps = payloads.POSITION, iv = payloads.INVESTMENT;
  const score = num(T.score, 0);
  const rr = num(T.rr, 0);
  // SSOT (2026-06-09): canonical verdict→class map + per-mode canonical lookup.
  // Never re-derive a verdict from score in JS — bind the engine's verdict
  // (server `stage` / `decisions_by_mode`). Re-deriving reintroduced the AVT-case
  // drift: scanner bound stage=BUY/67 while this brief recomputed WATCH (67<75).
  const _ovVCls = v => ({ BUY:'gn', WATCH:'am', WAIT:'am', AVOID:'rd', SHORT:'rd', SELL:'rd' }[String(v||'').toUpperCase()] || 'am');
  const _dbm = m => (T.decisionsByMode && (T.decisionsByMode[m] || T.decisionsByMode[m.toUpperCase()])) || null;

  if (strategy === 'SWING') {
    const p = sw;
    const p1 = p?.t1?.p_reach ?? 0;
    // Canonical swing verdict = decision_engine `stage` (compute_final_verdict),
    // matching what the scanner binds. Prefer stage over decisions_by_mode.swing:
    // the two engines can disagree (catalyst-sleeve relaxes EXTENDED entries), and
    // per the funnel/distribution rule stage is authoritative. The structural
    // engine's "wait" is surfaced as a caveat below, not as a competing verdict.
    const verdict = String(T.verdict || T.stage || 'WATCH').toUpperCase();
    const vCls = _ovVCls(verdict);

    const thesisParts = [];
    const _swDbm = _dbm('swing');
    if (_swDbm && String(_swDbm.verdict || '').toUpperCase() !== verdict && _swDbm.reason) {
      thesisParts.push('⚠ Structural: ' + _swDbm.reason);
    } else if ((T.entry_quality === 'EXTENDED' || T.entry_quality === 'MISSED')) {
      thesisParts.push(`⚠ Entry ${T.entry_quality} — verdict held by catalyst-sleeve relaxation; size with care`);
    }
    if (T.above_50ema) thesisParts.push('Price is above EMA-50 (short-term trend bullish)');
    else thesisParts.push('Price is below EMA-50 (trend headwind)');
    if (T.macd_bullish) thesisParts.push('MACD is bullish');
    if (T.squeeze_on) thesisParts.push('Bollinger-squeeze ON — directional expansion imminent');
    if ((T.rvol ?? 0) >= 1.5) thesisParts.push(`RVOL ${T.rvol?.toFixed(2)} — elevated volume confirms interest`);
    if (p?.t1?.price) thesisParts.push(`Engine T1 at ${fmtPx(p.t1.price)} (P(reach) ${p1 >= 0 ? Math.round(p1*100)+'%' : '—'})`);

    const gatesPass = [
      score >= 70,
      T.above_50ema,
      rr >= 3,
      (T.earn_days == null || T.earn_days > 7),
      T.regime && !/panic|risk_off/i.test(T.regime),
      T.entry_quality && /FRESH|PULLBACK|VALID/.test(T.entry_quality),
      (p?.t1?.confluence ?? 0) >= 3,
      (p?.t1?.p_reach ?? 0) >= 0.25,
    ].filter(Boolean).length;

    const kpis = [
      { k:'SCORE', v: score + '/100', vc: score >= 75 ? 'gn' : score >= 55 ? 'am' : 'rd', s: score >= 75 ? 'strong' : 'moderate' },
      { k:'CONVICTION', v: safeStr(T.conviction_tier || '—'), vc: 'am', s: '' },
      { k:'R:R', v: rr ? rr.toFixed(1) + ':1' : '—', vc: rr >= 3 ? 'gn' : rr >= 2 ? 'am' : 'rd', s: rr >= 3 ? '≥ 3 · full size' : rr >= 2 ? '2-3 · reduce' : 'below floor' },
      { k:'REGIME', v: safeStr(T.regime || '—').replace('_',' '), vc: /trending/.test(T.regime||'') ? 'gn' : /panic/.test(T.regime||'') ? 'rd' : 'am', s: '' },
      { k:'GATES', v: gatesPass + '/8', vc: gatesPass >= 6 ? 'gn' : gatesPass >= 4 ? 'am' : 'rd', s: gatesPass >= 6 ? 'go' : gatesPass >= 4 ? 'review' : 'fail' },
    ];

    const entryLo = T.entry_lo ?? p?.t1?.price;
    const entryHi = T.entry_hi;
    const triggerStr = entryLo
      ? `Price in ${fmtPx(entryLo)}${entryHi ? '–'+fmtPx(entryHi) : ''} with RVOL > 1.2`
      : 'Entry zone pending engine data';
    const invalidate = `Daily close < ${fmtPx(T.stop ?? p?.stop?.price)} (CHoCH)`;
    const sizeStr = T.alloc_pct ? T.alloc_pct + '% NAV' : (portfolio ? 'already held' : 'pending gates');

    const convTier = safeStr(T.conviction_tier || '');
    const stars = convTier.includes('T1') ? '★★★★★' : convTier.includes('T2') ? '★★★☆☆' : convTier.includes('T3') ? '★★☆☆☆' : '★☆☆☆☆';

    const callV = verdict + ' · ' + (convTier || 'REVIEW');
    const callR = thesisParts.slice(0, 2).join('. ') + '.';
    const callT = `Hold 2–10 days · exit at T1 ${fmtPx(p?.t1?.price)} or stop ${fmtPx(T.stop ?? p?.stop?.price)}`;

    return {
      title: `EXECUTIVE BRIEF · OVERVIEW · SYNTHESIS @ SWING · 2–10d`,
      verdict, vCls, stars,
      thesis: thesisParts.slice(0, 3).join('. ') + '.',
      kpis,
      trigger: triggerStr,
      alignment: `Score ${score} · Regime ${safeStr(T.regime || '—')} · EMA stack ${T.above_50ema ? 'OK' : 'broken'}`,
      invalidate,
      size: sizeStr,
      callV, callR, callT,
    };
  }

  if (strategy === 'POSITION') {
    const p = ps;
    const conf = p?.t1?.confluence ?? 0;
    const p1 = p?.t1?.p_reach ?? 0;
    // Canonical POSITION verdict from decisions_by_mode.position (medium_term engine).
    // Fall back to the confluence heuristic only when the engine verdict is absent.
    const _posDbm = _dbm('position');
    const verdict = _posDbm && _posDbm.verdict
      ? String(_posDbm.verdict).toUpperCase()
      : (conf >= 4 && p1 >= 0.3 ? 'BUY' : 'WATCH');
    const vCls = _ovVCls(verdict);

    const earnDays = T.earn_days;
    const esp = T.zacks_earnings_esp;
    const thesisParts = [];
    if (earnDays != null) thesisParts.push(`Earnings in ${earnDays}d — PEAD setup window`);
    if (esp != null && esp > 0) thesisParts.push(`Zacks ESP +${esp.toFixed(2)}% — analyst beat bias`);
    if ((T.analyst_upside ?? 0) > 0.05) thesisParts.push(`Analyst upside ${(T.analyst_upside*100).toFixed(0)}% to PT ${fmtPx(T.analyst_target)}`);
    if (thesisParts.length === 0) thesisParts.push('Multi-week structural setup based on engine targets and fundamentals');

    const rrPos = p?.t1?.r_multiple ?? rr;
    const kpis = [
      { k:'SCORE', v: score + '/100', vc: score >= 75 ? 'gn' : score >= 55 ? 'am' : 'rd', s: '' },
      { k:'CATALYST', v: earnDays != null ? earnDays + 'd' : '—', vc: earnDays != null && earnDays <= 14 ? 'am' : 'rd', s: earnDays != null ? 'to earnings' : 'no schedule' },
      { k:'ESP', v: esp != null ? (esp > 0 ? '+' : '') + esp.toFixed(2) + '%' : '—', vc: esp > 0 ? 'gn' : esp < 0 ? 'rd' : 'am', s: esp > 0 ? 'beat bias' : '—' },
      { k:'R:R', v: rrPos ? rrPos.toFixed(1) + ':1' : '—', vc: rrPos >= 3 ? 'gn' : rrPos >= 2 ? 'am' : 'rd', s: '' },
      { k:'CONFLUENCE', v: conf.toFixed(1), vc: conf >= 5 ? 'gn' : conf >= 3 ? 'am' : 'rd', s: conf + ' sources' },
    ];

    const stopP = p?.stop?.price ?? T.stop;
    const regimeHaircut = /choppy/i.test(T.regime||'') ? '70% max' : /risk_off/i.test(T.regime||'') ? '35% max' : 'full size';
    const callV = verdict + ' · POSITION';
    const callR = thesisParts.slice(0, 2).join('. ') + '.';
    const callT = `Hold 2wk–6mo · T1 at ${fmtPx(p?.t1?.price)} · stop ${fmtPx(stopP)}`;
    const stars = conf >= 5 ? '★★★★★' : conf >= 4 ? '★★★☆☆' : '★★☆☆☆';

    return {
      title: 'EXECUTIVE BRIEF · OVERVIEW · SYNTHESIS @ POSITION · 2wk–6mo',
      verdict, vCls, stars,
      thesis: thesisParts.slice(0, 3).join('. ') + '.',
      kpis,
      trigger: earnDays != null ? `ER−7d conditional entry at ${fmtPx(T.entry_lo ?? p?.t1?.price)}` : `Structural entry ${fmtPx(T.entry_lo ?? p?.t1?.price)}`,
      alignment: `Conf ${conf.toFixed(1)} · P(reach) ${Math.round(p1*100)}% · Regime ${regimeHaircut}`,
      invalidate: `Stop ${fmtPx(stopP)} OR analyst revision turns negative`,
      size: `${regimeHaircut} · half-Kelly`,
      callV, callR, callT,
    };
  }

  // INVESTMENT
  {
    const p = iv;
    const upside = T.analyst_upside ?? 0;
    // Canonical INVEST verdict from decisions_by_mode.invest (long_term gate engine).
    // Fall back to the analyst-upside heuristic only when the engine verdict is absent.
    const _ivDbm = _dbm('invest') || _dbm('investment');
    const verdict = _ivDbm && _ivDbm.verdict
      ? String(_ivDbm.verdict).toUpperCase()
      : (upside >= 0.15 ? 'BUY' : upside >= 0.05 ? 'WATCH' : 'AVOID');
    const vCls = _ovVCls(verdict);

    const fundScore = num(T.fund_score, 0);
    const thesisParts = [];
    if (upside >= 0.10) thesisParts.push(`Analyst consensus PT ${fmtPx(T.analyst_target)} — ${(upside*100).toFixed(0)}% upside`);
    if (fundScore >= 60) thesisParts.push(`Quality score ${fundScore}/100 — solid fundamentals`);
    thesisParts.push(`Long-term hold in sector ${escapeHtml(T.sector || '—')}`);

    const tenYrPasses = [
      fundScore >= 60,
      upside >= 0.10,
      (T.analyst_target ?? 0) > 0,
      safeStr(T.sector || '').length > 0,
    ].filter(Boolean).length;

    const mosPct = T.analyst_target && T.price
      ? ((T.analyst_target - T.price) / T.analyst_target * 100).toFixed(0) + '%'
      : '—';

    const kpis = [
      { k:'10Y TEST', v: tenYrPasses + '/4', vc: tenYrPasses >= 3 ? 'gn' : tenYrPasses >= 2 ? 'am' : 'rd', s: 'passes' },
      { k:'MoS', v: mosPct, vc: upside >= 0.15 ? 'gn' : upside >= 0.05 ? 'am' : 'rd', s: 'margin of safety' },
      { k:'SCORE', v: score + '/100', vc: score >= 75 ? 'gn' : score >= 55 ? 'am' : 'rd', s: '' },
      { k:'ANALYST PT', v: fmtPx(T.analyst_target), vc: upside >= 0.10 ? 'gn' : 'am', s: fmtPct((upside||0)*100, 0) + ' upside' },
      { k:'QUALITY', v: fundScore ? fundScore + '/100' : '—', vc: fundScore >= 70 ? 'gn' : fundScore >= 50 ? 'am' : 'rd', s: '' },
    ];

    const stars = upside >= 0.20 ? '★★★★★' : upside >= 0.15 ? '★★★☆☆' : upside >= 0.05 ? '★★☆☆☆' : '★☆☆☆☆';
    const callV = verdict + ' · INVEST';
    const callR = thesisParts.slice(0, 2).join('. ') + '.';
    const callT = `Buy at price ≤ ${T.analyst_target ? fmtPx(T.analyst_target * 0.85) : '—'} · hold to IV ${fmtPx(T.analyst_target)}`;

    return {
      title: 'EXECUTIVE BRIEF · OVERVIEW · SYNTHESIS @ INVESTMENT · 1–5yr',
      verdict, vCls, stars,
      thesis: thesisParts.slice(0, 3).join('. ') + '.',
      kpis,
      trigger: `Price ≤ ${T.analyst_target ? fmtPx(T.analyst_target * 0.85) : '—'} (MoS > 15%)`,
      alignment: `Analyst upside ${(upside*100).toFixed(0)}% · Quality ${fundScore}/100`,
      invalidate: `Quality breaks or analyst PT cut > 10%`,
      size: `3–5% NAV on BUY trigger · scale over 3 tranches`,
      callV, callR, callT,
    };
  }
}

// ─── exec brief renderer ─────────────────────────────────────────────────
function renderExecBrief() {
  const strat = STATE.activeStrategy || 'SWING';
  const b = _computeExecBrief(strat);

  // Update button classes
  ['SWING','POSITION','INVESTMENT'].forEach(m => {
    const btnId = 'qovBtn' + m.charAt(0) + m.slice(1).toLowerCase();
    const btn = document.getElementById(btnId);
    if (btn) btn.classList.toggle('on', m === strat);
  });

  const holdMap = { SWING:'2–10d', POSITION:'2wk–6mo', INVESTMENT:'1–5yr' };
  setHTML('qovStratMeta', `hold: ${holdMap[strat]}`);

  const kpiHtml = b.kpis.map(k =>
    `<div class="qov-exec-kpi"><div class="k">${escapeHtml(k.k)}</div><div class="v ${k.vc}">${escapeHtml(String(k.v))}</div><div class="s">${escapeHtml(k.s)}</div></div>`
  ).join('');

  setHTML('qovExec', `
    <div class="qov-exec-hdr">
      <div class="qov-exec-badge">EXEC BRIEF</div>
      <div class="qov-exec-title">${escapeHtml(b.title)}</div>
    </div>
    <div class="qov-exec-body">
      <div class="qov-exec-vbox">
        <div class="qov-exec-v ${b.vCls}">${b.verdict}</div>
        <div class="qov-exec-stars">${b.stars}</div>
      </div>
      <div class="qov-exec-thesis">${escapeHtml(b.thesis)}</div>
      <div class="qov-exec-dq">
        <div class="k">REGIME</div>
        <div class="v">${escapeHtml(safeStr((_T()||{}).regime||'—'))}</div>
      </div>
    </div>
    <div class="qov-exec-kpis">${kpiHtml}</div>
    <div class="qov-exec-row"><div class="qov-exec-row-k">TRIGGER</div><div class="qov-exec-row-v">${escapeHtml(b.trigger)}</div></div>
    <div class="qov-exec-row"><div class="qov-exec-row-k">ALIGNMENT</div><div class="qov-exec-row-v">${escapeHtml(b.alignment)}</div></div>
    <div class="qov-exec-row"><div class="qov-exec-row-k">INVALIDATE</div><div class="qov-exec-row-v">${escapeHtml(b.invalidate)}</div></div>
    <div class="qov-exec-row"><div class="qov-exec-row-k">SIZE</div><div class="qov-exec-row-v">${escapeHtml(b.size)}</div></div>
    <div class="qov-exec-call">
      <div class="qov-exec-call-v">${escapeHtml(b.callV)}</div>
      <div class="qov-exec-call-r">${escapeHtml(b.callR)}</div>
      <div class="qov-exec-call-t">${escapeHtml(b.callT)}</div>
    </div>`);
}

// ─── cross-lens renderer ──────────────────────────────────────────────────
function renderCrossLens() {
  const T = _T() || {};
  const { payloads, portfolio } = STATE;
  const upside = T.analyst_upside ?? 0;
  const score = num(T.score, 0);
  const rr = num(T.rr, 0);
  const regime = safeStr(T.regime || '');
  const ns = (() => {
    const raw = T.news_sentiment_score;
    if (typeof raw === 'object' && raw) return raw.score ?? 0;
    return typeof raw === 'number' ? raw : null;
  })();

  const lenses = [
    {
      nm: 'VALUE',
      cls: upside > 0.10 ? 'gn' : upside < -0.05 ? 'rd' : 'am',
      lb: upside > 0.10 ? 'UPSIDE' : upside < -0.05 ? 'OVERVAL' : 'WATCH',
    },
    {
      nm: 'SWING',
      cls: (score >= 75 && T.above_50ema) ? 'gn' : score < 55 ? 'rd' : 'am',
      lb: (score >= 75 && T.above_50ema) ? 'BUY' : score < 55 ? 'AVOID' : 'WATCH',
    },
    {
      nm: 'EARNINGS',
      cls: (T.earn_days != null && T.earn_days <= 7) ? 'am' : T.earn_days != null ? 'gn' : 'am',
      lb: (T.earn_days != null && T.earn_days <= 7) ? 'BINARY' : T.earn_days != null ? '+' + T.earn_days + 'd' : 'NEUTRAL',
    },
    {
      nm: 'MACRO',
      cls: regime === 'risk_on_trending' ? 'gn' : regime === 'panic' ? 'rd' : 'am',
      lb: regime === 'risk_on_trending' ? 'TRENDING' : regime === 'panic' ? 'PANIC' : 'CHOPPY',
    },
    {
      nm: 'INSIDER',
      cls: (T.insider_buys ?? 0) > (T.insider_sells ?? 0) ? 'gn'
           : ((T.insider_sells ?? 0) > (T.insider_buys ?? 0) && (T.insider_sells ?? 0) > 3) ? 'rd'
           : 'am',
      lb: (T.insider_buys ?? 0) > (T.insider_sells ?? 0) ? 'BUYING'
          : ((T.insider_sells ?? 0) > (T.insider_buys ?? 0) && (T.insider_sells ?? 0) > 3) ? 'SELLING'
          : 'NEUTRAL',
    },
    {
      nm: 'RISK',
      cls: rr >= 3 ? 'gn' : (rr < 1.5 || rr === 0) ? 'rd' : 'am',
      lb: rr >= 3 ? 'OK' : (rr < 1.5 || rr === 0) ? 'POOR RR' : 'SIZE-CAP',
    },
    {
      nm: 'NEWS',
      cls: ns != null && ns > 0.3 ? 'gn' : ns != null && ns < -0.3 ? 'rd' : 'am',
      lb: ns != null && ns > 0.3 ? 'BULLISH' : ns != null && ns < -0.3 ? 'BEARISH' : 'NEUTRAL',
    },
    {
      nm: 'PORTFOLIO',
      cls: portfolio ? 'gn' : 'am',
      lb: portfolio ? 'HELD' : 'NOT HELD',
    },
  ];

  const pillsHtml = lenses.map(l =>
    `<div class="qov-xlens-vote"><div class="qov-xlens-dot ${l.cls}"></div><span class="qov-xlens-nm">${l.nm}</span><span class="qov-xlens-lb">${l.lb}</span></div>`
  ).join('');

  const conflicts = [];
  const swingLens = lenses.find(l => l.nm === 'SWING');
  const valueLens = lenses.find(l => l.nm === 'VALUE');
  if (swingLens && valueLens && swingLens.cls !== valueLens.cls && (swingLens.cls === 'gn' || valueLens.cls === 'gn')) {
    conflicts.push(`Swing (${swingLens.lb}) vs Value (${valueLens.lb}) disagree — check lens alignment before sizing`);
  }
  if (regime === 'panic') {
    conflicts.push('Macro lens shows PANIC — all long entries should be paused per regime gate');
  }

  const conflictsHtml = conflicts.map(c => `<div class="qov-xlens-conflict">${escapeHtml(c)}</div>`).join('');

  setHTML('qovXlens', `<div class="qov-xlens-votes">${pillsHtml}</div>${conflictsHtml}`);
}

// ─── collapsible panel helpers ───────────────────────────────────────────
function _updateOpenCount() {
  const root = document.getElementById('qovRoot');
  if (!root) return;
  const total = root.querySelectorAll('.qov-collapsible').length;
  const open = root.querySelectorAll('.qov-collapsible.open').length;
  setHTML('qovOpenCount', open + ' of ' + total + ' open');
}

window.__qovToggle = (id) => {
  const el = document.getElementById(id);
  if (el) { el.classList.toggle('open'); _updateOpenCount(); }
};

window.__qovExpandAll = () => {
  const root = document.getElementById('qovRoot');
  if (root) root.querySelectorAll('.qov-collapsible').forEach(p => p.classList.add('open'));
  _updateOpenCount();
};

window.__qovCollapseAll = () => {
  const root = document.getElementById('qovRoot');
  if (root) root.querySelectorAll('.qov-collapsible').forEach(p => p.classList.remove('open'));
  _updateOpenCount();
};

window.__qovSetStrat = (s) => {
  STATE.activeStrategy = s;
  // Re-render every mode-dependent section so the toggle is fully live:
  // exec brief, B1 engine targets, B2 setup strip, B3 risk, B4 forward
  // outcomes, B5 pre-flight, B6 decision matrix, B8 strategy-fit highlight,
  // B9 action-trigger highlight, and the (dead-code) verdict strip horizons.
  // renderAll() is idempotent (pure STATE re-reads, no fetch / listener leak),
  // so re-running the mode-agnostic panels is cheap and side-effect-free.
  // renderVerdictStrip targets a sticky-strip that the current shell does not
  // mount; guard it so its null-DOM access can never abort the rest.
  try { renderVerdictStrip(); } catch (e) { /* verdict strip not mounted */ }
  renderAll();
};

// ─── section renderers ──────────────────────────────────────────────────
function renderVerdictStrip() {
  const T = _T() || {};
  const { ticker, payloads } = STATE;
  setText('qovTicker', ticker || '—');
  const industry = T.industry, sector = T.sector;
  setText('qovName', (industry || sector)
    ? `${industry || ''}${industry && sector ? ' · ' : ''}${sector || ''}` : '');
  const price = num(T.price, NaN);
  const chg = num(T.pct_chg, num(T.perf_1d, 0));
  setHTML('qovPrice', !isNaN(price) ? `$${price.toFixed(2)}` : '—');
  setHTML('qovChg', `<span class="qov-chg" style="color:${chg>=0?'var(--gn)':'var(--rd)'}">${(chg>=0?'+':'') + chg.toFixed(2)}%</span>`);

  // SSOT (2026-06-09): bind the canonical swing verdict (stage / decision.verdict)
  // verbatim — do NOT OR-in score>=75 / score<55, which let a high/low score
  // override the engine and reproduced the scanner-vs-overview divergence.
  const score = num(T.score, 0);
  const vRaw = String((T.decision && T.decision.verdict) || T.verdict || T.stage || 'WATCH').toUpperCase();
  const vMap = { BUY:['BUY','buy'], WATCH:['WATCH','watch'], WAIT:['WAIT','watch'],
                 AVOID:['AVOID','avoid'], SHORT:['SHORT','avoid'], SELL:['SELL','avoid'] };
  const [vLabel, vCls] = vMap[vRaw] || ['WATCH','watch'];
  $('qovSysVerdict').className = 'qov-vd ' + vCls;
  setText('qovSysVerdict', vLabel);
  const conv = safeStr(T.conviction_tier ?? T.conviction?.label) || '—';
  setText('qovSysConv', `Conviction · ${conv} · score ${score}`);

  const hor = ['SWING','POSITION','INVESTMENT'].map(m => {
    const p = payloads[m];
    if (!p) return { lbl:m, val:'…', cls:'am' };
    if (p.decision === 'reject') return { lbl:m, val:'NO TRADE', cls:'rd' };
    if (p.invest_stub) return { lbl:m, val:'INTERIM', cls:'am' };
    if (p.is_etf)      return { lbl:m, val:'ETF', cls:'am' };
    const w = p.warnings || [];
    const t1c = p.t1?.confluence || 0, t1r = p.t1?.r_multiple || 0;
    if (w.some(x => /choch/i.test(x))) return { lbl:m, val:'TIGHTEN', cls:'am' };
    if (t1c >= 5 && t1r >= 2.5) return { lbl:m, val:'BUY', cls:'gn' };
    if (t1c < 3 || t1r < 1.5)    return { lbl:m, val:'WEAK', cls:'rd' };
    return { lbl:m, val:'WATCH', cls:'am' };
  });
  setHTML('qovHorizons', hor.map(h => {
    const lbl = h.lbl === 'INVESTMENT' ? 'INVEST' : h.lbl;
    const on = h.lbl === STATE.activeStrategy ? ' on' : '';
    return `<div class="qov-h ${h.cls}${on}"><div class="lbl">${lbl}</div><div class="val">${h.val}</div></div>`;
  }).join(''));

  const anyP = payloads.SWING || payloads.POSITION || payloads.INVESTMENT;
  const ts = anyP?.timestamp || '—';
  const cache = anyP?._cache?.status === 'hit' ? `hit · ${anyP._cache.age_sec}s` : 'miss';
  const regime = T.regime || _D().regime?.label || '—';
  setHTML('qovStamp', `Engine: ${String(ts).slice(0,16).replace('T',' ')}Z<br>Cache: ${cache}<br>Regime: <b style="color:var(--am)">${regime}</b>`);
}

function renderStrategyFit() {
  const { ticker, payloads } = STATE;
  const modes = [
    { ui:'SWING',      label:'SWING',      hold:'2–10 d · min R 1.5', cls:'swing' },
    { ui:'POSITION',   label:'POSITION',   hold:'2 wk – 6 mo · min R 2.0/3.0', cls:'position' },
    { ui:'INVESTMENT', label:'INVESTMENT', hold:'1+ years · IV-based', cls:'investment' },
  ];
  let bestScore = -1, bestIdx = -1;
  modes.forEach((m, i) => {
    const p = payloads[m.ui];
    const score = p ? (p.t1?.confluence || 0) * (0.4 + (p.t1?.p_reach || 0)) * Math.max(p.t1?.r_multiple || 0, 0.5) : 0;
    if (score > bestScore) { bestScore = score; bestIdx = i; }
  });
  const html = modes.map((m, i) => {
    const isBest = i === bestIdx && bestScore > 0;
    const p = payloads[m.ui];
    const v = _deriveVerdict(p);
    const t1 = p?.t1, t2 = p?.t2;
    let reason;
    if (!p) reason = 'Loading engine…';
    else if (p.decision === 'reject') reason = `Engine rejected ${m.label} — ${(p.warnings||[])[0]||'no target'}.`;
    else if (p.invest_stub) reason = 'INVEST mode using analyst-PT stub. Full IV triangulation pending.';
    else if (t1) reason = `Engine T1 ${escapeHtml(safeStr(t1.behavior))} @ ${fmtPx(t1.price)} · ${escapeHtml(safeStr(t1.action))} · R-mult ${fmtR(t1.r_multiple)}.`;
    else reason = 'No structural T1 found.';
    const tgts = t1
      ? `<b>T1</b> ${fmtPx(t1.price)} (conf ${(t1.confluence||0).toFixed(1)} · ${escapeHtml(safeStr(t1.behavior))})${t2 ? ` · <b>T2</b> ${fmtPx(t2.price)} (conf ${(t2.confluence||0).toFixed(1)} · ${escapeHtml(safeStr(t2.behavior))})` : ''}<br><b>Stop</b> ${fmtPx(p?.stop?.price)} · <b>P(reach)</b> ${t1.p_reach != null ? Math.round(t1.p_reach*100)+'%' : '—'}`
      : '<span style="color:var(--qink-3)">no targets</span>';
    const isActive = m.ui === STATE.activeStrategy;
    return `<div class="qov-fc ${m.cls}${isBest ? ' best' : ''}${isActive ? ' active' : ''}">${isBest ? '<div class="qov-best-badge">★ BEST FIT</div>' : ''}<div class="qov-fc-mode">${m.label}</div><div class="qov-fc-hold">${m.hold}</div><div class="qov-fc-verdict ${v.cls}">${v.label}</div><div class="qov-fc-reason">${reason}</div><div class="qov-fc-tgts">${tgts}</div></div>`;
  }).join('');
  setHTML('qovFitGrid', html);
  const bestMode = bestIdx >= 0 ? modes[bestIdx].label : '—';
  setHTML('qovSysRec', `★ <b>SYSTEM RECOMMENDATION:</b> For ${ticker} today, <b>${bestMode}</b> is the best-fit lens (highest confluence × P(reach) × R composite).`);
}

function renderDecisionMatrix() {
  const T = _T() || {};
  const { ticker } = STATE;
  const pPos = _activeP();
  const t1 = pPos?.t1, stopP = pPos?.stop?.price;
  const score = num(T.score, 0);

  const why = [];
  if (score >= 70) why.push(`<span class="b">Score ${score}/100</span> — above normalized threshold`);
  if ((T.insider_buys || 0) > (T.insider_sells || 0)) why.push(`<span class="b">Insider net buying</span> — ${T.insider_buys||0} buys vs ${T.insider_sells||0} sells`);
  if (T.squeeze_on || T.squeeze?.on) why.push(`<span class="b">Squeeze ON</span> — directional expansion imminent`);
  if ((T.rs_rank || 0) >= 70) why.push(`<span class="b">RS rank ${T.rs_rank}</span> — outperforming sector`);
  if ((t1?.p_reach || 0) >= 0.5) why.push(`<span class="b">P(reach T1) ${Math.round(t1.p_reach*100)}%</span> — Bayesian blend`);
  if ((T.analyst_upside || 0) > 0.1) why.push(`<span class="b">Analyst upside ${(T.analyst_upside*100).toFixed(0)}%</span> — consensus PT above current`);

  const cautions = [];
  for (const w of (pPos?.warnings || [])) cautions.push(`<span class="b">${escapeHtml(w.split(' — ')[0])}</span> — engine warning`);
  if (!T.above_50ema) cautions.push(`<span class="b">Below EMA50</span> — short-term trend broken`);
  if (!T.macd_bullish) cautions.push(`<span class="b">MACD bearish</span> — momentum down`);
  if (T.earn_days != null && T.earn_days <= 7) cautions.push(`<span class="b">Earnings in ${T.earn_days}d</span> — binary risk`);
  if ((T.short_pct || T.short_float_pct || 0) > 15) cautions.push(`<span class="b">Short interest ${(T.short_pct||T.short_float_pct).toFixed(1)}%</span> — squeeze/crowded`);

  const avoid = [];
  if (stopP) avoid.push(`<span class="b">Close &lt; ${fmtPx(stopP)}</span> — breaks structural stop · thesis broken`);
  avoid.push(`<span class="b">Fundamentals shift</span> — if score drops below 60 in next scan`);
  if (T.earn_days != null) avoid.push(`<span class="b">Earnings miss + ER-day gap &gt; 5%</span> — historical reaction reset`);
  if ((T.beta || 0) > 2) avoid.push(`<span class="b">β &gt; 2</span> — high market sensitivity · scale down`);

  setHTML('qovDMGrid', `
    <div class="qov-dm-col buy">
      <div class="qov-dm-head gn">✓ WHY BUY · ${why.length} reasons</div>
      <ul class="qov-dm-list">${why.length ? why.map(r => `<li>${r}</li>`).join('') : '<li>No clear buy reasons.</li>'}</ul>
    </div>
    <div class="qov-dm-col watch">
      <div class="qov-dm-head am">⚠ WHY WAIT · ${cautions.length} cautions</div>
      <ul class="qov-dm-list">${cautions.length ? cautions.map(r => `<li>${r}</li>`).join('') : '<li>No active cautions.</li>'}</ul>
      ${t1 ? `<div class="qov-dm-falsify"><b>Best add-zone:</b> below ${fmtPx(t1.price * 0.96)} (3-4% pullback to engine support).</div>` : ''}
    </div>
    <div class="qov-dm-col avoid">
      <div class="qov-dm-head rd">✗ WHY AVOID · falsification</div>
      <ul class="qov-dm-list">${avoid.map(r => `<li>${r}</li>`).join('')}</ul>
    </div>`);
}

function renderEngineTargets() {
  const T = _T() || {};
  const p = _activeP();
  const price = num(T.price, p?.price_at_analysis ?? 0);
  const t1 = p?.t1, t2 = p?.t2, stopP = p?.stop?.price;

  const rows = [];
  if (t2) {
    const pct = ((t2.price - price) / price) * 100;
    rows.push({ lbl:'t2', name:`T2 · ${fmtPx(t2.price)}`, fill:100, color:'rgba(34,211,238,', pct });
  }
  if (t1) {
    const pct = ((t1.price - price) / price) * 100;
    const t1Pct = t2 ? Math.max(20, Math.min(95, (pct / (((t2.price - price) / price) * 100)) * 100)) : 70;
    rows.push({ lbl:'t1', name:`T1 · ${fmtPx(t1.price)}`, fill:t1Pct, color:'rgba(183,148,244,', pct });
  }
  const entryPx = (p?.entry?.price != null) ? num(p.entry.price, price) : price;
  rows.push({ lbl:'entry', name:`ENTRY · ${fmtPx(entryPx)}`, fill:48, color:'rgba(230,234,242,', pct: ((entryPx - price) / price) * 100 });
  if (stopP) {
    const pct = ((stopP - price) / price) * 100;
    rows.push({ lbl:'stop', name:`STOP · ${fmtPx(stopP)}`, fill:0, color:'rgba(255,107,91,', pct });
  }
  setHTML('qovTargetMap', rows.map(r => `
    <div class="qov-map-row">
      <div class="qov-map-lbl ${r.lbl}">${r.name}</div>
      <div class="qov-map-track"><div class="qov-map-fill" style="width:${r.fill}%; background:${r.lbl==='entry'?'rgba(230,234,242,.18)':r.lbl==='stop'?'rgba(255,107,91,.30)':`linear-gradient(90deg, ${r.color}.10) 0%, ${r.color}.40) 100%)`}"></div></div>
      <div class="qov-map-px ${r.lbl}">${fmtPct(r.pct, 1)}</div>
    </div>`).join(''));

  function srcChips(srcs) {
    return (srcs || []).map(s => `<span class="qov-et-src"><span class="dot" style="background:${SRC_COLOR[s.type]||'var(--qink-3)'}"></span>${escapeHtml(s.type)} ${fmtPx(s.price)} (${s.weight})</span>`).join('');
  }
  function tCard(t, label, cls) {
    if (!t) return `<div class="qov-et-card"><div class="qov-et-head"><div class="qov-et-label ${cls}">${label}</div><div>—</div></div><div style="color:var(--qink-3);font:500 11px var(--qmono);padding:8px 0">engine produced no ${label.toLowerCase()}</div></div>`;
    const bh = BEHAVIOR_CLS[t.behavior] || 'mix';
    const ps = t.p_reach_source || {};
    return `<div class="qov-et-card">
      <div class="qov-et-head"><div class="qov-et-label ${cls}">${label}</div><div><span class="qov-et-price">${fmtPx(t.price)}</span><span class="qov-et-r">${fmtR(t.r_multiple)}</span></div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">BEHAVIOR</div><div class="qov-et-row-v"><span class="qov-et-pill ${bh}">${escapeHtml(safeStr(t.behavior) || '—')}</span></div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">CONFLUENCE</div><div class="qov-et-row-v">${(t.confluence||0).toFixed(1)} from ${(t.sources||[]).length} sources</div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">P(REACH)</div><div class="qov-et-row-v">${t.p_reach != null ? Math.round(t.p_reach*100)+'%' : '—'} · Bayes ${ps.bayes != null ? Math.round(ps.bayes*100)+'%' : '—'} / MC ${ps.mc != null ? Math.round(ps.mc*100)+'%' : '—'} / analog ${ps.analog != null ? Math.round(ps.analog*100)+'%' : '—'}</div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">ACTION</div><div class="qov-et-row-v">${escapeHtml(safeStr(t.action) || '—')}</div></div>
      <div class="qov-et-row" style="align-items:flex-start"><div class="qov-et-row-k">SOURCES</div><div class="qov-et-sources">${srcChips(t.sources) || '<span style="color:var(--qink-3)">none</span>'}</div></div>
    </div>`;
  }
  setHTML('qovEtGrid', tCard(t1, 'T1 · TARGET', 't1') + tCard(t2, 'T2 · STRETCH', 't2'));
}

function renderIntrinsicValue() {
  const T = _T() || {};
  const price = num(T.price, 0);
  const pt = num(T.analyst_target, 0);
  const mos = pt && price ? ((pt - price) / pt) * 100 : null;
  const cells = [
    { k:'REVERSE DCF', v:'—', sub:'—', cls:'' },
    { k:'OWNER EARN YIELD', v:'—', sub:'—', cls:'' },
    { k:'INTRINSIC VALUE', v: pt ? fmtPx(pt) : '—', sub: pt ? `analyst PT · <b style="color:${mos > 0 ? 'var(--gn)' : 'var(--rd)'}">MoS ${mos.toFixed(1)}%</b>` : 'no analyst consensus', cls: mos > 10 ? 'gn' : mos > 0 ? 'am' : '' },
    { k:'QUALITY (PIO/Z/M)', v:'—', sub:'—', cls:'' },
    { k:'EARN YIELD vs 10Y', v:'—', sub:'—', cls:'' },
    { k:'MOAT', v:'—', sub:'—', cls:'' },
  ];
  setHTML('qovValGrid', cells.map(c => `<div class="qov-v ${c.cls}"><div class="qov-v-k">${c.k}</div><div class="qov-v-v ${c.cls}">${c.v}</div><div class="qov-v-sub">${c.sub}</div></div>`).join(''));
  setHTML('qovBuffett', `<div class="q">★ The 10-year test · if markets closed for a decade, would you own this?</div><div class="a"><b style="color:var(--am)">Qualitative judgment required</b> — moat, capital allocation, reinvestment ROIIC, management. Engine context: sector ${escapeHtml(T.sector || '—')}, industry ${escapeHtml(T.industry || '—')}, score ${T.score || '—'}.</div>`);
}

function renderEarningsCard() {
  const T = _T() || {};
  const earnDays = T.earn_days;
  const hist = T.zacks_eps_surprise_history || [];
  const cells = [
    { k:'REPORT DATE', v: earnDays != null ? `+${earnDays}d` : '—' },
    { k:'TIMING', v:'—' },
    { k:'FISCAL Q', v:'—' },
    { k:'EPS CONSENSUS', v:'—' },
    { k:'REVENUE CONS', v:'—' },
    { k:'WHISPER', v:'—' },
    { k:'DAYS TO PRINT', v: earnDays != null ? `+${earnDays}d` : '—' },
  ];
  setHTML('qovErHead', cells.map(c => `<div class="qov-er-cell"><div class="k">${c.k}</div><div class="v">${c.v}</div></div>`).join(''));

  const iv = (T.options_data || {}).iv_rank;
  const ivStr = iv != null ? Math.round(iv*100)+'%' : '—';
  const esp = T.zacks_earnings_esp;
  const beatRate = T.earnings_beat;
  setHTML('qovErMid', `
    <div class="qov-er-implied">
      <div class="label">IMPLIED MOVE · option-derived</div>
      <div class="move">—</div>
      <div class="sub">Requires ATM straddle · pending options chain wiring · IV rank ${ivStr}</div>
      <div class="sub" style="margin-top:6px"><b>Vol-crush risk:</b> IV rank ${ivStr} · premiums likely compress post-print.</div>
    </div>
    <div class="qov-er-rev">
      <div class="label">EARNINGS PERFORMANCE</div>
      <div class="qov-er-rev-row"><div class="k">ESP</div><div class="v ${esp > 0 ? 'gn' : esp < 0 ? 'rd' : ''}">${esp != null ? (esp > 0 ? '+' : '') + esp.toFixed(2) + '%' : '—'}</div><div>${esp > 0 ? '↑' : esp < 0 ? '↓' : '—'}</div></div>
      <div class="qov-er-rev-row"><div class="k">BEAT RATE</div><div class="v ${beatRate > 60 ? 'gn' : ''}">${beatRate != null ? beatRate + '%' : '—'}</div><div></div></div>
      <div class="qov-er-rev-row"><div class="k">DAYS</div><div class="v">${earnDays != null ? earnDays + 'd' : '—'}</div><div></div></div>
      <div style="margin-top:8px; font:500 10.5px var(--qmono); color:var(--qink-1); line-height:1.5">${T.esp_play ? '<b style="color:var(--gn)">ESP PLAY signal active</b>' : 'ESP-play signal not active'}</div>
    </div>`);

  if (hist && hist.length) {
    setHTML('qovErTbody', hist.slice(0, 8).map(q => `
      <tr><td>${escapeHtml(q.quarter || '—')}</td>
          <td>${q.eps_actual != null ? '$' + q.eps_actual.toFixed(2) : '—'} / ${q.eps_estimate != null ? '$' + q.eps_estimate.toFixed(2) : '—'}</td>
          <td class="${q.surprise_pct > 0 ? 'gn' : 'rd'}">${q.surprise_pct != null ? (q.surprise_pct > 0 ? '+' : '') + q.surprise_pct.toFixed(1) + '%' : '—'}</td>
          <td>—</td><td>—</td><td>—</td>
          <td>${q.surprise_pct > 0 ? 'beat' : 'miss'}</td>
      </tr>`).join(''));
    const beats = hist.filter(q => q.surprise_pct > 0).length;
    const avgSurp = hist.reduce((s, q) => s + (q.surprise_pct || 0), 0) / hist.length;
    setHTML('qovErStatsBanner', `<b>${beats} / ${hist.length} beats</b> · avg EPS surprise ${(avgSurp > 0 ? '+' : '') + avgSurp.toFixed(1)}% · ${T.esp_play ? '<b style="color:var(--gn)">ESP-play fires</b>' : 'ESP-play not active'}`);
  } else {
    setHTML('qovErTbody', `<tr><td colspan="7" style="color:var(--qink-3); padding:14px"><b>No earnings history available</b> for ${STATE.ticker}.</td></tr>`);
    setHTML('qovErStatsBanner', `<b>8Q stats:</b> data not available.`);
  }
}

function renderMyPosition() {
  const pf = STATE.portfolio;
  // In collapsible shell, position panel is always present (qovPanelCd).
  // Show "not held" message when no portfolio entry.
  if (!pf) {
    setHTML('qovPosGrid', `<div style="grid-column:1/-1;padding:14px;color:var(--qink-3);font:500 11px var(--qmono)">Not currently held in tracked portfolio.</div>`);
    setHTML('qovPosTax', '');
    return;
  }
  const T = _T() || {};
  const price = num(T.price, pf.current_price ?? 0);
  const qty = num(pf.shares ?? pf.quantity, 0);
  const cost = num(pf.entry_price ?? pf.cost_basis, 0);
  const pnl = qty * (price - cost);
  const pnlPct = cost ? ((price - cost) / cost) * 100 : 0;
  const entryDate = pf.entry_date || pf.opened_at;
  const days = entryDate ? Math.floor((Date.now() - new Date(entryDate).getTime()) / (1000*60*60*24)) : null;
  const cells = [
    { k:'HELD QTY', v: qty + ' sh', sub:(pf.direction || 'long'), cls:'' },
    { k:'COST BASIS', v: fmtPx(cost), sub: entryDate ? entryDate.slice(0,10) : '—', cls:'' },
    { k:'UNREAL P&L', v: (pnl >= 0 ? '+' : '') + '$' + Math.abs(pnl).toFixed(0), sub: fmtPct(pnlPct), cls: pnl >= 0 ? 'gn' : 'rd' },
    { k:'DAYS HELD', v: days != null ? days + 'd' : '—', sub: days != null && days < 365 ? `LT in ${365-days}d · ST gain` : 'LT eligible', cls: days != null && days < 365 ? 'am' : 'gn' },
    { k:'STOP', v: fmtPx(pf.stop), sub: pf.stop && price ? fmtPct(((pf.stop - price) / price) * 100) : '—', cls:'' },
    { k:'TARGET', v: fmtPx(pf.target1 || pf.target), sub: pf.target1 && price ? fmtPct(((pf.target1 - price) / price) * 100) : '—', cls:'' },
  ];
  setHTML('qovPosGrid', cells.map(c => `<div class="qov-ps ${c.cls}"><div class="qov-ps-k">${c.k}</div><div class="qov-ps-v ${c.cls}">${c.v}</div><div class="qov-ps-sub">${c.sub}</div></div>`).join(''));
  const taxNote = days != null && days < 365
    ? `Entered ${entryDate?.slice(0,10) || '—'} (${days}d ago). Long-term rate eligible in ${365-days}d. Selling now would realize <b style="color:var(--am)">short-term gain</b>.`
    : `Long-term eligible.`;
  setHTML('qovPosTax', `<b style="color:var(--qink)">Tax / lot status:</b> Cost basis ${fmtPx(cost)} · ${taxNote}`);
}

function renderMTF() {
  const T = _T() || {};
  const daily = {
    trend: T.above_50ema ? 'bull' : 'bear',
    trendNote: T.above_8ema && T.above_21ema && T.above_50ema ? 'Above EMA 8/21/50 · uptrend' : (!T.above_50ema ? 'Below EMA 50 · breakdown' : 'Mixed EMA stack'),
    mom: T.macd_bullish ? 'bull' : 'bear',
    momNote: `MACD ${escapeHtml(T.macd_signal || '—')} · RSI ${T.rsi != null ? Math.round(T.rsi) : '—'}`,
    vol: T.rvol > 1.5 ? (T.pct_chg < 0 ? 'bear' : 'bull') : 'neut',
    volNote: T.rvol != null ? `RVOL ${T.rvol.toFixed(2)} · ${T.rvol > 1.5 ? 'elevated' : 'normal'}` : 'RVOL —',
    bias: T.above_50ema && T.macd_bullish ? 'BULL' : (!T.above_50ema && !T.macd_bullish ? 'BEAR' : 'NEUTRAL'),
  };
  const rows = [
    { tf:'MONTHLY', trend:'neut', trendNote:'—', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias:'—', biasCls:'am' },
    { tf:'WEEKLY',  trend: T.weekly_bull ? 'bull' : 'neut', trendNote: T.weekly_bull ? 'Weekly trend bullish' : 'Weekly trend not confirmed', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias: T.weekly_bull ? 'BULL' : 'NEUT', biasCls: T.weekly_bull ? 'gn' : 'am' },
    { tf:'DAILY',   ...daily, biasCls: daily.bias === 'BULL' ? 'gn' : daily.bias === 'BEAR' ? 'rd' : 'am' },
    { tf:'4 HOUR',  trend:'neut', trendNote:'—', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias:'—', biasCls:'am' },
    { tf:'1 HOUR',  trend:'neut', trendNote:'—', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias:'—', biasCls:'am' },
  ];
  setHTML('qovMtfBody', rows.map(r => `
    <tr><td><span class="qov-mtf-tf">${r.tf}</span></td>
        <td><span class="qov-mtf-cell"><span class="dot ${r.trend}"></span>${r.trendNote}</span></td>
        <td><span class="qov-mtf-cell"><span class="dot ${r.mom}"></span>${r.momNote}</span></td>
        <td><span class="qov-mtf-cell"><span class="dot ${r.vol}"></span>${r.volNote}</span></td>
        <td><span class="qov-pill ${r.biasCls}">${r.bias}</span></td>
    </tr>`).join(''));
  const bulls = rows.filter(r => r.bias === 'BULL').length;
  const bears = rows.filter(r => r.bias === 'BEAR').length;
  const col = bulls > bears ? 'var(--gn)' : bears > bulls ? 'var(--rd)' : 'var(--am)';
  $('qovMtfSummary').style.borderLeftColor = col;
  setHTML('qovMtfSummary', `<b style="color:${col}">Bias:</b> ${bulls} bullish · ${bears} bearish · ${rows.length-bulls-bears} neutral. Monthly / 4H / 1H data not yet available — daily and weekly derived from scan indicators.`);
}

function renderSetupStrip() {
  const T = _T() || {};
  // Only the →T1/→T2/→STOP cells are mode-dependent (read from the active
  // engine payload); EMA/MACD/RSI/RVOL/BETA/EARN cells stay sourced from T.
  const p = _activeP();
  const price = num(T.price, p?.price_at_analysis ?? 0);
  const t1 = p?.t1, t2 = p?.t2, stopP = p?.stop?.price;
  const cells = [
    { k:'CURRENT', v: fmtPx(price), sub: fmtPct(T.pct_chg ?? T.perf_1d ?? 0, 2) + ' today', cls:(T.pct_chg ?? 0) >= 0 ? 'gn' : 'rd' },
    { k:'→ T1',    v: fmtPx(t1?.price), sub: t1 ? `conf ${(t1.confluence||0).toFixed(1)} · ${escapeHtml(t1.behavior)}` : '—', cls: t1 ? 'am' : '' },
    { k:'→ T2',    v: fmtPx(t2?.price), sub: t2 ? `conf ${(t2.confluence||0).toFixed(1)} · ${escapeHtml(t2.behavior)}` : '—', cls: t2 ? 'am' : '' },
    { k:'→ STOP',  v: fmtPx(stopP), sub: stopP && price ? fmtPct(((stopP-price)/price)*100, 1) + ' · 1.0R' : '—', cls:'rd' },
    { k:'EMA STACK', v: T.above_8ema && T.above_21ema && T.above_50ema ? 'BULLISH' : (!T.above_50ema ? 'BEARISH' : 'MIXED'), sub: `8/${T.above_8ema?'✓':'✗'} 21/${T.above_21ema?'✓':'✗'} 50/${T.above_50ema?'✓':'✗'} 200/${T.above_200sma?'✓':'✗'}`, cls: T.above_50ema && T.above_200sma ? 'gn' : 'rd' },
    { k:'MACD', v: T.macd_bullish ? 'BULLISH' : 'BEARISH', sub: escapeHtml(T.macd_signal || '—'), cls: T.macd_bullish ? 'gn' : 'rd' },
    { k:'RSI(14)', v: T.rsi != null ? Math.round(T.rsi) : '—', sub: T.rsi == null ? '—' : (T.rsi >= 70 ? 'overbought' : T.rsi >= 50 ? 'bullish' : T.rsi >= 30 ? 'bearish' : 'oversold'), cls: T.rsi == null ? '' : (T.rsi >= 70 || T.rsi <= 30 ? 'am' : '') },
    { k:'RVOL', v: T.rvol != null ? T.rvol.toFixed(2) : '—', sub: T.rvol == null ? '—' : (T.rvol >= 1.5 ? 'elevated' : 'normal'), cls: T.rvol == null ? '' : (T.rvol >= 1.5 ? 'am' : '') },
    { k:'BETA', v: T.beta != null ? T.beta.toFixed(2) : '—', sub: T.beta == null ? '—' : (T.beta < 0.8 ? 'low-β' : T.beta > 1.5 ? 'high-β' : 'mid-β'), cls: T.beta == null ? '' : (Math.abs(T.beta - 1) < 0.2 ? 'gn' : 'am') },
    { k:'EARN DAYS', v: T.earn_days != null ? `+${T.earn_days}d` : '—', sub: T.earn_days == null ? 'no schedule' : (T.earn_days <= 7 ? 'imminent' : T.earn_days <= 30 ? 'this month' : 'beyond hold'), cls: T.earn_days == null ? '' : (T.earn_days <= 7 ? 'rd' : 'am') },
  ];
  setHTML('qovPqGrid', cells.map(c => `<div class="qov-pq-cell"><div class="qov-pq-k">${c.k}</div><div class="qov-pq-v ${c.cls}">${c.v}</div><div class="qov-pq-sub">${c.sub}</div></div>`).join(''));
}

function renderRiskProfile() {
  const T = _T() || {};
  const p = _activeP();
  const price = num(T.price, p?.price_at_analysis ?? 0);
  const stopP = p?.stop?.price;
  const sizing = p?.sizing || {};
  const oneR = price && stopP ? Math.abs(price - stopP) : null;
  const sizeSh = sizing.shares ?? sizing.size ?? null;
  const equity = sizing.equity ?? 25000;
  const maxLoss = sizeSh && oneR ? sizeSh * oneR : null;
  const beta = T.beta;
  const cells = [
    { k:'SIZE', v: sizeSh != null ? sizeSh + ' sh' : '—', sub: sizing.basis || 'half-Kelly + regime mult', cls:'gn' },
    { k:'1R RISK', v: oneR != null ? '$' + oneR.toFixed(2) : '—', sub: oneR && price ? `${price.toFixed(2)} → ${stopP.toFixed(2)}` : '—', cls:'rd' },
    { k:'MAX LOSS', v: maxLoss != null ? '−$' + maxLoss.toFixed(0) : '—', sub: maxLoss && equity ? `${(maxLoss/equity*100).toFixed(2)}% of $${(equity/1000).toFixed(0)}K` : '—', cls:'rd' },
    { k:'DD HAIRCUT', v: sizing.drawdown_mult != null ? (sizing.drawdown_mult * 100).toFixed(0) + '%' : '100%', sub: 'drawdown scaler', cls: sizing.drawdown_mult < 1 ? 'am' : 'gn' },
    { k:'β-ADJ', v: beta != null ? beta.toFixed(2) + '×' : '—', sub: beta == null ? '—' : (beta < 1 ? 'defensive' : 'aggressive'), cls: beta != null && Math.abs(beta - 1) < 0.3 ? 'gn' : 'am' },
  ];
  setHTML('qovRpGrid', cells.map(c => `<div class="qov-rp-cell ${c.cls}"><div class="qov-rp-k">${c.k}</div><div class="qov-rp-v ${c.cls}">${c.v}</div><div class="qov-rp-sub">${c.sub}</div></div>`).join(''));
}

function renderNewsPulse() {
  const T = _T() || {};
  const articles = (T.news_articles || []).slice(0, 5);
  const nsRaw = T.news_sentiment_score;
  const ns = (typeof nsRaw === 'object' && nsRaw) ? (nsRaw.score || 0) : (typeof nsRaw === 'number' ? nsRaw : null);
  const momentum = (typeof nsRaw === 'object' && nsRaw) ? (nsRaw.momentum || '') : '';
  const cnt = (typeof nsRaw === 'object' && nsRaw) ? (nsRaw.article_count || articles.length) : articles.length;
  const nsCls = ns == null ? 'am' : ns >= 2 ? 'gn' : ns <= -2 ? 'rd' : 'am';
  const nsLabel = ns == null ? 'no signal' : ns >= 2 ? 'net BULLISH' : ns <= -2 ? 'net BEARISH' : 'mixed';
  const newsRows = articles.length
    ? articles.map(a => {
        const sent = (a.sentiment || a.sentiment_label || 'neutral').toLowerCase();
        const cls = sent.includes('pos')||sent.includes('bull') ? 'gn' : sent.includes('neg')||sent.includes('bear') ? 'rd' : 'am';
        const day = (a.date || a.published_at || '').slice(5,10);
        return `<div class="qov-news-row"><span class="qov-news-day">${escapeHtml(day || '—')}</span><span class="qov-news-src">${escapeHtml(a.source || a.publisher || '—')}</span><span class="qov-news-body">${escapeHtml(a.title || a.headline || '(no title)')}</span><span class="qov-news-sent"><span class="qov-pill ${cls}">${sent.slice(0,4).toUpperCase()}</span></span></div>`;
      }).join('')
    : `<div style="padding:14px; color:var(--qink-3); font:500 11px var(--qmono)">no recent news articles</div>`;
  setHTML('qovNsGrid', `
    <div class="qov-ns-gauge">
      <div style="font:700 9.5px var(--qmono); color:var(--qink-3); letter-spacing:.13em">NEWS SENT 30D</div>
      <div class="qov-ns-gauge-v ${nsCls}">${ns != null ? (ns>=0?'+':'') + ns.toFixed(2) : '—'}</div>
      <div class="qov-ns-gauge-sub">${nsLabel}${momentum ? ' · '+momentum : ''} · ${cnt} articles</div>
      <div style="margin-top:12px; padding-top:12px; border-top:1px solid var(--qline); font:500 10.5px var(--qmono); color:var(--qink-1); line-height:1.6">
        <b>Catalyst:</b> earnings ${T.earn_days != null ? '+' + T.earn_days + 'd' : '—'}<br>
        <b>Insider 90d:</b> ${T.insider_buys || 0} buys / ${T.insider_sells || 0} sells<br>
        <b>Zacks ESP:</b> ${T.zacks_earnings_esp != null ? (T.zacks_earnings_esp > 0 ? '+' : '') + T.zacks_earnings_esp.toFixed(2) + '%' : '—'}
      </div>
    </div>
    <div class="qov-ns-feed">${newsRows}</div>`);
}

function renderForwardOutcomes() {
  const T = _T() || {};
  const p = _activeP();
  const t1 = p?.t1 || {}, t2 = p?.t2 || {};
  const pT1 = t1.p_reach ?? 0;
  const pT2 = t2.p_reach ?? 0;
  const pStop = Math.max(0, Math.min(1, 1 - pT1 - 0.15));
  const pFlat = Math.max(0, 1 - pT1 - pT2 - pStop);
  function bar(label, v, color) {
    return `<div class="qov-fo-bar-row"><div class="qov-fo-bar-k">${label}</div><div class="qov-fo-bar-track"><div class="qov-fo-bar-fill" style="width:${Math.round(v*100)}%; background:${color}"></div></div><div class="qov-fo-bar-v" style="color:${color}">${Math.round(v*100)}%</div></div>`;
  }
  setHTML('qovFoGrid', `
    <div>
      <div style="font:700 9.5px var(--qmono); color:var(--qink-3); letter-spacing:.13em; margin-bottom:8px">PROBABILITY · ${_activeLabel()} lens</div>
      ${bar('P(REACH T1)', pT1, 'var(--gn)')}
      ${bar('P(REACH T2)', pT2, 'var(--am)')}
      ${bar('P(STOP HIT)', pStop, 'var(--rd)')}
      ${bar('P(FLAT)',     pFlat, 'var(--qink-3)')}
    </div>
    <div>
      <div style="font:700 9.5px var(--qmono); color:var(--qink-3); letter-spacing:.13em; margin-bottom:8px">HOLD WINDOW</div>
      <div class="qov-fo-grid">
        <div>
          <div class="qov-fo-cell"><div class="k">SETUP FAMILY</div><div class="v">${escapeHtml(safeStr(T.setup) || '—')}</div></div>
          <div class="qov-fo-cell"><div class="k">REGIME</div><div class="v" style="color:var(--am)">${escapeHtml(safeStr(T.regime) || '—')}</div></div>
          <div class="qov-fo-cell"><div class="k">MIN HOLD</div><div class="v">${T.hold_period_min ? T.hold_period_min + ' d' : '—'}</div></div>
          <div class="qov-fo-cell"><div class="k">MAX HOLD</div><div class="v">${(T.max_hold_days || T.hold_period_max) ? (T.max_hold_days || T.hold_period_max) + ' d' : '—'}</div></div>
          <div class="qov-fo-cell"><div class="k">SETUP n</div><div class="v">${T._setup_n || '—'}</div></div>
          <div class="qov-fo-cell"><div class="k">WILSON LB</div><div class="v" style="color:var(--gn)">${T._setup_wilson_lb != null ? (T._setup_wilson_lb*100).toFixed(0)+'%' : '—'}</div></div>
        </div>
      </div>
    </div>`);
}

function renderPreFlight() {
  const T = _T() || {};
  const p = _activeP();
  const warns = p?.warnings || [];
  const items = [];
  items.push({ pass: T.market_cap >= 1e9, k:'Liquidity gate · ' + (T.market_cap ? '$'+(T.market_cap/1e9).toFixed(1)+'B mcap' : '—') });
  items.push({ pass: T.earn_days == null || T.earn_days > 7, warn: T.earn_days != null && T.earn_days <= 7, k:'Earnings blackout · ' + (T.earn_days != null ? '+'+T.earn_days+'d' : 'no schedule') });
  items.push({ pass: T.regime && !/panic|risk_off/i.test(T.regime), k:'Regime allow · ' + (T.regime || '—') });
  items.push({ pass: T.entry_quality && /FRESH|PULLBACK|VALID/.test(T.entry_quality), warn: T.entry_quality === 'EXTENDED', k:'Entry quality · ' + (T.entry_quality || '—') });
  items.push({ pass: (p?.t1?.r_multiple || 0) >= 3, warn: (p?.t1?.r_multiple || 0) >= 2 && (p?.t1?.r_multiple || 0) < 3, k:'R:R ≥ 3.0 · actual ' + ((p?.t1?.r_multiple || 0).toFixed(2)) });
  items.push({ pass: T.score >= 70, warn: T.score >= 55 && T.score < 70, k:'Score band ≥ 70 · actual ' + (T.score || '—') });
  items.push({ pass: !warns.some(w=>/choch/i.test(w)), warn: warns.some(w=>/choch/i.test(w)), k:'CHoCH check · ' + (warns.some(w=>/choch/i.test(w)) ? 'warning' : 'clear') });
  items.push(T._setup_wilson_lb != null
    ? { pass: T._setup_wilson_lb >= 0.5, warn: T._setup_wilson_lb >= 0.35 && T._setup_wilson_lb < 0.5, k:'Wilson LB ≥ 50% · ' + (T._setup_wilson_lb*100).toFixed(0)+'%' }
    : { pass: true, warn: false, k:'Wilson LB · N/A (uncomputed)' });
  items.push({ pass: (p?.t1?.confluence || 0) >= 4, warn: (p?.t1?.confluence || 0) >= 2, k:'Confluence ≥ 4 · ' + ((p?.t1?.confluence || 0).toFixed(1)) });
  items.push({ pass: (p?.t1?.p_reach || 0) >= 0.4, warn: (p?.t1?.p_reach || 0) >= 0.25, k:'P(reach T1) ≥ 40% · ' + (p?.t1?.p_reach != null ? Math.round(p.t1.p_reach*100)+'%' : '—') });
  setHTML('qovPfGrid', items.map(it => {
    const dot = it.pass ? 'pass' : (it.warn ? 'warn' : 'fail');
    return `<div class="qov-pf-cell"><div class="qov-pf-dot ${dot}"></div><div class="qov-pf-k">${it.k}</div></div>`;
  }).join(''));
  const fails = items.filter(it => !it.pass && !it.warn).length;
  const wn = items.filter(it => it.warn).length;
  const banner = fails > 0
    ? `<b style="color:var(--rd)">${fails} gate(s) FAIL</b> — engine does not allow new entry.`
    : wn > 0
      ? `<b style="color:var(--am)">${wn} warning(s)</b> — engine allows with caution: ${warns.slice(0,3).map(escapeHtml).join(' · ')}`
      : `<b style="color:var(--gn)">All gates clear</b> — engine fully approves new entry.`;
  $('qovPfBanner').className = 'qov-banner ' + (fails > 0 ? 'warn' : wn > 0 ? 'warn' : 'info');
  setHTML('qovPfBanner', banner);
}

function renderActionTriggers() {
  const T = _T() || {};
  const { payloads } = STATE;
  function buildCard(modeUi, cls, modeCls, p) {
    const act = modeUi === STATE.activeStrategy ? ' active' : '';
    if (!p || p.decision === 'reject') {
      return `<div class="qov-trig-card ${cls}${act}"><div class="qov-trig-mode ${modeCls}">${modeUi} · NO TRADE</div><div style="padding:8px 0; color:var(--qink-3); font:500 11px var(--qmono)">Engine cannot generate ${modeUi} targets.</div></div>`;
    }
    const t1 = p.t1 || {}, t2 = p.t2 || {}, stopP = p.stop?.price;
    const rules = [];
    rules.push({ lbl:'EXIT TRIGGER (failsafe)', body:`<span class="when">IF intraday tick &lt; ${fmtPx(stopP)}</span> → <span class="neg">SELL FULL · close-based stop</span>` });
    if (t1.price) rules.push({ lbl:'T1 TRIGGER · trim', body:`<span class="when">IF price tags ${fmtPx(t1.price)} (T1)</span> → <span class="then">${escapeHtml(safeStr(t1.action) || 'trim 33%')} · trail remainder</span>` });
    if (t2.price) rules.push({ lbl:'T2 TRIGGER · scale', body:`<span class="when">IF price tags ${fmtPx(t2.price)} (T2)</span> → <span class="then">${escapeHtml(safeStr(t2.action) || 'scale 50%')} · trail balance</span>` });
    if (modeUi === 'POSITION' && T.above_50ema === false) {
      rules.push({ lbl:'ADD TRIGGER', body:`<span class="when">IF price tags primary zone</span> <span class="and">AND</span> <span class="when">1h closes green</span> <span class="and">AND</span> <span class="when">RSI &gt; 35</span> → <span class="then">ADD 1/3 size · raise stop</span>` });
    }
    if (modeUi === 'INVESTMENT' && T.analyst_target) {
      rules.push({ lbl:'ADD TRIGGER (value)', body:`<span class="when">IF price &lt; ${fmtPx(T.analyst_target * 0.85)} (MoS &gt; 15%)</span> → <span class="then">ADD on weakness · hold to IV ${fmtPx(T.analyst_target)}</span>` });
    }
    rules.push({ lbl:'INVALIDATION', body:`<span class="when">IF daily close &lt; ${fmtPx(stopP)}</span> <span class="and">OR</span> <span class="when">score drops &lt; 60</span> → <span class="neg">EXIT FULL · thesis broken</span>` });
    return `<div class="qov-trig-card ${cls}${act}"><div class="qov-trig-mode ${modeCls}">${modeUi} · ${(p.decision || 'TRADE').toUpperCase()}</div>${rules.map(r => `<div class="qov-trig-rule"><div class="label">${r.lbl}</div><div class="ruleBody">${r.body}</div></div>`).join('')}</div>`;
  }
  setHTML('qovTrigGrid',
    buildCard('SWING', 'swing', 'am', payloads.SWING) +
    buildCard('POSITION', 'position', 'blue', payloads.POSITION) +
    buildCard('INVESTMENT', 'investment', 'lead', payloads.INVESTMENT));
}

function renderAll() {
  const _safe = (name, fn) => { try { fn(); } catch(e) { console.warn('[overview] ' + name + ' threw:', e); } };
  _safe('crossLens',     renderCrossLens);
  _safe('execBrief',     renderExecBrief);
  _safe('strategyFit',   renderStrategyFit);
  _safe('decisionMatrix',renderDecisionMatrix);
  _safe('engineTargets', renderEngineTargets);
  _safe('intrinsicValue',renderIntrinsicValue);
  _safe('earningsCard',  renderEarningsCard);
  _safe('myPosition',    renderMyPosition);
  _safe('mtf',           renderMTF);
  _safe('setupStrip',    renderSetupStrip);
  _safe('riskProfile',   renderRiskProfile);
  _safe('newsPulse',     renderNewsPulse);
  _safe('fwdOutcomes',   renderForwardOutcomes);
  _safe('preFlight',     renderPreFlight);
  _safe('actionTriggers',renderActionTriggers);
  _updateOpenCount();
}

// ─── render entry point ─────────────────────────────────────────────────
export function render() {
  _ensureStyle();
  const T = _T();
  const body = (typeof $ === 'function') ? $('eliteOverviewBody')
              : document.getElementById('eliteOverviewBody');
  if (!body || !T) return;

  // Mount shell once per ticker change
  const tk = (T.ticker || T.symbol || '').toUpperCase();
  if (STATE.ticker !== tk || !STATE.mounted) {
    body.innerHTML = _shellHTML();
    STATE.ticker = tk;
    STATE.payloads = {};
    STATE.portfolio = null;
    STATE.mounted = true;
  }

  // Initial synchronous paint from T (instant)
  renderAll();
  setHTML('qovBanner', `ⓘ <b>OVERVIEW V2</b> · <b>${tk}</b> · loading engine data from <code>/api/trade_engine</code>…`);

  // Async fetch + re-render
  Promise.all([
    loadEngine(tk, 'SWING'),
    loadEngine(tk, 'POSITION'),
    loadEngine(tk, 'INVESTMENT'),
    loadPortfolio(tk),
  ]).then(([sw, ps, iv, pf]) => {
    if (STATE.ticker !== tk) return;  // ticker changed mid-flight; abort
    STATE.payloads = { SWING:sw, POSITION:ps, INVESTMENT:iv };
    STATE.portfolio = pf;
    renderAll();
    const ok = !!sw || !!ps || !!iv;
    const cls = ok ? 'info' : 'warn';
    const msg = ok
      ? `<b style="color:var(--gn)">✓ ENGINE LOADED</b> · SWG ${sw ? '✓' : '—'} POS ${ps ? '✓' : '—'} INV ${iv ? '✓' : '—'} · portfolio ${pf ? '✓ held' : '— not held'}`
      : `<b style="color:var(--rd)">⚠ Engine unreachable</b> — page is showing T-payload data only.`;
    $('qovBanner').className = 'qov-banner ' + cls;
    setHTML('qovBanner', msg);
  });
}

export function dispose() {
  STATE.ticker = null;
  STATE.payloads = {};
  STATE.portfolio = null;
  STATE.mounted = false;
  STATE.activeStrategy = 'SWING';
}
