// surface-desks.jsx — Screener Desks: 11 trader-archetype books, regime-aware.
// Reads /api/screener_desks (built by screener_desks.py from the real scan bundle +
// per-setup Wilson edge + Schwab live overlay). Display layer — no scoring here.
(function () {
  const CSS = `
  .dk-wrap{--dk-mom:#f0a53c;--dk-bo:#e5573f;--dk-pb:#37b6a2;--dk-qf:#6f8cf0;--dk-cat:#c77dff;
    --dk-mr:#4db8ff;--dk-def:#9aa0a6;--dk-short:#e5573f;--dk-val:#c9a24b;--dk-smart:#e08fd0;--dk-qual:#6fd39a;
    --dk-good:#2fbf7a;--dk-warn:#e5a83f;--dk-bad:#e5573f;--dk-gold:#ffd479;
    --dk-line:#1e2a27;--dk-panel:#111917;--dk-panel2:#0d1413;--dk-txt:#e8f0ee;--dk-dim:#8aa39c;--dk-faint:#5c716b;
    padding:6px 4px 40px;color:var(--dk-txt);font-size:13px}
  .dk-wrap .mono{font-family:'SF Mono',ui-monospace,Menlo,monospace}
  .dk-regime{display:flex;gap:10px;align-items:center;background:linear-gradient(90deg,#12201d,#0f1a18);
    border:1px solid var(--dk-line);border-radius:12px;padding:11px 15px;margin:2px 0 12px;flex-wrap:wrap}
  .dk-regime .tag{font-weight:700;letter-spacing:.5px;color:var(--dk-gold)}
  .dk-regime .chip{background:#0c1513;border:1px solid var(--dk-line);border-radius:20px;padding:3px 11px;color:var(--dk-dim);font-size:11.5px}
  .dk-regime .verdict{margin-left:auto;color:var(--dk-dim);font-size:11.5px;max-width:440px}
  .dk-hz{display:inline-flex;background:#0c1312;border:1px solid var(--dk-line);border-radius:10px;padding:4px;gap:4px;margin-bottom:14px}
  .dk-hz button{background:none;border:0;color:var(--dk-dim);font:600 12.5px/1 inherit;padding:8px 15px;border-radius:7px;cursor:pointer}
  .dk-hz button.on{background:#1a2a26;color:var(--dk-txt);box-shadow:inset 0 0 0 1px #24413a}
  .dk-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:11px}
  @media(max-width:1250px){.dk-grid{grid-template-columns:repeat(3,1fr)}}
  @media(max-width:960px){.dk-grid{grid-template-columns:repeat(2,1fr)}}
  .dk-col{background:var(--dk-panel);border:1px solid var(--dk-line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
  .dk-col.lead{box-shadow:0 0 0 1px #1c3a2e,0 8px 30px -12px rgba(47,191,122,.35)}
  .dk-col.dorm{opacity:.5}
  .dk-chead{padding:12px 13px 10px;border-bottom:1px solid var(--dk-line);background:var(--dk-panel2)}
  .dk-chead .ttl{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:800}
  .dk-dot{width:9px;height:9px;border-radius:50%}
  .dk-chead .who{color:var(--dk-dim);font-size:10.5px;margin-top:4px}
  .dk-sp{float:right;font-size:9px;font-weight:800;letter-spacing:.5px;border-radius:20px;padding:2px 8px}
  .dk-sp.lead{color:var(--dk-good);background:#0d1c17;border:1px solid #1c3a2e}
  .dk-sp.act{color:var(--dk-dim);border:1px solid var(--dk-line)}
  .dk-sp.dorm{color:var(--dk-faint);border:1px solid var(--dk-line)}
  .dk-edge{margin-top:8px;font-family:'SF Mono',monospace;font-size:10px;border-radius:7px;padding:5px 7px;line-height:1.35}
  .dk-edge.e-good{color:var(--dk-good);background:#0c1a14;border:1px solid #163a2b}
  .dk-edge.e-mid{color:var(--dk-warn);background:#1a160c;border:1px solid #3a3016}
  .dk-edge.e-bad{color:var(--dk-bad);background:#1a0e0c;border:1px solid #3a1a16}
  .dk-edge.e-unp{color:var(--dk-faint);background:#12100c;border:1px solid var(--dk-line)}
  .dk-cards{padding:7px;display:flex;flex-direction:column;gap:6px}
  .dk-card{background:var(--dk-panel2);border:1px solid var(--dk-line);border-radius:9px;padding:8px 9px;cursor:pointer}
  .dk-card:hover{border-color:#2c3d39}
  .dk-card.conf{box-shadow:inset 2px 0 0 var(--dk-gold)}
  .dk-top{display:flex;align-items:baseline;gap:6px}
  .dk-rk{font-family:'SF Mono',monospace;font-size:10.5px;color:var(--dk-faint);width:14px}
  .dk-sym{font-weight:800;font-size:13.5px}
  .dk-vc{font-size:9px;font-weight:800;letter-spacing:.3px;border-radius:5px;padding:1px 5px;margin-left:4px}
  .dk-vc.buy{color:#08120d;background:var(--dk-good)}
  .dk-vc.watch{color:var(--dk-warn);border:1px solid #3a3016}
  .dk-vc.avoid{color:var(--dk-faint);border:1px solid var(--dk-line)}
  .dk-vc.pass{color:var(--dk-faint);border:1px dashed var(--dk-line)}
  .dk-vc.short{color:#120a08;background:var(--dk-bad)}
  .dk-acc{font-family:'SF Mono',monospace;font-size:9px;font-weight:800;color:var(--dk-gold);background:#1a160c;border:1px solid #3a3016;border-radius:5px;padding:0 4px;margin-left:3px}
  .dk-live{font-size:8px;color:var(--dk-good);margin-left:3px}
  .dk-px{margin-left:auto;font-family:'SF Mono',monospace;color:var(--dk-dim);font-size:11.5px}
  .dk-px .up{color:var(--dk-good)}.dk-px .dn{color:var(--dk-bad)}
  .dk-sect{color:var(--dk-faint);font-size:10px;margin:2px 0 5px 20px}
  .dk-hl{margin-left:20px;font-family:'SF Mono',monospace;font-size:11px}.dk-hl .kv{color:var(--dk-dim)}
  .dk-pill{display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:5px}
  .dk-p-zone{color:#0a0e0d;background:var(--dk-good)}.dk-p-appr{color:var(--dk-good);border:1px solid #1c3a2e}
  .dk-p-ext{color:var(--dk-warn);border:1px solid #3a3320}.dk-p-fire{color:#0a0e0d;background:var(--dk-bo)}
  .dk-fchips{margin:4px 0 1px 20px;font-family:'SF Mono',monospace;font-size:10.5px;display:flex;flex-wrap:wrap;gap:2px 9px}
  .dk-fchips .fl{color:var(--dk-faint);font-size:9px}
  .dk-plan{margin:5px 0 0 20px;font-family:'SF Mono',monospace;font-size:10px;color:var(--dk-faint)}.dk-plan b{color:var(--dk-pb)}
  .dk-empty{color:var(--dk-faint);font-size:10.5px;padding:14px 10px;text-align:center;font-style:italic}
  .dk-foot{color:var(--dk-faint);font-size:11px;margin-top:18px;border-top:1px solid var(--dk-line);padding-top:11px;max-width:960px}
  .dk-load{color:var(--dk-dim);padding:40px;text-align:center}
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
    return React.createElement("span", { className: "dk-vc " + cls, key: "vc", title: "This desk's own call from raw signals — click card for the full deep-dive" }, vd);
  }

  function Card({ r, i, ck, onTicker }) {
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
    return React.createElement("div", { className: "dk-card" + (conf ? " conf" : ""), onClick: () => r.t && onTicker && onTicker(r.t) }, kids);
  }

  function SurfaceDesks({ onTicker }) {
    ensureStyle();
    const [data, setData] = React.useState(null);
    const [hz, setHz] = React.useState("swing");
    const [err, setErr] = React.useState(null);
    React.useEffect(() => {
      const BV = window.__BV;
      if (BV && BV.get) {
        BV.get("/api/screener_desks").then((d) => setData(d)).catch((e) => setErr(String(e)));
      } else {
        setErr("boot adapter not ready");
      }
    }, []);

    if (err) return React.createElement("div", { className: "dk-wrap" }, React.createElement("div", { className: "dk-load" }, "Screener Desks unavailable: " + err));
    if (!data) return React.createElement("div", { className: "dk-wrap" }, React.createElement("div", { className: "dk-load" }, "Loading desks…"));

    const reg = data.regime || {};
    const note = REGIME_NOTE[reg.regime4] || "Regime decides which desks lead.";
    const pool = (data.horizons || {})[hz] || {};

    const regimeStrip = React.createElement("div", { className: "dk-regime" }, [
      React.createElement("span", { className: "tag", key: "t" }, "REGIME · " + String(reg.regime4 || "—").toUpperCase().replace(/_/g, " ")),
      reg.vix != null ? React.createElement("span", { className: "chip", key: "v" }, "VIX " + (+reg.vix).toFixed(1)) : null,
      reg.breadth != null ? React.createElement("span", { className: "chip", key: "b" }, "Breadth " + (+reg.breadth).toFixed(0) + "%") : null,
      reg.distribution_days != null ? React.createElement("span", { className: "chip", key: "d", style: { color: "var(--dk-warn)" } }, reg.distribution_days + " distribution days") : null,
      React.createElement("span", { className: "verdict", key: "n" }, [React.createElement("b", { key: "b", style: { color: "var(--dk-good)" } }, "Desks live today → "), note]),
    ]);

    const hzToggle = React.createElement("div", { className: "dk-hz" },
      [["swing", "SWING · 2–5 day"], ["position", "POSITION · 2–8 wk"], ["invest", "INVEST · 3–12 mo"]].map(([k, lbl]) =>
        React.createElement("button", { key: k, className: hz === k ? "on" : "", onClick: () => setHz(k) }, lbl)));

    const cols = (data.desks || []).map((d) => {
      const rows = pool[d.key] || [];
      const dorm = d.state === "dorm";
      const spCls = d.state === "lead" ? "lead" : dorm ? "dorm" : "act";
      const spTxt = d.state === "lead" ? "LEADING" : dorm ? "DORMANT" : "ACTIVE";
      let body;
      if (!rows.length) {
        body = React.createElement("div", { className: "dk-empty" },
          dorm ? "Regime does not call for this desk today. Auto-arms when conditions flip."
            : (d.emptymsg || "No qualifying names today."));
      } else {
        body = rows.map((r, i) => React.createElement(Card, { key: r.t + i, r, i, ck: d.key, onTicker }));
      }
      return React.createElement("div", { className: "dk-col " + (d.state === "lead" ? "lead" : dorm ? "dorm" : ""), key: d.key }, [
        React.createElement("div", { className: "dk-chead", key: "h" }, [
          React.createElement("span", { className: "dk-sp " + spCls, key: "sp" }, spTxt),
          React.createElement("div", { className: "dk-ttl", key: "t" }, [
            React.createElement("span", { className: "dk-dot", key: "d", style: { background: d.color } }),
            React.createElement("span", { key: "n" }, d.name)]),
          React.createElement("div", { className: "who", key: "w" }, d.who),
          React.createElement("div", { className: "dk-edge " + ((d.edge && d.edge.class) || "e-unp"), key: "e" }, (d.edge && d.edge.text) || ""),
        ]),
        React.createElement("div", { className: "dk-cards", key: "c" }, body),
      ]);
    });

    return React.createElement("div", { className: "dk-wrap" }, [
      React.createElement("div", { key: "sub", style: { color: "var(--dk-dim)", fontSize: "12px", margin: "0 0 10px" } },
        "Eleven trader-archetype books · ranked from the live scan · " + (data.live_at ? "Schwab live " + data.live_at : "close-anchored") + " · confluence ⋈ flags cross-desk names."),
      regimeStrip, hzToggle,
      React.createElement("div", { className: "dk-grid", key: "g" }, cols),
      React.createElement("div", { className: "dk-foot", key: "f" },
        "Each column ranks the universe its own way; the regime engine sets LEADING / ACTIVE / DORMANT. Edge headers show real Wilson win-rate + profit-factor from closed trades. Display layer — re-presents scan output, adds no signal."),
    ]);
  }

  window.SurfaceDesks = SurfaceDesks;
})();
