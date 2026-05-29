#!/usr/bin/env python3
"""Re-inject the Aurora design CSS into infra/prototype/Stocksmith.html.

WORKFLOW for design updates from Claude Design
----------------------------------------------
1. Re-export / re-fetch the design bundle. Overwrite the changed file(s) in
   THIS folder (design/stocksmith/ for CSS, design/stocksmith/src/ for JSX).
2. VISUAL change (any *.css)  ->  run:  python3 design/stocksmith/build_stocksmith.py
   That re-concatenates the CSS in load order and swaps ONLY the first <style>
   block in Stocksmith.html. The supplemental <style> and ALL JSX are untouched.
3. STRUCTURE / DATA change (home.jsx etc.)  ->  diff the new src against this
   baseline, port the markup delta into Stocksmith.html by hand, and wire any
   NEW field to its real /v2 source (see FIELD_MAP in MANIFEST.md). Then commit
   the updated baseline so the next diff is clean.

The first <style> block in Stocksmith.html is, by construction, the design CSS.
The second <style> block is Stocksmith-only chrome (loading / empty / toast).
"""
import re, pathlib

REF  = pathlib.Path(__file__).resolve().parent
ROOT = REF.parents[1]                      # SwingTrade/
HTML = ROOT / "infra" / "prototype" / "Stocksmith.html"

# Load order matters (later files override earlier; tqp styles live in vh-rich).
ORDER = [
    "tokens.css", "components.css", "shell.css", "aurora.css", "visual-rich.css",
    "user-menu.css", "home-hero.css", "home-cards.css", "home-discovery.css",
    "themes-extra.css", "tier.css", "vh-rich.css",
    # surfaces (added 2026-05-28 for User Management)
    "workspaces.css", "surface-lab.css", "surface-news.css", "surface-users.css",
]

def main():
    parts = []
    for f in ORDER:
        p = REF / f
        if p.exists():
            parts.append(f"/* ===== {f} ===== */\n{p.read_text()}")
        else:
            print(f"  (skip — missing {f})")
    css = "\n".join(parts)
    html = HTML.read_text()
    new, n = re.subn(r"<style>.*?</style>", "<style>\n" + css + "\n</style>", html, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("ERROR: could not locate the first <style> block in Stocksmith.html")
    HTML.write_text(new)
    print(f"re-injected {len(css):,} chars of design CSS from {len(parts)} files into {HTML.name}")

if __name__ == "__main__":
    main()
