# 📈 Daily Market Digest

An automated news aggregation and curation system that delivers curated market news, AI/tech updates, and breaking stock alerts directly to Telegram. Powered by AI-based ranking and scheduled via GitHub Actions.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions)

## ✨ Features

### 📊 Daily Market Digest (`digest_script.py`)
- **Global Macro News**: Fed decisions, GDP, inflation, interest rates
- **India Market Coverage**: BSE/NSE updates, Sensex, Nifty movements  
- **World Markets**: NASDAQ, Dow Jones, major global events
- **AI-Powered Curation**: Uses Groq LLM to rank and filter the most relevant headlines
- **Runs daily at 8:00 AM IST**

### 🤖 AI & Tech Digest (`ai_digest_script.py`)
- **AI/ML Headlines**: Coverage of ChatGPT, OpenAI, Google AI, LLMs
- **Tech Industry News**: TechCrunch, The Verge integration
- **Smart Filtering**: AI ranks headlines by relevance and importance
- **Runs daily at 8:00 PM IST**

### 🚨 Breaking News Alerts (`breaking_news.py`)
- **Real-time Stock Alerts**: Recent breaking stock market news
- **Market Hours Focus**: Runs every 3 hours during trading hours (9 AM - 6 PM IST, weekdays)
- **Time-Sensitive**: Filters for news from the last 3-4 hours only

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11 |
| RSS Parsing | `feedparser` |
| HTTP Client | `requests` |
| AI Ranking | Groq API (Llama 3.3 70B) |
| URL Shortening | Short.io |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions (cron) |

## 📡 Data Sources

- **Financial RSS**: Reuters Business, MarketWatch, Economic Times, Business Standard
- **Tech RSS**: Google News (AI queries), TechCrunch, The Verge
- **India Markets**: NSE/BSE announcements, ET Markets
- **Global Markets**: CNBC, Google News (market queries)

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Telegram Bot Token ([create one](https://core.telegram.org/bots#creating-a-new-bot))
- Telegram Chat ID

### Installation

```bash
# Clone the repository
git clone https://github.com/abhij1306/daily-market-digest.git
cd daily-market-digest

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies
pip install feedparser requests
```

### Environment Variables

```bash
# Required
export TG_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"

# Optional - enables AI ranking
export GROQ_API_KEY="your_groq_api_key"

# Optional - enables URL shortening  
export SHORTIO_API_KEY="your_shortio_api_key"
```

### Run Locally

```bash
# Run market digest
python digest_script.py

# Run AI/tech digest  
python ai_digest_script.py

# Run breaking news check
python breaking_news.py
```

## ⚙️ GitHub Actions Workflows

The project includes automated workflows for scheduled execution:

| Workflow | Schedule | Description |
|----------|----------|-------------|
| `digest.yml` | 02:30 UTC (08:00 IST) | Daily market digest |
| `ai-digest.yml` | 14:30 UTC (20:00 IST) | AI & tech news digest |
| `breaking-news.yml` | Every 3h (market hours) | Breaking stock alerts |

### Required GitHub Secrets

Configure these in your repository settings → Secrets → Actions:

- `TG_TOKEN` - Telegram bot token
- `TG_CHAT_ID` - Telegram chat/channel ID
- `GROQ_API_KEY` - Groq API key (optional but recommended)
- `SHORTIO_API_KEY` - Short.io API key (optional)

## 📂 Project Structure

```
daily-market-digest/
├── .github/
│   └── workflows/
│       ├── digest.yml           # Daily market digest workflow
│       ├── ai-digest.yml        # AI tech news workflow
│       └── breaking-news.yml    # Breaking news alerts workflow
├── digests/                     # Archived digest files (markdown)
├── logs/                        # Application logs
├── digest_script.py             # Main market digest script
├── ai_digest_script.py          # AI/tech news digest script
├── breaking_news.py             # Breaking stock alerts script
├── .gitignore
├── LICENSE
└── README.md
```

## 📄 Sample Output

```
📈 Daily Market Digest — 16 Jan 2026

🌍 Global Macro Highlights

• Fed Signals Pause in Rate Cuts Amid Inflation Concerns
  https://abhij1306.short.gy/abc123

• IMF Revises Global Growth Forecast to 3.2% for 2026
  https://abhij1306.short.gy/def456

━━━━━━━━━━━━━━━━

🇮🇳 India Market Highlights

• Sensex Crosses 85,000 Mark on Strong FII Inflows
  https://abhij1306.short.gy/ghi789

• RBI Holds Repo Rate Steady at 6.5%
  https://abhij1306.short.gy/jkl012
```

## 🔧 Configuration

### Customizing RSS Sources

Edit the feed lists in `digest_script.py`:

```python
GLOBAL_RSS = [
    "https://feeds.reuters.com/reuters/businessNews",
    # Add your preferred sources
]

INDIA_RSS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    # Add India-specific sources
]
```

### Adjusting Schedule

Modify the cron expressions in `.github/workflows/*.yml`:

```yaml
on:
  schedule:
    - cron: "30 2 * * *"   # Customize timing
```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 👤 Author

**abhij1306**

- GitHub: [@abhij1306](https://github.com/abhij1306)

---

⭐ Star this repo if you find it useful!
