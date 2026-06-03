// surface-settings.jsx — Settings · operator role · capabilities · preferences · audit.
// Per-user surface. Preferences persist to localStorage (settings_v1) and apply live.

const { useState: useSet, useEffect: useSete } = React;

const SET_LS = "settings_v1";
const SET_DEFAULTS = {
  defaultMode: "SWING", accent: "copper", defaultLens: "overview", landingSurface: "home",
  density: "comfortable", poll: 6, numFmt: "abbreviated",
  notifAlerts: true, notifEarnings: true, notifFills: false, notifDigest: true,
};
function loadSet() { try { return { ...SET_DEFAULTS, ...JSON.parse(localStorage.getItem(SET_LS) || "{}") }; } catch (e) { return { ...SET_DEFAULTS }; } }

const SET_CAPS = [
  { n: "View all surfaces & lenses", s: "on" }, { n: "Run scans & screeners", s: "on" },
  { n: "Edit watchlists & portfolios", s: "on" }, { n: "Edit signal_log", s: "on" },
  { n: "Edit decision_log", s: "off" }, { n: "CapStudio matrix admin", s: "gated" },
  { n: "Force regime override", s: "gated" }, { n: "Manual setup kill", s: "gated" },
  { n: "Export data / reports", s: "on" }, { n: "Live order routing", s: "off" },
  { n: "Manage users & roles", s: "off" }, { n: "View audit log", s: "on" },
];

