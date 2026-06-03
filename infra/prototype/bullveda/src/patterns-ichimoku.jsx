// patterns-ichimoku.jsx — Ichimoku Kinko Hyo. Tenkan/Kijun, the forward-projected
// Kumo cloud (Senkou A/B shifted +26), Chikou span (shifted −26), TK cross & twist.

const { useMemo: useMemoIch } = React;
const ICH_FWD = 26;

function computeIchimoku(bars) {
  const n = bars.length;
  const hh = (p, i) => { let m = -1e9; for (let k = Math.max(0, i - p + 1); k <= i; k++) m = Math.max(m, bars[k].hi); return m; };
  const ll = (p, i) => { let m = 1e9; for (let k = Math.max(0, i - p + 1); k <= i; k++) m = Math.min(m, bars[k].lo); return m; };
  const rawA = [], rawB = [], tenkan = [], kijun = [], chikou = [];
  for (let i = 0; i < n; i++) {
    const tk = (hh(9, i) + ll(9, i)) / 2;
    const kj = (hh(26, i) + ll(26, i)) / 2;
    rawA[i] = (tk + kj) / 2;
    rawB[i] = (hh(52, i) + ll(52, i)) / 2;
    if (i >= 8) tenkan.push({ i, price: tk });
    if (i >= 25) kijun.push({ i, price: kj });
    if (i >= ICH_FWD) chikou.push({ i: i - ICH_FWD, price: bars[i].c });
  }
  // cloud plotted shifted +26, flat-filled left so it spans the chart
  const spanA = [], spanB = [];
  for (let x = 0; x <= n - 1 + ICH_FWD; x++) {
    spanA.push({ i: x, price: rawA[Math.min(n - 1, Math.max(25, x - ICH_FWD))] });
    spanB.push({ i: x, price: rawB[Math.min(n - 1, Math.max(51, x - ICH_FWD))] });
  }
  return { tenkan, kijun, chikou, spanA, spanB };
}

function useIchimoku(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x6c4;
  return useMemoIch(() => {
    const anchors = [
      { i: 0, price: 192 }, { i: 12, price: 184 }, { i: 24, price: 196 }, { i: 34, price: 190 },
      { i: 46, price: 202 }, { i: 56, price: 198 }, { i: 66, price: 209 }, { i: 79, price: 213.4 },
    ];
    const bars = buildSeries({ n: 80, anchors, seed, volSpikes: {} });
    return { bars, ich: computeIchimoku(bars) };
  }, [seed]);
}

function IchimokuChart({ ticker, height = 330 }) {
  const { bars, ich } = useIchimoku(ticker);
  const lines = [
    { pts: ich.tenkan, tone: "cy", width: 1.4, opacity: 0.9 },     // Tenkan
    { pts: ich.kijun, tone: "copper", width: 1.6, opacity: 0.9 },  // Kijun
    { pts: ich.chikou, tone: "violet", width: 1.2, dash: "4 3", opacity: 0.7 }, // Chikou
  ];
  return <CandleChart bars={bars} height={height} lines={lines} cloud={{ spanA: ich.spanA, spanB: ich.spanB }}
                      accent="cy" span={80 + ICH_FWD} projectFrom={80} volume={false} />;
}

const ICH_LINES = [
  { name: "Tenkan-sen (9)", val: "208.6", role: "fast trigger · above Kijun", tone: "cy" },
  { name: "Kijun-sen (26)", val: "201.4", role: "trend baseline · dynamic stop", tone: "copper" },
  { name: "Senkou A", val: "205.0", role: "cloud top (leading)", tone: "gn" },
  { name: "Senkou B", val: "197.2", role: "cloud base (leading)", tone: "rd" },
  { name: "Chikou span", val: "213.4", role: "lagging close · above price 26-ago", tone: "violet" },
];
function IchLines({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Component", k: "name" }, { h: "Value", k: "val", mono: true, align: "right" }, { h: "Read", k: "role" }]}
    rows={ICH_LINES.map(l => ({ name: <b style={{ color: `var(--${l.tone})` }}>{l.name}</b>, val: <b>${l.val}</b>,
      role: <span className="dim2" style={{ fontSize: 11 }}>{l.role}</span> }))} />;
}

const ICH_SIGNALS = [
  { s: "Price above the Kumo", v: "PASS", tone: "gn" },
  { s: "Tenkan &gt; Kijun (bullish TK cross)", v: "PASS", tone: "gn" },
  { s: "Chikou span free of price", v: "PASS", tone: "gn" },
  { s: "Future Kumo green (Senkou A &gt; B)", v: "PASS", tone: "gn" },
  { s: "Price above Kijun baseline", v: "PASS", tone: "gn" },
];
function IchSignals({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Ichimoku signal", k: "s" }, { h: "Status", k: "v", align: "right" }]}
    rows={ICH_SIGNALS.map(r => ({ s: <span dangerouslySetInnerHTML={{ __html: r.s }} />, v: <Pill tone={r.tone} small>{r.v}</Pill> }))} />;
}

function IchTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Level", k: "l" }, { h: "Price", k: "p", mono: true, align: "right" }, { h: "Role", k: "r" }]}
        rows={[
          { l: <b className="up">Kumo-breakout target</b>, p: <b>$222</b>, r: <span className="dim2" style={{ fontSize: 11 }}>cloud height projected from break</span> },
          { l: <b className="copper">Kijun-sen</b>, p: <b>$201.4</b>, r: <span className="dim2" style={{ fontSize: 11 }}>trailing stop / re-entry</span> },
          { l: <b className="gn">Cloud top (Senkou A)</b>, p: <b>$205.0</b>, r: <span className="dim2" style={{ fontSize: 11 }}>first support on a dip</span> },
        ]} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">A close back <b className="dn">inside the Kumo (&lt; $205)</b> neutralises the signal; below Senkou B <b className="dn">$197</b> flips bearish.</span>
      </div>
    </div>
  );
}

function IchStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Cloud</div><div className="pv-stat-v mono up">Price above</div></div>
      <div className="pv-stat-cell"><div className="label-cap">TK cross</div><div className="pv-stat-v mono up">Bullish</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Chikou</div><div className="pv-stat-v mono up">Free</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Future Kumo</div><div className="pv-stat-v mono up">Green · twist</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.74} tone="cy" width={72} /></div></div>
    </div>
  );
}

function IchimokuView({ ticker, dir }) {
  const Chart = <IchimokuChart ticker={ticker} height={dir === "C" ? 250 : 340} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        <IchStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Ichimoku — full overlay" sub="Tenkan · Kijun · Kumo (projected) · Chikou" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Signal checklist" style="minimal" />
            <div className="pv-pad"><IchSignals dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Components" style="minimal" />
            <div className="pv-pad"><IchLines /></div>
            <SectionHeader n={4} title="Targets" style="minimal" />
            <div className="pv-pad"><IchTargets /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <IchStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Components</div>
            <IchLines dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Signal checklist</div>
            <IchSignals dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Targets &amp; invalidation</div>
            <IchTargets />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pv-view">
      <IchStat />
      <SectionHeader n={1} title="Ichimoku Kinko Hyo — full overlay" sub="Tenkan/Kijun · forward-projected Kumo · Chikou span" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Components</div>
          <IchLines />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Signal checklist · 5 of 5</div>
          <IchSignals />
        </div>
        <div>
          <div className="pv-block-h label-cap">Targets &amp; invalidation</div>
          <IchTargets />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { IchimokuView });
