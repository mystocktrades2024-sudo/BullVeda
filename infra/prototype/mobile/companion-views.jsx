// companion-views.jsx — hero, list, detail shell, sheets, responsive root.
const { useState: uS, useEffect: uE, useRef: uR } = React;
const { GaugeRing, SecBadge, Pillars, Sec, Panel, KpiGrid, Chip, Row, Read, Ico } = window;
const { scoreTone, toneVar, fmt, sign, resolveTicker } = window.cmpHelpers;

const MODES = ["SWING", "POSITION", "INVESTMENT"];
const ALERT_SYM = "ARCM"; // the ticker the Slack alert references

function useWatched(sym) {
  const [, f] = uS(0);
  uE(() => { const h = () => f((x) => x + 1); window.addEventListener("watchlist-change", h); return () => window.removeEventListener("watchlist-change", h); }, []);
  return window.WatchStore ? window.WatchStore.has(sym) : false;
}

/* ───────────────────────── hero ───────────────────────── */
function VerdictHero({ ticker, mode }) {
  const t = ticker, tone = scoreTone(t.score);
  const conf = t.score >= 70 ? "HIGH" : t.score >= 55 ? "MODERATE" : "LOW";
  return (
    <div className="cmp-hero">
      <div className="cmp-hero-top">
        <div className="cmp-hero-ring">
          <GaugeRing value={t.score} size={92} stroke={7} />
          <div className="cmp-hero-ring-num"><b style={{ color: toneVar(tone) }}>{t.score}</b><span>/ 100</span></div>
        </div>
        <div className="cmp-hero-id">
          <div className="cmp-hero-bias" style={{ color: toneVar(window.secBiasTone(t.verdict)) }}>{window.secBias(t.verdict)}</div>
          <div className="cmp-hero-conf">Composite bias · {mode} · confidence <b style={{ color: toneVar(tone) }}>{conf}</b></div>
          <div className="cmp-hero-setup">{t.setupFamily} · hold ~{t.holdDays}d · target <b>{fmt(t.rMultiple, 1)}R</b></div>
        </div>
      </div>
      <Pillars pillars={t.pillars} />
    </div>
  );
}

/* ───────────────────────── list ───────────────────────── */
function StockCard({ row, selected, onOpen, pinned }) {
  const tone = scoreTone(row.score);
  return (
    <button className={`cmp-card ${selected ? "is-sel" : ""}`} onClick={() => onOpen(row.sym)}>
      <div className="cmp-card-gauge">
        <GaugeRing value={row.score} size={46} stroke={4} />
        <div className="cmp-card-gauge-num mono" style={{ color: toneVar(tone) }}>{row.score}</div>
      </div>
      <div className="cmp-card-main">
        <div className="cmp-card-row1">
          <span className="cmp-card-sym">{row.sym}</span>
          <span className="cmp-card-name">{row.name}</span>
        </div>
        <div className="cmp-card-row2">
          <span className="cmp-card-price mono">${fmt(row.price)}</span>
          <span className={`cmp-card-chg mono ${row.chg >= 0 ? "up" : "dn"}`}>{sign(row.chg)}{fmt(row.chg)}%</span>
          <SecBadge verdict={row.verdict} />
          <span className="cmp-card-setup">{row.setup}</span>
        </div>
      </div>
      {!pinned && <span className="cmp-card-chev">{Ico.chevR}</span>}
    </button>
  );
}

function ScanList({ scan, setScan, selectedSym, onOpen, posture }) {
  const all = window.WATCHLIST || [];
  const buy = all.filter((r) => r.verdict === "BUY");
  const elite = all.filter((r) => r.score >= 65);
  const byScore = [...all].sort((a, b) => b.score - a.score);
  const list = scan === "elite" ? [...elite].sort((a, b) => b.score - a.score)
    : scan === "all" ? byScore : buy;
  const alertRow = all.find((r) => r.sym === ALERT_SYM);
  const caps = { all: "All candidates", buy: "Bullish candidates", elite: "Elite picks" };
  return (
    <div className="cmp-rail">
      <div className="cmp-listhead">
        <div className="cmp-brandrow">
          <div className="cmp-brand-dot">S</div>
          <div>
            <div className="cmp-brand-name">Swing<b>Trade</b></div>
            <div className="cmp-brand-sub">Field companion</div>
          </div>
          <div className="cmp-listhead-spacer" />
          {window.HeaderActions && <window.HeaderActions />}
        </div>
        <div className="cmp-scantabs">
          <button className={`cmp-scantab ${scan === "all" ? "is-on" : ""}`} onClick={() => setScan("all")}>
            <b>{all.length}</b><span className="cmp-scantab-n">ALL</span>
          </button>
          <button className={`cmp-scantab ${scan === "buy" ? "is-on" : ""}`} onClick={() => setScan("buy")}>
            <b>{buy.length}</b><span className="cmp-scantab-n">BULLISH</span>
          </button>
          <button className={`cmp-scantab ${scan === "elite" ? "is-on" : ""}`} onClick={() => setScan("elite")}>
            <b>{elite.length}</b><span className="cmp-scantab-n">ELITE</span>
          </button>
        </div>
      </div>
      <div className="cmp-listscroll">
        {alertRow && (
          <div className="cmp-alertpin">
            <div className="cmp-alertpin-tag">{Ico.bolt} Slack alert · 2m ago</div>
            <div style={{ height: 8 }} />
            <StockCard row={alertRow} selected={selectedSym === alertRow.sym} onOpen={onOpen} pinned />
          </div>
        )}
        <div className="cmp-listscroll-cap">
          <span className="cmp-cap">{caps[scan]}</span>
          <span className="cmp-cap">{list.length} names</span>
        </div>
        {list.map((r) => <StockCard key={r.sym} row={r} selected={selectedSym === r.sym} onOpen={onOpen} />)}
        <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
      </div>
    </div>
  );
}

