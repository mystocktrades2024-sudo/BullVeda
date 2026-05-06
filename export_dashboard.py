"""
Export a fully self-contained dashboard HTML that works offline.
No server needed — all data, CSS, and JS embedded inline.
Share the output file with anyone; they just open it in a browser.

Usage:
    python3 export_dashboard.py
    # Output: cache/dashboard_standalone.html
"""

from pathlib import Path
import re

BASE_DIR = Path(__file__).parent
CACHE = BASE_DIR / "cache"


def export_standalone(output_name: str = "dashboard_standalone.html") -> Path:
    html_path = CACHE / "dashboard.html"
    css_path = CACHE / "dashboard.css"
    js_path = CACHE / "dashboard.js"
    data_path = CACHE / "dashboard-data.js"
    out_path = CACHE / output_name

    html = html_path.read_text(encoding="utf-8")

    # Inline CSS
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        html = html.replace(
            '<link rel="stylesheet" href="dashboard.css">',
            f"<style>{css}</style>"
        )
        # Also try alternate link formats
        html = re.sub(
            r'<link[^>]+dashboard\.css[^>]*>',
            f"<style>{css}</style>",
            html
        )

    # Inline JS
    if js_path.exists():
        js = js_path.read_text(encoding="utf-8")
        html = html.replace(
            '<script src="dashboard.js"></script>',
            f"<script>{js}</script>"
        )

    # Inline ST_DATA — use string find/replace to avoid regex issues with \u escapes
    if data_path.exists():
        data = data_path.read_text(encoding="utf-8")
        # Find the script tag that loads dashboard-data.js
        marker = 'src="dashboard-data.js"'
        idx = html.find(marker)
        if idx >= 0:
            # Find the enclosing <script ...>...</script>
            tag_start = html.rfind("<script", 0, idx)
            tag_end = html.find("</script>", idx) + len("</script>")
            if tag_start >= 0 and tag_end > tag_start:
                html = html[:tag_start] + f"<script>{data}</script>" + html[tag_end:]

    # Patch fetch calls to not hit localhost (show "offline" message instead)
    html = html.replace(
        "fetch(_baseUrl + '/api/analyze/'+ticker)",
        "Promise.reject(new Error('Offline mode — data from last scan only'))"
    )
    html = html.replace(
        "fetch('/api/analyze/' + ticker)",
        "Promise.reject(new Error('Offline mode — data from last scan only'))"
    )

    out_path.write_text(html, encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"✓ Exported: {out_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Share this file — opens in any browser, no server needed.")
    print(f"  All {len(re.findall(r'ST_DATA', html))} ticker analyses embedded inline.")
    return out_path


if __name__ == "__main__":
    export_standalone()
