// surface-desks.jsx — Screener Desks: 11 trader-archetype books, regime-aware.
// Reads /api/screener_desks (built by screener_desks.py from the real scan bundle +
// per-setup Wilson edge + Schwab live overlay). Display layer — no scoring here.
(function () {
  const CSS = `
  .dk-wrap{
    --dk-mom:var(--amb);--dk-bo:var(--rd);--dk-pb:var(--cy);--dk-qf:var(--blue);--dk-cat:var(--violet);
    --dk-mr:var(--blue);--dk-def:var(--ink-3);--dk-short:var(--rd);--dk-val:var(--copper);--dk-smart:var(--violet);--dk-qual:var(--gn);
    --dk-good:var(--gn);--dk-warn:var(--amb);--dk-bad:var(--rd);--dk-gold:var(--amb);
    --dk-line:var(--line);--dk-panel:var(--bg-1);--dk-panel2:var(--bg-2);--dk-txt:var(--ink);--dk-dim:var(--ink-2);--dk-faint:var(--ink-3);
    padding:6px 4px 40px;color:var(--dk-txt);font-size:13px}
  .dk-wrap .mono{font-family:'SF Mono',ui-monospace,Menlo,monospace}
  .dk-regime{display:flex;gap:10px;align-items:center;background:var(--dk-panel);
    border:1px solid var(--dk-line);border-radius:12px;padding:11px 15px;margin:2px 0 12px;flex-wrap:wrap}
  .dk-regime .tag{font-weight:700;letter-spacing:.5px;color:var(--dk-warn)}
  .dk-regime .chip{background:var(--bg-2);border:1px solid var(--dk-line);border-radius:20px;padding:3px 11px;color:var(--dk-dim);font-size:11.5px}
  .dk-regime .verdict{margin-left:auto;color:var(--dk-dim);font-size:11.5px;max-width:440px}
  .dk-hz{display:inline-flex;background:var(--bg-2);border:1px solid var(--dk-line);border-radius:10px;padding:4px;gap:4px;margin-bottom:14px}
  .dk-hz button{background:none;border:0;color:var(--dk-dim);font:600 12.5px/1 inherit;padding:8px 15px;border-radius:7px;cursor:pointer}
  .dk-hz button.on{background:var(--bg-3);color:var(--dk-txt);box-shadow:inset 0 0 0 1px var(--line-2)}
  .dk-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:11px}
  @media(max-width:1250px){.dk-grid{grid-template-columns:repeat(3,1fr)}}
  @media(max-width:960px){.dk-grid{grid-template-columns:repeat(2,1fr)}}
  .dk-col{background:var(--dk-panel);border:1px solid var(--dk-line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
  .dk-col.lead{box-shadow:0 0 0 1px var(--dk-good),0 8px 30px -14px var(--gn-bg)}
  .dk-col.dorm{opacity:.5}
  .dk-chead{padding:12px 13px 10px;border-bottom:1px solid var(--dk-line);background:var(--dk-panel2)}
  .dk-chead .ttl{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:800}
  .dk-dot{width:9px;height:9px;border-radius:50%}
  .dk-chead .who{color:var(--dk-dim);font-size:10.5px;margin-top:4px}
  .dk-sp{float:right;font-size:9px;font-weight:800;letter-spacing:.5px;border-radius:20px;padding:2px 8px}
  .dk-sp.lead{color:var(--dk-good);background:var(--gn-bg);border:1px solid transparent}
  .dk-sp.act{color:var(--dk-dim);border:1px solid var(--dk-line)}
  .dk-sp.dorm{color:var(--dk-faint);border:1px solid var(--dk-line)}
  .dk-edge{margin-top:8px;font-family:'SF Mono',monospace;font-size:10px;border-radius:7px;padding:5px 7px;line-height:1.35}
  .dk-edge.e-good{color:var(--dk-good);background:var(--gn-bg);border:1px solid transparent}
  .dk-edge.e-mid{color:var(--dk-warn);background:var(--amb-bg);border:1px solid transparent}
  .dk-edge.e-bad{color:var(--dk-bad);background:var(--rd-bg);border:1px solid transparent}
  .dk-edge.e-unp{color:var(--dk-faint);background:var(--bg-2);border:1px solid var(--dk-line)}
  .dk-cards{padding:7px;display:flex;flex-direction:column;gap:6px}
  .dk-card{background:var(--dk-panel2);border:1px solid var(--dk-line);border-radius:9px;padding:8px 9px;cursor:pointer}
  .dk-card:hover{border-color:var(--line-2)}
  .dk-card.conf{box-shadow:inset 2px 0 0 var(--dk-gold)}
  .dk-top{display:flex;align-items:baseline;gap:6px}
  .dk-rk{font-family:'SF Mono',monospace;font-size:10.5px;color:var(--dk-faint);width:14px}
  .dk-sym{font-weight:800;font-size:13.5px}
  .dk-vc{font-size:9px;font-weight:800;letter-spacing:.3px;border-radius:5px;padding:1px 5px;margin-left:4px}
  .dk-vc.buy{color:var(--bg-0);background:var(--dk-good)}
  .dk-vc.watch{color:var(--dk-warn);background:var(--amb-bg)}
  .dk-vc.avoid{color:var(--dk-faint);border:1px solid var(--dk-line)}
  .dk-vc.pass{color:var(--dk-faint);border:1px dashed var(--dk-line)}
  .dk-vc.short{color:var(--bg-0);background:var(--dk-bad)}
  .dk-acc{font-family:'SF Mono',monospace;font-size:9px;font-weight:800;color:var(--dk-gold);background:var(--amb-bg);border:1px solid transparent;border-radius:5px;padding:0 4px;margin-left:3px}
  .dk-live{font-size:8px;color:var(--dk-good);margin-left:3px}
  .dk-px{margin-left:auto;font-family:'SF Mono',monospace;color:var(--dk-dim);font-size:11.5px}
  .dk-px .up{color:var(--dk-good)}.dk-px .dn{color:var(--dk-bad)}
  .dk-sect{color:var(--dk-faint);font-size:10px;margin:2px 0 5px 20px}
  .dk-hl{margin-left:20px;font-family:'SF Mono',monospace;font-size:11px}.dk-hl .kv{color:var(--dk-dim)}
  .dk-pill{display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:5px}
  .dk-p-zone{color:var(--bg-0);background:var(--dk-good)}.dk-p-appr{color:var(--dk-good);border:1px solid var(--dk-good)}
  .dk-p-ext{color:var(--dk-warn);border:1px solid var(--dk-warn)}.dk-p-fire{color:var(--bg-0);background:var(--dk-warn)}
  .dk-fchips{margin:4px 0 1px 20px;font-family:'SF Mono',monospace;font-size:10.5px;display:flex;flex-wrap:wrap;gap:2px 9px}
  .dk-fchips .fl{color:var(--dk-faint);font-size:9px}
  .dk-plan{margin:5px 0 0 20px;font-family:'SF Mono',monospace;font-size:10px;color:var(--dk-faint)}.dk-plan b{color:var(--dk-pb)}
  .dk-empty{color:var(--dk-faint);font-size:10.5px;padding:14px 10px;text-align:center;font-style:italic}
  .dk-foot{color:var(--dk-faint);font-size:11px;margin-top:18px;border-top:1px solid var(--dk-line);padding-top:11px;max-width:960px}
  .dk-load{color:var(--dk-dim);padding:40px;text-align:center}
  .dk-src{display:inline-block;font-family:'SF Mono',monospace;font-size:10px;font-weight:800;letter-spacing:.5px;color:var(--dk-gold);background:var(--amb-bg);border:1px solid transparent;border-radius:6px;padding:3px 10px;margin:0 0 8px}
  .dk-fresh{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-family:'SF Mono',monospace;font-size:10.5px;color:var(--dk-faint);margin:0 0 10px}
  .dk-fresh .f{color:var(--dk-dim)}
  .dk-fresh b{color:var(--dk-txt);font-weight:700}
  .dk-fresh .dot{width:6px;height:6px;border-radius:50%;background:var(--dk-good);display:inline-block;margin-right:4px}
  .dk-fresh .stale{background:var(--dk-warn)}
  .dk-fresh button{background:var(--bg-2);border:1px solid var(--dk-line);border-radius:7px;color:var(--dk-dim);cursor:pointer;font:inherit;font-size:10.5px;padding:3px 9px}
  .dk-fresh button:hover{color:var(--dk-txt);border-color:var(--line-2)}
  .dk-fresh .cad{color:var(--dk-faint)}
  .dk-ctrls{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
  .dk-ctrls input{background:var(--bg-2);border:1px solid var(--dk-line);border-radius:8px;color:var(--dk-txt);padding:6px 10px;font:inherit;font-size:12px;width:150px}
  .dk-ctrls input.px{width:62px}
  .dk-ctrls select{background:var(--bg-2);border:1px solid var(--dk-line);border-radius:8px;color:var(--dk-txt);padding:6px 8px;font:inherit;font-size:12px}
  .dk-ctrls .tg{cursor:pointer;border:1px solid var(--dk-line);border-radius:8px;padding:6px 11px;font-size:12px;color:var(--dk-dim);background:none}
  .dk-ctrls .tg.on{background:var(--gn-bg);color:var(--dk-good);border-color:transparent}
  .dk-ctrls .lbl{font-size:11px;color:var(--dk-faint)}
  .dk-best{background:var(--dk-panel);border:1px solid var(--dk-line);border-radius:12px;padding:10px 12px;margin-bottom:12px}
  .dk-best .bh{font-size:11px;font-weight:800;letter-spacing:.5px;color:var(--dk-gold);margin-bottom:8px}
  .dk-best .brow{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px}
  .dk-bi{flex:0 0 auto;background:var(--dk-panel2);border:1px solid var(--dk-line);border-radius:9px;padding:7px 10px;cursor:pointer;min-width:148px}
  .dk-bi:hover{border-color:var(--line-2)}
  .dk-bi .s{font-weight:800;font-size:13px}
  .dk-bi .px{font-family:'SF Mono',monospace;font-size:11px;color:var(--dk-dim);margin-left:6px}
  .dk-bi .d{font-size:9.5px;color:var(--dk-dim);margin-top:3px}
  .dk-cnt{font-size:9px;color:var(--dk-faint);font-family:'SF Mono',monospace;margin-top:6px}
  .dk-conc{font-size:9px;color:var(--dk-warn);font-family:'SF Mono',monospace;margin-top:3px}
  .dk-livetr{font-size:9px;font-family:'SF Mono',monospace;margin-top:4px;color:var(--dk-good)}
  .dk-livetr.neg{color:var(--dk-bad)}
  .dk-tkt{margin:6px 0 0 20px;font-family:'SF Mono',monospace;font-size:10px;display:flex;flex-direction:column;gap:4px;
    border-top:1px dashed var(--dk-line);padding-top:5px}
  .dk-tkt .ev{color:var(--dk-good)}
  .dk-tkt .chips{display:flex;flex-wrap:wrap;gap:4px}
  .dk-tkt .c{font-size:8.5px;border:1px solid var(--dk-line);border-radius:5px;padding:1px 5px;color:var(--dk-faint)}
  .dk-tkt .c.warn{color:var(--dk-warn);border-color:var(--dk-warn)}
  .dk-tkt .c.bad{color:var(--dk-bad);border-color:var(--dk-bad)}
  `;

  function ensureStyle() {
    if (document.getElementById("dk-style")) return;
    const s = document.createElement("style");
    s.id = "dk-style"; s.textContent = CSS;
    document.head.appendChild(s);
  }

  const REGIME_NOTE = {
    risk_on_choppy: "Choppy + distributive tape favors Quant-Factor & Swing-Pullback (quality + location). Pure Momentum / Breakout demoted.",
    neutral: "Choppy / neutral tape — quality + location lead; momentum secondary.",
    risk_on_trending: "Clean uptrend — Momentum · Breakout · Pullback lead. Mean-Rev & Defensive sit out.",
    bull: "Bullish trend — Momentum · Breakout · Pullback lead.",
    risk_off_trending: "Risk-off — Defensive · Quality · Short lead. Momentum/Breakout dormant.",
    panic: "Panic — Defensive & Short only. No new momentum longs.",
  };

  function n(x) { return (x === null || x === undefined || isNaN(x)) ? null : +x; }

  function agoStr(ts) {
    if (!ts) return null;
    let ms = Date.parse(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(ts) ? ts.replace(" ", "T") : ts);
    if (isNaN(ms)) return null;
    const s = Math.max(0, Math.floor((Date.now() - ms) / 1000));
    if (s < 90) return s + "s ago";
    if (s < 5400) return Math.round(s / 60) + "m ago";
    if (s < 172800) return Math.round(s / 3600) + "h ago";
    return Math.round(s / 86400) + "d ago";
  }

  function pill(r) {
    const s = r._livestate || r.state, e = r.eq;
    if (s === "AT_ZONE" || e === "FRESH") return React.createElement("span", { className: "dk-pill dk-p-zone" }, "AT ZONE");
    if (s === "APPROACHING") return React.createElement("span", { className: "dk-pill dk-p-appr" }, "APPROACHING");
    if (n(r.rvol) >= 1.5) return React.createElement("span", { className: "dk-pill dk-p-fire" }, "FIRING " + (+r.rvol).toFixed(1));
    if (s === "EXTENDED" || s === "MISSED" || e === "EXTENDED" || e === "MISSED") return React.createElement("span", { className: "dk-pill dk-p-ext" }, "EXTENDED");
    return null;
  }

  function priceCell(r) {
    const px = n(r.price);
    const chg = n(r._chg);
    const kids = [px != null ? "$" + px.toFixed(2) : "—"];
    if (chg != null) kids.push(React.createElement("span", { className: chg >= 0 ? "up" : "dn", key: "c" }, " " + (chg >= 0 ? "+" : "") + chg.toFixed(1) + "%"));
    return React.createElement("span", { className: "dk-px" }, kids);
  }

  function mid(r, ck) {
    const kv = (t) => React.createElement("span", { className: "kv" }, t);
    const H = (children) => React.createElement("div", { className: "dk-hl" }, children);
    if (ck === "mom") return H([React.createElement("b", { key: 1 }, "RS " + (r.rs ?? "—")), " ", kv("Sharpe"), " " + (r.sharpe != null ? (+r.sharpe).toFixed(1) : "—") + " ", kv("sc"), " " + (r.score ?? "—")]);
    if (ck === "bo") return H([pill(r) || kv("coiled"), " ", kv("ATR"), " " + (r.atr != null ? (+r.atr).toFixed(1) + "%" : "—") + " ", kv("trig"), " " + (r.entry_hi != null ? "$" + (+r.entry_hi).toFixed(2) : "—")]);
    if (ck === "pb") return H([pill(r), " ", kv("R:R"), " " + (r._rr ?? "—") + " ", kv("RS"), " " + (r.rs ?? "—")]);
    if (ck === "cat") return H([r._pcr != null ? React.createElement("span", { className: "dk-pill dk-p-fire", key: 1 }, "UOA P/C " + (+r._pcr).toFixed(2)) : React.createElement("span", { className: "dk-pill dk-p-appr", key: 1 }, "T" + (r.cat || "?")), " ", kv("RS"), " " + (r.rs ?? "—")]);
    if (ck === "mr") return H([React.createElement("b", { key: 1, style: { color: "var(--dk-mr)" } }, "RSI " + (r.rsi != null ? (+r.rsi).toFixed(0) : "—")), " ", kv("oversold · sc"), " " + (r.score ?? "—")]);
    if (ck === "val") return H([React.createElement("b", { key: 1, style: { color: "var(--dk-val)" } }, "VAL " + Math.round(r._val || 0)), " ", kv("fwd P/E"), " " + (r.fwd_pe != null ? (+r.fwd_pe).toFixed(1) : "—") + " ", kv("P/S"), " " + (r.ps != null ? (+r.ps).toFixed(1) : "—")]);
    if (ck === "qual") return H([React.createElement("b", { key: 1, style: { color: "var(--dk-qual)" } }, "Q " + Math.round(r._qc || 0)), " ", kv("ROE"), " " + (r.roe != null ? (+r.roe).toFixed(0) + "%" : "—") + " ", kv("GM"), " " + (r.gm != null ? (+r.gm).toFixed(0) + "%" : "—")]);
    if (ck === "smart") return H([React.createElement("span", { className: "dk-pill dk-p-appr", key: 1 }, "INSIDER/CONGRESS"), " ", kv("RS"), " " + (r.rs ?? "—")]);
    if (ck === "short") return H([React.createElement("span", { className: "dk-pill dk-p-ext", key: 1 }, String(r._bear || "breakdown")), " ", kv("RS"), " " + (r.rs ?? "—") + " ", kv("RSI"), " " + (r.rsi != null ? (+r.rsi).toFixed(0) : "—")]);
    if (ck === "def") return H([kv("defensive · beta≤1 · RS"), " " + (r.rs ?? "—")]);
    // qf — factor chips
    const chip = (l, v, c) => React.createElement("span", { key: l }, React.createElement("span", { className: "fl", style: { color: c } }, l), " " + Math.round(v || 0));
    return React.createElement("div", { className: "dk-fchips" }, [
      chip("MOM", r._mom, "var(--dk-mom)"), chip("QUAL", r._qual, "var(--dk-good)"),
      chip("TRND", r._trend, "var(--dk-qf)"), chip("VAL", r._val != null ? r._val : 50, "var(--dk-val)"),
      chip("CAT", r._cat, "var(--dk-warn)")]);
  }

  function verdictChip(r, ck) {
    const vd = String(r._dv || "").toUpperCase();  // this desk's OWN verdict, not the scanner's
    if (!vd) return null;
    const cls = vd === "BUY" ? "buy" : vd === "WATCH" ? "watch" : vd === "SHORT" ? "short"
      : vd === "PASS" ? "pass" : "avoid";
    const why = r._why ? r._why + "  —  click card for the full deep-dive" : "This desk's own call from raw signals";
    return React.createElement("span", { className: "dk-vc " + cls, key: "vc", title: why }, vd);
  }

  function fmtUsd(v) {
    if (v == null) return "—";
    if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B";
    if (v >= 1e6) return "$" + Math.round(v / 1e6) + "M";
    return "$" + Math.round(v / 1e3) + "K";
  }

  function ticket(r) {
    const t = r._tkt;
    if (!t) return null;
    const line = "P " + Math.round((t.p || 0) * 100) + "% · E[R] " + ((t.ev >= 0 ? "+" : "") + t.ev)
      + (t.size ? " · size " + t.size + "% (risk " + t.risk + "%)" : "") + (t.measured ? "" : " · edge est");
    const chips = [];
    if (t.adv != null) chips.push(["$ADV " + fmtUsd(t.adv) + (t.thin ? " ⚠thin" : ""), t.thin ? "warn" : ""]);
    if (t.ear_days != null && t.ear_days >= 0 && t.ear_days <= 10) chips.push(["⚠ earnings " + t.ear_days + "d", "bad"]);
    else if (t.ear_days != null && t.ear_days >= 0) chips.push(["earnings " + t.ear_days + "d", ""]);
    if (t.short_float != null && +t.short_float >= 10) chips.push(["short " + (+t.short_float).toFixed(0) + "% ⚠squeeze", "warn"]);
    if (t.beta != null) chips.push(["β " + (+t.beta).toFixed(2), ""]);
    return React.createElement("div", { className: "dk-tkt", key: "tkt" }, [
      React.createElement("div", { className: "ev", key: "l" }, line),
      chips.length ? React.createElement("div", { className: "chips", key: "c" },
        chips.map((c, i) => React.createElement("span", { className: "c " + c[1], key: i }, c[0]))) : null,
    ]);
  }

  function Card({ r, i, ck, onTicker, maxSize }) {
    const conf = (r._across || 1) >= 2;
    const kids = [
      React.createElement("div", { className: "dk-top", key: "t" }, [
        React.createElement("span", { className: "dk-rk", key: "r" }, i + 1),
        React.createElement("span", { className: "dk-sym", key: "s" }, r.t),
        verdictChip(r, ck),
        conf ? React.createElement("span", { className: "dk-acc", key: "a", title: "Across " + r._across + " desks: " + (r._acrosslbls || "") }, "⋈" + r._across) : null,
        r._livepx ? React.createElement("span", { className: "dk-live", key: "l", title: "live Schwab quote" }, "● LIVE") : null,
        priceCell(r),
      ]),
      React.createElement("div", { className: "dk-sect", key: "se" }, [r.sector, r.industry].filter(Boolean).join(" · ") || "—"),
      React.createElement("div", { key: "m" }, mid(r, ck)),
    ];
    if ((ck === "pb" || ck === "bo") && r.entry_lo != null && r.stop != null) {
      kids.push(React.createElement("div", { className: "dk-plan", key: "p" }, [
        "entry ", React.createElement("b", { key: "b" }, "$" + (+r.entry_lo).toFixed(2) + "–" + (+r.entry_hi).toFixed(2)),
        " · stop $" + (+r.stop).toFixed(2) + (r.t1 != null ? " · T1 $" + (+r.t1).toFixed(2) : "")]));
    }
    if (r._dv === "BUY" || r._dv === "SHORT") {
      const tk = ticket(r);
      if (tk) kids.push(tk);
    }
    return React.createElement("div", { className: "dk-card" + (conf ? " conf" : ""), onClick: () => r.t && onTicker && onTicker(r.t) }, kids);
  }

  function SurfaceDesks({ onTicker }) {
    ensureStyle();
    const [data, setData] = React.useState(null);
    const [hz, setHz] = React.useState("swing");
    const [err, setErr] = React.useState(null);
    const [q, setQ] = React.useState("");
    const [buyOnly, setBuyOnly] = React.useState(false);
    const [showOverflow, setShowOverflow] = React.useState(false);
    const [sortBy, setSortBy] = React.useState("rank");
    const [pMin, setPMin] = React.useState("");
    const [pMax, setPMax] = React.useState("");
    const [fetchedAt, setFetchedAt] = React.useState(0);
    const [, setTick] = React.useState(0);
    const load = React.useCallback(() => {
      const BV = window.__BV;
      if (BV && BV.get) {
        BV.get("/api/screener_desks").then((d) => { setData(d); setErr(null); setFetchedAt(Date.now()); }).catch((e) => setErr(String(e)));
      } else {
        setErr("boot adapter not ready");
      }
    }, []);
    React.useEffect(() => {
      load();
      const iv = setInterval(load, 90000);                       // auto re-pull every 90s
      const tk = setInterval(() => setTick((t) => t + 1), 5000); // tick the "ago" labels
      return () => { clearInterval(iv); clearInterval(tk); };
    }, [load]);

    if (err) return React.createElement("div", { className: "dk-wrap" }, React.createElement("div", { className: "dk-load" }, "Screener Desks unavailable: " + err));
    if (!data) return React.createElement("div", { className: "dk-wrap" }, React.createElement("div", { className: "dk-load" }, "Loading desks…"));

    const reg = data.regime || {};
    const note = REGIME_NOTE[reg.regime4] || "Regime decides which desks lead.";
    const pool = (data.horizons || {})[hz] || {};
    const books = pool.books || {};
    const best = pool.best || [];
    const maxSize = reg.max_size_pct || null;

    const qlc = q.trim().toUpperCase();
    const pmin = parseFloat(pMin), pmax = parseFloat(pMax);
    function prep(rows) {
      let out = (rows || []).slice();
      if (qlc) out = out.filter((r) => (r.t || "").toUpperCase().indexOf(qlc) >= 0);
      if (!isNaN(pmin)) out = out.filter((r) => r.price != null && +r.price >= pmin);
      if (!isNaN(pmax)) out = out.filter((r) => r.price != null && +r.price <= pmax);
      if (buyOnly) out = out.filter((r) => r._dv === "BUY" || r._dv === "SHORT");
      else if (!showOverflow) out = out.filter((r) => r._dv === "BUY" || r._dv === "WATCH" || r._dv === "SHORT");  // hide PASS/AVOID overflow
      if (sortBy === "rr") out.sort((a, b) => (+b._rr || 0) - (+a._rr || 0));
      else if (sortBy === "chg") out.sort((a, b) => (b._chg == null ? -999 : +b._chg) - (a._chg == null ? -999 : +a._chg));
      else if (sortBy === "conf") out.sort((a, b) => (b._across || 0) - (a._across || 0));
      return out;
    }

    const regimeStrip = React.createElement("div", { className: "dk-regime" }, [
      React.createElement("span", { className: "tag", key: "t" }, "REGIME · " + String(reg.regime4 || "—").toUpperCase().replace(/_/g, " ")),
      reg.vix != null ? React.createElement("span", { className: "chip", key: "v" }, "VIX " + (+reg.vix).toFixed(1)) : null,
      reg.breadth != null ? React.createElement("span", { className: "chip", key: "b" }, "Breadth " + (+reg.breadth).toFixed(0) + "%") : null,
      reg.distribution_days != null ? React.createElement("span", { className: "chip", key: "d", style: { color: "var(--dk-warn)" } }, reg.distribution_days + " distribution days") : null,
      maxSize != null ? React.createElement("span", { className: "chip", key: "ms" }, "max size " + maxSize + "%") : null,
      React.createElement("span", { className: "verdict", key: "n" }, [React.createElement("b", { key: "b", style: { color: "var(--dk-good)" } }, "Desks live today → "), note]),
    ]);

    const hzToggle = React.createElement("div", { className: "dk-hz" },
      [["swing", "SWING · 2–5 day"], ["position", "POSITION · 2–8 wk"], ["invest", "INVEST · 3–12 mo"]].map(([k, lbl]) =>
        React.createElement("button", { key: k, className: hz === k ? "on" : "", onClick: () => setHz(k) }, lbl)));

    const ctrls = React.createElement("div", { className: "dk-ctrls" }, [
      React.createElement("input", { key: "q", placeholder: "search ticker…", value: q, onChange: (e) => setQ(e.target.value) }),
      React.createElement("span", { className: "lbl", key: "pl" }, "$"),
      React.createElement("input", { key: "pmin", className: "px", type: "number", placeholder: "min", value: pMin, onChange: (e) => setPMin(e.target.value) }),
      React.createElement("span", { className: "lbl", key: "pd" }, "–"),
      React.createElement("input", { key: "pmax", className: "px", type: "number", placeholder: "max", value: pMax, onChange: (e) => setPMax(e.target.value) }),
      [["<$100", "", "100"], ["$100–250", "100", "250"], [">$250", "250", ""]].map(([lbl, mn, mx]) =>
        React.createElement("button", { key: lbl, className: "tg" + ((pMin === mn && pMax === mx) ? " on" : ""), onClick: () => { setPMin(mn); setPMax(mx); } }, lbl)),
      React.createElement("button", { key: "bo", className: "tg" + (buyOnly ? " on" : ""), onClick: () => setBuyOnly(!buyOnly) }, buyOnly ? "✓ BUY only" : "BUY only"),
      React.createElement("button", { key: "ov", className: "tg" + (showOverflow ? " on" : ""), onClick: () => setShowOverflow(!showOverflow), title: "also show names that rank high but don't clear the desk's buy bar" }, showOverflow ? "✓ show overflow" : "show overflow"),
      React.createElement("span", { className: "lbl", key: "sl" }, "sort"),
      React.createElement("select", { key: "s", value: sortBy, onChange: (e) => setSortBy(e.target.value) }, [
        React.createElement("option", { key: "rank", value: "rank" }, "desk rank"),
        React.createElement("option", { key: "rr", value: "rr" }, "R:R"),
        React.createElement("option", { key: "chg", value: "chg" }, "live %"),
        React.createElement("option", { key: "conf", value: "conf" }, "confluence"),
      ]),
    ]);

    const bestStrip = best.length ? React.createElement("div", { className: "dk-best" }, [
      React.createElement("div", { className: "bh", key: "h" }, "★ BEST IDEAS TODAY · desks that agree on a BUY (self-contained)"),
      React.createElement("div", { className: "brow", key: "r" }, best.map((b, i) =>
        React.createElement("div", { className: "dk-bi", key: b.t + i, onClick: () => onTicker && onTicker(b.t) }, [
          React.createElement("div", { key: "s" }, [
            React.createElement("span", { className: "s", key: "y" }, b.t),
            b.n >= 2 ? React.createElement("span", { className: "dk-acc", key: "x", title: b.desks.join(" · ") }, "⋈" + b.n) : null,
            b.price != null ? React.createElement("span", { className: "px", key: "p" }, "$" + (+b.price).toFixed(2) + (b.chg != null ? "  " + (b.chg >= 0 ? "+" : "") + (+b.chg).toFixed(1) + "%" : "")) : null,
          ]),
          React.createElement("div", { className: "d", key: "d" }, b.desks.join(" · ")),
        ]))),
    ]) : null;

    const cols = (data.desks || []).map((d) => {
      const bk = books[d.key] || { rows: [], n: 0 };
      const rows = prep(bk.rows);
      const dorm = d.state === "dorm";
      const spCls = d.state === "lead" ? "lead" : dorm ? "dorm" : "act";
      const spTxt = d.state === "lead" ? "LEADING" : dorm ? "DORMANT" : "ACTIVE";
      let body;
      if (!rows.length) {
        body = React.createElement("div", { className: "dk-empty" },
          (bk.rows && bk.rows.length) ? ("No BUY/WATCH today — " + bk.rows.length + " ranked. Toggle 'show overflow' to see them.")
            : dorm ? "Regime does not call for this desk today. Auto-arms when conditions flip."
              : (d.emptymsg || "No qualifying names today."));
      } else {
        body = rows.map((r, i) => React.createElement(Card, { key: r.t + i, r, i, ck: d.key, onTicker, maxSize }));
      }
      return React.createElement("div", { className: "dk-col " + (d.state === "lead" ? "lead" : dorm ? "dorm" : ""), key: d.key }, [
        React.createElement("div", { className: "dk-chead", key: "h" }, [
          React.createElement("span", { className: "dk-sp " + spCls, key: "sp" }, spTxt),
          React.createElement("div", { className: "dk-ttl", key: "t" }, [
            React.createElement("span", { className: "dk-dot", key: "d", style: { background: d.color } }),
            React.createElement("span", { key: "n" }, d.name)]),
          React.createElement("div", { className: "who", key: "w" }, d.who),
          React.createElement("div", { className: "dk-edge " + ((d.edge && d.edge.class) || "e-unp"), key: "e" }, (d.edge && d.edge.text) || ""),
          d.live ? React.createElement("div", { className: "dk-livetr" + ((d.live.er != null && d.live.er < 0) ? " neg" : ""), key: "lt", title: "forward outcomes of this desk's own live BUY calls" },
            "◉ LIVE · n=" + d.live.n + " · WR " + Math.round((d.live.wr || 0) * 100) + "% · PF " + (d.live.pf != null ? (+d.live.pf).toFixed(2) : "—") + " · E[R] " + ((d.live.er >= 0 ? "+" : "") + d.live.er)) : null,
          React.createElement("div", { className: "dk-cnt", key: "c" }, rows.length + " shown · " + bk.n + " scanned"),
          bk.conc ? React.createElement("div", { className: "dk-conc", key: "cc" }, "⚠ concentrated · " + bk.conc.n + " of " + bk.conc.of + " " + bk.conc.sector) : null,
        ]),
        React.createElement("div", { className: "dk-cards", key: "c" }, body),
      ]);
    });

    const fetchedAgo = fetchedAt ? Math.floor((Date.now() - fetchedAt) / 1000) : null;
    const liveAge = agoStr(data.live_at);
    const liveStale = (() => { const ms = data.live_at ? Date.parse(data.live_at) : 0; return ms ? (Date.now() - ms) > 20 * 60 * 1000 : true; })();
    const freshBar = React.createElement("div", { className: "dk-fresh" }, [
      React.createElement("span", { className: "f", key: "b" }, [
        React.createElement("span", { className: "dot" + (liveStale ? " stale" : ""), key: "d" }),
        "Ticker lists updated ", React.createElement("b", { key: "g" }, data.generated_at || "—")]),
      React.createElement("span", { className: "cad", key: "sch" }, "· desks re-rank 5×/day (5:15 · 7:00 · 9:30 · 11:30 · 13:30 PT) — names can change at each"),
      data.live_at
        ? React.createElement("span", { className: "f", key: "l" }, ["· Live prices ", React.createElement("b", { key: "la" }, liveAge || "—"), " (every 5 min)"])
        : React.createElement("span", { className: "f", key: "l" }, "· Live prices: off-hours (close-anchored)"),
      (data.live_track && data.live_track.n_resolved != null) ? React.createElement("span", { className: "cad", key: "lt" },
        "· desk track record: " + (data.live_track.n_resolved || 0) + " resolved / " + (data.live_track.n_open || 0) + " open (forward outcomes accruing daily)") : null,
      fetchedAgo != null ? React.createElement("span", { className: "cad", key: "p" }, "· tab auto-refreshes 90s (pulled " + (fetchedAgo < 90 ? fetchedAgo + "s" : Math.round(fetchedAgo / 60) + "m") + " ago)") : null,
      React.createElement("button", { key: "r", onClick: load }, "↻ refresh now"),
    ]);

    return React.createElement("div", { className: "dk-wrap" }, [
      React.createElement("div", { key: "src", className: "dk-src", title: "Every ticker + verdict on this tab is produced by the Screener Desk engine — not the signal scanner." },
        "◆ SOURCE · SCREENER DESK ENGINE — self-contained, independent of the signal scanner"),
      React.createElement("div", { key: "sub", style: { color: "var(--dk-dim)", fontSize: "12px", margin: "0 0 8px" } },
        "11 desks each decide BUY on their own raw-signal checklist over the FULL universe · hover a verdict for its why."),
      freshBar,
      regimeStrip, hzToggle, ctrls, bestStrip,
      React.createElement("div", { className: "dk-grid", key: "g" }, cols),
      React.createElement("div", { className: "dk-foot", key: "f" },
        "Each desk scans the whole universe and calls BUY/WATCH/PASS on its OWN criteria — never the old scanner's score or verdict. Regime sets LEADING/ACTIVE/DORMANT; confluence ⋈ is internal agreement only. Hover any verdict chip to see which conditions passed/failed."),
    ]);
  }

  window.SurfaceDesks = SurfaceDesks;
})();
