/* mrbullalgo-override.js — MrBullAlgo adapter shim.
 *
 * MrBullAlgo = BullVeda's UI + MrAlgo's decision core. Render-blocking <head>
 * script injected ONLY on /MRBULLALGO (BullVeda itself never loads it). Runs
 * BEFORE the inlined bullveda-boot adapter, so it can wrap the network layer and
 * re-route the decision contracts to MrAlgo's engine; ML / options / earnings /
 * crypto pass through to SwingTrade unchanged.
 *
 * PHASE 1: reroute the combined boot payload's universe -> MrAlgo. BullVeda pulls
 * the whole universe inside /api/bullveda-boot (BOOT.universe.screener); we rewrite
 * that request to /api/mrbull/boot, which returns the same payload with the
 * screener swapped for MrAlgo-mapped rows (Tech+Fund verdict, @Buy zone ->
 * entry_quality, score, structural targets). Everything else is untouched.
 */
(function () {
  "use strict";
  window.__MRBULLALGO__ = true;
  window.__MRBULLALGO_PHASE__ = 3;

  // ── network shim: rewrite the boot endpoint to the MrAlgo-backed one ──
  // "/api/bullveda-boot" -> "/api/mrbull/boot"  (does NOT touch "/api/bullveda-heavy")
  function remap(url) {
    if (typeof url !== "string") return url;
    // Phase 1: universe (inside the combined boot)
    if (url.indexOf("/api/bullveda-boot") !== -1) {
      return url.replace("/api/bullveda-boot", "/api/mrbull/boot");
    }
    // Phase 2: per-mode trade plan (Overview hero) -> MrAlgo structural/PAC targets
    if (url.indexOf("/api/trade_engine") !== -1) {
      return url.replace("/api/trade_engine", "/api/mrbull/trade_engine");
    }
    return url;
  }

  try {
    var _open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      var args = Array.prototype.slice.call(arguments);
      var nu = remap(url);
      if (nu !== url) { try { console.log("[MrBullAlgo] XHR ->", nu); } catch (e) {} }
      args[1] = nu;
      return _open.apply(this, args);
    };
  } catch (e) {}

  try {
    var _fetch = window.fetch;
    if (_fetch) {
      window.fetch = function (input, init) {
        try {
          if (typeof input === "string") input = remap(input);
          else if (input && input.url) {
            var nu = remap(input.url);
            if (nu !== input.url) input = new Request(nu, input);
          }
        } catch (e) {}
        return _fetch.call(this, input, init);
      };
    }
  } catch (e) {}

  try { console.log("[MrBullAlgo] override loaded · phase 1 (universe -> MrAlgo)"); } catch (e) {}

  // ── MrAlgo-native surfaces (Research / ETF / PAC chart) as injected tabs ──
  // BullVeda's bundle can't be rebuilt here, so we mount these OUTSIDE React (on
  // document.body) and iframe the already-built MrAlgo views (/MRALGO?...&embed=1).
  function currentTicker() {
    try {
      var m = (document.body.innerText || "").match(/\bHome\s*\/\s*([A-Z]{1,5})\b/);
      return m ? m[1] : "";
    } catch (e) { return ""; }
  }
  function setupMrBullTabs() {
    if (document.getElementById("mrbull-launcher")) return;
    var TABS = [
      { id: "research", label: "📚 Research", url: function () { return "/MRALGO?view=research&embed=1"; } },
      { id: "etf", label: "📊 ETF", url: function () { return "/MRALGO?hz=etf&embed=1"; } },
      { id: "pac", label: "📉 PAC Chart", url: function () { var t = currentTicker(); return "/MRALGO?embed=1" + (t ? "&t=" + encodeURIComponent(t) : ""); } },
    ];
    // overlay
    var ov = document.createElement("div");
    ov.id = "mrbull-overlay";
    ov.style.cssText = "position:fixed;inset:0;z-index:100000;background:#0a0d0c;display:none;flex-direction:column";
    var bar = document.createElement("div");
    bar.style.cssText = "display:flex;align-items:center;gap:12px;padding:10px 16px;background:#0c1119;border-bottom:1px solid #1b2530;color:#d7e0dd;font:600 13px 'JetBrains Mono',monospace;flex:none";
    var ttl = document.createElement("span"); ttl.id = "mrbull-ov-title"; ttl.textContent = "MrAlgo";
    var sp = document.createElement("span"); sp.style.cssText = "margin-left:auto;color:#5a6b63;font-weight:400;font-size:11px"; sp.textContent = "MrAlgo-native · live";
    var cx = document.createElement("button");
    cx.textContent = "✕ Close"; cx.style.cssText = "background:#131b24;border:1px solid #223;color:#22d3ee;border-radius:7px;padding:5px 12px;cursor:pointer;font:inherit";
    cx.onclick = function () { ov.style.display = "none"; ifr.src = "about:blank"; };
    var ifr = document.createElement("iframe");
    ifr.id = "mrbull-ov-iframe"; ifr.style.cssText = "flex:1;width:100%;border:0;background:#0a0d0c";
    bar.appendChild(ttl); bar.appendChild(sp); bar.appendChild(cx);
    ov.appendChild(bar); ov.appendChild(ifr);
    document.body.appendChild(ov);
    // launcher strip (bottom-left, out of the way of Ask Kairos bottom-right)
    var L = document.createElement("div");
    L.id = "mrbull-launcher";
    L.style.cssText = "position:fixed;left:64px;bottom:16px;z-index:99999;display:flex;gap:8px;align-items:center;background:#0c1119ee;border:1px solid #1b2530;border-radius:12px;padding:6px 8px;backdrop-filter:blur(8px)";
    var tag = document.createElement("span");
    tag.textContent = "MrAlgo"; tag.style.cssText = "color:#22d3ee;font:700 10px 'JetBrains Mono',monospace;letter-spacing:.1em;padding:0 4px";
    L.appendChild(tag);
    TABS.forEach(function (t) {
      var btn = document.createElement("button");
      btn.textContent = t.label;
      btn.style.cssText = "background:#131b24;border:1px solid #223;color:#d7e0dd;border-radius:8px;padding:6px 11px;cursor:pointer;font:600 11.5px 'JetBrains Mono',monospace;white-space:nowrap";
      btn.onmouseenter = function () { btn.style.borderColor = "#22d3ee"; btn.style.color = "#22d3ee"; };
      btn.onmouseleave = function () { btn.style.borderColor = "#223"; btn.style.color = "#d7e0dd"; };
      btn.onclick = function () {
        document.getElementById("mrbull-ov-title").textContent = "MrAlgo · " + t.label.replace(/^[^ ]+ /, "");
        ifr.src = t.url();
        ov.style.display = "flex";
      };
      L.appendChild(btn);
    });
    document.body.appendChild(L);
  }

  // ── cosmetic rebrand ──
  function rebrand() {
    try {
      document.title = "MrBullAlgo — Terminal";
      var ld = document.getElementById("bv-loading");
      if (ld) {
        ld.querySelectorAll("div").forEach(function (d) {
          if (/LOADING BULLVEDA/i.test(d.textContent)) d.textContent = "LOADING MRBULLALGO · LIVE DATA";
        });
      }
      var swap = function () {
        document.querySelectorAll("*").forEach(function (el) {
          if (el.childElementCount === 0 && el.textContent === "BullVeda") el.textContent = "MrBullAlgo";
        });
      };
      swap();
      var mo = new MutationObserver(function () { swap(); });
      mo.observe(document.documentElement, { childList: true, subtree: true });
      setTimeout(function () { try { mo.disconnect(); } catch (e) {} }, 8000);
    } catch (e) {}
  }
  function init() {
    rebrand();
    setTimeout(setupMrBullTabs, 1500);
    setTimeout(setupMrBullTabs, 4500);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
