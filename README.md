# AI Career Assistant System

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

---

# Member 2 — Job Scraping & Verification Engineer

Branch: `feature/job-scraping-verification`

### Overview

This component provides two AI-powered agents for the Career Assistant System:

1. **Job Scraping Agent** (`/agents/job_scraping_agent.py`) — Collects job/internship listings from LinkedIn and Indeed
2. **Job Verification Agent** (`/agents/job_verification_agent.py`) — Validates, deduplicates, and quality-scores listings

### Project Structure

```
├── agents/
│   ├── __init__.py
│   ├── job_scraping_agent.py      # Job Scraping Agent
│   └── job_verification_agent.py  # Job Verification Agent
├── tools/
│   ├── __init__.py
│   ├── scraping_tools.py          # Indeed + LinkedIn scraping tools
│   └── verification_tools.py      # Company verification, dedup, flagging
├── tests/
│   ├── __init__.py
│   └── test_scraping_verification.py  # unit tests
├── config/
│   ├── __init__.py
│   └── settings.py                # Configuration (env vars, no hardcoded keys)
├── docs/
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
```

### Model

- **gpt-4o-mini** — Do NOT upgrade without lead approval

### Key Features

- Multi-platform scraping (Indeed + LinkedIn)
- Unique `job_id` per record with field standardisation across platforms
- Exponential backoff retry on API failures
- Rate limiting with queue-based retry scheduling
- Incomplete data flagged for manual review — pipeline never crashes
- Cross-platform duplicate detection (URL, fingerprint, fuzzy matching)
- Company legitimacy verification via heuristics
- Expired posting detection (posted_date vs deadline comparison)
- Suspicious listing flagging (payment requests, spelling errors, invalid links)
- Verified status output: `verified` / `rejected` / `flagged_for_review`
- All API credentials loaded from environment variables
- All outputs are valid JSON — no unhandled exceptions
- ≥ 95% accuracy filtering invalid listings (SRS 5.3)
