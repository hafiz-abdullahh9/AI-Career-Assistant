"""
Scraping tools for Indeed and LinkedIn job platforms.

Tools:
  - scrape_indeed_jobs(keyword, location, job_type, experience_level, proxies)
  - scrape_linkedin_jobs(keyword, location, job_type, experience_level, proxies)

Adapted from the existing Crawl4AI-based Indeed scraper in the parent project.
Handles:
  - Search result pagination
  - Detail page extraction (full description + apply link)
  - Rate limiting with random delays
  - Proxy rotation
  - Retry logic with exponential backoff
  - Unique job_id assignment per record
  - Field standardisation across platforms
"""

import asyncio
import random
import logging
import uuid
import re
import html
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlencode, quote_plus, urlparse, parse_qs

logger = logging.getLogger("career_assistant.scraping")

try:
    from config import settings as _settings   # adjust if your path differs
except Exception:
    try:
        import settings as _settings
    except Exception:
        _settings = None

def _cfg(name, default):
    return getattr(_settings, name, default) if _settings else default


# ═══════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS — shared by both platform scrapers
# ═══════════════════════════════════════════════════════════════════

def _generate_job_id(platform: str, source_url: str) -> str:
    """Generate a deterministic unique job_id from platform + URL."""
    raw = f"{platform}:{source_url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _clean_html(text: str, keep_newlines: bool = False) -> str:
    """Strip HTML tags, decode entities, and normalise whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<p[^>]*?>", "\n", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    if keep_newlines:
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_relevant(title: str, keyword: str) -> bool:
    """
    Check if the job title is relevant to the search keyword.
    Returns True if at least one token from the keyword is found in the title.
    """
    if not title or not keyword:
        return False
    # Simple tokenization: lowercase and extract alphanumeric words
    title_tokens = set(re.findall(r'\w+', title.lower()))
    keyword_tokens = set(re.findall(r'\w+', keyword.lower()))
    return bool(title_tokens.intersection(keyword_tokens))


def _is_valid_url(url: str) -> bool:
    """Validate that a string is a properly formatted URL or mailto link."""
    if not url:
        return False
    url = url.strip()
    if url.startswith("mailto:"):
        return True
    if any(url.lower().split('?')[0].endswith(ext) for ext in
           [".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".json", ".xml"]):
        return False
    blocklist = [
        "/browsejobs", "/support", "/legal", "/promo", "/hire",
        "/preferences", "/cookies", "/contact",
        "support.indeed.com", "secure.indeed.com",
    ]
    if any(term in url.lower() for term in blocklist):
        return False
    return bool(re.match(r'^https?://[^\s/$.?#].[^\s]*$', url, re.IGNORECASE))


def _normalize_relative_date(raw_date: str) -> str:
    """
    Normalise raw date text to standardised YYYY-MM-DD.
    Handles: "Just posted", "Today", "Yesterday", "N days ago", etc.
    """
    if not raw_date:
        return ""
    text = raw_date.strip().lower()
    text = re.sub(r'\b(?:employer|posted|active|state|myjobsstatedate)\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    ref_date = datetime.now()

    if "just" in text or "today" in text:
        delta_days = 0
    elif "yesterday" in text:
        delta_days = 1
    elif "30+" in text or "30+ days" in text:
        delta_days = 30
    else:
        digits = re.findall(r'(\d+)', text)
        if digits:
            delta_days = int(digits[0])
        elif "a day" in text or "one day" in text:
            delta_days = 1
        else:
            return ""

    result_date = ref_date - timedelta(days=delta_days)
    return result_date.strftime("%Y-%m-%d")


def _parse_job_type(chunk: str) -> str:
    """Extract job type keywords from an HTML chunk or text string."""
    if not chunk:
        return ""
    valid_types = [
        "full-time", "part-time", "contract", "internship",
        "temporary", "remote", "hybrid", "on-site", "freelance",
    ]
    found_types = []
    cleaned = _clean_html(chunk).lower()
    for vt in valid_types:
        if re.search(rf'\b{re.escape(vt)}\b', cleaned):
            cap_vt = vt.capitalize()
            if cap_vt not in found_types:
                found_types.append(cap_vt)
    return ", ".join(found_types) if found_types else ""


def _extract_salary(text: str) -> str:
    """Attempt to extract salary information from text."""
    if not text:
        return ""
    patterns = [
        r'(?:Rs\.?|PKR|USD|\$|£|€)\s*[\d,]+(?:\s*[-–]\s*(?:Rs\.?|PKR|USD|\$|£|€)?\s*[\d,]+)?(?:\s*(?:per|/)\s*(?:month|year|annum|hr|hour|day))?',
        r'[\d,]+\s*[-–]\s*[\d,]+\s*(?:PKR|USD|Rs\.?|per\s*(?:month|year|annum))',
        r'(?:salary|compensation|pay)\s*[:：]\s*[^\n]+',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""


def _extract_deadline(text: str) -> str:
    """Attempt to extract application deadline from text."""
    if not text:
        return ""
    patterns = [
        r'(?:deadline|apply\s+by|last\s+date|closing\s+date)\s*[:：]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'(?:deadline|apply\s+by|last\s+date|closing\s+date)\s*[:：]?\s*(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:deadline|apply\s+by|last\s+date|closing\s+date)\s*[:：]?\s*([^\n,]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _extract_contact_info(text: str) -> str:
    """Extract contact information (emails, phones) from text."""
    if not text:
        return ""
    contacts = []
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    contacts.extend(emails)
    phones = re.findall(r'(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}', text)
    contacts.extend(phones)
    return "; ".join(contacts) if contacts else ""


def _extract_required_skills(description: str) -> list[str]:
    """Extract skills from the job description using keyword matching."""
    if not description:
        return []
    common_skills = [
        "python", "java", "javascript", "typescript", "c++", "c#", "ruby", "go",
        "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
        "sql", "nosql", "mongodb", "postgresql", "mysql", "redis",
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
        "machine learning", "deep learning", "data science", "ai",
        "html", "css", "git", "agile", "scrum", "rest api", "graphql",
        "excel", "power bi", "tableau", "sap", "erp",
        "communication", "leadership", "teamwork", "problem solving",
        "project management", "data analysis", "data entry",
    ]
    text_lower = description.lower()
    found = []
    for skill in common_skills:
        if re.search(rf'\b{re.escape(skill)}\b', text_lower):
            found.append(skill.title())
    return found


def _extract_json_object(text: str, start_pos: int) -> str:
    """Find the matching closing brace for the opening brace at start_pos."""
    brace_count = 0
    in_string = False
    escape = False
    quote_char = None

    for idx in range(start_pos, len(text)):
        char = text[idx]
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char in ['"', "'"]:
            if not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char:
                in_string = False
                quote_char = None
            continue
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_pos:idx + 1]
    return ""


def _canonical_indeed_url(href: str) -> str:
    """Reduce any Indeed job link to a stable canonical form using jobkey."""
    BASE = "https://pk.indeed.com"
    if not href:
        return ""
    absolute = urljoin(BASE, href)
    jk_match = re.search(r"[?&]jk=([0-9a-fA-F]+)", absolute)
    if jk_match:
        return f"{BASE}/viewjob?jk={jk_match.group(1)}"
    parsed = urlparse(absolute)
    qs = parse_qs(parsed.query)
    for key in ("jk", "jobkey"):
        if key in qs and qs[key]:
            return f"{BASE}/viewjob?jk={qs[key][0]}"
    return absolute


def _standardise_job_record(raw: dict, platform: str) -> dict:
    """
    Standardise a raw job record into the canonical schema.
    Returns a dict with all required fields for the Career Assistant system.
    """
    source_url = raw.get("source_url", raw.get("detail_url", ""))
    job_id = _generate_job_id(platform, source_url)
    description = raw.get("description", "")

    return {
        "job_id": job_id,
        "platform": platform,
        "title": raw.get("title", ""),
        "company": raw.get("company", ""),
        "description": description,
        "required_skills": raw.get("required_skills") or _extract_required_skills(description),
        "location": raw.get("location", ""),
        "salary": raw.get("salary") or _extract_salary(description),
        "job_type": raw.get("job_type", ""),
        "date_posted": raw.get("date_posted", ""),
        "application_deadline": raw.get("application_deadline") or _extract_deadline(description),
        "contact_info": raw.get("contact_info") or _extract_contact_info(description),
        "apply_link": raw.get("apply_link", ""),
        "source_url": source_url,
        "scraped_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
#  RATE LIMITING & RETRY
# ═══════════════════════════════════════════════════════════════════

async def _rate_limit(min_delay: float = None, max_delay: float = None):
    """Sleep for a random delay to be polite (uses settings MIN/MAX_DELAY)."""
    if min_delay is None:
        min_delay = _cfg("MIN_DELAY", 2.0)
    if max_delay is None:
        max_delay = _cfg("MAX_DELAY", 4.0)
    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)


async def _fetch_with_retry(crawler, url: str, config, retries: int = 2):
    """Fetch a URL with retry logic and exponential backoff."""
    last_error = "Unknown error"
    for attempt in range(retries + 1):
        try:
            result = await crawler.arun(url=url, config=config)
            if result.success:
                return result
            else:
                last_error = result.error_message
                logger.warning(
                    f"Attempt {attempt + 1}/{retries + 1} failed for {url}: {result.error_message}"
                )
        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"Attempt {attempt + 1}/{retries + 1} exception for {url}: {e}"
            )

        if attempt < retries:
            backoff = min(60.0, (2 ** attempt) * 1.0)
            logger.info(f"Retrying in {backoff:.1f}s (exponential backoff)")
            await asyncio.sleep(backoff)

    logger.error(f"All {retries + 1} attempts failed for {url}. Last error: {last_error}")
    return None


# ═══════════════════════════════════════════════════════════════════
#  PROXY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

class ProxyRotator:
    """Round-robin proxy selector."""

    def __init__(self, proxies: Optional[list[str]] = None):
        self.proxies = proxies or []
        self._index = 0

    def next(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy


# ═══════════════════════════════════════════════════════════════════
#  INDEED SCRAPING TOOL
# ═══════════════════════════════════════════════════════════════════

def _build_indeed_search_url(keyword: str, location: str = "", job_type: str = "",
                             start: int = 0, experience_level: str = "",
                             days_filter: int = None) -> str:
    """Build Indeed search URL with filters."""
    if days_filter is None:
        days_filter = _cfg("DAYS_FILTER", 7)
    params = {"q": keyword, "fromage": days_filter, "start": start}
    if location:
        params["l"] = location
    if job_type:
        jt_map = {"full-time": "fulltime", "part-time": "parttime", "contract": "contract",
                  "internship": "internship", "temporary": "temporary"}
        jt = jt_map.get(job_type.lower(), "")
        if jt:
            params["jt"] = jt
    if experience_level:
        exp_map = {"entry": "ENTRY_LEVEL", "entry-level": "ENTRY_LEVEL",
                   "mid": "MID_LEVEL", "mid-level": "MID_LEVEL", "senior": "SENIOR_LEVEL"}
        ex = exp_map.get(experience_level.lower().replace("_", "-"), "")
        if ex:
            params["explvl"] = ex
    return f"https://pk.indeed.com/jobs?{urlencode(params)}"


def _parse_indeed_search_results(html_content: str, keyword: str) -> list[dict]:
    """
    Parse job cards from Indeed search results HTML.
    Uses JSON provider data extraction first, with HTML fallback.
    """
    listings = []

    # 1. Try JSON extraction first (highly robust)
    try:
        script_match = re.search(
            r'window\.mosaic\.providerData\[[\'"]mosaic-provider-jobcards[\'"]\]\s*=\s*(\{.*)',
            html_content, re.DOTALL | re.IGNORECASE
        )
        if not script_match:
            script_match = re.search(
                r'window\.mosaic\.initialData\s*=\s*(\{.*)',
                html_content, re.DOTALL | re.IGNORECASE
            )
        if not script_match:
            script_match = re.search(
                r'window\._initialData\s*=\s*(\{.*)',
                html_content, re.DOTALL | re.IGNORECASE
            )
        if not script_match:
            script_match = re.search(
                r'(?:_initialData|initialData)\s*=\s*(\{.*)',
                html_content, re.DOTALL | re.IGNORECASE
            )

        if script_match:
            script_text = script_match.group(1).strip()
            start_idx = script_text.find('{')
            if start_idx != -1:
                json_str = _extract_json_object(script_text, start_idx)
                if json_str:
                    data = json.loads(json_str)
                    results = []
                    if 'metaData' in data and 'mosaicProviderJobCardsModel' in data['metaData']:
                        results = data['metaData']['mosaicProviderJobCardsModel'].get('results', [])
                    elif 'hostQueryExecutionResult' in data:
                        results = data['hostQueryExecutionResult'].get('data', {}).get('jobData', {}).get('results', [])
                    elif 'results' in data:
                        results = data['results']

                    if results:
                        logger.info(f"Extracted {len(results)} jobs from Indeed JSON data.")
                        for job in results:
                            if isinstance(job, dict) and 'job' in job:
                                job_data = job['job']
                            else:
                                job_data = job
                            if not isinstance(job_data, dict):
                                continue

                            title = _clean_html(job_data.get('title', ''))
                            if not _is_relevant(title, keyword):
                                continue

                            company = _clean_html(
                                str(job_data.get('company', '') or
                                    job_data.get('companyName', '') or
                                    job_data.get('sourceEmployerName', '') or
                                    job_data.get('truncatedCompany', '') or '')
                            )
                            location = _clean_html(
                                job_data.get('formattedLocation', '') or
                                job_data.get('location', '') or ''
                            )
                            raw_date = _clean_html(
                                job_data.get('formattedRelativeTime', '') or
                                job_data.get('formattedRelativeDate', '') or ''
                            )
                            date_posted = _normalize_relative_date(raw_date)

                            job_types_list = job_data.get('jobTypes', []) or job_data.get('jobType', []) or []
                            if isinstance(job_types_list, list):
                                job_type = ", ".join(
                                    str(jt).capitalize() for jt in job_types_list if jt
                                )
                            elif isinstance(job_types_list, str):
                                job_type = _parse_job_type(job_types_list)
                            else:
                                job_type = ""

                            jobkey = job_data.get('jobkey', '') or job_data.get('jobKey', '') or ''
                            if jobkey:
                                raw_url = f"https://pk.indeed.com/viewjob?jk={jobkey}"
                            else:
                                link = job_data.get('link', '')
                                raw_url = urljoin("https://pk.indeed.com", link)
                            detail_url = _canonical_indeed_url(raw_url)
                            
                            snippet_html = job_data.get('snippet', '') or job_data.get('snippetText', '') or ''
                            description = _clean_html(snippet_html, keep_newlines=True)

                            listings.append({
                                "title": title,
                                "company": company,
                                "location": location,
                                "date_posted": date_posted,
                                "job_type": job_type,
                                "detail_url": detail_url,
                                "description": description,
                            })

                        if listings:
                            return listings
    except Exception as e:
        logger.warning(f"Failed to extract Indeed results from JSON: {e}. Falling back to HTML.")

    # 2. Fallback to HTML card-by-card parsing
    card_chunks = re.split(
        r'<div[^>]*?class="[^"]*?(?:job_seen_beacon|cardOutline|resultContent)[^"]*?"',
        html_content
    )
    if len(card_chunks) > 1:
        logger.info(f"HTML fallback: parsing {len(card_chunks) - 1} card blocks")
        for chunk in card_chunks[1:]:
            chunk = re.sub(r'<script[^>]*?>.*?</script>', '', chunk, flags=re.DOTALL | re.IGNORECASE)
            chunk = re.sub(r'<style[^>]*?>.*?</style>', '', chunk, flags=re.DOTALL | re.IGNORECASE)

            title_match = re.search(
                r'<a[^>]*?class="[^"]*?jcs-JobTitle[^"]*?"[^>]*?href="([^"]*?)"[^>]*?>(.*?)</a>',
                chunk, re.DOTALL | re.IGNORECASE
            )
            if not title_match:
                title_match = re.search(
                    r'<a[^>]*?href="([^"]*?(?:/rc/clk|/pagead/clk|/company/[^"]*?/jobs/[^"]*?)[^"]*?)"[^>]*?>(.*?)</a>',
                    chunk, re.DOTALL | re.IGNORECASE
                )
            if not title_match:
                continue

            href = title_match.group(1)
            title = _clean_html(title_match.group(2))
            if not title or not _is_relevant(title, keyword):
                continue
                
            detail_url = _canonical_indeed_url(urljoin("https://pk.indeed.com", href))

            company_match = re.search(
                r'<span[^>]*?data-testid="company-name"[^>]*?>(.*?)</span>',
                chunk, re.DOTALL | re.IGNORECASE
            )
            company = _clean_html(company_match.group(1)) if company_match else ""

            location_match = re.search(
                r'<div[^>]*?data-testid="text-location"[^>]*?>(.*?)</div>',
                chunk, re.DOTALL | re.IGNORECASE
            )
            location = _clean_html(location_match.group(1)) if location_match else ""

            job_type = _parse_job_type(chunk)

            date_match = re.search(
                r'data-testid="myJobsStateDate"[^>]*?>(.*?)</(?:span|div|td)>',
                chunk, re.DOTALL | re.IGNORECASE
            )
            if not date_match:
                date_match = re.search(
                    r'<(?:span|div|td)[^>]*?>(.*?(?:just\s+posted|today|yesterday|ago|\d+\+?\s+days?|active).*?)</(?:span|div|td)>',
                    chunk, re.DOTALL | re.IGNORECASE
                )
            raw_date = _clean_html(date_match.group(1)) if date_match else ""
            date_posted = _normalize_relative_date(raw_date)
            
            snippet_match = re.search(
                r'<div[^>]*?class="[^"]*?(?:job-snippet|summary)[^"]*?"[^>]*?>(.*?)</div>',
                chunk, re.DOTALL | re.IGNORECASE
            )
            description = _clean_html(snippet_match.group(1), keep_newlines=True) if snippet_match else ""

            listings.append({
                "title": title,
                "company": company,
                "location": location,
                "date_posted": date_posted,
                "job_type": job_type,
                "detail_url": detail_url,
                "description": description,
            })

    logger.info(f"Parsed {len(listings)} job cards from Indeed search page")
    return listings


def _has_indeed_next_page(html_content: str) -> bool:
    """Check if there's a next page of Indeed results."""
    return bool(re.search(
        r'<a[^>]*?aria-label="Next Page"[^>]*?>|'
        r'<a[^>]*?data-testid="pagination-page-next"[^>]*?>|'
        r'<nav[^>]*?>.*?<a[^>]*?aria-label="Next"[^>]*?>',
        html_content, re.DOTALL | re.IGNORECASE,
    ))


