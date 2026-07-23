/* mrbullalgo-override.js — MrBullAlgo adapter shim.
 *
 * MrBullAlgo = BullVeda's UI + MrAlgo's decision core. This file is a
 * render-blocking <head> script injected ONLY on the /MRBULLALGO route (BullVeda
 * itself never loads it). It runs BEFORE the inlined bullveda-boot adapter, so it
 * can wrap the network layer and re-route the decision contracts (universe /
 * ticker / trade_engine / fundamentals / pattern) to MrAlgo's engine, while
 * ML / options / earnings / crypto pass through to SwingTrade unchanged.
 *
 * PHASE 0 (this version): NO data rerouting yet — pure pass-through clone, so
 * MrBullAlgo === BullVeda under a new name (zero behaviour change). Only the
 * brand is swapped so the two are visually distinguishable. Phase 1 adds the
 * fetch/XHR shim here.
 */
(function () {
  "use strict";
  window.__MRBULLALGO__ = true;
  window.__MRBULLALGO_PHASE__ = 0;
  try { console.log("[MrBullAlgo] override loaded · phase 0 (pass-through clone)"); } catch (e) {}

  // Cosmetic rebrand once the DOM is up (BullVeda -> MrBullAlgo in visible chrome).
  function rebrand() {
    try {
      document.title = "MrBullAlgo — Terminal";
      // Loading-screen label (static HTML, present before React mounts).
      var ld = document.getElementById("bv-loading");
      if (ld) {
        ld.querySelectorAll("div").forEach(function (d) {
          if (/LOADING BULLVEDA/i.test(d.textContent)) d.textContent = "LOADING MRBULLALGO · LIVE DATA";
        });
      }
      // In-app brand text (rendered by React later) — swap on a light observer.
      var swap = function () {
        document.querySelectorAll("*").forEach(function (el) {
          if (el.childElementCount === 0 && el.textContent === "BullVeda") el.textContent = "MrBullAlgo";
        });
      };
      swap();
      var mo = new MutationObserver(function () { swap(); });
      mo.observe(document.documentElement, { childList: true, subtree: true });
      // Stop the observer after the app has settled to avoid churn.
      setTimeout(function () { try { mo.disconnect(); } catch (e) {} }, 8000);
    } catch (e) {}
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", rebrand);
  } else {
    rebrand();
  }
})();
