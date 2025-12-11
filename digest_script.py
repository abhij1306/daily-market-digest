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
    """Shorten URL using TinyURL free service with retry"""
    import time
    
    for attempt in range(2):  # Try twice
        try:
            # Add small delay to avoid rate limiting
            time.sleep(0.5)
            
            api_url = f"https://tinyurl.com/api-create.php?url={quote_plus(url)}"
            response = requests.get(api_url, timeout=15)
            
            if response.status_code == 200 and response.text.startswith('http'):
                short_url = response.text.strip()
                print(f"✓ Shortened: {short_url}")
                return short_url
            else:
                print(f"✗ Attempt {attempt + 1} failed, retrying...")
                time.sleep(1)
        except Exception as e:
            print(f"✗ Attempt {attempt + 1} error: {str(e)[:50]}")
            time.sleep(1)
    
    # If both attempts fail, return original URL
    print(f"✗ Using original URL after retries")
    return url


def format_news_item(item):
    """Format a single news item - just title and link"""
    title = clean_html(item.get("title", "")).strip()
    link = item.get("link", "")
    
    if not title:
        return ""
    
    # Use original link to ensure it works properly
    return f"• {title}\n  {link}\n"


def rank_news_with_ai(all_items):
    """Use AI to rank news by importance for market digest"""
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    if not GROQ_API_KEY or len(all_items) == 0:
        # If no API key or no items, return as-is
        return all_items
    
    try:
        # Create a simple list of titles for AI to rank
        titles_list = "\n".join([f"{i+1}. {clean_html(item.get('title', ''))[:100]}" 
                                 for i, item in enumerate(all_items[:20])])  # Limit to first 20
        
        prompt = f"""Rank these news headlines by importance for market traders and investors. 
Focus on: Fed decisions, GDP, inflation, major market moves, India economy, corporate actions.

{titles_list}

Return ONLY the numbers of the top 10 most important headlines, comma-separated (e.g., 3,1,7,2,9,4,8,5,10,6)"""

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 100
            },
            timeout=10
        )
        
        if response.status_code == 200:
            ai_response = response.json()["choices"][0]["message"]["content"].strip()
            # Parse the ranked numbers
            ranked_indices = [int(x.strip())-1 for x in ai_response.split(",") if x.strip().isdigit()]
            
            # Reorder items based on AI ranking
            ranked_items = [all_items[i] for i in ranked_indices if i < len(all_items)]
            # Add remaining items that weren't ranked
            remaining = [item for i, item in enumerate(all_items) if i not in ranked_indices]
            
            print(f"✓ AI ranked {len(ranked_items)} news items")
            return ranked_items + remaining
        else:
            print(f"✗ AI ranking failed, using original order")
            return all_items
    except Exception as e:
        print(f"✗ AI ranking error: {str(e)[:50]}")
        return all_items


def build_digest_message(all_items):
    """Build simple digest message with just titles and links"""
    # Use AI to rank news by importance
    ranked_items = rank_news_with_ai(all_items)
    
    msg = f"📈 Daily Market Digest — {now_ist().strftime('%d %b %Y')}\n\n"
    
    count = 0
    for item in ranked_items:
        if count >= 10:  # 10 items with clean short URLs
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
    "https://feeds.reuters.com/reuters/businessNews",  # Reuters Business
    "https://feeds.marketwatch.com/marketwatch/topstories/",  # MarketWatch
]

INDIA_RSS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",  # ET Markets
    "https://www.business-standard.com/rss/markets-106.rss",  # Business Standard
]

BSE_RSS = "https://www.bseindia.com/xml-data/announce/RSS.xml"

WORLD_RSS = [
    "https://www.cnbc.com/id/100727362/device/rss/rss.html",  # CNBC World Markets
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

    # Collect items from each source with limit for diversity
    # 1. Global macro news (take 3 from each)
    for url in GLOBAL_RSS:
        items = fetch_rss(url)[:3]
        all_items.extend(items)
        print(f"✓ Fetched {len(items)} from Global RSS")

    # 2. India business news (take 3 from each)
    for url in INDIA_RSS:
        items = fetch_rss(url)[:3]
        all_items.extend(items)
        print(f"✓ Fetched {len(items)} from India RSS")

    # 3. BSE announcements (take 2)
    bse_items = fetch_rss(BSE_RSS)[:2]
    all_items.extend(bse_items)
    print(f"✓ Fetched {len(bse_items)} from BSE")

    # 4. World events (take 3)
    for url in WORLD_RSS:
        items = fetch_rss(url)[:3]
        all_items.extend(items)
        print(f"✓ Fetched {len(items)} from World RSS")

    print(f"\n📊 Total items collected: {len(all_items)}")


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
