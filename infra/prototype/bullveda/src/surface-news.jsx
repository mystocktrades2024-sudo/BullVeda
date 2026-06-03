// surface-news.jsx — News · Sentiment hub (EODHD /news + sentiment shaped).
// Hero read + filter rail + main feed (linked) + right-rail: trending tickers,
// source breakdown, sentiment timeline, macro headlines.

const { useState: useNS, useMemo: useNSm } = React;

const NEWS_CATS = [
  ["all", "All"], ["mkt", "Macro · Market"], ["earnings", "Earnings"],
  ["analyst", "Analyst"], ["ma", "M&A"], ["reg", "Regulatory · FDA"], ["your", "Your book"],
];

// Resolve each publisher to its real page — ticker-deep-linked where supported,
// else the publisher's markets/news homepage. In production these are the exact
// article URLs returned by the news feed (Yahoo Finance / Zacks / EODHD).
const SOURCE_URL = {
  "Yahoo Finance":   s => s ? `https://finance.yahoo.com/quote/${s}/news`            : "https://finance.yahoo.com/news/",
  "Zacks":           s => s ? `https://www.zacks.com/stock/quote/${s}`               : "https://www.zacks.com/stock/research/",
  "Reuters":         s => s ? `https://www.reuters.com/site-search/?query=${s}`       : "https://www.reuters.com/markets/",
  "Bloomberg":       s => s ? `https://www.bloomberg.com/quote/${s}:US`               : "https://www.bloomberg.com/markets",
  "WSJ":             s => s ? `https://www.wsj.com/market-data/quotes/${s}`           : "https://www.wsj.com/news/markets",
  "CNBC":            s => s ? `https://www.cnbc.com/quotes/${s}`                      : "https://www.cnbc.com/markets/",
  "Barron's":        s => s ? `https://www.barrons.com/market-data/stocks/${(s||"").toLowerCase()}` : "https://www.barrons.com/market-data",
  "MarketWatch":     s => s ? `https://www.marketwatch.com/investing/stock/${(s||"").toLowerCase()}` : "https://www.marketwatch.com/",
  "Seeking Alpha":   s => s ? `https://seekingalpha.com/symbol/${s}/news`             : "https://seekingalpha.com/market-news",
  "FT":              () => "https://www.ft.com/markets",
  "Goldman":         s => s ? `https://finance.yahoo.com/quote/${s}/analysis`         : "https://finance.yahoo.com/research/",
  "Morgan Stanley":  s => s ? `https://finance.yahoo.com/quote/${s}/analysis`         : "https://finance.yahoo.com/research/",
  "Endpoints":       () => "https://endpts.com/",
  "FierceBio":       () => "https://www.fiercebiotech.com/",
};
function srcUrl(src, sym) {
  const f = SOURCE_URL[src];
  return f ? f(sym) : (sym ? `https://finance.yahoo.com/quote/${sym}/news` : "https://finance.yahoo.com/news/");
}

