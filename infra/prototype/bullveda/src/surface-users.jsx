// surface-users.jsx — Admin · User Management.
// REAL: reads the live auth store (/api/users) + role catalog (/api/roles);
// add / edit / delete / role-change / suspend / reset-password all hit the
// admin-gated backend (auth.py) and persist. No fabricated personas. The
// "Tier Access" tab is an in-session gating PREVIEW (honestly labelled) — it
// is NOT wired to the live RBAC source of truth (data/roles.json +
// data/capability_registry.json), which is role-based, not the prototype's
// T0–T5 tier ladder.

const { useState: useUM, useMemo: useUMm } = React;

// ── real auth API (GET/POST/PATCH/DELETE; same-origin basic auth carries) ──
function umApi(method, path, body) {
  const opts = { method, credentials: "same-origin", headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  return fetch(path, opts).then(async r => {
    if (!r.ok) { const t = await r.text().catch(() => ""); throw new Error(t || (path + " → " + r.status)); }
    const ct = r.headers.get("content-type") || "";
    return ct.includes("json") ? r.json() : r.text();
  });
}

const UM_TAB_PROFILES = ["beginner", "trader", "quant", "all", "custom"];

function useDirectory() {
  const [users, setUsers] = useUM(null);  // null = loading
  const [roles, setRoles] = useUM(null);
  const [err, setErr] = useUM(null);
  const load = React.useCallback(() => {
    Promise.all([
      umApi("GET", "/api/users"),
      umApi("GET", "/api/roles").catch(() => null),
    ]).then(([u, r]) => {
      setUsers((u && u.users) || (Array.isArray(u) ? u : []));
      setRoles(r ? (Array.isArray(r) ? r : (r.roles || [])) : []);
      setErr(null);
    }).catch(e => { setErr(String(e.message || e)); setUsers([]); setRoles([]); });
  }, []);
  React.useEffect(() => { load(); }, [load]);
  return { users, roles, err, reload: load };
}

function umRoleMeta(roles, id) { return (roles || []).find(r => r.id === id) || { id, name: id, color: "" }; }
function umRoleTone(color) {
  const m = { fail: "rd", danger: "rd", error: "rd", warn: "amb", warning: "amb", ok: "gn", success: "gn", good: "gn", info: "cy", accent: "copper", brand: "copper", muted: "ink" };
  return m[(color || "").toLowerCase()] || "copper";
}
function umRelTime(iso) {
  if (!iso) return "never";
  const t = Date.parse(iso); if (!Number.isFinite(t)) return "—";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return "just now";
  const mn = s / 60; if (mn < 60) return Math.round(mn) + "m ago";
  const h = mn / 60; if (h < 24) return Math.round(h) + "h ago";
  const d = h / 24; if (d < 30) return Math.round(d) + "d ago";
  return new Date(t).toISOString().slice(0, 10);
}
function umStatus(u) {
  if (u.disabled) return { label: "suspended", cls: "suspended" };
  if (!u.last_login && u.must_change_password) return { label: "invited", cls: "trial" };
  if (u.must_change_password) return { label: "pending pw", cls: "trial" };
  if (!u.last_login) return { label: "never signed in", cls: "trial" };
  return { label: "active", cls: "active" };
}
function umInitials(u) {
  const base = (u.display_name || u.username || "?").trim();
  const parts = base.split(/[\s._-]+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : base.slice(0, 2)).toUpperCase();
}

function SurfaceUsers() {
  const [view, setView] = useUM("users");
  const dir = useDirectory();
  const [q, setQ] = useUM("");
  const [fRole, setFRole] = useUM("all");
  const [editing, setEditing] = useUM(null);
  const [busy, setBusy] = useUM(null);    // username currently mutating
  const [toast, setToast] = useUM(null);  // {msg, bad}

  const users = dir.users, roles = dir.roles || [];
  const flash = (msg, bad) => { setToast({ msg, bad }); window.setTimeout(() => setToast(null), 3400); };

  // effective role list for selects: catalog if present, else derive from users
  const roleOpts = useUMm(() => {
    if (roles.length) return roles.map(r => ({ id: r.id, name: r.name || r.id, color: r.color }));
    const seen = {}; (users || []).forEach(u => { if (u.role) seen[u.role] = 1; });
    ["admin", "trader", "viewer", "free"].forEach(r => seen[r] = 1);
    return Object.keys(seen).map(id => ({ id, name: id, color: "" }));
  }, [roles, users]);

  const rows = useUMm(() => {
    let r = (users || []).map((u, i) => ({ ...u, _i: i }));
    if (q.trim()) { const s = q.toLowerCase(); r = r.filter(u => ((u.display_name || "") + (u.username || "") + (u.email || "")).toLowerCase().includes(s)); }
    if (fRole !== "all") r = r.filter(u => u.role === fRole);
    return r;
  }, [users, q, fRole]);

  const roleCounts = useUMm(() => {
    const c = {}; (users || []).forEach(u => { c[u.role] = (c[u.role] || 0) + 1; });
    return Object.keys(c).sort((a, b) => c[b] - c[a]).map(id => ({ id, n: c[id], meta: umRoleMeta(roles, id) }));
  }, [users, roles]);

  const patchUser = (username, fields, okMsg) => {
    setBusy(username);
    umApi("PATCH", "/api/users/" + encodeURIComponent(username), fields)
      .then(() => { dir.reload(); flash(okMsg || ("Updated " + username)); })
      .catch(e => flash(String(e.message || e), true))
      .finally(() => setBusy(null));
  };
  const setRole = (u, role) => {
    if (role === u.role) return;
    const fields = { role };
    if (u.is_owner && u.role === "admin" && role !== "admin") fields.__confirm_owner_demote__ = true;
    patchUser(u.username, fields, "Role → " + role + " for " + u.username);
  };
  const toggleDisabled = (u) => patchUser(u.username, { disabled: !u.disabled }, (!u.disabled ? "Suspended " : "Reactivated ") + u.username);

  const saveUser = (payload, isNew) =>
    (isNew ? umApi("POST", "/api/users", payload)
           : umApi("PATCH", "/api/users/" + encodeURIComponent(payload.username), payload.fields))
      .then(() => { dir.reload(); setEditing(null); flash(isNew ? "Created " + payload.username : "Saved " + payload.username); });
  const deleteUser = (u) =>
    umApi("DELETE", "/api/users/" + encodeURIComponent(u.username))
      .then(() => { dir.reload(); setEditing(null); flash("Deleted " + u.username); })
      .catch(e => flash(String(e.message || e), true));
  const resetPw = (u, pw) =>
    umApi("POST", "/api/users/" + encodeURIComponent(u.username) + "/reset-password", { new_password: pw })
      .then(() => flash("Password reset for " + u.username));

  const openNew = () => setEditing({ __new__: true, username: "", display_name: "", email: "", role: "viewer", tab_profile: "trader", disabled: false, must_change_password: true });
  const openEdit = (u) => setEditing({ ...u });

  const loading = users === null;

  return (
    <div className="surface wsx wsx--amb um">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">ADMIN · USER MANAGEMENT · RBAC</div>
          <h1 className="wsx-title mono">User Management</h1>
          <div className="wsx-sub mono dim2">live auth store · add &amp; edit users · assign roles · preview tier gating</div>
        </div>
        <div className="wsx-hdr-r">
          {view === "users" && <button className="btn btn--primary btn--sm" onClick={openNew} disabled={loading || dir.err}>＋ Add user</button>}
          <FreshnessPill state={dir.err ? "stale" : "live"} age={dir.err ? "auth" : (users ? users.length + " users" : "…")} />
        </div>
      </div>

      <div className="um-viewtabs">
        <button className={`um-vt ${view==="users"?"is-on":""}`} onClick={()=>setView("users")}>Users &amp; Roles</button>
        <button className={`um-vt ${view==="access"?"is-on":""}`} onClick={()=>setView("access")}>Tier Access · Preview</button>
      </div>

      {view === "users" ? (
        dir.err ? (
          <div className="wsx-body"><div className="pm-note mono dim2" style={{ padding: 18 }}>
            Couldn’t load the user directory — <b className="warn">{dir.err}</b>.
            This surface needs an <b>admin</b> session (the live <code>/api/users</code> endpoint is admin-gated). Sign in as an admin account to manage users.
          </div></div>
        ) : loading ? (
          <div className="wsx-body"><div className="smc-empty mono dim2" style={{ padding: 18 }}>Loading user directory from <b className="copper">/api/users</b>…</div></div>
        ) : (
        <>
          <div className="um-tiers">
            {roleCounts.map(t => (
              <button key={t.id} className={`um-tier ${fRole===t.id?"is-on":""}`} onClick={()=>setFRole(fRole===t.id?"all":t.id)}
                style={{ borderColor: fRole===t.id ? `var(--${umRoleTone(t.meta.color)})` : undefined }}>
                <div className="um-tier-n mono">{t.n}</div>
                <div className="um-tier-l mono">{t.meta.name || t.id}</div>
                <div className="um-tier-p mono dim2">role</div>
              </button>
            ))}
          </div>

          <div className="lab-tabs">
            <button className={`lab-tab ${fRole==="all"?"is-on":""}`} onClick={()=>setFRole("all")}>All users · {users.length}</button>
            <input className="nw-search mono" placeholder="⌕ name, username or email…" value={q} onChange={e=>setQ(e.target.value)} style={{marginLeft:"auto"}} />
          </div>

          <div className="wsx-body">
            <table className="dtable wsx-tbl um-tbl">
              <thead><tr>
                <th>User</th><th>Email</th><th>Status</th><th>Profile</th><th>Last login</th><th>Role · assign</th><th></th>
              </tr></thead>
              <tbody>{rows.map(u=>{
                const st = umStatus(u);
                const isBusy = busy === u.username;
                return (
                <tr key={u.username} className={isBusy ? "is-busy" : ""}>
                  <td><div className="um-user">
                    <span className="um-avatar">{umInitials(u)}</span>
                    <div style={{display:"flex",flexDirection:"column",lineHeight:1.2}}>
                      <b>{u.display_name || u.username}{u.is_owner && <span className="amb mono" style={{fontSize:10,marginLeft:6}}>★ OWNER</span>}</b>
                      <span className="mono dim2" style={{fontSize:11}}>@{u.username}</span>
                    </div>
                  </div></td>
                  <td className="dim2">{u.email || <span className="dim">—</span>}</td>
                  <td><span className={`um-status um-status--${st.cls}`}>{st.label}</span></td>
                  <td className="mono dim2">{u.tab_profile || "—"}</td>
                  <td className="dim2">{umRelTime(u.last_login)}</td>
                  <td>
                    <select className="um-sel" value={u.role} disabled={isBusy} onChange={e=>setRole(u, e.target.value)}
                      title={u.is_owner ? "Owner — demoting requires confirmation" : `Assign role`}>
                      {roleOpts.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                  </td>
                  <td style={{whiteSpace:"nowrap"}}>
                    <button className="um-edit" onClick={()=>toggleDisabled(u)} disabled={isBusy || u.is_owner}
                      title={u.is_owner ? "Owner can’t be suspended" : (u.disabled ? "Reactivate" : "Suspend")}>{u.disabled ? "⏼" : "⏸"}</button>
                    <button className="um-edit" onClick={()=>openEdit(u)} title="Edit user" style={{marginLeft:4}}>✎</button>
                  </td>
                </tr>
              );})}</tbody>
            </table>
          </div>

          <div className="pm-note mono dim2">
            Changes persist to the live auth store (<code>auth.py</code>) and take effect on the user’s next request. The <b>owner</b> account can’t be suspended or silently demoted from admin. New users start with <b>must-change-password</b>. All mutations are admin-gated and recorded in the audit log (<code>/api/audit_log</code>).
          </div>
        </>
        )
      ) : (
        <TierAccessConfig tiers={window.TIER_LIST || []} />
      )}

      {toast && <div className={`um-toast ${toast.bad ? "is-bad" : "is-ok"} mono`} style={{
        position:"fixed", right:18, bottom:18, zIndex:9999, padding:"10px 14px", borderRadius:8,
        background: toast.bad ? "var(--rd-bg, #2a1414)" : "var(--gn-bg, #122017)",
        border:`1px solid var(--${toast.bad ? "rd" : "gn"})`, color:`var(--${toast.bad ? "rd" : "gn"})`, fontSize:12, maxWidth:360 }}>
        {toast.bad ? "✕ " : "✓ "}{toast.msg}
      </div>}

      {editing && (
        <UserEditModal user={editing} roleOpts={roleOpts} onSave={saveUser} onDelete={deleteUser} onReset={resetPw} onClose={()=>setEditing(null)} />
      )}
    </div>
  );
}

function UserEditModal({ user, roleOpts, onSave, onDelete, onReset, onClose }) {
  const isNew = !!user.__new__;
  const [u, setU] = useUM(() => ({
    username: user.username || "", display_name: user.display_name || "", email: user.email || "",
    role: user.role || "viewer", tab_profile: user.tab_profile || "trader",
    disabled: !!user.disabled, must_change_password: !!user.must_change_password, password: "",
  }));
  const [pw2, setPw2] = useUM("");
  const [err, setErr] = useUM(null);
  const [saving, setSaving] = useUM(false);
  const set = (k, v) => setU(x => ({ ...x, [k]: v }));

  const emailOk = !u.email || /\S+@\S+\.\S+/.test(u.email);
  const unameOk = !isNew || /^[a-z0-9_.-]{2,}$/.test(u.username.toLowerCase());
  const pwOk = !isNew || u.password.length >= 8;
  const valid = u.display_name.trim() && emailOk && unameOk && pwOk && u.role;

  const submit = () => {
    setErr(null); setSaving(true);
    const done = () => setSaving(false);
    if (isNew) {
      onSave({ username: u.username.toLowerCase().trim(), password: u.password, role: u.role,
        display_name: u.display_name.trim(), email: u.email.trim(), disabled: u.disabled, tab_profile: u.tab_profile }, true)
        .catch(e => setErr(String(e.message || e))).finally(done);
    } else {
      const fields = { display_name: u.display_name.trim(), email: u.email.trim(), role: u.role,
        tab_profile: u.tab_profile, disabled: u.disabled, must_change_password: u.must_change_password };
      if (user.is_owner && user.role === "admin" && u.role !== "admin") fields.__confirm_owner_demote__ = true;
      onSave({ username: user.username, fields }, false)
        .catch(e => setErr(String(e.message || e))).finally(done);
    }
  };
  const doReset = () => {
    setErr(null);
    if (pw2.length < 8) { setErr("New password must be ≥ 8 characters"); return; }
    onReset(user, pw2).then(() => { setPw2(""); }).catch(e => setErr(String(e.message || e)));
  };

  return ReactDOM.createPortal((
    <div className="um-modal-bg" onMouseDown={onClose}>
      <div className="um-modal" onMouseDown={e=>e.stopPropagation()}>
        <div className="um-modal-h">
          <span className="mono">{isNew ? "ADD USER" : "EDIT USER · @" + user.username}{user.is_owner ? " · ★ OWNER" : ""}</span>
          <button className="um-modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="um-modal-body">
          {isNew && <label className="um-field"><span className="mono dim2">Username <b className="amb">· permanent</b></span>
            <input className="um-input mono" value={u.username} onChange={e=>set("username", e.target.value.toLowerCase())} placeholder="jdoe" /></label>}
          <label className="um-field"><span className="mono dim2">Display name</span>
            <input className="um-input" value={u.display_name} onChange={e=>set("display_name", e.target.value)} placeholder="Jane Trader" /></label>
          <label className="um-field"><span className="mono dim2">Email</span>
            <input className="um-input" value={u.email} onChange={e=>set("email", e.target.value)} placeholder="jane@fund.com" /></label>
          <div className="um-field-row">
            <label className="um-field"><span className="mono dim2">Role</span>
              <select className="um-input" value={u.role} onChange={e=>set("role", e.target.value)}>
                {roleOpts.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select></label>
            <label className="um-field"><span className="mono dim2">Tab profile</span>
              <select className="um-input" value={u.tab_profile} onChange={e=>set("tab_profile", e.target.value)}>
                {UM_TAB_PROFILES.map(p => <option key={p} value={p}>{p}</option>)}
              </select></label>
          </div>
          {isNew && <label className="um-field"><span className="mono dim2">Temporary password <b className="dim">· ≥ 8 chars · user must change on first login</b></span>
            <input className="um-input mono" type="text" value={u.password} onChange={e=>set("password", e.target.value)} placeholder="set a temp password" /></label>}
          <label className="um-toggle"><input type="checkbox" checked={u.disabled} disabled={user.is_owner} onChange={e=>set("disabled", e.target.checked)} /><span className="mono">Suspended {user.is_owner && <b className="dim">· owner can’t be suspended</b>}</span></label>
          {!isNew && <label className="um-toggle"><input type="checkbox" checked={u.must_change_password} onChange={e=>set("must_change_password", e.target.checked)} /><span className="mono">Force password change on next login</span></label>}

          {!isNew && (
            <div className="um-field" style={{marginTop:10, paddingTop:10, borderTop:"1px solid var(--line)"}}>
              <span className="mono dim2">Reset password (admin)</span>
              <div style={{display:"flex", gap:6}}>
                <input className="um-input mono" type="text" value={pw2} onChange={e=>setPw2(e.target.value)} placeholder="new password ≥ 8 chars" style={{flex:1}} />
                <button className="btn btn--sm" onClick={doReset} disabled={pw2.length<8}>Reset</button>
              </div>
            </div>
          )}

          {err && <div className="mono" style={{color:"var(--rd)", fontSize:12, marginTop:8}}>✕ {err}</div>}
        </div>
        <div className="um-modal-foot">
          {!isNew && !user.is_owner && <button className="btn btn--sm um-del" onClick={()=>{ if (window.confirm("Delete @"+user.username+"? This removes their login permanently.")) onDelete(user); }}>🗑 Delete</button>}
          <div style={{marginLeft:"auto", display:"flex", gap:6}}>
            <button className="btn btn--sm" onClick={onClose}>Cancel</button>
            <button className="btn btn--primary btn--sm" disabled={!valid || saving} onClick={()=>valid && submit()}>{saving ? "Saving…" : isNew ? "Create user" : "Save changes"}</button>
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
      <div className="pm-note mono" style={{ marginBottom: 10, borderColor: "var(--amb)", color: "var(--amb)" }}>
        ⚠ <b>Session preview only.</b> This matrix gates the surfaces/lenses in <b>your current browser session</b> so you can see how each tier’s view looks. It is <b>not</b> persisted and does <b>not</b> write to the live RBAC source of truth (<code>data/roles.json</code> + <code>data/capability_registry.json</code>), which is <b>role</b>-based, not this T0–T5 tier ladder. Reloading resets it.
      </div>
      <div className="tac-legend mono dim2">
        <b>Tier access matrix</b> — columns are tiers, rows are features. Click a cell to set the tier that <b>unlocks</b> a surface; click a surface name to gate its individual sections. Changes apply to this session only.
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
        Preview tool: edits set an in-session access map over the icon-rail, workspace routing, the 14-lens tabs,
        and every section within a surface. Switch the tier picker (top bar) to preview any tier’s view — sections
        above the selected tier blur behind an upgrade prompt. To change what users <i>actually</i> get, edit their
        <b> role</b> on the Users tab (live <code>auth.py</code>); the real per-role capability map lives in CapStudio
        (<code>data/capability_registry.json</code>).
      </div>
    </div>
  );
}

window.SurfaceUsers = SurfaceUsers;
