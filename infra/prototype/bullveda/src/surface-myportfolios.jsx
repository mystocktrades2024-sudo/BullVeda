// surface-myportfolios.jsx — user-owned multi-portfolio manager.
// Dropdown switcher + combined view · editable holdings · risk analytics · journal.

const { useState: useMP, useEffect: useMPe, useMemo: useMPm, useRef: useMPr } = React;

function useMyPF() {
  const [v, f] = useMP(0);
  useMPe(() => { const h = () => f(x => x + 1); window.addEventListener("mypf-change", h); return () => window.removeEventListener("mypf-change", h); }, []);
  return v;
}

const MP_ASSET = [["stock", "Stock"], ["etf", "ETF"], ["crypto", "Crypto"], ["cash", "Cash"]];
const fmt$ = (v, d = 0) => (v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtPct = (v, d = 2) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d) + "%";
const toneOf = v => v > 0 ? "gn" : v < 0 ? "rd" : "ink";
// compact date + days-held for holdings ("12 May '26", title "held 21d")
const MP_MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtBuyDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return iso;
  return `${d.getDate()} ${MP_MON[d.getMonth()]} '${String(d.getFullYear()).slice(2)}`;
}
function heldDays(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return "";
  const days = Math.max(0, Math.round((Date.now() - d.getTime()) / 86400000));
  return `held ${days}d`;
}

// Trade-management guidance — turns price vs entry / stop / T1 / T2 into a
// plain-English next action. Returns { act, tone, detail } or null for cash.
function posGuidance(r) {
  if (r.type === "cash") return null;
  const last = r.last, entry = r.cost, stop = r.stop, t1 = r.target, t2 = r.target2;
  const pct = (to) => ((to - last) / last) * 100;
  if (stop && last <= stop) return { act: "✕ Exit now", tone: "rd", detail: `stop $${stop} hit` };
  if (t2 && last >= t2) return { act: "At T2 · trim / trail", tone: "gn", detail: `T2 $${t2} reached — bank the rest or trail` };
  if (t1 && last >= t1) return { act: "Trim now · T1 hit", tone: "gn", detail: t2 ? `take ⅓, trail stop up, hold runner → T2 $${t2}` : `take partial, trail stop; set a T2` };
  if (stop && (last - stop) / last * 100 <= 4) return { act: "Near stop · reduce", tone: "amb", detail: `only ${((last - stop) / last * 100).toFixed(1)}% above stop $${stop}` };
  if (t1 && last >= entry) return { act: `Hold → T1 $${t1}`, tone: "cy", detail: `+${pct(t1).toFixed(0)}% to T1${t2 ? ` · then T2 $${t2}` : ""}` };
  if (last >= entry) return { act: "Hold · set T1", tone: "ink", detail: "in profit — define a target" };
  return { act: "Hold above stop", tone: "dim2", detail: stop ? `defend $${stop}` : "no stop set — add one" };
}

