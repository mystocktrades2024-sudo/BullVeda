// lens-portfolio.jsx + lens-tape.jsx

// ────────────────────────────────────────────────────────────
// PORTFOLIO — held state, simulator, correlation, sleep-test
// ────────────────────────────────────────────────────────────
function LensPortfolio({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("pf-1"); const s2 = useStateToggle("pf-2");
  const s3 = useStateToggle("pf-3"); const s4 = useStateToggle("pf-4");
  const s5 = useStateToggle("pf-5");

  return (
    <div className="lens lens--pf">
      <div className="hero pf-hero">
        <div className="th-left">
          <div className="label-cap">Position fit · post-fill</div>
          <div className="th-score">
            <div className="th-score-num mono">FIT</div>
            <Pill tone="gn" dot>within all gates</Pill>
          </div>
          <div className="th-pill-row">
            <Pill tone="gn" small>NAV use 6.8% / 7.0% cap</Pill>
            <Pill tone="gn" small>Correl-to-book 0.34</Pill>
            <Pill tone="amb" small>Materials 18% sector</Pill>
            <Pill tone="gn" small>Tax: long-term eligible</Pill>
          </div>
        </div>
        <div className="th-right">
          <BookSparkline />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Held-Position State"
          sub="cash · positions · open R · NAV"
          style={headerStyle} right={<StateToggle name="pf-1" />} />
        <StateWrap state={s1.value} source="portfolio_state · paper account">
          <div className="lens-pad"><HeldState /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Position Simulator"
          sub="live R:R · sizing · NAV-risk · what-if 1× / 1.5× / 2× size"
          style={headerStyle} right={<StateToggle name="pf-2" />} />
        <StateWrap state={s2.value} source="simulator · portfolio_state">
          <div className="lens-pad"><PositionSim ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Correlation to Book"
          sub="rolling 60-day · per-position pairwise"
          style={headerStyle} right={<StateToggle name="pf-3" />} />
        <StateWrap state={s3.value} source="correlation matrix · 60d">
          <div className="lens-pad"><CorrTable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Factor Exposure · Sector Allocation"
          sub="pre vs post fill · vs household policy"
          style={headerStyle} right={<StateToggle name="pf-4" />} />
        <StateWrap state={s4.value} source="factor decomposition">
          <div className="lens-pad"><FactorPanel /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Sleep-Test · Suitability"
          sub="overnight max-drawdown · ER-week exposure · weekend gap risk"
          style={headerStyle} right={<StateToggle name="pf-5" />} />
        <StateWrap state={s5.value} source="risk engine · scenario sweep">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Max overnight loss" value="−$680" tone="amb" sub="3σ down · post fill" />
              <KpiTile label="Weekend gap risk" value="−$520" tone="amb" sub="historical median 3σ" />
              <KpiTile label="ER-week max" value="−$870" tone="rd" sub="implied move down" />
              <KpiTile label="Sleep score" value="A−" tone="gn" sub="below household tolerance" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="copper" cells={[
            { lens: "Portfolio",  verdict: "FIT",   tone: "gn",  note: "all caps · correl 0.34" },
            { lens: "Risk",       verdict: "OK",    tone: "gn",  note: "VaR within limits" },
            { lens: "Factor",     verdict: "TILT",  tone: "amb", note: "+0.18 momentum exposure" },
            { lens: "Sleep",      verdict: "A−",    tone: "gn",  note: "tolerable overnight" },
            { lens: "Plan",       verdict: "READY", tone: "gn",  note: "pre-sized ticket" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Portfolio</span>
        <span className="mono">
          Adds 6.8% NAV at 0.34 correl · sector still under cap. Fits the book.
          <b className="copper"> Ticket pre-filled for your review.</b>
        </span>
      </div>
    </div>
  );
}

function BookSparkline() {
  const data = [];
  let v = 100;
  for (let i = 0; i < 30; i++) {
    v += (Math.random() - 0.42) * 1.2 + 0.18;
    data.push(v);
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
      <div className="label-cap">Book equity · 30d</div>
      <Sparkline data={data} color="var(--gn)" w={220} h={56} />
      <div className="mono dim2" style={{ fontSize: 11 }}>$108,420 · +1.20% today · max DD −2.1%</div>
    </div>
  );
}

function HeldState() {
  const rows = [
    { sym: "BORA", name: "Bora Industries", qty: 240, entry: 28.40, last: 31.10, openR: "+1.30R", pl: "+$648", days: 8 },
    { sym: "INPR", name: "Inpera Capital",  qty: 180, entry: 41.20, last: 39.80, openR: "−0.42R", pl: "−$252", days: 4 },
    { sym: "FLNX", name: "Felinex Tech",    qty: 60,  entry: 162.00, last: 168.40, openR: "+0.71R", pl: "+$384", days: 12 },
  ];
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Sym</th><th>Name</th><th className="r">Qty</th><th className="r">Entry</th>
          <th className="r">Last</th><th className="r">Open R</th><th className="r">P/L</th><th className="r">Held d</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.sym}>
            <td className="mono"><b>{r.sym}</b></td>
            <td className="dim">{r.name}</td>
            <td className="r mono tabular">{r.qty}</td>
            <td className="r mono tabular">{r.entry.toFixed(2)}</td>
            <td className="r mono tabular">{r.last.toFixed(2)}</td>
            <td className={`r mono tabular ${r.openR.startsWith("+") ? "up" : "dn"}`}>{r.openR}</td>
            <td className={`r mono tabular ${r.pl.startsWith("+") ? "up" : "dn"}`}>{r.pl}</td>
            <td className="r mono tabular dim">{r.days}</td>
          </tr>
        ))}
        <tr style={{ borderTop: "1px solid var(--line)" }}>
          <td colSpan={6} className="mono dim2"><b>Totals · 3 positions · 16.4% NAV deployed · cash $90,628</b></td>
          <td className="r mono tabular up">+$780</td>
          <td></td>
        </tr>
      </tbody>
    </table>
  );
}