function SurfaceSettings() {
  const [s, setS] = useSet(loadSet);
  const [live, setLive] = useSet(false);
  const [log, setLog] = useSet(() => [
    { t: "now", a: "Opened Settings", tone: "cy" },
    { t: "2m", a: "Switched tier preview → Elite", tone: "ink" },
    { t: "14m", a: "Edited Core Equity portfolio · +ARCM", tone: "gn" },
    { t: "31m", a: "Ran scan · breakout · 22 hits", tone: "ink" },
    { t: "1h", a: "Viewed ARGN · 14-lens detail", tone: "ink" },
  ]);
  const set = (k, v) => { const next = { ...s, [k]: v }; setS(next); try { localStorage.setItem(SET_LS, JSON.stringify(next)); } catch (e) {} setLog(l => [{ t: "now", a: `Changed ${k} → ${v}`, tone: "amb" }, ...l].slice(0, 10)); };
  useSete(() => { try { localStorage.setItem(SET_LS, JSON.stringify(s)); } catch (e) {} }, []);

  const capOn = SET_CAPS.filter(c => c.s === "on").length;
  const capGated = SET_CAPS.filter(c => c.s === "gated").length;

  const Seg = ({ k, opts }) => (
    <span className="set-seg">{opts.map(([v, l]) => <button key={v} className={s[k] === v ? "is-on" : ""} onClick={() => set(k, v)}>{l}</button>)}</span>
  );
  const Toggle = ({ k, label, sub }) => (
    <div className="set-toggle" onClick={() => set(k, !s[k])}>
      <span className={`set-tog-sw ${s[k] ? "is-on" : ""}`}><span className="set-tog-dot" /></span>
      <span className="set-tog-l"><b>{label}</b>{sub && <span className="dim2 mono"> · {sub}</span>}</span>
    </div>
  );

  return (
    <div className="surface wsx wsx--copper set-srf">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SETTINGS · ROLE · CAPABILITIES · PREFERENCES</div>
          <h1 className="wsx-title mono">Settings</h1>
          <div className="wsx-sub mono dim2">your role &amp; capabilities · personal preferences (saved locally, applied on load) · session audit</div>
        </div>
        <FreshnessPill state="live" age="now" />
      </div>

      {/* operator hero */}
      <div className="set-hero">
        <div className="set-hero-l">
          <span className="set-hero-badge">★ OPERATOR</span>
          <div className="set-hero-role mono">⚒ Owner — j.kairos</div>
          <div className="set-hero-mech mono dim2">CapStudio admin · all module renders enabled · <b className="copper">paper-only</b> — no live order routing · role changes apply on next page load.</div>
        </div>
        <div className="set-hero-nums">
          <div className="set-hero-num"><div className="k mono dim2">Caps enabled</div><div className="v mono up">{capOn}</div><div className="s mono dim2">of {SET_CAPS.length} · {capGated} gated</div></div>
          <div className="set-hero-num"><div className="k mono dim2">Plan</div><div className="v mono copper">Elite</div><div className="s mono dim2">$330 · paper</div></div>
        </div>
      </div>

      <div className="set-2col">
        {/* capabilities */}
        <div className="lab-card">
          <div className="lab-card-h mono">CAPABILITIES <span className="dim2">· green enabled · amber gated · grey off · CapStudio is source of truth</span></div>
          <div className="set-caps">
            {SET_CAPS.map((c, i) => (
              <div key={i} className={`set-cap set-cap--${c.s}`}>
                <span className="set-cap-dot" />
                <span className="set-cap-n">{c.n}</span>
                <span className="set-cap-s mono">{c.s === "on" ? "ENABLED" : c.s === "gated" ? "GATED" : "OFF"}</span>
              </div>
            ))}
          </div>
          {/* paper-only — no live execution surface */}
          <div className="set-live set-live--paper">
            <div className="set-live-l">
              <span className="mono"><b className="up">● PAPER MODE · SIMULATION ONLY</b></span>
              <span className="set-live-sub mono dim2">This terminal does not route live orders. Every trade is paper / simulated for research &amp; education — informational only, not investment advice.</span>
            </div>
            <span className="set-live-btn" style={{ pointerEvents: "none", opacity: 0.65 }}>No live trading</span>
          </div>
        </div>

        {/* preferences */}
        <div className="lab-card">
          <div className="lab-card-h mono">PREFERENCES <span className="dim2">· saved to localStorage · applied on next load</span></div>
          <div className="set-prefs">
            <div className="set-pref"><span className="set-pref-k">Accent</span><span className="set-accents">{["copper", "cy", "gn", "violet", "blue"].map(a => <button key={a} className={`set-acc ${s.accent === a ? "is-on" : ""}`} style={{ background: `var(--${a})` }} onClick={() => set("accent", a)} title={a} />)}</span></div>
            <div className="set-pref"><span className="set-pref-k">Default lens</span><Seg k="defaultLens" opts={[["overview", "Overview"], ["plan", "Plan"], ["technicals", "Technicals"]]} /></div>
            <div className="set-pref"><span className="set-pref-k">Landing surface</span><Seg k="landingSurface" opts={[["home", "Home"], ["momentum", "Momentum"], ["myportfolios", "Portfolios"]]} /></div>
            <div className="set-pref"><span className="set-pref-k">Density</span><Seg k="density" opts={[["compact", "Compact"], ["comfortable", "Comfortable"]]} /></div>
            <div className="set-pref"><span className="set-pref-k">Number format</span><Seg k="numFmt" opts={[["abbreviated", "1.2M"], ["full", "1,200,000"]]} /></div>
            <div className="set-pref"><span className="set-pref-k">Poll interval</span><span className="set-poll"><input type="range" min="3" max="30" step="1" value={s.poll} onChange={e => set("poll", +e.target.value)} /><span className="mono">{s.poll}s</span></span></div>
          </div>
          <div className="set-notif-h label-cap">Notifications</div>
          <div className="set-notifs">
            <Toggle k="notifAlerts" label="Price & signal alerts" sub="real-time" />
            <Toggle k="notifEarnings" label="Earnings reminders" sub="T−2 days" />
            <Toggle k="notifFills" label="Paper fills" sub="simulated" />
            <Toggle k="notifDigest" label="Daily digest" sub="EOD email" />
          </div>
        </div>
      </div>

      {/* session audit log */}
      <div className="lab-card">
        <div className="lab-card-h mono">SESSION AUDIT LOG <span className="dim2">· append-only · last {log.length} actions this session</span></div>
        <div className="set-audit">
          {log.map((e, i) => (
            <div key={i} className="set-audit-row">
              <span className={`set-audit-dot kpi-tone-bg--${e.tone === "ink" ? "" : e.tone}`} />
              <span className="set-audit-t mono dim2">{e.t}</span>
              <span className="set-audit-a mono">{e.a}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="pf-note mono dim2">
        Your preferences persist in this browser (<b>localStorage</b>) and apply on next load · capabilities are read from the <b>CapStudio RBAC matrix</b> (admins edit it in User Management) · the audit log is the per-session accountability trail. Live trading is gated — arming is session-scoped and re-locks on reload.
      </div>
    </div>
  );
}

window.SurfaceSettings = SurfaceSettings;