/* ───────────────────────── detail ───────────────────────── */
function LensStrip({ lensId, setLensId }) {
  const ref = uR(null);
  return (
    <div className="cmp-lensstrip" ref={ref}>
      {(window.LENSES || []).map((l, i) => (
        <button key={l.id} className={`cmp-lenstab ${lensId === l.id ? "is-on" : ""}`}
          onClick={(e) => { setLensId(l.id); e.currentTarget.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" }); }}>
          {window.LENS_ICONS[l.id]}
          <span className="cmp-lenstab-n mono">{String(i + 1).padStart(2, "0")}</span>
          <span className="cmp-lenstab-l">{l.label.replace(/ · .*/, "")}</span>
        </button>
      ))}
    </div>
  );
}

function DetailM({ ticker, mode, setMode, lensId, setLensId, onBack, posture, onAction }) {
  // REAL detail: start from the elite-derived base, upgrade in place to the full
  // /api/ticker scored row (rsi, beta, fundamentals, trade plan, ML — all live).
  const t = window.useLiveTicker(ticker);
  const watched = useWatched(t.symbol);
  const Lens = (window.MOBILE_LENSES || {})[lensId];
  const bodyRef = uR(null);
  uE(() => { if (bodyRef.current) bodyRef.current.scrollTop = 0; }, [lensId, t.symbol]);
  return (
    <div className="cmp-detail">
      <div className="cmp-dhead">
        <div className="cmp-dhead-row">
          {posture === "phone" && <button className="cmp-back" onClick={onBack}>{Ico.chevL}</button>}
          <div className="cmp-dhead-id">
            <div className="cmp-dhead-sym"><b>{t.symbol}</b><span className="cmp-dhead-exch">{t.exchange}</span></div>
            <div className="cmp-dhead-name">{t.name} · {t.sector}</div>
          </div>
          <button className={`cmp-iconbtn ${watched ? "is-on" : ""}`} onClick={() => window.WatchStore.toggle({ sym: t.symbol, name: t.name, sector: t.sector, price: t.price, chg: t.chg, score: t.score, verdict: t.verdict, setup: t.setupFamily })}>
            {watched ? Ico.starFill : Ico.star}
          </button>
          <button className="cmp-iconbtn" onClick={() => onAction("actions")}>{Ico.dots}</button>
        </div>
        <div className="cmp-dhead-quote">
          <span className="cmp-dhead-price mono">${fmt(t.price)}</span>
          <span className={`cmp-dhead-chg mono ${t.chg >= 0 ? "up" : "dn"}`}>{sign(t.chgAbs)}{fmt(t.chgAbs)} ({sign(t.chg)}{fmt(t.chg)}%)</span>
          <div className="cmp-dhead-stats">
            <span className="cmp-dhead-stat mono">VOL <b>{fmt(t.vol / 1e6, 1)}M</b></span>
            <span className="cmp-dhead-stat mono">RSI <b>{fmt(t.rsi, 0)}</b></span>
            <span className="cmp-dhead-stat mono">β <b>{fmt(t.beta)}</b></span>
          </div>
        </div>
        <div className="cmp-modeseg">
          {MODES.map((m) => <button key={m} className={mode === m ? "is-on" : ""} onClick={() => setMode(m)}>{m === "INVESTMENT" ? "INVEST" : m}</button>)}
        </div>
      </div>
      <LensStrip lensId={lensId} setLensId={setLensId} />
      <div className="cmp-dbody" ref={bodyRef}>
        {Lens ? <Lens ticker={t} mode={mode} /> : <div className="cmp-disc">Lens unavailable.</div>}
      </div>
      <ActionBar ticker={t} watched={watched} onAction={onAction} />
    </div>
  );
}

function ActionBar({ ticker, watched, onAction }) {
  const t = ticker;
  return (
    <div className="cmp-actionbar">
      <button className="cmp-act cmp-act-primary" onClick={() => onAction("copy")}>{Ico.copy}<span>Copy levels</span></button>
      <button className="cmp-act" onClick={() => onAction("alert")}>{Ico.bell}<span>Alert</span></button>
      <button className={`cmp-act ${watched ? "is-on" : ""}`} onClick={() => window.WatchStore.toggle({ sym: t.symbol, name: t.name, sector: t.sector, price: t.price, chg: t.chg, score: t.score, verdict: t.verdict, setup: t.setupFamily })}>
        {watched ? Ico.starFill : Ico.star}<span>{watched ? "Saved" : "Watchlist"}</span>
      </button>
      <button className="cmp-act" onClick={() => onAction("desktop")}>{Ico.ext}<span>Desktop</span></button>
    </div>
  );
}

/* ───────────────────────── sheets ───────────────────────── */
function Sheet({ onClose, children }) {
  return (
    <div className="cmp-scrim" onClick={onClose}>
      <div className="cmp-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="cmp-sheet-grip" />
        {children}
      </div>
    </div>
  );
}

function ActionSheet({ ticker, onClose, onAction }) {
  const t = ticker;
  const item = (icon, title, sub, fn) => (
    <button className="cmp-sheet-item" onClick={fn}>{icon}<span>{title}{sub && <span className="cmp-sheet-item-sub">{sub}</span>}</span></button>
  );
  return (
    <Sheet onClose={onClose}>
      <div className="cmp-sheet-title">{t.symbol} · {window.secBias(t.verdict)} {t.score}</div>
      <div className="cmp-sheet-sub">{t.name}</div>
      {item(Ico.copy, "Copy trade levels", `Entry ${fmt(t.pivot)} · Stop ${fmt(t.stop)} · T1 ${fmt(t.t1)}`, () => onAction("copy"))}
      {item(Ico.bell, "Set price alert", "Notify on trigger or stop", () => onAction("alert"))}
      {item(Ico.share, "Share to Slack", "Send this read to the channel", () => onAction("share"))}
      {item(Ico.ext, "Open full terminal", "Continue on desktop", () => onAction("desktop"))}
    </Sheet>
  );
}

function AlertSheet({ ticker, onClose, onToast }) {
  const t = ticker;
  const [px, setPx] = uS(+fmt(t.pivot));
  const [kind, setKind] = uS("above");
  return (
    <Sheet onClose={onClose}>
      <div className="cmp-sheet-title">Price alert · {t.symbol}</div>
      <div className="cmp-sheet-sub">Get a push when {t.symbol} crosses your level. Current ${fmt(t.price)}.</div>
      <div className="cmp-modeseg" style={{ marginBottom: 14 }}>
        {[["above", "Above ▲"], ["below", "Below ▼"]].map(([k, l]) => <button key={k} className={kind === k ? "is-on" : ""} onClick={() => setKind(k)}>{l}</button>)}
      </div>
      <div className="cmp-sheet-row">
        <div className="cmp-stepper"><button onClick={() => setPx((p) => +(p - 0.5).toFixed(2))}>–</button></div>
        <input className="cmp-sheet-input mono" value={px} onChange={(e) => setPx(e.target.value)} inputMode="decimal" />
        <div className="cmp-stepper"><button onClick={() => setPx((p) => +(+p + 0.5).toFixed(2))}>+</button></div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="cmp-sheet-btn cmp-sheet-btn--ghost" style={{ flex: 1 }} onClick={() => { setPx(+fmt(t.pivot)); setKind("above"); }}>Use trigger</button>
        <button className="cmp-sheet-btn" style={{ flex: 1.4 }} onClick={() => { window.AlertStore && window.AlertStore.add({ sym: t.symbol, kind, px: +px }); onClose(); onToast(`Alert set · ${t.symbol} ${kind} $${px}`); }}>Set alert</button>
      </div>
    </Sheet>
  );
}

/* ───────────────────────── exports ───────────────────────── */
// Building blocks consumed by companion-surfaces.jsx + companion-app.jsx.
Object.assign(window, {
  VerdictHero, StockCard, ScanList, LensStrip, DetailM, ActionBar,
  Sheet, ActionSheet, AlertSheet, useWatched, ALERT_SYM, MODES,
});
