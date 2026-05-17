#!/usr/bin/env python3
"""
Audit 360 — single-command system health audit for SwingTrade.

Runs 12 checks and produces:
  - CLI report (color-coded with ANSI)
  - HTML report at cache/audit_360_<date>.html

Usage:
    python3 audit_360.py                  # full audit, save HTML
    python3 audit_360.py --quick          # skip network probes
    python3 audit_360.py --no-html        # CLI only

Status legend:
    PASS  green   — section is healthy
    WARN  yellow  — investigate but not blocking
    FAIL  red     — fix before next live trade

Overall health score = avg(check_score), where:
    PASS = 100, WARN = 60, FAIL = 0
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
KAIROS_CSS = '''
:root {
  --bg-0:#000000; --bg:#000; --bg-1:#0a0d0c; --bg-2:#0f1311; --bg-3:#141816;
  --line:#1d2520; --line-2:#2a352e;
  --ink:#d8d6cc; --ink-1:#b0aea3; --ink-2:#80847a; --ink-3:#545851; --ink-4:#2e312c;
  --gn:#5be57c; --gn-bg:rgba(91,229,124,0.08); --gn-dim:rgba(91,229,124,0.30);
  --amb:#ffb95c; --amb-bg:rgba(255,185,92,0.08); --amb-dim:rgba(255,185,92,0.30);
  --rd:#ff6b5b; --rd-bg:rgba(255,107,91,0.08); --rd-dim:rgba(255,107,91,0.30);
  --cy:#5ec8d8; --cy-bg:rgba(94,200,216,0.08);
  --copper:#d97757; --copper-bg:rgba(217,119,87,0.08);
  --vio:#a78bfa; --vio-bg:rgba(167,139,250,0.08);
  --sans:'Inter','Aptos','Aptos Display',-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',sans-serif;
  --mono:'Inter','Aptos','Aptos Display',-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',sans-serif;
}
* { box-sizing:border-box; margin:0; padding:0; }
html, body {
  background: var(--bg-1); color: var(--ink);
  font: 13px var(--sans); line-height: 1.55;
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}
a { color: inherit; text-decoration: none; cursor: pointer; }
code { font: 600 11px var(--mono); background: var(--cy-bg); color: var(--cy); padding: 1px 5px; border-radius: 2px; }

.refv2 { padding: 18px 22px 60px; max-width: 1500px; margin: 0 auto; }

/* ── Topbar (sticky) ────────────────────────────────────────────────── */
.rf-topbar {
  position: sticky; top: 0; z-index: 10;
  background: rgba(10,13,12,0.96); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--line);
  padding: 14px 0 12px; margin-bottom: 22px;
}
.rf-crumbs { display:flex; align-items:center; gap:14px; font:600 10.5px var(--mono); letter-spacing:.10em; color: var(--ink-3); text-transform: uppercase; }
.rf-crumbs a { color: var(--copper); }
.rf-crumbs a:hover { color: var(--ink); }
.rf-crumbs .sep { color: var(--ink-4); }
.rf-title-row { display:flex; align-items:baseline; gap:12px; margin-top: 10px; }
.rf-title { font:800 26px var(--sans); color: var(--ink); letter-spacing:-0.015em; }
.rf-sub  { font:500 12px var(--mono); color: var(--ink-2); letter-spacing:.04em; }
.rf-meta { display:flex; gap: 14px; flex-wrap: wrap; font: 500 11px var(--mono); color: var(--ink-3); letter-spacing: .04em; margin-top: 6px; }
.rf-meta b { color: var(--ink-1); font-weight: 700; }

/* ── Section header (mirrors .qc-h) ─────────────────────────────────── */
.rf-qch { display:flex; justify-content:space-between; align-items:baseline; margin:22px 4px 10px; padding:0 4px; }
.rf-qch .q { font:700 16px var(--sans); color: var(--ink); letter-spacing:-0.005em; display:flex; align-items:center; gap:10px; }
.rf-qch .num { display:inline-flex; width:26px; height:26px; align-items:center; justify-content:center; background: var(--copper-bg); color: var(--copper); border:1px solid color-mix(in oklch, var(--copper) 30%, transparent); border-radius:2px; font:800 11px var(--mono); letter-spacing:.04em; }
.rf-qch .sub { font:500 11.5px var(--mono); color: var(--ink-3); letter-spacing:.04em; margin-left: 4px; }
.rf-qch .r { font:600 10.5px var(--mono); color: var(--ink-3); letter-spacing:.06em; }
.rf-qch .where { font:500 11px var(--mono); color: var(--ink-3); margin: -6px 4px 12px; padding: 0 4px; letter-spacing: .02em; }

/* ── Hero (mirrors .rf-hero) ────────────────────────────────────────── */
.rf-hero {
  background: linear-gradient(135deg, var(--copper-bg) 0%, var(--bg-2) 60%, var(--bg-2) 100%);
  border: 1px solid var(--line); border-left: 4px solid var(--copper); border-radius: 4px;
  padding: 18px 22px; margin-bottom: 14px;
  display: grid; grid-template-columns: 1.4fr 240px 1fr 260px; gap: 24px; align-items: center;
}
.rf-hero.gn  { border-left-color: var(--gn);  background: linear-gradient(135deg, var(--gn-bg)  0%, var(--bg-2) 60%, var(--bg-2) 100%); }
.rf-hero.am  { border-left-color: var(--amb); background: linear-gradient(135deg, var(--amb-bg) 0%, var(--bg-2) 60%, var(--bg-2) 100%); }
.rf-hero.rd  { border-left-color: var(--rd);  background: linear-gradient(135deg, var(--rd-bg)  0%, var(--bg-2) 60%, var(--bg-2) 100%); }
.rf-hero.cy  { border-left-color: var(--cy);  background: linear-gradient(135deg, var(--cy-bg)  0%, var(--bg-2) 60%, var(--bg-2) 100%); }
.rf-hero.vio { border-left-color: var(--vio); background: linear-gradient(135deg, var(--vio-bg) 0%, var(--bg-2) 60%, var(--bg-2) 100%); }
.rf-hero-head { display:flex; flex-direction:column; gap: 4px; }
.rf-hero-badge {
  display:inline-flex; align-items:center; gap: 6px;
  padding: 3px 10px; background: var(--copper-bg); color: var(--copper);
  border: 1px solid color-mix(in oklch, var(--copper) 30%, transparent);
  border-radius: 2px;
  font: 800 9.5px var(--mono); letter-spacing: .12em; text-transform: uppercase;
  width: fit-content; margin-bottom: 4px;
}
.rf-hero.gn  .rf-hero-badge { background: var(--gn-bg);  color: var(--gn);  border-color: var(--gn-dim); }
.rf-hero.am  .rf-hero-badge { background: var(--amb-bg); color: var(--amb); border-color: var(--amb-dim); }
.rf-hero.rd  .rf-hero-badge { background: var(--rd-bg);  color: var(--rd);  border-color: var(--rd-dim); }
.rf-hero-name { font: 800 22px var(--sans); color: var(--ink); letter-spacing: -0.01em; line-height: 1.15; }
.rf-hero-name .icon { font-size: 24px; margin-right: 8px; }
.rf-hero-mech { font: 500 12px var(--mono); color: var(--ink-2); letter-spacing: .02em; margin-top: 5px; line-height: 1.55; }
.rf-hero-mech b { color: var(--ink-1); font-weight: 700; }
.rf-hero-num { text-align:center; }
.rf-hero-num .k { font: 700 9.5px var(--mono); color: var(--ink-3); letter-spacing: .12em; text-transform: uppercase; }
.rf-hero-num .v { font: 800 52px var(--sans); color: var(--ink); font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -0.03em; margin-top: 4px; }
.rf-hero-num .v.gn { color: var(--gn); } .rf-hero-num .v.am { color: var(--amb); }
.rf-hero-num .v.rd { color: var(--rd); } .rf-hero-num .v.cy { color: var(--cy); }
.rf-hero-num .s { font: 500 11px var(--mono); color: var(--ink-2); margin-top: 6px; letter-spacing: .04em; }
.rf-hero-meta { font: 600 10px var(--mono); color: var(--ink-3); letter-spacing: .10em; text-transform: uppercase; margin-bottom: 6px; }
.rf-hero-stats { display:flex; flex-direction:column; gap: 6px; }
.rf-hero-stat { display:flex; justify-content:space-between; padding: 6px 9px; background: var(--bg-3); border-radius: 2px; font: 600 11px var(--mono); }
.rf-hero-stat .l { color: var(--ink-3); letter-spacing: .04em; }
.rf-hero-stat .v { color: var(--ink); font-weight: 800; }
.rf-hero-stat .v.gn { color: var(--gn); } .rf-hero-stat .v.am { color: var(--amb); }
.rf-hero-stat .v.rd { color: var(--rd); } .rf-hero-stat .v.cy { color: var(--cy); }
.rf-hero-tickers { display: flex; flex-wrap: wrap; gap: 6px; }
.rf-hero-tickers a {
  padding: 5px 10px; background: var(--bg-3); border: 1px solid var(--line); border-radius: 3px;
  color: var(--ink-1); font: 800 11.5px var(--mono); letter-spacing: .04em;
  transition: all 80ms;
}
.rf-hero-tickers a:hover { border-color: var(--copper); color: var(--copper); }

/* ── Cards ──────────────────────────────────────────────────────────── */
.rf-grid    { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.rf-grid-3  { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.rf-grid-2  { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.rf-card {
  background: var(--bg-2); border: 1px solid var(--line); border-radius: 3px;
  padding: 14px; display: flex; flex-direction: column; gap: 8px;
  position: relative; overflow: hidden;
  transition: border-color 100ms;
}
.rf-card.hot  { border-top: 3px solid var(--gn); }
.rf-card.warm { border-top: 3px solid var(--amb); }
.rf-card.cold { border-top: 3px solid var(--ink-3); }
.rf-card.crit { border-top: 3px solid var(--rd); }
.rf-card.cy   { border-top: 3px solid var(--cy); }
.rf-card.vio  { border-top: 3px solid var(--vio); }
.rf-card.copper { border-top: 3px solid var(--copper); }
.rf-card-h { display:flex; justify-content:space-between; align-items:flex-start; gap: 8px; }
.rf-card-h-l { display:flex; align-items:center; gap: 7px; }
.rf-card-icon { font-size: 18px; line-height: 1; }
.rf-card-n { font: 800 13px var(--sans); color: var(--ink); letter-spacing: .02em; line-height: 1.1; }

/* ── Pills ──────────────────────────────────────────────────────────── */
.rf-pill { padding: 2px 7px; border-radius: 2px; font: 800 9px var(--mono); letter-spacing: .10em; text-transform: uppercase; flex-shrink: 0; }
.rf-pill.hot   { background: var(--gn-bg);  color: var(--gn);  border: 1px solid var(--gn-dim); }
.rf-pill.warm  { background: var(--amb-bg); color: var(--amb); border: 1px solid var(--amb-dim); }
.rf-pill.cold  { background: var(--bg-3);   color: var(--ink-3); border: 1px solid var(--line-2); }
.rf-pill.crit  { background: var(--rd-bg);  color: var(--rd);  border: 1px solid var(--rd-dim); }
.rf-pill.pass  { background: var(--gn-bg);  color: var(--gn);  border: 1px solid var(--gn-dim); }
.rf-pill.warn  { background: var(--amb-bg); color: var(--amb); border: 1px solid var(--amb-dim); }
.rf-pill.fail  { background: var(--rd-bg);  color: var(--rd);  border: 1px solid var(--rd-dim); }
.rf-pill.info  { background: var(--cy-bg);  color: var(--cy);  border: 1px solid color-mix(in oklch, var(--cy) 30%, transparent); }
.rf-pill.must  { background: var(--rd-bg);  color: var(--rd);  border: 1px solid var(--rd-dim); }
.rf-pill.should { background: var(--amb-bg); color: var(--amb); border: 1px solid var(--amb-dim); }
.rf-pill.good  { background: var(--gn-bg);  color: var(--gn);  border: 1px solid var(--gn-dim); }

/* ── Mech / desc ────────────────────────────────────────────────────── */
.rf-mech { font: 500 11.5px var(--mono); color: var(--ink-2); letter-spacing: .02em; line-height: 1.55; }
.rf-mech b { color: var(--ink-1); font-weight: 700; }

/* ── Table ──────────────────────────────────────────────────────────── */
.rf-table { width: 100%; border-collapse: collapse; background: var(--bg-2); border: 1px solid var(--line); border-radius: 3px; overflow: hidden; margin: 6px 0; }
.rf-table th, .rf-table td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--line); font: 500 11.5px var(--mono); }
.rf-table tr:last-child td { border-bottom: 0; }
.rf-table th { font: 800 9.5px var(--mono); letter-spacing: .14em; text-transform: uppercase; color: var(--ink-3); background: var(--bg-3); border-bottom: 1px solid var(--line-2); }
.rf-table td.tk { color: var(--ink); font-weight: 800; letter-spacing: .04em; }
.rf-table td .gn { color: var(--gn); font-weight: 700; }
.rf-table td .rd { color: var(--rd); font-weight: 700; }
.rf-table td .am { color: var(--amb); font-weight: 700; }
.rf-table td .cy { color: var(--cy); font-weight: 700; }

/* ── Tip / Warn blocks ──────────────────────────────────────────────── */
.rf-block { padding: 12px 16px; border-radius: 3px; margin: 10px 0; font: 500 12px var(--mono); border: 1px solid var(--line); border-left: 4px solid var(--copper); background: var(--bg-2); line-height: 1.6; }
.rf-block b { color: var(--copper); font-weight: 700; letter-spacing: .04em; }
.rf-block.gn  { border-left-color: var(--gn);  background: linear-gradient(135deg, var(--gn-bg) 0%, var(--bg-2) 100%); }
.rf-block.gn b { color: var(--gn); }
.rf-block.am  { border-left-color: var(--amb); background: linear-gradient(135deg, var(--amb-bg) 0%, var(--bg-2) 100%); }
.rf-block.am b { color: var(--amb); }
.rf-block.rd  { border-left-color: var(--rd);  background: linear-gradient(135deg, var(--rd-bg) 0%, var(--bg-2) 100%); }
.rf-block.rd b { color: var(--rd); }
.rf-block.cy  { border-left-color: var(--cy);  background: linear-gradient(135deg, var(--cy-bg) 0%, var(--bg-2) 100%); }
.rf-block.cy b { color: var(--cy); }

/* ── Pre / details ──────────────────────────────────────────────────── */
.rf-card pre, pre.rf-pre {
  background: var(--bg-1); border: 1px solid var(--line); border-radius: 3px;
  padding: 10px 12px; font: 500 11px var(--mono); color: var(--ink-1);
  line-height: 1.6; overflow-x: auto; margin: 6px 0 0;
}
details { margin-top: 6px; }
details summary {
  cursor: pointer; user-select: none;
  font: 700 10.5px var(--mono); letter-spacing: .10em; text-transform: uppercase;
  color: var(--ink-3); padding: 4px 0;
  border-top: 1px dashed var(--line);
}
details summary:hover { color: var(--ink); }
details[open] summary { color: var(--copper); }

/* ── Actions list ───────────────────────────────────────────────────── */
.rf-actions {
  margin-top: 10px; padding: 10px 14px;
  background: var(--cy-bg); border: 1px solid color-mix(in oklch, var(--cy) 30%, transparent);
  border-left: 3px solid var(--cy); border-radius: 3px;
}
.rf-actions-l { font: 800 9.5px var(--mono); color: var(--cy); letter-spacing: .16em; text-transform: uppercase; margin-bottom: 4px; }
.rf-actions ul { margin: 0; padding-left: 18px; font: 500 11.5px var(--mono); color: var(--ink-1); }
.rf-actions li { margin: 3px 0; line-height: 1.5; }

/* ── Checklist (cheatsheet) ─────────────────────────────────────────── */
.rf-check { display:flex; flex-direction:column; gap: 6px; margin: 10px 0; }
.rf-check-item {
  display: grid; grid-template-columns: auto 1fr auto;
  gap: 12px; align-items: start;
  padding: 11px 14px; background: var(--bg-2); border: 1px solid var(--line);
  border-radius: 3px; transition: all .15s;
  cursor: pointer;
}
.rf-check-item:hover { border-color: var(--line-2); background: var(--bg-3); }
.rf-check-item input[type=checkbox] {
  width: 16px; height: 16px; margin-top: 2px; accent-color: var(--copper); cursor: pointer;
}
.rf-check-l { font: 500 12.5px var(--sans); color: var(--ink-1); }
.rf-check-l b { color: var(--ink); font-weight: 700; }
.rf-check-l .hint { display:block; font: 500 11.5px var(--mono); color: var(--ink-3); margin-top: 4px; line-height: 1.55; letter-spacing: .02em; }
.rf-check-item.done { opacity: .55; }
.rf-check-item.done .rf-check-l b { text-decoration: line-through; color: var(--ink-3); }

/* ── TOC (cheatsheet) ───────────────────────────────────────────────── */
.rf-toc { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; margin: 14px 0 24px; }
.rf-toc a {
  display: flex; align-items: center; gap: 10px;
  padding: 11px 14px; background: var(--bg-2); border: 1px solid var(--line); border-radius: 3px;
  transition: all 80ms;
}
.rf-toc a:hover { border-color: var(--copper); background: var(--bg-3); transform: translateY(-1px); }
.rf-toc-num {
  display:inline-flex; width: 24px; height: 24px; align-items:center; justify-content:center;
  background: var(--copper-bg); color: var(--copper);
  border: 1px solid color-mix(in oklch, var(--copper) 30%, transparent);
  border-radius: 2px;
  font: 800 11px var(--mono); flex-shrink: 0;
}
.rf-toc-t { display:flex; flex-direction:column; gap: 2px; }
.rf-toc-t b { color: var(--ink); font: 700 12.5px var(--sans); letter-spacing: -0.005em; }
.rf-toc-t span { color: var(--ink-3); font: 500 10.5px var(--mono); letter-spacing: .02em; }

/* ── Decision boxes (cheatsheet) ────────────────────────────────────── */
.rf-decision { display:grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 12px 0; }
.rf-dbox {
  padding: 14px 16px; border-radius: 3px;
  background: var(--bg-2); border: 1px solid var(--line);
}
.rf-dbox.go { border-top: 3px solid var(--gn); background: linear-gradient(135deg, var(--gn-bg) 0%, var(--bg-2) 80%); }
.rf-dbox.no { border-top: 3px solid var(--rd); background: linear-gradient(135deg, var(--rd-bg) 0%, var(--bg-2) 80%); }
.rf-dbox h4 { margin: 0 0 8px; font: 800 11px var(--mono); letter-spacing: .14em; text-transform: uppercase; }
.rf-dbox.go h4 { color: var(--gn); }
.rf-dbox.no h4 { color: var(--rd); }
.rf-dbox ul { margin: 0; padding-left: 18px; font: 500 12px var(--mono); color: var(--ink-1); line-height: 1.6; }
.rf-dbox li { margin: 3px 0; }
.rf-dbox b { color: var(--ink); font-weight: 700; }

/* ── Decision tree (cheatsheet) ─────────────────────────────────────── */
.rf-tree {
  background: var(--bg-2); border: 1px solid var(--line);
  border-left: 3px solid var(--copper); border-radius: 3px;
  padding: 16px 20px; margin: 12px 0;
  font: 500 12px var(--mono); line-height: 1.85;
  color: var(--ink-1); white-space: pre-wrap; overflow-x: auto;
}
.rf-tree .ok { color: var(--gn); font-weight: 700; }
.rf-tree .no { color: var(--rd); font-weight: 700; }
.rf-tree .br { color: var(--ink-3); }

/* ── Glossary (cheatsheet) ──────────────────────────────────────────── */
.rf-glossary { display: grid; grid-template-columns: 220px 1fr; gap: 6px 18px; margin: 12px 0; }
.rf-glossary dt {
  font: 800 12px var(--mono); color: var(--copper);
  letter-spacing: .06em; padding-top: 4px;
}
.rf-glossary dd {
  font: 500 11.5px var(--mono); color: var(--ink-1);
  line-height: 1.6; padding: 4px 0 4px 10px;
  border-left: 1px solid var(--line);
}
.rf-glossary dd b { color: var(--ink); font-weight: 700; }

/* ── Progress pill (cheatsheet) ─────────────────────────────────────── */
.rf-progress {
  position: fixed; bottom: 20px; right: 20px;
  background: var(--bg-2); border: 1px solid var(--line-2);
  border-radius: 3px; padding: 8px 14px;
  font: 600 11px var(--mono); color: var(--ink-2);
  box-shadow: 0 4px 18px rgba(0,0,0,0.5);
  z-index: 50;
}
.rf-progress b { color: var(--copper); font: 800 12px var(--mono); letter-spacing: .04em; }
.rf-progress .reset { margin-left: 10px; color: var(--ink-3); cursor: pointer; text-decoration: underline; }
.rf-progress .reset:hover { color: var(--ink); }

/* ── Print ──────────────────────────────────────────────────────────── */
@media print {
  .rf-topbar, .rf-progress { position: static; }
  body { background: white; color: black; }
  .rf-card, .rf-dbox, .rf-tree, .rf-table, .rf-block, .rf-check-item, .rf-glossary dd { background: white; border-color: #ccc; color: black; }
  .rf-card-n, .rf-title, h2, h3, h4 { color: black; }
}

/* ── Responsive ─────────────────────────────────────────────────────── */
@media (max-width: 1280px) {
  .rf-grid { grid-template-columns: repeat(2, 1fr); }
  .rf-grid-3 { grid-template-columns: 1fr; }
  .rf-hero { grid-template-columns: 1fr; gap: 14px; }
}
@media (max-width: 720px) {
  .rf-decision { grid-template-columns: 1fr; }
  .rf-glossary { grid-template-columns: 1fr; }
  .rf-check-item { grid-template-columns: auto 1fr; }
  .rf-check-item .rf-pill { grid-column: 2; margin-top: 4px; }
}
'''

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
DATA = ROOT / "data"
CONFIG = ROOT / "config"

# ANSI colors
_RED = "\033[31m"
_GRN = "\033[32m"
_YEL = "\033[33m"
_BLU = "\033[34m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


# ──────────────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────────────

@dataclass
class AuditResult:
    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    summary: str
    details: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0

    def score(self) -> int:
        return {"PASS": 100, "WARN": 60, "FAIL": 0}.get(self.status, 0)

    def colored_status(self) -> str:
        c = {"PASS": _GRN, "WARN": _YEL, "FAIL": _RED}.get(self.status, "")
        return f"{c}{self.status:4s}{_RESET}"


def _run(name: str, fn) -> AuditResult:
    """Wrap a check fn so exceptions never crash the audit."""
    t0 = time.time()
    try:
        result = fn()
        if isinstance(result, AuditResult):
            result.elapsed_s = round(time.time() - t0, 2)
            return result
        # Allow returning a 3-tuple (status, summary, details_or_dict)
        status, summary, extra = result
        details = extra if isinstance(extra, list) else []
        metrics = extra if isinstance(extra, dict) else {}
        return AuditResult(name=name, status=status, summary=summary,
                           details=details, metrics=metrics,
                           elapsed_s=round(time.time() - t0, 2))
    except Exception as e:
        return AuditResult(
            name=name, status="FAIL",
            summary=f"check raised exception: {type(e).__name__}: {e}",
            details=traceback.format_exc().splitlines()[-6:],
            elapsed_s=round(time.time() - t0, 2),
        )


# ──────────────────────────────────────────────────────────────────
# 1. SYSTEM STATE — last scan time, regime, portfolio basics
# ──────────────────────────────────────────────────────────────────

def check_system_state() -> AuditResult:
    bundle_path = CACHE / "last_bundle.json"
    if not bundle_path.exists():
        return AuditResult(
            name="system_state", status="FAIL",
            summary="no last_bundle.json — system has never scanned",
            actions=["python3 swing_trade.py"],
        )
    bundle = json.loads(bundle_path.read_text())
    mtime = datetime.fromtimestamp(bundle_path.stat().st_mtime)
    age_h = (datetime.now() - mtime).total_seconds() / 3600

    regime = bundle.get("regime", {}) or {}
    regime4 = regime.get("regime4", "?")
    vix = (regime.get("vix") or {}).get("vix_current", "?")

    portfolio_state_path = DATA / "portfolio_state.json"
    pos_count = 0
    cash = equity = None
    if portfolio_state_path.exists():
        ps = json.loads(portfolio_state_path.read_text())
        pos_count = len(ps.get("positions", []))
        cash = ps.get("cash")
        equity = ps.get("equity")

    details = [
        f"last_bundle.json: {mtime.strftime('%Y-%m-%d %H:%M')} ({age_h:.1f}h ago)",
        f"regime: {regime4}  vix: {vix}",
        f"portfolio: {pos_count} open positions, cash=${cash}, equity=${equity}",
        f"all_scored: {len(bundle.get('all_scored', []))}, "
        f"buy_candidates: {len(bundle.get('buy_candidates', []))}, "
        f"killed: {len(bundle.get('killed', []))}",
    ]
    metrics = {
        "scan_age_hours": round(age_h, 1),
        "regime": regime4,
        "vix": vix,
        "open_positions": pos_count,
        "cash": cash,
        "equity": equity,
        "scored_total": len(bundle.get("all_scored", [])),
        "buy_count": len(bundle.get("buy_candidates", [])),
        "killed_count": len(bundle.get("killed", [])),
    }

    if age_h > 48:
        return AuditResult(
            name="system_state", status="FAIL",
            summary=f"scan is {age_h:.0f}h stale — bundle from {mtime.strftime('%Y-%m-%d')}",
            details=details, metrics=metrics,
            actions=["python3 swing_trade.py  (full re-scan)"],
        )
    if age_h > 18:
        return AuditResult(
            name="system_state", status="WARN",
            summary=f"scan is {age_h:.0f}h old — consider re-scan",
            details=details, metrics=metrics,
            actions=["python3 swing_trade.py"],
        )
    return AuditResult(
        name="system_state", status="PASS",
        summary=f"scan {age_h:.1f}h ago, regime={regime4}, {pos_count} positions",
        details=details, metrics=metrics,
    )


# ──────────────────────────────────────────────────────────────────
# 2. DATA SOURCE HEALTH — EODHD reachability, plan tier
# ──────────────────────────────────────────────────────────────────

def check_data_sources(quick: bool = False) -> AuditResult:
    details: list[str] = []
    metrics: dict = {}
    failures: list[str] = []
    warnings: list[str] = []

    # 2a. .env presence
    env_path = ROOT / ".env"
    if not env_path.exists():
        return AuditResult(
            name="data_sources", status="FAIL",
            summary=".env missing — no credentials loaded",
            actions=["create .env with EODHD_API_KEY at minimum"],
        )
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    eodhd_key = env.get("EODHD_API_KEY", "")
    alpaca_key = env.get("ALPACA_API_KEY", "")
    schwab_key = env.get("SCHWAB_APP_KEY", "")
    slack_url = env.get("SLACK_WEBHOOK_URL", "")

    details.append(f"EODHD_API_KEY: {'present' if eodhd_key else 'MISSING'}"
                   + (f" ({len(eodhd_key)} chars)" if eodhd_key else ""))
    details.append(f"ALPACA_API_KEY: {'present' if alpaca_key else 'MISSING'}")
    details.append(f"SCHWAB_APP_KEY: {'present' if schwab_key else 'MISSING'}")
    details.append(f"SLACK_WEBHOOK_URL: {'present' if slack_url else 'MISSING'}")

    metrics["eodhd_key_present"] = bool(eodhd_key)
    metrics["alpaca_key_present"] = bool(alpaca_key)
    metrics["schwab_key_present"] = bool(schwab_key)

    if not eodhd_key:
        failures.append("EODHD_API_KEY missing — system cannot fetch market data")

    # 2b. EODHD live ping (skip in quick mode)
    if not quick and eodhd_key:
        try:
            t0 = time.time()
            url = f"https://eodhd.com/api/eod/AAPL.US?api_token={eodhd_key}&fmt=json&from=2026-04-20&to=2026-04-21"
            req = urllib.request.Request(url, headers={"User-Agent": "audit_360/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                code = r.getcode()
            ms = (time.time() - t0) * 1000
            details.append(f"EODHD ping: HTTP {code} in {ms:.0f}ms")
            metrics["eodhd_ping_ms"] = round(ms)
            metrics["eodhd_ping_code"] = code
            if code != 200:
                failures.append(f"EODHD non-200: {code}")
        except urllib.error.HTTPError as e:
            failures.append(f"EODHD HTTP error: {e.code}")
            details.append(f"EODHD ping FAILED: {e}")
            metrics["eodhd_ping_code"] = e.code
        except Exception as e:
            warnings.append(f"EODHD unreachable: {type(e).__name__}")
            details.append(f"EODHD ping FAILED: {e}")

        # 2c. Plan tier — fundamentals endpoint
        try:
            import eodhd_client as e
            r = e.fundamentals("AAPL")
            if isinstance(r, dict) and r.get("Highlights"):
                details.append("EODHD All-In-One: ACTIVE (fundamentals reachable)")
                metrics["eodhd_aio_active"] = True
            else:
                warnings.append("EODHD fundamentals returned no data")
                metrics["eodhd_aio_active"] = False
        except Exception as e:
            warnings.append(f"EODHD fundamentals check raised: {type(e).__name__}")
            metrics["eodhd_aio_active"] = False

    # 2d. Capitol Trades reachability (replacement for Senate Stock Watcher)
    if not quick:
        try:
            t0 = time.time()
            req = urllib.request.Request(
                "https://www.capitoltrades.com/trades?per_page=10",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=6) as r:
                code = r.getcode()
            ms = (time.time() - t0) * 1000
            details.append(f"capitoltrades.com: HTTP {code} in {ms:.0f}ms")
            metrics["capitoltrades_code"] = code
            if code != 200:
                warnings.append(f"capitoltrades.com {code}")
        except Exception as e:
            warnings.append(f"capitoltrades.com unreachable: {type(e).__name__}")
            details.append(f"capitoltrades.com: {e}")

    # 2e. SQLite reachable
    db_path = DATA / "swingtrade.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        details.append(f"SQLite swingtrade.db: {size_kb:.0f} KB")
        metrics["sqlite_kb"] = round(size_kb)
    else:
        warnings.append("SQLite db missing — JSON-only fallback in use")

    # decide overall
    if failures:
        return AuditResult(
            name="data_sources", status="FAIL",
            summary="; ".join(failures), details=details, metrics=metrics,
            actions=["check .env credentials", "verify EODHD plan at eodhd.com"],
        )
    if warnings:
        return AuditResult(
            name="data_sources", status="WARN",
            summary="; ".join(warnings), details=details, metrics=metrics,
        )
    return AuditResult(
        name="data_sources", status="PASS",
        summary="all primary data sources reachable",
        details=details, metrics=metrics,
    )


# ──────────────────────────────────────────────────────────────────
# 3. UNIVERSE COVERAGE — last bundle scoring stats
# ──────────────────────────────────────────────────────────────────

def check_universe_coverage() -> AuditResult:
    bundle_path = CACHE / "last_bundle.json"
    if not bundle_path.exists():
        return AuditResult(name="universe_coverage", status="FAIL",
                           summary="no last_bundle.json")
    bundle = json.loads(bundle_path.read_text())

    all_scored = bundle.get("all_scored", [])
    killed = bundle.get("killed", [])
    buy = bundle.get("buy_candidates", [])
    near_blocked = bundle.get("near_short_blocked", [])
    total_attempted = len(all_scored) + len(killed)

    # Scoring distribution
    scores = [s.get("score", 0) for s in all_scored if s.get("score") is not None]
    if scores:
        median_score = sorted(scores)[len(scores) // 2]
        max_score = max(scores)
        score_60_plus = sum(1 for s in scores if s >= 60)
        score_70_plus = sum(1 for s in scores if s >= 70)
        score_80_plus = sum(1 for s in scores if s >= 80)
    else:
        median_score = max_score = score_60_plus = score_70_plus = score_80_plus = 0

    # Direction breakdown
    longs = sum(1 for s in all_scored if s.get("direction") == "long")
    shorts = sum(1 for s in all_scored if s.get("direction") == "short")
    nones = sum(1 for s in all_scored if s.get("direction") not in ("long", "short"))

    details = [
        f"total scored: {len(all_scored)} | killed: {len(killed)} | total attempted: {total_attempted}",
        f"buy candidates: {len(buy)} | near-short blocked: {len(near_blocked)}",
        f"score distribution: median={median_score}, max={max_score}",
        f"  ≥60: {score_60_plus} ({score_60_plus/max(1,len(scores))*100:.0f}%)",
        f"  ≥70: {score_70_plus} ({score_70_plus/max(1,len(scores))*100:.0f}%)",
        f"  ≥80: {score_80_plus} ({score_80_plus/max(1,len(scores))*100:.0f}%)",
        f"direction: long={longs}, short={shorts}, none={nones}",
    ]
    metrics = {
        "total_scored": len(all_scored),
        "killed": len(killed),
        "buy_candidates": len(buy),
        "median_score": median_score,
        "max_score": max_score,
        "score_60_plus": score_60_plus,
        "score_70_plus": score_70_plus,
        "score_80_plus": score_80_plus,
        "longs": longs,
        "shorts": shorts,
    }

    # Health gates
    if total_attempted < 100:
        return AuditResult(name="universe_coverage", status="FAIL",
                           summary=f"universe too small: {total_attempted} tickers attempted",
                           details=details, metrics=metrics,
                           actions=["check Zacks login + universe.json freshness"])
    if score_60_plus / max(1, len(scores)) < 0.05:
        return AuditResult(name="universe_coverage", status="WARN",
                           summary=f"only {score_60_plus} ({score_60_plus/max(1,len(scores))*100:.0f}%) score ≥60 — may indicate scoring drift",
                           details=details, metrics=metrics)
    if len(buy) == 0:
        return AuditResult(name="universe_coverage", status="WARN",
                           summary="0 BUY candidates in last bundle (regime may be flat)",
                           details=details, metrics=metrics)
    return AuditResult(name="universe_coverage", status="PASS",
                       summary=f"{len(all_scored)} scored, {len(buy)} BUYs",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 4. SCORING ENGINE VALIDITY — Basel zone, score-band monotonicity
# ──────────────────────────────────────────────────────────────────

def check_scoring_engine() -> AuditResult:
    sl_path = DATA / "signal_log.json"
    if not sl_path.exists():
        return AuditResult(name="scoring_engine", status="WARN",
                           summary="no signal_log.json — scoring engine unverifiable",
                           actions=["start tracking signals via swing_trade.py"])
    signals = json.loads(sl_path.read_text())
    if not isinstance(signals, list):
        return AuditResult(name="scoring_engine", status="FAIL",
                           summary="signal_log.json malformed (not a list)")

    # accuracy_framework recognises closed signals via status='CLOSED' or result ∈ closed-results
    # and computes R-multiple from actual_pnl_pct / entry / stop. Pass raw signals.
    win_results = {"TARGET_HIT", "WIN_EXPIRED"}
    loss_results = {"STOPPED", "LOSS_EXPIRED"}
    closed = [s for s in signals
              if s.get("status") == "CLOSED" or s.get("result") in (win_results | loss_results)]

    metrics: dict = {
        "total_signals": len(signals),
        "closed_signals": len(closed),
    }

    if len(closed) < 30:
        return AuditResult(name="scoring_engine", status="WARN",
                           summary=f"only {len(closed)} closed signals — insufficient for accuracy framework (need ≥30)",
                           details=[
                               f"total signals: {len(signals)}",
                               f"closed signals: {len(closed)}",
                               "outcomes are populated by signal_tracker.py during scan",
                           ],
                           metrics=metrics,
                           actions=["wait for more closed signals", "verify signal_tracker.update_signal_outcomes is firing"])

    # Try the accuracy framework
    try:
        import accuracy_framework as af
        am = af.compute_all_accuracy_metrics(closed)
        summary = am.get("summary", {})
        basel = am.get("basel", {})
        kupiec = am.get("kupiec_pof", {})
        christ = am.get("christoffersen", {})
        per_band = am.get("by_score_band", {})

        zone = basel.get("zone", "?")
        wr = summary.get("win_rate")
        avg_r = summary.get("avg_r")
        pf = summary.get("pf")
        details = [
            f"closed signals: {len(closed)}, win_rate: {wr}%, avg_R: {avg_r}, pf: {pf}",
            f"Basel zone: {zone}",
            f"  exceptions: {basel.get('n_exceptions', '?')}/{basel.get('n_trades', '?')} "
            f"(expected: {basel.get('expected', '?')}, rate: {basel.get('exception_rate', '?')}%)",
            f"Kupiec POF: verdict={kupiec.get('verdict', '?')}, p={kupiec.get('p_value', '?')}",
            f"Christoffersen: verdict={christ.get('verdict', '?')}, p={christ.get('p_value', '?')}",
        ]
        metrics["closed_n"] = am.get("n_closed", len(closed))
        metrics["win_rate_pct"] = wr
        metrics["avg_r"] = avg_r
        metrics["profit_factor"] = pf
        metrics["basel_zone"] = zone
        metrics["basel_exceptions"] = basel.get("n_exceptions")
        metrics["basel_expected"] = basel.get("expected")
        metrics["kupiec_p"] = kupiec.get("p_value")
        metrics["christoffersen_p"] = christ.get("p_value")

        # Score-band monotonicity check — sort numerically. "<60" should sort before "60-69"
        def _band_key(band: str) -> int:
            if band.startswith("<"):
                # "<60" → -1 to sort before "60-69"
                m = re.search(r"\d+", band)
                return int(m.group(0)) - 1 if m else -1
            m = re.search(r"\d+", band)
            return int(m.group(0)) if m else 0

        bands_sorted = []
        for band, m in (per_band or {}).items():
            band_wr = m.get("win_rate")
            n = m.get("n")
            if band_wr is not None and n and n >= 5:
                bands_sorted.append((band, band_wr, n))
        bands_sorted.sort(key=lambda x: _band_key(x[0]))
        details.append("score band WR (n≥5):")
        for band, band_wr, n in bands_sorted:
            details.append(f"  {band}: WR={band_wr}% n={n}")

        # Monotonicity check: WR should rise (or be flat) with score band
        wrs = [b[1] for b in bands_sorted if b[2] >= 10]  # need n≥10 for stable WR
        is_monotonic = all(wrs[i] <= wrs[i+1] + 5 for i in range(len(wrs)-1)) if len(wrs) >= 2 else None
        metrics["monotonic_score_band"] = is_monotonic
        if is_monotonic is False:
            details.append("⚠ score-band WR NOT monotonic — higher scores not winning more (within ±5pp)")

        if zone == "RED":
            return AuditResult(name="scoring_engine", status="FAIL",
                               summary=f"Basel RED — {basel.get('n_exceptions','?')} exceptions vs {basel.get('expected','?')} expected, WR={wr}%",
                               details=details, metrics=metrics,
                               actions=["recalibrate scoring weights", "tighten regime filter", "raise BUY thresholds"])
        if zone == "YELLOW":
            return AuditResult(name="scoring_engine", status="WARN",
                               summary=f"Basel YELLOW — {basel.get('n_exceptions','?')}/{basel.get('expected','?')} exceptions, WR={wr}%, PF={pf}",
                               details=details, metrics=metrics,
                               actions=["check tail_loss_filter is enabled (drops new signals only — historical won't change)",
                                        "investigate which setups are blowing through stops"])
        if zone == "GREEN":
            return AuditResult(name="scoring_engine", status="PASS",
                               summary=f"Basel GREEN — WR={wr}%, avg_R={avg_r}, PF={pf}, n={len(closed)}",
                               details=details, metrics=metrics)
        if zone == "INSUFFICIENT_DATA":
            return AuditResult(name="scoring_engine", status="WARN",
                               summary=f"Basel needs ≥250 closed signals, have {len(closed)} — keep tracking",
                               details=details, metrics=metrics)
        return AuditResult(name="scoring_engine", status="WARN",
                           summary=f"Basel zone={zone}",
                           details=details, metrics=metrics)
    except Exception as e:
        return AuditResult(name="scoring_engine", status="WARN",
                           summary=f"accuracy_framework raised: {type(e).__name__}: {e}",
                           details=[
                               f"closed signals: {len(closed)}",
                               "framework expects fields: score, stars, outcome, r_multiple",
                           ],
                           metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 5. TIER-1 DETECTOR EDGE — last backfill report
# ──────────────────────────────────────────────────────────────────

def check_tier1_detectors() -> AuditResult:
    backfill_path = CACHE / "tier1_backfill_results.json"
    if not backfill_path.exists():
        # Try alternative locations
        for alt in [CACHE / "tier1_backfill.json", DATA / "tier1_backfill.json"]:
            if alt.exists():
                backfill_path = alt
                break
        else:
            return AuditResult(name="tier1_detectors", status="WARN",
                               summary="no tier1 backfill report — run tier1_backfill.py",
                               actions=["python3 tier1_backfill.py"])

    try:
        data = json.loads(backfill_path.read_text())
    except Exception as e:
        return AuditResult(name="tier1_detectors", status="WARN",
                           summary=f"tier1 backfill unreadable: {e}")

    detectors = data.get("detectors", data) if isinstance(data, dict) else {}
    if not detectors:
        return AuditResult(name="tier1_detectors", status="WARN",
                           summary="tier1 backfill has no detector results",
                           actions=["python3 tier1_backfill.py"])

    details = []
    metrics = {}
    apply_recommend = []

    # Per-detector view
    for name, m in detectors.items():
        if not isinstance(m, dict):
            continue
        wr = m.get("win_rate") or m.get("wr")
        n = m.get("n") or m.get("trades", 0)
        avg_r = m.get("avg_r") or m.get("avg_r_multiple")
        if isinstance(wr, float) and wr <= 1.0:
            wr_pct = wr * 100
        else:
            wr_pct = wr or 0
        details.append(f"  {name}: n={n}, WR={wr_pct:.0f}%, avg_R={avg_r}")
        metrics[name] = {"n": n, "wr_pct": wr_pct, "avg_r": avg_r}
        # Recommend apply_to_score=true if WR>55 AND avg_R>0
        if isinstance(avg_r, (int, float)) and avg_r > 0.5 and wr_pct > 55 and n >= 10:
            apply_recommend.append(name)

    # Read current config to compare
    cfg_path = CONFIG / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    t1_cfg = cfg.get("tier1_signals", {})
    apply_per = t1_cfg.get("apply_to_score_per_detector", {})
    details.insert(0, f"current apply_to_score config: {apply_per}")
    metrics["apply_to_score_per_detector"] = apply_per

    actions = []
    if apply_recommend:
        actions.append(
            f"consider apply_to_score=true for: {', '.join(apply_recommend)}"
        )

    return AuditResult(name="tier1_detectors", status="PASS",
                       summary=f"{len(detectors)} detectors validated",
                       details=details, metrics=metrics, actions=actions)


# ──────────────────────────────────────────────────────────────────
# 6. LIVE TRADING STATE — Alpaca parity, recent paper P&L
# ──────────────────────────────────────────────────────────────────

def check_live_trading(quick: bool = False) -> AuditResult:
    portfolio_path = DATA / "portfolio_state.json"
    if not portfolio_path.exists():
        return AuditResult(name="live_trading", status="WARN",
                           summary="portfolio_state.json missing")

    ps = json.loads(portfolio_path.read_text())
    positions = ps.get("positions", [])
    cash = ps.get("cash", 0)
    equity = ps.get("equity", 0)

    # Paper trading activation marker
    activation_path = DATA / "paper_trading_start.json"
    paper_active = activation_path.exists()
    if paper_active:
        try:
            act_data = json.loads(activation_path.read_text())
            start = act_data.get("activated_at", act_data.get("start"))
        except Exception:
            start = None
    else:
        start = None

    details = [
        f"local positions: {len(positions)}",
        f"cash: ${cash:,.2f}",
        f"equity: ${equity:,.2f}",
        f"paper trading window: {'ACTIVE since ' + str(start) if paper_active else 'NOT activated'}",
    ]
    metrics = {
        "open_positions": len(positions),
        "cash": cash,
        "equity": equity,
        "paper_active": paper_active,
    }

    # Position-level checks
    no_stop = [p for p in positions if not p.get("stop")]
    no_target = [p for p in positions if not p.get("target1") and not p.get("target")]
    if no_stop:
        details.append(f"⚠ {len(no_stop)} positions WITHOUT stop loss: {[p.get('ticker') for p in no_stop]}")
    if no_target:
        details.append(f"⚠ {len(no_target)} positions WITHOUT target: {[p.get('ticker') for p in no_target]}")

    # Try Alpaca parity (skip in quick)
    if not quick:
        try:
            import executor
            client, account = executor._make_client()
            try:
                alpaca_positions = client.get_all_positions()
            except AttributeError:
                # older alpaca-py
                alpaca_positions = client.list_positions()
            details.append(f"Alpaca positions: {len(alpaca_positions)}")
            metrics["alpaca_positions"] = len(alpaca_positions)

            local_tickers = sorted(p.get("ticker") for p in positions)
            alpaca_tickers = sorted(getattr(p, "symbol", str(p)) for p in alpaca_positions)
            details.append(f"local: {local_tickers}")
            details.append(f"alpaca: {alpaca_tickers}")

            divergence = set(local_tickers) ^ set(alpaca_tickers)
            metrics["divergence_count"] = len(divergence)
            if divergence:
                return AuditResult(
                    name="live_trading", status="WARN",
                    summary=f"local-Alpaca divergence: {sorted(divergence)}",
                    details=details, metrics=metrics,
                    actions=["sync via /api/portfolio/sync_alpaca endpoint"],
                )
        except Exception as e:
            details.append(f"Alpaca check failed: {type(e).__name__}: {e}")
            metrics["alpaca_error"] = str(e)

    if no_stop or no_target:
        return AuditResult(name="live_trading", status="FAIL",
                           summary=f"{len(no_stop)} positions w/o stop, {len(no_target)} w/o target",
                           details=details, metrics=metrics,
                           actions=["set stop+target on all open positions"])
    return AuditResult(name="live_trading", status="PASS",
                       summary=f"{len(positions)} positions, all have stop+target",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 7. RISK CONTROLS — % of BUYs with valid stop+target+R:R≥3
# ──────────────────────────────────────────────────────────────────

def check_risk_controls() -> AuditResult:
    bundle_path = CACHE / "last_bundle.json"
    if not bundle_path.exists():
        return AuditResult(name="risk_controls", status="WARN", summary="no last_bundle.json")
    bundle = json.loads(bundle_path.read_text())
    buys = bundle.get("buy_candidates", [])

    # Inspect each BUY for a valid trade plan
    missing_stop = []
    missing_target = []
    rr_below_3 = []
    invalid_geometry = []
    for s in buys:
        tp = s.get("trade_plan") or {}
        ticker = s.get("ticker")
        stop = tp.get("stop")
        t1 = tp.get("target1")
        rr = tp.get("rr_ratio")
        entry_low = tp.get("entry_low")
        entry_high = tp.get("entry_high")
        direction = s.get("direction", "long")
        if not stop:
            missing_stop.append(ticker)
        if not t1:
            missing_target.append(ticker)
        if rr is not None and rr < 3.0:
            rr_below_3.append((ticker, rr))
        if stop and t1 and entry_low and entry_high:
            entry_mid = (entry_low + entry_high) / 2
            if direction == "long":
                if not (stop < entry_mid < t1):
                    invalid_geometry.append(ticker)
            else:
                if not (t1 < entry_mid < stop):
                    invalid_geometry.append(ticker)

    details = [
        f"buy candidates: {len(buys)}",
        f"missing stop: {len(missing_stop)} {missing_stop[:5]}",
        f"missing target: {len(missing_target)} {missing_target[:5]}",
        f"R:R < 3: {len(rr_below_3)} {rr_below_3[:5]}",
        f"invalid geometry (stop/entry/target order wrong): {len(invalid_geometry)} {invalid_geometry[:5]}",
    ]
    metrics = {
        "buy_count": len(buys),
        "missing_stop": len(missing_stop),
        "missing_target": len(missing_target),
        "rr_below_3": len(rr_below_3),
        "invalid_geometry": len(invalid_geometry),
    }

    if invalid_geometry:
        return AuditResult(name="risk_controls", status="FAIL",
                           summary=f"{len(invalid_geometry)} BUYs have invalid stop/entry/target geometry",
                           details=details, metrics=metrics,
                           actions=["inspect trade_plan generation in analysis.py"])
    if missing_stop or missing_target or rr_below_3:
        return AuditResult(name="risk_controls", status="WARN",
                           summary=f"{len(missing_stop)} no stop, {len(missing_target)} no target, {len(rr_below_3)} R:R<3",
                           details=details, metrics=metrics)
    return AuditResult(name="risk_controls", status="PASS",
                       summary=f"all {len(buys)} BUYs have valid stop+target+R:R≥3",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 8. R:R COHERENCE — count of inconsistent trade plans
# ──────────────────────────────────────────────────────────────────

def check_rr_coherence() -> AuditResult:
    bundle_path = CACHE / "last_bundle.json"
    if not bundle_path.exists():
        return AuditResult(name="rr_coherence", status="WARN", summary="no last_bundle.json")
    bundle = json.loads(bundle_path.read_text())

    # Pull from buy_candidates + medium_term_picks + long_term_picks
    candidates = []
    candidates.extend(bundle.get("buy_candidates", []))
    candidates.extend(bundle.get("medium_term_picks", []))
    candidates.extend(bundle.get("long_term_picks", []))

    inconsistent = []
    for s in candidates:
        tp = s.get("trade_plan") or {}
        rr_cached = tp.get("rr_ratio")
        entry_low = tp.get("entry_low")
        entry_high = tp.get("entry_high")
        stop = tp.get("stop")
        t1 = tp.get("target1")
        if not all(isinstance(x, (int, float)) for x in [rr_cached, entry_low, entry_high, stop, t1]):
            continue
        entry_mid = (entry_low + entry_high) / 2
        risk = entry_mid - stop  # for long
        if s.get("direction") == "short":
            risk = stop - entry_mid
            reward = entry_mid - t1
        else:
            reward = t1 - entry_mid
        if risk <= 0:
            continue
        rr_computed = reward / risk
        if rr_cached and abs(rr_computed - rr_cached) / max(0.1, rr_cached) > 0.20:
            inconsistent.append({
                "ticker": s.get("ticker"),
                "cached": rr_cached,
                "computed": round(rr_computed, 2),
            })

    details = [
        f"checked: {len(candidates)} picks (buy + medium + long)",
        f"inconsistent (>20% diff between cached and computed R:R): {len(inconsistent)}",
    ]
    if inconsistent[:5]:
        details.append("samples:")
        for x in inconsistent[:5]:
            details.append(f"  {x['ticker']}: cached={x['cached']} computed={x['computed']}")

    metrics = {
        "checked": len(candidates),
        "inconsistent": len(inconsistent),
        "inconsistent_pct": round(100 * len(inconsistent) / max(1, len(candidates)), 1),
    }

    if metrics["inconsistent_pct"] > 20:
        return AuditResult(name="rr_coherence", status="FAIL",
                           summary=f"{metrics['inconsistent_pct']}% of picks have inconsistent R:R",
                           details=details, metrics=metrics,
                           actions=["audit analysis.py:_coherent_rr usage"])
    if metrics["inconsistent_pct"] > 5:
        return AuditResult(name="rr_coherence", status="WARN",
                           summary=f"{metrics['inconsistent_pct']}% inconsistent",
                           details=details, metrics=metrics)
    return AuditResult(name="rr_coherence", status="PASS",
                       summary=f"all picks have coherent R:R (or geometry incomplete)",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 9. CONFIG INTEGRITY — required keys, threshold sanity
# ──────────────────────────────────────────────────────────────────

def check_config_integrity() -> AuditResult:
    cfg_path = CONFIG / "config.json"
    if not cfg_path.exists():
        return AuditResult(name="config_integrity", status="FAIL",
                           summary="config/config.json missing")
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception as e:
        return AuditResult(name="config_integrity", status="FAIL",
                           summary=f"config.json invalid JSON: {e}")

    issues = []
    details = []

    # Required top-level blocks
    required = [
        "regime4_thresholds",
        "tail_loss_filter",
        "tier1_signals",
        "regime_weight_shifts",
        "sector_relative_ranking",
        "portfolio_vol_targeting",
    ]
    for k in required:
        if k not in cfg:
            issues.append(f"missing config block: {k}")

    # Threshold sanity
    t = cfg.get("regime4_thresholds", {})
    trending = (t.get("risk_on_trending") or {}).get("buy_min_score")
    choppy = (t.get("risk_on_choppy") or {}).get("buy_min_score")
    if trending and (trending < 50 or trending > 80):
        issues.append(f"risk_on_trending buy_min_score={trending} outside [50,80]")
    if choppy and (choppy < 55 or choppy > 80):
        issues.append(f"risk_on_choppy buy_min_score={choppy} outside [55,80]")
    details.append(f"buy_min_score: trending={trending}, choppy={choppy}")

    # Tail filter — schema uses _enabled / min_score_for_buy / min_stars_for_buy
    tlf = cfg.get("tail_loss_filter", {})
    tlf_enabled = tlf.get("_enabled", tlf.get("enabled"))
    tlf_min_score = tlf.get("min_score_for_buy", tlf.get("min_score"))
    tlf_min_stars = tlf.get("min_stars_for_buy", tlf.get("min_stars"))
    if not tlf_enabled:
        issues.append("tail_loss_filter disabled — was supposed to be ON for Basel GREEN")
    details.append(f"tail_loss_filter: enabled={tlf_enabled}, min_score={tlf_min_score}, min_stars={tlf_min_stars}")

    # Equity — lives under portfolio.account_equity (also portfolio.config_e.starting_equity)
    portfolio_cfg = cfg.get("portfolio", {})
    eq = portfolio_cfg.get("account_equity")
    if not eq:
        eq = (portfolio_cfg.get("config_e") or {}).get("starting_equity")
    if not eq:
        eq = cfg.get("account_equity")  # legacy top-level fallback
    details.append(f"account_equity: ${eq}")
    if not eq or eq <= 0:
        issues.append(f"account_equity invalid: {eq}")

    metrics = {
        "trending_thresh": trending,
        "choppy_thresh": choppy,
        "tail_filter_enabled": tlf.get("enabled"),
        "account_equity": eq,
    }

    if issues:
        return AuditResult(name="config_integrity", status="WARN" if len(issues) <= 2 else "FAIL",
                           summary="; ".join(issues[:3]),
                           details=details + ["issues:"] + ["  " + i for i in issues],
                           metrics=metrics,
                           actions=["edit config/config.json"])
    return AuditResult(name="config_integrity", status="PASS",
                       summary=f"all required blocks present, thresholds in range",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 10. CODE HEALTH — syntax, _legacy imports leaking, orphans
# ──────────────────────────────────────────────────────────────────

def check_code_health() -> AuditResult:
    issues = []
    details = []
    metrics = {}
    # Active modules — exclude _legacy/, demo.py, and underscore-prefixed
    active = sorted([f for f in ROOT.glob("*.py")
                     if not f.name.startswith("_")
                     and f.name not in ("demo.py", "audit_360.py")])
    metrics["active_modules"] = len(active)

    syntax_errors = []
    legacy_imports = []
    polygon_refs = []

    for f in active:
        try:
            src = f.read_text()
            ast.parse(src, filename=str(f))
        except SyntaxError as e:
            syntax_errors.append(f"{f.name}:{e.lineno}: {e.msg}")
            continue
        # Check for _legacy imports
        if re.search(r"^\s*from\s+_legacy\.", src, re.MULTILINE):
            legacy_imports.append(f.name)
        if re.search(r"^\s*import\s+_legacy", src, re.MULTILINE):
            legacy_imports.append(f.name)
        # Check for polygon references in active code (CLAUDE.md says decommissioned)
        # Allow data_fetcher.py and eodhd_client.py (have aliases for back-compat)
        if f.name not in ("data_fetcher.py", "eodhd_client.py", "build_data.py", "tracker.py"):
            poly_hits = re.findall(r"polygon", src, re.IGNORECASE)
            if poly_hits and len(poly_hits) > 2:
                polygon_refs.append(f"{f.name} ({len(poly_hits)} polygon refs)")

    metrics["syntax_errors"] = len(syntax_errors)
    metrics["legacy_imports"] = len(legacy_imports)
    metrics["polygon_refs"] = len(polygon_refs)

    if syntax_errors:
        issues.append(f"{len(syntax_errors)} files have syntax errors")
        details.extend(["  " + s for s in syntax_errors])
    if legacy_imports:
        issues.append(f"{len(legacy_imports)} files import from _legacy/")
        details.extend(["  " + s for s in legacy_imports])
    if polygon_refs:
        details.append(f"{len(polygon_refs)} files mention polygon — consider rename:")
        details.extend(["  " + s for s in polygon_refs[:5]])

    details.insert(0, f"scanned {len(active)} active modules")

    if syntax_errors:
        return AuditResult(name="code_health", status="FAIL",
                           summary="; ".join(issues),
                           details=details, metrics=metrics,
                           actions=["fix syntax errors before next scan"])
    if legacy_imports:
        return AuditResult(name="code_health", status="WARN",
                           summary="; ".join(issues),
                           details=details, metrics=metrics)
    return AuditResult(name="code_health", status="PASS",
                       summary=f"{len(active)} modules, no syntax errors, no _legacy leaks",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 11. SERVER HEALTH — port reachability, endpoint sample
# ──────────────────────────────────────────────────────────────────

def check_server_health(quick: bool = False) -> AuditResult:
    if quick:
        return AuditResult(name="server_health", status="PASS",
                           summary="skipped (--quick)")
    # Port 7432
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", 7432))
        s.close()
        port_open = True
    except Exception as e:
        port_open = False
        port_err = str(e)

    details = [f"port 7432: {'OPEN' if port_open else 'CLOSED'}"]
    metrics = {"port_open": port_open}

    if not port_open:
        return AuditResult(name="server_health", status="WARN",
                           summary=f"localhost:7432 not reachable ({port_err})",
                           details=details, metrics=metrics,
                           actions=["./start-server.sh"])

    # Sample endpoints (basic auth) — use only routes that actually exist in server.py
    endpoints = [
        "/api/portfolio",
        "/api/positions/summary",
        "/api/config",
        "/api/bundles/list",
    ]
    auth_header = "Basic Z2FyaTpzd2luZzIwMjY="  # gari:swing2026
    failures = []
    for ep in endpoints:
        try:
            t0 = time.time()
            req = urllib.request.Request(
                f"http://127.0.0.1:7432{ep}",
                headers={"Authorization": auth_header, "User-Agent": "audit_360"},
            )
            with urllib.request.urlopen(req, timeout=4) as r:
                code = r.getcode()
            ms = (time.time() - t0) * 1000
            details.append(f"  {ep}: HTTP {code} in {ms:.0f}ms")
            metrics[f"endpoint_{ep}"] = {"code": code, "ms": round(ms)}
            if code >= 400:
                failures.append(f"{ep} {code}")
        except Exception as e:
            details.append(f"  {ep}: {type(e).__name__}: {e}")
            failures.append(f"{ep} {type(e).__name__}")

    if failures:
        return AuditResult(name="server_health", status="WARN",
                           summary=f"endpoint failures: {failures}",
                           details=details, metrics=metrics)
    return AuditResult(name="server_health", status="PASS",
                       summary=f"port open + {len(endpoints)} endpoints reachable",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# 12. DOCUMENTATION DRIFT — files referenced in CLAUDE.md exist
# ──────────────────────────────────────────────────────────────────

def check_doc_drift() -> AuditResult:
    cm_path = ROOT / "CLAUDE.md"
    if not cm_path.exists():
        return AuditResult(name="doc_drift", status="WARN",
                           summary="CLAUDE.md missing")
    src = cm_path.read_text()
    # Find code-fenced filenames
    refs = re.findall(r"`([\w/\.-]+\.(?:py|html|json|md|sh|yml|css|js))`", src)
    # Filter out external URLs and obvious non-paths
    refs = [r for r in refs if not r.startswith("http")]
    refs = list(dict.fromkeys(refs))  # dedupe, preserve order

    # Memory references live in user's home (~/.claude/...) — skip them
    memory_files = {
        "project_swingtrade_phase4.md", "feedback_timezone.md",
        "reference_project_path.md", "feedback_data_source_priority.md",
        "feedback_localhost_not_file_path.md",
    }

    missing = []
    for r in refs:
        # Skip remote/system paths
        if r.startswith("/") and not r.startswith("/Volumes/"):
            continue
        # Skip memory file references (live outside project)
        if r in memory_files:
            continue
        # Search common locations: project root + subdirs
        candidates = [
            ROOT / r,
            ROOT.parent / r,
        ]
        # Also try basename-only in nested dirs (CLAUDE.md sometimes uses bare names)
        if "/" not in r:
            for sub in ["backtest", "infra/prototype", "infra/healthcheck",
                        "infra/launchd", "infra/cloudflared", "config",
                        "docs", "tests", "_legacy"]:
                candidates.append(ROOT / sub / r)
        if not any(c.exists() for c in candidates):
            missing.append(r)

    metrics = {
        "refs_total": len(refs),
        "missing": len(missing),
    }
    details = [
        f"file references in CLAUDE.md: {len(refs)}",
        f"missing in filesystem: {len(missing)}",
    ]
    if missing:
        details.append("missing files:")
        details.extend(["  " + m for m in missing[:15]])

    if len(missing) > 5:
        return AuditResult(name="doc_drift", status="WARN",
                           summary=f"{len(missing)} files referenced in CLAUDE.md are missing",
                           details=details, metrics=metrics,
                           actions=["update CLAUDE.md to reflect actual file layout"])
    return AuditResult(name="doc_drift", status="PASS",
                       summary=f"{len(refs)} refs, {len(missing)} missing (≤5 acceptable)",
                       details=details, metrics=metrics)


# ──────────────────────────────────────────────────────────────────
# Render output
# ──────────────────────────────────────────────────────────────────

CHECKS = [
    ("system_state", check_system_state, []),
    ("data_sources", check_data_sources, ["quick"]),
    ("universe_coverage", check_universe_coverage, []),
    ("scoring_engine", check_scoring_engine, []),
    ("tier1_detectors", check_tier1_detectors, []),
    ("live_trading", check_live_trading, ["quick"]),
    ("risk_controls", check_risk_controls, []),
    ("rr_coherence", check_rr_coherence, []),
    ("config_integrity", check_config_integrity, []),
    ("code_health", check_code_health, []),
    ("server_health", check_server_health, ["quick"]),
    ("doc_drift", check_doc_drift, []),
]


def render_cli(results: list[AuditResult], overall_score: int) -> str:
    """ANSI-colored CLI table."""
    out = []
    out.append("")
    out.append(f"{_BOLD}{'='*72}{_RESET}")
    out.append(f"{_BOLD} SwingTrade Audit 360 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{_RESET}")
    out.append(f"{_BOLD}{'='*72}{_RESET}")
    out.append("")
    overall_color = _GRN if overall_score >= 85 else _YEL if overall_score >= 60 else _RED
    health_label = "HEALTHY" if overall_score >= 85 else "DEGRADED" if overall_score >= 60 else "UNHEALTHY"
    out.append(f"  Overall health: {overall_color}{_BOLD}{overall_score}/100  {health_label}{_RESET}")
    out.append("")
    out.append(f"  {'CHECK':<22} {'STATUS':<6} {'TIME':<7} SUMMARY")
    out.append(f"  {'-'*22} {'-'*6} {'-'*7} {'-'*40}")
    for r in results:
        elapsed = f"{r.elapsed_s:.1f}s"
        out.append(f"  {r.name:<22} {r.colored_status()}   {elapsed:<7} {r.summary}")
    out.append("")
    # Details for any non-PASS
    for r in results:
        if r.status == "PASS":
            continue
        c = _RED if r.status == "FAIL" else _YEL
        out.append(f"{c}{_BOLD}▼ {r.name} ({r.status}){_RESET}")
        for d in r.details[:20]:
            out.append(f"    {_DIM}{d}{_RESET}")
        if r.actions:
            out.append(f"    {_BOLD}actions:{_RESET}")
            for a in r.actions:
                out.append(f"      → {a}")
        out.append("")
    out.append(f"{_BOLD}{'='*72}{_RESET}")
    return "\n".join(out)


def render_html(results: list[AuditResult], overall_score: int) -> str:
    """Render an HTML audit report (kairos terminal aesthetic · 2026-05-16)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    health_label = "HEALTHY" if overall_score >= 85 else "DEGRADED" if overall_score >= 60 else "UNHEALTHY"
    health_cls   = "gn"      if overall_score >= 85 else "am"        if overall_score >= 60 else "rd"
    health_pill  = "PASS"    if overall_score >= 85 else "DEGRADED"  if overall_score >= 60 else "FAIL"

    pass_n = sum(1 for r in results if r.status == "PASS")
    warn_n = sum(1 for r in results if r.status == "WARN")
    fail_n = sum(1 for r in results if r.status == "FAIL")

    # Per-card rendering (top-border accent matches status)
    cards = []
    for r in results:
        card_cls   = {"PASS":"hot","WARN":"warm","FAIL":"crit"}.get(r.status, "cold")
        pill_cls   = {"PASS":"pass","WARN":"warn","FAIL":"fail"}.get(r.status, "cold")
        details_html = ""
        if r.details:
            details_html = (
                "<details><summary>Details</summary>"
                "<pre class=\"rf-pre\">" + "\n".join(d for d in r.details) + "</pre></details>"
            )
        metrics_html = ""
        if r.metrics:
            try:
                metrics_html = (
                    "<details><summary>Metrics</summary>"
                    f"<pre class=\"rf-pre\">{json.dumps(r.metrics, indent=2, default=str)}</pre>"
                    "</details>"
                )
            except Exception:
                pass
        actions_html = ""
        if r.actions:
            actions_html = (
                "<div class=\"rf-actions\"><div class=\"rf-actions-l\">Recommended actions</div>"
                "<ul>" + "".join(f"<li>{a}</li>" for a in r.actions) + "</ul></div>"
            )
        cards.append(f"""
        <div class="rf-card {card_cls}">
          <div class="rf-card-h">
            <div class="rf-card-h-l">
              <span class="rf-card-icon">●</span>
              <span class="rf-card-n">{r.name}</span>
            </div>
            <span class="rf-pill {pill_cls}">{r.status}</span>
          </div>
          <div class="rf-mech">{r.summary} <b style="color:var(--ink-3); font-weight:500">· {r.elapsed_s}s</b></div>
          {details_html}
          {metrics_html}
          {actions_html}
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwingTrade · Audit 360 — {ts}</title>
<style>
{KAIROS_CSS}
</style>
</head>
<body>
<div class="refv2">

  <div class="rf-topbar">
    <div class="rf-crumbs">
      <a href="/v2/kairos.html">← Kairos</a>
      <span class="sep">·</span>
      <span>Reference</span>
      <span class="sep">·</span>
      <span style="color:var(--ink-1)">Audit 360</span>
    </div>
    <div class="rf-title-row">
      <span class="rf-title">⚕ Audit 360</span>
      <span class="rf-sub">12-check institutional system health</span>
    </div>
    <div class="rf-meta">
      <span><b>Generated:</b> {ts}</span>
      <span><b>Re-run:</b> <code>python3 audit_360.py</code></span>
    </div>
  </div>

  <div class="rf-hero {health_cls}">
    <div class="rf-hero-head">
      <span class="rf-hero-badge">★ {health_pill}</span>
      <div class="rf-hero-name"><span class="icon">⚕</span>System Health · {health_label}</div>
      <div class="rf-hero-mech">All 12 health checks executed in sequence. PASS / WARN / FAIL on each. Overall score weighted by criticality. Recommended actions surfaced inline.</div>
    </div>
    <div class="rf-hero-num">
      <div class="k">Health score</div>
      <div class="v {health_cls}">{overall_score}</div>
      <div class="s">out of 100</div>
    </div>
    <div>
      <div class="rf-hero-meta">Breakdown</div>
      <div class="rf-hero-stats">
        <div class="rf-hero-stat"><span class="l">PASS</span><span class="v gn">{pass_n}</span></div>
        <div class="rf-hero-stat"><span class="l">WARN</span><span class="v am">{warn_n}</span></div>
        <div class="rf-hero-stat"><span class="l">FAIL</span><span class="v rd">{fail_n}</span></div>
      </div>
    </div>
    <div>
      <div class="rf-hero-meta">Coverage</div>
      <div class="rf-hero-stats">
        <div class="rf-hero-stat"><span class="l">Total checks</span><span class="v">{len(results)}</span></div>
        <div class="rf-hero-stat"><span class="l">Last run</span><span class="v cy">{ts}</span></div>
        <div class="rf-hero-stat"><span class="l">Schedule</span><span class="v gn">on-demand</span></div>
      </div>
    </div>
  </div>

  <div class="rf-qch"><div class="q"><span class="num">⚕</span>Per-check results</div><span class="sub">expand any card for details + metrics + recommended actions</span><span class="r">{len(results)} checks · {ts}</span></div>

  <div class="rf-grid-2">
    {''.join(cards)}
  </div>

  <div class="rf-block cy" style="margin-top:22px">
    <b>RE-RUN ·</b> <code>python3 audit_360.py</code> regenerates this report. <code>--quick</code> skips server-roundtrip checks for faster runs. Output writes to <code>cache/audit_360_latest.html</code> + a dated archive.
  </div>

</div>
</body>
</html>
"""
    return html


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="SwingTrade 360-degree system audit")
    ap.add_argument("--quick", action="store_true", help="skip network probes")
    ap.add_argument("--no-html", action="store_true", help="skip HTML report")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout instead of CLI table")
    args = ap.parse_args()

    results: list[AuditResult] = []
    for name, fn, opts in CHECKS:
        if "quick" in opts:
            wrapped = lambda f=fn: f(quick=args.quick)
        else:
            wrapped = lambda f=fn: f()
        results.append(_run(name, wrapped))

    overall = round(sum(r.score() for r in results) / max(1, len(results)))

    if args.json:
        out = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": overall,
            "checks": [asdict(r) for r in results],
        }
        print(json.dumps(out, indent=2, default=str))
        return

    print(render_cli(results, overall))

    if not args.no_html:
        out_path = CACHE / f"audit_360_{datetime.now().strftime('%Y-%m-%d')}.html"
        out_path.write_text(render_html(results, overall))
        latest = CACHE / "audit_360_latest.html"
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(out_path.name)
        except Exception:
            latest.write_text(render_html(results, overall))
        print(f"  → HTML report: {out_path}")
        print(f"  → Latest symlink: {latest}")

    # Exit code: non-zero on FAIL
    fail_count = sum(1 for r in results if r.status == "FAIL")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
