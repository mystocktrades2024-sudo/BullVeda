// surface-crypto.jsx — Crypto Market surface. 24/7 majors+alts board with live
// prices, 24h/7d/30d change, mcap, volume, dominance, Fear & Greed.
// Data via window.CryptoFeed (sim now; EODHD/CoinGecko in production).

const { useState: useCX, useMemo: useCXm, useEffect: useCXe, useRef: useCXr } = React;

function cxFmtUsd(v) {
  if (v >= 1e12) return "$" + (v / 1e12).toFixed(2) + "T";
  if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return "$" + (v / 1e6).toFixed(1) + "M";
  return "$" + v.toFixed(0);
}
function cxFmtPx(v) { return "$" + (v >= 1 ? v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : v.toFixed(5)); }

// live-flash price cell (reuses the My-Portfolio pattern)
function CxPrice({ value }) {
  const prev = useCXr(value);
  const [flash, setFlash] = useCX(null);
  useCXe(() => {
    if (prev.current != null && value !== prev.current) {
      setFlash(value > prev.current ? "up" : "dn");
      const t = setTimeout(() => setFlash(null), 650);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return <span className={`mpf-live ${flash ? "mpf-live--" + flash : ""}`}>{cxFmtPx(value)}</span>;
}

function cxSpark(sym, up) {
  const code = sym.charCodeAt(0) + (sym.charCodeAt(1) || 66);
  const a = []; let v = 0;
  for (let i = 0; i < 20; i++) { v += (Math.sin(i * 0.7 + code) + (up ? 0.2 : -0.16)) * 0.5; a.push(v); }
  const w = 70, h = 22, mn = Math.min(...a), mx = Math.max(...a);
  const x = i => (i / (a.length - 1)) * w, y = val => h - ((val - mn) / ((mx - mn) || 1)) * (h - 4) - 2;
  return <svg width={w} height={h} className="cx-spark"><polyline points={a.map((p, i) => `${x(i)},${y(p)}`).join(" ")} fill="none" stroke={`var(--${up ? "gn" : "rd"})`} strokeWidth="1.4" /></svg>;
}

function useCrypto() {
  const [v, f] = useCX(0);
  useCXe(() => { const h = () => f(x => x + 1); window.addEventListener("crypto-change", h); return () => window.removeEventListener("crypto-change", h); }, []);
  return v;
}

function SurfaceCrypto({ onTicker }) {
  const ver = useCrypto();
  const CF = window.CryptoFeed;
  const [cat, setCat] = useCX("all");
  const [sort, setSort] = useCX("signal"); // signal | mcap | chg24 | vol

  // live 24/7 tick every 5s
  useCXe(() => {
    if (!CF || !CF.tick) return;
    const iv = setInterval(() => CF.tick(), 5000);
    return () => clearInterval(iv);
  }, []);

  const cats = useCXm(() => ["all", ...Array.from(new Set((CF ? CF.COINS : []).map(c => c.cat)))], []);
  const g = useCXm(() => (CF ? CF.globals() : {}), [ver]);
  const rows = useCXm(() => {
    let r = CF ? CF.list() : [];
    if (cat !== "all") r = r.filter(x => x.cat === cat);
    if (sort === "chg24") r = r.slice().sort((a, b) => b.chg24 - a.chg24);
    else if (sort === "vol") r = r.slice().sort((a, b) => b.vol - a.vol);
    else if (sort === "signal") r = r.slice().sort((a, b) => b.score - a.score);
    return r;
  }, [ver, cat, sort]);

  const topPick = useCXm(() => {
    const buys = (CF ? CF.list() : []).filter(x => x.verdict === "BUY").sort((a, b) => b.score - a.score);
    return buys[0] || null;
  }, [ver]);

  const Pct = ({ v }) => <span className={`tabular ${v >= 0 ? "up" : "dn"}`}>{v >= 0 ? "+" : ""}{v.toFixed(2)}%</span>;

  return (
    <div className="surface wsx wsx--copper cx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">DIGITAL ASSETS · 24/7 MARKET</div>
          <div className="mpf-titlerow"><h2 className="ipo-title">Crypto Market</h2></div>
          <div className="wsx-sub mono dim2">live prices · 24h / 7d / 30d · mcap · dominance · prices via EODHD crypto (simulated in this prototype)</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="5s" /></div>
      </div>

      <div className="ipo-kpis">
        <PfTile l="Total market cap" v={cxFmtUsd(g.totalMcap || 0)} s="all tracked assets" tone="ink" />
        <PfTile l="24h volume" v={cxFmtUsd(g.totalVol || 0)} s="aggregate" tone="cy" />
        <PfTile l="BTC dominance" v={`${(g.btcDom || 0).toFixed(1)}%`} s={`ETH ${(g.ethDom || 0).toFixed(1)}%`} tone="copper" />
        <PfTile l="Fear & Greed" v={g.fng || "—"} s={g.fngLabel || ""} tone={g.fng >= 55 ? "gn" : g.fng >= 45 ? "amb" : "rd"} />
      </div>

      <div className="ipo-bar">
        <div className="ipo-chips">
          {cats.map(c => <button key={c} className={`trk-chip ${cat === c ? "is-on" : ""}`} onClick={() => setCat(c)}>{c === "all" ? "All assets" : c}</button>)}
        </div>
        <div className="trk-toggle trk-toggle--sm ipo-bar-r">
          {[["signal", "Best signal"], ["mcap", "Mkt cap"], ["chg24", "24h move"], ["vol", "Volume"]].map(([id, l]) => (
            <button key={id} className={sort === id ? "is-on" : ""} onClick={() => setSort(id)}>{l}</button>
          ))}
        </div>
      </div>

      {topPick && (
        <div className="cx-pick" onClick={() => onTicker && onTicker(topPick.sym)}>
          <span className="cx-pick-tag mono">▶ TOP BUY SIGNAL</span>
          <span className="cx-pick-sym mono"><b>{topPick.sym}</b> {topPick.name}</span>
          <span className="cx-pick-score mono">score <b className="up">{topPick.score}</b></span>
          <span className="cx-pick-why mono dim2">{topPick.why}</span>
          <span className="cx-pick-px mono">{cxFmtPx(topPick.last)} <span className={topPick.chg24 >= 0 ? "up" : "dn"}>{topPick.chg24 >= 0 ? "+" : ""}{topPick.chg24.toFixed(2)}%</span></span>
        </div>
      )}

      <div className="wsx-body">
        <table className="dtable wsx-tbl pf-tbl cx-tbl">
          <thead><tr>
            <th className="r">#</th><th>Asset</th><th>Cat</th><th>Signal</th><th className="r">Price</th>
            <th className="r">24h</th><th className="r">7d</th><th className="r">30d</th>
            <th className="r">Market cap</th><th className="r">24h vol</th><th>7d trend</th>
          </tr></thead>
          <tbody>{rows.map(r => (
            <tr key={r.sym} onClick={() => onTicker && onTicker(r.sym)}>
              <td className="r tabular dim2">{r.rank}</td>
              <td><b className="cx-sym">{r.sym}</b><span className="cx-name dim2"> {r.name}</span></td>
              <td><span className={`cx-cat cx-cat--${r.cat.toLowerCase()}`}>{r.cat}</span></td>
              <td><span className={`cx-sig cx-sig--${r.vtone}`} title={r.why}>{r.verdict}<b className="cx-sig-sc">{r.score}</b></span></td>
              <td className="r tabular"><CxPrice value={r.last} /></td>
              <td className="r"><Pct v={r.chg24} /></td>
              <td className="r"><Pct v={r.chg7} /></td>
              <td className="r"><Pct v={r.chg30} /></td>
              <td className="r tabular"><b>{cxFmtUsd(r.mcap)}</b></td>
              <td className="r tabular dim2">{cxFmtUsd(r.vol)}</td>
              <td>{cxSpark(r.sym, r.chg7 >= 0)}</td>
            </tr>
          ))}</tbody>
        </table>
        <div className="lab-verdict mono dim2"><b>Signal</b> = Kairos trend read (BUY ≥70 · WATCH 50–69 · AVOID &lt;70): medium-term momentum minus 24h over-extension, per asset. Sort by <b>Best signal</b> to rank what to buy. Hover a signal for the reason. Live 24/7 — ticks every 5s. Demo model — map to your scoring service in production.</div>
      </div>
    </div>
  );
}

window.SurfaceCrypto = SurfaceCrypto;
