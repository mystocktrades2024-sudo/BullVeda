// patterns-volumeprofile.jsx — Market / Volume Profile (Auction Market Theory).
//
// REAL DATA: the profile (POC / VAH / VAL / HVN / LVN / nodes / targets /
// auction read) is computed server-side by engines/volprofile.py over real
// EODHD bars and fetched via the shared pattern endpoint.
// Mode-aware: SWING=daily, POSITION=weekly, INVESTMENT=monthly.
//
// Falls back to the illustrative fixture when the server is absent or the
// window has too few bars; the header badge says so honestly.

const { useMemo: useMemoVp } = React;

// ── illustrative fixture (fallback only — labelled in the UI) ───────────────
function _buildFixtureProfile() {
  const bins = [];
  for (let pr = 186; pr <= 218; pr++) {
    const g1 = Math.exp(-((pr - 204.5) ** 2) / (2 * 4.4 ** 2));
    const g2 = 0.55 * Math.exp(-((pr - 196) ** 2) / (2 * 2.8 ** 2));
    bins.push({ price: pr, vol: (g1 + g2) * 100 + 5 });
  }
  let pocI = 0; bins.forEach((b, i) => { if (b.vol > bins[pocI].vol) pocI = i; });
  bins[pocI].poc = true;
  const max = bins[pocI].vol;
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
const _FIX_VP = _buildFixtureProfile();

const FIX_NODES = [
  { px: "204 – 206", type: "HVN · POC", role: "Fair value · magnet / acceptance", tone: "copper", price_val: 205 },
  { px: "196", type: "HVN", role: "Secondary acceptance · support shelf", tone: "cy", price_val: 196 },
  { px: "200 – 201", type: "LVN", role: "Rejection gap · price moves fast through", tone: "ink-2", price_val: 200 },
  { px: "211 – 212", type: "LVN", role: "Thin zone above VA · breakout accelerant", tone: "ink-2", price_val: 211 },
];

const FIX_TARGETS = [
  { scenario: "Accept > VAH", basis: "LVN 211–212 offers no resistance", target: "$218", conf: 0.63, tone: "gn", scenario_tone: "up" },
  { scenario: "VA extension",  basis: "1× value-area height above VAH",  target: "$224", conf: 0.50, tone: "gn", scenario_tone: "up" },
  { scenario: "Reject at VAH", basis: "Rotation back to POC magnet",      target: "$204", conf: 0.34, tone: "amb", scenario_tone: "warn" },
];

const FIX_INVALIDATION = "Acceptance (2+ closes) back below VAL $199 shifts the auction lower — value migrating down.";

const FIX_STAT = {
  poc: "$205.0", value_area: "199 – 211", shape: "D · balanced",
  price_vs_va: "above VAH", confidence: 0.66,
  poc_raw: 205, vah_raw: 211, val_raw: 199,
};

var VP_FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  profile: _FIX_VP.bins, poc: _FIX_VP.poc, vah: _FIX_VP.vah, val: _FIX_VP.val,
  nodes: FIX_NODES, targets: FIX_TARGETS, invalidation: FIX_INVALIDATION,
  stat: FIX_STAT, shape: "D · balanced", price_vs_va: "above VAH",
  confidence: 0.66,
};

function _buildFixtureBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x2b8;
  const anchors = [
    { i: 0, price: 196 }, { i: 8, price: 204 }, { i: 16, price: 198 }, { i: 24, price: 205 },
    { i: 32, price: 200 }, { i: 40, price: 207 }, { i: 48, price: 210 }, { i: 55, price: 213.4 },
  ];
  return buildSeries({ n: 56, anchors, seed, volSpikes: {} });
}

