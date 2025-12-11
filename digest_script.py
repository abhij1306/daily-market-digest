import os
import json
import requests
import feedparser
import datetime
import re
from urllib.parse import urlparse, quote_plus

# --------------------------
# TIMEZONE (IST)
# --------------------------
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

def now_ist():
    return datetime.datetime.utcnow() + IST_OFFSET


# --------------------------
# CLEANING + FORMATTING
# --------------------------
def clean_html(raw):
    """Remove HTML tags and entities"""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", raw)
    
    # Remove &nbsp; and similar entities
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    
    # Remove excessive spaces
    return " ".join(text.split())


def shorten_url(url):
    """Extract domain name from URL"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except:
        return url


def escape_md(text):
    """Escape special characters for Telegram MarkdownV2"""
    # For basic markdown, we only need to escape certain characters
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_news_item(item):
    """Format a single news item for Telegram with markdown"""
    title = clean_html(item.get("title", "")).strip()
    summary = clean_html(item.get("summary", "")).strip()
    link = item.get("link", "")
    
    source = shorten_url(link)
    
    # Limit summary length
    if len(summary) > 150:
        summary = summary[:147] + "..."
    
    return f"• *{escape_md(title)}*\n  _{escape_md(summary)}_\n  🔗 {escape_md(source)}\n"


def build_markdown_digest(global_items, india_items, corporate_items, world_items):
    """Build beautiful markdown digest with sections"""
    msg = f"*📈 Daily Market Digest — {escape_md(now_ist().strftime('%d %b %Y'))}*\n\n"
    msg += "────────────────────\n\n"

    # GLOBAL MACRO
    msg += "*🌍 Global Macro Highlights*\n"
    for it in global_items[:5]:
        msg += format_news_item(it)
    msg += "\n────────────────────\n\n"

    # INDIA MARKET
    msg += "*🇮🇳 India Market Highlights*\n"
    for it in india_items[:5]:
        msg += format_news_item(it)
    msg += "\n────────────────────\n\n"

    # CORPORATE EVENTS
    msg += "*🏢 Corporate Actions (NSE/BSE)*\n"
    for ce in corporate_items[:5]:
        msg += escape_md(f"• {ce}") + "\n"
    msg += "\n────────────────────\n\n"

    # WORLD EVENTS
    msg += "*🌐 Major World Events*\n"
    for it in world_items[:5]:
        msg += format_news_item(it)
    msg += "\n────────────────────\n\n"

    msg += "_Reply */full* to receive the detailed full digest\\._"

    return msg[:3900]  # safe Telegram limit



# --------------------------
# TELEGRAM SENDER (FREE)

# --------------------------
def send_telegram(msg):
    TOKEN = os.getenv("TG_TOKEN")
    CHAT_ID = os.getenv("TG_CHAT_ID")
    if not TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return

    # URL-encode message to avoid breaking the URL
    safe_msg = quote_plus(msg)

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={safe_msg}"
    try:
        r = requests.get(url, timeout=10)
        print("Telegram response:", r.text)
    except Exception as e:
        print("Telegram send error:", e)


# --------------------------
# FREE NEWS SOURCES
# --------------------------
GLOBAL_RSS = [
    "https://news.google.com/rss/search?q=fed+OR+gdp+OR+cpi+OR+inflation+OR+markets&hl=en-IN&gl=IN&ceid=IN:en",
    "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
]

INDIA_RSS = [
    "https://news.google.com/rss/topics/CAAqBwgKMOTf5wswyY0k?hl=en-IN&gl=IN&ceid=IN:en",
]

BSE_RSS = "https://www.bseindia.com/xml-data/announce/RSS.xml"

WORLD_RSS = [
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pKVGlnQVAB?hl=en-IN&gl=IN&ceid=IN:en",  # World news
]

NSE_BLOCK = "https://www.nseindia.com/api/block-deals?index=equities"
NSE_BULK  = "https://www.nseindia.com/api/bulk-deals?index=equities"


# --------------------------
# FETCH HELPERS
# --------------------------
def fetch_rss(url):
    try:
        data = feedparser.parse(url)
        return [{
            "title": e.get("title"),
            "link": e.get("link"),
            "summary": e.get("summary", "")
        } for e in data.entries]
    except:
        return []

def fetch_nse_json(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive"
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)  # initialize cookies
        r = session.get(url, headers=headers, timeout=10)
        r.raise_for_status()

        # Try JSON decode
        data = r.json()

        # NSE sometimes returns a list instead of dict
        if isinstance(data, list):
            return {"data": data}

        # NSE usually returns dict with 'data'
        if isinstance(data, dict):
            return data

        return {"data": []}

    except Exception as e:
        print("NSE fetch failed:", e)
        return {"data": []}


# --------------------------
# MAIN DIGEST LOGIC
# --------------------------
def run_digest():

    # Categorized items
    global_items = []
    india_items = []
    corporate_items = []
    world_items = []

    # 1. Global macro news
    for url in GLOBAL_RSS:
        global_items.extend(fetch_rss(url))

    # 2. India business news
    for url in INDIA_RSS:
        india_items.extend(fetch_rss(url))

    # 3. BSE announcements
    bse_items = fetch_rss(BSE_RSS)
    for item in bse_items:
        corporate_items.append(clean_html(item.get("title", "")))

    # 4. NSE Block deals
    nse_block = fetch_nse_json(NSE_BLOCK)
    for blk in nse_block.get("data", []):
        symbol = blk.get('symbol', 'Unknown')
        qty = blk.get('quantity', '')
        corporate_items.append(f"Block Deal: {symbol} - Qty: {qty}")

    # 5. NSE Bulk deals
    nse_bulk = fetch_nse_json(NSE_BULK)
    for blk in nse_bulk.get("data", []):
        symbol = blk.get('symbol', 'Unknown')
        qty = blk.get('quantity', '')
        corporate_items.append(f"Bulk Deal: {symbol} - Qty: {qty}")

    # 6. World events
    for url in WORLD_RSS:
        world_items.extend(fetch_rss(url))

    # Build beautiful markdown digest
    msg = build_markdown_digest(global_items, india_items, corporate_items, world_items)
    
    # Save to file
    os.makedirs("digests", exist_ok=True)
    fname = f"digests/digest_{now_ist().strftime('%Y%m%d_%H%M')}.md"
    
    with open(fname, "w", encoding="utf-8") as f:
        f.write(msg)
    
    # Send to Telegram
    send_telegram(msg)

    return fname


if __name__ == "__main__":
    print("Generated:", run_digest())
