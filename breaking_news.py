import os
import json
import requests
import feedparser
import datetime
from urllib.parse import quote_plus

# Timezone
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

def now_ist():
    return datetime.datetime.utcnow() + IST_OFFSET

def send_telegram(msg):
    TOKEN = os.getenv("TG_TOKEN")
    CHAT_ID = os.getenv("TG_CHAT_ID")
    if not TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return
    
    safe_msg = quote_plus(msg)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={safe_msg}"
    try:
        r = requests.get(url, timeout=10)
        print("Telegram response:", r.text)
    except Exception as e:
        print("Telegram send error:", e)

# Stock-focused RSS feeds
STOCK_NEWS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",  # ET Stocks
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",  # MarketWatch Pulse
    "https://www.business-standard.com/rss/markets-106.rss",  # BS Markets
]

def fetch_rss(url):
    try:
        data = feedparser.parse(url)
        return [{
            "title": data.entries[i].get("title"),
            "link": data.entries[i].get("link"),
            "published": data.entries[i].get("published_parsed", None)
        } for i in range(min(3, len(data.entries)))]  # Only get latest 3
    except:
        return []

def is_recent(published_time, hours=3):
    """Check if news is from last N hours"""
    if not published_time:
        return True  # Include if we can't determine time
    
    try:
        pub_dt = datetime.datetime(*published_time[:6])
        now = datetime.datetime.utcnow()
        diff = now - pub_dt
        return diff.total_seconds() < (hours * 3600)
    except:
        return True

def get_breaking_news():
    """Fetch only recent breaking stock news"""
    all_items = []
    
    for url in STOCK_NEWS_FEEDS:
        items = fetch_rss(url)
        # Filter for recent news only
        recent_items = [item for item in items if is_recent(item.get("published"), hours=4)]
        all_items.extend(recent_items)
        print(f"✓ Fetched {len(recent_items)} recent items")
    
    return all_items

def format_alert(items):
    """Format breaking news alert"""
    if len(items) == 0:
        return None
    
    msg = f"🚨 Breaking Stock News — {now_ist().strftime('%I:%M %p IST')}\n\n"
    
    count = 0
    for item in items[:5]:  # Max 5 breaking news
        title = item.get("title", "").strip()
        link = item.get("link", "")
        
        if title and len(msg + f"• {title}\n  {link}\n\n") < 3800:
            msg += f"• {title}\n  {link}\n\n"
            count += 1
    
    if count == 0:
        return None
        
    return msg

if __name__ == "__main__":
    print(f"🔍 Checking for breaking stock news at {now_ist().strftime('%I:%M %p IST')}...")
    
    breaking_items = get_breaking_news()
    print(f"📊 Found {len(breaking_items)} recent news items")
    
    if len(breaking_items) > 0:
        alert_msg = format_alert(breaking_items)
        if alert_msg:
            send_telegram(alert_msg)
            print("✅ Breaking news alert sent!")
        else:
            print("ℹ️ No significant breaking news to report")
    else:
        print("ℹ️ No breaking news at this time")
