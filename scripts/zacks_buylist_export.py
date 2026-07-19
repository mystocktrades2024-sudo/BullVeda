#!/usr/bin/env python3
"""
Zacks Rank #1 Buy-List → Excel exporter  (standalone daily job)

Scrapes https://www.zacks.com/stocks/buy-list/ (Zacks Premium "Zacks #1 Rank"
list), parses ticker + VGM grades, cross-references our own engine verdict from
the latest scan bundle, and writes a dated + a "latest" Excel workbook.

WHY THIS IS A SEPARATE JOB (not part of the scan):
  The owner disabled Zacks inside the scan on 2026-06-03 (`config.skip_zacks`)
  because the Selenium/undetected-chromedriver login is the system's most
  fragile dependency — a Chrome auto-update → driver mismatch once crashed the
  scan itself. This exporter is fully ISOLATED: it reuses the login helper but
  runs in its own launchd job, wrapped so any failure only skips the Excel
  export and never touches the scan, the bundle, or any downstream state.
  It also does NOT flip `skip_zacks`; the scan stays Zacks-free.

Outputs (cache/, gitignored):
  cache/zacks_buylist_YYYYMMDD.xlsx   — dated snapshot
  cache/zacks_buylist_latest.xlsx     — stable path for humans
  cache/zacks_buylist_latest.json     — machine-readable snapshot

Usage:
  python3 scripts/zacks_buylist_export.py            # scrape + export
  python3 scripts/zacks_buylist_export.py --dry-run  # login+parse, no files
  python3 scripts/zacks_buylist_export.py --from-cache  # skip scrape, re-export last JSON
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

CREDS_PATH = BASE_DIR / "config" / "zacks_credentials.json"
CACHE_DIR = BASE_DIR / "cache"
LOG_DIR = CACHE_DIR / "logs"
BUNDLE_PATH = CACHE_DIR / "last_bundle.json"
JSON_SNAPSHOT = CACHE_DIR / "zacks_buylist_latest.json"
# Output folder — lives inside MasterAlgo's served cache so the workbook is both
# downloadable and its JSON is fetchable by the MasterAlgo "My Picks" tab at
# /MASTERALGO/Zacks/. Falls back to a local ./Zacks if MasterAlgo isn't present.
_MASTERALGO_CACHE = Path("/Volumes/MyMacDisk/Claude Skills/MasterAlgo/cache")
OUTPUT_DIR = (_MASTERALGO_CACHE / "Zacks") if _MASTERALGO_CACHE.exists() else (BASE_DIR / "Zacks")
WEB_PICKS_JSON = OUTPUT_DIR / "picks.json"
BUY_LIST_URL = "https://www.zacks.com/stocks/buy-list/"
BEST_STOCKS_URL = "https://www.zacks.com/featured-articles/101/best-stocks-to-buy-now"
TOP_MOVERS_URL = "https://www.zacks.com/ultimate/top_movers.php"

GRADES = {"A", "A+", "A-", "B", "B+", "B-", "C", "C+", "C-", "D", "D+", "D-", "F"}
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

log = logging.getLogger("zacks_buylist")


def _now_pt() -> datetime:
    return datetime.now(ZoneInfo("America/Los_Angeles"))


def _chrome_major() -> int | None:
    """Detect the installed Chrome major version so undetected-chromedriver
    matches it. Avoids the hard-pinned version_main=146 in data_fetcher that
    breaks on every Chrome auto-update (the owner's #1 fragility)."""
    import subprocess
    try:
        out = subprocess.check_output([CHROME_BIN, "--version"], text=True, timeout=10)
        m = re.search(r"(\d+)\.\d+\.\d+", out)
        return int(m.group(1)) if m else None
    except Exception as e:
        log.warning("Chrome version detect failed (%s) — letting uc auto-match", e)
        return None


def _login_driver(creds: dict):
    """Self-contained Zacks Ultimate login. Own driver (dynamic Chrome version),
    NOT data_fetcher._ultimate_login_driver (which pins version_main=146)."""
    import time

    import undetected_chromedriver as uc

    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")

    kwargs = {"options": opts, "use_subprocess": True}
    major = _chrome_major()
    if major:
        kwargs["version_main"] = major
        log.info("Launching undetected-chromedriver for Chrome %d", major)
    driver = uc.Chrome(**kwargs)
    # Harden against slow morning loads / ChromeDriver command-channel hangs — the
    # 5AM job died on a single 120s WebDriver ReadTimeoutError. Give commands, page
    # loads, and scripts more room than the defaults.
    try:
        driver.command_executor.set_timeout(240)
    except Exception:
        pass
    try:
        driver.set_page_load_timeout(90)
        driver.set_script_timeout(60)
    except Exception:
        pass

    driver.get("https://www.zacks.com/ultimate/")
    time.sleep(4)
    try:
        driver.execute_script("var c=document.getElementById('accept_cookie');if(c)c.click()")
        time.sleep(1)
    except Exception:
        pass
    driver.execute_script(f"""
        var inputs=document.querySelectorAll(
            'input[type=text],input[type=email],input[name*=user],input[name*=email]');
        var pwds=document.querySelectorAll('input[type=password]');
        for(var i=0;i<inputs.length;i++){{
            inputs[i].value={json.dumps(creds["username"])};
            inputs[i].dispatchEvent(new Event('input',{{bubbles:true}}));
        }}
        for(var i=0;i<pwds.length;i++){{
            pwds[i].value={json.dumps(creds["password"])};
            pwds[i].dispatchEvent(new Event('input',{{bubbles:true}}));
        }}
        var btns=document.querySelectorAll('input[type=submit],button[type=submit]');
        if(btns.length>0)btns[0].click();
    """)
    time.sleep(6)
    return driver


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------
def scrape_all() -> dict:
    """Login ONCE and scrape both Zacks pages in the same session.

    Returns {"buy_list": [...], "best_stocks": [...]}.
    buy_list row : {symbol, company, price, value, growth, momentum, vgm}
    best_stocks  : {symbol, company, price, chg_12w, fwd_pe, eps_growth_1y, sales_growth_1y}
    Raises on hard failure (no driver / no login) so the caller logs + exits.
    """
    import time

    from bs4 import BeautifulSoup

    if not CREDS_PATH.exists():
        raise FileNotFoundError(f"Zacks credentials not found: {CREDS_PATH}")
    creds = json.loads(CREDS_PATH.read_text())

    driver = _login_driver(creds)
    if driver is None:
        raise RuntimeError("Zacks login failed (driver init returned None)")

    try:
        # ── Page 1: Zacks Rank #1 buy list ──────────────────────────────────
        driver.get(BUY_LIST_URL)
        time.sleep(3)
        try:  # ask DataTables to render all rows (not just the first page)
            driver.execute_script(
                """
                document.querySelectorAll('.dataTables_length select').forEach(function(s){
                    s.value='-1';
                    s.dispatchEvent(new Event('change',{bubbles:true}));
                });
                """
            )
            time.sleep(2)
        except Exception:
            pass
        buy_list = _parse_table(BeautifulSoup(driver.page_source, "html.parser"))
        if not buy_list:
            raise RuntimeError(
                "Buy-list table parsed 0 rows — page layout may have changed "
                "or the session was blocked by Incapsula."
            )
        log.info("Parsed %d Zacks Rank #1 tickers", len(buy_list))

        # ── Page 2: Best Stocks to Buy Now (curated featured list) ───────────
        best_stocks = []
        try:
            driver.get(BEST_STOCKS_URL)
            time.sleep(4)
            best_stocks = _parse_best_stocks(BeautifulSoup(driver.page_source, "html.parser"))
            log.info("Parsed %d 'Best Stocks to Buy Now' names", len(best_stocks))
        except Exception as e:
            log.warning("Best Stocks page failed (non-fatal): %s", e)

        # ── Page 3: All Open Trades (Ultimate) ──────────────────────────────
        all_trades = []
        try:
            driver.get(TOP_MOVERS_URL)
            time.sleep(5)
            soup_tm = BeautifulSoup(driver.page_source, "html.parser")
            all_trades = _parse_movers_table(soup_tm, "all_trades_sortable")
            log.info("Parsed %d All Open Trades", len(all_trades))
        except Exception as e:
            log.warning("All Open Trades page failed (non-fatal): %s", e)

        return {"buy_list": buy_list, "best_stocks": best_stocks, "all_trades": all_trades}
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _parse_best_stocks(soup) -> list[dict]:
    """Parse the 'Best Stocks to Buy Now' featured-table-view curated list."""
    table = soup.find("table", class_="featured-table-view")
    if not table:
        # fallback: first table with quote links
        for t in soup.find_all("table"):
            if t.find("a", href=re.compile(r"/stock/quote/")):
                table = t
                break
    rows: list[dict] = []
    if not table:
        return rows

    trs = table.find_all("tr")
    # Company is a <th> in each row, other columns are <td> — include both so
    # header indices (0..N) align with cell indices.
    headers = [th.get_text(" ", strip=True).lower() for th in trs[0].find_all(["th", "td"])]

    def col(needles, exclude=()):
        for i, h in enumerate(headers):
            if any(n in h for n in needles) and not any(x in h for x in exclude):
                return i
        return None

    i_chg = col(["price change", "12 week", "12-week"])
    i_pe = col(["forward pe", "forward p/e", "fwd pe"])
    i_price = col(["price"], exclude=["change"])   # avoid "12 Week Price Change"
    i_eps = col(["eps growth", "proj eps"])
    i_sales = col(["sales growth", "projected sales"])

    seen = set()
    for tr in trs[1:]:
        cells = tr.find_all(["th", "td"])
        link = tr.find("a", href=re.compile(r"/stock/quote/"))
        if not link:
            continue
        m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
        if not m:
            continue
        sym = m.group(1).replace(".", "-").upper()
        if sym in seen:
            continue
        seen.add(sym)
        # company: first cell text minus the ticker/paren
        c0 = cells[0].get_text(" ", strip=True) if cells else ""
        company = c0.split("(")[0].strip()  # drop "( TICKER Quick Quote TICKER )"

        def g(i):
            return cells[i].get_text(" ", strip=True).lstrip("$") if (i is not None and i < len(cells)) else ""
        rows.append({
            "symbol": sym,
            "company": company,
            "price": g(i_price),
            "chg_12w": g(i_chg),
            "fwd_pe": g(i_pe),
            "eps_growth_1y": g(i_eps),
            "sales_growth_1y": g(i_sales),
        })
    return rows


def _parse_movers_table(soup, table_id: str) -> list[dict]:
    """Parse a Zacks Ultimate movers/trades table by id.
    Columns: Company | Sym | Type | +Date | $Add | $Last | %Chg | Service.
    id=30_day_sortable → 30-day top movers; id=all_trades_sortable → all open trades."""
    table = soup.find("table", id=table_id)
    if not table:
        return []
    rows: list[dict] = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue
        link = tr.find("a", href=re.compile(r"/stock/quote/"))
        m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"]) if link else None
        if not m:
            continue
        sym = m.group(1).replace(".", "-").upper()

        def c(i):
            return cells[i].get_text(" ", strip=True) if i < len(cells) else ""
        rows.append({
            "symbol": sym,
            "company": c(0).replace("Quick Quote", "").strip(),
            "type": c(2),
            "date_added": c(3),
            "price_add": c(4).lstrip("$"),
            "price_last": c(5).lstrip("$"),
            "pct_chg": c(6),
            "service": c(7),
        })
    return rows


def _parse_table(soup) -> list[dict]:
    """Parse the Zacks buy-list table (mirror of data_fetcher's logic, isolated)."""
    table = soup.find("table", id="full_one_list_table_full_one_list")
    rows: list[dict] = []
    if not table:
        # Fallback: any quote link on the page → symbol only
        seen = set()
        for link in soup.find_all("a", href=re.compile(r"/stock/quote/")):
            m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
            if m:
                t = m.group(1).replace(".", "-").upper()
                if t not in seen:
                    seen.add(t)
                    rows.append({"symbol": t, "company": "", "price": "",
                                 "value": "—", "growth": "—", "momentum": "—", "vgm": "—"})
        return rows

    # Detect VGM grade columns by voting on which columns hold A–F grades
    grade_votes: dict[int, int] = {}
    for tr in table.find_all("tr")[1:10]:
        for i, c in enumerate(tr.find_all("td")):
            if c.get_text(strip=True).upper() in GRADES:
                grade_votes[i] = grade_votes.get(i, 0) + 1
    gcols = sorted([i for i, n in grade_votes.items() if n >= 2])
    val_i = gcols[0] if len(gcols) > 0 else None
    gro_i = gcols[1] if len(gcols) > 1 else None
    mom_i = gcols[2] if len(gcols) > 2 else None
    vgm_i = gcols[3] if len(gcols) > 3 else None

    def _grade(cells, idx):
        if idx is None or idx >= len(cells):
            return "—"
        cell = cells[idx]
        g = cell.get_text(strip=True)
        if g.upper() in GRADES:
            return g
        for span in cell.find_all(["span", "div"]):
            sv = span.get_text(strip=True)
            if sv.upper() in GRADES:
                return sv
        return g or "—"

    seen = set()
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        link = tr.find("a", href=re.compile(r"/stock/quote/"))
        if not link:
            continue
        m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
        if not m:
            continue
        sym = m.group(1).replace(".", "-").upper()
        if sym in seen:
            continue
        seen.add(sym)

        # company: first cell text that isn't the symbol / a grade / a number
        company = ""
        price = ""
        for c in cells:
            txt = c.get_text(" ", strip=True)
            if not txt:
                continue
            if not price and re.fullmatch(r"\$?\d[\d,]*\.?\d*", txt.replace(",", "")):
                price = txt.lstrip("$")
            elif (not company and txt.upper() != sym and txt.upper() not in GRADES
                  and not re.fullmatch(r"[\d.,$%+\-]+", txt) and len(txt) > 2):
                company = txt
        rows.append({
            "symbol": sym,
            "company": company,
            "price": price,
            "value": _grade(cells, val_i),
            "growth": _grade(cells, gro_i),
            "momentum": _grade(cells, mom_i),
            "vgm": _grade(cells, vgm_i),
        })
    return rows


# ---------------------------------------------------------------------------
# Enrich with our engine verdict (best-effort, from the latest scan bundle)
# ---------------------------------------------------------------------------
def load_engine_verdicts() -> dict[str, dict]:
    if not BUNDLE_PATH.exists():
        return {}
    try:
        bundle = json.loads(BUNDLE_PATH.read_text())
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for r in bundle.get("all_scored", []) or []:
        t = r.get("ticker")
        if not t:
            continue
        v = r.get("verdict")
        verdict = v.get("verdict") if isinstance(v, dict) else (v or r.get("decision"))
        out[t] = {
            "our_verdict": verdict or "",
            "our_score": r.get("score") if isinstance(r.get("score"), (int, float)) else r.get("raw_score"),
            "entry_quality": r.get("entry_quality") or "",
            "setup_family": r.get("setup_family") or "",
        }
    return out


# ---------------------------------------------------------------------------
# Excel writer
# ---------------------------------------------------------------------------
SRC_ORDER = ["Zacks Rank #1", "Best Stocks to Buy Now", "All Open Trades"]


def _build_merged(rows, best, trades) -> list[dict]:
    """Merge all four sources into ONE row per symbol (deduped). A symbol found
    in multiple lists gets Source = comma-joined list; the first non-empty value
    wins for each field, and Zacks Service accumulates distinct services."""
    agg: dict[str, dict] = {}

    def add(sym, company, source, *, service="", type_="", date_added="",
            value="", growth="", momentum="", vgm=""):
        d = agg.get(sym)
        if not d:
            d = {"symbol": sym, "company": "", "value": "", "growth": "",
                 "momentum": "", "vgm": "", "type": "", "date_added": "",
                 "_sources": [], "_services": []}
            agg[sym] = d
        if company and not d["company"]:
            d["company"] = company
        if source not in d["_sources"]:
            d["_sources"].append(source)
        if service and service not in d["_services"]:
            d["_services"].append(service)
        for k, v in (("value", value), ("growth", growth), ("momentum", momentum),
                     ("vgm", vgm), ("type", type_), ("date_added", date_added)):
            if v and not d[k]:
                d[k] = v

    for r in rows or []:
        add(r["symbol"], r.get("company", ""), "Zacks Rank #1",
            value=r.get("value", ""), growth=r.get("growth", ""),
            momentum=r.get("momentum", ""), vgm=r.get("vgm", ""))
    for r in best or []:
        add(r["symbol"], r.get("company", ""), "Best Stocks to Buy Now")
    for r in trades or []:
        add(r["symbol"], r.get("company", ""), "All Open Trades",
            service=r.get("service", ""), type_=r.get("type", ""), date_added=r.get("date_added", ""))

    out = []
    for d in agg.values():
        d["service"] = ", ".join(d.pop("_services"))
        d["source"] = ", ".join(s for s in SRC_ORDER if s in d["_sources"])
        d.pop("_sources")
        out.append(d)
    out.sort(key=lambda x: x["symbol"])
    return out


def _write_merged_sheet(ws, merged, verdicts, styles):
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter
    hdr_fill, hdr_font, verdict_fill, short_fill = styles
    headers = ["Symbol", "Company", "Zacks Service", "Our Verdict", "Our Score",
               "Entry Quality", "Value", "Growth", "Momentum", "VGM", "Type",
               "Date Added", "Source"]
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")
    for i, r in enumerate(merged or [], start=1):
        v = verdicts.get(r["symbol"], {})
        ov = str(v.get("our_verdict", "")).upper()
        vals = [r["symbol"], r["company"], r.get("service", ""),
                ov or ("—" if r["symbol"] not in verdicts else ""),
                v.get("our_score", ""), v.get("entry_quality", ""),
                r.get("value", ""), r.get("growth", ""), r.get("momentum", ""),
                r.get("vgm", ""), r.get("type", ""), r.get("date_added", ""), r.get("source", "")]
        for j, val in enumerate(vals, 1):
            cell = ws.cell(row=i + 1, column=j, value=val)
            if j == 4 and ov in verdict_fill:
                cell.fill = verdict_fill[ov]
            if j == 11 and str(val).lower() == "short":
                cell.fill = short_fill
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for j, w in enumerate([9, 28, 18, 11, 9, 13, 7, 7, 10, 6, 7, 12, 22], 1):
        ws.column_dimensions[get_column_letter(j)].width = w


def _write_movers_sheet(wb, title, mover_rows, verdicts, styles):
    """Shared writer for the 30d-Top-Movers and All-Open-Trades sheets."""
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment
    hdr_fill, hdr_font, verdict_fill, short_fill = styles
    ws = wb.create_sheet(title)
    headers = ["#", "Symbol", "Company", "Type", "Date Added", "$Add", "$Last",
               "%Chg", "Zacks Service", "Our Verdict", "Our Score", "Entry Quality"]
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")
    for i, r in enumerate(mover_rows or [], start=1):
        v = verdicts.get(r["symbol"], {})
        ov = str(v.get("our_verdict", "")).upper()
        vals = [i, r["symbol"], r["company"], r.get("type", ""), r.get("date_added", ""),
                r.get("price_add", ""), r.get("price_last", ""), r.get("pct_chg", ""),
                r.get("service", ""), ov or ("—" if r["symbol"] not in verdicts else ""),
                v.get("our_score", ""), v.get("entry_quality", "")]
        for j, val in enumerate(vals, 1):
            cell = ws.cell(row=i + 1, column=j, value=val)
            if j == 4 and str(val).lower() == "short":
                cell.fill = short_fill
            if j == 10 and ov in verdict_fill:
                cell.fill = verdict_fill[ov]
    ws.freeze_panes = "A2"
    for j, w in enumerate([4, 9, 26, 7, 12, 9, 9, 9, 18, 11, 9, 13], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    return ws


def write_excel(rows: list[dict], best_rows: list[dict], trade_rows: list[dict],
                verdicts: dict[str, dict], out_paths: list[Path], as_of: str):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    hdr_fill = PatternFill("solid", fgColor="1F3B4D")
    hdr_font = Font(bold=True, color="FFFFFF")
    verdict_fill = {
        "BUY": PatternFill("solid", fgColor="C6EFCE"),
        "WATCH": PatternFill("solid", fgColor="FFEB9C"),
        "SHORT": PatternFill("solid", fgColor="FFC7CE"),
        "AVOID": PatternFill("solid", fgColor="F2DCDB"),
    }

    short_fill = PatternFill("solid", fgColor="FCE4EC")
    styles = (hdr_fill, hdr_font, verdict_fill, short_fill)

    wb = Workbook()

    # ── Sheet 1: All (Merged) — every source stacked, requested column set ──
    ws0 = wb.active
    ws0.title = "All (Merged)"
    merged = _build_merged(rows, best_rows, trade_rows)
    _write_merged_sheet(ws0, merged, verdicts, styles)

    # ── Sheet 2: Zacks Rank #1 (full detail) ────────────────────────────────
    ws = wb.create_sheet("Zacks Rank #1")
    headers = ["#", "Symbol", "Company", "Price", "Value", "Growth", "Momentum",
               "VGM", "Our Verdict", "Our Score", "Entry Quality", "Setup Family"]
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")

    for i, r in enumerate(rows, start=1):
        v = verdicts.get(r["symbol"], {})
        ov = str(v.get("our_verdict", "")).upper()
        vals = [i, r["symbol"], r["company"], r["price"], r["value"], r["growth"],
                r["momentum"], r["vgm"], ov or ("—" if r["symbol"] not in verdicts else ""),
                v.get("our_score", ""), v.get("entry_quality", ""), v.get("setup_family", "")]
        for j, val in enumerate(vals, 1):
            cell = ws.cell(row=i + 1, column=j, value=val)
            if j == 9 and ov in verdict_fill:
                cell.fill = verdict_fill[ov]
    ws.freeze_panes = "A2"
    # column widths
    widths = [4, 9, 30, 9, 7, 7, 10, 6, 11, 9, 13, 18]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w

    # ── Sheet 2: Best Stocks to Buy Now (curated featured list) ─────────────
    ws2 = wb.create_sheet("Best Stocks to Buy Now")
    headers2 = ["#", "Symbol", "Company", "Price", "12-Wk Chg", "Fwd PE",
                "Proj EPS Grw 1Y", "Proj Sales Grw 1Y", "Our Verdict", "Our Score",
                "Entry Quality", "Setup Family"]
    for j, h in enumerate(headers2, 1):
        c = ws2.cell(row=1, column=j, value=h)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")
    for i, r in enumerate(best_rows or [], start=1):
        v = verdicts.get(r["symbol"], {})
        ov = str(v.get("our_verdict", "")).upper()
        vals = [i, r["symbol"], r["company"], r.get("price", ""), r.get("chg_12w", ""),
                r.get("fwd_pe", ""), r.get("eps_growth_1y", ""), r.get("sales_growth_1y", ""),
                ov or ("—" if r["symbol"] not in verdicts else ""),
                v.get("our_score", ""), v.get("entry_quality", ""), v.get("setup_family", "")]
        for j, val in enumerate(vals, 1):
            cell = ws2.cell(row=i + 1, column=j, value=val)
            if j == 9 and ov in verdict_fill:
                cell.fill = verdict_fill[ov]
    ws2.freeze_panes = "A2"
    for j, w in enumerate([4, 9, 30, 10, 11, 8, 15, 16, 11, 9, 13, 18], 1):
        ws2.column_dimensions[get_column_letter(j)].width = w

    # ── Sheet 4: All Open Trades ────────────────────────────────────────────
    _write_movers_sheet(wb, "All Open Trades", trade_rows, verdicts, styles)

    # metadata sheet
    meta = wb.create_sheet("About")
    meta["A1"] = "Source — Rank #1"
    meta["B1"] = BUY_LIST_URL
    meta["A2"] = "Source — Best Stocks"
    meta["B2"] = BEST_STOCKS_URL
    meta["A3"] = "Source — Open Trades"
    meta["B3"] = TOP_MOVERS_URL
    meta["A4"] = "As of (PT)"
    meta["B4"] = as_of
    meta["A5"] = "Rank #1 tickers"
    meta["B5"] = len(rows)
    meta["A6"] = "Best-stocks tickers"
    meta["B6"] = len(best_rows or [])
    meta["A7"] = "All open trades"
    meta["B7"] = len(trade_rows or [])
    meta["A8"] = "Note"
    meta["B8"] = ("'Our Verdict' is this system's engine read from the latest scan "
                  "bundle (— = not in our scored universe). These lists are the "
                  "provider's picks; they are NOT our BUY. All Open Trades = every "
                  "currently-open position across all Ultimate services (Long & Short).")
    for r in range(1, 9):
        meta.cell(row=r, column=1).font = Font(bold=True)
    meta.column_dimensions["A"].width = 20
    meta.column_dimensions["B"].width = 80

    for p in out_paths:
        wb.save(p)
        log.info("Wrote %s", p)


# ---------------------------------------------------------------------------
def _scrape_with_retries(attempts=3, backoff=20):
    """Run scrape_all() with a FRESH browser session per try. The 5AM job used to
    die on a single transient ChromeDriver read-timeout with no retry; a slow
    morning page load or a stale session now gets 2 more shots before giving up."""
    import time
    last = None
    for k in range(1, attempts + 1):
        try:
            return scrape_all()
        except Exception as e:
            last = e
            log.warning("scrape attempt %d/%d failed: %s", k, attempts, e)
            if k < attempts:
                time.sleep(backoff * k)          # 20s, then 40s
    raise last


def _clear_stale_marker():
    try:
        (OUTPUT_DIR / "zacks_stale.json").unlink(missing_ok=True)
    except Exception:
        pass


def _write_stale_marker(as_of, err):
    """Breadcrumb so MasterAlgo can surface 'Zacks list is stale — this morning's
    refresh failed'. Never touches the good picks.json from the last success."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        serving = None
        if WEB_PICKS_JSON.exists():
            try:
                serving = json.loads(WEB_PICKS_JSON.read_text()).get("as_of")
            except Exception:
                pass
        (OUTPUT_DIR / "zacks_stale.json").write_text(json.dumps({
            "stale": True, "failed_at": as_of, "error": str(err)[:300],
            "serving_as_of": serving,
        }, indent=2))
        log.warning("wrote staleness marker — serving prior list (as_of=%s)", serving)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="scrape+parse, print, write no files")
    ap.add_argument("--from-cache", action="store_true", help="re-export from last JSON snapshot (no scrape)")
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(LOG_DIR / "zacks_buylist.log")],
    )

    as_of = _now_pt().strftime("%Y-%m-%d %H:%M %Z")
    try:
        if args.from_cache:
            if not JSON_SNAPSHOT.exists():
                log.error("No cached snapshot at %s", JSON_SNAPSHOT)
                return 1
            snap = json.loads(JSON_SNAPSHOT.read_text())
            rows = snap.get("rows") or snap.get("buy_list") or []
            best = snap.get("best_stocks") or []
            trades = snap.get("all_trades") or []
            as_of = snap.get("as_of", as_of)
        else:
            data = _scrape_with_retries(attempts=3)
            rows, best, trades = data["buy_list"], data["best_stocks"], data["all_trades"]

        verdicts = load_engine_verdicts()
        n_our_buys = sum(1 for r in rows
                         if str(verdicts.get(r["symbol"], {}).get("our_verdict", "")).upper() == "BUY")
        log.info("Rank #1: %d | Best: %d | All Open Trades: %d | our BUYs among Rank#1: %d",
                 len(rows), len(best), len(trades), n_our_buys)

        if args.dry_run:
            print("== Rank #1 (first 12) ==")
            for r in rows[:12]:
                v = verdicts.get(r["symbol"], {})
                print(f"  {r['symbol']:<7} {r['company'][:22]:<22} VGM={r['vgm']:<2} our={v.get('our_verdict','—')}")
            print(f"  ... {len(rows)} total")
            print("== Best Stocks to Buy Now ==")
            for r in best:
                print(f"  {r['symbol']:<7} {r['company'][:22]:<22} 12wk={r.get('chg_12w',''):<8} fPE={r.get('fwd_pe','')}")
            print(f"== All Open Trades ({len(trades)} total, first 6) ==")
            for r in trades[:6]:
                print(f"  {r['symbol']:<7} {r['company'][:20]:<20} {r.get('type',''):<5} "
                      f"{r.get('pct_chg',''):<8} {r.get('service','')}")
            print("(dry-run, no files written)")
            return 0

        # persist raw JSON snapshot (internal, drives --from-cache)
        JSON_SNAPSHOT.write_text(json.dumps(
            {"as_of": as_of, "source_buy_list": BUY_LIST_URL, "source_best_stocks": BEST_STOCKS_URL,
             "source_open_trades": TOP_MOVERS_URL, "count": len(rows), "best_count": len(best),
             "trades_count": len(trades),
             "rows": rows, "best_stocks": best, "all_trades": trades},
            indent=2))

        # Excel → Zacks folder (served by MasterAlgo)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _now_pt().strftime("%Y%m%d")
        out_paths = [OUTPUT_DIR / f"zacks_picks_{stamp}.xlsx",
                     OUTPUT_DIR / "zacks_picks_latest.xlsx"]
        write_excel(rows, best, trades, verdicts, out_paths, as_of)

        # web JSON for the MasterAlgo "My Picks" tab (deduped merged rows + our verdict)
        merged = _build_merged(rows, best, trades)
        for m in merged:
            v = verdicts.get(m["symbol"], {})
            m["our_verdict"] = v.get("our_verdict", "")
            m["our_score"] = v.get("our_score", "")
            m["entry_quality"] = v.get("entry_quality", "")
            m["setup_family"] = v.get("setup_family", "")
        WEB_PICKS_JSON.write_text(json.dumps({
            "as_of": as_of,
            "sources": {"Zacks Rank #1": len(rows), "Best Stocks to Buy Now": len(best),
                        "All Open Trades": len(trades)},
            "unique_symbols": len(merged),
            "xlsx": "Zacks/zacks_picks_latest.xlsx",
            "picks": merged,
        }, indent=2))
        _clear_stale_marker()                    # fresh list written — clear any prior staleness flag
        log.info("DONE — Rank#1 %d + Best %d + Trades %d | %d unique → %s (+ picks.json)",
                 len(rows), len(best), len(trades), len(merged), out_paths[-1])
        return 0
    except Exception as e:
        log.error("zacks_buylist_export FAILED after retries: %s", e, exc_info=True)
        _write_stale_marker(as_of, e)            # leave last-good picks.json intact + flag it stale
        return 1


if __name__ == "__main__":
    sys.exit(main())
