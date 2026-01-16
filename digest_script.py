#!/usr/bin/env python3
"""
digest_script.py
Production-ready Market Digest generator.

Environment variables expected:
- TG_TOKEN        -> Telegram bot token
- TG_CHAT_ID      -> Telegram numeric chat id
- GROQ_API_KEY    -> OPTIONAL: for AI ranking (if you have one)
- STORAGE_PATH    -> optional path for outputs (default ./digests)
- LOG_PATH        -> optional path for logs (default ./logs)

Usage:
- Run locally or in CI (GitHub Actions). Designed for scheduled runs.
"""
from __future__ import annotations
import os
import json
import time
import requests
import feedparser
import datetime
import hashlib
import logging
import re
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse

# -------------------------
# Configuration
# -------------------------
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
STORAGE_PATH = os.getenv("STORAGE_PATH", "./digests")
LOG_PATH = os.getenv("LOG_PATH", "./logs")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # optional ranking API
TELEGRAM_MAX = 3900  # safe per-message limit with MarkdownV2

# RSS / Sources - adjust as necessary
GLOBAL_RSS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://news.google.com/rss/search?q=fed+interest+rates+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=gdp+inflation+economy+when:1d&hl=en-US&gl=US&ceid=US:en",
]
INDIA_RSS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://news.google.com/rss/search?q=india+stock+market+sensex+nifty+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
]
WORLD_RSS = [
    "https://www.cnbc.com/id/100727362/device/rss/rss.xml",
    "https://news.google.com/rss/search?q=stock+market+nasdaq+dow+jones+when:1d&hl=en-US&gl=US&ceid=US:en",
]
BSE_RSS = "https://www.bseindia.com/xml-data/announce/RSS.xml"
NSE_BLOCK = "https://www.nseindia.com/api/block-deals?index=equities"
NSE_BULK = "https://www.nseindia.com/api/bulk-deals?index=equities"

