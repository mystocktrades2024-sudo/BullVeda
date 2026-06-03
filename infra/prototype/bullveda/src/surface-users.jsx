// surface-users.jsx — Admin · User Management. Assign users to commercial tiers.

const { useState: useUM, useMemo: useUMm } = React;

const UM_SEED = [
  { name: "Jules Kairos",   email: "jules@kairos.fund",    tier: 5, status: "active",   last: "now",     mfa: true,  trades: 412 },
  { name: "Priya Natarajan",email: "priya@meridiancap.com",tier: 4, status: "active",   last: "2m ago",  mfa: true,  trades: 318 },
  { name: "Marcus Welby",   email: "marcus@welbyadv.com",  tier: 3, status: "active",   last: "1h ago",  mfa: true,  trades: 196 },
  { name: "Dana Okoye",     email: "dana@okoye.io",        tier: 2, status: "active",   last: "3h ago",  mfa: false, trades: 84 },
  { name: "Theo Brandt",    email: "theo@brandtfx.de",     tier: 2, status: "active",   last: "yesterday",mfa: true, trades: 71 },
  { name: "Lena Park",      email: "lena@parkquant.kr",    tier: 1, status: "trial",    last: "2d ago",  mfa: false, trades: 12 },
  { name: "Sam Rivera",     email: "sam.rivera@gmail.com", tier: 1, status: "active",   last: "5h ago",  mfa: false, trades: 23 },
  { name: "Omar Haddad",    email: "omar@haddadcap.ae",    tier: 0, status: "active",   last: "1d ago",  mfa: false, trades: 3 },
  { name: "Grace Liu",      email: "grace@liufunds.sg",    tier: 3, status: "suspended",last: "12d ago", mfa: true,  trades: 142 },
];