const NEWS_ITEMS = [
  { t: "12:48", sym: "NVDA", cat: "mkt",      sent: +0.8, tone: "gn", src: "Yahoo Finance", imp: "high", head: "Chipmakers rally as data-center capex guidance lifts sector", blurb: "Multiple hyperscalers reaffirm 2026 AI infrastructure spend; semis broadly bid pre-open.", tags: ["AI", "Semis", "Capex"] },
  { t: "11:30", sym: null,   cat: "mkt",      sent: +0.3, tone: "gn", src: "Reuters",    imp: "high", head: "Fed minutes preview: market prices 88% hold, dot-plot in focus", blurb: "Rates desk positioning skews to a hawkish-hold; 2Y yields ticked up 3bp.", tags: ["Fed", "Rates", "Macro"] },
  { t: "10:14", sym: "ARCM", cat: "your",     sent: +0.7, tone: "gn", src: "Zacks",      imp: "med",  head: "Specialty materials names see insider buying cluster", blurb: "Form-4 filings show CFO + COO net purchases across three coatings names this week.", tags: ["Insider", "Materials"] },
  { t: "09:02", sym: "XOM",  cat: "mkt",      sent: -0.4, tone: "rd", src: "Yahoo Finance", imp: "med",  head: "Crude slips on demand worries; energy complex under pressure", blurb: "Brent −1.8% after soft China PMI; integrated majors lead the leg lower.", tags: ["Energy", "Crude"] },
  { t: "08:20", sym: "GENO", cat: "earnings", sent: +0.5, tone: "gn", src: "FierceBio",  imp: "high", head: "Genoa Bio Phase-2 readout ahead of next-week print", blurb: "Primary endpoint met in mid-stage trial; Street models a probability-weighted bump.", tags: ["Biotech", "FDA", "Catalyst"] },
  { t: "07:55", sym: "CRWV", cat: "earnings", sent: +0.8, tone: "gn", src: "Zacks",      imp: "high", head: "CoreWave beats Q1, raises FY guide on data-center demand", blurb: "Revenue +34% YoY, raises FY EBITDA; shares +9% pre-market.", tags: ["Earnings", "Beat", "Cloud"] },
  { t: "07:30", sym: "ARGN", cat: "analyst",  sent: +0.6, tone: "gn", src: "Goldman",    imp: "med",  head: "Argentum upgraded to Buy, PT $240 on automation cycle", blurb: "Analyst cites order backlog inflection and margin expansion into H2.", tags: ["Upgrade", "Robotics"] },
  { t: "06:48", sym: "BIVO", cat: "reg",      sent: -0.6, tone: "rd", src: "Endpoints",  imp: "high", head: "Bivota gets FDA complete response letter; pipeline reset", blurb: "Agency requests additional CMC data; approval timeline pushed ~9 months.", tags: ["FDA", "CRL", "Biotech"] },
  { t: "06:12", sym: "MERC", cat: "ma",       sent: +0.4, tone: "amb", src: "Bloomberg", imp: "med",  head: "Mercia Semi explores strategic options, sources say", blurb: "Company said to work with advisors on a potential sale of its memory unit.", tags: ["M&A", "Rumor", "Semis"] },
  { t: "05:50", sym: "DRSH", cat: "mkt",      sent: +0.5, tone: "gn", src: "MarketWatch", imp: "low",  head: "Energy bid as supply headline lifts crude 2%", blurb: "Sympathy strength across E&P; Druseh leads mid-cap movers.", tags: ["Energy", "Sympathy"] },
  { t: "05:12", sym: "NVRH", cat: "analyst",  sent: -0.3, tone: "rd", src: "Morgan Stanley", imp: "low", head: "Novara Health cut to Equal-Weight on valuation", blurb: "Downgrade on risk/reward after the recent run; estimates unchanged.", tags: ["Downgrade", "Healthcare"] },
  { t: "04:40", sym: null,   cat: "mkt",      sent: +0.2, tone: "ink", src: "Reuters",   imp: "med",  head: "Dollar steady ahead of CPI; gold holds near record", blurb: "DXY flat, 10Y at 4.32%; positioning light into the inflation print.", tags: ["FX", "Gold", "CPI"] },
];

