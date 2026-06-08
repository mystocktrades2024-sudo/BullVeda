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

// ── Real headline mapping ────────────────────────────────────────
// Mirror of home.jsx → realStories(): window.__BV.marketNews (loaded at boot
// from critical.market_news) → story objects. Never fabricates: returns null
// when there is no live feed so the served path renders an honest empty state.
// When served with no feed (or run un-served with no feed), the surface renders
// the honest empty state — never fabricated headlines or demo tickers.
function newsAgo(dateStr) {
  if (!dateStr) return "";
  const then = Date.parse(dateStr);
  if (!isFinite(then)) return "";
  const min = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (min < 60) return min + "m";
  const hr = min / 60;
  if (hr < 24) return (hr < 10 ? hr.toFixed(0) : Math.round(hr)) + "h";
  return Math.round(hr / 24) + "d";
}
const _newsSym0 = (s) => String(s || "").split(".")[0].toUpperCase();

// Derive a filter-rail category from the headline text + symbol coverage.
function newsCategory(title, summary, symCount) {
  const s = ((title || "") + " " + (summary || "")).toLowerCase();
  if (/\b(fda|approval|complete response|crl|recall|sec\b|antitrust|regulat|lawsuit|settlement)\b/.test(s)) return "reg";
  if (/\b(acqui|merger|takeover|buyout|deal to buy|stake in|strategic options)\b/.test(s)) return "ma";
  if (/\b(upgrade|downgrade|price target|initiat|reiterat|analyst|raised to|cut to|overweight|underweight)\b/.test(s)) return "analyst";
  if (/\b(earnings|q[1-4]\b|quarter|revenue|eps|guidance|beats?|misses?|raises? (fy|guide))\b/.test(s)) return "earnings";
  if (symCount === 0 || /\b(fed|cpi|inflation|jobs|payroll|gdp|rates?|treasury|yields?|dollar|powell|fomc|macro|economy)\b/.test(s)) return "mkt";
  return "mkt";
}

// Build real story objects from the live market-news feed. Returns null when
// served with no feed (→ honest empty), or [] never (callers handle null).
function realNewsItems() {
  const mn = (typeof window !== "undefined" && window.__BV && window.__BV.marketNews) || [];
  if (!mn.length) return null;
  const out = [];
  for (const a of mn) {
    if (!a || !a.title) continue;
    const syms = (a.symbols || []).map(_newsSym0).filter(Boolean);
    const tone = a.sentiment === "positive" ? "gn" : a.sentiment === "negative" ? "rd" : "amb";
    const pol = (typeof a.polarity === "number" && isFinite(a.polarity)) ? a.polarity : null;
    const sent = pol == null ? null : tone === "rd" ? -Math.abs(pol) : tone === "amb" ? 0 : Math.abs(pol);
    out.push({
      t: newsAgo(a.date), date: a.date, sym: syms[0] || null, syms,
      cat: newsCategory(a.title, a.summary, syms.length),
      sent, tone, src: a.source || "EODHD",
      head: a.title, blurb: a.summary || "", url: a.url || "",
      tags: syms.slice(0, 3),
    });
  }
  return out.length ? out : null;
}

