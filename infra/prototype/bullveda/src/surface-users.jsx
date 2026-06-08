// surface-users.jsx — Admin · User Management.
// REAL on both tabs:
//  • Users & Roles — reads the live auth store (/api/users) + role catalog
//    (/api/roles); add / edit / delete / role-change / suspend / reset-password
//    all hit the admin-gated backend (auth.py) and persist. No fabricated personas.
//  • Role Access · Live RBAC — a real enable/disable matrix over every gateable
//    capability in data/capability_registry.json (tabs + sub-tabs/sections +
//    actions) × every role; each toggle PATCHes /api/roles/{id}, persists to
//    data/roles.json and is audit-logged. Same source of truth CapStudio edits.

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
          <div className="wsx-sub mono dim2">live auth store · add &amp; edit users · assign roles · gate every capability per role</div>
        </div>
        <div className="wsx-hdr-r">
          {view === "users" && <button className="btn btn--primary btn--sm" onClick={openNew} disabled={loading || dir.err}>＋ Add user</button>}
          <FreshnessPill state={dir.err ? "stale" : "live"} age={dir.err ? "auth" : (users ? users.length + " users" : "…")} />
        </div>
      </div>

      <div className="um-viewtabs">
        <button className={`um-vt ${view==="users"?"is-on":""}`} onClick={()=>setView("users")}>Users &amp; Roles</button>
        <button className={`um-vt ${view==="access"?"is-on":""}`} onClick={()=>setView("access")}>Role Access · Live RBAC</button>
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
        <RoleAccessConfig />
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

// ─── Role Access · LIVE RBAC ───────────────────────────────────────────────
// Real, persisted enable/disable matrix over EVERY gateable capability:
//   rows  = capability_registry.json  (tabs + sub-tabs/sections + actions),
//           grouped exactly as the registry groups them
//   cols  = real roles from /api/roles
//   cell  = is this capability granted to this role? click to toggle
// Each toggle PATCHes /api/roles/{role_id} with the full permissions object →
// persists to data/roles.json and is audit-logged (admin-only). This is the
// SAME source of truth CapStudio edits — no preview, no in-memory mock.

function useRbac() {
  const [reg, setReg] = useUM(null);     // {tabs, sub_tabs, actions, groups}
  const [roles, setRoles] = useUM(null); // [{id,name,color,permissions:{tabs,sub_tabs,actions}}]
  const [err, setErr] = useUM(null);
  const load = React.useCallback(() => {
    Promise.all([
      umApi("GET", "/api/capability-registry"),
      umApi("GET", "/api/roles"),
    ]).then(([rg, rl]) => {
      setReg(rg && rg.tabs ? rg : { tabs: {}, sub_tabs: {}, actions: {}, groups: [] });
      setRoles((rl && rl.roles) || (Array.isArray(rl) ? rl : []));
      setErr(null);
    }).catch(e => { setErr(String(e.message || e)); setReg({ tabs: {}, sub_tabs: {}, actions: {}, groups: [] }); setRoles([]); });
  }, []);
  React.useEffect(() => { load(); }, [load]);
  return { reg, roles, err, setRoles, reload: load };
}

function rbacPerm(role, kind) { return (role && role.permissions && role.permissions[kind]) || []; }
function rbacWild(role, kind) { return rbacPerm(role, kind).indexOf("*") >= 0; }
function rbacGranted(role, kind, id) { const l = rbacPerm(role, kind); return l.indexOf("*") >= 0 || l.indexOf(id) >= 0; }

