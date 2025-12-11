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


def shorten_link(url):
    """Shorten URL using TinyURL free service"""
    import time
    try:
        # Add small delay to avoid rate limiting
        time.sleep(0.3)
        
        api_url = f"https://tinyurl.com/api-create.php?url={quote_plus(url)}"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200 and response.text.startswith('http'):
            short_url = response.text.strip()
            print(f"✓ Shortened: {short_url}")
            return short_url
        else:
            print(f"✗ Shortening failed, using original")
            return url
    except Exception as e:
        print(f"✗ Shortening error: {str(e)[:50]}")
        return url


def format_news_item(item):
    """Format a single news item - just title and link"""
    title = clean_html(item.get("title", "")).strip()
    link = item.get("link", "")
    
    if not title:
        return ""
    
    # Shorten the link for cleaner messages
    short_link = shorten_link(link)
    
    return f"• {title}\n  {short_link}\n"


def build_digest_message(all_items):
    """Build simple digest message with just titles and links"""
    msg = f"📈 Daily Market Digest — {now_ist().strftime('%d %b %Y')}\n\n"
    
    count = 0
    for item in all_items:
        if count >= 10:  # Increased to 10 items with shortened URLs
            break
        formatted = format_news_item(item)
        if formatted:
            # Check if adding this item would exceed Telegram's limit
            if len(msg + formatted) > 3800:  # Leave some buffer
                break
            msg += formatted
            count += 1
    
    return msg




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

    all_items = []

    # 1. Global macro news
    for url in GLOBAL_RSS:
        all_items.extend(fetch_rss(url))

    # 2. India business news
    for url in INDIA_RSS:
        all_items.extend(fetch_rss(url))

    # 3. BSE announcements
    all_items.extend(fetch_rss(BSE_RSS))

    # 4. World events
    for url in WORLD_RSS:
        all_items.extend(fetch_rss(url))

    # 5. NSE Block deals
    nse_block = fetch_nse_json(NSE_BLOCK)
    for blk in nse_block.get("data", []):
        all_items.append({
            "title": f"NSE Block Deal: {blk.get('symbol', 'Unknown')}",
            "link": "https://www.nseindia.com"
        })

    # 6. NSE Bulk deals
    nse_bulk = fetch_nse_json(NSE_BULK)
    for blk in nse_bulk.get("data", []):
        all_items.append({
            "title": f"NSE Bulk Deal: {blk.get('symbol', 'Unknown')}",
            "link": "https://www.nseindia.com"
        })

    # Build simple digest message
    msg = build_digest_message(all_items)
    
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
