"""
Configuration settings for the AI-Based Career Assistant System.

All API credentials are loaded from environment variables — never hardcoded.
Model: gpt-4o-mini — do NOT upgrade without lead approval.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenAI / LLM Settings ─────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
LLM_MODEL = "gemini-2.5-flash"  # Switched to Gemini as requested

# ── Scraping Settings ──────────────────────────────────────────────
BASE_URL_INDEED = "https://pk.indeed.com"
SEARCH_URL_INDEED = f"{BASE_URL_INDEED}/jobs"

BASE_URL_LINKEDIN = "https://www.linkedin.com"
SEARCH_URL_LINKEDIN = f"{BASE_URL_LINKEDIN}/jobs/search"

# Rate limiting: random delay between requests (seconds)
MIN_DELAY = 6.0
MAX_DELAY = 12.0

# Maximum retries for a failed request
MAX_RETRIES = 3

# Maximum search result pages to scrape (safety cap)
MAX_PAGES = 20

# Only scrape jobs posted in the last N days
DAYS_FILTER = 7

# Proxy list for rotation (comma-separated string in .env)
PROXIES = [p for p in os.environ.get("PROXIES", "").split(",") if p.strip()]

# ── Retry / Backoff Settings ──────────────────────────────────────
RETRY_BASE_DELAY = 1.0       # Base delay for exponential backoff (seconds)
RETRY_MAX_DELAY = 60.0       # Maximum delay between retries (seconds)
RETRY_BACKOFF_FACTOR = 2.0   # Exponential backoff multiplier

# ── Queue Settings ─────────────────────────────────────────────────
RATE_LIMIT_QUEUE_SIZE = 100   # Maximum number of queued requests

# ── Database ───────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

# ── Logging ────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "scraper.log")

# ── Verification Settings ─────────────────────────────────────────
COMPANY_VERIFICATION_API = os.environ.get("COMPANY_VERIFICATION_API", "")
SUSPICIOUS_KEYWORDS = [
    "wire transfer", "western union", "moneygram", "upfront payment",
    "processing fee", "registration fee", "advance payment",
    "send money", "pay to apply", "guaranteed income",
    "no experience needed and high salary", "too good to be true",
]

# Minimum required fields for a job listing to be considered valid
REQUIRED_JOB_FIELDS = ["title", "company", "description"]