function RoleAccessConfig() {
  const { reg, roles, err, setRoles, reload } = useRbac();
  const [busy, setBusy] = useUM(null);     // "role:kind:id" mutating
  const [toast, setToast] = useUM(null);
  const [open, setOpen] = useUM(() => ({ main_tabs: true }));
  const [hideEmpty, setHideEmpty] = useUM(false);
  const flash = (msg, bad) => { setToast({ msg, bad }); window.setTimeout(() => setToast(null), 3200); };

  if (err) {
    return <div className="tac"><div className="pm-note mono dim2" style={{ padding: 18 }}>
      Couldn’t load the capability registry / roles — <b className="warn">{err}</b>.
      This needs an <b>admin</b> session (the role-write endpoints are admin-gated).
    </div></div>;
  }
  if (!reg || !roles) {
    return <div className="tac"><div className="smc-empty mono dim2" style={{ padding: 18 }}>Loading live RBAC from <b className="copper">/api/capability-registry</b> + <b className="copper">/api/roles</b>…</div></div>;
  }

  // build grouped rows straight from the registry groups
  const groups = (reg.groups || []).map(g => {
    const kind = g.perm_type;                  // tabs | sub_tabs | actions
    const catalog = reg[kind] || {};
    const items = Object.keys(catalog)
      .filter(id => (catalog[id].group || "") === g.id)
      .map(id => ({ id, kind, label: catalog[id].label || id, meta: catalog[id] }))
      .sort((a, b) => a.label.localeCompare(b.label));
    return { id: g.id, label: g.label || g.id, kind, desc: g.description || "", items };
  }).filter(g => g.items.length);

  // any registry entries whose group isn't declared → catch-all bucket
  ["tabs", "sub_tabs", "actions"].forEach(kind => {
    const declared = new Set(groups.filter(g => g.kind === kind).flatMap(g => g.items.map(i => i.id)));
    const orphans = Object.keys(reg[kind] || {}).filter(id => !declared.has(id))
      .map(id => ({ id, kind, label: (reg[kind][id].label || id), meta: reg[kind][id] }));
    if (orphans.length) groups.push({ id: "_orphan_" + kind, label: "Other · " + kind, kind, desc: "", items: orphans });
  });

  const toggle = (role, kind, id) => {
    if (rbacWild(role, kind)) { flash(`${role.id} has ALL ${kind} (·*·) — edit the wildcard in roles.json to gate individually`, true); return; }
    const cur = rbacPerm(role, kind).slice();
    const at = cur.indexOf(id);
    const nowOn = at < 0;
    if (at < 0) cur.push(id); else cur.splice(at, 1);
    const perms = Object.assign({ tabs: [], sub_tabs: [], actions: [] }, role.permissions || {});
    perms[kind] = cur;
    const bkey = role.id + ":" + kind + ":" + id;
    setBusy(bkey);
    setRoles(rs => rs.map(r => r.id === role.id ? Object.assign({}, r, { permissions: perms }) : r)); // optimistic
    umApi("PATCH", "/api/roles/" + encodeURIComponent(role.id), { permissions: perms })
      .then(() => flash(`${nowOn ? "Enabled" : "Disabled"} ${id} · ${role.name || role.id}`))
      .catch(e => { flash(String(e.message || e), true); reload(); })
      .finally(() => setBusy(null));
  };

  const cols = roles;
  const gridCols = `minmax(220px,1.7fr) repeat(${cols.length}, minmax(56px,1fr))`;
  const totalCaps = (reg.tabs ? Object.keys(reg.tabs).length : 0) + (reg.sub_tabs ? Object.keys(reg.sub_tabs).length : 0) + (reg.actions ? Object.keys(reg.actions).length : 0);

  return (
    <div className="tac">
      <div className="pm-note mono" style={{ marginBottom: 10, borderColor: "var(--gn)", color: "var(--gn)" }}>
        ✓ <b>Live RBAC.</b> Every toggle PATCHes the role’s permissions to <code>data/roles.json</code> and is admin-audit-logged — the same capability map CapStudio edits. {totalCaps} gateable capabilities × {cols.length} roles. Wildcard (<code>*</code>) roles are shown all-on and locked (edit the wildcard in <code>roles.json</code> to gate one-by-one).
      </div>
      <div className="lab-tabs" style={{ marginBottom: 8 }}>
        <span className="mono dim2">Click a cell to grant / revoke. Click a group to collapse.</span>
        <label className="mono dim2" style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={hideEmpty} onChange={e => setHideEmpty(e.target.checked)} /> hide rows nobody has
        </label>
      </div>

      <div className="lab-card">
        <div className="tacx" style={{ gridTemplateColumns: gridCols }}>
          <div className="tacx-corner mono">Capability</div>
          {cols.map(r => {
            const gT = rbacWild(r, "tabs") ? "∗" : rbacPerm(r, "tabs").length;
            return (
              <div key={r.id} className="tacx-th" title={r.description || r.id}>
                <div className="tacx-th-name mono" style={{ color: `var(--${umRoleTone(r.color)})` }}>{r.name || r.id}</div>
                <div className="tacx-th-price mono dim2">{r.id}</div>
                <div className="tacx-th-cnt mono">{gT}<span className="dim2">t</span></div>
              </div>
            );
          })}

          {groups.map(g => {
            const isOpen = open[g.id] !== false;
            return (
              <React.Fragment key={g.id}>
                <button className={`tacx-name is-grouphead ${isOpen ? "is-open" : ""}`} style={{ gridColumn: `1 / -1`, textAlign: "left" }}
                  onClick={() => setOpen(o => Object.assign({}, o, { [g.id]: o[g.id] === false }))}>
                  <span className={`tac-caret ${isOpen ? "is-open" : ""}`}>▸</span>
                  <span className="tacx-name-l"><b>{g.label}</b></span>
                  <span className="tacx-name-meta mono dim2">{g.items.length} · {g.kind}</span>
                </button>
                {isOpen && g.items.map(it => {
                  const anyHas = cols.some(r => rbacGranted(r, it.kind, it.id));
                  if (hideEmpty && !anyHas) return null;
                  return (
                    <React.Fragment key={g.id + "/" + it.id}>
                      <div className="tacx-secname" title={it.id}>
                        <span className="tacx-sec-l">{it.label}</span>
                        <span className="mono dim2" style={{ fontSize: 10, marginLeft: 6 }}>{it.id}</span>
                      </div>
                      {cols.map(r => {
                        const on = rbacGranted(r, it.kind, it.id);
                        const wild = rbacWild(r, it.kind);
                        const bkey = r.id + ":" + it.kind + ":" + it.id;
                        const isBusy = busy === bkey;
                        return (
                          <button key={r.id} disabled={isBusy}
                            className={`tacx-cell ${on ? "is-on" : ""} ${wild ? "is-floor" : ""} ${isBusy ? "is-busy" : ""}`}
                            onClick={() => toggle(r, it.kind, it.id)}
                            title={wild ? `${r.name} = ALL ${it.kind} (wildcard, locked)` : `${on ? "Revoke" : "Grant"} ${it.label} · ${r.name || r.id}`}>
                            {wild ? "∗" : on ? "✓" : ""}
                          </button>
                        );
                      })}
                    </React.Fragment>
                  );
                })}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <div className="pm-note mono dim2">
        Source of truth: <code>data/roles.json</code> (per-role grants) over <code>data/capability_registry.json</code> (the catalog of {totalCaps} gateable functions). Each user’s <b>role</b> (Users tab) resolves to these grants. Changes are admin-gated, persisted, and recorded in the audit log (<code>capstudio_edit_role</code>). To add a brand-new gateable capability, add it to the registry first (CapStudio / <code>/api/capability-registry</code>).
      </div>

      {toast && <div className={`um-toast ${toast.bad ? "is-bad" : "is-ok"} mono`} style={{
        position: "fixed", right: 18, bottom: 18, zIndex: 9999, padding: "10px 14px", borderRadius: 8,
        background: toast.bad ? "var(--rd-bg, #2a1414)" : "var(--gn-bg, #122017)",
        border: `1px solid var(--${toast.bad ? "rd" : "gn"})`, color: `var(--${toast.bad ? "rd" : "gn"})`, fontSize: 12, maxWidth: 380 }}>
        {toast.bad ? "✕ " : "✓ "}{toast.msg}
      </div>}
    </div>
  );
}


window.SurfaceUsers = SurfaceUsers;