def _parse_indeed_apply_link(html_content: str, detail_url: str) -> str:
    """Extract the direct application link from an Indeed detail page."""
    if not html_content:
        return ""

    # 1. Indeed apply data attributes
    for attr in ['data-indeed-apply-joburl', 'data-indeed-apply-apiurl']:
        match = re.search(f'{attr}="([^"]+)"', html_content, re.IGNORECASE)
        if match and _is_valid_url(match.group(1).strip()):
            return match.group(1).strip()

    # 2. Apply button classes
    match = re.search(
        r'<a[^>]*?class="[^"]*?(?:apply-button|indeed-apply-button|jobsearch-IndeedApplyButton)[^"]*?"[^>]*?href="([^"]*?)"',
        html_content, re.IGNORECASE
    )
    if match and _is_valid_url(match.group(1).strip()):
        return match.group(1).strip()

    # 3. CTA containers
    match = re.search(
        r'class="[^"]*?CallToActionButton[^"]*?".*?href="([^"]*?)"',
        html_content, re.DOTALL | re.IGNORECASE
    )
    if match and _is_valid_url(match.group(1).strip()):
        return match.group(1).strip()

    # 4. Links containing apply/jobs
    matches = re.findall(
        r'href="(https?://[^"]*?(?:apply|mailto|jobs)[^"]*?)"',
        html_content, re.IGNORECASE
    )
    for url in matches:
        if _is_valid_url(url):
            return url

    # 5. Fallback: email in body
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', html_content)
    if email_match:
        return f"mailto:{email_match.group(0)}"

    return ""