function NewsHub({ onTicker, tabs }) {
  const [cat, setCat] = useNS("all");
  const [q, setQ] = useNS("");

  // Real feed from window.__BV.marketNews. null = no live feed → honest empty.
  const feed = useNSm(() => realNewsItems(), []);
  const hasFeed = !!(feed && feed.length);

  const rows = useNSm(() => {
    let r = feed || [];
    if (cat !== "all") r = r.filter(n => n.cat === cat);
    if (q.trim()) {
      const s = q.toLowerCase();
      r = r.filter(n => (n.head + " " + (n.blurb || "") + " " + (n.syms || []).join(" ") + " " + (n.tags || []).join(" ")).toLowerCase().includes(s));
    }
    return r;
  }, [feed, cat, q]);

  // Sentiment read banner — computed over the real feed only.
  const scored = (feed || []).filter(n => typeof n.sent === "number");
  const net = scored.length ? scored.reduce((s, n) => s + n.sent, 0) / scored.length : 0;
  const pos = (feed || []).filter(n => typeof n.sent === "number" && n.sent > 0.1).length;
  const neg = (feed || []).filter(n => typeof n.sent === "number" && n.sent < -0.1).length;
  const neu = (feed || []).length - pos - neg;
  const total = (feed || []).length;

  // Trending tickers — by real mention count across the live feed.
  // (All hooks must run before the honest-empty early return — Rules of Hooks.)
  const trend = useNSm(() => {
    const m = {};
    for (const n of (feed || [])) {
      for (const s of (n.syms || [])) {
        if (!m[s]) m[s] = { sym: s, n: 0, sent: 0, scored: 0 };
        m[s].n += 1;
        if (typeof n.sent === "number") { m[s].sent += n.sent; m[s].scored += 1; }
      }
    }
    return Object.values(m).sort((a, b) => b.n - a.n).slice(0, 6).map(r => {
      const avg = r.scored ? r.sent / r.scored : 0;
      return { sym: r.sym, n: r.n, avg, tone: avg > 0.05 ? "gn" : avg < -0.05 ? "rd" : "amb" };
    });
  }, [feed]);
  const trendMax = Math.max(1, ...trend.map(r => r.n));

  // Source breakdown — by real story count per publisher.
  const srcRows = useNSm(() => {
    const m = {};
    for (const n of (feed || [])) { const s = n.src || "EODHD"; m[s] = (m[s] || 0) + 1; }
    return Object.entries(m).map(([s, c]) => [s, c]).sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [feed]);
  const srcMax = Math.max(1, ...srcRows.map(r => r[1]));

  // Served + no feed → honest empty (no fabricated headlines).
  if (!hasFeed) {
    return (
      <div className="surface wsx wsx--violet news2">
        <div className="wsx-hdr">
          <div className="wsx-hdr-l">
            <div className="wsx-eyebrow mono">NEWS · SENTIMENT HUB</div>
            <h1 className="wsx-title mono">News &amp; Sentiment</h1>
            <div className="wsx-sub mono dim2">aggregated market headlines · sentiment-scored · ticker-linked · links to source</div>
          </div>
        </div>
        {tabs}
        <div className="nw-empty mono dim2" style={{ margin: "40px auto", textAlign: "center", maxWidth: 520 }}>
          No market headlines in the feed right now.
        </div>
      </div>
    );
  }

  return (
    <div className="surface wsx wsx--violet news2">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">NEWS · SENTIMENT HUB</div>
          <h1 className="wsx-title mono">News &amp; Sentiment</h1>
          <div className="wsx-sub mono dim2">aggregated market headlines · sentiment-scored · ticker-linked · links to source</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="live" />
          <span className="mono dim2">market news · {total} {total === 1 ? "story" : "stories"}</span>
        </div>
      </div>

      {tabs}

      {/* Sentiment read banner — computed from the live feed */}
      <div className="nw-read">
        <div className="nw-read-gauge">
          <div className="nw-read-num mono" data-tone={net > 0.2 ? "gn" : net < -0.1 ? "rd" : "amb"}>{net >= 0 ? "+" : ""}{net.toFixed(2)}</div>
          <div className="nw-read-lbl mono dim2">NET TONE</div>
        </div>
        <div className="nw-read-body mono">
          {scored.length ? (
            <>Tape reads <b className={net > 0.1 ? "up" : net < -0.1 ? "dn" : "warn"}>{net > 0.1 ? "constructive" : net < -0.1 ? "cautious" : "mixed"}</b> — {pos} positive vs {neg} negative across {scored.length} scored {scored.length === 1 ? "headline" : "headlines"} ({neu} neutral).</>
          ) : (
            <>Sentiment scores not available for the current feed — {total} {total === 1 ? "headline" : "headlines"} shown unscored.</>
          )}
        </div>
        <div className="nw-read-bars">
          <div className="nw-bar"><span className="nw-bar-l mono dim2">Positive</span><div className="nw-bar-t"><div className="nw-bar-f" style={{ width: `${total ? pos/total*100 : 0}%`, background: "var(--gn)" }} /></div><span className="mono up">{pos}</span></div>
          <div className="nw-bar"><span className="nw-bar-l mono dim2">Neutral</span><div className="nw-bar-t"><div className="nw-bar-f" style={{ width: `${total ? neu/total*100 : 0}%`, background: "var(--ink-3)" }} /></div><span className="mono dim2">{neu}</span></div>
          <div className="nw-bar"><span className="nw-bar-l mono dim2">Negative</span><div className="nw-bar-t"><div className="nw-bar-f" style={{ width: `${total ? neg/total*100 : 0}%`, background: "var(--rd)" }} /></div><span className="mono dn">{neg}</span></div>
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
          {rows.map((n, i) => {
            const href = n.url || srcUrl(n.src, n.sym);
            return (
            <article key={i} className={`nw-card nw-card--${n.tone}`}>
              <div className="nw-card-top">
                {n.t && <span className="mono nw-time dim2">{n.t}</span>}
                <a className="mono nw-src" href={href} target="_blank" rel="noopener noreferrer" title={`Open ${n.src}`}>{n.src} ↗</a>
                {n.sym && <button className="nw-sym mono" onClick={() => onTicker(n.sym)}>{n.sym} ›</button>}
                {typeof n.sent === "number" && (
                  <span className={`nw-sent mono ${n.sent >= 0 ? "up" : "dn"}`} title="sentiment score">{n.sent >= 0 ? "+" : ""}{n.sent.toFixed(1)}</span>
                )}
              </div>
              <a className="nw-head" href={href} target="_blank" rel="noopener noreferrer">{n.head}</a>
              {n.blurb && <div className="nw-blurb mono dim2">{n.blurb}</div>}
              <div className="nw-card-foot">
                <div className="nw-tags">
                  {(n.tags || []).map((tg, j) => <button key={j} className="nw-tag mono" onClick={() => onTicker(tg)}>{tg}</button>)}
                </div>
                <div className="nw-links mono">
                  <a href={href} target="_blank" rel="noopener noreferrer">Read on {n.src} ↗</a>
                  {n.sym && <a href="#" onClick={e => { e.preventDefault(); onTicker(n.sym); }}>Open {n.sym} →</a>}
                </div>
              </div>
            </article>
          );})}
          {rows.length === 0 && <div className="nw-empty mono dim2">No stories match this filter.</div>}
        </div>

        {/* Right rail */}
        <div className="nw-rail">
          <div className="lab-card">
            <div className="lab-card-h mono">🔥 TRENDING TICKERS · by mentions</div>
            <div className="nw-trend">
              {trend.length ? trend.map((r, i) => {
                const ss = (r.avg >= 0 ? "+" : "") + r.avg.toFixed(1);
                return (
                <button key={i} className="nw-trend-row" onClick={() => onTicker(r.sym)}>
                  <span className="mono nw-trend-sym"><b>{r.sym}</b></span>
                  <span className="nw-trend-bar"><i style={{ width: `${r.n/trendMax*100}%`, background: `var(--${r.tone})` }} /></span>
                  <span className="mono dim2 nw-trend-n">{r.n}</span>
                  {r.avg !== 0 && <span className={`mono nw-trend-s ${r.avg >= 0 ? "up" : "dn"}`}>{ss}</span>}
                </button>
              );}) : <div className="nw-empty mono dim2">No tagged tickers in the feed.</div>}
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">📰 SOURCE BREAKDOWN · tap to open</div>
            <div className="nw-src-list">
              {srcRows.map((s, i) => (
                <a key={i} className="nw-src-row" href={srcUrl(s[0], null)} target="_blank" rel="noopener noreferrer">
                  <span className="mono nw-src-n">{s[0]} ↗</span>
                  <div className="nw-src-bar"><i style={{ width: `${s[1]/srcMax*100}%` }} /></div>
                  <span className="mono dim2">{s[1]}</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="pm-note mono dim2">
        Headlines + sentiment aggregated from the live market-news feed · sentiment-scored ·
        ticker linkage via symbol match · every headline and "Read on …" link opens the original article at the source in a new tab.
      </div>
    </div>
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
