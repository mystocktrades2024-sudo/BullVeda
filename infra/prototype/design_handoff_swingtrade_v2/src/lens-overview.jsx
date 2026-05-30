// lens-overview.jsx — quant overview (overrides the in-file LensOverview)
// Loaded AFTER detail-panel.jsx so window.LensOverview = this one.

// ──── Rich VerdictHero — overrides the in-file one ──────────────
function VerdictHero({ ticker, mode, heroStyle, sizeCat }) {
  const pillars = ticker.pillars;
  const entry = ticker.pivot * 1.002;
  const risk = entry - ticker.stop;
  const reward1 = ticker.t1 - entry;
  return (
    <div className="hero vh-rich vh-rich--compact">
      <div className="vhr-cockpit">
        <div className="vhr-vis">
          {heroStyle === "gauge" && <Gauge value={ticker.score} label="OVERALL" size={sizeCat === "S" ? 120 : 140} />}
          {heroStyle === "radar" && <Radar pillars={pillars} size={sizeCat === "S" ? 130 : 156} />}
          {heroStyle === "cone"  && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <div className="label-cap">10d cone · ±{ticker.ml.magnitude.hi.toFixed(0)}%</div>
              <Cone lo={ticker.ml.magnitude.lo} mid={ticker.ml.magnitude.mid} hi={ticker.ml.magnitude.hi} w={220} h={108} />
            </div>
          )}
          <div className="vhr-pillchips">
            {Object.entries(pillars).map(([k, v]) => {
              const tone = v >= 70 ? "gn" : v >= 50 ? "amb" : "rd";
              return <span key={k} className={`vhr-pchip kpi-tone--${tone}`} title={k} data-field={`t.scoring_breakdown.${k}_score`}>{k.slice(0, 4)} {v}</span>;
            })}
          </div>
        </div>

        <div className="vhr-body">
          <div className="vhr-eyebrow">
            <span className="mono label-cap">Setup · Execution · <b className="copper">{mode}</b></span>
            <Pill tone="gn" dot small>LIVE 14:23 ET</Pill>
          </div>
          <div className="vhr-setup mono">
            <b className="copper">{ticker.setupFamily}</b>
            <span className="dim2"> · hold ~{ticker.holdDays}d · </span><b>{ticker.rMultiple.toFixed(2)}R</b>
            <span className="dim2"> · {(ticker.setupStats.winRate*100).toFixed(0)}% hist · Wilson LB {(ticker.setupStats.wilsonLB*100).toFixed(0)}%</span>
          </div>

          <div className="vhr-ticket">
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">ENTRY</div>
              <div className="vhr-tk-v mono copper" data-field="canonical_trade_plan.entry.low" data-fallback="entry_low ▸ entry_lo" data-provenance="comp">${entry.toFixed(2)}</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">STOP · MAX LOSS</div>
              <div className="vhr-tk-v mono dn" data-field="canonical_trade_plan.stop" data-fallback="trade_plan.stop ▸ stop" data-provenance="comp">${ticker.stop.toFixed(2)}</div>
              <div className="vhr-tk-sub mono dim2">−${risk.toFixed(2)} · −{(risk/entry*100).toFixed(1)}%</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">T1 · T2</div>
              <div className="vhr-tk-v mono up" data-field="canonical_trade_plan.target1" data-fallback="t1 ▸ trade_levels.t1" data-provenance="comp">${ticker.t1.toFixed(2)} <span className="dim2">·</span> ${ticker.t2.toFixed(2)}</div>
              <div className="vhr-tk-sub mono dim2">+${reward1.toFixed(2)} · {(reward1/risk).toFixed(2)}R</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">SIZE · NAV</div>
              <div className="vhr-tk-v mono" data-field="position_size.shares" data-provenance="comp">110 sh</div>
              <div className="vhr-tk-sub mono dim2">$7,416 · 6.8% NAV</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">R · WILSON</div>
              <div className="vhr-tk-v mono copper" data-field="canonical_trade_plan.rr_ratio" data-fallback="rr_ratio ▸ rr" data-provenance="comp">{ticker.rMultiple.toFixed(2)}R</div>
              <div className="vhr-tk-sub mono dim2">LB 47.7% · PF 1.41</div>
            </div>
          </div>

          <div className="vhr-actions">
            <button className="vhr-act vhr-act--gn">▲ BUY · BRACKET</button>
            <button className="vhr-act vhr-act--rd">▼ SHORT</button>
            <button className="vhr-act">＋ WATCH</button>
            <button className="vhr-act vhr-act--ghost">⚙ ADJUST SIZE</button>
          </div>
        </div>
      </div>
    </div>
  );
}
window.VerdictHero = VerdictHero;

