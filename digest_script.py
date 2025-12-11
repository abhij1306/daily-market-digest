# digest_script.py
import feedparser, requests, json, os, datetime, time, re

IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

def now_ist():
    return datetime.datetime.utcnow() + IST_OFFSET

def fetch_rss(url):
    try:
        data = feedparser.parse(url)
        return [{
            "title": e.get("title"),
            "link": e.get("link"),
            "summary": e.get("summary", ""),
            "published": e.get("published", "")
        } for e in data.entries]
    except:
        return []

def fetch_json(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except:
        return []

# ---------- FREE SOURCES ----------
GLOBAL_RSS = [
    "https://news.google.com/rss/search?q=fed+OR+gdp+OR+cpi+OR+inflation+OR+\"interest+rates\"&hl=en-IN&gl=IN&ceid=IN:en",
    "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
]

INDIA_RSS = [
    "https://news.google.com/rss/topics/CAAqBwgKMOTf5wswyY0k?hl=en-IN&gl=IN&ceid=IN:en",
]

NSE_BLOCK = "https://www.nseindia.com/api/block-deals?index=equities"
NSE_BULK =  "https://www.nseindia.com/api/bulk-deals?index=equities"
BSE_RSS = "https://www.bseindia.com/xml-data/announce/RSS.xml"

# ---------- SUMMARIZER (FREE) ----------
def summarize(text):
    # Free DeepSeek-R1 inference endpoint (public mirror)
    endpoint = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "deepseek-r1",
        "messages": [{"role": "user", "content": f"Summarize into bullet points:\n{text}"}],
        "temperature": 0.3,
        "max_tokens": 300
    }
    try:
        r = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=20)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return text
    except:
        return text

# ---------- MAIN ----------
def run_digest():
    all_items = []

    # news
    for url in GLOBAL_RSS + INDIA_RSS:
        all_items.extend(fetch_rss(url))

    # bse announcements
    all_items.extend(fetch_rss(BSE_RSS))

    # nse block/bulk
    nse_block = fetch_json(NSE_BLOCK)
    nse_bulk  = fetch_json(NSE_BULK)
    
    # Extract relevant fields
    for blk in nse_block.get("data", []):
        all_items.append({
            "title": f"NSE Block Deal: {blk.get('symbol')}",
            "link": "https://www.nseindia.com",
            "summary": json.dumps(blk)
        })
    for blk in nse_bulk.get("data", []):
        all_items.append({
            "title": f"NSE Bulk Deal: {blk.get('symbol')}",
            "link": "https://www.nseindia.com",
            "summary": json.dumps(blk)
        })

    # Build combined text for summarization
    combined_text = "\n".join([f"{i['title']} — {i['summary']}" for i in all_items[:40]])

    result = summarize(combined_text)

    output = {
        "generated_at": str(now_ist()),
        "headlines": result
    }

    # Save output
    os.makedirs("digests", exist_ok=True)
    fname = f"digests/digest_{now_ist().strftime('%Y%m%d_%H%M')}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(result)

    return fname

if __name__ == "__main__":
    print(run_digest())