# Logging
os.makedirs(LOG_PATH, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_PATH, "digest.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)


# -------------------------
# Utilities
# -------------------------
def now_ist() -> datetime.datetime:
    return datetime.datetime.utcnow() + IST_OFFSET


def ensure_dirs():
    os.makedirs(STORAGE_PATH, exist_ok=True)
    os.makedirs(LOG_PATH, exist_ok=True)


def short_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc or url
        # remove www.
        return host.replace("www.", "")
    except Exception:
        return url


def shorten_link(url: str) -> str:
    """Shorten URL using Short.io API with custom domain"""
    if not url or len(url) < 30:  # Don't shorten already short URLs
        return url
    
    # Short.io API configuration
    SHORTIO_API_KEY = os.getenv("SHORTIO_API_KEY")
    SHORTIO_DOMAIN = "abhij1306.short.gy"
    
    if not SHORTIO_API_KEY:
        logging.warning("Short.io API key not set, using original URL")
        return url
    
    for attempt in range(2):  # Try twice
        try:
            time.sleep(0.2)  # Small delay to avoid rate limiting
            headers = {
                "Authorization": SHORTIO_API_KEY,
                "Content-Type": "application/json"
            }
            data = {
                "originalURL": url,
                "domain": SHORTIO_DOMAIN
            }
            response = requests.post(
                "https://api.short.io/links",
                headers=headers,
                json=data,
                timeout=8
            )
            
            if response.status_code == 200:
                result = response.json()
                short_url = result.get("shortURL", "")
                if short_url:
                    logging.info("Shortened URL: %s -> %s", url[:50], short_url)
                    return short_url
            else:
                logging.warning("Short.io attempt %d failed (%s): %s", 
                              attempt + 1, response.status_code, response.text[:100])
                time.sleep(1)
        except Exception as e:
            logging.warning("Short.io attempt %d error: %s", attempt + 1, str(e)[:100])
            time.sleep(1)
    
    # If both attempts fail, return original URL
    logging.info("Using original URL after shortening failed")
    return url


def id_for_item(item: Dict[str, Any]) -> str:
    s = (item.get("title", "") or "") + "|" + (item.get("link", "") or "")
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# Clean HTML & entities
RE_TAG = re.compile(r"<[^>]+>")
RE_ENTITY = re.compile(r"&[a-zA-Z0-9#]+;")

def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = RE_TAG.sub("", raw)
    text = RE_ENTITY.sub(" ", text)
    # collapse whitespace
    return " ".join(text.split())


# Markdown V2 escaping (Telegram)
MDV2_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"

def escape_md_v2(text: str) -> str:
    if not text:
        return ""
    # Replace backslashes first
    text = text.replace("\\", "\\\\")
    out = []
    for ch in text:
        if ch in MDV2_ESCAPE_CHARS:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def chunk_text(s: str, limit: int = TELEGRAM_MAX) -> List[str]:
    if len(s) <= limit:
        return [s]
    chunks = []
    start = 0
    while start < len(s):
        end = min(start + limit, len(s))
        # try to break on newline for readability
        if end < len(s):
            nl = s.rfind("\n", start, end)
            if nl > start + 50:  # avoid tiny chunk
                end = nl
        chunks.append(s[start:end])
        start = end
    return chunks


# -------------------------
# Fetchers
# -------------------------
def fetch_rss(url: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        d = feedparser.parse(url)
        items = []
        for e in d.entries[:limit]:
            items.append({
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "summary": e.get("summary", "") or e.get("description", "")
            })
        logging.info("Fetched %d items from RSS %s", len(items), url)
        return items
    except Exception as e:
        logging.warning("RSS fetch error for %s: %s", url, str(e)[:200])
        return []


def fetch_nse_json(url: str) -> Dict[str, Any]:
    # Robust NSE fetch: handshake then JSON parse, with retries and validation
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    }
    session = requests.Session()
    for attempt in range(3):
        try:
            # initial GET to obtain cookies
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            r = session.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "application/json" not in ctype.lower():
                # sometimes NSE returns HTML or empty; treat as empty
                logging.warning("NSE returned non-json (ctype=%s) for %s", ctype, url)
                # try to parse as json fallback
                try:
                    data = r.json()
                except Exception:
                    data = []
                # Normalize to dict with 'data'
                if isinstance(data, list):
                    return {"data": data}
                if isinstance(data, dict):
                    return data
                return {"data": []}
            data = r.json()
            logging.info("NSE fetch success: %s items", len(data) if isinstance(data, list) else len(data.get("data", [])))
            if isinstance(data, list):
                return {"data": data}
            if isinstance(data, dict):
                return data
            return {"data": []}
        except Exception as e:
            logging.warning("NSE fetch attempt %d failed: %s", attempt + 1, str(e)[:200])
            time.sleep(1 + attempt)
    return {"data": []}


# -------------------------
# Optional AI ranking (defensive)
# -------------------------
def rank_with_groq(all_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not GROQ_API_KEY or len(all_items) == 0:
        return all_items
    try:
        # build simple prompt with titles
        titles = "\n".join(
            f"{i+1}. {clean_text(it.get('title',''))[:140]}" for i, it in enumerate(all_items[:30])
        )
        prompt = (
            "You are a financial news curator. From these headlines, select ONLY the most important and UNIQUE news "
            "relevant to market traders and investors. Focus on:\n"
            "- Fed/RBI decisions, interest rates, monetary policy\n"
            "- GDP, inflation, CPI, economic data\n"
            "- Major corporate actions (earnings, M&A, IPOs)\n"
            "- Stock market moves (Sensex, Nifty, Dow, Nasdaq)\n"
            "- Significant geopolitical events affecting markets\n\n"
            "EXCLUDE:\n"
            "- Personal finance advice\n"
            "- Celebrity/entertainment news\n"
            "- Duplicate stories (same event from different sources)\n"
            "- Minor company updates\n\n"
            "Headlines:\n" + titles + "\n\n"
            "Return ONLY the numbers of the top 8-10 UNIQUE, RELEVANT headlines, comma-separated (e.g., 3,1,7,2,9,4,8,5)"
        )
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 120
            },
            timeout=8
        )
        if resp.status_code != 200:
            logging.warning("GROQ non-200: %s", resp.status_code)
            return all_items
        body = resp.json()
        raw = body.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        nums = re.findall(r"\d+", raw)
        indices = [int(x) - 1 for x in nums if 0 < int(x) <= len(all_items)]
        ranked = [all_items[i] for i in indices]
        remaining = [all_items[i] for i in range(len(all_items)) if i not in indices]
        logging.info("AI ranked %d items", len(ranked))
        return ranked + remaining
    except Exception as e:
        logging.warning("AI ranking error: %s", str(e)[:200])
        return all_items