// per-ticker pre-mortem note — persisted to localStorage
function PreMortemNote({ symbol }) {
  const key = "premortem-" + (symbol || "x");
  const [val, setVal] = React.useState(() => { try { return localStorage.getItem(key) || ""; } catch (e) { return ""; } });
  return (
    <div className="pm-note-wrap">
      <div className="label-cap" style={{ marginBottom: 6 }}>Your pre-mortem · written before entry</div>
      <textarea className="pm-note mono" placeholder="If this trade fails, the most likely reason will be… (your own words — saved per ticker)"
        value={val} onChange={e => { setVal(e.target.value); try { localStorage.setItem(key, e.target.value); } catch (e2) {} }} />
    </div>
  );
}

function LensOverview({ ticker: t0, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const ticker = (window.modeAdjust ? window.modeAdjust(t0, mode) : t0);
  const s1 = useStateToggle("ov-1"); const s2 = useStateToggle("ov-2");
  const s3 = useStateToggle("ov-3"); const s4 = useStateToggle("ov-4");
  const s5 = useStateToggle("ov-5"); const s6 = useStateToggle("ov-6");
  const s7 = useStateToggle("ov-7"); const s8 = useStateToggle("ov-8");

  return (
    <div className="lens lens--ov">
      {window.CompositeVerdict && <CompositeVerdict ticker={ticker} mode={mode} onLens={(name) => {
        const map = { "Overview": "overview", "AI Edge": "mledge", "Technicals": "technicals", "Patterns": "patterns", "SMC": "smc", "Value": "investment", "Risk": "risk", "Track Rec.": "mledge", "Plan": "plan", "Earnings": "earnings", "Options": "options", "Insider": "tape", "Tape": "tape" };
        if (window.__setLens && map[name]) window.__setLens(map[name]);
      }} />}

      <DeskRead ticker={ticker} mode={mode} />

      <VerdictHero ticker={ticker} mode={mode} heroStyle={heroStyle} sizeCat={sizeCat} />

      <div className="lens-section">
        <SectionHeader n="0" title="Company Snapshot · Quant Read"
          sub="who they are · why now · where the numbers come from"
          style={headerStyle} right={<FreshnessPill state="live" age="18s" />} />
        <div className="lens-pad"><CompanySnapshot ticker={ticker} /></div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="14-Lens Confluence Heatmap"
          sub="every discipline's verdict at a glance · conflicts surfaced"
          style={headerStyle} right={<StateToggle name="ov-1" />} />
        <StateWrap state={s1.value} source="all-lens aggregator · live polling">
          <div className="lens-pad"><ConfluenceHeatmap /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Sleeve Attribution · Mechanism"
          sub="which strategy family · alpha source · last 5 instances"
          style={headerStyle} right={<StateToggle name="ov-3" />} />
        <StateWrap state={s3.value} source="strategy classifier + setup_stats.json">
          <div className="lens-pad"><SleeveAttribution ticker={ticker} /></div>
        </StateWrap>
      </div>

      {(window.__tier ?? 4) >= 3 && (
      <div className="lens-2col">
      <div className="lens-section">
        <SectionHeader n={3} title="Rule-Engine · Gate Cascade Audit"
          sub="how this name got from 612 ranked → BUY · every gate in order · PRO+"
          style={headerStyle} right={<StateToggle name="ov-4" />} />
        <StateWrap state={s4.value} source="rule engine · audit log">
          <div className="lens-pad"><GateCascade /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="What Changed · 24h Delta"
          sub="since last bundle (02:14:08 ET) · per-pillar deltas"
          style={headerStyle} right={<StateToggle name="ov-6" />} />
        <StateWrap state={s6.value} source="bundle diff · per-pillar last 24h">
          <div className="lens-pad"><WhatChanged /></div>
        </StateWrap>
      </div>
      </div>
      )}

      <div className="lens-section">
        <SectionHeader n={5} title="Pre-Mortem · Honesty Surface"
          sub="what would make this thesis wrong · written before entry"
          style={headerStyle} right={<StateToggle name="ov-8" />} />
        <StateWrap state={s8.value} source="thesis library · per-ticker">
          <div className="lens-pad">
            <div className="premortem">
              <div className="premortem-row"><span className="pm-num mono">1</span><span className="pm-text">Loses VWAP intraday AND closes below $65.10 — invalidation cascade.</span><Pill tone="rd" small>HARD</Pill></div>
              <div className="premortem-row"><span className="pm-num mono">2</span><span className="pm-text">Sector ETF (XLB) breaks 50-DMA on +1.5σ volume — regime flip.</span><Pill tone="amb" small>MEDIUM</Pill></div>
              <div className="premortem-row"><span className="pm-num mono">3</span><span className="pm-text">CPI prints &gt;0.4% MoM next Wed — risk-off reset.</span><Pill tone="amb" small>MACRO</Pill></div>
              <div className="premortem-row"><span className="pm-num mono">4</span><span className="pm-text">Top-2 customer (31% of revenue) cuts guidance on Q1 call.</span><Pill tone="rd" small>FUNDAMENTAL</Pill></div>
            </div>
            <PreMortemNote symbol={ticker.symbol} />
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          {(() => {
            const ie = window.insiderEdge && window.insiderEdge(ticker.symbol);
            const cells = [
              { lens: "Overview",  verdict: "BUY",   tone: "gn",  note: `score ${ticker.score} · 4 of 5 pillars green` },
              { lens: "Technicals",verdict: "PASS",  tone: "gn",  note: "RSI 64 · VWAP-reclaim" },
              { lens: "Value",     verdict: "MARG.", tone: "amb", note: "MoS 6%" },
              { lens: "Risk",      verdict: "OK",    tone: "gn",  note: "VaR −2.1%" },
              { lens: "Earnings",  verdict: "11 d",  tone: "amb", note: "trim pre-ER" },
            ];
            if (ie) cells.push({ lens: "Insider", verdict: ie.verdict, tone: ie.tone, note: `conviction ${ie.score} · ${ie.buyers} buyer${ie.buyers === 1 ? "" : "s"}${ie.officers ? ` · ${ie.officers} C-suite` : ""}` });
            return <CrossLens lead="copper" cells={cells} />;
          })()}
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · {mode}</span>
        <span className="mono">
          Take the breakout above <b className="copper">${ticker.pivot.toFixed(2)}</b>,
          half-Kelly size · 9 of 10 gates pass · Wilson LB <b className="up">47.7%</b> · expectancy <b className="up">+0.51R</b>.
        </span>
      </div>
    </div>
  );
}

function ConfluenceHeatmap() {
  const cells = [
    { lens: "Overview", v: "BUY",     tone: "gn",  note: "score 78" },
    { lens: "Plan",     v: "READY",   tone: "gn",  note: "R 1.74" },
    { lens: "Chart",    v: "TREND+",  tone: "gn",  note: "stacked-bull" },
    { lens: "Technicals",v:"PASS",    tone: "gn",  note: "RSI 64" },
    { lens: "Patterns", v: "VCP·B2",  tone: "gn",  note: "conf 74%" },
    { lens: "SMC",      v: "OB+BoS",  tone: "gn",  note: "spring held" },
    { lens: "Value",    v: "MARG.",   tone: "amb", note: "MoS 6%" },
    { lens: "Risk",     v: "OK",      tone: "gn",  note: "VaR −2.1%" },
    { lens: "Earnings", v: "11d",     tone: "amb", note: "trim pre-ER" },
    { lens: "Options",  v: "RICH",    tone: "amb", note: "IV/HV 1.42" },
    { lens: "Portfolio",v: "FIT",     tone: "gn",  note: "correl 0.34" },
    { lens: "Tape",     v: "+12 INS", tone: "gn",  note: "rising sent." },
    { lens: "Track Rec.",v:"EDGE",    tone: "gn",  note: "Wilson 47.7" },
    { lens: "AI Edge",  v: "+0.18",   tone: "gn",  note: "hit-net pos." },
  ];
  return (
    <div className="conf-grid">
      {cells.map((c, i) => {
        const map = { "Overview": "overview", "Plan": "plan", "Chart": "chart", "Technicals": "technicals", "Patterns": "patterns", "SMC": "smc", "Value": "investment", "Risk": "risk", "Earnings": "earnings", "Options": "options", "Portfolio": "tape", "Tape": "tape", "Track Rec.": "mledge", "AI Edge": "mledge" };
        const go = () => { if (window.__setLens && map[c.lens]) window.__setLens(map[c.lens]); };
        return (
          <button key={i} className={`conf-cell conf-${c.tone}`} onClick={go} title={`open ${c.lens}`}>
            <div className="conf-lens mono">{c.lens}</div>
            <div className={`conf-v mono kpi-tone--${c.tone}`}>{c.v}</div>
            <div className="conf-note mono dim2">{c.note}</div>
          </button>
        );
      })}
      <div className="conf-summary">
        <Pill tone="gn" dot>10 PASS</Pill>
        <Pill tone="amb" small>3 CAUTION</Pill>
        <Pill tone="rd" small>0 FAIL</Pill>
        <span className="mono dim2" style={{ marginLeft: 12 }}>
          Disagreement score: <b className="warn">low</b> — clean confluence; act on the bracket.
        </span>
      </div>
    </div>
  );
}

function SleeveAttribution({ ticker }) {
  return (
    <div className="sleeve">
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">SLEEVE</span>
        <div><Pill tone="copper">CONTINUATION BREAKOUT · base #2</Pill> <span className="mono dim2">· 2 of 11 active sleeves · 12% of current book</span></div>
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">MECHANISM</span>
        <span className="mono">
          Post-base breakout on dry-volume pullback. <b className="copper">Alpha source:</b> liquidity withdrawal then demand absorption at pivot.
          <b className="copper"> Why it works:</b> regime where institutional accumulation is observable but not yet priced.
        </span>
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">WILSON</span>
        <WilsonPill n={47} winRate={0.617} lb={0.477} />
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">LAST 5</span>
        <div className="sleeve-recent">
          {[
            { sym: "ARGN", date: "Apr 22", out: "+1.84R", tone: "gn" },
            { sym: "BORA", date: "Apr 04", out: "+0.72R", tone: "gn" },
            { sym: "VLCT", date: "Mar 18", out: "−1.0R",  tone: "rd" },
            { sym: "ZOTR", date: "Feb 27", out: "+2.10R", tone: "gn" },
            { sym: "NVRH", date: "Feb 06", out: "+0.41R", tone: "amb" },
          ].map((s, i) => (
            <div key={i} className="sleeve-rec">
              <span className="mono"><b>{s.sym}</b></span>
              <span className="mono dim2">{s.date}</span>
              <span className={`mono kpi-tone--${s.tone}`}>{s.out}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function GateCascade() {
  const gates = [
    { n: 1, label: "Universe · mcap ≥ $100M · ADV ≥ 500k",       v: "612 / 1402", tone: "gn" },
    { n: 2, label: "Liquidity · spread ≤ 10bp · L1 ≥ 1000",      v: "PASS",       tone: "gn" },
    { n: 3, label: "Trend · close > 50-DMA · 200-DMA rising",    v: "PASS",       tone: "gn" },
    { n: 4, label: "Setup detected · pattern conf ≥ 0.60",       v: "VCP 0.74",   tone: "gn" },
    { n: 5, label: "Wilson LB ≥ 45% · per setup family",         v: "47.7%",      tone: "gn" },
    { n: 6, label: "R-multiple ≥ 1.5 · entry/stop/T1 valid",     v: "1.74R",      tone: "gn" },
    { n: 7, label: "Risk · max loss ≤ 0.75% NAV",                v: "0.39%",      tone: "gn" },
    { n: 8, label: "Correl-to-book ≤ 0.55",                      v: "0.34",       tone: "gn" },
    { n: 9, label: "ER not in T1 window (T+14d > ER date)",      v: "ER in 11d",  tone: "amb", warn: true },
    { n: 10,label: "ML hit-net ≥ +0.05",                         v: "+0.18",      tone: "gn" },
  ];
  return (
    <div className="gates">
      {gates.map(g => (
        <div key={g.n} className={`gate-row gate-${g.tone}`}>
          <span className="gate-n mono">{String(g.n).padStart(2,"0")}</span>
          <span className="gate-mark mono">{g.warn ? "!" : "✓"}</span>
          <span className="gate-lbl">{g.label}</span>
          <span className={`gate-result mono kpi-tone--${g.tone}`}>{g.v}</span>
        </div>
      ))}
      <div className="gates-summary mono">
        <b className="up">9 of 10 gates pass · 1 caution (ER in window).</b> Recommendation: take bracket with <b>25% size cut</b> + full exit T−2 sessions pre-ER unless thesis confirms.
      </div>
    </div>
  );
}

function MacroDrill() {
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
      <KpiTile label="Regime · MULTI-FACTOR" value="BULL · LOW-VIX" tone="gn" sub="highest WR regime · 71% historical" />
      <KpiTile label="XLB · 50-DMA"          value="+3.4%"          tone="gn" sub="rising · sector tailwind" />
      <KpiTile label="VIX percentile 1y"     value="32%"            tone="gn" sub="below median · risk-on" />
      <KpiTile label="US10Y · 5d delta"      value="−14bp"          tone="gn" sub="rates easing · duration friendly" />
      <KpiTile label="Breadth · A/D NYSE"    value="1.84"           tone="gn" sub="participation broad" />
      <KpiTile label="HY spread · 5d"        value="−6bp"           tone="gn" sub="risk appetite holding" />
    </div>
  );
}

function WhatChanged() {
  const items = [
    { label: "Composite score",           old: "74",   now: "78",   tone: "gn",  note: "+4 · drove BUY trigger" },
    { label: "Technical pillar",          old: "78",   now: "82",   tone: "gn",  note: "MACD+ · VWAP reclaim" },
    { label: "Catalyst pillar",           old: "62",   now: "58",   tone: "amb", note: "−4 · ER proximity weight" },
    { label: "ML hit-net",                old: "0.14", now: "0.18", tone: "gn",  note: "+4pt edge improvement" },
    { label: "Insider activity (90d net)",old: "+8",   now: "+12",  tone: "gn",  note: "CFO + COO buys May 18-22" },
    { label: "Sector ETF (XLB)",          old: "+0.6%",now: "+1.2%",tone: "gn",  note: "sector confirming" },
  ];
  return (
    <div className="wc">
      {items.map((it, i) => (
        <div key={i} className="wc-row">
          <span className="mono wc-lbl">{it.label}</span>
          <span className="mono dim2 wc-old">{it.old}</span>
          <span className="mono dim">→</span>
          <span className={`mono wc-new kpi-tone--${it.tone}`}><b>{it.now}</b></span>
          <span className="mono dim wc-note">{it.note}</span>
        </div>
      ))}
    </div>
  );
}

function StressSnapshot() {
  const scenarios = [
    { name: "VIX spike +8",       pnl: "−$680",   pct: "−0.63% NAV", action: "Cut 50%",    tone: "amb" },
    { name: "Sector rotation −5%",pnl: "−$520",   pct: "−0.48% NAV", action: "Trim 25%",   tone: "amb" },
    { name: "Earnings gap −15%",  pnl: "−$420",   pct: "−0.39% NAV", action: "OCO exit",   tone: "rd"  },
    { name: "Macro shock (CPI)",  pnl: "−$610",   pct: "−0.56% NAV", action: "Reduce 50%", tone: "amb" },
    { name: "Sector kill",        pnl: "−$890",   pct: "−0.82% NAV", action: "Flatten",    tone: "rd"  },
    { name: "Liquidity dry-up",   pnl: "−$340",   pct: "−0.31% NAV", action: "Hold · wide",tone: "ink" },
  ];
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(6, 1fr)" }}>
      {scenarios.map((s, i) => (
        <KpiTile key={i} label={s.name} value={s.pnl} tone={s.tone} sub={`${s.pct} · ${s.action}`} />
      ))}
    </div>
  );
}

// Override the in-file LensOverview from detail-panel.jsx
window.LensOverview = LensOverview;

// ─── Desk Read — how a 20-yr quant scans it in 2 seconds ────────
function DeskRead({ ticker, mode }) {
  const entry = ticker.pivot * 1.002;
  const risk = entry - ticker.stop;
  const reward = ticker.t1 - entry;
  const wr = 0.617, lb = 0.477;
  // expectancy in R: p*win − q*loss (loss capped at 1R)
  const evR = (wr * (reward / risk) - (1 - wr) * 1).toFixed(2);
  return (
    <div className="dr">
      <div className="dr-metrics">
        <DrCell label="EXPECTANCY" value={`+${evR}R`} tone="gn" tip="p·b − q · per unit risk" />
        <DrCell label="EDGE · WILSON LB" value={`${(lb*100).toFixed(0)}%`} tone="gn" tip="95% lower bound · n=47" />
        <DrCell label="DOWNSIDE" value="−$420" tone="rd" tip="0.39% NAV · hard stop" />
        <DrCell label="R:R" value={`${(reward/risk).toFixed(2)}`} tone="copper" tip="reward ÷ risk to T1" />
        <DrCell label="CORREL → BOOK" value="0.34" tone="gn" tip="cap 0.55 · adds cleanly" />
        <DrCell label="LIQUIDITY" value="A" tone="gn" tip="2 bp spread · 1.12M ADV" />
        <DrCell label="REGIME FIT" value="71%" tone="gn" tip="setup WR in current regime" />
        <DrCell label="TIME RISK" value="ER 11d" tone="amb" tip="trim 25% pre-print" />
      </div>

      <div className="dr-call mono">
        <span className="dr-call-tag">DESK READ</span>
        <span className="dr-call-txt">
          Clean continuation BO with a real, sample-validated edge (LB 48%, +{evR}R expectancy).
          Downside bounded at 0.39% NAV, adds at 0.34 correl, fits the bull/low-VIX regime where this
          setup wins 71%. <b className="warn">One caveat:</b> ER in 11d — size −25% and flatten T−2 if unconfirmed.
          <b className="copper"> Take the bracket.</b>
        </span>
      </div>
    </div>
  );
}

function DrCell({ label, value, tone, tip }) {
  return (
    <div className={`dr-cell dr-cell--${tone}`} title={tip}>
      <div className="dr-cell-l mono">{label}</div>
      <div className={`dr-cell-v mono kpi-tone--${tone}`}>{value}</div>
    </div>
  );
}

// ─── Company Snapshot · Quant Read ──────────────────────────
function CompanySnapshot({ ticker }) {
  return (
    <div className="cs-grid">
      <div className="cs-card cs-card--who">
        <div className="cs-card-hdr">
          <div className="label-cap">WHO · {ticker.symbol}</div>
          <span className="mono dim2">{ticker.exchange} · {ticker.sector} · {ticker.industry}</span>
        </div>
        <div className="cs-name mono">{ticker.name}</div>
        <div className="cs-blurb mono dim">
          Mid-cap specialty-materials operator · 70% specialty coatings / 30% adjacent chemicals ·
          top-2 customers = 31% of revenue · Akron capacity expansion ships H2 (+18% volume).
        </div>
        <div className="cs-meta">
          <span className="cs-chip mono"><span className="dim2">mcap</span> <b>${(ticker.mcap/1e9).toFixed(2)}B</b></span>
          <span className="cs-chip mono"><span className="dim2">β</span> <b>{ticker.beta.toFixed(2)}</b></span>
          <span className="cs-chip mono"><span className="dim2">float</span> <b>76.4M</b></span>
          <span className="cs-chip mono"><span className="dim2">short</span> <b>{ticker.shortFloat.toFixed(1)}%</b></span>
          <span className="cs-chip mono"><span className="dim2">insider own</span> <b>{ticker.insiderOwn.toFixed(1)}%</b></span>
          <span className="cs-chip mono"><span className="dim2">ADV 20d</span> <b>{(ticker.avgVol/1e6).toFixed(2)}M sh</b></span>
          <span className="cs-chip mono"><span className="dim2">spread</span> <b className="up">2 bp</b></span>
          <span className="cs-chip mono"><span className="dim2">opt OI</span> <b>48k</b></span>
        </div>
      </div>

      <div className="cs-card cs-card--er">
        <div className="cs-card-hdr">
          <div className="label-cap">EARNINGS · NEXT CATALYST</div>
          <Pill tone="amb" small>T−{ticker.earnings.days}d</Pill>
        </div>
        <div className="cs-er-big">
          <div className="cs-er-num mono">{ticker.earnings.days}</div>
          <div className="cs-er-meta">
            <div className="mono dim2">days to print</div>
            <div className="mono"><b>{ticker.earnings.date}</b> · BMO · Wed</div>
          </div>
        </div>
        <div className="cs-er-tiles">
          <div className="cs-er-tile">
            <span className="label-cap">ESP</span>
            <span className="mono up"><b>+4.1%</b></span>
          </div>
          <div className="cs-er-tile">
            <span className="label-cap">EPS est.</span>
            <span className="mono"><b>$0.97</b></span>
          </div>
          <div className="cs-er-tile">
            <span className="label-cap">Beat rate</span>
            <span className="mono up"><b>6 / 8 Q</b></span>
          </div>
          <div className="cs-er-tile">
            <span className="label-cap">Implied move</span>
            <span className="mono warn"><b>±6.4%</b></span>
          </div>
        </div>
        <div className="cs-er-history mono">
          <span className="dim2">last 8Q:</span>
          {[+5.2,+3.1,-6.2,+2.4,+0.6,+2.8,-1.4,+3.9].map((r, i) => (
            <span key={i} className={r >= 0 ? "up" : "dn"}>{r >= 0 ? "▲" : "▼"}{Math.abs(r).toFixed(1)}</span>
          ))}
        </div>
      </div>

      <div className="cs-card cs-card--val">
        <div className="cs-card-hdr">
          <div className="label-cap">VALUATION · QUALITY</div>
          <Pill tone="amb" small>MoS 6%</Pill>
        </div>
        <div className="cs-val-row">
          <div className="cs-val-tile">
            <span className="label-cap">P/E TTM</span>
            <span className="mono"><b>{ticker.pe.toFixed(1)}</b></span>
            <span className="mono dim2">peers 24.1</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">Fwd P/E</span>
            <span className="mono up"><b>{ticker.fwdPe.toFixed(1)}</b></span>
            <span className="mono dim2">peers 21.0</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">P/S TTM</span>
            <span className="mono"><b>4.6</b></span>
            <span className="mono dim2">peers 5.2</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">EV/EBITDA</span>
            <span className="mono up"><b>14.8</b></span>
            <span className="mono dim2">peers 17.4</span>
          </div>
        </div>
        <div className="cs-val-row">
          <div className="cs-val-tile">
            <span className="label-cap">ROIC 5y</span>
            <span className="mono up"><b>18.2%</b></span>
            <span className="mono dim2">A · top quartile</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">Op margin</span>
            <span className="mono up"><b>16.4%</b></span>
            <span className="mono dim2">stable 3Q</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">Net debt/EBITDA</span>
            <span className="mono up"><b>0.81×</b></span>
            <span className="mono dim2">low leverage</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">FCF yield</span>
            <span className="mono up"><b>4.8%</b></span>
            <span className="mono dim2">vs UST 4.32%</span>
          </div>
        </div>
      </div>

      <div className="cs-card cs-card--src">
        <div className="cs-card-hdr">
          <div className="label-cap">WHY BUY · WHY NOT</div>
          <Pill tone="gn" small>BUY · 4 of 5</Pill>
        </div>
        <div className="cs-bb">
          <div className="cs-bb-col cs-bb--bull">
            <div className="cs-bb-h mono"><span className="up">▲ WHY BUY</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot up" /><span className="mono">Stacked-bullish · price &gt; all MAs · base #2 pivot</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot up" /><span className="mono">Edge validated · Wilson LB 47.7% · n=47 · PF 1.84</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot up" /><span className="mono">Regime-fit · setup wins 71% in bull/low-VIX</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot up" /><span className="mono">Insider cluster · CFO+COO buys 90d · sentiment +0.42</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot up" /><span className="mono">R:R 1.74 to T1 · downside bounded 0.39% NAV</span></div>
          </div>
          <div className="cs-bb-col cs-bb--bear">
            <div className="cs-bb-h mono"><span className="dn">▼ WHY NOT</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot amb" /><span className="mono">ER in 11d · implied move ±6.4% &gt; T1 distance</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot amb" /><span className="mono">Catalyst pillar soft (58) · drift, not dated event</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot amb" /><span className="mono">Value marginal · MoS only 6% · ~5% above fair</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot dn" /><span className="mono">Top-2 customers = 31% revenue concentration</span></div>
            <div className="cs-bb-row"><span className="cs-bb-dot amb" /><span className="mono">RVOL 1.18× · below 1.30× breakout-trigger floor</span></div>
          </div>
        </div>
        <div className="cs-bb-net mono">
          <span className="dim2">NET:</span> Edge &amp; structure outweigh the caveats — <b className="copper">take it, −25% size pre-ER</b>.
        </div>
      </div>
    </div>
  );
}
