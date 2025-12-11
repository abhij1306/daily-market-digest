import os
import json
import requests
import feedparser
import datetime
import urllib.parse

# --------------------------
# TIMEZONE (IST)
# --------------------------
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

def now_ist():
    return datetime.datetime.utcnow() + IST_OFFSET


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
    safe_msg = urllib.parse.quote_plus(msg)

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
# FREE SUMMARIZER (DeepSeek-R1)
# --------------------------
def summarize(text):
    endpoint = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": "deepseek-r1",
        "messages": [
            {"role": "user",
             "content": f"Summarize the following into concise bullet points. Focus on market-moving events, India company news, global macro signals, and major world events.\n\n{text}"}
        ],
        "temperature": 0.3,
        "max_tokens": 350
    }

    try:
        r = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=20)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return text
    except:
        return text


# --------------------------
# MAIN DIGEST LOGIC
# --------------------------
def run_digest():

    all_items = []

    # 1. Global news
    for url in GLOBAL_RSS:
        all_items.extend(fetch_rss(url))

    # 2. India business news
    for url in INDIA_RSS:
        all_items.extend(fetch_rss(url))

    # 3. BSE announcements
    all_items.extend(fetch_rss(BSE_RSS))

    # 4. NSE Block deals
    nse_block = fetch_json(NSE_BLOCK)
    for blk in nse_block.get("data", []):
    all_items.append({
        "title": f"NSE Block Deal: {blk.get('symbol', 'Unknown')}",
        "link": "https://www.nseindia.com",
        "summary": json.dumps(blk)
    })

    # 5. NSE Bulk deals
    nse_bulk = fetch_json(NSE_BULK)
    for blk in nse_bulk.get("data", []):
    all_items.append({
        "title": f"NSE Bulk Deal: {blk.get('symbol', 'Unknown')}",
        "link": "https://www.nseindia.com",
        "summary": json.dumps(blk)
    })

    # Combine into single text block
    combined = "\n".join([f"{i['title']} — {i['summary']}" for i in all_items[:50]])

    # Summarize via free LLM
    final_summary = summarize(combined)

    # Save to file
    os.makedirs("digests", exist_ok=True)
    fname = f"digests/digest_{now_ist().strftime('%Y%m%d_%H%M')}.md"

    with open(fname, "w", encoding="utf-8") as f:
        f.write(final_summary)

    # Send to Telegram
    send_telegram(final_summary[:3500])

    return fname


if __name__ == "__main__":
    print("Generated:", run_digest())
