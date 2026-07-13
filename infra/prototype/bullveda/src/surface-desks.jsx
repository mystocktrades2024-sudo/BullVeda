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
  .dk-rb{font-size:8.5px;font-weight:800;letter-spacing:.2px;border-radius:5px;padding:1px 5px;margin-left:4px;cursor:help;white-space:nowrap}
  .dk-rb.real{color:var(--bg-0);background:var(--dk-good)}
  .dk-rb.marg{color:var(--dk-warn);background:var(--amb-bg);border:1px solid var(--dk-warn)}
  .dk-rb.unv{color:var(--dk-faint);border:1px dashed var(--dk-line)}
  .dk-rb.notreal{color:var(--dk-bad);border:1px solid var(--dk-bad)}
  .dk-dd .chk.warn{color:var(--dk-warn)}
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
  .dk-ddbtn{margin:6px 0 0 20px;font-size:9.5px;color:var(--dk-dim);background:none;border:1px solid var(--dk-line);border-radius:6px;padding:2px 8px;cursor:pointer;font-family:'SF Mono',monospace}
  .dk-ddbtn:hover{color:var(--dk-txt);border-color:var(--line-2)}
  .dk-dd{margin:7px 0 2px 20px;border-top:1px solid var(--dk-line);padding-top:7px;display:flex;flex-direction:column;gap:7px}
  .dk-dd .thesis{font-size:10px;color:var(--dk-dim);font-style:italic;line-height:1.4}
  .dk-dd .sh{font-size:8px;font-weight:800;letter-spacing:.6px;color:var(--dk-faint);margin-bottom:3px}
  .dk-dd .kv{display:flex;flex-wrap:wrap;gap:2px 14px;font-family:'SF Mono',monospace;font-size:9.5px;color:var(--dk-txt)}
  .dk-dd .kv .k{color:var(--dk-faint)}
  .dk-dd .chk{font-family:'SF Mono',monospace;font-size:9.5px;color:var(--dk-dim);margin-right:10px}
  .dk-dd .inval{font-family:'SF Mono',monospace;font-size:9.5px;color:var(--dk-warn)}
  /* ── master leaderboard table (top-of-page, all desks) ── */
  .dk-mt{background:var(--dk-panel);border:1px solid var(--dk-line);border-radius:12px;margin-bottom:12px;overflow:hidden}
  .dk-mt-h{display:flex;align-items:center;gap:10px;padding:10px 13px;cursor:pointer;user-select:none;background:var(--dk-panel2);border-bottom:1px solid var(--dk-line)}
  .dk-mt-h .cv{font-size:11px;color:var(--dk-faint)}
  .dk-mt-h .t{font-size:11px;font-weight:800;letter-spacing:.5px;color:var(--dk-gold)}
  .dk-mt-h .c{font-size:10.5px;color:var(--dk-faint);font-family:'SF Mono',monospace}
  .dk-mt-h .hint{margin-left:auto;font-size:10px;color:var(--dk-faint);font-family:'SF Mono',monospace}
  .dk-mt-scroll{overflow-x:auto;max-height:560px;overflow-y:auto}
  table.dk-mtbl{border-collapse:collapse;width:100%;font-size:11.5px;min-width:1120px}
  .dk-mtbl th{position:sticky;top:0;z-index:2;background:var(--dk-panel2);color:var(--dk-faint);font-size:9px;font-weight:800;letter-spacing:.5px;text-align:left;padding:7px 9px;border-bottom:1px solid var(--dk-line);white-space:nowrap;cursor:pointer;user-select:none}
  .dk-mtbl th.num{text-align:right}
  .dk-mtbl th:hover{color:var(--dk-txt)}
  .dk-mtbl th .ar{color:var(--dk-gold);margin-left:2px}
  .dk-mtbl td{padding:6px 9px;border-bottom:1px solid var(--dk-line);white-space:nowrap;vertical-align:middle}
  .dk-mtbl td.num{text-align:right;font-family:'SF Mono',monospace}
  .dk-mtbl tbody tr{cursor:pointer}
  .dk-mtbl tbody tr:hover{background:var(--dk-panel2)}
  .dk-mt-rk{font-family:'SF Mono',monospace;font-size:10px;color:var(--dk-faint)}
  .dk-mt-sym{font-weight:800;font-size:12.5px}
  .dk-mt-desks{display:flex;flex-wrap:wrap;gap:3px;max-width:190px}
  .dk-mt-db{font-size:8.5px;font-weight:700;letter-spacing:.2px;border-radius:4px;padding:1px 5px;border:1px solid var(--dk-line);white-space:nowrap}
  .dk-mt-up{color:var(--dk-good)}.dk-mt-dn{color:var(--dk-bad)}
  .dk-mt-rr.good{color:var(--dk-good);font-weight:700}.dk-mt-rr.bad{color:var(--dk-bad)}
  .dk-mt-stk{font-size:8.5px;font-family:'SF Mono',monospace;color:var(--dk-faint)}
  .dk-mt-risk{font-family:'SF Mono',monospace;font-size:9px;color:var(--dk-faint);display:flex;gap:6px}
  .dk-mt-risk .w{color:var(--dk-warn)}.dk-mt-risk .b{color:var(--dk-bad)}
  .dk-mt-empty{padding:18px;text-align:center;color:var(--dk-faint);font-style:italic;font-size:11px}
  .dk-mt-live{font-size:8px;color:var(--dk-good);margin-left:3px}
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

  // LIVE 'real buy' re-check (Schwab) — shown next to the desk verdict on BUY cards.
  // Green REAL BUY / amber MARGINAL / grey UNVERIFIED / red NOT REAL, with the failing
  // reasons in the tooltip. This is the honest live confirmation over the desk's raw call.
  function realBuyBadge(r) {
    const rb = r._realbuy;
    if (!rb || !rb.verdict) return null;
    const map = {
      "REAL BUY": ["real", "✓ REAL BUY" + (rb.tier ? " " + rb.tier : "")],
      "MARGINAL": ["marg", "⚠ MARGINAL"],
      "UNVERIFIED": ["unv", "? UNVERIFIED"],
      "NOT REAL": ["notreal", "✗ NOT REAL"],
    };
    const m = map[rb.verdict] || ["unv", rb.verdict];
    const reasons = [].concat(rb.fails || [], rb.warns || []).map((x) => "• " + x).join("\n");
    const title = "LIVE real-buy check (" + (rb.live ? "live Schwab intraday" : "daily fallback") + ")\n"
      + rb.verdict + (rb.tier ? " · " + rb.tier : "") + "\n" + reasons;
    return React.createElement("span", { className: "dk-rb " + m[0], key: "rb", title: title }, m[1]);
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

  const MECH = {
    pb: "Pullback to value — institutions re-add on the dip in an uptrend; buy the retrace at 3:1 R:R.",
    mom: "Relative-strength leadership — the strongest names keep leading (Jegadeesh-Titman).",
    bo: "Volatility contraction → expansion — supply dries up, then breaks out on volume (Minervini VCP).",
    qf: "Cross-sectional multi-factor — top-decile blend of momentum/quality/value/trend vs peers.",
    cat: "Post-event drift — the market under-reacts to catalysts (Bernard-Thomas PEAD).",
    mr: "Short-term mean reversion — oversold bounce with the long-term trend intact (Connors).",
    val: "Cheap + improving — buy the cheap decile while quality holds and revisions aren't falling.",
    qual: "Quality compounder — durable high-ROIC businesses at a reasonable price (GARP).",
    smart: "Information edge — follow insider clusters / congressional buying (Bettis-Coles).",
    def: "Defensive rotation — low-beta / staples / gold when breadth breaks (flight to safety).",
    short: "Relative-weakness breakdown — short the RS-worst names below key moving averages.",
  };

  function deepDive(r, d) {
    const t = r._tkt || {};
    const CE = React.createElement;
    const kv = (k, v) => CE("span", { key: k }, [CE("span", { className: "k", key: "k" }, k + " "), v == null ? "—" : v]);
    const sec = (title, kids) => CE("div", { key: title }, [CE("div", { className: "sh", key: "h" }, title), CE("div", { className: "kv", key: "b" }, kids)]);
    const usd = (v) => v == null ? "—" : "$" + (+v).toFixed(2);
    const inval = [];
    if (r.stop != null) inval.push("close < stop " + usd(r.stop));
    if (r.ema50i != null) inval.push("loses EMA50 " + usd(r.ema50i));
    if (t.ear_days != null && t.ear_days >= 0 && t.ear_days <= 14) inval.push("earnings in " + t.ear_days + "d");
    const kids = [
      CE("div", { className: "thesis", key: "th" }, "◆ " + (MECH[d.key] || d.who || "")),
      sec("DESK EDGE", [CE("span", { key: "e" }, (d.edge && d.edge.text) || "—"), d.live ? kv("· live", "n=" + d.live.n + " WR " + Math.round((d.live.wr || 0) * 100) + "%") : null]),
      sec("WHY IT FIRED", (r._why || "").split(" · ").map((w, i) => CE("span", { key: i, className: "chk" }, w))),
      r._realbuy ? sec("● LIVE REAL-BUY CHECK", [].concat(
        [CE("span", { key: "v", className: "chk " + (r._realbuy.verdict === "REAL BUY" ? "" : r._realbuy.verdict === "NOT REAL" ? "bad" : "warn") },
          r._realbuy.verdict + (r._realbuy.tier ? " · " + r._realbuy.tier : "") + (r._realbuy.live ? " (live)" : " (daily)"))],
        (r._realbuy.fails || []).map((f, i) => CE("span", { key: "f" + i, className: "chk bad" }, "✗ " + f)),
        (r._realbuy.warns || []).map((w, i) => CE("span", { key: "w" + i, className: "chk" }, "· " + w))
      )) : null,
      sec("LIVE TECHNICALS", [kv("RSI", r.rsi != null ? (+r.rsi).toFixed(0) : null), kv("ADX", r.adx != null ? (+r.adx).toFixed(0) : null),
        kv("EMA8", r.ema8 != null ? usd(r.ema8) : null), kv("EMA21", r.ema21 != null ? usd(r.ema21) : null), kv("EMA50", r.ema50i != null ? usd(r.ema50i) : null),
        kv("ATR%", r.atr != null ? (+r.atr).toFixed(1) : null), kv("RVOL", r.rvol != null ? (+r.rvol).toFixed(1) : null), kv("RS", r.rs)]),
      sec("TRADE PLAN", [kv("entry", r.entry_lo != null ? usd(r.entry_lo) + "–" + (+r.entry_hi).toFixed(2) : null), kv("stop", usd(r.stop)), kv("T1", usd(r.t1)), kv("R:R", r._rr)]),
      sec("RISK & PROBABILITY", [kv("P", Math.round((t.p || 0) * 100) + "%"), kv("E[R]", t.ev), kv("size", t.size != null ? t.size + "%" : null),
        kv("max-loss", t.maxloss != null ? t.maxloss + "%" : null), kv("$ADV", t.adv != null ? fmtUsd(t.adv) : null), kv("β", t.beta != null ? (+t.beta).toFixed(2) : null)]),
    ];
    if (r.fwd_pe != null || r.roe != null || r.gm != null) {
      kids.push(sec("FUNDAMENTALS", [kv("fwd P/E", r.fwd_pe != null ? (+r.fwd_pe).toFixed(1) : null), kv("P/S", r.ps != null ? (+r.ps).toFixed(1) : null),
        kv("ROE", r.roe != null ? (+r.roe).toFixed(0) + "%" : null), kv("GM", r.gm != null ? (+r.gm).toFixed(0) + "%" : null)]));
    }
    if ((r._across || 1) >= 2) kids.push(sec("CONFLUENCE", [CE("span", { key: "c", className: "chk" }, "⋈ also flagged by " + (r._acrosslbls || ""))]));
    kids.push(CE("div", { key: "inv" }, [CE("div", { className: "sh", key: "h" }, "INVALIDATION · PRE-MORTEM"), CE("div", { className: "inval", key: "b" }, "✗ " + inval.join("  ·  "))]));
    return CE("div", { className: "dk-dd", key: "dd" }, kids);
  }

  // Open a ticker on the user's logged-in TradingView Desktop chart via the CDP
  // bridge (/api/tv/open sets the symbol on the active chart, preserving their
  // saved PHSwing + LuxAlgo layout). Honest-fail: any bridge error → open the TV
  // web chart in a new tab. Visual layer only — never touches scoring.
  function openInTV(sym, mode) {
    sym = (sym || "").toUpperCase();
    var web = "https://www.tradingview.com/chart/?symbol=" + encodeURIComponent(sym);
    try {
      fetch("/api/tv/open?t=" + encodeURIComponent(sym) + "&mode=" + encodeURIComponent(mode || "swing"),
            { method: "POST", credentials: "same-origin" })
        .then(function (r) { return r.json().catch(function () { return { ok: false, web: web }; }); })
        .then(function (d) { if (!d || !d.ok) window.open((d && d.web) || web, "_blank"); })
        .catch(function () { window.open(web, "_blank"); });
    } catch (e) { window.open(web, "_blank"); }
  }

  function Card({ r, i, ck, onTicker, maxSize, desk, open, onToggle, mode }) {
    const conf = (r._across || 1) >= 2;
    const kids = [
      React.createElement("div", { className: "dk-top", key: "t" }, [
        React.createElement("span", { className: "dk-rk", key: "r" }, i + 1),
        React.createElement("span", { className: "dk-sym", key: "s" }, r.t),
        React.createElement("button", {
          className: "dk-tvbtn", key: "tv",
          title: "Open " + r.t + " on your TradingView Desktop chart (falls back to TV web)",
          onClick: (e) => { e.stopPropagation(); openInTV(r.t, mode); },
          style: { marginLeft: "6px", fontSize: "9px", lineHeight: "1", padding: "2px 5px", cursor: "pointer", background: "none", border: "1px solid var(--dk-line)", borderRadius: "5px", color: "var(--dk-dim)", fontFamily: "'SF Mono',monospace" }
        }, "📈 TV"),
        verdictChip(r, ck),
        realBuyBadge(r),
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
      if (desk) {
        kids.push(React.createElement("button", { className: "dk-ddbtn", key: "ddb", onClick: (e) => { e.stopPropagation(); onToggle && onToggle(); } },
          open ? "▲ hide deep dive" : "▾ deep dive"));
        if (open) kids.push(deepDive(r, desk));
      }
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
    const [ddOpen, setDdOpen] = React.useState({});
    const [mtOpen, setMtOpen] = React.useState(true);
    const [mtSort, setMtSort] = React.useState({ key: "verdict", dir: "desc" });
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
          realBuyBadge(b),
          React.createElement("div", { className: "d", key: "d" }, b.desks.join(" · ")),
        ]))),
    ]) : null;

    // ── Master leaderboard: one row per unique ticker across ALL desks ──
    // Pure display over the same payload the cards use. A ticker can appear in
    // several desks; we keep its strongest verdict as the primary row and list
    // every desk that flagged it. Honors the same search/price/BUY/overflow filters.
    const DK_SHORT = { mom: "MOM", bo: "BO", pb: "PB", qf: "QF", cat: "CAT", mr: "MR", val: "VAL", smart: "SMART", qual: "QUAL", def: "DEF", short: "SHORT" };
    const keyColor = {}; (data.desks || []).forEach((d) => { keyColor[d.key] = d.color; });
    const PRI = { BUY: 5, SHORT: 4, WATCH: 3, PASS: 2, AVOID: 1 };
    function buildMaster() {
      const byT = {};
      Object.keys(books).forEach((k) => {
        (books[k].rows || []).forEach((r) => {
          const t = r.t; if (!t) return;
          let e = byT[t];
          if (!e) { e = { t, keys: [], best: r, pri: PRI[r._dv] || 0 }; byT[t] = e; }
          if (e.keys.indexOf(k) < 0) e.keys.push(k);
          const pri = PRI[r._dv] || 0;
          if (pri > e.pri || (pri === e.pri && (+(r._factor || 0)) > (+(e.best._factor || 0)))) { e.best = r; e.pri = pri; }
        });
      });
      let arr = Object.keys(byT).map((t) => ({ t, r: byT[t].best, desks: byT[t].keys, ndesk: byT[t].keys.length, pri: byT[t].pri }));
      arr = arr.filter((x) => {
        const r = x.r;
        if (qlc && (x.t || "").toUpperCase().indexOf(qlc) < 0) return false;
        if (!isNaN(pmin) && !(r.price != null && +r.price >= pmin)) return false;
        if (!isNaN(pmax) && !(r.price != null && +r.price <= pmax)) return false;
        if (buyOnly) return r._dv === "BUY" || r._dv === "SHORT";
        if (!showOverflow) return r._dv === "BUY" || r._dv === "WATCH" || r._dv === "SHORT";
        return true;
      });
      const dir = mtSort.dir === "asc" ? 1 : -1, sk = mtSort.key;
      const val = (x) => {
        const r = x.r;
        if (sk === "ticker") return x.t;
        if (sk === "chg") return r._chg == null ? -1e9 : +r._chg;
        if (sk === "rr") return +r._rr || 0;
        if (sk === "rsi") return r.rsi == null ? -1 : +r.rsi;
        if (sk === "rs") return r.rs == null ? -1 : +r.rs;
        if (sk === "conf") return x.ndesk;
        if (sk === "edge") return (r._tkt && r._tkt.ev != null) ? +r._tkt.ev : -1e9;
        return x.pri * 1e6 + (+(r._factor || 0));   // verdict (default)
      };
      arr.sort((a, b) => { const va = val(a), vb = val(b); return (typeof va === "string") ? va.localeCompare(vb) * dir : (va - vb) * dir; });
      return arr;
    }
    const masterRows = buildMaster();
    const setSort = (k) => setMtSort((s) => s.key === k ? { key: k, dir: s.dir === "asc" ? "desc" : "asc" } : { key: k, dir: k === "ticker" ? "asc" : "desc" });
    const th = (label, k, num) => React.createElement("th", { key: k, className: num ? "num" : "", onClick: () => setSort(k), title: "sort by " + label },
      [label, mtSort.key === k ? React.createElement("span", { className: "ar", key: "a" }, mtSort.dir === "asc" ? " ▲" : " ▼") : null]);
    function mRow(x, i) {
      const r = x.r, tk = r._tkt || {};
      const vd = String(r._dv || "").toUpperCase();
      const vcls = vd === "BUY" ? "buy" : vd === "WATCH" ? "watch" : vd === "SHORT" ? "short" : vd === "PASS" ? "pass" : "avoid";
      const rr = n(r._rr), rrCls = rr == null ? "" : rr >= 3 ? "good" : rr < 1 ? "bad" : "";
      const chg = n(r._chg), px = n(r.price);
      const deskBadges = x.desks.map((k) => React.createElement("span", { key: k, className: "dk-mt-db", style: { color: keyColor[k] || "var(--dk-dim)", borderColor: (keyColor[k] || "var(--dk-line)") } }, DK_SHORT[k] || k.toUpperCase()));
      const stack = (r.above50 || r.above200) ? React.createElement("span", { className: "dk-mt-stk" }, (r.above50 ? "50▲" : "50▽") + (r.above200 ? "200▲" : "200▽")) : null;
      const edge = tk.p != null ? ("P " + Math.round(tk.p * 100) + "% · " + ((tk.ev >= 0 ? "+" : "") + tk.ev)) : "—";
      const risk = [];
      if (tk.beta != null) risk.push(React.createElement("span", { key: "b" }, "β" + (+tk.beta).toFixed(2)));
      if (tk.ear_days != null && tk.ear_days >= 0 && tk.ear_days <= 10) risk.push(React.createElement("span", { key: "e", className: "b" }, "⚠E" + tk.ear_days + "d"));
      if (tk.short_float != null && +tk.short_float >= 10) risk.push(React.createElement("span", { key: "s", className: "w" }, "SI" + (+tk.short_float).toFixed(0) + "%"));
      return React.createElement("tr", { key: x.t + i, onClick: () => onTicker && onTicker(x.t) }, [
        React.createElement("td", { key: "rk", className: "dk-mt-rk" }, i + 1),
        React.createElement("td", { key: "sym" }, [
          React.createElement("span", { className: "dk-mt-sym", key: "y" }, x.t),
          x.ndesk >= 2 ? React.createElement("span", { className: "dk-acc", key: "c", title: x.desks.map((k) => DK_SHORT[k] || k).join(" · ") }, "⋈" + x.ndesk) : null,
          r._livepx ? React.createElement("span", { className: "dk-mt-live", key: "l", title: "live Schwab quote" }, "●") : null,
        ]),
        React.createElement("td", { key: "px", className: "num" }, [
          px != null ? "$" + px.toFixed(2) : "—",
          chg != null ? React.createElement("span", { className: chg >= 0 ? "dk-mt-up" : "dk-mt-dn", key: "c" }, "  " + (chg >= 0 ? "+" : "") + chg.toFixed(1) + "%") : null,
        ]),
        React.createElement("td", { key: "dk" }, React.createElement("div", { className: "dk-mt-desks" }, deskBadges)),
        React.createElement("td", { key: "vd" }, vd ? React.createElement("span", { className: "dk-vc " + vcls, title: r._why || "" }, vd) : "—"),
        React.createElement("td", { key: "rr", className: "num dk-mt-rr " + rrCls }, rr != null ? rr.toFixed(1) : "—"),
        React.createElement("td", { key: "eq" }, [pill(r), pill(r) ? " " : null, stack]),
        React.createElement("td", { key: "rsi", className: "num" }, r.rsi != null ? (+r.rsi).toFixed(0) : "—"),
        React.createElement("td", { key: "rs", className: "num" }, (r.rs != null ? r.rs : "—") + (r.sharpe != null ? " · " + (+r.sharpe).toFixed(1) : "")),
        React.createElement("td", { key: "fn", className: "num" }, [
          r.fwd_pe != null ? (+r.fwd_pe).toFixed(1) : "—",
          " · ", r.roe != null ? (+r.roe).toFixed(0) + "%" : "—",
          " · ", r.gm != null ? (+r.gm).toFixed(0) + "%" : "—",
        ]),
        React.createElement("td", { key: "ed", className: "num" }, edge),
        React.createElement("td", { key: "rk2" }, React.createElement("div", { className: "dk-mt-risk" }, risk.length ? risk : "—")),
      ]);
    }
    const masterTable = React.createElement("div", { className: "dk-mt" }, [
      React.createElement("div", { className: "dk-mt-h", key: "h", onClick: () => setMtOpen((o) => !o) }, [
        React.createElement("span", { className: "cv", key: "cv" }, mtOpen ? "▾" : "▸"),
        React.createElement("span", { className: "t", key: "t" }, "★ ALL NAMES · MASTER TABLE"),
        React.createElement("span", { className: "c", key: "c" }, masterRows.length + " tickers across all desks · " + hz),
        React.createElement("span", { className: "hint", key: "hn" }, "click a header to sort · click a row to open"),
      ]),
      mtOpen ? React.createElement("div", { className: "dk-mt-scroll", key: "s" },
        masterRows.length ? React.createElement("table", { className: "dk-mtbl" }, [
          React.createElement("thead", { key: "th" }, React.createElement("tr", null, [
            React.createElement("th", { key: "rk" }, "#"),
            th("TICKER", "ticker"), th("PRICE / Δ", "chg", true), React.createElement("th", { key: "dk" }, "DESKS"),
            th("VERDICT", "verdict"), th("R:R", "rr", true), React.createElement("th", { key: "eq" }, "ENTRY / TREND"),
            th("RSI", "rsi", true), th("RS·SHRP", "rs", true), React.createElement("th", { key: "fn", className: "num" }, "FWDPE·ROE·GM"),
            th("EDGE P·E[R]", "edge", true), React.createElement("th", { key: "rk2" }, "RISK"),
          ])),
          React.createElement("tbody", { key: "tb" }, masterRows.map(mRow)),
        ]) : React.createElement("div", { className: "dk-mt-empty" }, "No names match the current filters. Toggle 'show overflow' or clear the search / price filter.")) : null,
    ]);

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
        body = rows.map((r, i) => {
          const kk = d.key + "|" + r.t;
          return React.createElement(Card, { key: r.t + i, r, i, ck: d.key, onTicker, maxSize, desk: d, mode: hz,
            open: !!ddOpen[kk], onToggle: () => setDdOpen((o) => Object.assign({}, o, { [kk]: !o[kk] })) });
        });
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
        ? React.createElement("span", { className: "f", key: "l" }, ["· Live prices ", React.createElement("b", { key: "la" }, liveAge || "—"), " (every 2 min)"])
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
      regimeStrip, hzToggle, ctrls, masterTable, bestStrip,
      React.createElement("div", { className: "dk-grid", key: "g" }, cols),
      React.createElement("div", { className: "dk-foot", key: "f" },
        "Each desk scans the whole universe and calls BUY/WATCH/PASS on its OWN criteria — never the old scanner's score or verdict. Regime sets LEADING/ACTIVE/DORMANT; confluence ⋈ is internal agreement only. Hover any verdict chip to see which conditions passed/failed."),
    ]);
  }

  window.SurfaceDesks = SurfaceDesks;
})();
