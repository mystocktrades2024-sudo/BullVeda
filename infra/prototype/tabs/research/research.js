// tabs/research/research.js — extracted from dashboard.html (renderResearchTab 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  // Default: load Statistical Rigor on first open
  rsSwitch('rigor');
}

export function dispose() { /* no-op */ }