# -------------------------
# Formatter: Markdown V2 beautiful layout
# -------------------------
def format_item_plain(item: Dict[str, Any]) -> str:
    """Format news item in plain text with shortened link"""
    title = clean_text(item.get("title", "")).strip()
    if not title:
        return ""
    link = item.get("link", "") or ""
    
    # Shorten the link using Short.io
    short_link = shorten_link(link) if link else ""
    
    # Plain text format: bullet + title + link on next line
    return f"• {title}\n  {short_link}\n\n"


def build_plain_message(global_items: List[Dict[str, Any]],
                        india_items: List[Dict[str, Any]],
                        corporate_items: List[Dict[str, Any]],
                        world_items: List[Dict[str, Any]]) -> str:
    """Build plain text message with shortened links"""
    date_str = now_ist().strftime("%d %b %Y")
    header = f"📈 Daily Market Digest — {date_str}\n\n"
    sep = "━━━━━━━━━━━━━━━━\n\n"
    parts: List[str] = [header]

    # Global
    if global_items:
        parts.append("🌍 Global Macro Highlights\n\n")
        for it in global_items[:5]:
            parts.append(format_item_plain(it))
        parts.append(sep)

    # India
    if india_items:
        parts.append("🇮🇳 India Market Highlights\n\n")
        for it in india_items[:5]:
            parts.append(format_item_plain(it))
        parts.append(sep)

    # Corporate
    if corporate_items:
        parts.append("🏢 Corporate Actions (NSE / BSE)\n\n")
        for it in corporate_items[:8]:
            # corporate items might be structured dicts from NSE with symbol/qty/price
            sym = it.get("symbol") or it.get("title") or ""
            if isinstance(sym, dict):
                sym = sym.get("symbol", "")
            line = str(sym) # No escaping needed for plain text
            parts.append(f"• {line}\n")
        parts.append(sep)

    # World
    if world_items:
        parts.append("🌐 Major World Events\n\n")
        for it in world_items[:5]:
            parts.append(format_item_plain(it))


    text = "".join(parts)
    # final safety trim
    if len(text) > TELEGRAM_MAX:
        return text[:TELEGRAM_MAX]
    return text


# -------------------------
# Telegram sender (POST JSON)
# -------------------------
def send_telegram_markdown(message: str, parse_mode: str = None) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        logging.error("Telegram credentials missing - TG_TOKEN: %s, TG_CHAT_ID: %s", 
                     "SET" if TG_TOKEN else "MISSING", 
                     "SET" if TG_CHAT_ID else "MISSING")
        return False
    
    logging.info("Attempting to send Telegram message (length: %d chars)", len(message))
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    headers = {"Content-Type": "application/json"}
    chunks = chunk_text(message, TELEGRAM_MAX)
    logging.info("Message split into %d chunks", len(chunks))
    
    for idx, c in enumerate(chunks):
        logging.info("Sending chunk %d/%d", idx + 1, len(chunks))
        payload = {"chat_id": TG_CHAT_ID, "text": c}
        if parse_mode:  # Only add parse_mode if specified
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code != 200:
                logging.warning("Telegram API error %s: %s", r.status_code, r.text[:500])
                
                # If MarkdownV2 parsing failed, try plain text as fallback
                if parse_mode == "MarkdownV2" and "can't parse" in r.text.lower():
                    logging.info("MarkdownV2 parse error, retrying with plain text")
                    # Remove markdown formatting and retry
                    plain_text = c.replace("\\", "").replace("*", "").replace("_", "").replace("`", "")
                    payload_plain = {"chat_id": TG_CHAT_ID, "text": plain_text}
                    r2 = requests.post(url, json=payload_plain, timeout=15)
                    if r2.status_code == 200:
                        logging.info("Plain text fallback succeeded")
                        continue
                    else:
                        logging.error("Plain text fallback also failed: %s", r2.text[:500])
                        return False
                else:
                    return False
            else:
                logging.info("Chunk %d sent successfully", idx + 1)
            # small pause to avoid hitting rate limits
            time.sleep(0.4)
        except Exception as e:
            logging.exception("Telegram send exception: %s", str(e)[:200])
            return False
    
    logging.info("All chunks sent successfully")
    return True


