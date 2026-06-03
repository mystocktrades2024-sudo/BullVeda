// patterns-volumeprofile.jsx — Market / Volume Profile (Auction Market Theory).
// Volume-by-price histogram with POC / VAH / VAL, HVN/LVN nodes, profile shape,
// and acceptance/rejection targets. (EODHD/Schwab intraday bins the volume.)

const { useMemo: useMemoVp } = React;

function buildProfile() {
  const bins = [];
  for (let pr = 186; pr <= 218; pr++) {
    const g1 = Math.exp(-((pr - 204.5) ** 2) / (2 * 4.4 ** 2));      // main node
    const g2 = 0.55 * Math.exp(-((pr - 196) ** 2) / (2 * 2.8 ** 2)); // secondary node
    bins.push({ price: pr, vol: (g1 + g2) * 100 + 5 });
  }
  let pocI = 0; bins.forEach((b, i) => { if (b.vol > bins[pocI].vol) pocI = i; });
  bins[pocI].poc = true;
  const max = bins[pocI].vol;
  // value area: expand from POC until 70% of total volume
  const total = bins.reduce((s, b) => s + b.vol, 0);
  let lo = pocI, hi = pocI, acc = bins[pocI].vol;
  while (acc < total * 0.7 && (lo > 0 || hi < bins.length - 1)) {
    const below = lo > 0 ? bins[lo - 1].vol : -1;
    const above = hi < bins.length - 1 ? bins[hi + 1].vol : -1;
    if (above >= below) { hi++; acc += bins[hi].vol; } else { lo--; acc += bins[lo].vol; }
  }
  bins.forEach((b, i) => {
    if (i > 0 && i < bins.length - 1) {
      if (b.vol > bins[i - 1].vol && b.vol > bins[i + 1].vol && b.vol > 0.42 * max && !b.poc) b.hvn = true;
      if (b.vol < bins[i - 1].vol && b.vol < bins[i + 1].vol && b.vol < 0.3 * max) b.lvn = true;
    }
  });
  return { bins, poc: bins[pocI].price, vah: bins[hi].price, val: bins[lo].price };
}
const VP = buildProfile();

function useVolProfile(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x2b8;
  return useMemoVp(() => {
    const anchors = [
      { i: 0, price: 196 }, { i: 8, price: 204 }, { i: 16, price: 198 }, { i: 24, price: 205 },
      { i: 32, price: 200 }, { i: 40, price: 207 }, { i: 48, price: 210 }, { i: 55, price: 213.4 },
    ];
    const bars = buildSeries({ n: 56, anchors, seed, volSpikes: {} });
    return { bars };
  }, [seed]);
}

function VolProfileChart({ ticker, height = 320 }) {
  const { bars } = useVolProfile(ticker);
  const hlines = [
    { price: VP.vah, label: `VAH ${VP.vah}`, tone: "cy", dash: "4 5" },
    { price: VP.poc, label: `POC ${VP.poc}`, tone: "copper", dash: "5 4" },
    { price: VP.val, label: `VAL ${VP.val}`, tone: "cy", dash: "4 5", labelBelow: true },
  ];
  return <CandleChart bars={bars} height={height} hlines={hlines} profile={VP.bins} accent="cy" />;
}