function NewsHub({ onTicker, tabs }) {
  const [cat, setCat] = useNS("all");
  const [q, setQ] = useNS("");
  const rows = useNSm(() => {
    let r = NEWS_ITEMS;
    if (cat !== "all") r = r.filter(n => n.cat === cat);
    if (q.trim()) {
      const s = q.toLowerCase();
      r = r.filter(n => (n.head + " " + (n.sym || "") + " " + n.tags.join(" ")).toLowerCase().includes(s));
    }
    return r;
  }, [cat, q]);

  const net = (NEWS_ITEMS.reduce((s, n) => s + n.sent, 0) / NEWS_ITEMS.length);
  const pos = NEWS_ITEMS.filter(n => n.sent > 0.1).length;
  const neg = NEWS_ITEMS.filter(n => n.sent < -0.1).length;

  return (
    <div className="surface wsx wsx--violet news2">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">NEWS · SENTIMENT HUB</div>
          <h1 className="wsx-title mono">News &amp; Sentiment</h1>
          <div className="wsx-sub mono dim2">aggregated from Yahoo Finance · Zacks · Reuters &amp; more · sentiment-scored · ticker-linked · links to source</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="22s" />
          <span className="mono dim2">EODHD /news · {NEWS_ITEMS.length} stories · last 8h</span>
        </div>
      </div>

      {tabs}

      {/* Sentiment read banner */}
      <div className="nw-read">
        <div className="nw-read-gauge">
          <div className="nw-read-num mono" data-tone={net > 0.2 ? "gn" : net < -0.1 ? "rd" : "amb"}>{net >= 0 ? "+" : ""}{net.toFixed(2)}</div>
          <div className="nw-read-lbl mono dim2">NET TONE · 8h</div>
        </div>
        <div className="nw-read-body mono">
          Tape reads <b className="up">constructive</b> — {pos} positive vs {neg} negative stories, led by AI/semis capex and an earnings beat (CRWV +9%).
          <b className="warn"> Watch:</b> CPI at 08:30 dominates; one biotech CRL (BIVO) and an energy-demand wobble are the only real negatives.
        </div>
        <div className="nw-read-bars">
          <div className="nw-bar"><span className="nw-bar-l mono dim2">Positive</span><div className="nw-bar-t"><div className="nw-bar-f" style={{ width: `${pos/NEWS_ITEMS.length*100}%`, background: "var(--gn)" }} /></div><span className="mono up">{pos}</span></div>
          <div className="nw-bar"><span className="nw-bar-l mono dim2">Neutral</span><div className="nw-bar-t"><div className="nw-bar-f" style={{ width: `${(NEWS_ITEMS.length-pos-neg)/NEWS_ITEMS.length*100}%`, background: "var(--ink-3)" }} /></div><span className="mono dim2">{NEWS_ITEMS.length-pos-neg}</span></div>
          <div className="nw-bar"><span className="nw-bar-l mono dim2">Negative</span><div className="nw-bar-t"><div className="nw-bar-f" style={{ width: `${neg/NEWS_ITEMS.length*100}%`, background: "var(--rd)" }} /></div><span className="mono dn">{neg}</span></div>
        </div>
      </div>

      <div className="lab-tabs">
        {NEWS_CATS.map(([id, l]) => (
          <button key={id} className={`lab-tab ${cat === id ? "is-on" : ""}`} onClick={() => setCat(id)}>{l}</button>
        ))}
        <input className="nw-search mono" placeholder="⌕ search headlines, tickers, tags…" value={q} onChange={e => setQ(e.target.value)} />
      </div>

      <div className="nw-grid">
        {/* Main feed */}
        <div className="nw-feed">
          {rows.map((n, i) => (
            <article key={i} className={`nw-card nw-card--${n.tone}`}>
              <div className="nw-card-top">
                <span className="mono nw-time dim2">{n.t}</span>
                <a className="mono nw-src" href={srcUrl(n.src, n.sym)} target="_blank" rel="noopener noreferrer" title={`Open ${n.src}`}>{n.src} ↗</a>
                {n.imp === "high" && <span className="nw-imp mono">●  HIGH</span>}
                {n.sym && <button className="nw-sym mono" onClick={() => onTicker(n.sym)}>{n.sym} ›</button>}
                <span className={`nw-sent mono ${n.sent >= 0 ? "up" : "dn"}`} title="sentiment score">{n.sent >= 0 ? "+" : ""}{n.sent.toFixed(1)}</span>
              </div>
              <a className="nw-head" href={srcUrl(n.src, n.sym)} target="_blank" rel="noopener noreferrer">{n.head}</a>
              <div className="nw-blurb mono dim2">{n.blurb}</div>
              <div className="nw-card-foot">
                <div className="nw-tags">
                  {n.tags.map((tg, j) => <span key={j} className="nw-tag mono">{tg}</span>)}
                </div>
                <div className="nw-links mono">
                  <a href={srcUrl(n.src, n.sym)} target="_blank" rel="noopener noreferrer">Read on {n.src} ↗</a>
                  {n.sym && <a href="#" onClick={e => { e.preventDefault(); onTicker(n.sym); }}>Open {n.sym} →</a>}
                </div>
              </div>
            </article>
          ))}
          {rows.length === 0 && <div className="nw-empty mono dim2">No stories match this filter.</div>}
        </div>

        {/* Right rail */}
        <div className="nw-rail">
          <div className="lab-card">
            <div className="lab-card-h mono">🔥 TRENDING TICKERS · by mentions</div>
            <div className="nw-trend">
              {[["CRWV", 14, "+0.8", "gn"], ["NVDA", 11, "+0.7", "gn"], ["BIVO", 9, "−0.6", "rd"], ["GENO", 7, "+0.5", "gn"], ["MERC", 6, "+0.4", "amb"], ["ARCM", 5, "+0.7", "gn"]].map((r, i) => (
                <button key={i} className="nw-trend-row" onClick={() => onTicker(r[0])}>
                  <span className="mono nw-trend-sym"><b>{r[0]}</b></span>
                  <span className="nw-trend-bar"><i style={{ width: `${r[1]/14*100}%`, background: `var(--${r[3]})` }} /></span>
                  <span className="mono dim2 nw-trend-n">{r[1]}</span>
                  <span className={`mono nw-trend-s ${r[2].startsWith("+") ? "up" : "dn"}`}>{r[2]}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">📰 SOURCE BREAKDOWN · tap to open</div>
            <div className="nw-src-list">
              {[["Yahoo Finance", 3, "gn"], ["Reuters", 2, "gn"], ["Zacks", 2, "gn"], ["Bloomberg", 1, "amb"], ["Goldman", 1, "gn"], ["FierceBio", 1, "ink"]].map((s, i) => (
                <a key={i} className="nw-src-row" href={srcUrl(s[0], null)} target="_blank" rel="noopener noreferrer">
                  <span className="mono nw-src-n">{s[0]} ↗</span>
                  <div className="nw-src-bar"><i style={{ width: `${s[1]/3*100}%` }} /></div>
                  <span className="mono dim2">{s[1]}</span>
                </a>
              ))}
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">⚠ MACRO WIRE · today</div>
            <div className="nw-macro">
              {[["08:30", "CPI Core MoM", "HIGH", "rd"], ["10:00", "Powell speaks", "HIGH", "rd"], ["—", "Fed minutes (Wed)", "HIGH", "amb"], ["—", "PCE (Fri)", "HIGH", "amb"]].map((m, i) => (
                <div key={i} className={`nw-macro-row nw-macro--${m[3]}`}>
                  <span className="mono nw-macro-t dim2">{m[0]}</span>
                  <span className="mono nw-macro-e">{m[1]}</span>
                  <Pill tone={m[2] === "HIGH" ? "rd" : "amb"} small>{m[2]}</Pill>
                </div>
              ))}
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">📡 SENTIMENT · 24h trend</div>
            <NwSentTrend />
            <div className="lab-verdict mono dim2">Net tone improving since 04:00 — risk-on bias building into the open, pending CPI.</div>
          </div>
        </div>
      </div>

      <div className="pm-note mono dim2">
        Headlines + sentiment aggregated from <b>Yahoo Finance</b>, <b>Zacks</b>, Reuters, Bloomberg &amp; more (publisher-weighted, 22s poll) · macro from the economic calendar ·
        ticker linkage via NER + symbol match · every headline and "Read on …" link opens the original article at the source in a new tab.
      </div>
    </div>
  );
}

function NwSentTrend() {
  const data = useNSm(() => {
    const a = []; let v = -0.1;
    for (let i = 0; i < 24; i++) { v += (Math.sin(i * 0.5) * 0.06) + 0.02 + (Math.random() - 0.45) * 0.05; a.push(v); }
    return a;
  }, []);
  const w = 240, h = 60, min = Math.min(...data, -0.3), max = Math.max(...data, 0.6);
  const x = i => (i / (data.length - 1)) * w;
  const y = vv => h - ((vv - min) / (max - min)) * (h - 6) - 3;
  const zero = y(0);
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
      <defs><linearGradient id="nw-st" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.3" /><stop offset="100%" stopColor="var(--gn)" stopOpacity="0" /></linearGradient></defs>
      <line x1="0" y1={zero} x2={w} y2={zero} stroke="var(--glass-line)" strokeDasharray="2 3" />
      <path d={`M 0 ${zero} L ${data.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w} ${zero} Z`} fill="url(#nw-st)" />
      <polyline points={data.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke="var(--gn)" strokeWidth="1.6" fill="none" style={{ filter: "drop-shadow(0 0 4px var(--gn))" }} />
      <circle cx={x(data.length - 1)} cy={y(data[data.length - 1])} r="3" fill="var(--gn)" style={{ filter: "drop-shadow(0 0 6px var(--gn))" }} />
    </svg>
  );
}

// Shared sub-tab switcher for the merged Sentiment hub (Editorial news + Social crowd).
function SentimentTabs({ view, onPick }) {
  return (
    <div className="lab-tabs snt-tabs">
      <button className={`lab-tab ${view === "news" ? "is-on" : ""}`} onClick={() => onPick("news")}>Editorial</button>
      <button className={`lab-tab ${view === "social" ? "is-on" : ""}`} onClick={() => onPick("social")}>Social</button>
    </div>
  );
}

// SurfaceNews is now the unified Sentiment hub: editorial news feed + social
// crowd-positioning, toggled by a segmented control in the header.
function SurfaceNews({ onTicker, initialView }) {
  const [view, setView] = useNS(() => {
    if (initialView) return initialView;
    try { return localStorage.getItem("st-sentiment-view") || "news"; } catch (e) { return "news"; }
  });
  const pick = v => { setView(v); try { localStorage.setItem("st-sentiment-view", v); } catch (e) {} };
  const tabs = <SentimentTabs view={view} onPick={pick} />;
  const Social = window.SurfaceSocial;
  if (view === "social" && Social) return <Social onTicker={onTicker} tabs={tabs} />;
  return <NewsHub onTicker={onTicker} tabs={tabs} />;
}

Object.assign(window, { SurfaceNews, NewsHub, SentimentTabs });
