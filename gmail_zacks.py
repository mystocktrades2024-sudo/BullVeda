"""
Gmail → Zacks email parser.

Pulls Zacks emails from Gmail via API, parses rank changes, trade alerts,
and commentary into structured data for the SwingTrade scoring pipeline.

Setup (one-time):
  1. Go to console.cloud.google.com → Create project → Enable Gmail API
  2. Create OAuth 2.0 credentials (Desktop app type)
  3. Download credentials.json → save as SwingTrade/config/gmail_credentials.json
  4. First run opens browser to authorize → token saved automatically

Usage:
  from gmail_zacks import fetch_zacks_emails
  data = fetch_zacks_emails(days=3)
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

log = logging.getLogger("swingtrade.gmail")

BASE_DIR = Path(__file__).parent
CREDS_PATH = BASE_DIR / "config" / "gmail_credentials.json"
TOKEN_PATH = BASE_DIR / "config" / "gmail_token.json"
CACHE_PATH = BASE_DIR / "cache" / "gmail_zacks_cache.json"

# How long to cache results (avoid hitting Gmail on every request)
CACHE_TTL_MINUTES = 30

# Zacks sender patterns
ZACKS_SENDERS = [
    "zacks.com",
    "zacksinvestmentmanagement.com",
]

# Email classification patterns (subject line → category)
EMAIL_PATTERNS = [
    # Rank changes
    (r"rank\s*#?\s*1\b.*(?:alert|upgrade|change)", "rank_change"),
    (r"strong\s+buy", "rank_change"),
    (r"rank\s+(?:change|upgrade|downgrade)", "rank_change"),
    (r"moved\s+to\s+(?:a\s+)?(?:zacks\s+)?rank\s*#?\s*\d", "rank_change"),
    # Ultimate trade alerts
    (r"ultimate.*(?:buy|sell|trade|alert|add)", "ultimate_alert"),
    (r"(?:buy|sell)\s+alert.*ultimate", "ultimate_alert"),
    (r"new\s+(?:buy|addition).*ultimate", "ultimate_alert"),
    # Confidential alerts
    (r"confidential.*(?:buy|sell|trade|alert)", "confidential_alert"),
    (r"(?:buy|sell)\s+alert.*confidential", "confidential_alert"),
    # Bull / Bear of the day
    (r"bull\s+of\s+the\s+day", "bull_of_day"),
    (r"bear\s+of\s+the\s+day", "bear_of_day"),
    # Earnings
    (r"earnings\s+(?:preview|surprise|ESP|beat|miss)", "earnings"),
    # General commentary / newsletters
    (r"(?:morning|afternoon|market)\s+(?:commentary|comment|update|outlook)", "commentary"),
    (r"(?:stock|market)\s+(?:of\s+the\s+day|spotlight)", "commentary"),
    (r"investor\s+collection", "commentary"),
    # Daily summary emails
    (r"daily\s+summary.*ultimate", "ultimate_summary"),
    (r"daily\s+summary.*headline\s+trader", "headline_trader"),
    (r"daily\s+summary.*short\s+sell", "short_sell_list"),
    (r"daily\s+summary.*surprise\s+trader", "surprise_trader"),
    (r"daily\s+summary.*insider\s+trader", "insider_trader"),
    (r"daily\s+summary.*(?:large|mid|small).?cap", "portfolio_summary"),
    (r"daily\s+summary.*(?:technology|marijuana|hcare|healthcare)", "portfolio_summary"),
    (r"daily\s+summary.*counterstrike", "portfolio_summary"),
    (r"daily\s+summary", "portfolio_summary"),
    # Articles & analysis
    (r"latest\s+analysis\s+from", "analyst_article"),
    (r"new\s+article\s+published", "article"),
]

# Ticker extraction: $AAPL, (AAPL), ticker: AAPL, or bare AAPL followed by %/whitespace
TICKER_RE = re.compile(
    r'(?:'
    r'\$([A-Z]{1,5})\b'                              # $AAPL
    r'|'
    r'\(([A-Z]{1,5})\)'                               # (AAPL)
    r'|'
    r'(?:ticker|symbol|stock)[:\s]+([A-Z]{1,5})\b'    # ticker: AAPL
    r'|'
    r'\b([A-Z]{2,5})\s+[\d.]+%'                       # AAPL 9.48%
    r'|'
    r'(?:^|\n)\s*([A-Z]{2,5})\s+(?:Short|Long|Buy|Sell|Add|Close)' # AAPL Short
    r')',
    re.MULTILINE
)

# Common non-ticker words to exclude
NON_TICKERS = {
    "NYSE", "NASDAQ", "ETF", "CEO", "CFO", "COO", "IPO", "EPS", "ESP",
    "GDP", "CPI", "PPI", "FOMC", "SEC", "FDA", "DOJ", "FTC", "LLC",
    "INC", "CORP", "LTD", "USA", "THE", "AND", "FOR", "ARE", "BUT",
    "NOT", "YOU", "ALL", "HER", "WAS", "ONE", "OUR", "OUT", "HAS",
    "BUY", "SELL", "NEW", "OLD", "TOP", "LOW", "ANY", "DAY", "NOW",
    "HOW", "MAY", "CAN", "DID", "GET", "HIS", "ITS", "LET", "SAY",
    "SHE", "TOO", "USE", "MID", "EDT", "EST", "PST", "PDF", "HTML",
    "USD", "EUR", "GBP", "JPY", "CAD",
}


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML tags, keep text."""
    def __init__(self):
        super().__init__()
        self._text = []

    def handle_data(self, data):
        self._text.append(data)

    def get_text(self):
        return " ".join(self._text)


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _get_gmail_service():
    """Authenticate and return Gmail API service object."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    creds = None

    # Load existing token
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or authorize
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not CREDS_PATH.exists():
                log.error(
                    f"Gmail credentials not found at {CREDS_PATH}\n"
                    "  Setup: console.cloud.google.com → Gmail API → OAuth credentials → "
                    "download as gmail_credentials.json"
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        TOKEN_PATH.write_text(creds.to_json())
        log.info("Gmail token saved")

    return build("gmail", "v1", credentials=creds)


def _classify_email(subject: str) -> str:
    """Classify an email by subject line into a category."""
    subj_lower = subject.lower()
    for pattern, category in EMAIL_PATTERNS:
        if re.search(pattern, subj_lower):
            return category
    return "other"


def _extract_tickers(text: str) -> list[str]:
    """Extract stock tickers from text."""
    tickers = set()
    for match in TICKER_RE.finditer(text):
        ticker = (match.group(1) or match.group(2) or match.group(3)
                  or match.group(4) or match.group(5) or "").upper()
        if ticker and ticker not in NON_TICKERS and len(ticker) >= 2:
            tickers.add(ticker)
    return sorted(tickers)


def _extract_rank_info(text: str) -> dict:
    """Extract Zacks rank change details from text."""
    info = {}

    # Rank number
    rank_match = re.search(r"(?:zacks\s+)?rank\s*#?\s*(\d)", text, re.IGNORECASE)
    if rank_match:
        info["rank"] = int(rank_match.group(1))
        rank_labels = {1: "Strong Buy", 2: "Buy", 3: "Hold", 4: "Sell", 5: "Strong Sell"}
        info["rank_text"] = rank_labels.get(info["rank"], f"Rank {info['rank']}")

    # Previous rank
    prev_match = re.search(r"(?:from|was|previous)\s+(?:a\s+)?(?:zacks\s+)?rank\s*#?\s*(\d)", text, re.IGNORECASE)
    if prev_match:
        info["previous_rank"] = int(prev_match.group(1))

    # Direction
    if re.search(r"upgrade|moved\s+(?:up|to\s+a\s+(?:better|higher))", text, re.IGNORECASE):
        info["direction"] = "upgrade"
    elif re.search(r"downgrade|moved\s+(?:down|to\s+a\s+(?:worse|lower))", text, re.IGNORECASE):
        info["direction"] = "downgrade"

    return info


def _extract_trade_action(text: str) -> dict:
    """Extract buy/sell action from trade alert emails."""
    info = {}
    if re.search(r"\bbuy\b|add(?:ing|ed)?|open(?:ing|ed)?\s+(?:a\s+)?(?:long|position)", text, re.IGNORECASE):
        info["action"] = "BUY"
    elif re.search(r"\bsell\b|clos(?:ing|ed?)|exit(?:ing|ed)?|remov", text, re.IGNORECASE):
        info["action"] = "SELL"

    # Price targets
    price_match = re.search(r"(?:target|price\s+target|TP)[:\s]*\$?([\d.]+)", text, re.IGNORECASE)
    if price_match:
        info["target_price"] = float(price_match.group(1))

    buy_under = re.search(r"(?:buy\s+(?:under|below|up\s+to))[:\s]*\$?([\d.]+)", text, re.IGNORECASE)
    if buy_under:
        info["buy_under"] = float(buy_under.group(1))

    return info


def _parse_email(msg_data: dict) -> dict | None:
    """Parse a single Gmail message into structured Zacks data."""
    headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    date_str = headers.get("date", "")

    # Verify it's from Zacks
    if not any(z in sender.lower() for z in ZACKS_SENDERS):
        return None

    # Parse date
    try:
        date = parsedate_to_datetime(date_str)
        date_iso = date.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_iso = date_str

    # Get email body — try top-level first, then parts, then nested parts
    body_text = ""
    payload = msg_data.get("payload", {})

    def _get_body(part):
        if part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        return ""

    def _extract_text(part):
        """Recursively extract text from a MIME part."""
        mime = part.get("mimeType", "")
        raw = _get_body(part)
        if raw:
            if "html" in mime:
                return _html_to_text(raw)
            elif "plain" in mime:
                return raw
        # Check sub-parts
        for sub in part.get("parts", []):
            text = _extract_text(sub)
            if text and len(text.strip()) > 20:
                return text
        return ""

    # Top-level body (single-part emails)
    if payload.get("body", {}).get("data"):
        raw = _get_body(payload)
        mime = payload.get("mimeType", "")
        body_text = _html_to_text(raw) if "html" in mime else raw

    # Multi-part: prefer text/plain, fallback to text/html
    if not body_text.strip() or len(body_text.strip()) < 50:
        for part in payload.get("parts", []):
            text = _extract_text(part)
            if text and len(text.strip()) > len(body_text.strip()):
                body_text = text

    # Clean up: remove CSS/style content that leaked through
    body_text = re.sub(r'\.[\w-]+\s*\{[^}]*\}', '', body_text)  # .class { ... }
    body_text = re.sub(r'@media[^{]*\{[^}]*\}', '', body_text)  # @media queries
    body_text = re.sub(r'\s+', ' ', body_text).strip()

    # Classify
    category = _classify_email(subject)
    tickers = _extract_tickers(subject + " " + body_text[:2000])

    result = {
        "subject": subject,
        "from": sender,
        "date": date_iso,
        "category": category,
        "tickers": tickers,
    }

    # Category-specific extraction
    if category == "rank_change":
        rank_info = _extract_rank_info(subject + " " + body_text[:1000])
        result["rank_info"] = rank_info
    elif category in ("ultimate_alert", "confidential_alert"):
        trade_info = _extract_trade_action(subject + " " + body_text[:1000])
        result["trade_info"] = trade_info
    elif category in ("bull_of_day", "bear_of_day"):
        result["sentiment"] = "bullish" if category == "bull_of_day" else "bearish"

    # Snippet (first 200 chars of body for display)
    result["snippet"] = body_text[:200].strip().replace("\n", " ") if body_text else ""

    return result


def fetch_zacks_emails(days: int = 3, max_results: int = 50,
                       use_cache: bool = True) -> dict:
    """
    Fetch and parse Zacks emails from Gmail.

    Args:
        days: How many days back to search
        max_results: Max emails to fetch
        use_cache: Use cached results if fresh

    Returns:
        {
            "emails": [...],           # All parsed emails
            "rank_changes": {...},     # ticker → rank info (most recent)
            "trade_alerts": [...],     # Ultimate/Confidential trade alerts
            "bull_bear": [...],        # Bull/Bear of the Day picks
            "ticker_mentions": {...},  # ticker → mention count
            "last_fetched": "...",
        }
    """
    # Check cache
    if use_cache and CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text())
            cached_at = datetime.fromisoformat(cache.get("last_fetched", "2000-01-01"))
            if datetime.now() - cached_at < timedelta(minutes=CACHE_TTL_MINUTES):
                log.info(f"Gmail cache hit ({len(cache.get('emails', []))} emails)")
                return cache
        except Exception:
            pass

    service = _get_gmail_service()
    if not service:
        return {"emails": [], "rank_changes": {}, "trade_alerts": [],
                "bull_bear": [], "ticker_mentions": {}, "error": "No Gmail credentials"}

    # Search for Zacks emails
    after_date = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"from:zacks.com after:{after_date}"

    log.info(f"Searching Gmail: {query}")

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
    except Exception as e:
        log.error(f"Gmail search failed: {e}")
        return {"emails": [], "rank_changes": {}, "trade_alerts": [],
                "bull_bear": [], "ticker_mentions": {}, "error": str(e)}

    messages = results.get("messages", [])
    log.info(f"Found {len(messages)} Zacks emails")

    if not messages:
        return {"emails": [], "rank_changes": {}, "trade_alerts": [],
                "bull_bear": [], "ticker_mentions": {}, "last_fetched": datetime.now().isoformat()}

    # Fetch and parse each message
    emails = []
    for msg in messages:
        try:
            msg_data = service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()
            parsed = _parse_email(msg_data)
            if parsed:
                emails.append(parsed)
        except Exception as e:
            log.warning(f"Failed to parse email {msg['id']}: {e}")

    # Build structured output
    rank_changes = {}
    trade_alerts = []
    bull_bear = []
    ticker_mentions = {}

    for email in emails:
        # Count ticker mentions
        for t in email.get("tickers", []):
            ticker_mentions[t] = ticker_mentions.get(t, 0) + 1

        cat = email["category"]
        if cat == "rank_change":
            for t in email.get("tickers", []):
                if t not in rank_changes:
                    rank_changes[t] = {
                        **email.get("rank_info", {}),
                        "date": email["date"],
                        "subject": email["subject"],
                    }
        elif cat in ("ultimate_alert", "confidential_alert"):
            trade_alerts.append({
                "tickers": email.get("tickers", []),
                "category": cat,
                "date": email["date"],
                "subject": email["subject"],
                **email.get("trade_info", {}),
            })
        elif cat in ("bull_of_day", "bear_of_day"):
            bull_bear.append({
                "tickers": email.get("tickers", []),
                "sentiment": email.get("sentiment", "neutral"),
                "date": email["date"],
                "subject": email["subject"],
            })

    output = {
        "emails": emails,
        "rank_changes": rank_changes,
        "trade_alerts": trade_alerts,
        "bull_bear": bull_bear,
        "ticker_mentions": ticker_mentions,
        "last_fetched": datetime.now().isoformat(),
        "total": len(emails),
        "by_category": {},
    }

    # Summary by category
    for email in emails:
        cat = email["category"]
        output["by_category"][cat] = output["by_category"].get(cat, 0) + 1

    # Cache results
    try:
        CACHE_PATH.write_text(json.dumps(output, indent=2, default=str))
        log.info(f"Gmail cache saved ({len(emails)} emails)")
    except Exception as e:
        log.warning(f"Cache save failed: {e}")

    return output


def get_zacks_email_bonus(ticker: str, gmail_data: dict | None = None) -> dict:
    """
    Compute scoring bonus for a ticker based on Zacks email signals.

    Returns:
        {
            "bonus": int (-3 to +5),
            "signals": ["Rank #1 upgrade (email)", ...],
            "rank_from_email": dict or None,
            "trade_alert": dict or None,
            "bull_bear": str or None,
            "mention_count": int,
        }
    """
    if not gmail_data:
        gmail_data = {}

    bonus = 0
    signals = []

    # Rank change
    rank_info = gmail_data.get("rank_changes", {}).get(ticker)
    if rank_info:
        rank = rank_info.get("rank")
        if rank == 1:
            bonus += 5
            signals.append(f"Zacks Rank #1 — {rank_info.get('rank_text', 'Strong Buy')} (email alert)")
        elif rank == 2:
            bonus += 2
            signals.append(f"Zacks Rank #2 — Buy (email alert)")
        elif rank == 4:
            bonus -= 2
            signals.append(f"Zacks Rank #4 — Sell (email alert)")
        elif rank == 5:
            bonus -= 3
            signals.append(f"Zacks Rank #5 — Strong Sell (email alert)")

    # Trade alerts (Ultimate / Confidential)
    trade_alert = None
    for alert in gmail_data.get("trade_alerts", []):
        if ticker in alert.get("tickers", []):
            trade_alert = alert
            action = alert.get("action", "")
            if action == "BUY":
                bonus += 3
                cat = "Ultimate" if "ultimate" in alert.get("category", "") else "Confidential"
                signals.append(f"Zacks {cat} BUY alert (email)")
            elif action == "SELL":
                bonus -= 3
                cat = "Ultimate" if "ultimate" in alert.get("category", "") else "Confidential"
                signals.append(f"Zacks {cat} SELL alert (email)")
            break

    # Bull/Bear of the Day
    bull_bear = None
    for bb in gmail_data.get("bull_bear", []):
        if ticker in bb.get("tickers", []):
            bull_bear = bb.get("sentiment")
            if bull_bear == "bullish":
                bonus += 2
                signals.append("Zacks Bull of the Day (email)")
            elif bull_bear == "bearish":
                bonus -= 2
                signals.append("Zacks Bear of the Day (email)")
            break

    # Mention frequency bonus (heavily mentioned = market attention)
    mention_count = gmail_data.get("ticker_mentions", {}).get(ticker, 0)
    if mention_count >= 5:
        bonus += 1
        signals.append(f"Mentioned {mention_count}x in Zacks emails")

    # Cap bonus
    bonus = max(-5, min(7, bonus))

    return {
        "bonus": bonus,
        "signals": signals,
        "rank_from_email": rank_info,
        "trade_alert": trade_alert,
        "bull_bear": bull_bear,
        "mention_count": mention_count,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    data = fetch_zacks_emails(days=3)
    print(f"\nFetched {data['total']} Zacks emails")
    print(f"Categories: {data['by_category']}")
    print(f"Rank changes: {list(data['rank_changes'].keys())}")
    print(f"Trade alerts: {len(data['trade_alerts'])}")
    print(f"Bull/Bear: {len(data['bull_bear'])}")
    print(f"Top mentioned tickers: {sorted(data['ticker_mentions'].items(), key=lambda x: -x[1])[:10]}")
    if data.get("error"):
        print(f"Error: {data['error']}")