// ── data hook: real → fixture fallback (mode-aware) ─────────────────────────
function useVolProfileModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("volprofile", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;
  const fixtureBars = useMemoVp(() => _buildFixtureBars(ticker), [sym]);

  // fully-formed real payload?
  const usable = (
    state === "loaded" && real && real.ok &&
    real.state === "real" && real.profile && real.profile.length &&
    real.bars && real.bars.length
  );

  if (usable) {
    return {
      model: {
        isReal: true, source: "real",
        tier: real.tier, tf,
        bars:        real.bars,
        profile:     real.profile,
        poc:         real.poc,
        vah:         real.vah,
        val:         real.val,
        shape:       real.shape,
        price_vs_va: real.price_vs_va,
        nodes:       real.nodes   || [],
        targets:     real.targets || [],
        invalidation: real.invalidation || "",
        read:        real.read || "",
        stat:        real.stat || FIX_STAT,
        confidence:  real.confidence,
        cur_close:   real.cur_close,
        lvn_above:   real.lvn_above,
        lvn_below:   real.lvn_below,
      },
      state: "real", sym, tf, usable: true,
    };
  }

  // real responded but no usable structure
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...VP_FIXTURE_MODEL, bars: fixtureBars, tf },
      state: "none", sym, tf, usable: false,
      message: real.message || "No usable volume profile for this window.",
    };
  }

  // not yet loaded or server absent → illustrative fixture
  return {
    model: { ...VP_FIXTURE_MODEL, bars: fixtureBars },
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── chart ────────────────────────────────────────────────────────────────────
function VolProfileChart({ model, height = 320 }) {
  const bars    = model.bars || [];
  const vah     = (model.stat && model.stat.vah_raw != null) ? model.stat.vah_raw : (model.vah || 0);
  const val     = (model.stat && model.stat.val_raw != null) ? model.stat.val_raw : (model.val || 0);
  const poc     = (model.stat && model.stat.poc_raw != null) ? model.stat.poc_raw : (model.poc || 0);
  const profile = model.profile || [];
  const hlines  = [
    { price: vah, label: `VAH ${(+vah).toFixed(2)}`, tone: "cy",     dash: "4 5" },
    { price: poc, label: `POC ${(+poc).toFixed(2)}`, tone: "copper", dash: "5 4" },
    { price: val, label: `VAL ${(+val).toFixed(2)}`, tone: "cy",     dash: "4 5", labelBelow: true },
  ].filter(h => h.price > 0);

  return <CandleChart bars={bars} height={height} hlines={hlines} profile={profile} accent="cy" />;
}

// ── stat header strip ────────────────────────────────────────────────────────
function VpStat({ model }) {
  const s   = (model && model.stat) || FIX_STAT;
  const poc = s.poc || `$${(model.poc || 0).toFixed(2)}`;
  const va  = s.value_area || `${(model.val || 0).toFixed(2)} – ${(model.vah || 0).toFixed(2)}`;
  const shp = s.shape || model.shape || "—";
  const pos = s.price_vs_va || model.price_vs_va || "—";
  const conf = s.confidence != null ? s.confidence : (model.confidence || 0);
  const posTone = (pos.includes("above") ? "up" : pos.includes("below") ? "dn" : "dim2");
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">POC</div><div className="pv-stat-v mono copper">{poc}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Value area</div><div className="pv-stat-v mono cy">{va}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Shape</div><div className="pv-stat-v mono">{shp}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Price vs VA</div><div className={`pv-stat-v mono ${posTone}`}>{pos}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={conf} tone="cy" width={72} /></div></div>
    </div>
  );
}

// ── value area table ─────────────────────────────────────────────────────────
function VpValueArea({ model }) {
  const vah  = (model.stat && model.stat.vah_raw != null) ? model.stat.vah_raw : (model.vah || 0);
  const val  = (model.stat && model.stat.val_raw != null) ? model.stat.val_raw : (model.val || 0);
  const poc  = (model.stat && model.stat.poc_raw != null) ? model.stat.poc_raw : (model.poc || 0);
  const dp   = (poc < 20 || val < 20) ? 2 : (poc < 100 ? 2 : 2);
  return (
    <table className="pv-table">
      <thead><tr>
        <th className="label-cap">Level</th>
        <th className="label-cap" style={{ textAlign: "right" }}>Price</th>
        <th className="label-cap">Meaning</th>
      </tr></thead>
      <tbody>
        <tr>
          <td><b className="cy">VAH</b></td>
          <td className="mono" style={{ textAlign: "right" }}><b>${vah.toFixed(dp)}</b></td>
          <td><span className="dim2" style={{ fontSize: 11 }}>top of 70% value · sell-side edge</span></td>
        </tr>
        <tr>
          <td><b className="copper">POC</b></td>
          <td className="mono" style={{ textAlign: "right" }}><b>${poc.toFixed(dp)}</b></td>
          <td><span className="dim2" style={{ fontSize: 11 }}>highest-traded price · fair value</span></td>
        </tr>
        <tr>
          <td><b className="cy">VAL</b></td>
          <td className="mono" style={{ textAlign: "right" }}><b>${val.toFixed(dp)}</b></td>
          <td><span className="dim2" style={{ fontSize: 11 }}>bottom of value · buy-side edge</span></td>
        </tr>
      </tbody>
    </table>
  );
}

// ── volume nodes table ───────────────────────────────────────────────────────
function VpNodes({ model, dense }) {
  const nodes = (model && model.nodes && model.nodes.length) ? model.nodes : FIX_NODES;
  return <MiniTable dense={dense}
    cols={[
      { h: "Price", k: "px", mono: true },
      { h: "Node",  k: "type", mono: true },
      { h: "Auction role", k: "role" },
    ]}
    rows={nodes.map(n => ({
      px:   <b>{n.px}</b>,
      type: <span style={{ color: `var(--${n.tone || "ink-2"})` }}>{n.type}</span>,
      role: <span className="dim2" style={{ fontSize: 11 }}>{n.role}</span>,
    }))} />;
}

