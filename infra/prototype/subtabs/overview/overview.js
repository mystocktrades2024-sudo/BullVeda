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
const STATE = { ticker:null, payloads:{}, portfolio:null, mounted:false };

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
  return `<div class="qov-root">
    <div class="qov-banner info" id="qovBanner">ⓘ loading…</div>
    <div class="qov-strip">
      <div>
        <div class="qov-tk" id="qovTicker">—</div>
        <div class="qov-nm" id="qovName"></div>
        <div style="margin-top:7px"><span class="qov-px" id="qovPrice">—</span><span id="qovChg"></span></div>
      </div>
      <div class="qov-mid">
        <div style="text-align:center">
          <div id="qovSysVerdict" class="qov-vd watch">—</div>
          <div id="qovSysConv" class="qov-conv">—</div>
        </div>
        <div class="qov-hor" id="qovHorizons"></div>
      </div>
      <div class="qov-stamp" id="qovStamp">Engine: —<br>Cache: —<br>Regime: —</div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">A</span>Strategy Fit Verdict<span class="sub">— all three horizons read this ticker · pick the lens that fits your hold window</span><span class="tag">ENGINE</span></div>
      <div class="qov-fit" id="qovFitGrid"></div>
      <div class="qov-banner warn" id="qovSysRec" style="margin:12px 0 0">—</div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">B</span>Decision Matrix<span class="sub">— engine-derived reasons + falsification criteria</span><span class="tag">ENGINE + ELITE</span></div>
      <div class="qov-dm" id="qovDMGrid"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">C</span>Engine Targets · Where T1 / T2 Live Structurally<span class="sub">— confluence-scored from structural sources · not ATR multiples</span><span class="tag">target_engine.py</span></div>
      <div class="qov-map" id="qovTargetMap"></div>
      <div class="qov-et" id="qovEtGrid"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">C·b</span>Intrinsic Value &amp; Quality<span class="sub">— Buffett discipline · reverse DCF · owner earnings · MoS · quality scores · moat</span><span class="tag">FUNDAMENTALS</span></div>
      <div class="qov-val" id="qovValGrid"></div>
      <div class="qov-buffett" id="qovBuffett"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">C·c</span>Earnings · Detailed Card<span class="sub">— next print · implied move · revisions · 8-quarter reaction history · vol-crush risk</span><span class="tag">EODHD + OPTIONS</span></div>
      <div class="qov-er-head" id="qovErHead"></div>
      <div class="qov-er-mid" id="qovErMid"></div>
      <table class="qov-er-tbl"><thead><tr><th>QUARTER</th><th>EPS ACT / EST</th><th>SURPRISE</th><th>REV ACT / EST</th><th>GAP %</th><th>+5d DRIFT</th><th>NOTE</th></tr></thead><tbody id="qovErTbody"></tbody></table>
      <div class="qov-banner info" id="qovErStatsBanner" style="margin:11px 0 0">—</div>
    </div>

    <div class="qov-panel" id="qovMyPosPanel" style="display:none">
      <div class="qov-h2"><span class="num">C·d</span>My Position<span class="sub">— cost basis · P&amp;L · days held · cap usage</span><span class="tag">PORTFOLIO</span></div>
      <div class="qov-pos" id="qovPosGrid"></div>
      <div class="qov-pos-tax" id="qovPosTax">—</div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">C·e</span>Multi-Timeframe Alignment<span class="sub">— trend / momentum / volume across M · W · D · 4h · 1h</span><span class="tag">TECHNICALS</span></div>
      <table class="qov-mtf-tbl"><thead><tr><th>TIMEFRAME</th><th>TREND</th><th>MOMENTUM</th><th>VOLUME / RVOL</th><th>BIAS</th></tr></thead><tbody id="qovMtfBody"></tbody></table>
      <div class="qov-mtf-sum" id="qovMtfSummary">—</div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">D</span>Setup Quality Strip<span class="sub">— current state · price · levels · indicators · key gates</span><span class="tag">ELITE + ENGINE</span></div>
      <div class="qov-pq" id="qovPqGrid"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">E</span>Risk Profile<span class="sub">— stop · 1R · max loss · DD haircut · β-adjusted</span><span class="tag">ENGINE.sizing</span></div>
      <div class="qov-rp" id="qovRpGrid"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">F</span>News &amp; Catalyst Pulse<span class="sub">— 30-day news flow · sentiment · catalyst · insider</span><span class="tag">ELITE</span></div>
      <div class="qov-ns" id="qovNsGrid"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">G</span>Forward Outcomes<span class="sub">— probability blend · hold window estimates</span><span class="tag">ENGINE.p_reach</span></div>
      <div class="qov-fo" id="qovFoGrid"></div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">H</span>Pre-Flight Checklist<span class="sub">— engine gates · warnings · final approval</span><span class="tag">ENGINE.gates</span></div>
      <div class="qov-pf" id="qovPfGrid"></div>
      <div class="qov-banner info" id="qovPfBanner" style="margin:11px 0 0">—</div>
    </div>

    <div class="qov-panel">
      <div class="qov-h2"><span class="num">I</span>Action Triggers · Conditional Rules Per Lens<span class="sub">— specific IF / THEN rules · mechanical execution (CLAUDE principle 8)</span><span class="tag">RULES ENGINE</span></div>
      <div class="qov-trig" id="qovTrigGrid"></div>
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

  const dec = String(T.decision?.verdict || T.verdict || '').toLowerCase();
  const score = num(T.score, 0);
  let vLabel = 'WATCH', vCls = 'watch';
  if (/buy/.test(dec) || score >= 75) { vLabel = 'BUY'; vCls = 'buy'; }
  else if (/avoid|kill|reject|short|exit/.test(dec) || score < 55) { vLabel = 'AVOID'; vCls = 'avoid'; }
  $('qovSysVerdict').className = 'qov-vd ' + vCls;
  setText('qovSysVerdict', vLabel);
  const conv = T.conviction_tier ?? T.conviction?.label ?? '—';
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
    return `<div class="qov-h ${h.cls}"><div class="lbl">${lbl}</div><div class="val">${h.val}</div></div>`;
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
    else if (t1) reason = `Engine T1 ${escapeHtml(t1.behavior || '')} @ ${fmtPx(t1.price)} · ${escapeHtml(t1.action || '')} · R-mult ${fmtR(t1.r_multiple)}.`;
    else reason = 'No structural T1 found.';
    const tgts = t1
      ? `<b>T1</b> ${fmtPx(t1.price)} (conf ${(t1.confluence||0).toFixed(1)} · ${escapeHtml(t1.behavior||'')})${t2 ? ` · <b>T2</b> ${fmtPx(t2.price)} (conf ${(t2.confluence||0).toFixed(1)} · ${escapeHtml(t2.behavior||'')})` : ''}<br><b>Stop</b> ${fmtPx(p?.stop?.price)} · <b>P(reach)</b> ${t1.p_reach != null ? Math.round(t1.p_reach*100)+'%' : '—'}`
      : '<span style="color:var(--qink-3)">no targets</span>';
    return `<div class="qov-fc ${m.cls}${isBest ? ' best' : ''}">${isBest ? '<div class="qov-best-badge">★ BEST FIT</div>' : ''}<div class="qov-fc-mode">${m.label}</div><div class="qov-fc-hold">${m.hold}</div><div class="qov-fc-verdict ${v.cls}">${v.label}</div><div class="qov-fc-reason">${reason}</div><div class="qov-fc-tgts">${tgts}</div></div>`;
  }).join('');
  setHTML('qovFitGrid', html);
  const bestMode = bestIdx >= 0 ? modes[bestIdx].label : '—';
  setHTML('qovSysRec', `★ <b>SYSTEM RECOMMENDATION:</b> For ${ticker} today, <b>${bestMode}</b> is the best-fit lens (highest confluence × P(reach) × R composite).`);
}

function renderDecisionMatrix() {
  const T = _T() || {};
  const { payloads, ticker } = STATE;
  const pPos = payloads.POSITION;
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
  const { payloads } = STATE;
  const p = payloads.POSITION || payloads.SWING || payloads.INVESTMENT;
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
  rows.push({ lbl:'entry', name:`ENTRY · ${fmtPx(price)}`, fill:48, color:'rgba(230,234,242,', pct:0 });
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
      <div class="qov-et-row"><div class="qov-et-row-k">BEHAVIOR</div><div class="qov-et-row-v"><span class="qov-et-pill ${bh}">${escapeHtml(t.behavior || '—')}</span></div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">CONFLUENCE</div><div class="qov-et-row-v">${(t.confluence||0).toFixed(1)} from ${(t.sources||[]).length} sources</div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">P(REACH)</div><div class="qov-et-row-v">${t.p_reach != null ? Math.round(t.p_reach*100)+'%' : '—'} · Bayes ${ps.bayes != null ? Math.round(ps.bayes*100)+'%' : '—'} / MC ${ps.mc != null ? Math.round(ps.mc*100)+'%' : '—'} / analog ${ps.analog != null ? Math.round(ps.analog*100)+'%' : '—'}</div></div>
      <div class="qov-et-row"><div class="qov-et-row-k">ACTION</div><div class="qov-et-row-v">${escapeHtml(t.action || '—')}</div></div>
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
    { k:'REVERSE DCF', v:'—', sub:'requires DCF model · pending Phase 2', cls:'' },
    { k:'OWNER EARN YIELD', v:'—', sub:'requires FCF + buybacks · pending', cls:'' },
    { k:'INTRINSIC VALUE', v: pt ? fmtPx(pt) : '—', sub: pt ? `analyst PT · <b style="color:${mos > 0 ? 'var(--gn)' : 'var(--rd)'}">MoS ${mos.toFixed(1)}%</b>` : 'no analyst consensus', cls: mos > 10 ? 'gn' : mos > 0 ? 'am' : '' },
    { k:'QUALITY (PIO/Z/M)', v:'—', sub:'Piotroski/Altman/Beneish · pending', cls:'' },
    { k:'EARN YIELD vs 10Y', v:'—', sub:'requires forward earnings', cls:'' },
    { k:'MOAT', v:'—', sub:'qualitative · pending peer benchmarking', cls:'' },
  ];
  setHTML('qovValGrid', cells.map(c => `<div class="qov-v ${c.cls}"><div class="qov-v-k">${c.k}</div><div class="qov-v-v ${c.cls}">${c.v}</div><div class="qov-v-sub">${c.sub}</div></div>`).join(''));
  setHTML('qovBuffett', `<div class="q">★ The 10-year test · if markets closed for a decade, would you own this?</div><div class="a"><b style="color:var(--am)">Requires fundamental judgment</b> — moat, capital allocation, reinvestment ROIIC, management not yet automated. Engine has: sector ${escapeHtml(T.sector || '—')}, industry ${escapeHtml(T.industry || '—')}, score ${T.score || '—'}. Full Buffett-test computation arrives in Phase 2 (intrinsic value module).</div>`);
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
  const panel = $('qovMyPosPanel');
  if (!pf) { if (panel) panel.style.display = 'none'; return; }
  if (panel) panel.style.display = '';
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
    { tf:'MONTHLY', trend:'neut', trendNote:'monthly bars not yet plumbed', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias:'—', biasCls:'am' },
    { tf:'WEEKLY',  trend: T.weekly_bull ? 'bull' : 'neut', trendNote: T.weekly_bull ? 'Weekly trend bullish' : 'Weekly trend not confirmed', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias: T.weekly_bull ? 'BULL' : 'NEUT', biasCls: T.weekly_bull ? 'gn' : 'am' },
    { tf:'DAILY',   ...daily, biasCls: daily.bias === 'BULL' ? 'gn' : daily.bias === 'BEAR' ? 'rd' : 'am' },
    { tf:'4 HOUR',  trend:'neut', trendNote:'4h bars not yet plumbed', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias:'—', biasCls:'am' },
    { tf:'1 HOUR',  trend:'neut', trendNote:'1h bars not yet plumbed', mom:'neut', momNote:'—', vol:'neut', volNote:'—', bias:'—', biasCls:'am' },
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
  setHTML('qovMtfSummary', `<b style="color:${col}">Bias:</b> ${bulls} bullish · ${bears} bearish · ${rows.length-bulls-bears} neutral. <b style="color:var(--am)">Only daily timeframe is plumbed today</b> — weekly/4h/1h require OHLCV multi-resolution wiring (Phase 2).`);
}

function renderSetupStrip() {
  const T = _T() || {};
  const { payloads } = STATE;
  const p = payloads.POSITION || payloads.SWING || payloads.INVESTMENT;
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
  const p = STATE.payloads.POSITION || STATE.payloads.SWING || STATE.payloads.INVESTMENT;
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
  const p = STATE.payloads.POSITION || STATE.payloads.SWING || STATE.payloads.INVESTMENT;
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
      <div style="font:700 9.5px var(--qmono); color:var(--qink-3); letter-spacing:.13em; margin-bottom:8px">PROBABILITY · POSITION lens</div>
      ${bar('P(REACH T1)', pT1, 'var(--gn)')}
      ${bar('P(REACH T2)', pT2, 'var(--am)')}
      ${bar('P(STOP HIT)', pStop, 'var(--rd)')}
      ${bar('P(FLAT)',     pFlat, 'var(--qink-3)')}
    </div>
    <div>
      <div style="font:700 9.5px var(--qmono); color:var(--qink-3); letter-spacing:.13em; margin-bottom:8px">HOLD WINDOW</div>
      <div class="qov-fo-grid">
        <div>
          <div class="qov-fo-cell"><div class="k">SETUP FAMILY</div><div class="v">${escapeHtml(T.setup_family || T.setup || '—')}</div></div>
          <div class="qov-fo-cell"><div class="k">REGIME</div><div class="v" style="color:var(--am)">${escapeHtml(T.regime || '—')}</div></div>
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
  const p = STATE.payloads.POSITION || STATE.payloads.SWING || STATE.payloads.INVESTMENT;
  const warns = p?.warnings || [];
  const items = [];
  items.push({ pass: T.market_cap >= 1e9, k:'Liquidity gate · ' + (T.market_cap ? '$'+(T.market_cap/1e9).toFixed(1)+'B mcap' : '—') });
  items.push({ pass: T.earn_days == null || T.earn_days > 7, warn: T.earn_days != null && T.earn_days <= 7, k:'Earnings blackout · ' + (T.earn_days != null ? '+'+T.earn_days+'d' : 'no schedule') });
  items.push({ pass: T.regime && !/panic|risk_off/i.test(T.regime), k:'Regime allow · ' + (T.regime || '—') });
  items.push({ pass: T.entry_quality && /FRESH|PULLBACK|VALID/.test(T.entry_quality), warn: T.entry_quality === 'EXTENDED', k:'Entry quality · ' + (T.entry_quality || '—') });
  items.push({ pass: (p?.t1?.r_multiple || 0) >= 3, warn: (p?.t1?.r_multiple || 0) >= 2 && (p?.t1?.r_multiple || 0) < 3, k:'R:R ≥ 3.0 · actual ' + ((p?.t1?.r_multiple || 0).toFixed(2)) });
  items.push({ pass: T.score >= 70, warn: T.score >= 55 && T.score < 70, k:'Score band ≥ 70 · actual ' + (T.score || '—') });
  items.push({ pass: !warns.some(w=>/choch/i.test(w)), warn: warns.some(w=>/choch/i.test(w)), k:'CHoCH check · ' + (warns.some(w=>/choch/i.test(w)) ? 'warning' : 'clear') });
  items.push({ pass: T._setup_wilson_lb >= 0.5, warn: T._setup_wilson_lb >= 0.35 && T._setup_wilson_lb < 0.5, k:'Wilson LB ≥ 50% · ' + (T._setup_wilson_lb != null ? (T._setup_wilson_lb*100).toFixed(0)+'%' : '—') });
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
    if (!p || p.decision === 'reject') {
      return `<div class="qov-trig-card ${cls}"><div class="qov-trig-mode ${modeCls}">${modeUi} · NO TRADE</div><div style="padding:8px 0; color:var(--qink-3); font:500 11px var(--qmono)">Engine cannot generate ${modeUi} targets.</div></div>`;
    }
    const t1 = p.t1 || {}, t2 = p.t2 || {}, stopP = p.stop?.price;
    const rules = [];
    rules.push({ lbl:'EXIT TRIGGER (failsafe)', body:`<span class="when">IF intraday tick &lt; ${fmtPx(stopP)}</span> → <span class="neg">SELL FULL · close-based stop</span>` });
    if (t1.price) rules.push({ lbl:'T1 TRIGGER · trim', body:`<span class="when">IF price tags ${fmtPx(t1.price)} (T1)</span> → <span class="then">${escapeHtml(t1.action || 'trim 33%')} · trail remainder</span>` });
    if (t2.price) rules.push({ lbl:'T2 TRIGGER · scale', body:`<span class="when">IF price tags ${fmtPx(t2.price)} (T2)</span> → <span class="then">${escapeHtml(t2.action || 'scale 50%')} · trail balance</span>` });
    if (modeUi === 'POSITION' && T.above_50ema === false) {
      rules.push({ lbl:'ADD TRIGGER', body:`<span class="when">IF price tags primary zone</span> <span class="and">AND</span> <span class="when">1h closes green</span> <span class="and">AND</span> <span class="when">RSI &gt; 35</span> → <span class="then">ADD 1/3 size · raise stop</span>` });
    }
    if (modeUi === 'INVESTMENT' && T.analyst_target) {
      rules.push({ lbl:'ADD TRIGGER (value)', body:`<span class="when">IF price &lt; ${fmtPx(T.analyst_target * 0.85)} (MoS &gt; 15%)</span> → <span class="then">ADD on weakness · hold to IV ${fmtPx(T.analyst_target)}</span>` });
    }
    rules.push({ lbl:'INVALIDATION', body:`<span class="when">IF daily close &lt; ${fmtPx(stopP)}</span> <span class="and">OR</span> <span class="when">score drops &lt; 60</span> → <span class="neg">EXIT FULL · thesis broken</span>` });
    return `<div class="qov-trig-card ${cls}"><div class="qov-trig-mode ${modeCls}">${modeUi} · ${(p.decision || 'TRADE').toUpperCase()}</div>${rules.map(r => `<div class="qov-trig-rule"><div class="label">${r.lbl}</div><div class="ruleBody">${r.body}</div></div>`).join('')}</div>`;
  }
  setHTML('qovTrigGrid',
    buildCard('SWING', 'swing', 'am', payloads.SWING) +
    buildCard('POSITION', 'position', 'blue', payloads.POSITION) +
    buildCard('INVESTMENT', 'investment', 'lead', payloads.INVESTMENT));
}

function renderAll() {
  renderVerdictStrip();
  renderStrategyFit();
  renderDecisionMatrix();
  renderEngineTargets();
  renderIntrinsicValue();
  renderEarningsCard();
  renderMyPosition();
  renderMTF();
  renderSetupStrip();
  renderRiskProfile();
  renderNewsPulse();
  renderForwardOutcomes();
  renderPreFlight();
  renderActionTriggers();
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
}