def _parse_indeed_description(html_content: str) -> str:
    """Extract the full job description from an Indeed detail page."""
    if not html_content:
        return ""
    m = re.search(r'<div[^>]*id="jobDescriptionText"[^>]*>(.*?)</div>\s*</div>',
                  html_content, re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.search(r'<div[^>]*id="jobDescriptionText"[^>]*>(.*?)</div>',
                      html_content, re.DOTALL | re.IGNORECASE)
    return _clean_html(m.group(1), keep_newlines=True) if m else ""

def _parse_linkedin_description(html_content: str) -> str:
    """Extract the full job description from a LinkedIn detail page."""
    if not html_content:
        return ""
    m = re.search(
        r'<div[^>]*class="[^"]*?(?:show-more-less-html__markup|description__text)[^"]*?"[^>]*>(.*?)</div>',
        html_content, re.DOTALL | re.IGNORECASE)
    return _clean_html(m.group(1), keep_newlines=True) if m else ""


async def scrape_indeed_jobs(
    keyword: str,
    location: str = "",
    job_type: str = "",
    experience_level: str = "",
    proxies: Optional[list[str]] = None,
    max_pages: int = 20,
) -> list[dict]:
    """
    Scrape job/internship listings from Indeed using search filters.

    Args:
        keyword: Search keyword (e.g. "Python Developer")
        location: Location filter (e.g. "Lahore")
        job_type: Job type filter (e.g. "Full-time", "Internship")
        experience_level: Experience level filter
        proxies: Optional list of proxy URLs for rotation
        max_pages: Maximum search result pages to scrape

    Returns:
        List of standardised job records with all extracted fields.

    Error Handling:
        - API connection failures: retry with exponential backoff
        - Rate limiting: implements queue and schedule retries
        - Incomplete job data: logged and flagged — never crashes the pipeline
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    proxy_rotator = ProxyRotator(proxies)
    all_jobs = []
    seen_urls: set[str] = set()

    proxy = proxy_rotator.next()
    browser_config = BrowserConfig(
        headless=False,
        enable_stealth=True,               # real kwarg in 0.8.x; combine with undetected below
        browser_type="chromium",
        proxy=proxy,                       # None right now — that's fine, home IP works
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        viewport_width=1920,
        viewport_height=1080,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=60000,
        wait_until="load",                 # NOT domcontentloaded — let the CF sensor finish
        session_id="indeed_session",       # reuse ONE warm context across all requests
        magic=True,
        simulate_user=True,
        override_navigator=True,
        delay_before_return_html=12.0,     # give the challenge time to clear before reading HTML
    )

    logger.info(f"Starting Indeed scrape: keyword='{keyword}', location='{location}', "
                f"job_type='{job_type}', max_pages={max_pages}")

    try:
        from crawl4ai import UndetectedAdapter
        from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

        undetected_adapter = UndetectedAdapter()
        crawler_strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            browser_adapter=undetected_adapter,
        )
        async with AsyncWebCrawler(
            crawler_strategy=crawler_strategy,
            config=browser_config,
        ) as crawler:
            # Phase 1: Scrape search pages
            page, start = 0, 0
            while page < max_pages:
                url = _build_indeed_search_url(keyword, location, job_type, start,
                                               experience_level=experience_level)
                logger.info(f"Indeed search page {page + 1}: {url}")

                result = await _fetch_with_retry(crawler, url, crawler_config)
                if not result or not result.html:
                    logger.warning(f"Failed to fetch Indeed page {page + 1}")
                    break

                listings = _parse_indeed_search_results(result.html, keyword)
                if not listings:
                    logger.info("No more Indeed listings found.")
                    break

                new = [l for l in listings if l["detail_url"] not in seen_urls]
                for listing in new:
                    seen_urls.add(listing["detail_url"])
                    detail_html = ""
                    try:
                        dres = await _fetch_with_retry(crawler, listing["detail_url"], crawler_config)
                        detail_html = dres.html if dres else ""
                    except Exception as exc:
                        logger.warning(f"Indeed detail fetch failed {listing['detail_url']}: {exc}")
                    if detail_html:
                        desc = _parse_indeed_description(detail_html)
                        if desc:
                            listing["description"] = desc
                        listing["apply_link"] = (_parse_indeed_apply_link(detail_html, listing["detail_url"])
                                                 or listing["detail_url"])
                    else:
                        listing["apply_link"] = listing.get("apply_link") or listing["detail_url"]
                    listing["source_url"] = listing["detail_url"]
                    await _rate_limit()
                    try:
                        all_jobs.append(_standardise_job_record(listing, "indeed"))
                    except Exception as exc:
                        logger.error(f"Error standardising {listing['detail_url']}: {exc}")

                page += 1
                if not _has_indeed_next_page(result.html):
                    break
                start += 10
                await _rate_limit()

    except Exception as exc:
        logger.error(f"Indeed scrape failed: {exc}")
        # Never crash the pipeline — return whatever we have
        if not all_jobs:
            raise

    logger.info(f"Indeed scrape complete: {len(all_jobs)} total jobs collected")
    return all_jobs


# ═══════════════════════════════════════════════════════════════════
#  LINKEDIN SCRAPING TOOL
# ═══════════════════════════════════════════════════════════════════

def _build_linkedin_search_url(keyword: str, location: str = "", job_type: str = "",
                               start: int = 0, experience_level: str = "",
                               days_filter: int = None) -> str:
    """Build LinkedIn *guest* job-search URL (returns real card markup)."""
    if days_filter is None:
        days_filter = _cfg("DAYS_FILTER", 7)
    params = {"keywords": keyword, "start": start}
    if location:
        params["location"] = location
    if job_type:
        jt_map = {"full-time": "F", "part-time": "P", "contract": "C",
                  "internship": "I", "temporary": "T"}
        jt = jt_map.get(job_type.lower(), "")
        if jt:
            params["f_JT"] = jt
    if experience_level:
        exp_map = {"internship": "1", "entry": "2", "entry-level": "2", "associate": "3",
                   "mid": "4", "mid-senior": "4", "senior": "4", "director": "5", "executive": "6"}
        ex = exp_map.get(experience_level.lower().replace("_", "-"), "")
        if ex:
            params["f_E"] = ex
    if days_filter:
        params["f_TPR"] = f"r{int(days_filter) * 86400}"
    return f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{urlencode(params)}"


def _parse_linkedin_search_results(html_content: str, keyword: str) -> list[dict]:
    """Parse job cards from LinkedIn search results HTML."""
    listings = []

    # LinkedIn uses data-entity-urn or job-card-container patterns
    card_matches = re.findall(
        r'<div[^>]*?class="[^"]*?(?:job-search-card|base-card|jobs-search__results-list)[^"]*?"[^>]*?>(.*?)</div>\s*</div>',
        html_content, re.DOTALL | re.IGNORECASE
    )

    # Alternative: look for list items with job data
    if not card_matches:
        card_matches = re.findall(
            r'<li[^>]*?>(.*?)</li>',
            html_content, re.DOTALL | re.IGNORECASE
        )

    for chunk in card_matches:
        # Extract title and link
        title_match = re.search(
            r'<a[^>]*?class="[^"]*?(?:base-card__full-link|job-card-container__link)[^"]*?"[^>]*?href="([^"]*?)"[^>]*?>(.*?)</a>',
            chunk, re.DOTALL | re.IGNORECASE
        )
        if not title_match:
            title_match = re.search(
                r'<h3[^>]*?class="[^"]*?base-search-card__title[^"]*?"[^>]*?>(.*?)</h3>',
                chunk, re.DOTALL | re.IGNORECASE
            )

        if not title_match:
            continue

        if title_match.lastindex and title_match.lastindex >= 2:
            href = title_match.group(1)
            title = _clean_html(title_match.group(2))
        else:
            href = ""
            title = _clean_html(title_match.group(1))

        if not title or not _is_relevant(title, keyword):
            continue

        detail_url = urljoin("https://www.linkedin.com", html.unescape(href)) if href else ""

        # Company
        company_match = re.search(
            r'<h4[^>]*?class="[^"]*?base-search-card__subtitle[^"]*?"[^>]*?>(.*?)</h4>',
            chunk, re.DOTALL | re.IGNORECASE
        )
        if not company_match:
            company_match = re.search(
                r'<a[^>]*?class="[^"]*?(?:company|hidden-nested-link)[^"]*?"[^>]*?>(.*?)</a>',
                chunk, re.DOTALL | re.IGNORECASE
            )
        company = _clean_html(company_match.group(1)) if company_match else ""

        # Location
        location_match = re.search(
            r'<span[^>]*?class="[^"]*?job-search-card__location[^"]*?"[^>]*?>(.*?)</span>',
            chunk, re.DOTALL | re.IGNORECASE
        )
        location = _clean_html(location_match.group(1)) if location_match else ""

        # Date
        date_match = re.search(
            r'<time[^>]*?datetime="([^"]*?)"', chunk, re.IGNORECASE
        )
        date_posted = date_match.group(1) if date_match else ""

        listings.append({
            "title": title,
            "company": company,
            "location": location,
            "date_posted": date_posted,
            "job_type": "",
            "detail_url": detail_url,
        })

    logger.info(f"Parsed {len(listings)} job cards from LinkedIn search page")
    return listings


async def scrape_linkedin_jobs(
    keyword: str,
    location: str = "",
    job_type: str = "",
    experience_level: str = "",
    proxies: Optional[list[str]] = None,
    max_pages: int = 10,
) -> list[dict]:
    """
    Scrape job/internship listings from LinkedIn using search filters.

    Args:
        keyword: Search keyword (e.g. "Machine Learning Engineer")
        location: Location filter
        job_type: Job type filter (e.g. "Full-time", "Internship")
        experience_level: Experience level filter
        proxies: Optional list of proxy URLs for rotation
        max_pages: Maximum pages to scrape

    Returns:
        List of standardised job records.

    Error Handling:
        - API connection failures: retry with exponential backoff
        - Rate limiting: implements queue and schedule retries
        - Incomplete job data: logged and flagged — never crashes the pipeline
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    proxy_rotator = ProxyRotator(proxies)
    all_jobs = []
    seen_urls: set[str] = set()

    proxy = proxy_rotator.next()
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        proxy=proxy,
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        viewport_width=1920,
        viewport_height=1080,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=45000,
        wait_until="domcontentloaded",
        session_id="linkedin_session",
        magic=True,
        simulate_user=True,
        override_navigator=True,
        delay_before_return_html=5.0,
    )

    logger.info(f"Starting LinkedIn scrape: keyword='{keyword}', location='{location}', "
                f"job_type='{job_type}'")

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            page, start = 0, 0
            while page < max_pages:
                url = _build_linkedin_search_url(keyword, location, job_type, start,
                                                 experience_level=experience_level)
                logger.info(f"LinkedIn search page {page + 1}: {url}")

                result = await _fetch_with_retry(crawler, url, crawler_config)
                if not result or not result.html:
                    logger.warning(f"Failed to fetch LinkedIn page {page + 1}")
                    break

                listings = _parse_linkedin_search_results(result.html, keyword)
                if not listings:
                    logger.info("No more LinkedIn listings found.")
                    break

                new = [l for l in listings if l.get("detail_url") and l["detail_url"] not in seen_urls]
                for listing in new:
                    seen_urls.add(listing["detail_url"])
                    detail_html = ""
                    try:
                        dres = await _fetch_with_retry(crawler, listing["detail_url"], crawler_config)
                        detail_html = dres.html if dres else ""
                    except Exception as exc:
                        logger.warning(f"LinkedIn detail fetch failed {listing['detail_url']}: {exc}")
                    listing["description"] = _parse_linkedin_description(detail_html) if detail_html else ""
                    listing["apply_link"] = listing["detail_url"]
                    listing["source_url"] = listing["detail_url"]
                    await _rate_limit()
                    try:
                        all_jobs.append(_standardise_job_record(listing, "linkedin"))
                    except Exception as exc:
                        logger.error(f"Error standardising {listing.get('detail_url')}: {exc}")

                page += 1
                start += 25  # LinkedIn uses 25 per page
                await _rate_limit()

    except Exception as exc:
        logger.error(f"LinkedIn scrape failed: {exc}")
        if not all_jobs:
            raise

    logger.info(f"LinkedIn scrape complete: {len(all_jobs)} total jobs collected")
    return all_jobs
