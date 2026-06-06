// lens-earnings.jsx + lens-options.jsx

// ────────────────────────────────────────────────────────────
// EARNINGS — countdown, implied-move cone, beat probability
// ────────────────────────────────────────────────────────────
function PEADPanel({ ticker }) {
  const rows = [
    { sc: "After a BEAT", tone: "gn", pts: [["T+1", "+1.8%"], ["T+5", "+3.4%"], ["T+10", "+4.9%"]] },
    { sc: "After a MISS", tone: "rd", pts: [["T+1", "−2.1%"], ["T+5", "−1.2%"], ["T+10", "+0.3%"]] },
    { sc: "In-line", tone: "amb", pts: [["T+1", "+0.2%"], ["T+5", "+0.6%"], ["T+10", "+1.1%"]] },
  ];
  // days since last print → where we sit on the drift window (demo, per-ticker)
  const sinceP = ((((ticker && ticker.symbol) || "X").charCodeAt(0)) % 9) + 1;   // 1–9 sessions ago
  const inWindow = sinceP <= 10;
  const pos = Math.min(100, sinceP / 10 * 100);
  const realized = +(4.9 * (sinceP / 10)).toFixed(1);
  return (
    <div>
      <div className="pead-now">
        <div className="pead-now-h mono dim2">DRIFT WINDOW · last print {sinceP}d ago {inWindow ? `· ${10 - sinceP} sessions of edge left` : "· window closed"}</div>
        <div className="pead-track">
          <span className="pead-track-fill" style={{ width: `${pos}%` }} />
          <span className="pead-now-mark" style={{ left: `${pos}%` }} title={`T+${sinceP} · ~${realized}% captured`}><span className="pead-now-dot" /><span className="pead-now-lbl mono">NOW · T+{sinceP}</span></span>
          <span className="pead-track-end mono dim">T+0</span><span className="pead-track-end pead-track-end--r mono dim">T+10</span>
        </div>
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="Beat → +10d drift" value="+4.9%" tone="gn" sub="median · 12-Q" />
        <KpiTile label="Miss → +10d drift" value="+0.3%" tone="amb" sub="mean-reverts" />
        <KpiTile label="Beat continuation" value="73%" tone="gn" sub="positive 10-day" />
        <KpiTile label="PEAD edge" value="TRADEABLE" tone="gn" sub="drift > noise floor" />
      </div>
      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "118px 1fr", gap: 14, alignItems: "center" }}>
            <Pill tone={r.tone} small>{r.sc}</Pill>
            <div style={{ display: "flex", gap: 16 }}>
              {r.pts.map(([t, v], j) => (
                <span key={j} className="mono" style={{ fontSize: 12 }}>
                  <span className="dim2" style={{ fontSize: 10 }}>{t}</span>{" "}
                  <b className={v.indexOf("−") === 0 ? "dn" : "up"}>{v}</b>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="mono dim2" style={{ marginTop: 10, fontSize: 11, lineHeight: 1.5 }}>
        Beats drift <b className="up">+4.9% over 10 sessions</b> (9 of last 12 Q) while misses mean-revert — a positive post-earnings-announcement-drift edge. Add on a confirmed beat into the T+1 gap; the drift sits above the noise floor.
      </div>
    </div>
  );
}

// Real upcoming-earnings prediction for this ticker (cached data_earnings.json →
// BV.earningsBeat, no live EODHD). null when the name has no scheduled report.
function findEarnings(ticker) {
  const sym = ((ticker && ticker.symbol) || "").split(".")[0].toUpperCase();
  const list = (window.__BV && window.__BV.earningsBeat) || [];
  return list.find(r => ((r.ticker || "").split(".")[0].toUpperCase()) === sym) || null;
}
function erMoney(v) { return (typeof v === "number" && isFinite(v)) ? "$" + v.toFixed(2) : "—"; }
function erPct(v, d = 1) { return (typeof v === "number" && isFinite(v)) ? v.toFixed(d) + "%" : "—"; }

function LensEarnings({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("er-1"); const s2 = useStateToggle("er-2");
  const s3 = useStateToggle("er-3"); const s4 = useStateToggle("er-4");
  const row = findEarnings(ticker);

  if (!row) {
    return (
      <div className="lens lens--er">
        <div className="lens-section"><div className="lens-pad">
          <div className="smc-empty mono dim2" style={{ padding: "16px" }}>
            No scheduled-earnings prediction for <b className="warn">{(ticker && ticker.symbol) || "this name"}</b> in the
            beat-watchlist (covers names reporting in the next ~2 weeks). Earnings analytics — implied move, beat
            probability, history and event sizing — appear here once a report is scheduled.
          </div>
        </div></div>
      </div>
    );
  }

  const b = row.breakdown || {};
  const im = b.implied_move || {}, hist = b.historical || {}, kel = b.kelly_sizing || {}, au = b.analyst_upside || {}, liq = b.liquidity || {};
  const tierTone = row.tier === "STRONG" ? "gn" : row.tier === "SOLID" ? "cy" : row.tier === "MODERATE" ? "amb" : "ink";
  const advFmt = liq.adv_dollar_60d ? (liq.adv_dollar_60d >= 1e9 ? "$" + (liq.adv_dollar_60d / 1e9).toFixed(1) + "B" : "$" + (liq.adv_dollar_60d / 1e6).toFixed(0) + "M") : "—";
  const patt = (hist.pattern || "").split("");   // e.g. "BBBB" → beat/beat/beat/beat

  return (
    <div className="lens lens--er">
      <ERCockpit row={row} />

      <div className="lens-section">
        <SectionHeader n={1} title="Implied Move · ATM Straddle"
          sub="the move options are pricing for the print"
          style={headerStyle} right={<StateToggle name="er-1" />}
          tip="The ATM straddle's cost as a % of price = the move the options market expects on earnings. Buy below it / sell above it if you have an edge." />
        <StateWrap state={s1.value} source={`${im.source || "options"} · ATM ${im.expiry_date || ""}`}>
          <div className="lens-pad"><div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            <KpiTile label="Implied move" value={`±${erPct(im.implied_move_pct, 2)}`} tone="amb" sub={im.spot != null ? `${erMoney(im.spot * (1 - (im.implied_move_pct || 0) / 100))} — ${erMoney(im.spot * (1 + (im.implied_move_pct || 0) / 100))}` : "—"} />
            <KpiTile label="ATM straddle" value={erMoney(im.straddle_cost)} tone="ink" sub={`exp ${im.expiry_date || "—"}`} />
            <KpiTile label="ATM strike" value={erMoney(im.atm_strike)} tone="ink" sub={`spot ${erMoney(im.spot)}`} />
            <KpiTile label="Source" value={(im.source || "—").toUpperCase()} tone="ink" sub="live chain" />
          </div></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Beat Probability · Score"
          sub="composite beat-prediction model · historical + analyst + setup"
          style={headerStyle} right={<StateToggle name="er-2" />}
          tip="Composite beat score (0–100) and tier from this name's history, analyst upside and the model's win probability." />
        <StateWrap state={s2.value} source="beat-prediction model">
          <div className="lens-pad"><div className="kpi-row" style={{ gridTemplateColumns: "repeat(5, 1fr)" }}>
            <KpiTile label="Beat score" value={row.beat_score != null ? row.beat_score.toFixed(1) : "—"} tone={tierTone} sub={`tier ${row.tier || "—"}`} />
            <KpiTile label="Win prob (model)" value={kel.win_prob != null ? (kel.win_prob * 100).toFixed(0) + "%" : "—"} tone={kel.win_prob >= 0.6 ? "gn" : "amb"} sub="P(beat)" />
            <KpiTile label="Historical beat rate" value={hist.rate != null ? hist.rate.toFixed(0) + "%" : "—"} tone={hist.rate >= 70 ? "gn" : "amb"} sub={`${hist.n_quarters || "—"} quarters`} />
            <KpiTile label="Median surprise" value={hist.median_surprise_pct != null ? "+" + hist.median_surprise_pct.toFixed(1) + "%" : "—"} tone="gn" sub="EPS vs est" />
            <KpiTile label="Analyst upside" value={au.upside_pct != null ? "+" + au.upside_pct.toFixed(1) + "%" : "—"} tone="gn" sub="to mean PT" />
          </div></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Beat History"
          sub={`${hist.n_quarters || 0}-quarter EPS beat/miss pattern`}
          style={headerStyle} right={<StateToggle name="er-3" />} />
        <StateWrap state={s3.value} source="earnings history">
          <div className="lens-pad">
            {patt.length ? <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              {patt.map((ch, i) => (
                <span key={i} className={`pill pill--sm pill--${ch === "B" ? "gn" : "rd"}`}>{ch === "B" ? "BEAT" : "MISS"}</span>
              ))}
              <span className="mono dim2" style={{ marginLeft: 8 }}>{hist.rate != null ? hist.rate.toFixed(0) + "% beat rate" : ""} · median +{hist.median_surprise_pct != null ? hist.median_surprise_pct.toFixed(1) : "—"}% surprise (oldest → newest)</span>
            </div> : <div className="smc-empty mono dim2">— no beat history in feed</div>}
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Event Sizing · Kelly"
          sub="how much to risk into a binary event"
          style={headerStyle} right={<StateToggle name="er-4" />}
          tip="Kelly bet size for the event using the model's win-prob and the implied-move payoff/risk. Capped (often to 0) when the straddle is too rich vs the edge." />
        <StateWrap state={s4.value} source="event-Kelly · win-prob × payoff/risk">
          <div className="lens-pad"><div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            <KpiTile label="Kelly fraction" value={kel.kelly_frac != null ? (kel.kelly_frac * 100).toFixed(0) + "%" : "—"} tone={kel.kelly_frac > 0 ? "gn" : "rd"} sub={kel.cap_reason ? kel.cap_reason.replace(/_/g, " ") : "raw f*"} />
            <KpiTile label="Payoff" value={erPct(kel.payoff_pct, 2)} tone="gn" sub="if right" />
            <KpiTile label="Risk (implied move)" value={erPct(kel.risk_pct, 2)} tone="rd" sub="if wrong" />
            <KpiTile label="Liquidity (ADV)" value={advFmt} tone="ink" sub="60d $-vol" />
          </div></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="amb" cells={[
            { lens: "Earnings", verdict: `${row.days_to_earnings} d`, tone: "amb", note: `${row.before_after || ""} · ${row.report_date || ""}` },
            { lens: "Beat", verdict: row.tier || "—", tone: tierTone, note: `score ${row.beat_score != null ? row.beat_score.toFixed(0) : "—"} · ${kel.win_prob != null ? (kel.win_prob * 100).toFixed(0) + "% win" : "—"}` },
            { lens: "Implied move", verdict: `±${erPct(im.implied_move_pct, 1)}`, tone: "amb", note: "straddle " + erMoney(im.straddle_cost) },
            { lens: "Event size", verdict: kel.kelly_frac > 0 ? (kel.kelly_frac * 100).toFixed(0) + "%" : "0%", tone: kel.kelly_frac > 0 ? "gn" : "rd", note: kel.cap_reason ? kel.cap_reason.replace(/_/g, " ") : "Kelly" },
            { lens: "History", verdict: hist.pattern || "—", tone: hist.rate >= 70 ? "gn" : "amb", note: `${hist.rate != null ? hist.rate.toFixed(0) + "%" : "—"} beat` },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Earnings</span>
        <span className="mono">
          {row.tier ? <b className={`kpi-tone--${tierTone}`}>{row.tier}</b> : null} beat-setup · reports <b>{row.before_after || ""} {row.report_date || ""}</b> ({row.days_to_earnings}d).
          Options price a <b className="warn">±{erPct(im.implied_move_pct, 1)}</b> move; model win-prob <b className="up">{kel.win_prob != null ? (kel.win_prob * 100).toFixed(0) + "%" : "—"}</b>,
          history <b className="up">{hist.rate != null ? hist.rate.toFixed(0) + "%" : "—"}</b> beat over {hist.n_quarters || "—"}Q.
          {kel.kelly_frac > 0 ? <> Event-Kelly favors a <b className="up">{(kel.kelly_frac * 100).toFixed(0)}%</b> position.</> : <> Straddle too rich vs edge — <b className="dn">event-Kelly 0%</b> (don't pay up).</>}
        </span>
      </div>
    </div>
  );
}

function ImpliedMoveCone() {
  return (
    <svg viewBox="0 0 300 130" width="300" height="130" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="ic-gn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.32" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ic-rd" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="20" y1="65" x2="280" y2="65" stroke="var(--line)" strokeDasharray="3 3" />
      {/* Filled bands */}
      <path d="M 20 65 Q 150 14 280 14 L 280 65 L 20 65 Z" fill="url(#ic-gn)" />
      <path d="M 20 65 Q 150 116 280 116 L 280 65 L 20 65 Z" fill="url(#ic-rd)" />
      {/* Cone outlines */}
      <path d="M 20 65 Q 150 14 280 14" stroke="var(--gn)" strokeWidth="1.6" fill="none"
            style={{ filter: "drop-shadow(0 0 5px var(--gn))" }} />
      <path d="M 20 65 Q 150 116 280 116" stroke="var(--rd)" strokeWidth="1.6" fill="none"
            style={{ filter: "drop-shadow(0 0 5px var(--rd))" }} />
      {/* Today marker */}
      <circle cx="20" cy="65" r="4" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <text x="20" y="128" fontSize="9" className="mono" textAnchor="start" fill="var(--ink-2)">T−11</text>
      {/* ER day */}
      <line x1="230" y1="0" x2="230" y2="130" stroke="var(--amb)" strokeWidth="1.4" strokeDasharray="2 3"
            style={{ filter: "drop-shadow(0 0 4px var(--amb))" }} />
      <rect x="200" y="0" width="62" height="14" rx="7" fill="color-mix(in oklab, var(--amb) 22%, transparent)"
            stroke="var(--amb)" strokeWidth="0.8" />
      <text x="231" y="10" fontSize="8.5" className="mono" textAnchor="middle" fill="var(--amb)" letterSpacing="0.10em">ER · JUN 09</text>
      <text x="276" y="11" fontSize="10" className="mono" textAnchor="end" fill="var(--gn)" fontWeight="500">+6.4%</text>
      <text x="276" y="125" fontSize="10" className="mono" textAnchor="end" fill="var(--rd)" fontWeight="500">−6.4%</text>
    </svg>
  );
}

function ERHistory() {
  const rows = [
    { q: "Q1 FY26", date: "03-Mar-2026", est: 1.50, act: 1.57, eps: "+4.6%", rev: "+2.8%", rx: "+5.4%", cont: "+2.1%", tape: "BEAT+GAP+DRIFT", t: "gn" },
    { q: "Q4 FY25", date: "11-Dec-2025", est: 1.39, act: 1.49, eps: "+7.2%", rev: "+4.1%", rx: "+8.1%", cont: "+3.4%", tape: "BEAT+GAP+DRIFT", t: "gn" },
    { q: "Q3 FY25", date: "04-Sep-2025", est: 1.28, act: 1.33, eps: "+3.9%", rev: "+1.6%", rx: "+1.2%", cont: "−1.8%", tape: "BEAT+FADE", t: "amb" },
    { q: "Q2 FY25", date: "05-Jun-2025", est: 1.20, act: 1.28, eps: "+6.5%", rev: "+3.2%", rx: "+6.2%", cont: "+1.9%", tape: "BEAT+GAP+DRIFT", t: "gn" },
    { q: "Q1 FY25", date: "06-Mar-2025", est: 1.06, act: 1.15, eps: "+8.4%", rev: "+5.0%", rx: "+9.6%", cont: "+4.3%", tape: "BEAT+RUNAWAY", t: "gn" },
    { q: "Q4 FY24", date: "05-Dec-2024", est: 1.03, act: 1.07, eps: "+4.2%", rev: "+1.4%", rx: "+3.8%", cont: "+0.4%", tape: "BEAT+GAP", t: "gn" },
    { q: "Q3 FY24", date: "05-Sep-2024", est: 0.92, act: 0.98, eps: "+6.1%", rev: "+2.3%", rx: "+4.1%", cont: "+1.6%", tape: "BEAT+GAP+DRIFT", t: "gn" },
    { q: "Q2 FY24", date: "06-Jun-2024", est: 0.88, act: 0.93, eps: "+5.7%", rev: "+2.7%", rx: "+3.5%", cont: "+2.6%", tape: "BEAT+GAP+DRIFT", t: "gn" },
  ];
  const sgn = v => v.indexOf("−") === 0 ? "dn" : "up";
  return (
    <div>
      <div className="er-bh-badge"><Pill tone="gn" small dot>8 / 8 BEATS · WR 100%</Pill><span className="mono dim2">avg surprise +5.8% · perfect beat record</span></div>
      <table className="dtable er-bh-tbl">
        <thead>
          <tr>
            <th>Quarter</th><th>Report date</th>
            <th className="r">EPS est</th><th className="r">EPS act</th><th className="r">EPS surp</th>
            <th className="r">Rev surp</th><th className="r">1-day Rx</th><th className="r">5-day cont</th><th>Tape</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="mono"><b>{r.q}</b></td>
              <td className="mono dim">{r.date}</td>
              <td className="r mono tabular dim2">${r.est.toFixed(2)}</td>
              <td className="r mono tabular"><b>${r.act.toFixed(2)}</b></td>
              <td className="r mono tabular up">{r.eps}</td>
              <td className="r mono tabular up">{r.rev}</td>
              <td className={`r mono tabular ${sgn(r.rx)}`}>{r.rx}</td>
              <td className={`r mono tabular ${sgn(r.cont)}`}>{r.cont}</td>
              <td><Pill tone={r.t} small>{r.tape}</Pill></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── §3 · Analyst EPS revisions — leading edge of beat probability ──
function AnalystRevisions() {
  const est = [1.41, 1.42, 1.44, 1.46, 1.48, 1.50];
  const w = 150, hh = 38, mn = Math.min(...est), mx = Math.max(...est);
  const sx = i => 4 + (i / (est.length - 1)) * (w - 8);
  const sy = v => hh - 4 - ((v - mn) / (mx - mn || 1)) * (hh - 8);
  const rows = [
    { p: "Next Q · Q2 FY26", now: "$1.52", ago: "$1.44", d: "+5.6%", up: 9, dn: 1 },
    { p: "FY26", now: "$6.05", ago: "$5.78", d: "+4.7%", up: 11, dn: 2 },
    { p: "FY27", now: "$7.10", ago: "$6.80", d: "+4.4%", up: 8, dn: 1 },
  ];
  return (
    <div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="Consensus EPS · next Q" value="$1.50" tone="ink" sub="from $1.44 · 90d ago" />
        <KpiTile label="90-day revision" value="+6.4%" tone="gn" sub="estimate raised" />
        <KpiTile label="Up : Down revisions" value="9 : 1" tone="gn" sub="last 90 days" />
        <KpiTile label="Revision trend" value="RISING" tone="gn" sub="bullish lead" />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
        <div>
          <div className="label-cap" style={{ marginBottom: 4 }}>Consensus estimate · 6-mo trend</div>
          <svg width={w} height={hh} style={{ display: "block" }}>
            <defs><linearGradient id="er-rev-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.3" /><stop offset="100%" stopColor="var(--gn)" stopOpacity="0" /></linearGradient></defs>
            <path d={`M ${sx(0)},${hh - 4} L ${est.map((v, i) => `${sx(i)},${sy(v)}`).join(" L ")} L ${sx(est.length - 1)},${hh - 4} Z`} fill="url(#er-rev-g)" />
            <polyline points={est.map((v, i) => `${sx(i)},${sy(v)}`).join(" ")} fill="none" stroke="var(--gn)" strokeWidth="1.8" />
            <circle cx={sx(est.length - 1)} cy={sy(est[est.length - 1])} r="3" fill="var(--gn)" />
          </svg>
        </div>
        <table className="dtable" style={{ flex: 1, minWidth: 280 }}>
          <thead><tr><th>Horizon</th><th className="r">Now</th><th className="r">90d ago</th><th className="r">Δ</th><th className="r">Up/Dn</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="mono"><b>{r.p}</b></td>
                <td className="r mono tabular">{r.now}</td>
                <td className="r mono tabular dim2">{r.ago}</td>
                <td className="r mono tabular up">{r.d}</td>
                <td className="r mono tabular"><span className="up">{r.up}</span><span className="dim2">/</span><span className="dn">{r.dn}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mono dim2" style={{ marginTop: 10, fontSize: 11, lineHeight: 1.5 }}>
        Estimate revisions are the single best leading indicator of beats — <b className="up">rising consensus</b> (+6.4% over 90d, 9 up vs 1 down) plus positive Zacks ESP (+4.1%) precede upside surprises. The drift in estimates is the early tell before the print.
      </div>
    </div>
  );
}

// ─── §1 · ER countdown + implied-move cone cockpit ──────────────────
function ERCockpit({ row }) {
  const b = (row && row.breakdown) || {};
  const imb = b.implied_move || {}, hist = b.historical || {}, kel = b.kelly_sizing || {};
  const cur = imb.spot || 100;
  const [ref, w] = useWidth(640);
  const im = (imb.implied_move_pct || 0) / 100; // 1σ implied move (real)
  const patt = (hist.pattern || "").split("");
  // cone geometry
  const h = 188, padT = 22, padB = 30, padR = 62, padL = 10;
  const plotW = Math.max(120, w - padL - padR), plotR = padL + plotW, plotH = h - padT - padB;
  const erX = padL + plotW * 0.60;
  const vmax = cur * (1 + 2 * im) * 1.012, vmin = cur * (1 - 2 * im) * 0.988;
  const yOf = v => padT + plotH - ((v - vmin) / (vmax - vmin)) * plotH;
  const lvls = [["+2σ", cur * (1 + 2 * im)], ["+1σ", cur * (1 + im)], ["spot", cur], ["−1σ", cur * (1 - im)], ["−2σ", cur * (1 - 2 * im)]];
  return (
    <div className="er-ck">
      <div className="er-ck-top">
        <span className="er-ck-title mono">⌛ ER COUNTDOWN · IMPLIED-MOVE CONE</span>
        <span className="er-ck-meta mono">{(row && row.ticker) || ""} · beat-score <b>{row && row.beat_score != null ? row.beat_score.toFixed(0) : "—"}</b> · tier <b>{(row && row.tier) || "—"}</b></span>
      </div>
      <div className="er-ck-body">
        <div className="er-ck-days">
          <div className="label-cap">Days to report</div>
          <div className="er-ck-days-num mono">{row && row.days_to_earnings != null ? row.days_to_earnings : "—"}</div>
          <div className="mono dim2">{(row && row.report_date) || "—"} · {(row && row.before_after) || ""}</div>
        </div>
        <div className="er-ck-cone" ref={ref}>
          <svg width={w} height={h}>
            <defs>
              <linearGradient id="er-cone-g" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="var(--violet)" stopOpacity="0.05" /><stop offset="100%" stopColor="var(--violet)" stopOpacity="0.22" /></linearGradient>
            </defs>
            <text x={padL} y={14} fontSize="9" className="mono" fill="var(--ink-3)" style={{ letterSpacing: "0.1em" }}>TODAY · ${cur.toFixed(2)}  →  ER  →  ER+7D · 1σ &amp; 2σ BANDS</text>
            {/* 2σ then 1σ cone */}
            <path d={`M ${erX},${yOf(cur)} L ${plotR},${yOf(cur * (1 + 2 * im))} L ${plotR},${yOf(cur * (1 - 2 * im))} Z`} fill="url(#er-cone-g)" opacity="0.55" />
            <path d={`M ${erX},${yOf(cur)} L ${plotR},${yOf(cur * (1 + im))} L ${plotR},${yOf(cur * (1 - im))} Z`} fill="var(--violet)" opacity="0.22" />
            {/* spot line + ER marker */}
            <line x1={padL} y1={yOf(cur)} x2={erX} y2={yOf(cur)} stroke="var(--ink-1)" strokeWidth="2" />
            <line x1={erX} y1={yOf(cur)} x2={plotR} y2={yOf(cur)} stroke="var(--copper)" strokeWidth="1.4" strokeDasharray="4 4" />
            <line x1={erX} y1={padT} x2={erX} y2={padT + plotH} stroke="var(--copper)" strokeDasharray="3 3" opacity="0.7" />
            <text x={erX + 5} y={padT + 8} fontSize="9.5" className="mono" fill="var(--copper)" style={{ fontWeight: 700 }}>ER · {(row && row.report_date) || ""}</text>
            <circle cx={padL} cy={yOf(cur)} r="3" fill="var(--ink-1)" />
            {lvls.map(([l, v], i) => (
              <text key={i} x={plotR + 4} y={yOf(v) + 3} fontSize="9" className="mono" fill={`var(--${l === "spot" ? "copper" : "violet"})`} style={{ fontWeight: l === "spot" ? 700 : 500 }}>{l} ${v.toFixed(0)}</text>
            ))}
          </svg>
        </div>
      </div>
      <div className="er-ck-stats">
        <div className="er-ck-stat"><div className="label-cap">Implied move</div><div className="er-ck-stat-v mono amb">±{(cur * im).toFixed(2)}</div><div className="mono dim2">±{(im * 100).toFixed(1)}% · ATM straddle</div></div>
        <div className="er-ck-stat"><div className="label-cap">ATM straddle premium</div><div className="er-ck-stat-v mono">{imb.straddle_cost != null ? "$" + imb.straddle_cost.toFixed(2) : "—"}</div><div className="mono dim2">ATM C+P · exp {imb.expiry_date || "—"}</div></div>
        <div className="er-ck-stat"><div className="label-cap">Beat probability</div><div className="er-ck-stat-v mono gn-c">{kel.win_prob != null ? (kel.win_prob * 100).toFixed(0) + "%" : "—"}</div><div className="mono dim2">model · {hist.rate != null ? hist.rate.toFixed(0) + "% hist" : "—"}</div></div>
      </div>
      <div className="er-ck-bars">
        <div className="er-ck-bars-h"><span className="label-cap">{hist.n_quarters || 0}-Quarter beat pattern</span><span className="mono dim2">beat-rate <b className="up">{hist.rate != null ? hist.rate.toFixed(0) + "%" : "—"}</b> · median surprise <b className="up">+{hist.median_surprise_pct != null ? hist.median_surprise_pct.toFixed(1) : "—"}%</b></span></div>
        <div className="er-ck-bars-row">
          {patt.length ? patt.map((ch, i) => (
            <div key={i} className="er-ck-bar">
              <div className="er-ck-bar-v mono">{ch === "B" ? "✓" : "✕"}</div>
              <div className="er-ck-bar-fill" style={{ height: ch === "B" ? "100%" : "30%", background: ch === "B" ? "var(--gn)" : "var(--rd)" }} />
              <div className="er-ck-bar-q mono dim2">{i + 1}</div>
            </div>
          )) : <div className="mono dim2">no beat history in feed</div>}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// OPTIONS — quant trader's vol cockpit (EODHD + Schwab feeds)
// ────────────────────────────────────────────────────────────
function LensOptions({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("op-1"); const s2 = useStateToggle("op-2");
  const s3 = useStateToggle("op-3"); const s4 = useStateToggle("op-4");
  const s5 = useStateToggle("op-5"); const s6 = useStateToggle("op-6");
  const s7 = useStateToggle("op-7"); const s8 = useStateToggle("op-8");
  const s9 = useStateToggle("op-9");

  return (
    <div className="lens lens--opt">
      <OptionsHero />

      <div className="lens-section">
        <SectionHeader n={1} title="Vol Regime · Cockpit"
          sub="IV term structure · rank · percentile · vol-risk premium"
          style={headerStyle} right={<StateToggle name="op-1" />} />
        <StateWrap state={s1.value} source="EODHD /options · Schwab /markets/options/chains · 30d ATM ladder">
          <div className="lens-pad"><VolCockpit /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Skew · Surface"
          sub="25Δ risk reversal · butterfly · ATM skew per expiry"
          style={headerStyle} right={<StateToggle name="op-2" />} />
        <StateWrap state={s2.value} source="EODHD · per-strike IV reconstructed from chain">
          <div className="lens-pad"><SkewSurface /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Greeks · Position-Adjusted"
          sub="delta · gamma · vega · theta · charm · vanna · dollar-Greeks"
          style={headerStyle} right={<StateToggle name="op-3" />} />
        <StateWrap state={s3.value} source="Schwab /markets/options · Greeks per contract · book aggregated">
          <div className="lens-pad"><GreeksGrid /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Dealer Positioning · GEX"
          sub="gamma exposure by strike · call/put walls · gamma flip · max pain"
          style={headerStyle} right={<StateToggle name="op-4" />} />
        <StateWrap state={s4.value} source="EODHD OI · gamma model (SqueezeMetrics-style)">
          <div className="lens-pad"><GEXChart /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Chain · ATM ±3 · Jul 18"
          sub="Greeks · OI · vol · bid/ask spread"
          style={headerStyle} right={<StateToggle name="op-5" />} />
        <StateWrap state={s5.value} source="Schwab /markets/options/chains · live · ≤30s">
          <div className="lens-pad"><ChainGrid /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Unusual Options Activity"
          sub="volume / OI · premium · sweepers · BTO vs STO inference"
          style={headerStyle} right={<StateToggle name="op-6" />} />
        <StateWrap state={s6.value} source="Schwab /markets/options/movers · time & sales · prop UOA detector">
          <div className="lens-pad"><UOATable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Strategy Matrix"
          sub="comparison · R · prob-of-profit · max loss · max gain · vega-exposure"
          style={headerStyle} right={<StateToggle name="op-7" />} />
        <StateWrap state={s7.value} source="strategy synthesizer · conditional on swing thesis">
          <div className="lens-pad"><StrategyMatrix /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Payoff · Selected Strategy"
          sub="Aug $65/$75 call-spread · vega-neutral at structure-level"
          style={headerStyle} right={<StateToggle name="op-8" />} />
        <StateWrap state={s8.value} source="payoff calc · Greeks-aware">
          <div className="lens-pad"><PayoffDiagram /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={9} title="Pre-ER Vol Crush · Projection"
          sub="historical 4Q IV term-structure crush · short-vol structure suitability"
          style={headerStyle} right={<StateToggle name="op-9" />} />
        <StateWrap state={s9.value} source="EODHD · 4Q IV history · proprietary crush model">
          <div className="lens-pad"><VolCrushProjection /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={10} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="amb" cells={[
            { lens: "Options",  verdict: "RICH",   tone: "amb", note: "IV/HV 1.42 · VRP +14 vol-pts" },
            { lens: "Earnings", verdict: "11 d",   tone: "amb", note: "post-ER crush ≈ −42%" },
            { lens: "Plan",     verdict: "EQUITY", tone: "gn",  note: "stock entry preferred" },
            { lens: "Flow",     verdict: "BULL",   tone: "gn",  note: "+$1.8M call premium 5d" },
            { lens: "GEX",      verdict: "−$84M",  tone: "amb", note: "below flip · vol-amp regime" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Options</span>
        <span className="mono">
          Vol is rich (<b className="warn">IV/HV 1.42</b>) with steep put skew. Equity entry preferred.
          If hedging: <b className="copper">Aug $65/$75 call-spread @ $2.85</b> (2.50R, vega-neutral structure).
          For pure short-vol post-ER: iron condor $62/65/72/75.
        </span>
      </div>
    </div>
  );
}

function OptionsHero() {
  return (
    <div className="hero opt-hero">
      <div className="th-left">
        <div className="label-cap">Vol regime · ARCM · Jul-Aug surface</div>
        <div className="th-score">
          <div className="th-score-num mono">RICH</div>
          <Pill tone="amb" dot>IV/HV 1.42×</Pill>
          <Pill tone="gn" small>VRP +14v</Pill>
          <Pill tone="amb" small>IVR 68% (1y)</Pill>
          <Pill tone="rd" small>Skew steep ↓</Pill>
        </div>
        <div className="th-pill-row">
          <Pill tone="ink" small>IV30 48.2%</Pill>
          <Pill tone="ink" small>IV60 42.4%</Pill>
          <Pill tone="ink" small>HV20 34.1%</Pill>
          <Pill tone="ink" small>Max pain $65</Pill>
          <Pill tone="ink" small>P/C 0.62</Pill>
          <Pill tone="ink" small>GEX −$84M</Pill>
        </div>
      </div>
      <div className="th-right">
        <SkewMini />
      </div>
    </div>
  );
}

function SkewMini() {
  // Quick mini skew curve
  return (
    <svg viewBox="0 0 280 110" width="280" height="110" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="skm-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--violet)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--violet)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="20" y1="90" x2="270" y2="90" stroke="var(--line)" strokeDasharray="3 3" />
      <line x1="145" y1="0" x2="145" y2="110" stroke="var(--copper)" strokeWidth="1.2" strokeDasharray="2 3" />
      <text x="145" y="11" fontSize="8.5" className="mono" fill="var(--copper)" textAnchor="middle" letterSpacing="0.10em">ATM $67</text>
      <path d="M 20 28 Q 75 70, 145 70 Q 215 64, 270 54 L 270 90 L 20 90 Z" fill="url(#skm-fill)" />
      <path d="M 20 28 Q 75 70, 145 70 Q 215 64, 270 54" stroke="var(--violet)" strokeWidth="2" fill="none"
            style={{ filter: "drop-shadow(0 0 6px var(--violet))" }} />
      <circle cx="20"  cy="28" r="3.5" fill="var(--rd)" style={{ filter: "drop-shadow(0 0 7px var(--rd))" }} />
      <circle cx="145" cy="70" r="3.5" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 7px var(--copper))" }} />
      <circle cx="270" cy="54" r="3.5" fill="var(--gn)" style={{ filter: "drop-shadow(0 0 7px var(--gn))" }} />
      <text x="22" y="22" fontSize="9.5" className="mono" fill="var(--rd)">62% · 25Δ put</text>
      <text x="266" y="48" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">44% · 25Δ call</text>
      <text x="270" y="106" fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)" letterSpacing="0.10em">25ΔRR −18 vol-pts</text>
    </svg>
  );
}

// ─── §1 Vol Cockpit ──────────────────────────────────────────────────
function VolCockpit() {
  return (
    <div className="vcp">
      {/* Term structure curve */}
      <div className="vcp-block">
        <div className="vcp-block-hdr">
          <span className="label-cap">Term structure · ATM IV</span>
          <span className="mono dim2">contango · back-month cheaper</span>
        </div>
        <TermStructureChart />
      </div>

      {/* IV rank + percentile + VRP gauges */}
      <div className="vcp-block">
        <div className="vcp-block-hdr">
          <span className="label-cap">Vol stack</span>
          <span className="mono dim2">vs own history · vs realized</span>
        </div>
        <div className="kpi-row" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
          <KpiTile label="IV30" value="48.2%" tone="amb" sub="vs HV20 34.1%" />
          <KpiTile label="IV/HV" value="1.42×" tone="amb" sub="sell-vol favorable" />
          <KpiTile label="IV rank 1y" value="68%" tone="amb" sub="above median" />
          <KpiTile label="IV percentile" value="74%" tone="amb" sub="74% of trading days lower" />
          <KpiTile label="VRP" value="+14.1v" tone="gn" sub="vol-risk premium" />
          <KpiTile label="Realized 4Q" value="±5.8%" tone="ink" sub="median ER reaction" />
        </div>
      </div>
    </div>
  );
}

function TermStructureChart() {
  const data = [
    { dte: 11, iv: 56.8, tag: "Pre-ER",   tone: "amb" },
    { dte: 18, iv: 48.2, tag: "Jul 18",   tone: "copper" },
    { dte: 46, iv: 42.4, tag: "Aug 15",   tone: "ink" },
    { dte: 81, iv: 40.1, tag: "Sep 19",   tone: "ink" },
    { dte: 109,iv: 38.2, tag: "Oct 17",   tone: "ink" },
    { dte: 144,iv: 36.8, tag: "Nov 21",   tone: "ink" },
    { dte: 200,iv: 35.2, tag: "Jan 16",   tone: "ink" },
  ];
  const w = 460, h = 160, padT = 18, padB = 28, padL = 36, padR = 14;
  const xMax = Math.max(...data.map(d => d.dte));
  const yMin = 32, yMax = 60;
  const x = (dte) => padL + (dte / xMax) * (w - padL - padR);
  const y = (iv)  => padT + (1 - (iv - yMin) / (yMax - yMin)) * (h - padT - padB);
  const pts = data.map(d => [x(d.dte), y(d.iv)]);
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="ts-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--amb)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--amb)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="var(--glass-line)" />
      <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="var(--glass-line)" />
      {[35, 40, 45, 50, 55].map(v => (
        <g key={v}>
          <line x1={padL} y1={y(v)} x2={w - padR} y2={y(v)} stroke="var(--glass-line)" strokeDasharray="2 3" opacity="0.5" />
          <text x={padL - 6} y={y(v) + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">{v}%</text>
        </g>
      ))}
      <path d={`M ${pts.map(p => p.join(",")).join(" L ")} L ${w - padR} ${h - padB} L ${padL} ${h - padB} Z`} fill="url(#ts-fill)" />
      <polyline points={pts.map(p => p.join(",")).join(" ")} stroke="var(--amb)" strokeWidth="2" fill="none" strokeLinejoin="round"
                style={{ filter: "drop-shadow(0 0 5px var(--amb))" }} />
      {data.map((d, i) => (
        <g key={i}>
          <circle cx={x(d.dte)} cy={y(d.iv)} r="3.5" fill={`var(--${d.tone})`}
                  style={{ filter: `drop-shadow(0 0 6px var(--${d.tone}))` }} />
          <text x={x(d.dte)} y={y(d.iv) - 8} fontSize="9" className="mono" fill={`var(--${d.tone})`} textAnchor="middle">{d.iv.toFixed(1)}</text>
        </g>
      ))}
      {data.map((d, i) => (
        <text key={`x${i}`} x={x(d.dte)} y={h - padB + 14} fontSize="9" className="mono" fill="var(--ink-3)" textAnchor="middle">
          {d.dte}d
        </text>
      ))}
      {/* ER marker */}
      <rect x={x(11) - 22} y={padT - 14} width="44" height="11" rx="5.5" fill="color-mix(in oklab, var(--amb) 22%, transparent)" stroke="var(--amb)" strokeWidth="0.8" />
      <text x={x(11)} y={padT - 5} fontSize="8" className="mono" textAnchor="middle" fill="var(--amb)" letterSpacing="0.10em">ER 11d</text>
    </svg>
  );
}

// ─── §2 Skew Surface ─────────────────────────────────────────────────
function SkewSurface() {
  return (
    <div className="skew-grid">
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="25ΔRR · Jul 18" value="−18.0v" tone="rd"  sub="put skew · steep" />
        <KpiTile label="25ΔRR · Aug 15" value="−12.4v" tone="amb" sub="moderating" />
        <KpiTile label="25ΔBF · Jul 18" value="+2.8v"  tone="amb" sub="wings priced rich" />
        <KpiTile label="ATM skew · Jul" value="−1.2v"  tone="ink" sub="symmetric" />
      </div>
      <SkewCurve />
      <div className="mono dim" style={{ fontSize: 11 }}>
        Put skew steepened over the past 5 sessions (likely ER-related hedging demand).
        Right tail (call wing) becomes attractive for short premium if thesis intact.
      </div>
    </div>
  );
}

function SkewCurve() {
  const w = 580, h = 170, padT = 14, padB = 28, padL = 36, padR = 14;
  // strikes 56..82 (deltas from -25 put to +25 call)
  const strikes = [56, 59, 62, 65, 67, 70, 73, 76, 79, 82];
  // Jul 18 (steep), Aug 15 (less steep), Sep 19 (flat)
  const expiries = [
    { name: "Jul 18 · 18d", iv: [62, 58, 53, 48, 47, 46, 47, 48, 49, 50], color: "var(--rd)" },
    { name: "Aug 15 · 46d", iv: [54, 50, 46, 43, 42, 42, 42, 43, 43, 44], color: "var(--amb)" },
    { name: "Sep 19 · 81d", iv: [48, 45, 42, 40, 40, 40, 40, 40, 40, 40], color: "var(--gn)" },
  ];
  const xMin = 56, xMax = 82;
  const yMin = 36, yMax = 66;
  const x = (k) => padL + ((k - xMin) / (xMax - xMin)) * (w - padL - padR);
  const y = (iv) => padT + (1 - (iv - yMin) / (yMax - yMin)) * (h - padT - padB);

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ overflow: "visible" }}>
      <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="var(--glass-line)" />
      <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="var(--glass-line)" />
      {[40, 45, 50, 55, 60].map(v => (
        <g key={v}>
          <line x1={padL} y1={y(v)} x2={w - padR} y2={y(v)} stroke="var(--glass-line)" strokeDasharray="2 3" opacity="0.5" />
          <text x={padL - 6} y={y(v) + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">{v}%</text>
        </g>
      ))}
      {/* ATM line */}
      <line x1={x(67)} y1={padT} x2={x(67)} y2={h - padB} stroke="var(--copper)" strokeDasharray="2 3" opacity="0.6" />
      <text x={x(67)} y={padT - 2} fontSize="9" className="mono" fill="var(--copper)" textAnchor="middle">ATM $67</text>

      {expiries.map((e, ei) => {
        const pts = strikes.map((k, i) => [x(k), y(e.iv[i])]);
        return (
          <g key={ei}>
            <polyline points={pts.map(p => p.join(",")).join(" ")} stroke={e.color} strokeWidth="1.8" fill="none"
                      style={{ filter: `drop-shadow(0 0 4px ${e.color})` }} />
            {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="2.5" fill={e.color} />)}
          </g>
        );
      })}
      {strikes.map(k => (
        <text key={k} x={x(k)} y={h - padB + 14} fontSize="9" className="mono" textAnchor="middle" fill="var(--ink-3)">
          ${k}
        </text>
      ))}
      {/* Legend */}
      <g transform={`translate(${padL + 8}, ${padT + 6})`}>
        {expiries.map((e, i) => (
          <g key={i} transform={`translate(0, ${i * 14})`}>
            <rect width="14" height="3" fill={e.color} y="4" rx="1.5" />
            <text x="20" y="9" fontSize="9.5" className="mono" fill="var(--ink-1)">{e.name}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

// ─── §3 Greeks Grid ──────────────────────────────────────────────────
function GreeksGrid() {
  const rows = [
    { g: "Δ Delta",    raw: 110,    dollar: "+$7,416", note: "1.0 per equity sh · long stock", tone: "copper" },
    { g: "Γ Gamma",    raw: 0,      dollar: "$0",      note: "linear · no curvature",          tone: "ink" },
    { g: "𝓥 Vega",     raw: 0,      dollar: "$0",      note: "no vol exposure (stock)",        tone: "ink" },
    { g: "Θ Theta",    raw: 0,      dollar: "$0",      note: "no decay",                       tone: "ink" },
    { g: "𝜌 Rho",      raw: 0,      dollar: "$0",      note: "no rate sensitivity",            tone: "ink" },
    { g: "Charm",      raw: 0,      dollar: "$0",      note: "—",                              tone: "ink" },
  ];
  const altRows = [
    { g: "Δ Delta",    raw: 62,     dollar: "+$4,183", note: "0.62 net (call-spread)",         tone: "copper" },
    { g: "Γ Gamma",    raw: 0.012,  dollar: "+$81",    note: "long gamma · benefits move",     tone: "gn" },
    { g: "𝓥 Vega",     raw: -3.4,   dollar: "−$230/v",  note: "short vol · IV crush helps",     tone: "gn" },
    { g: "Θ Theta",    raw: -1.20,  dollar: "−$1.20/d", note: "−40 d decay over 33d hold",      tone: "amb" },
    { g: "𝜌 Rho",      raw: 0.18,   dollar: "+$18/bp",  note: "tiny rate exposure",             tone: "ink" },
    { g: "Charm",      raw: -0.04,  dollar: "−$2.7/d",  note: "delta-decay accelerates near ER",tone: "amb" },
  ];
  return (
    <div className="greeks">
      <div className="greeks-col">
        <div className="greeks-hdr label-cap">Equity · 110 sh long</div>
        <table className="dtable">
          <thead><tr><th>Greek</th><th className="r">Raw</th><th className="r">$ Greek</th><th>Read</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="mono"><b>{r.g}</b></td>
                <td className="r mono tabular">{r.raw}</td>
                <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.dollar}</td>
                <td className="mono dim">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="greeks-col">
        <div className="greeks-hdr label-cap">Alt · Aug $65/$75 call-spread</div>
        <table className="dtable">
          <thead><tr><th>Greek</th><th className="r">Raw</th><th className="r">$ Greek</th><th>Read</th></tr></thead>
          <tbody>
            {altRows.map((r, i) => (
              <tr key={i}>
                <td className="mono"><b>{r.g}</b></td>
                <td className="r mono tabular">{r.raw}</td>
                <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.dollar}</td>
                <td className="mono dim">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── §4 GEX (gamma exposure) ─────────────────────────────────────────
function GEXChart() {
  const strikes = [60, 62, 64, 65, 66, 67, 68, 70, 72, 75];
  // Negative GEX = puts dominate (vol-amplifying); positive = calls (vol-suppressing)
  const gex = [-28, -42, -22, +18, -34, -54, -18, +62, +48, +24];
  const cur = 67.42;
  const maxAbs = Math.max(...gex.map(Math.abs));
  const w = 580, h = 200, padT = 18, padB = 36, padL = 40, padR = 14;
  const innerH = h - padT - padB;
  const yMid = padT + innerH / 2;
  const yFor = (v) => yMid - (v / maxAbs) * (innerH / 2);
  const x = (k, i) => padL + i * ((w - padL - padR) / strikes.length) + ((w - padL - padR) / strikes.length) / 2;
  const barW = ((w - padL - padR) / strikes.length) * 0.7;

  // Find call wall (largest positive GEX), put wall (largest negative)
  const callWallIdx = gex.indexOf(Math.max(...gex));
  const putWallIdx = gex.indexOf(Math.min(...gex));
  // Gamma flip: where cumulative GEX crosses zero
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="gex-gn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="1" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0.3" />
        </linearGradient>
        <linearGradient id="gex-rd" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="1" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.3" />
        </linearGradient>
      </defs>
      <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="var(--glass-line)" />
      <line x1={padL} y1={yMid} x2={w - padR} y2={yMid} stroke="var(--ink-3)" strokeDasharray="2 3" />
      <text x={padL - 6} y={yMid + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">$0</text>
      <text x={padL - 6} y={padT + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--gn)">+{maxAbs}M</text>
      <text x={padL - 6} y={h - padB + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--rd)">−{maxAbs}M</text>

      {/* Spot price marker */}
      <line x1={padL + ((cur - 60) / (75 - 60)) * (w - padL - padR)} y1={padT - 4}
            x2={padL + ((cur - 60) / (75 - 60)) * (w - padL - padR)} y2={h - padB}
            stroke="var(--copper)" strokeWidth="1.4" strokeDasharray="3 3"
            style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />

      {strikes.map((k, i) => {
        const v = gex[i];
        const isCall = i === callWallIdx;
        const isPut = i === putWallIdx;
        const y0 = v >= 0 ? yFor(v) : yMid;
        const hBar = Math.abs(yFor(v) - yMid);
        return (
          <g key={k}>
            <rect x={x(k, i) - barW / 2} y={y0} width={barW} height={Math.max(2, hBar)}
                  fill={v >= 0 ? "url(#gex-gn)" : "url(#gex-rd)"}
                  style={{ filter: (isCall || isPut) ? `drop-shadow(0 0 8px ${v >= 0 ? "var(--gn)" : "var(--rd)"})` : "none" }} />
            <text x={x(k, i)} y={h - padB + 14} fontSize="9" className="mono" textAnchor="middle"
                  fill={k === Math.round(cur) ? "var(--copper)" : "var(--ink-3)"}>${k}</text>
            <text x={x(k, i)} y={v >= 0 ? yFor(v) - 4 : yFor(v) + 11} fontSize="9" className="mono" textAnchor="middle"
                  fill={v >= 0 ? "var(--gn)" : "var(--rd)"}>{v >= 0 ? "+" : ""}{v}</text>
            {isCall && (
              <text x={x(k, i)} y={yFor(v) - 16} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--gn)" letterSpacing="0.10em">CALL WALL</text>
            )}
            {isPut && (
              <text x={x(k, i)} y={yFor(v) + 24} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--rd)" letterSpacing="0.10em">PUT WALL</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function VolCrushProjection() {
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
      <KpiTile label="Pre-ER IV (current)" value="56.8%" tone="amb" sub="Jul 18 · ATM straddle" />
      <KpiTile label="Post-ER IV (proj.)"  value="33.0%" tone="gn"  sub="median 4Q crush −42%" />
      <KpiTile label="Crush $-value · ATM" value="+$1.84" tone="gn"  sub="per share short straddle" />
      <KpiTile label="Short-vol PoP"       value="64%"   tone="gn"  sub="iron condor 62/65/72/75" />
    </div>
  );
}

function IVSmile() {
  return (
    <svg viewBox="0 0 280 110" width="280" height="110" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="ivs-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--violet)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--violet)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="20" y1="90" x2="270" y2="90" stroke="var(--line)" strokeDasharray="3 3" />
      <line x1="145" y1="0" x2="145" y2="110" stroke="var(--copper)" strokeWidth="1.2" strokeDasharray="2 3"
            style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
      <rect x="118" y="0" width="54" height="14" rx="7" fill="color-mix(in oklab, var(--copper) 18%, transparent)" stroke="var(--copper)" strokeWidth="0.8" />
      <text x="145" y="10" fontSize="8.5" className="mono" fill="var(--copper)" textAnchor="middle" letterSpacing="0.10em">ATM $67</text>
      <path d="M 20 38 Q 80 78, 145 70 Q 210 64, 270 50 L 270 90 L 20 90 Z" fill="url(#ivs-fill)" />
      <path d="M 20 38 Q 80 78, 145 70 Q 210 64, 270 50" stroke="var(--violet)" strokeWidth="1.8" fill="none"
            style={{ filter: "drop-shadow(0 0 6px var(--violet))" }} />
      <circle cx="20"  cy="38" r="3" fill="var(--rd)" style={{ filter: "drop-shadow(0 0 6px var(--rd))" }} />
      <circle cx="145" cy="70" r="3" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 6px var(--copper))" }} />
      <circle cx="270" cy="50" r="3" fill="var(--gn)" style={{ filter: "drop-shadow(0 0 6px var(--gn))" }} />
      <text x="22" y="34" fontSize="9.5" className="mono" fill="var(--rd)">put · 62%</text>
      <text x="266" y="46" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">call · 44%</text>
    </svg>
  );
}

function UOATable() {
  const rows = [
    { t: "13:52", side: "CALL", strike: "$70", exp: "Jul 18", prem: "$1.42", vol: 4_280, oi: 1_120, note: "BTO · 3.8× OI", tone: "gn" },
    { t: "12:14", side: "CALL", strike: "$72.5", exp: "Aug 15", prem: "$1.10", vol: 2_140, oi: 480, note: "BTO · sweeper", tone: "gn" },
    { t: "11:08", side: "PUT",  strike: "$62.5", exp: "Jul 18", prem: "$0.88", vol: 1_240, oi: 940, note: "Hedge buy", tone: "amb" },
    { t: "10:42", side: "CALL", strike: "$67.5", exp: "Jun 20", prem: "$1.86", vol: 1_960, oi: 620, note: "Pre-ER buy", tone: "gn" },
  ];
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Time</th><th>Side</th><th>Strike</th><th>Exp</th>
          <th className="r">Prem</th><th className="r">Vol</th><th className="r">OI</th><th>Note</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="mono dim">{r.t}</td>
            <td><Pill tone={r.side === "CALL" ? "gn" : "rd"} small>{r.side}</Pill></td>
            <td className="mono"><b>{r.strike}</b></td>
            <td className="mono dim">{r.exp}</td>
            <td className="r mono tabular">{r.prem}</td>
            <td className="r mono tabular">{r.vol.toLocaleString()}</td>
            <td className="r mono tabular dim">{r.oi.toLocaleString()}</td>
            <td className={`mono ${r.tone === "gn" ? "up" : "warn"}`}>{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ChainGrid() {
  const strikes = [65, 66, 67, 68, 70];
  const cur = 67.42;
  return (
    <table className="dtable chain">
      <thead>
        <tr>
          <th colSpan="4" className="ch-side-c">CALLS</th>
          <th>Strike</th>
          <th colSpan="4" className="ch-side-p">PUTS</th>
        </tr>
        <tr>
          <th>OI</th><th>Vol</th><th>IV</th><th className="r">Bid/Ask</th>
          <th></th>
          <th className="r">Bid/Ask</th><th>IV</th><th>Vol</th><th>OI</th>
        </tr>
      </thead>
      <tbody>
        {strikes.map(k => {
          const itm = k <= cur;
          return (
            <tr key={k} className={k === Math.round(cur) ? "is-current" : ""}>
              <td className="mono dim">{(2400 - k * 12).toLocaleString()}</td>
              <td className="mono">{(740 - k * 8).toLocaleString()}</td>
              <td className="mono">{(42 + (cur - k) * 1.2).toFixed(0)}%</td>
              <td className={`r mono tabular ${itm ? "up" : "dim"}`}>{Math.max(0.05, cur - k + 1.4).toFixed(2)} / {(Math.max(0.10, cur - k + 1.5)).toFixed(2)}</td>
              <td className="mono ch-strike"><b>${k}</b></td>
              <td className={`r mono tabular ${!itm ? "up" : "dim"}`}>{Math.max(0.05, k - cur + 1.3).toFixed(2)} / {Math.max(0.10, k - cur + 1.4).toFixed(2)}</td>
              <td className="mono">{(44 + (k - cur) * 1.4).toFixed(0)}%</td>
              <td className="mono">{(380 + k * 6).toLocaleString()}</td>
              <td className="mono dim">{(1100 + k * 12).toLocaleString()}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function StrategyMatrix() {
  const rows = [
    { name: "Equity · BUY-STOP",          R: "1.74", maxL: "$420", maxG: "open", pref: true, note: "primary" },
    { name: "Aug $65/$75 call-spread",   R: "2.50", maxL: "$285", maxG: "$715", pref: false, note: "defined-risk alt" },
    { name: "Aug $65 long call",         R: "2.10", maxL: "$510", maxG: "open", pref: false, note: "high IV — costly" },
    { name: "Collar (long stock + Aug 62/72)", R: "0.95", maxL: "$220", maxG: "$385", pref: false, note: "if hedging long" },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Strategy</th><th className="r">R</th><th className="r">Max Loss</th><th className="r">Max Gain</th><th>Note</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={r.pref ? "is-current" : ""}>
            <td className="mono"><b>{r.name}</b></td>
            <td className="r mono tabular copper">{r.R}</td>
            <td className="r mono tabular dn">{r.maxL}</td>
            <td className="r mono tabular up">{r.maxG}</td>
            <td className="mono dim">{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PayoffDiagram() {
  // Bull call spread $65/$75 paid $2.85, 1 contract = 100 sh
  const w = 580, h = 200, padT = 22, padB = 32, padL = 24, padR = 60;
  const minPx = 58, maxPx = 80;
  const cost = 2.85, low = 65, high = 75;
  const innerH = h - padT - padB;
  const x = (p) => padL + ((p - minPx) / (maxPx - minPx)) * (w - padL - padR);
  const pnlAt = (px) => (Math.min(high - low, Math.max(0, px - low)) - cost) * 100;
  const samples = [];
  for (let p = minPx; p <= maxPx; p += 0.25) samples.push([p, pnlAt(p)]);
  const pnls = samples.map(s => s[1]);
  const pnlMin = Math.min(...pnls) * 1.2, pnlMax = Math.max(...pnls) * 1.2;
  const y = (pnl) => padT + innerH - ((pnl - pnlMin) / (pnlMax - pnlMin)) * innerH;
  const y0 = y(0);
  const pts = samples.map(([p, pl]) => [x(p), y(pl)]);
  const breakeven = low + cost;
  const maxLossY = y(pnlAt(minPx));
  const maxGainY = y(pnlAt(maxPx));

  return (
    <div className="payoff-block">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ overflow: "visible" }}>
        <defs>
          <linearGradient id="pd-gn" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.40" />
            <stop offset="100%" stopColor="var(--gn)" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="pd-rd" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.40" />
            <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.02" />
          </linearGradient>
          <clipPath id="pd-clip-gn"><rect x="0" y="0" width={w} height={y0} /></clipPath>
          <clipPath id="pd-clip-rd"><rect x="0" y={y0} width={w} height={h - y0} /></clipPath>
        </defs>

        {/* Axes */}
        <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="var(--glass-line)" />
        <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="var(--glass-line)" />
        <line x1={padL} y1={y0} x2={w - padR} y2={y0} stroke="var(--ink-3)" strokeDasharray="3 3" opacity="0.5" />

        {/* Gradient fills */}
        <g clipPath="url(#pd-clip-gn)">
          <path d={`M ${padL} ${y0} L ${pts.map(p => p.join(",")).join(" L ")} L ${w - padR} ${y0} Z`} fill="url(#pd-gn)" />
        </g>
        <g clipPath="url(#pd-clip-rd)">
          <path d={`M ${padL} ${y0} L ${pts.map(p => p.join(",")).join(" L ")} L ${w - padR} ${y0} Z`} fill="url(#pd-rd)" />
        </g>

        {/* Strike verticals */}
        <line x1={x(low)} y1={padT - 4} x2={x(low)} y2={h - padB} stroke="var(--copper)" strokeWidth="1.4" strokeDasharray="3 3"
              style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
        <line x1={x(high)} y1={padT - 4} x2={x(high)} y2={h - padB} stroke="var(--gn)" strokeWidth="1.4" strokeDasharray="3 3"
              style={{ filter: "drop-shadow(0 0 4px var(--gn))" }} />
        <line x1={x(breakeven)} y1={padT - 4} x2={x(breakeven)} y2={h - padB} stroke="var(--ink-3)" strokeWidth="0.8" strokeDasharray="2 4" />

        {/* Payoff curve */}
        <polyline points={pts.map(p => p.join(",")).join(" ")} stroke="var(--ink)" strokeWidth="2.2" fill="none" strokeLinejoin="round"
                  style={{ filter: "drop-shadow(0 0 6px color-mix(in oklab, var(--copper) 60%, transparent))" }} />

        {/* Anchor dots */}
        <circle cx={x(low)} cy={y(pnlAt(low))} r="4" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
        <circle cx={x(high)} cy={y(pnlAt(high))} r="4" fill="var(--gn)" style={{ filter: "drop-shadow(0 0 8px var(--gn))" }} />
        <circle cx={x(breakeven)} cy={y0} r="3" fill="var(--ink-2)" />

        {/* Pill callouts */}
        <PayoffCallout x={x(low)}      y={padT - 4} label="$65 BUY" tone="copper" />
        <PayoffCallout x={x(high)}     y={padT - 4} label="$75 SELL" tone="gn" />
        <PayoffCallout x={x(breakeven)} y={padT - 4} label={`BE $${breakeven.toFixed(2)}`} tone="amb" />

        {/* Axis labels bottom */}
        {[58, 65, 70, 75, 80].map(p => (
          <text key={p} x={x(p)} y={h - padB + 14} fontSize="9.5" className="mono" textAnchor="middle" fill="var(--ink-3)">${p}</text>
        ))}

        {/* Right axis: max P&L */}
        <text x={w - padR + 6} y={maxGainY + 3} fontSize="10" className="mono" fill="var(--gn)">+$715</text>
        <text x={w - padR + 6} y={maxLossY + 3} fontSize="10" className="mono" fill="var(--rd)">−$285</text>
        <text x={w - padR + 6} y={y0 + 3} fontSize="10" className="mono" fill="var(--ink-3)">$0</text>

        {/* Title eyebrow */}
        <text x={padL} y={padT - 8} fontSize="9.5" className="mono" fill="var(--ink-3)" letterSpacing="0.12em">
          BULL CALL SPREAD · AUG $65 / $75 · 1 contract · cost $2.85
        </text>
      </svg>

      <div className="payoff-legend">
        <span className="mono"><b className="up">Max gain</b> $715 · at $75+</span>
        <span className="mono"><b className="dn">Max loss</b> $285 · below $65</span>
        <span className="mono"><b className="warn">Breakeven</b> ${breakeven.toFixed(2)}</span>
        <span className="mono"><b className="copper">R</b> 2.50</span>
      </div>
    </div>
  );
}

window.LensEarnings = LensEarnings;
window.LensOptions = LensOptions;