function PositionSim({ ticker }) {
  const rows = [
    { mult: "0.5×", sh: 55,  notional: 3708, navPct: 3.4, maxL: 210, ratio: "0.19% NAV", tone: "gn" },
    { mult: "1.0×", sh: 110, notional: 7416, navPct: 6.8, maxL: 420, ratio: "0.39% NAV", tone: "copper", on: true },
    { mult: "1.5×", sh: 165, notional: 11_124, navPct: 10.3, maxL: 630, ratio: "0.58% NAV", tone: "amb" },
    { mult: "2.0×", sh: 220, notional: 14_832, navPct: 13.7, maxL: 840, ratio: "0.78% NAV", tone: "rd" },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Size mult</th><th className="r">Shares</th><th className="r">Notional</th><th className="r">% NAV</th><th className="r">Max loss</th><th>Risk ratio</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={r.on ? "is-current" : ""}>
            <td className="mono"><b>{r.mult}</b></td>
            <td className="r mono tabular">{r.sh}</td>
            <td className="r mono tabular">${r.notional.toLocaleString()}</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.navPct.toFixed(1)}%</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>−${r.maxL}</td>
            <td className="mono dim">{r.ratio}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CorrTable() {
  const rows = [
    { sym: "BORA", c: 0.42, tone: "amb" },
    { sym: "INPR", c: 0.18, tone: "gn" },
    { sym: "FLNX", c: -0.12, tone: "gn" },
    { sym: "Book composite", c: 0.34, tone: "amb", bold: true },
  ];
  return (
    <div className="corr-tbl">
      {rows.map((r, i) => (
        <div key={i} className={`corr-row ${r.bold ? "is-bold" : ""}`}>
          <span className="mono">{r.sym}</span>
          <div className="corr-bar">
            <div className={`corr-bar-fill kpi-tone--${r.tone}`} style={{
              width: `${Math.abs(r.c) * 50}%`,
              marginLeft: r.c < 0 ? `${50 - Math.abs(r.c) * 50}%` : "50%",
              background: r.tone === "gn" ? "var(--gn)" : r.tone === "amb" ? "var(--amb)" : "var(--rd)",
            }} />
            <div className="corr-bar-axis" />
          </div>
          <span className={`mono kpi-tone--${r.tone}`}>{r.c >= 0 ? "+" : ""}{r.c.toFixed(2)}</span>
        </div>
      ))}
      <div className="corr-note mono dim2">Correlation cap = 0.55 (book composite). ARCM adds within tolerance.</div>
    </div>
  );
}

function FactorPanel() {
  const factors = [
    { f: "Momentum",  pre: 0.62, post: 0.80, tone: "amb", cap: 1.00 },
    { f: "Value",     pre: -0.10, post: -0.08, tone: "gn",  cap: 0.50 },
    { f: "Quality",   pre: 0.34, post: 0.41, tone: "gn",  cap: 1.00 },
    { f: "Size",      pre: -0.20, post: -0.16, tone: "gn",  cap: 0.50 },
    { f: "Vol",       pre: 0.18, post: 0.22, tone: "amb", cap: 0.40 },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Factor</th><th className="r">Pre</th><th className="r">Post</th><th>Δ</th><th className="r">Cap</th></tr></thead>
      <tbody>
        {factors.map((f, i) => (
          <tr key={i}>
            <td className="mono">{f.f}</td>
            <td className="r mono tabular dim">{f.pre.toFixed(2)}</td>
            <td className={`r mono tabular kpi-tone--${f.tone}`}>{f.post.toFixed(2)}</td>
            <td className={`mono ${f.post > f.pre ? "up" : "dn"}`}>{(f.post - f.pre >= 0 ? "+" : "")}{(f.post - f.pre).toFixed(2)}</td>
            <td className="r mono tabular dim">{f.cap.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ────────────────────────────────────────────────────────────
// TAPE · FLOW — news, insider, sentiment, 13F, catalysts
// ────────────────────────────────────────────────────────────
// Real tape data off the ticker's fundamentals (13F holders + insider) + sentiment
// pillar + earnings catalyst. Per-ticker news isn't on the ticker object (only
// market-level), so the news timeline shows an honest "not in feed" state.
function tapeData(ticker) {
  const holders = Array.isArray(ticker.holders) ? ticker.holders : (ticker.holders ? Object.values(ticker.holders) : []);
  const insider = Array.isArray(ticker.insiderTx) ? ticker.insiderTx : (ticker.insiderTx ? Object.values(ticker.insiderTx) : []);
  const sp = (ticker.pillars && typeof ticker.pillars.sentiment === "number") ? ticker.pillars.sentiment
    : (ticker.pillarPct && typeof ticker.pillarPct.sentiment === "number") ? ticker.pillarPct.sentiment : null;
  const sentNorm = (typeof sp === "number") ? +(sp / 50 - 1).toFixed(2) : null;   // 0-100 → −1..+1
  const er = (ticker.earnings && ticker.earnings.days != null) ? ticker.earnings : null;
  return { holders, insider, sentNorm, er, any: !!(holders.length || insider.length || sentNorm != null) };
}

function LensTape({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("tp-1"); const s2 = useStateToggle("tp-2");
  const s3 = useStateToggle("tp-3"); const s4 = useStateToggle("tp-4");
  const s5 = useStateToggle("tp-5");
  const td = tapeData(ticker);
  const insBuys = td.insider.filter(x => /^(P|BUY)/i.test(x.transactionCode || x.action || "")).length;
  const insSells = td.insider.filter(x => /^(S|SELL)/i.test(x.transactionCode || x.action || "")).length;
  const netIns = insBuys - insSells;
  const sentTone = td.sentNorm == null ? "ink" : td.sentNorm > 0.15 ? "gn" : td.sentNorm < -0.15 ? "rd" : "amb";

  if (!td.any) {
    return (
      <div className="lens lens--tape">
        <div className="lens-section"><div className="lens-pad">
          <div className="smc-empty mono dim2" style={{ padding: "16px" }}>
            No tape data loaded for <b className="warn">{(ticker && ticker.symbol) || "this name"}</b> yet —
            13F holders, insider transactions and the sentiment pillar come from the per-ticker fundamentals
            fetch. {ticker && ticker._loading ? "Loading…" : "Open from the scan (or wait for enrichment) to populate."}
          </div>
        </div></div>
      </div>
    );
  }

  return (
    <div className="lens lens--tape">
      <div className="hero tape-hero">
        <div className="th-left">
          <div className="label-cap">Tape read · {(ticker && ticker.symbol) || ""}</div>
          <div className="th-score">
            <div className="th-score-num mono">{netIns >= 0 ? "+" : ""}{netIns}</div>
            <Pill tone={netIns > 0 ? "gn" : netIns < 0 ? "rd" : "ink"} dot>net insider {netIns >= 0 ? "buys" : "sells"}</Pill>
            {td.sentNorm != null && <Pill tone={sentTone} small>sentiment {td.sentNorm >= 0 ? "+" : ""}{td.sentNorm}</Pill>}
          </div>
          <div className="th-pill-row">
            <Pill tone={td.insider.length ? "gn" : "ink"} small>{td.insider.length} insider tx</Pill>
            <Pill tone={td.holders.length ? "gn" : "ink"} small>{td.holders.length} 13F holders</Pill>
            {td.er && <Pill tone="copper" small>ER in {td.er.days}d</Pill>}
          </div>
        </div>
        <div className="th-right">
          <SentimentDial sentNorm={td.sentNorm} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="News Timeline"
          sub="per-ticker dated · scored"
          style={headerStyle} right={<StateToggle name="tp-1" />} />
        <StateWrap state={s1.value} source="EODHD · per-ticker news">
          <div className="lens-pad"><NewsTimeline ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Insider Transactions"
          sub="Form 4 · net direction"
          style={headerStyle} right={<StateToggle name="tp-2" />} />
        <StateWrap state={s2.value} source="EODHD · InsiderTransactions">
          <div className="lens-pad"><InsiderTable rows={td.insider} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="13F Holders"
          sub="institutional ownership · qty-on-qty change"
          style={headerStyle} right={<StateToggle name="tp-4" />} />
        <StateWrap state={s4.value} source="EODHD · Holders">
          <div className="lens-pad"><HoldersTable rows={td.holders} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Earnings Catalyst"
          sub="next scheduled report in the hold window"
          style={headerStyle} right={<StateToggle name="tp-5" />} />
        <StateWrap state={s5.value} source="earnings calendar">
          <div className="lens-pad">
            {td.er ? <div className="catcal">
              <div className="cat-countdown">
                <span className="cat-cd-n mono">{td.er.days}<span className="cat-cd-u">d</span></span>
                <div className="cat-cd-body">
                  <span className="cat-cd-lbl mono dim2">NEXT EARNINGS{td.er.date ? " · " + td.er.date : ""}</span>
                  <span className="cat-cd-evt mono">scheduled report <span className="cat-cd-imp">high impact</span></span>
                </div>
                {td.er.days <= 7 && <span className="cat-cd-warn mono">⚠ inside swing window — size −25% / flatten T−2</span>}
              </div>
            </div> : <div className="smc-empty mono dim2">— no scheduled earnings in the window</div>}
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="violet" cells={[
            { lens: "Insider", verdict: `${netIns >= 0 ? "+" : ""}${netIns}`, tone: netIns > 0 ? "gn" : netIns < 0 ? "rd" : "ink", note: `${insBuys} buys / ${insSells} sells` },
            { lens: "Sentiment", verdict: td.sentNorm != null ? `${td.sentNorm >= 0 ? "+" : ""}${td.sentNorm}` : "—", tone: sentTone, note: "pillar score" },
            { lens: "Holders", verdict: `${td.holders.length}`, tone: td.holders.length ? "gn" : "ink", note: "13F institutions" },
            { lens: "Earnings", verdict: td.er ? `${td.er.days}d` : "—", tone: "amb", note: td.er ? "in window" : "none scheduled" },
            { lens: "Risk", verdict: "OK", tone: "gn", note: "tape doesn't override risk" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Tape</span>
        <span className="mono">
          Insider net <b className={netIns > 0 ? "up" : netIns < 0 ? "dn" : ""}>{netIns >= 0 ? "+" : ""}{netIns}</b> ({insBuys} buys / {insSells} sells) ·
          {td.sentNorm != null ? <> sentiment <b className={sentTone === "gn" ? "up" : sentTone === "rd" ? "dn" : "warn"}>{td.sentNorm >= 0 ? "+" : ""}{td.sentNorm}</b> ·</> : null}
          {" "}{td.holders.length} institutional holders{td.er ? <> · earnings in <b className="copper">{td.er.days}d</b></> : ""}.
        </span>
      </div>
    </div>
  );
}

function SentimentDial({ sentNorm }) {
  const have = typeof sentNorm === "number";
  const v = have ? Math.max(-1, Math.min(1, sentNorm)) : 0;
  const tone = !have ? "ink-3" : v > 0.15 ? "gn" : v < -0.15 ? "rd" : "amb";
  const lbl = !have ? "NO DATA" : v > 0.15 ? "BULLISH" : v < -0.15 ? "BEARISH" : "NEUTRAL";
  const txt = have ? (v >= 0 ? "+" : "") + v.toFixed(2) : "—";
  const angle = -90 + v * 90;
  const tipX = 100 + 64 * Math.cos((angle * Math.PI) / 180);
  const tipY = 110 + 64 * Math.sin((angle * Math.PI) / 180);
  return (
    <svg viewBox="0 0 200 130" width="240" height="156" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="sd-arc" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="1" />
          <stop offset="50%" stopColor="var(--amb)" stopOpacity="1" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="1" />
        </linearGradient>
      </defs>
      <path d="M 30 110 A 70 70 0 0 1 170 110" stroke="var(--line)" strokeWidth="12" fill="none" strokeLinecap="round" />
      <path d="M 30 110 A 70 70 0 0 1 170 110" stroke="url(#sd-arc)" strokeWidth="12" fill="none" strokeLinecap="round"
            style={{ filter: "drop-shadow(0 0 8px color-mix(in oklab, var(--gn) 40%, transparent))" }} />
      {/* Tick marks */}
      {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
        const a = -180 + t * 180;
        const x1 = 100 + 56 * Math.cos((a * Math.PI) / 180);
        const y1 = 110 + 56 * Math.sin((a * Math.PI) / 180);
        const x2 = 100 + 66 * Math.cos((a * Math.PI) / 180);
        const y2 = 110 + 66 * Math.sin((a * Math.PI) / 180);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--bg-1)" strokeWidth="2" />;
      })}
      {/* Needle */}
      <line x1="100" y1="110" x2={tipX} y2={tipY} stroke="var(--copper)" strokeWidth="3" strokeLinecap="round"
            style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <circle cx="100" cy="110" r="7" fill="var(--bg-1)" stroke="var(--copper)" strokeWidth="2.5"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <circle cx="100" cy="110" r="3" fill="var(--copper)" />
      <text x="100" y="128" textAnchor="middle" className="mono" fontSize="16" fill={`var(--${tone})`} fontWeight="500"
            style={{ filter: `drop-shadow(0 0 8px color-mix(in oklab, var(--${tone}) 40%, transparent))` }}>{txt}</text>
      <text x="100" y="142" textAnchor="middle" className="mono" fontSize="9" fill="var(--ink-3)" letterSpacing="0.18em">{lbl}</text>
    </svg>
  );
}

function NewsTimeline({ ticker }) {
  const raw = (ticker && Array.isArray(ticker.news_articles)) ? ticker.news_articles : [];
  if (!raw.length) {
    return <div className="smc-empty mono dim2">— per-ticker news not in this feed (market-level news lives on the Markets tab)</div>;
  }
  const items = raw.slice(0, 8).map(a => {
    const sc = typeof a.sentiment === "number" ? a.sentiment : (a.sentiment && a.sentiment.polarity) || 0;
    return {
      d: (a.date || a.published || "").slice(5, 10).replace("-", "/"),
      t: a.title || a.headline || "—",
      s: (sc >= 0 ? "+" : "") + sc.toFixed(1),
      tone: sc > 0.15 ? "gn" : sc < -0.15 ? "rd" : "ink",
    };
  });
  return (
    <div className="news-tl">
      {items.map((it, i) => (
        <div key={i} className={`news-row news-${it.tone}`}>
          <span className="mono dim2 news-when">{it.d}</span>
          <span className="mono news-title">{it.t}</span>
          <span className={`mono news-score kpi-tone--${it.tone}`}>{it.s}</span>
        </div>
      ))}
    </div>
  );
}

function InsiderTable({ rows }) {
  const src = Array.isArray(rows) ? rows : [];
  if (!src.length) return <div className="smc-empty mono dim2">— no insider transactions on file</div>;
  const mapped = src.slice(0, 8).map(r => {
    const code = (r.transactionCode || r.action || "").toUpperCase();
    const isBuy = /^(P|BUY|A)/.test(code);
    const isSell = /^(S|SELL|D)/.test(code);
    const sh = Number(r.transactionAmount ?? r.sh ?? r.shares ?? 0) || 0;
    const px = Number(r.transactionPrice ?? r.px ?? r.price ?? 0) || 0;
    return {
      date: (r.transactionDate || r.date || "").slice(5, 10).replace("-", "/"),
      who: r.ownerName || r.who || r.name || "—",
      action: isBuy ? "BUY" : isSell ? "SELL" : (code || "—"),
      sh, px, val: sh * px,
      tone: isBuy ? "gn" : isSell ? "rd" : "ink",
    };
  });
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Date</th><th>Who</th><th>Action</th>
          <th className="r">Shares</th><th className="r">Price</th><th className="r">Value</th>
        </tr>
      </thead>
      <tbody>
        {mapped.map((r, i) => (
          <tr key={i}>
            <td className="mono dim">{r.date}</td>
            <td className="mono">{r.who}</td>
            <td><Pill tone={r.tone} small>{r.action}</Pill></td>
            <td className="r mono tabular">{r.sh.toLocaleString()}</td>
            <td className="r mono tabular">{r.px ? "$" + r.px.toFixed(2) : "—"}</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.val ? "$" + Math.round(r.val).toLocaleString() : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HoldersTable({ rows }) {
  const src = Array.isArray(rows) ? rows : [];
  if (!src.length) return <div className="smc-empty mono dim2">— no 13F holder data on file</div>;
  const mapped = src.map(r => {
    const ownPct = Number(r.totalShares ?? r.ownPct ?? r.pct ?? 0) || 0;
    const ch = Number(r.change_p ?? r.delta ?? 0);
    return {
      name: r.name || r.holder || "—",
      ownPct,
      ch: Number.isFinite(ch) ? ch : 0,
      tone: ch > 0.05 ? "gn" : ch < -0.05 ? "rd" : "ink",
    };
  }).sort((a, b) => b.ownPct - a.ownPct).slice(0, 8);
  return (
    <table className="dtable">
      <thead><tr><th>Holder</th><th className="r">Own %</th><th className="r">QoQ Δ</th></tr></thead>
      <tbody>
        {mapped.map((r, i) => (
          <tr key={i}>
            <td className="mono">{r.name}</td>
            <td className="r mono tabular">{r.ownPct.toFixed(1)}%</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.ch >= 0 ? "+" : ""}{r.ch.toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

window.LensPortfolio = LensPortfolio;
window.LensTape = LensTape;