const VP_NODES = [
  { px: "204 – 206", type: "HVN · POC", role: "Fair value · magnet / acceptance", tone: "copper" },
  { px: "196", type: "HVN", role: "Secondary acceptance · support shelf", tone: "cy" },
  { px: "200 – 201", type: "LVN", role: "Rejection gap · price moves fast through", tone: "ink-2" },
  { px: "211 – 212", type: "LVN", role: "Thin zone above VA · breakout accelerant", tone: "ink-2" },
];
function VpNodes({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Price", k: "px", mono: true }, { h: "Node", k: "type", mono: true }, { h: "Auction role", k: "role" }]}
    rows={VP_NODES.map(n => ({ px: <b>{n.px}</b>, type: <span style={{ color: `var(--${n.tone})` }}>{n.type}</span>,
      role: <span className="dim2" style={{ fontSize: 11 }}>{n.role}</span> }))} />;
}

function VpValueArea() {
  return (
    <MiniTable
      cols={[{ h: "Level", k: "lvl" }, { h: "Price", k: "px", mono: true, align: "right" }, { h: "Meaning", k: "m" }]}
      rows={[
        { lvl: <b className="cy">VAH</b>, px: <b>${VP.vah}.0</b>, m: <span className="dim2" style={{ fontSize: 11 }}>top of 70% value · sell-side edge</span> },
        { lvl: <b className="copper">POC</b>, px: <b>${VP.poc}.0</b>, m: <span className="dim2" style={{ fontSize: 11 }}>highest-traded price · fair value</span> },
        { lvl: <b className="cy">VAL</b>, px: <b>${VP.val}.0</b>, m: <span className="dim2" style={{ fontSize: 11 }}>bottom of value · buy-side edge</span> },
      ]} />
  );
}

function VpTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Scenario", k: "s" }, { h: "Basis", k: "b" }, { h: "Target", k: "t", mono: true, align: "right" }, { h: "Conf.", k: "c", align: "right" }]}
        rows={[
          { s: <b className="up">Accept &gt; VAH</b>, b: <span className="dim2" style={{ fontSize: 11 }}>LVN 211–212 offers no resistance</span>, t: <b>$218</b>, c: <ConfBar value={0.63} tone="gn" width={48} /> },
          { s: <b className="up">VA extension</b>, b: <span className="dim2" style={{ fontSize: 11 }}>1× value-area height above VAH</span>, t: <b>$224</b>, c: <ConfBar value={0.5} tone="gn" width={48} /> },
          { s: <b className="warn">Reject at VAH</b>, b: <span className="dim2" style={{ fontSize: 11 }}>rotation back to POC magnet</span>, t: <b>$204</b>, c: <ConfBar value={0.34} tone="amb" width={48} /> },
        ]} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">Acceptance (2+ closes) back below <b className="dn">VAL $199</b> shifts the auction lower — value migrating down.</span>
      </div>
    </div>
  );
}

function VpStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">POC</div><div className="pv-stat-v mono copper">${VP.poc}.0</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Value area</div><div className="pv-stat-v mono cy">{VP.val} – {VP.vah}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Shape</div><div className="pv-stat-v mono">D · balanced</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Price vs VA</div><div className="pv-stat-v mono up">above VAH</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.66} tone="cy" width={72} /></div></div>
    </div>
  );
}

function VolumeProfileView({ ticker, dir }) {
  const Chart = <VolProfileChart ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        <VpStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Volume profile — by price" sub="POC · value area · HVN/LVN nodes" style="minimal" />
            <div className="pv-pad">{Chart}</div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={2} title="Value area" style="minimal" />
            <div className="pv-pad"><VpValueArea /></div>
            <SectionHeader n={3} title="Targets" style="minimal" />
            <div className="pv-pad"><VpTargets /></div>
          </div>
        </div>
        <SectionHeader n={4} title="Volume nodes" style="minimal" />
        <div className="pv-pad"><VpNodes /></div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <VpStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Value area</div>
            <VpValueArea />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Volume nodes</div>
            <VpNodes dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Auction targets</div>
            <VpTargets />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pv-view">
      <VpStat />
      <SectionHeader n={1} title="Volume profile — volume by price" sub="POC · VAH/VAL value area · HVN/LVN nodes on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Value area</div>
          <VpValueArea />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Volume nodes (HVN / LVN)</div>
          <VpNodes />
        </div>
        <div>
          <div className="pv-block-h label-cap">Auction targets &amp; invalidation</div>
          <VpTargets />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { VolumeProfileView });
