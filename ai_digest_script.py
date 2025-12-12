#!/usr/bin/env python3
"""
ai_digest_script.py
AI Technology News Digest - Daily at 8 PM IST

Fetches and curates AI/ML/Tech news from various sources.
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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SHORTIO_API_KEY = os.getenv("SHORTIO_API_KEY", "REMOVED_SECRET")
SHORTIO_DOMAIN = "abhij1306.short.gy"
TELEGRAM_MAX = 3900

# AI/Tech News RSS Feeds
AI_TECH_RSS = [
    "https://news.google.com/rss/search?q=artificial+intelligence+AI+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=machine+learning+deep+learning+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=ChatGPT+OpenAI+Google+AI+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=LLM+generative+AI+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
]

# Logging
os.makedirs(LOG_PATH, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_PATH, "ai_digest.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)


# -------------------------
# Utilities (reuse from digest_script.py)
# -------------------------
def now_ist() -> datetime.datetime:
    return datetime.datetime.utcnow() + IST_OFFSET


def ensure_dirs():
    os.makedirs(STORAGE_PATH, exist_ok=True)
    os.makedirs(LOG_PATH, exist_ok=True)


def id_for_item(item: Dict[str, Any]) -> str:
    s = (item.get("title", "") or "") + "|" + (item.get("link", "") or "")
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


RE_TAG = re.compile(r"<[^>]+>")
RE_ENTITY = re.compile(r"&[a-zA-Z0-9#]+;")


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = RE_TAG.sub("", raw)
    text = RE_ENTITY.sub(" ", text)
    return " ".join(text.split())


def shorten_link(url: str) -> str:
    """Shorten URL using Short.io API"""
    if not url or len(url) < 30:
        return url
    
    if not SHORTIO_API_KEY:
        return url
    
    for attempt in range(2):
        try:
            time.sleep(0.2)
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
                logging.warning("Short.io attempt %d failed: %s", attempt + 1, response.text[:100])
                time.sleep(1)
        except Exception as e:
            logging.warning("Short.io error: %s", str(e)[:100])
            time.sleep(1)
    
    return url


def chunk_text(s: str, limit: int = TELEGRAM_MAX) -> List[str]:
    if len(s) <= limit:
        return [s]
    chunks = []
    start = 0
    while start < len(s):
        end = min(start + limit, len(s))
        if end < len(s):
            nl = s.rfind("\n", start, end)
            if nl > start + 50:
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


# -------------------------
# AI Ranking
# -------------------------
def rank_ai_news(all_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not GROQ_API_KEY or len(all_items) == 0:
        return all_items
    try:
        titles = "\n".join(
            f"{i+1}. {clean_text(it.get('title',''))[:140]}" for i, it in enumerate(all_items[:30])
        )
        prompt = (
            "You are an AI/Tech news curator. From these headlines, select ONLY the most important and UNIQUE news "
            "relevant to AI, machine learning, and technology professionals. Focus on:\n"
            "- Major AI model releases (GPT, Claude, Gemini, etc.)\n"
            "- Breakthrough research in AI/ML\n"
            "- Big tech AI announcements (Google, OpenAI, Meta, etc.)\n"
            "- AI regulations and policy\n"
            "- Significant AI startup funding/acquisitions\n"
            "- AI applications in industry\n\n"
            "EXCLUDE:\n"
            "- Generic tech news unrelated to AI\n"
            "- Duplicate stories (same event from different sources)\n"
            "- Minor product updates\n"
            "- Opinion pieces without news value\n\n"
            "Headlines:\n" + titles + "\n\n"
            "Return ONLY the numbers of the top 10-12 UNIQUE, RELEVANT AI/tech headlines, comma-separated (e.g., 3,1,7,2,9,4,8,5,11,6)"
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
                "max_tokens": 150
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
        logging.info("AI ranked %d items", len(ranked))
        return ranked
    except Exception as e:
        logging.warning("AI ranking error: %s", str(e)[:200])
        return all_items


# -------------------------
# Formatter
# -------------------------
def format_item_plain(item: Dict[str, Any]) -> str:
    title = clean_text(item.get("title", "")).strip()
    if not title:
        return ""
    link = item.get("link", "") or ""
    short_link = shorten_link(link) if link else ""
    return f"• {title}\n  {short_link}\n\n"


def build_ai_digest_message(items: List[Dict[str, Any]]) -> str:
    date_str = now_ist().strftime("%d %b %Y")
    header = f"🤖 AI & Tech Digest — {date_str}\n\n"
    parts: List[str] = [header]
    
    for it in items[:12]:
        parts.append(format_item_plain(it))
    
    text = "".join(parts)
    if len(text) > TELEGRAM_MAX:
        return text[:TELEGRAM_MAX]
    return text


# -------------------------
# Telegram
# -------------------------
def send_telegram(message: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        logging.error("Telegram credentials missing")
        return False
    
    logging.info("Attempting to send Telegram message (length: %d chars)", len(message))
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    chunks = chunk_text(message, TELEGRAM_MAX)
    logging.info("Message split into %d chunks", len(chunks))
    
    for idx, c in enumerate(chunks):
        logging.info("Sending chunk %d/%d", idx + 1, len(chunks))
        payload = {"chat_id": TG_CHAT_ID, "text": c}
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code != 200:
                logging.warning("Telegram API error %s: %s", r.status_code, r.text[:500])
                return False
            else:
                logging.info("Chunk %d sent successfully", idx + 1)
            time.sleep(0.4)
        except Exception as e:
            logging.exception("Telegram send exception: %s", str(e)[:200])
            return False
    
    logging.info("All chunks sent successfully")
    return True


# -------------------------
# Main
# -------------------------
def run_ai_digest() -> Tuple[str, Dict[str, Any]]:
    ensure_dirs()
    all_items: List[Dict[str, Any]] = []
    seen_ids = set()
    
    # Fetch from all AI/Tech RSS feeds
    for url in AI_TECH_RSS:
        try:
            items = fetch_rss(url, limit=5)
            for it in items:
                it["title"] = it.get("title", "") or ""
                it["link"] = it.get("link", "") or ""
                iid = id_for_item(it)
                if iid not in seen_ids:
                    seen_ids.add(iid)
                    all_items.append(it)
        except Exception as e:
            logging.warning("Error processing feed %s: %s", url, str(e)[:200])
    
    # AI ranking
    if GROQ_API_KEY:
        try:
            all_items = rank_ai_news(all_items)
        except Exception:
            logging.warning("AI ranking skipped due to error")
    
    # Build and send message
    msg = build_ai_digest_message(all_items)
    success = send_telegram(msg)
    status = {"telegram_sent": success, "items_collected": len(all_items)}
    
    # Save digest
    ts = now_ist().strftime("%Y%m%d_%H%M")
    out_file = os.path.join(STORAGE_PATH, f"ai_digest_{ts}.md")
    try:
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(msg + "\n\n")
            fh.write("METADATA:\n")
            fh.write(json.dumps(status, ensure_ascii=False, indent=2))
        logging.info("Saved AI digest to %s", out_file)
    except Exception as e:
        logging.exception("Failed to write digest file: %s", str(e)[:200])
    
    return out_file, status


if __name__ == "__main__":
    logging.info("Starting AI digest run")
    try:
        out, st = run_ai_digest()
        logging.info("Completed AI digest. File: %s Status: %s", out, st)
        print("Generated:", out)
    except Exception as fatal:
        logging.exception("AI digest run failed: %s", str(fatal)[:200])
        raise
