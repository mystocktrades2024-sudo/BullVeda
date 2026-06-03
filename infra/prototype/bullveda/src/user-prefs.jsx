// user-prefs.jsx — central per-user preference store with optional Supabase
// cross-device sync. Plain JS (no React dependency) so every store can use it.
//
//   window.UserPrefs.get(key, fallback)      → read (sync, from local cache)
//   window.UserPrefs.set(key, value)         → write (local + queued remote push)
//   window.UserPrefs.subscribe(key, cb)      → react to remote/cross-device changes
//   window.UserPrefs.setUser(id)             → switch the active user (auth hook)
//   window.UserPrefs.connectSupabase(cfg)    → enable cross-device sync (mode B)
//
// Persistence model:
//   • Always caches to localStorage, NAMESPACED BY USER → instant load + offline.
//   • When Supabase is connected, the cache is reconciled with the remote
//     `user_preferences` table on load, every set() is upserted (debounced),
//     and realtime postgres_changes push other devices' edits back into the UI.
//   • With no backend configured it still works — just per-user on this device.

(function () {
  const CACHE_PREFIX = "kairos.pref";
  let userId = resolveUser();
  const listeners = {};        // key -> Set(callback)
  let remote = null;           // backend adapter, or null (local-only)
  const pending = {};          // debounced push queue: key -> value
  let flushTimer = null;

  function resolveUser() {
    try {
      if (window.KairosUser && window.KairosUser.id) return String(window.KairosUser.id);
      const saved = localStorage.getItem("kairos.uid");
      if (saved) return saved;
    } catch (e) {}
    return "local";
  }

  const ck = (key) => `${CACHE_PREFIX}.${userId}.${key}`;
  function readCache(key, fb) {
    try { const v = localStorage.getItem(ck(key)); return v == null ? fb : JSON.parse(v); }
    catch (e) { return fb; }
  }
  function writeCache(key, val) {
    try { localStorage.setItem(ck(key), JSON.stringify(val)); } catch (e) {}
  }
  function emit(key, val) {
    (listeners[key] || []).forEach(cb => { try { cb(val, key); } catch (e) {} });
  }

  const UserPrefs = {
    userId: () => userId,
    isSynced: () => !!remote,

    setUser(id) {
      id = id ? String(id) : "local";
      if (id === userId) return;
      userId = id;
      try { localStorage.setItem("kairos.uid", id); } catch (e) {}
      if (remote) remote.pullAll();
      // re-broadcast this user's cached values so stores re-hydrate
      Object.keys(listeners).forEach(k => emit(k, readCache(k)));
      window.dispatchEvent(new CustomEvent("userprefs-user", { detail: { userId } }));
    },

    get(key, fb) { const v = readCache(key, undefined); return v === undefined ? fb : v; },

    set(key, val) {
      writeCache(key, val);
      emit(key, val);
      if (remote) queuePush(key, val);
    },

    subscribe(key, cb) {
      (listeners[key] = listeners[key] || new Set()).add(cb);
      return () => { if (listeners[key]) listeners[key].delete(cb); };
    },

    connectSupabase(config) { connectSupabase(config); },
  };

  function queuePush(key, val) {
    pending[key] = val;
    if (flushTimer) return;
    flushTimer = setTimeout(() => {
      const batch = {};
      Object.keys(pending).forEach(k => { batch[k] = pending[k]; delete pending[k]; });
      flushTimer = null;
      if (remote) remote.push(batch);
    }, 600);
  }

  // ── Supabase adapter (lazy-loaded) ───────────────────────────────
  function connectSupabase(config) {
    if (!config || !config.url || !config.anonKey) {
      console.warn("[UserPrefs] Supabase config needs { url, anonKey }");
      return;
    }
    const table = config.table || "user_preferences";
    loadScript("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js")
      .then(() => {
        const sb = window.supabase.createClient(config.url, config.anonKey);

        // bind the active user to the authenticated session
        sb.auth.getUser().then(({ data }) => { if (data && data.user) UserPrefs.setUser(data.user.id); }).catch(() => {});
        sb.auth.onAuthStateChange((_evt, session) => { if (session && session.user) UserPrefs.setUser(session.user.id); });

        remote = {
          async pullAll() {
            try {
              const { data, error } = await sb.from(table).select("pref_key,value").eq("user_id", userId);
              if (error) { console.warn("[UserPrefs] pull:", error.message); return; }
              (data || []).forEach(row => { writeCache(row.pref_key, row.value); emit(row.pref_key, row.value); });
            } catch (e) { console.warn("[UserPrefs] pull failed", e); }
          },
          async push(batch) {
            const rows = Object.keys(batch).map(k => ({
              user_id: userId, pref_key: k, value: batch[k], updated_at: new Date().toISOString(),
            }));
            try {
              const { error } = await sb.from(table).upsert(rows, { onConflict: "user_id,pref_key" });
              if (error) console.warn("[UserPrefs] push:", error.message);
            } catch (e) { console.warn("[UserPrefs] push failed", e); }
          },
        };

        // realtime — other devices' edits flow back into this session
        try {
          sb.channel("userprefs-" + userId)
            .on("postgres_changes", { event: "*", schema: "public", table, filter: `user_id=eq.${userId}` }, (payload) => {
              const row = payload.new;
              if (row && row.pref_key) { writeCache(row.pref_key, row.value); emit(row.pref_key, row.value); }
            })
            .subscribe();
        } catch (e) {}

        remote.pullAll();
        window.dispatchEvent(new CustomEvent("userprefs-synced", { detail: { userId } }));
        console.info("[UserPrefs] Supabase cross-device sync enabled · user", userId);
      })
      .catch(e => console.warn("[UserPrefs] supabase-js failed to load — staying local-only", e));
  }

  function loadScript(src) {
    return new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }

  // auto-connect if credentials were provided before this script ran
  if (window.SUPABASE_CONFIG) connectSupabase(window.SUPABASE_CONFIG);

  window.UserPrefs = UserPrefs;
})();