// ── targets + invalidation ───────────────────────────────────────────────────
function VpTargets({ model }) {
  const tgts = (model && model.targets && model.targets.length) ? model.targets : FIX_TARGETS;
  const inv  = (model && model.invalidation) ? model.invalidation : FIX_INVALIDATION;
  return (
    <div className="pv-targets">
      <table className="pv-table">
        <thead><tr>
          <th className="label-cap">Scenario</th>
          <th className="label-cap">Basis</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Target</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Conf.</th>
        </tr></thead>
        <tbody>
          {tgts.map((t, i) => {
            const sTone = t.scenario_tone || (t.tone === "rd" ? "dn" : t.tone === "gn" ? "up" : "warn");
            return (
              <tr key={i}>
                <td><b className={sTone}>{t.scenario}</b></td>
                <td><span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span></td>
                <td className="mono" style={{ textAlign: "right" }}><b>{t.target}</b></td>
                <td style={{ textAlign: "right" }}>
                  {t.conf != null
                    ? <ConfBar value={t.conf} tone={t.tone || "cy"} width={48} />
                    : <span className="dim mono">—</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">{inv}</span>
      </div>
    </div>
  );
}

// ── honest empty state ───────────────────────────────────────────────────────
function VpNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no volume profile</div>
        <div className="pv-empty-msg">{message || `Not enough volume data on ${sym || "this name"} to build a meaningful profile.`}</div>
        <div className="pv-empty-sub mono dim2">The detector requires at least 30 bars with real traded volume. It will populate automatically when enough data is available.</div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions) ────────────────────────────────────────────
function VolumeProfileView({ ticker, dir, mode }) {
  const { model, state, sym, tf, usable, message } = useVolProfileModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <VpNone sym={sym} message={message} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tier={model.tier} tf={tf || model.tf} />
    </div>
  );
  const Chart = <VolProfileChart model={model} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <VpStat model={model} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Volume profile — by price" sub="POC · value area · HVN/LVN nodes" style="minimal" />
            <div className="pv-pad">{Chart}</div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={2} title="Value area" style="minimal" />
            <div className="pv-pad"><VpValueArea model={model} /></div>
            <SectionHeader n={3} title="Auction targets" style="minimal" />
            <div className="pv-pad"><VpTargets model={model} /></div>
          </div>
        </div>
        <SectionHeader n={4} title="Volume nodes" style="minimal" />
        <div className="pv-pad"><VpNodes model={model} /></div>
        {usable && model.read && (
          <div className="pv-pad">
            <div className="pv-block-h label-cap">Auction read</div>
            <div className="pv-tl-note" style={{ padding: "8px 0" }}>{model.read}</div>
          </div>
        )}
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <VpStat model={model} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Value area</div>
            <VpValueArea model={model} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Volume nodes</div>
            <VpNodes model={model} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Auction targets</div>
            <VpTargets model={model} />
            {usable && model.read && (
              <>
                <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Auction read</div>
                <div className="pv-tl-note" style={{ padding: "6px 0", fontSize: 12 }}>{model.read}</div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <VpStat model={model} />
      <SectionHeader n={1} title="Volume profile — volume by price" sub="POC · VAH/VAL value area · HVN/LVN nodes on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Value area</div>
          <VpValueArea model={model} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Volume nodes (HVN / LVN)</div>
          <VpNodes model={model} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Auction targets &amp; invalidation</div>
          <VpTargets model={model} />
          {usable && model.read && (
            <>
              <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Auction read</div>
              <div className="pv-tl-note" style={{ padding: "8px 0" }}>{model.read}</div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── dynamic read line (lens-level) ──────────────────────────────────────────
function VolumeProfileReadLine({ ticker, mode }) {
  const { model, state, usable } = useVolProfileModel(ticker, mode);
  if (state === "none") {
    return <span className="mono">Not enough volume data to build a profile for this name — <b className="dim2">stand aside</b>.</span>;
  }
  if (!usable) {
    // illustrative fallback
    return <span className="mono">Value area <b className="cy">$199–$211</b>; POC <b className="copper">$205</b> (highest-traded price) is the magnet. Price above VAH — auction favours continuation; LVN at $211–212 is fast-travel zone.</span>;
  }
  const s   = model.stat || {};
  const poc = s.poc || `$${(model.poc || 0).toFixed(2)}`;
  const va  = s.value_area || "";
  const pos = s.price_vs_va || model.price_vs_va || "";
  const posTone = pos.includes("above") ? "up" : pos.includes("below") ? "dn" : "dim2";
  const lvnA = model.lvn_above ? ` Next LVN (fast-travel) at $${model.lvn_above.toFixed(2)}.` : "";
  const lvnB = model.lvn_below ? ` Nearest LVN below: $${model.lvn_below.toFixed(2)}.` : "";
  return (
    <span className="mono">
      Value area <b className="cy">${va}</b>; POC <b className="copper">{poc}</b>.
      Price is <b className={posTone}>{pos}</b>.
      {model.read && <> {model.read}</>}
      {lvnA}{lvnB}
    </span>
  );
}

Object.assign(window, { VolumeProfileView, VolumeProfileReadLine });