function SurfaceUsers() {
  const [view, setView] = useUM("users");
  const [users, setUsers] = useUM(UM_SEED);
  const [q, setQ] = useUM("");
  const [fTier, setFTier] = useUM("all");
  const [editing, setEditing] = useUM(null); // {_i, name, email, tier, status, mfa} or "new"
  const tiers = window.TIER_LIST || [];

  const rows = useUMm(() => {
    let r = users.map((u, i) => ({ ...u, _i: i }));
    if (q.trim()) { const s = q.toLowerCase(); r = r.filter(u => (u.name + u.email).toLowerCase().includes(s)); }
    if (fTier !== "all") r = r.filter(u => u.tier === +fTier);
    return r;
  }, [users, q, fTier]);

  const setTier = (i, tier) => setUsers(us => us.map((u, k) => k === i ? { ...u, tier } : u));
  const counts = useUMm(() => tiers.map(t => ({ ...t, n: users.filter(u => u.tier === t.id).length })), [users, tiers]);

  const openNew = () => setEditing({ _i: -1, name: "", email: "", tier: 1, status: "active", mfa: false, trades: 0, last: "never" });
  const openEdit = (u) => setEditing({ ...u });
  const saveUser = (u) => {
    setUsers(us => {
      if (u._i < 0) return [...us, { ...u, _i: undefined }];
      return us.map((x, k) => k === u._i ? { ...x, ...u } : x);
    });
    setEditing(null);
  };
  const deleteUser = (i) => { setUsers(us => us.filter((_, k) => k !== i)); setEditing(null); };

  return (
    <div className="surface wsx wsx--amb um">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">ADMIN · USER MANAGEMENT · RBAC</div>
          <h1 className="wsx-title mono">User Management</h1>
          <div className="wsx-sub mono dim2">add &amp; edit users · assign tiers · configure tier access</div>
        </div>
        <div className="wsx-hdr-r">
          {view === "users" && <button className="btn btn--primary btn--sm" onClick={openNew}>＋ Add user</button>}
          <FreshnessPill state="live" age="—" />
        </div>
      </div>

      <div className="um-viewtabs">
        <button className={`um-vt ${view==="users"?"is-on":""}`} onClick={()=>setView("users")}>Users &amp; Tiers</button>
        <button className={`um-vt ${view==="access"?"is-on":""}`} onClick={()=>setView("access")}>Tier Access · Configure</button>
      </div>

      {view === "users" ? (
        <>
          <div className="um-tiers">
            {counts.map(t => (
              <button key={t.id} className={`um-tier ${fTier===String(t.id)?"is-on":""} um-tier--${t.id}`} onClick={()=>setFTier(fTier===String(t.id)?"all":String(t.id))}>
                <div className="um-tier-n mono">{t.n}</div>
                <div className="um-tier-l mono">T{t.id} · {t.name}</div>
                <div className="um-tier-p mono dim2">{t.price}</div>
              </button>
            ))}
          </div>

          <div className="lab-tabs">
            <button className={`lab-tab ${fTier==="all"?"is-on":""}`} onClick={()=>setFTier("all")}>All users · {users.length}</button>
            <input className="nw-search mono" placeholder="⌕ name or email…" value={q} onChange={e=>setQ(e.target.value)} style={{marginLeft:"auto"}} />
          </div>

          <div className="wsx-body">
            <table className="dtable wsx-tbl um-tbl">
              <thead><tr>
                <th>User</th><th>Email</th><th>Status</th><th>MFA</th><th className="r">Trades</th><th>Last active</th><th>Tier · assign</th><th></th>
              </tr></thead>
              <tbody>{rows.map(u=>(
                <tr key={u._i}>
                  <td><div className="um-user"><span className="um-avatar">{(u.name||"?").split(" ").map(x=>x[0]).join("").slice(0,2)}</span><b>{u.name}</b></div></td>
                  <td className="dim2">{u.email}</td>
                  <td><span className={`um-status um-status--${u.status}`}>{u.status}</span></td>
                  <td>{u.mfa ? <span className="up">✓ on</span> : <span className="dim">— off</span>}</td>
                  <td className="r tabular">{u.trades}</td>
                  <td className="dim2">{u.last}</td>
                  <td>
                    <select className="um-sel" value={u.tier} onChange={e=>setTier(u._i, +e.target.value)} data-tier={u.tier}>
                      {tiers.map(t => <option key={t.id} value={t.id}>T{t.id} · {t.name} · {t.price}</option>)}
                    </select>
                  </td>
                  <td><button className="um-edit" onClick={()=>openEdit(u)} title="Edit user">✎</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>

          <div className="pm-note mono dim2">
            Tier changes apply immediately and gate every surface/lens via the RBAC matrix. Suspending revokes session tokens.
            MFA enforced for Tier ≥ 3. Audit-logged to Change History.
          </div>
        </>
      ) : (
        <TierAccessConfig tiers={tiers} />
      )}

      {editing && (
        <UserEditModal user={editing} tiers={tiers} onSave={saveUser} onDelete={deleteUser} onClose={()=>setEditing(null)} />
      )}
    </div>
  );
}

function UserEditModal({ user, tiers, onSave, onDelete, onClose }) {
  const [u, setU] = useUM(user);
  const set = (k, v) => setU(x => ({ ...x, [k]: v }));
  const isNew = u._i < 0;
  const valid = u.name.trim() && /\S+@\S+\.\S+/.test(u.email);
  return ReactDOM.createPortal((
    <div className="um-modal-bg" onMouseDown={onClose}>
      <div className="um-modal" onMouseDown={e=>e.stopPropagation()}>
        <div className="um-modal-h">
          <span className="mono">{isNew ? "ADD USER" : "EDIT USER"}</span>
          <button className="um-modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="um-modal-body">
          <label className="um-field"><span className="mono dim2">Full name</span>
            <input className="um-input" value={u.name} onChange={e=>set("name", e.target.value)} placeholder="Jane Trader" /></label>
          <label className="um-field"><span className="mono dim2">Email</span>
            <input className="um-input" value={u.email} onChange={e=>set("email", e.target.value)} placeholder="jane@fund.com" /></label>
          <div className="um-field-row">
            <label className="um-field"><span className="mono dim2">Tier</span>
              <select className="um-input" value={u.tier} onChange={e=>set("tier", +e.target.value)}>
                {tiers.map(t => <option key={t.id} value={t.id}>T{t.id} · {t.name} · {t.price}</option>)}
              </select></label>
            <label className="um-field"><span className="mono dim2">Status</span>
              <select className="um-input" value={u.status} onChange={e=>set("status", e.target.value)}>
                <option value="active">active</option><option value="trial">trial</option><option value="suspended">suspended</option>
              </select></label>
          </div>
          <label className="um-toggle"><input type="checkbox" checked={u.mfa} onChange={e=>set("mfa", e.target.checked)} /><span className="mono">MFA enabled {u.tier>=3 && <b className="amb">· required for Tier ≥ 3</b>}</span></label>
        </div>
        <div className="um-modal-foot">
          {!isNew && <button className="btn btn--sm um-del" onClick={()=>onDelete(u._i)}>🗑 Delete</button>}
          <div style={{marginLeft:"auto", display:"flex", gap:6}}>
            <button className="btn btn--sm" onClick={onClose}>Cancel</button>
            <button className="btn btn--primary btn--sm" disabled={!valid} onClick={()=>valid && onSave(u)}>{isNew ? "Create user" : "Save changes"}</button>
          </div>
        </div>
      </div>
    </div>
  ), document.body);
}

// ─── Tier Access configuration ──────────────────────────────────
const UM_SURFACE_LABELS = {
  home:"Home", "signal-scanner":"Signal Scanner", "market-map":"Market Map", watchlist:"Watchlist", buy:"Bullish Candidates",
  playbook:"Playbook", alerts:"Alerts", screener:"Screener", premarket:"Pre-Market", "sector-etf":"ETFs",
  "etf-screener":"ETF Screener", options:"Options", news:"News · Sentiment",
  elite:"Elite Picks", strategies:"Strategies", themes:"Themes", momentum:"Momentum", performance:"Performance",
  "ai-predict":"AI Predictions", insider:"Insider Trading", journal:"Trade Journal", social:"Social Sentiment",
  "portfolio-srf":"Portfolio",
};
const UM_LENS_LABELS = {
  overview:"Overview", plan:"Plan · Ticket", chart:"Chart", technicals:"Technicals", patterns:"Patterns", smc:"SMC",
  investment:"Investment", risk:"Risk", earnings:"Earnings", options:"Options", portfolio:"Portfolio", tape:"Tape · Flow",
  track:"Track Record", mledge:"AI Edge",
};

// Min-tier pill selector. `min` greys out tiers below the surface floor
// (a section can be equal-or-higher than its surface, never lower).
function TacPills({ tiers, value, onChange, min = 0, size }) {
  return (
    <div className={`tac-pills ${size === "sm" ? "tac-pills--sm" : ""}`}>
      {tiers.map(t => {
        const dis = t.id < min;
        return (
          <button key={t.id} disabled={dis}
            className={`tac-pill tac-pill--${t.id} ${value === t.id ? "is-on" : ""} ${dis ? "is-dis" : ""}`}
            onClick={() => !dis && onChange(t.id)}
            title={dis ? `Below surface floor (T${min})` : `${t.name} · ${t.price}`}>T{t.id}</button>
        );
      })}
    </div>
  );
}

function TierAccessConfig({ tiers }) {
  const [, force] = useUM(0);
  const bump = () => force(x => x + 1);
  const surf = window.SURFACE_TIER || {};
  const lens = window.LENS_TIER || {};
  const ST = window.SECTION_TIER || (window.SECTION_TIER = {});
  const OFF = window.SECTION_OFF || (window.SECTION_OFF = {});
  const key = window.sectionKey;
  const effTier = window.sectionTier;

  const [open, setOpen] = useUM(() => ({ premarket: true }));
  const toggleOpen = (k) => setOpen(o => ({ ...o, [k]: !o[k] }));

  const setSurf = (k, v) => { window.SURFACE_TIER[k] = v; bump(); };
  const setLens = (k, v) => { window.LENS_TIER[k] = v; bump(); };

  // section override: store only when raised ABOVE the surface/lens floor
  const setSec = (surface, panelId, tier) => {
    const floor = surface.indexOf("lens:") === 0 ? (lens[surface.slice(5)] ?? 0) : (surf[surface] ?? 0);
    const kk = key(surface, panelId);
    if (tier <= floor) delete ST[kk]; else ST[kk] = tier;
    bump();
  };
  const setGroupAll = (surface, panels, tier) => {
    const floor = surf[surface] ?? 0;
    panels.forEach(p => {
      const kk = key(surface, p.id);
      if (tier <= floor) delete ST[kk]; else ST[kk] = tier;
    });
    bump();
  };
  const toggleOff = (surface, panelId) => {
    const kk = key(surface, panelId);
    if (OFF[kk]) delete OFF[kk]; else OFF[kk] = true;
    bump();
  };

  const surfaces = Object.entries(UM_SURFACE_LABELS);

  return (
    <div className="tac">
      <div className="tac-legend mono dim2">
        <b>Tier access matrix</b> — columns are tiers, rows are features. Click a cell to set the tier that <b>unlocks</b> a surface; click a surface name to gate its individual sections. Changes apply live.
        <span className="tac-legendkey">
          <span><span className="tacx-lk tacx-lk--on">✓</span> included</span>
          <span><span className="tacx-lk tacx-lk--floor">●</span> unlock tier</span>
          <span><span className="tacx-lk tacx-lk--off">⊘</span> disabled</span>
        </span>
      </div>

      {/* ── Surfaces · tier access matrix ────────────────────────── */}
      <div className="lab-card">
        <div className="lab-card-h mono tac-acc-h">
          <span>SURFACE ACCESS MATRIX · {surfaces.length}</span>
          <span className="tac-acc-hint mono dim2">click a cell to set the unlock tier · click a name to gate sections</span>
        </div>
        <div className="tacx" style={{ gridTemplateColumns: `minmax(170px,1.4fr) repeat(${tiers.length}, minmax(44px,1fr))` }}>
          <div className="tacx-corner mono">Surface</div>
          {tiers.map(t => {
            const cnt = surfaces.filter(([sk]) => (surf[sk] ?? 0) <= t.id).length;
            return (
              <div key={t.id} className="tacx-th">
                <div className="tacx-th-name mono">{t.name}</div>
                <div className="tacx-th-price mono dim2">{t.price}</div>
                <div className="tacx-th-cnt mono">{cnt}/{surfaces.length}</div>
              </div>
            );
          })}
          {surfaces.map(([k, label]) => {
            const floor = surf[k] ?? 0;
            const groups = window.surfaceSections(k);
            const allPanels = groups.flatMap(g => g.panels);
            const nRaised = allPanels.filter(p => (ST[key(k, p.id)] ?? 0) > floor).length;
            const isOpen = !!open[k];
            return (
              <React.Fragment key={k}>
                <button className={`tacx-name ${isOpen ? "is-open" : ""}`} onClick={() => toggleOpen(k)} title="Gate this surface's sections">
                  <span className={`tac-caret ${isOpen ? "is-open" : ""}`}>▸</span>
                  <span className="tacx-name-l">{label}</span>
                  <span className="tacx-name-meta mono dim2">{allPanels.length}{nRaised > 0 ? ` ↑${nRaised}` : ""}</span>
                </button>
                {tiers.map(t => {
                  const inc = t.id >= floor, isFloor = t.id === floor;
                  return (
                    <button key={t.id} className={`tacx-cell ${inc ? "is-on" : ""} ${isFloor ? "is-floor" : ""}`}
                      onClick={() => setSurf(k, t.id)} title={`${label} · unlocks at ${t.name}`}>
                      {isFloor ? <span className="tacx-dot" /> : inc ? "✓" : ""}
                    </button>
                  );
                })}
                {isOpen && groups.map(g => (
                  <React.Fragment key={g.id}>
                    <div className="tacx-grouprow mono">{g.label}</div>
                    {g.panels.map(p => {
                      const off = !!OFF[key(k, p.id)];
                      const eff = effTier(k, p.id);
                      return (
                        <React.Fragment key={p.id}>
                          <div className={`tacx-secname ${off ? "is-off" : ""}`}>
                            <button className={`tac-onoff ${off ? "" : "is-on"}`} onClick={() => toggleOff(k, p.id)} title={off ? "Disabled — enable" : "Enabled — disable"}><span className="tac-onoff-dot" /></button>
                            <span className="tacx-sec-l">{p.label}</span>
                          </div>
                          {tiers.map(t => {
                            const below = t.id < floor, inc = !off && t.id >= eff, isEff = !off && t.id === eff;
                            return (
                              <button key={t.id} disabled={below} className={`tacx-cell tacx-cell--sm ${inc ? "is-on" : ""} ${isEff ? "is-floor" : ""} ${off ? "is-off" : ""} ${below ? "is-dis" : ""}`}
                                onClick={() => !below && setSec(k, p.id, t.id)} title={below ? `Below surface floor (${tiers[floor].name})` : `${p.label} · ${t.name}`}>
                                {off ? "⊘" : isEff ? <span className="tacx-dot" /> : inc ? "✓" : ""}
                              </button>
                            );
                          })}
                        </React.Fragment>
                      );
                    })}
                  </React.Fragment>
                ))}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* ── Per-ticker lenses (flat) ─────────────────────────────── */}
      <div className="lab-card">
        <div className="lab-card-h mono tac-acc-h">
          <span>PER-TICKER LENSES · {Object.keys(UM_LENS_LABELS).length}</span>
          <span className="tac-acc-hint mono dim2">click a cell to set the unlock tier · click a lens to gate sections</span>
        </div>
        <div className="tacx" style={{ gridTemplateColumns: `minmax(170px,1.4fr) repeat(${tiers.length}, minmax(44px,1fr))` }}>
          <div className="tacx-corner mono">Lens</div>
          {tiers.map(t => { const cnt = Object.keys(UM_LENS_LABELS).filter(lk => (lens[lk] ?? 0) <= t.id).length; return <div key={t.id} className="tacx-th"><div className="tacx-th-name mono">{t.name}</div><div className="tacx-th-price mono dim2">{t.price}</div><div className="tacx-th-cnt mono">{cnt}/{Object.keys(UM_LENS_LABELS).length}</div></div>; })}
          {Object.entries(UM_LENS_LABELS).map(([k, label]) => {
            const floor = lens[k] ?? 0;
            const lk = "lens:" + k;
            const groups = window.lensSections(k);
            const allPanels = groups.flatMap(g => g.panels);
            const nRaised = allPanels.filter(p => (ST[key(lk, p.id)] ?? 0) > floor).length;
            const isOpen = !!open[lk];
            return (
              <React.Fragment key={k}>
                <button className={`tacx-name ${isOpen ? "is-open" : ""}`} onClick={() => toggleOpen(lk)} title="Gate this lens's sections">
                  <span className={`tac-caret ${isOpen ? "is-open" : ""}`}>▸</span>
                  <span className="tacx-name-l">{label}</span>
                  <span className="tacx-name-meta mono dim2">{allPanels.length}{nRaised > 0 ? ` ↑${nRaised}` : ""}</span>
                </button>
                {tiers.map(t => { const inc = t.id >= floor, isFloor = t.id === floor; return (
                  <button key={t.id} className={`tacx-cell ${inc ? "is-on" : ""} ${isFloor ? "is-floor" : ""}`} onClick={() => setLens(k, t.id)} title={`${label} · unlocks at ${t.name}`}>
                    {isFloor ? <span className="tacx-dot" /> : inc ? "✓" : ""}
                  </button>
                ); })}
                {isOpen && groups.map(g => (
                  <React.Fragment key={g.id}>
                    <div className="tacx-grouprow mono">{g.label}</div>
                    {g.panels.map(p => {
                      const off = !!OFF[key(lk, p.id)];
                      const eff = effTier(lk, p.id);
                      return (
                        <React.Fragment key={p.id}>
                          <div className={`tacx-secname ${off ? "is-off" : ""}`}>
                            <button className={`tac-onoff ${off ? "" : "is-on"}`} onClick={() => toggleOff(lk, p.id)} title={off ? "Disabled — enable" : "Enabled — disable"}><span className="tac-onoff-dot" /></button>
                            <span className="tacx-sec-l">{p.label}</span>
                          </div>
                          {tiers.map(t => {
                            const below = t.id < floor, inc = !off && t.id >= eff, isEff = !off && t.id === eff;
                            return (
                              <button key={t.id} disabled={below} className={`tacx-cell tacx-cell--sm ${inc ? "is-on" : ""} ${isEff ? "is-floor" : ""} ${off ? "is-off" : ""} ${below ? "is-dis" : ""}`}
                                onClick={() => !below && setSec(lk, p.id, t.id)} title={below ? `Below lens floor (${tiers[floor].name})` : `${p.label} · ${t.name}`}>
                                {off ? "⊘" : isEff ? <span className="tacx-dot" /> : inc ? "✓" : ""}
                              </button>
                            );
                          })}
                        </React.Fragment>
                      );
                    })}
                  </React.Fragment>
                ))}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <div className="pm-note mono dim2">
        Source of truth: CapStudio RBAC matrix. Edits write the access map that gates the icon-rail, workspace
        routing, the 14-lens tabs, and now every section within a surface. Switch the tier picker (top bar) to
        preview any tier's view — sections above the selected tier blur behind an upgrade prompt.
      </div>
    </div>
  );
}

window.SurfaceUsers = SurfaceUsers;
