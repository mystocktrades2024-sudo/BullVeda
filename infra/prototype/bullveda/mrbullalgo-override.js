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
  window.__MRBULLALGO_PHASE__ = 2;

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
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", rebrand);
  else rebrand();
})();
