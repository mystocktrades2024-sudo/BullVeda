#!/usr/bin/env python3
"""smoke_test_modules.py — CapStudio modular system smoke test.

Walks every module in the registry and:
  1. Verifies the file exists on disk
  2. Validates JS syntax via `node --check`
  3. Confirms the server route returns expected HTTP code (401 or 200)
  4. Cross-checks dashboard.html exposures (window.X) needed by modules
  5. Reports any orphan `window.X = X` lines pointing at deleted identifiers
  6. Confirms no top-level call statements to deleted helpers

Run: python3 scripts/smoke_test_modules.py
Exits non-zero on any failure — suitable for pre-commit / CI.

(CapStudio test coverage 2026-05-09 — minimal pure-Python alternative to
Playwright that doesn't require npm install or browser. Future: add a
Playwright suite for full browser-side render verification.)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO = ROOT / "infra" / "prototype"
REG_PATH = ROOT / "data" / "capability_registry.json"

# Identifiers we know were folded out of dashboard.html — any orphan reference
# at top-level (outside an inline HTML attribute) means a parse-time bug.
DELETED_HELPERS = {
    'seFilterStrategies', '_earnFilterChange', '_earnSearch',
    '_auditLivePoll', '_tradingDaysSince', 'auditToggleExpand',
    '_renderAuditDetailPanel', '_startAuditPolling', 'auditClearFilters',
    'auditExportCsv', 'auditPresetRange', 'auditPresetYtd', 'auditPresetAll',
    '_markPresetActive', '_stgBuildTree', '_stgRenderConfig',
    '_stgToggleNode', '_stgToggleTab', '_stgToggleGroup', '_stgFilter',
    '_stgSave', '_stgResetToProfile', '_stgExport', '_selectProfile',
}

failures: list[str] = []


def fail(msg: str):
    failures.append(msg)
    print(f"  ✗ {msg}")


def ok(msg: str):
    print(f"  ✓ {msg}")


# ── 1. Registry → file existence + JS syntax ──────────────────────────
def check_registry_modules():
    print("\n[1] Registry → module files exist + parse")
    reg = json.loads(REG_PATH.read_text())
    missing, parse_fails = 0, 0
    for category in ("tabs", "sub_tabs"):
        for k, v in (reg.get(category) or {}).items():
            paths = []
            if v.get("module"):  paths.append(v["module"])
            for e in (v.get("extras") or []): paths.append(e)
            for p in paths:
                full = PROTO / p
                if not full.exists():
                    fail(f"{category}.{k}: missing module file {p}")
                    missing += 1
                    continue
                # node --check
                r = subprocess.run(["node", "--check", str(full)], capture_output=True, text=True)
                if r.returncode != 0:
                    fail(f"{category}.{k}: {p} — JS syntax error: {r.stderr.strip()[:200]}")
                    parse_fails += 1
    if missing == 0 and parse_fails == 0:
        ok(f"All registry-referenced modules exist + parse (checked tabs + sub_tabs)")


# ── 2. core/ modules parse ────────────────────────────────────────────
def check_core_modules():
    print("\n[2] core/*.js parse cleanly")
    for f in sorted((PROTO / "core").glob("*.js")):
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            fail(f"core/{f.name} — JS syntax error: {r.stderr.strip()[:200]}")
        else:
            ok(f"core/{f.name}")


# ── 3. Main script blocks of dashboard.html + elite-detail.html ──────
def extract_main_script(html_path: Path) -> str:
    src = html_path.read_text()
    blocks = re.findall(r"<script>(.*?)</script>", src, re.S)
    return max(blocks, key=len)


def check_inline_scripts():
    print("\n[3] Main inline <script> blocks parse")
    for name in ("dashboard.html", "elite-detail.html"):
        body = extract_main_script(PROTO / name)
        tmp = Path("/tmp") / f"_{name}.js"
        tmp.write_text(body)
        r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
        if r.returncode != 0:
            fail(f"{name} main script — {r.stderr.strip()[:200]}")
        else:
            ok(f"{name} main script ({body.count(chr(10))} lines)")
        tmp.unlink(missing_ok=True)


# ── 4. No top-level orphan calls to deleted helpers ─────────────────
def check_orphan_calls():
    print("\n[4] No top-level orphan calls to deleted helpers")
    src = (PROTO / "dashboard.html").read_text()
    found = 0
    for i, line in enumerate(src.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("//"): continue
        if line.startswith(" ") or line.startswith("\t"): continue  # skip indented (not top-level)
        m = re.match(r"^(\w+)\s*\(", stripped)
        if not m: continue
        if m.group(1) in DELETED_HELPERS:
            fail(f"dashboard.html:{i}: orphan top-level call: {line.strip()[:100]}")
            found += 1
    if found == 0:
        ok("No orphan top-level calls")


# ── 5. No orphan `window.X = X` lines pointing at deleted identifiers ─
def check_orphan_window_assigns():
    print("\n[5] No `window.X = X` orphans for deleted helpers")
    src = (PROTO / "dashboard.html").read_text()
    found = 0
    for i, line in enumerate(src.splitlines(), start=1):
        m = re.match(r"^window\.(\w+)\s*=\s*\1\s*;", line.strip())
        if m and m.group(1) in DELETED_HELPERS:
            fail(f"dashboard.html:{i}: orphan window.{m.group(1)} = {m.group(1)}")
            found += 1
    if found == 0:
        ok("No orphan window.X = X assignments")


# ── 6. Required window exposures present ─────────────────────────────
def check_window_exposures():
    print("\n[6] Required window exposures (shell.js dependencies)")
    src = (PROTO / "dashboard.html").read_text()
    required = ["TAB_RENDERERS", "_getDashboardData", "STRATEGIES",
                "AUDIT_DAY_COLS", "AUDIT_WEEK_COLS", "AUDIT_MONTH_COLS"]
    for sym in required:
        pat = rf"window\.{re.escape(sym)}\s*="
        if re.search(pat, src):
            ok(f"window.{sym} exposed")
        else:
            fail(f"MISSING window.{sym}")
    # elite-detail dependencies
    src2 = (PROTO / "elite-detail.html").read_text()
    for sym in ["_getDetailTicker", "__getDetailTicker"]:
        if re.search(rf"window\.{re.escape(sym)}\s*=", src2):
            ok(f"elite-detail: window.{sym}")
        else:
            fail(f"MISSING elite-detail: window.{sym}")


# ── 7. Routes respond (server must be running) ─────────────────────
def check_routes():
    print("\n[7] Server routes respond (401 = registered + auth-gated)")
    routes = [
        "/kairos.html", "/kairos.html", "/v2/_v",
        "/v2/core/shell.js", "/v2/core/shared.js", "/v2/core/drawer.js",
        "/v2/core/actions.js", "/v2/core/widgets.js",
        "/v2/core/elite-detail-shell.js",
        "/api/capability-registry", "/api/roles", "/api/me",
    ]
    for r in routes:
        url = f"http://localhost:7432{r}"
        # /api/* endpoints only accept GET; /v2/* support HEAD (FastAPI's api_route)
        method = "GET" if r.startswith("/api/") else "HEAD"
        try:
            req = urllib.request.Request(url, method=method)
            try:
                with urllib.request.urlopen(req, timeout=3) as resp:
                    code = resp.status
            except urllib.error.HTTPError as e:
                code = e.code
            if code in (200, 401):
                ok(f"{r} ({method}) → {code}")
            else:
                fail(f"{r} ({method}) → unexpected {code}")
        except Exception as e:
            fail(f"{r} → exception: {e}")


# ── 8. Capability registry self-consistency ───────────────────────
def check_registry_self():
    print("\n[8] Registry self-consistency")
    reg = json.loads(REG_PATH.read_text())
    group_ids = {g["id"] for g in (reg.get("groups") or [])}
    for cat in ("tabs", "sub_tabs", "actions"):
        for k, v in (reg.get(cat) or {}).items():
            g = v.get("group")
            if g and g not in group_ids:
                fail(f"{cat}.{k}.group='{g}' not in groups list")
    ok(f"Groups consistent ({len(group_ids)} groups)")


def main():
    if not REG_PATH.exists():
        print(f"✗ Registry not found: {REG_PATH}")
        sys.exit(2)
    print(f"CapStudio smoke test — {ROOT}")
    print("=" * 60)
    check_registry_modules()
    check_core_modules()
    check_inline_scripts()
    check_orphan_calls()
    check_orphan_window_assigns()
    check_window_exposures()
    check_routes()
    check_registry_self()
    print("\n" + "=" * 60)
    if failures:
        print(f"✗ {len(failures)} failure(s):")
        for f in failures: print(f"   - {f}")
        sys.exit(1)
    print(f"✓ ALL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