# -------------------------
# Main pipeline
# -------------------------
def run_digest() -> Tuple[str, Dict[str, Any]]:
    ensure_dirs()
    all_items: List[Dict[str, Any]] = []
    seen_ids = set()

    # 1. Get RSS items
    sources = [
        (GLOBAL_RSS, 3),
        (INDIA_RSS, 3),
        ([BSE_RSS], 2),
        (WORLD_RSS, 3)
    ]
    for src_list, limit in sources:
        for url in src_list:
            try:
                items = fetch_rss(url, limit)
                for it in items:
                    it["title"] = it.get("title", "") or ""
                    it["link"] = it.get("link", "") or ""
                    it["summary"] = it.get("summary", "") or ""
                    iid = id_for_item(it)
                    if iid not in seen_ids:
                        seen_ids.add(iid)
                        all_items.append(it)
            except Exception as e:
                logging.warning("Error processing feed %s: %s", url, str(e)[:200])

    # 2. NSE corporate events (block / bulk) - DISABLED due to unreliable API (404 errors)
    corporate_items: List[Dict[str, Any]] = []
    # try:
    #     nse_block = fetch_nse_json(NSE_BLOCK)
    #     for blk in nse_block.get("data", [])[:10]:
    #         # blk is often a dict with symbol, quantity, avgprice
    #         corporate_items.append({
    #             "symbol": blk.get("symbol") if isinstance(blk, dict) else str(blk),
    #             "raw": blk
    #         })
    #     nse_bulk = fetch_nse_json(NSE_BULK)
    #     for b in nse_bulk.get("data", [])[:10]:
    #         corporate_items.append({
    #             "symbol": b.get("symbol") if isinstance(b, dict) else str(b),
    #             "raw": b
    #         })
    #     logging.info("Corporate items collected: %d", len(corporate_items))
    # except Exception as e:
    #     logging.warning("Error collecting corporate items: %s", str(e)[:200])

    # 3. Split all_items into categories via simple heuristics
    global_items, india_items, world_items = [], [], []
    for it in all_items:
        t = (it.get("title") or "").lower()
        if any(k in t for k in ["fed", "gdp", "cpi", "inflation", "interest rate", "rate decision", "imf", "rbi"]):
            global_items.append(it)
        elif any(k in t for k in ["india", "nse", "bse", "mumbai", "delhi", "reliance", "tata", "infosys", "hdfc"]):
            india_items.append(it)
        else:
            world_items.append(it)

    # 4. Optional AI ranking: apply per category if available
    if GROQ_API_KEY:
        try:
            global_items = rank_with_groq(global_items)
            india_items = rank_with_groq(india_items)
            world_items = rank_with_groq(world_items)
        except Exception:
            logging.warning("AI ranking skipped due to error")

    # 5. Trim category sizes and ensure diversity
    global_items = global_items[:8]
    india_items = india_items[:8]
    world_items = world_items[:6]
    corporate_items = corporate_items[:8]

    # 6. Build message and send
    msg = build_plain_message(global_items, india_items, corporate_items, world_items)
    success = send_telegram_markdown(msg)  # Will use plain text (parse_mode=None)
    status = {"telegram_sent": success, "items_collected": len(all_items), "corporate_items": len(corporate_items)}

    # 7. Persist digest for audit
    ts = now_ist().strftime("%Y%m%d_%H%M")
    out_file = os.path.join(STORAGE_PATH, f"digest_{ts}.md")
    try:
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(msg + "\n\n")
            fh.write("METADATA:\n")
            fh.write(json.dumps(status, ensure_ascii=False, indent=2))
        logging.info("Saved digest to %s", out_file)
    except Exception as e:
        logging.exception("Failed to write digest file: %s", str(e)[:200])

    return out_file, status


# -------------------------
# CLI entrypoint
# -------------------------
if __name__ == "__main__":
    logging.info("Starting digest run")
    try:
        out, st = run_digest()
        logging.info("Completed digest. File: %s Status: %s", out, st)
        print("Generated:", out)
    except Exception as fatal:
        logging.exception("Digest run failed: %s", str(fatal)[:200])
        raise