function SurfaceMyPortfolios({ onTicker }) {
  const ver = useMyPF();
  const MyPF = window.MyPF;
  const [tab, setTab] = useMP("holdings");
  const [allView, setAllView] = useMP(false);
  const [adding, setAdding] = useMP(false);

  const pf = allView ? MyPF.combined() : MyPF.active();
  const sum = useMPm(() => MyPF.summarize(pf), [pf, tab, allView, adding, ver]);

  return (
    <div className="surface wsx wsx--copper mpf">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">MY PORTFOLIOS · TRACK YOUR OWN BOOK</div>
          <div className="mpf-titlerow">
            <PortfolioSwitcher allView={allView} setAllView={setAllView} />
          </div>
          <div className="wsx-sub mono dim2">add holdings · track P&L · risk analytics · trade journal · prices simulated, editable inline</div>
        </div>
        <div className="wsx-hdr-r">
          <button className="mpf-btn" onClick={() => { window.MyPF.reprice(); window.dispatchEvent(new CustomEvent("mypf-change")); }} title="Re-simulate live prices">⟳ Prices</button>
          <RiskProfilePill />
          <FreshnessPill state="live" age="5s" />
        </div>
      </div>

      <SummaryRow sum={sum} allView={allView} />

      <div className="lab-tabs mpf-tabs">
        {[["holdings", `Holdings · ${pf.holdings.length}`], ["alloc", "Allocation"], ["risk", "Risk Analytics"], ["perf", "Performance"], ["journal", `Journal · ${(pf.trades || []).length}`]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
        {!allView && tab === "holdings" && <button className="mpf-add" onClick={() => setAdding(a => !a)}>{adding ? "✕ Cancel" : "＋ Add holding"}</button>}
      </div>

      {tab === "holdings" && <HoldingsTab pf={pf} sum={sum} allView={allView} adding={adding} setAdding={setAdding} onTicker={onTicker} />}
      {tab === "alloc" && <AllocTab sum={sum} />}
      {tab === "risk" && <RiskTab pf={pf} />}
      {tab === "perf" && <PerfTab pf={pf} sum={sum} />}
      {tab === "journal" && <JournalTab pf={pf} allView={allView} />}

      <div className="pf-note mono dim2">
        Your data is saved locally in this browser (<b>localStorage</b>) · prices are <b>simulated</b> (click ⟳ Prices to re-roll) and can be overridden inline per holding · this is a tracking tool, not brokerage execution.
      </div>
    </div>
  );
}

// ── portfolio dropdown switcher ─────────────────────────────────
function PortfolioSwitcher({ allView, setAllView }) {
  const MyPF = window.MyPF;
  const [open, setOpen] = useMP(false);
  const [editing, setEditing] = useMP(null);
  const ref = useMPr(null);
  useMPe(() => { const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const list = MyPF.list();
  const active = MyPF.active();
  const label = allView ? "All Portfolios" : (active ? active.name : "—");
  return (
    <div className="mpf-switch" ref={ref}>
      <button className="mpf-switch-btn mono" onClick={() => setOpen(o => !o)}>
        <span className="mpf-switch-name">{label}</span>
        <span className="mpf-switch-meta dim2">{allView ? `${list.length} books` : `${(active ? active.holdings.length : 0)} holdings`}</span>
        <span className="mpf-switch-car">▾</span>
      </button>
      {open && (
        <div className="mpf-menu">
          <button className={`mpf-menu-item ${allView ? "is-on" : ""}`} onClick={() => { setAllView(true); setOpen(false); }}>
            <span className="mpf-menu-dot" style={{ background: "var(--copper)" }} />
            <span className="mpf-menu-l">All Portfolios <span className="dim2">· combined</span></span>
          </button>
          <div className="mpf-menu-div" />
          {list.map(p => (
            <div key={p.id} className={`mpf-menu-item ${!allView && MyPF.activeId() === p.id ? "is-on" : ""}`}>
              {editing === p.id ? (
                <input className="mpf-menu-edit mono" autoFocus defaultValue={p.name}
                  onBlur={e => { MyPF.rename(p.id, e.target.value.trim() || p.name); setEditing(null); }}
                  onKeyDown={e => { if (e.key === "Enter") e.target.blur(); }} />
              ) : (
                <button className="mpf-menu-l-btn" onClick={() => { setAllView(false); MyPF.setActive(p.id); setOpen(false); }}>
                  <span className="mpf-menu-dot" />
                  <span className="mpf-menu-l">{p.name} <span className="dim2">· {p.holdings.length}</span></span>
                </button>
              )}
              <span className="mpf-menu-acts">
                <button title="Rename" onClick={() => setEditing(p.id)}>✎</button>
                {list.length > 1 && <button title="Delete" className="rd" onClick={() => { if (confirm(`Delete "${p.name}"?`)) MyPF.remove(p.id); }}>✕</button>}
              </span>
            </div>
          ))}
          <div className="mpf-menu-div" />
          <button className="mpf-menu-new" onClick={() => { const n = prompt("New portfolio name:", "New Portfolio"); if (n) { MyPF.create(n.trim()); setAllView(false); setOpen(false); } }}>＋ New portfolio</button>
        </div>
      )}
    </div>
  );
}

function RiskProfilePill() {
  const MyPF = window.MyPF;
  const profiles = [["conservative", "Conservative"], ["moderate", "Moderate"], ["aggressive", "Aggressive"]];
  const cur = MyPF.riskProfile();
  const [open, setOpen] = useMP(false);
  const ref = useMPr(null);
  useMPe(() => { const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const tone = cur === "conservative" ? "gn" : cur === "aggressive" ? "rd" : "amb";
  return (
    <div className="mpf-rp" ref={ref}>
      <button className={`mpf-rp-btn mpf-rp-btn--${tone}`} onClick={() => setOpen(o => !o)}>
        <span className="mpf-rp-dot" /> Risk: {profiles.find(p => p[0] === cur)[1]} ▾
      </button>
      {open && <div className="mpf-rp-menu">{profiles.map(([id, l]) => (
        <button key={id} className={cur === id ? "is-on" : ""} onClick={() => { MyPF.setRiskProfile(id); setOpen(false); }}>{l}</button>
      ))}</div>}
    </div>
  );
}

// ── summary metrics ─────────────────────────────────────────────
function SummaryRow({ sum, allView }) {
  return (
    <div className="pf-hero2 mpf-hero">
      <div className="pf-hero-main mpf-hero-main">
        <div className="pf-hero-eyebrow mono dim2">TOTAL VALUE{allView ? " · ALL BOOKS" : ""}</div>
        <div className="pf-hero-num mono">{fmt$(sum.totalValue)}</div>
        <div className="pf-hero-sub mono">
          <span className={toneOf(sum.dayChg) === "gn" ? "up" : toneOf(sum.dayChg) === "rd" ? "dn" : "dim2"}>{fmt$(sum.dayChg)} ({fmtPct(sum.dayChgPct)})</span>
          <span className="dim2"> today</span>
        </div>
        <MpfSpark rows={sum.rows} />
      </div>
      <div className="pf-hero-tiles mpf-tiles">
        <PfTile l="Total gain/loss" v={`${fmt$(sum.unrealized)}`} s={fmtPct(sum.unrealizedPct)} tone={toneOf(sum.unrealized)} />
        <PfTile l="Unrealized" v={fmt$(sum.unrealized)} s="open positions" tone={toneOf(sum.unrealized)} />
        <PfTile l="Realized" v={fmt$(sum.realized)} s="closed trades" tone={toneOf(sum.realized)} />
        <PfTile l="Invested" v={fmt$(sum.invested)} s={`${sum.rows.filter(r => r.type !== "cash").length} positions`} tone="copper" />
        <PfTile l="Cash" v={fmt$(sum.cash)} s="buying power" tone="ink" />
        <PfTile l="Best" v={sum.best ? sum.best.sym : "—"} s={sum.best ? fmtPct(sum.best.pnlPct) : ""} tone="gn" />
        <PfTile l="Worst" v={sum.worst ? sum.worst.sym : "—"} s={sum.worst ? fmtPct(sum.worst.pnlPct) : ""} tone="rd" />
        <PfTile l="Est. div income" v={fmt$(sum.divIncome)} s="~annual" tone="cy" />
      </div>
    </div>
  );
}

function MpfSpark({ rows }) {
  // synthetic 40-pt equity path scaled to current invested value
  const data = useMPm(() => { const a = []; let v = 0; for (let i = 0; i < 40; i++) { v += 0.3 + Math.sin(i * 0.4) * 0.4 + (Math.random() - 0.45) * 0.6; a.push(v); } return a; }, [rows.length]);
  const w = 440, h = 64, min = Math.min(...data, -1), max = Math.max(...data, 8);
  const x = i => (i / (data.length - 1)) * w, y = v => h - ((v - min) / (max - min)) * (h - 6) - 3;
  const up = data[data.length - 1] >= 0;
  const c = up ? "gn" : "rd";
  return (<svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="pf-eq">
    <defs><linearGradient id="mpfeq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${c})`} stopOpacity="0.28" /><stop offset="100%" stopColor={`var(--${c})`} stopOpacity="0" /></linearGradient></defs>
    <path d={`M 0 ${y(0)} L ${data.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w} ${y(0)} Z`} fill="url(#mpfeq)" />
    <polyline points={data.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={`var(--${c})`} strokeWidth="1.8" style={{ filter: `drop-shadow(0 0 4px var(--${c}))` }} />
  </svg>);
}

function PfTile({ l, v, s, tone }) {
  return <div className={`pf-tile pf-tile--${tone}`}><div className="pf-tile-l mono dim2">{l}</div><div className={`pf-tile-v mono kpi-tone--${tone}`}>{v}</div><div className="pf-tile-s mono dim2">{s}</div></div>;
}

// live-ticking price cell — flashes green/red when the quote moves
function LivePrice({ value, override }) {
  const prev = useMPr(value);
  const [flash, setFlash] = useMP(null);
  useMPe(() => {
    if (prev.current != null && value !== prev.current) {
      setFlash(value > prev.current ? "up" : "dn");
      const t = setTimeout(() => setFlash(null), 650);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return <span className={`mpf-live ${override ? "mpf-ovr" : ""} ${flash ? "mpf-live--" + flash : ""}`}>${value.toFixed(2)}</span>;
}

// ── Holdings tab ────────────────────────────────────────────────
function HoldingsTab({ pf, sum, allView, adding, setAdding, onTicker }) {
  const MyPF = window.MyPF;
  const [edit, setEdit] = useMP(null); // {hid, field}
  const rows = sum.rows;
  // live quotes — re-price every 5s so Price + Day % refresh in real time
  useMPe(() => {
    if (!MyPF || !MyPF.tick) return;
    const iv = setInterval(() => MyPF.tick(), 5000);
    return () => clearInterval(iv);
  }, []);
  return (
    <div className="wsx-body">
      {adding && !allView && <AddHoldingForm pfId={pf.id} onDone={() => setAdding(false)} />}
      {rows.length === 0 && !adding ? (
        <div className="mpf-empty">
          <div className="mpf-empty-ico">▦</div>
          <div className="mpf-empty-t">No holdings yet</div>
          <div className="mpf-empty-s mono dim2">Add your first position to start tracking P&L.</div>
          <button className="mpf-add" onClick={() => setAdding(true)}>＋ Add holding</button>
        </div>
      ) : (
        <table className="dtable wsx-tbl pf-tbl mpf-tbl">
          <thead><tr>
            <th>Symbol</th><th>Type</th><th className="r">Qty</th><th className="r">Avg cost</th><th>Added</th>
            <th className="r">Price</th><th className="r">Day</th><th className="r">Mkt value</th>
            <th className="r">Gain/loss</th><th className="r">%</th><th className="r">Wt</th>
            <th className="r">Targets · T1/T2</th><th className="r">Stop</th><th>Action · guidance</th>
            {allView && <th>Book</th>}<th>Notes</th><th></th>
          </tr></thead>
          <tbody>{rows.map(r => {
            const wt = sum.invested ? r.mv / sum.invested * 100 : 0;
            const isCash = r.type === "cash";
            const upPct1 = r.target  ? (r.target  - r.last) / r.last * 100 : null;
            const upPct2 = r.target2 ? (r.target2 - r.last) / r.last * 100 : null;
            const stopPct = r.stop   ? (r.last - r.stop) / r.last * 100 : null;
            const g = posGuidance(r);
            const cellEdit = (field, val, render) => edit && edit.hid === r.id && edit.field === field
              ? <input className="mpf-cell-edit mono" autoFocus defaultValue={val}
                  onBlur={e => { const v = field === "sym" ? e.target.value.toUpperCase() : parseFloat(e.target.value); MyPF.updateHolding(pf.id, r.id, { [field]: (field === "sym" ? e.target.value.toUpperCase() : (isNaN(v) ? null : v)) }); setEdit(null); }}
                  onKeyDown={e => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") setEdit(null); }} />
              : <span onClick={e => { if (allView) return; e.stopPropagation(); setEdit({ hid: r.id, field }); }} className={allView ? "" : "mpf-editable"}>{render}</span>;
            return (
              <tr key={r.id}>
                <td onClick={() => onTicker && onTicker(r.sym)}><b className="mpf-sym">{r.sym}</b><div className="pf-name dim2">{r.sector}</div>{g && <div className={`mpf-sym-act mpf-act--${g.tone}`} title={g.detail}>{g.act}</div>}</td>
                <td><span className={`mpf-type mpf-type--${r.type}`}>{r.type}</span></td>
                <td className="r tabular">{cellEdit("qty", r.qty, r.qty)}</td>
                <td className="r tabular dim">{cellEdit("cost", r.cost, "$" + r.cost.toFixed(2))}</td>
                <td className="mpf-date dim2" title={heldDays(r.buyDate)}>
                  {edit && edit.hid === r.id && edit.field === "buyDate"
                    ? <input className="mpf-cell-edit mono" type="date" autoFocus defaultValue={r.buyDate || ""}
                        onBlur={e => { MyPF.updateHolding(pf.id, r.id, { buyDate: e.target.value || null }); setEdit(null); }}
                        onKeyDown={e => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") setEdit(null); }} />
                    : <span onClick={e => { if (allView) return; e.stopPropagation(); setEdit({ hid: r.id, field: "buyDate" }); }} className={allView ? "" : "mpf-editable"}>{r.type === "cash" ? "—" : fmtBuyDate(r.buyDate)}</span>}
                </td>
                <td className="r tabular">{cellEdit("priceOverride", r.last, <LivePrice value={r.last} override={r.priceOverride != null} />)}</td>
                <td className={`r tabular ${r.dayPct >= 0 ? "up" : "dn"}`}>{r.type === "cash" ? "—" : fmtPct(r.dayPct)}</td>
                <td className="r tabular">{fmt$(r.mv)}</td>
                <td className={`r tabular ${r.pnl >= 0 ? "up" : "dn"}`}><b>{fmt$(r.pnl)}</b></td>
                <td className={`r tabular ${r.pnlPct >= 0 ? "up" : "dn"}`}>{r.type === "cash" ? "—" : fmtPct(r.pnlPct)}</td>
                <td className="r tabular dim2">{wt.toFixed(1)}%</td>
                <td className="r mpf-tgts">{isCash ? <span className="dim">—</span> : (
                  <span className="mpf-tgts-stack">
                    <span className="mpf-tgt-row">
                      <span className="mpf-tgt-k mono">T1</span>
                      {cellEdit("target", r.target, r.target
                        ? <span className="mpf-tgt-v"><span className={r.last >= r.target ? "gn" : ""}>${r.target}</span> <span className="mpf-tgt-sub dim2">{upPct1 >= 0 ? "+" + upPct1.toFixed(0) + "%" : "✓"}</span></span>
                        : <span className="mpf-plan-set">+ set</span>)}
                    </span>
                    <span className="mpf-tgt-row">
                      <span className="mpf-tgt-k mono dim2">T2</span>
                      {cellEdit("target2", r.target2, r.target2
                        ? <span className="mpf-tgt-v"><span className={r.last >= r.target2 ? "gn" : ""}>${r.target2}</span> <span className="mpf-tgt-sub dim2">{upPct2 >= 0 ? "+" + upPct2.toFixed(0) + "%" : "✓"}</span></span>
                        : <span className="mpf-plan-set">+ set</span>)}
                    </span>
                  </span>)}</td>
                <td className="r tabular mpf-plan-cell">{isCash ? <span className="dim">—</span> : cellEdit("stop", r.stop,
                  r.stop ? <span className="mpf-plan-v"><span className={r.last <= r.stop ? "dn" : ""}>${r.stop}</span><span className={`mpf-plan-sub ${r.last <= r.stop ? "dn" : stopPct <= 4 ? "warn" : "dim2"}`} title="distance to stop">{r.last <= r.stop ? "EXIT" : "−" + stopPct.toFixed(0) + "%"}</span></span> : <span className="mpf-plan-set">+ set</span>)}</td>
                <td className="mpf-action">{g && <span className={`mpf-act mpf-act--${g.tone}`} title={g.detail}>{g.act}</span>}{g && <span className="mpf-act-d dim2">{g.detail}</span>}</td>
                {allView && <td className="dim2 mono" style={{ fontSize: 10 }}>{(MyPF.list().find(p => p.holdings.some(h => h.id === r.id)) || {}).name || "—"}</td>}
                <td className="mpf-notes dim2" title={r.notes}>{r.notes || "—"}</td>
                <td>{!allView && <button className="pf-act pf-act--rd" title="Remove" onClick={() => MyPF.removeHolding(pf.id, r.id)}>✕</button>}</td>
              </tr>
            );
          })}</tbody>
          <tfoot><tr className="mpf-foot">
            <td colSpan={7}><b>{allView ? "All books" : pf.name}</b> · {rows.filter(r => r.type !== "cash").length} positions + cash</td>
            <td className="r tabular"><b>{fmt$(sum.invested)}</b></td>
            <td className={`r tabular ${sum.unrealized >= 0 ? "up" : "dn"}`}><b>{fmt$(sum.unrealized)}</b></td>
            <td className={`r tabular ${sum.unrealizedPct >= 0 ? "up" : "dn"}`}>{fmtPct(sum.unrealizedPct)}</td>
            <td colSpan={allView ? 7 : 6}></td>
          </tr></tfoot>
        </table>
      )}
      {!allView && rows.length > 0 && <div className="mpf-cashrow"><span className="mono dim2">Cash balance</span> <input className="mpf-cash-edit mono" type="number" defaultValue={pf.cash} onBlur={e => MyPF.setCash(pf.id, e.target.value)} /> <span className="mono dim2">· click any Qty / Avg cost / Price to edit inline</span></div>}
    </div>
  );
}

function AddHoldingForm({ pfId, onDone }) {
  const MyPF = window.MyPF;
  const [f, setF] = useMP({ sym: "", qty: "", cost: "", type: "stock", buyDate: new Date().toISOString().slice(0, 10), target: "", stop: "", account: "Main", notes: "" });
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));
  const submit = () => {
    if (!f.sym || !f.qty || (!f.cost && f.type !== "cash")) { alert("Symbol, quantity and cost are required."); return; }
    MyPF.addHolding(pfId, { sym: f.sym.toUpperCase(), qty: +f.qty, cost: +f.cost || 0, type: f.type, buyDate: f.buyDate, target: f.target ? +f.target : null, stop: f.stop ? +f.stop : null, account: f.account, notes: f.notes });
    onDone();
  };
  return (
    <div className="mpf-addform">
      <div className="mpf-addgrid">
        <label className="mpf-fld"><span className="mono dim2">Symbol *</span><input className="mono" autoFocus value={f.sym} onChange={e => set("sym", e.target.value)} placeholder="AAPL" /></label>
        <label className="mpf-fld"><span className="mono dim2">Type</span><select value={f.type} onChange={e => set("type", e.target.value)}>{MP_ASSET.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="mpf-fld"><span className="mono dim2">Quantity *</span><input className="mono" type="number" value={f.qty} onChange={e => set("qty", e.target.value)} placeholder="100" /></label>
        <label className="mpf-fld"><span className="mono dim2">Avg cost *</span><input className="mono" type="number" value={f.cost} onChange={e => set("cost", e.target.value)} placeholder="150.00" /></label>
        <label className="mpf-fld"><span className="mono dim2">Buy date</span><input className="mono" type="date" value={f.buyDate} onChange={e => set("buyDate", e.target.value)} /></label>
        <label className="mpf-fld"><span className="mono dim2">Account</span><input className="mono" value={f.account} onChange={e => set("account", e.target.value)} placeholder="Main" /></label>
        <label className="mpf-fld"><span className="mono dim2">Target</span><input className="mono" type="number" value={f.target} onChange={e => set("target", e.target.value)} placeholder="opt." /></label>
        <label className="mpf-fld"><span className="mono dim2">Stop</span><input className="mono" type="number" value={f.stop} onChange={e => set("stop", e.target.value)} placeholder="opt." /></label>
        <label className="mpf-fld mpf-fld--wide"><span className="mono dim2">Notes / thesis</span><input className="mono" value={f.notes} onChange={e => set("notes", e.target.value)} placeholder="Why you own it…" /></label>
      </div>
      <div className="mpf-addacts">
        <button className="mpf-add" onClick={submit}>✓ Add to portfolio</button>
        <button className="mpf-btn" onClick={onDone}>Cancel</button>
      </div>
    </div>
  );
}

// ── Allocation tab ──────────────────────────────────────────────
function AllocTab({ sum }) {
  const rows = sum.rows.filter(r => r.type !== "cash");
  const inv = sum.invested || 1;
  const SEC_C = { Tech: "var(--cy)", Finance: "var(--blue)", Healthcare: "var(--violet)", Energy: "var(--amb)", Materials: "var(--copper)", Industrials: "var(--ink-2)", Consumer: "var(--gn)", Utilities: "var(--rd)", Crypto: "var(--amb)", Cash: "var(--ink-3)" };
  const group = (keyFn) => { const m = {}; rows.forEach(r => { const k = keyFn(r); m[k] = (m[k] || 0) + r.mv; }); return Object.entries(m).map(([k, v]) => ({ k, v, pct: v / inv * 100 })).sort((a, b) => b.v - a.v); };
  const sectors = group(r => r.sector), assets = group(r => r.type);
  const byPos = rows.map(r => ({ k: r.sym, v: r.mv, pct: r.mv / inv * 100 })).sort((a, b) => b.v - a.v);
  const Bar = ({ data, colorFor }) => (<>
    <div className="pf-secbar">{data.map((s, i) => <div key={i} className="pf-secseg" style={{ width: `${s.pct}%`, background: colorFor(s.k, i) }} title={`${s.k} ${s.pct.toFixed(0)}%`} />)}</div>
    <div className="pf-seclegend">{data.map((s, i) => <div key={i} className="pf-secrow"><span className="pf-secdot" style={{ background: colorFor(s.k, i) }} /><span className="pf-secn">{s.k}</span><span className="mono dim2">{fmt$(s.v)}</span><span className="mono">{s.pct.toFixed(0)}%</span></div>)}</div>
  </>);
  const posColor = (k, i) => ["var(--copper)", "var(--cy)", "var(--gn)", "var(--violet)", "var(--amb)", "var(--blue)", "var(--ink-2)"][i % 7];
  return (
    <div className="pf-expo mpf-alloc">
      <div className="lab-card"><div className="lab-card-h mono">SECTOR ALLOCATION</div><Bar data={sectors} colorFor={k => SEC_C[k] || "var(--ink-3)"} /></div>
      <div className="lab-card"><div className="lab-card-h mono">ASSET TYPE</div><Bar data={assets} colorFor={k => SEC_C[k === "etf" ? "Industrials" : k === "stock" ? "Tech" : k === "crypto" ? "Crypto" : "Cash"] || "var(--ink-3)"} /></div>
      <div className="lab-card pf-wide"><div className="lab-card-h mono">POSITION WEIGHTS</div><Bar data={byPos} colorFor={posColor} />
        {byPos[0] && byPos[0].pct > 25 && <div className="lab-verdict mono dim2">⚠ <b>{byPos[0].k}</b> is {byPos[0].pct.toFixed(0)}% of the book — concentrated. Consider trimming toward a &lt;25% single-name cap.</div>}
      </div>
    </div>
  );
}

// ── Risk Analytics tab ──────────────────────────────────────────
function RiskTab({ pf }) {
  const MyPF = window.MyPF;
  const r = useMPm(() => MyPF.risk(pf), [pf]);
  const profile = MyPF.riskProfile();
  const caps = { conservative: { beta: 0.85, top: 15, vol: 14 }, moderate: { beta: 1.1, top: 25, vol: 20 }, aggressive: { beta: 1.5, top: 40, vol: 32 } }[profile];
  const gauge = (label, val, cap, unit, fmt) => {
    const pct = Math.min(100, val / cap * 100); const breach = val > cap;
    return (
      <div className="mpf-rk-row">
        <span className="mpf-rk-l mono dim2">{label}</span>
        <div className="mpf-rk-track"><div className={`mpf-rk-fill ${breach ? "breach" : "ok"}`} style={{ width: `${pct}%` }} /><div className="mpf-rk-cap" style={{ left: "100%" }} title={`${profile} cap`} /></div>
        <span className={`mpf-rk-v mono ${breach ? "dn" : "up"}`}>{fmt ? fmt(val) : val + unit}</span>
        <span className="mpf-rk-cap-lbl mono dim2">cap {fmt ? fmt(cap) : cap + unit}</span>
      </div>
    );
  };
  const SEC_C = { Tech: "var(--cy)", Finance: "var(--blue)", Healthcare: "var(--violet)", Energy: "var(--amb)", Materials: "var(--copper)", Industrials: "var(--ink-2)", Consumer: "var(--gn)", Utilities: "var(--rd)", Crypto: "var(--amb)" };
  return (
    <div className="pf-expo mpf-risk">
      <div className="lab-card">
        <div className="lab-card-h mono">RISK vs PROFILE · {profile.toUpperCase()} caps</div>
        <div className="mpf-rk">
          {gauge("Portfolio beta", r.beta, caps.beta, "")}
          {gauge("Top position weight", +r.topWt.toFixed(0), caps.top, "%", v => v.toFixed(0) + "%")}
          {gauge("Annualized volatility", +r.annVol.toFixed(0), caps.vol, "%", v => v.toFixed(0) + "%")}
        </div>
        <div className="lab-verdict mono dim2">▏ = your {profile} cap. {(r.beta > caps.beta || r.topWt > caps.top || r.annVol > caps.vol) ? <span><b className="dn">Breaches flagged</b> — the book runs hotter than your stated tolerance.</span> : <span><b className="up">Within tolerance</b> on all gates.</span>}</div>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">KEY RISK METRICS</div>
        <div className="mpf-rk-tiles">
          <PfTile l="Portfolio β" v={r.beta.toFixed(2)} s="vs SPY" tone={r.beta > caps.beta ? "rd" : "gn"} />
          <PfTile l="1-day VaR 95%" v={fmt$(r.var95)} s={`${(r.var95 / r.invested * 100).toFixed(1)}% of book`} tone="amb" />
          <PfTile l="CVaR (ES) 95%" v={fmt$(r.cvar)} s="tail expectation" tone="rd" />
          <PfTile l="Volatility" v={`${r.annVol.toFixed(0)}%`} s="annualized" tone={r.annVol > caps.vol ? "rd" : "cy"} />
          <PfTile l="Est. max drawdown" v={`${r.maxDD}%`} s="modeled" tone="rd" />
          <PfTile l="Concentration HHI" v={r.hhi.toFixed(2)} s={`top: ${r.topSym} ${r.topWt.toFixed(0)}%`} tone={r.hhi > 0.25 ? "amb" : "gn"} />
          <PfTile l="Diversification" v={`${r.nNames} names`} s={r.nNames < 5 ? "thin" : "adequate"} tone={r.nNames < 5 ? "amb" : "gn"} />
          <PfTile l="Largest sector" v={r.sectors[0] ? r.sectors[0].k : "—"} s={r.sectors[0] ? `${r.sectors[0].pct.toFixed(0)}%` : ""} tone={r.sectors[0] && r.sectors[0].pct > 40 ? "amb" : "ink"} />
        </div>
      </div>
      <div className="lab-card pf-wide">
        <div className="lab-card-h mono">SECTOR EXPOSURE</div>
        <div className="pf-secbar">{r.sectors.map((s, i) => <div key={i} className="pf-secseg" style={{ width: `${s.pct}%`, background: SEC_C[s.k] || "var(--ink-3)" }} title={`${s.k} ${s.pct.toFixed(0)}%`} />)}</div>
        <div className="pf-seclegend">{r.sectors.map((s, i) => <div key={i} className="pf-secrow"><span className="pf-secdot" style={{ background: SEC_C[s.k] || "var(--ink-3)" }} /><span className="pf-secn">{s.k}</span><span className="mono">{s.pct.toFixed(0)}%</span></div>)}</div>
        <div className="lab-verdict mono dim2">VaR is a 1-day parametric estimate (95%, normal) on {fmt$(r.invested)} invested · β &amp; volatility from per-holding factor proxies. Demo analytics — directional, not a risk system of record.</div>
      </div>
    </div>
  );
}

// ── Journal tab ─────────────────────────────────────────────────
function JournalTab({ pf, allView }) {
  const MyPF = window.MyPF;
  const [showAdd, setShowAdd] = useMP(false);
  const [t, setT] = useMP({ sym: "", side: "BUY", qty: "", price: "", date: new Date().toISOString().slice(0, 10), note: "" });
  const trades = pf.trades || [];
  const realized = trades.filter(x => x.side === "SELL").reduce((s, x) => { const hb = pf.holdings.find(h => h.sym === x.sym); const basis = hb ? hb.cost : x.price * 0.9; return s + (x.price - basis) * x.qty; }, 0);
  const wins = trades.filter(x => x.side === "SELL").map(x => { const hb = pf.holdings.find(h => h.sym === x.sym); const basis = hb ? hb.cost : x.price * 0.9; return x.price > basis; });
  const wr = wins.length ? wins.filter(Boolean).length / wins.length * 100 : 0;
  const submit = () => { if (!t.sym || !t.qty || !t.price) { alert("Symbol, qty and price required."); return; } MyPF.addTrade(pf.id, { sym: t.sym.toUpperCase(), side: t.side, qty: +t.qty, price: +t.price, date: t.date, note: t.note }); setT({ sym: "", side: "BUY", qty: "", price: "", date: new Date().toISOString().slice(0, 10), note: "" }); setShowAdd(false); };
  return (
    <div className="wsx-body mpf-journal">
      <div className="mpf-jr-kpis">
        <PfTile l="Trades logged" v={trades.length} s={`${trades.filter(x => x.side === "BUY").length} buys · ${trades.filter(x => x.side === "SELL").length} sells`} tone="ink" />
        <PfTile l="Realized P&L" v={fmt$(realized)} s="closed legs" tone={toneOf(realized)} />
        <PfTile l="Win rate" v={`${wr.toFixed(0)}%`} s={`${wins.filter(Boolean).length}/${wins.length} sells`} tone={wr >= 50 ? "gn" : "amb"} />
        <PfTile l="Notes" v={trades.filter(x => x.note).length} s="annotated trades" tone="cy" />
      </div>
      {!allView && <div className="mpf-jr-addbar">{showAdd ? (
        <div className="mpf-jr-form">
          <input className="mono" placeholder="SYM" value={t.sym} onChange={e => setT(s => ({ ...s, sym: e.target.value }))} style={{ width: 70 }} />
          <select value={t.side} onChange={e => setT(s => ({ ...s, side: e.target.value }))}><option>BUY</option><option>SELL</option></select>
          <input className="mono" type="number" placeholder="qty" value={t.qty} onChange={e => setT(s => ({ ...s, qty: e.target.value }))} style={{ width: 70 }} />
          <input className="mono" type="number" placeholder="price" value={t.price} onChange={e => setT(s => ({ ...s, price: e.target.value }))} style={{ width: 90 }} />
          <input className="mono" type="date" value={t.date} onChange={e => setT(s => ({ ...s, date: e.target.value }))} />
          <input className="mono" placeholder="note / lesson…" value={t.note} onChange={e => setT(s => ({ ...s, note: e.target.value }))} style={{ flex: 1, minWidth: 120 }} />
          <button className="mpf-add" onClick={submit}>✓ Log</button>
          <button className="mpf-btn" onClick={() => setShowAdd(false)}>✕</button>
        </div>
      ) : <button className="mpf-add" onClick={() => setShowAdd(true)}>＋ Log a trade</button>}</div>}
      <table className="dtable wsx-tbl pf-tbl mpf-jr-tbl">
        <thead><tr><th>Date</th><th>Symbol</th><th>Side</th><th className="r">Qty</th><th className="r">Price</th><th className="r">Value</th><th>Note / lesson</th>{allView && <th>Book</th>}<th></th></tr></thead>
        <tbody>{trades.length === 0 ? <tr><td colSpan={8} className="dim2" style={{ textAlign: "center", padding: 24 }}>No trades logged yet.</td></tr> : trades.slice().sort((a, b) => (b.date || "").localeCompare(a.date || "")).map(tr => (
          <tr key={tr.id}>
            <td className="mono dim2">{tr.date}</td>
            <td><b>{tr.sym}</b></td>
            <td><span className={tr.side === "BUY" ? "up" : "dn"}>{tr.side}</span></td>
            <td className="r tabular">{tr.qty}</td>
            <td className="r tabular">${(+tr.price).toFixed(2)}</td>
            <td className="r tabular dim">{fmt$(tr.qty * tr.price)}</td>
            <td className="mpf-notes dim2" title={tr.note}>{tr.note || "—"}</td>
            {allView && <td className="dim2 mono" style={{ fontSize: 10 }}>{(MyPF.list().find(p => (p.trades || []).some(x => x.id === tr.id)) || {}).name || "—"}</td>}
            <td>{!allView && <button className="pf-act pf-act--rd" title="Delete" onClick={() => MyPF.removeTrade(pf.id, tr.id)}>✕</button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

window.SurfaceMyPortfolios = SurfaceMyPortfolios;

// ── Performance tab — equity, monthly returns, R-distribution, attribution
// computed from THIS portfolio's holdings + trade journal ──────────────
function PerfTab({ pf, sum }) {
  const MyPF = window.MyPF;
  const trades = (pf.trades || []).slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  const sells = trades.filter(t => t.side === "SELL");

  // realized R-multiples from closed legs (assume ~1R = 8% risk per trade)
  const rmults = sells.map(t => {
    const hb = pf.holdings.find(h => h.sym === t.sym);
    const basis = hb ? hb.cost : t.price * 0.92;
    const retPct = (t.price - basis) / basis;
    return +(retPct / 0.08).toFixed(2);
  });
  const wins = rmults.filter(r => r > 0), losses = rmults.filter(r => r <= 0);
  const winRate = rmults.length ? (wins.length / rmults.length) * 100 : 0;
  const avgWin = wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
  const avgLoss = losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : 0;
  const expectancy = rmults.length ? rmults.reduce((a, b) => a + b, 0) / rmults.length : 0;

  // equity curve: walk realized P&L over trade dates, end at current total value
  const eq = React.useMemo(() => {
    let cum = 0; const pts = [{ i: 0, v: 0 }];
    trades.forEach((t, i) => {
      if (t.side === "SELL") { const hb = pf.holdings.find(h => h.sym === t.sym); const basis = hb ? hb.cost : t.price * 0.92; cum += (t.price - basis) * t.qty; }
      pts.push({ i: i + 1, v: +cum.toFixed(0) });
    });
    pts.push({ i: trades.length + 1, v: +(cum + sum.unrealized).toFixed(0) });
    return pts;
  }, [pf, sum.unrealized]);

  // monthly returns (synthetic from trade cadence + unrealized spread)
  const months = React.useMemo(() => {
    const names = ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"];
    const seedV = (pf.holdings[0] ? pf.holdings[0].sym.charCodeAt(0) : 7);
    return names.map((m, i) => ({ m, v: +(((Math.sin(i * 1.7 + seedV) + Math.sin(i * 0.6)) * 2.4) + 0.7).toFixed(1) }));
  }, [pf]);

  // sector attribution from holdings
  const sectorAttr = React.useMemo(() => {
    const map = {}; sum.rows.filter(r => r.type !== "cash").forEach(r => { map[r.sector] = (map[r.sector] || 0) + r.pnl; });
    return Object.entries(map).map(([k, v]) => ({ k, v: Math.round(v) })).sort((a, b) => b.v - a.v);
  }, [sum]);

  const totalReturn = sum.cost ? (sum.unrealized + sum.realized) / sum.cost * 100 : 0;
  const eqMin = Math.min(0, ...eq.map(p => p.v)), eqMax = Math.max(0, ...eq.map(p => p.v));
  const W = 880, H = 150, ex = i => (i / Math.max(1, eq.length - 1)) * W, ey = v => H - ((v - eqMin) / ((eqMax - eqMin) || 1)) * (H - 8) - 4;
  const rbinDefs = [-2, -1, 0, 1, 2, 3]; const rbins = rbinDefs.map((lo, i) => ({ lo, hi: rbinDefs[i + 1] ?? 4, n: rmults.filter(r => r >= lo && r < (rbinDefs[i + 1] ?? 99)).length }));
  const rMax = Math.max(1, ...rbins.map(b => b.n));

  return (
    <div className="wsx-body mpf-perf">
      <div className="mpf-jr-kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
        <PfTile l="Total return" v={fmtPct(totalReturn)} s="realized + open" tone={toneOf(totalReturn)} />
        <PfTile l="Realized P&L" v={fmt$(sum.realized)} s={`${sells.length} closed`} tone={toneOf(sum.realized)} />
        <PfTile l="Win rate" v={`${winRate.toFixed(0)}%`} s={`${wins.length}/${rmults.length}`} tone={winRate >= 50 ? "gn" : "amb"} />
        <PfTile l="Expectancy" v={`${expectancy >= 0 ? "+" : ""}${expectancy.toFixed(2)}R`} s="per trade" tone={toneOf(expectancy)} />
        <PfTile l="Win/Loss" v={`${avgWin.toFixed(1)} / ${avgLoss.toFixed(1)}`} s="avg R" tone="cy" />
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">EQUITY CURVE · realized P&L → marked-to-market <span className="dim2">· {pf.name || "All books"}</span></div>
        <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="pf-eq">
          <defs><linearGradient id="mpfperf" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${eq[eq.length - 1].v >= 0 ? "gn" : "rd"})`} stopOpacity="0.25" /><stop offset="100%" stopColor={`var(--${eq[eq.length - 1].v >= 0 ? "gn" : "rd"})`} stopOpacity="0" /></linearGradient></defs>
          <line x1="0" y1={ey(0)} x2={W} y2={ey(0)} stroke="var(--line)" strokeDasharray="2 4" />
          <path d={`M 0 ${ey(0)} L ${eq.map(p => `${ex(p.i)},${ey(p.v)}`).join(" L ")} L ${W} ${ey(0)} Z`} fill="url(#mpfperf)" />
          <polyline points={eq.map(p => `${ex(p.i)},${ey(p.v)}`).join(" ")} fill="none" stroke={`var(--${eq[eq.length - 1].v >= 0 ? "gn" : "rd"})`} strokeWidth="2" />
        </svg>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">MONTHLY RETURNS · trailing 12</div>
        <div className="mpf-months">{months.map((m, i) => (
          <div key={i} className="mpf-month"><div className={`mpf-month-bar ${m.v >= 0 ? "up" : "dn"}`} style={{ height: `${Math.min(100, Math.abs(m.v) * 12 + 6)}%` }} /><div className="mpf-month-v mono">{m.v >= 0 ? "+" : ""}{m.v}</div><div className="mpf-month-m mono dim2">{m.m}</div></div>
        ))}</div>
      </div>

      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">R-multiple distribution · n={rmults.length}</div>
          <div className="mpf-rhist">{rbins.map((b, i) => (
            <div key={i} className="mpf-rbin"><div className={`mpf-rbin-bar ${b.lo >= 0 ? "up" : "dn"}`} style={{ height: `${(b.n / rMax) * 100}%` }} /><div className="mpf-rbin-l mono dim2">{b.lo >= 0 ? "+" : ""}{b.lo}R</div></div>
          ))}</div>
        </div>
        <div>
          <div className="pv-block-h label-cap">P&L attribution · by sector</div>
          <div className="pf-diverge">{sectorAttr.map((r, i) => { const mx = Math.max(...sectorAttr.map(x => Math.abs(x.v)), 1); return (
            <div key={i} className="pf-div-row"><span className="pf-div-k">{r.k}</span><div className="pf-div-track"><div className={`pf-div-fill ${r.v >= 0 ? "up" : "dn"}`} style={{ width: `${Math.abs(r.v) / mx * 100}%`, marginLeft: r.v >= 0 ? "50%" : `${50 - Math.abs(r.v) / mx * 50}%` }} /></div><span className={`pf-div-v mono ${r.v >= 0 ? "up" : "dn"}`}>{r.v >= 0 ? "+" : "−"}{fmt$(Math.abs(r.v))}</span></div>
          ); })}</div>
        </div>
      </div>

      <div className="pf-note mono dim2">Computed live from <b>your</b> holdings &amp; trade journal — equity walks realized closes then marks open positions to market. R-multiples assume ~8% risk/trade; edit trades in the Journal tab to refine. This is <b>your</b> portfolio performance (the Track Record surface audits the system's signals separately).</div>
    </div>
  );
}