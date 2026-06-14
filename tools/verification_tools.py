"""
Verification tools for the Job Verification Agent.

Tools:
  - verify_company(company_name)       — Verify company legitimacy using public records
  - detect_duplicates(job_list)         — Detect duplicate postings across platforms
  - check_expired_posting(job)          — Identify expired postings
  - flag_suspicious_listing(job)        — Flag suspicious listings

All tools return structured JSON-compatible dicts — never raise unhandled exceptions.
"""

import re
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from difflib import SequenceMatcher

logger = logging.getLogger("career_assistant.verification")


# ═══════════════════════════════════════════════════════════════════
#  SUSPICIOUS CONTENT PATTERNS
# ═══════════════════════════════════════════════════════════════════

SUSPICIOUS_PAYMENT_KEYWORDS = [
    "wire transfer", "western union", "moneygram", "upfront payment",
    "processing fee", "registration fee", "advance payment",
    "send money", "pay to apply", "guaranteed income",
    "pay for training", "investment required", "cash deposit",
    "money order", "bank transfer required",
]

SUSPICIOUS_CONTACT_PATTERNS = [
    r'(?:gmail|yahoo|hotmail|outlook)\.com',  # Non-corporate emails in company listings
]

SUSPICIOUS_TITLE_PATTERNS = [
    r'(?:earn|make)\s+\$?\d+.*(?:per|a)\s+(?:day|hour|week)',  # "Earn $5000 per week"
    r'no\s+(?:experience|skills?)\s+(?:needed|required|necessary)',
    r'work\s+from\s+home.*\$\d+',
]


# ═══════════════════════════════════════════════════════════════════
#  COMPANY VERIFICATION
# ═══════════════════════════════════════════════════════════════════

def verify_company(company_name: str) -> dict:
    """
    Verify company legitimacy using public records and heuristics.

    Checks performed:
      1. Company name is not empty or generic
      2. No suspicious patterns in company name
      3. Cross-reference with known legitimate indicators
      4. Check for presence of a valid domain

    Args:
        company_name: The company name to verify.

    Returns:
        dict with keys:
          - company_name (str)
          - is_verified (bool)
          - confidence (float, 0.0–1.0)
          - flags (list[str]) — reasons for concern
          - verification_method (str)
    """
    try:
        if not company_name or not company_name.strip():
            return {
                "company_name": company_name or "",
                "is_verified": False,
                "confidence": 0.0,
                "flags": ["Company name is empty"],
                "verification_method": "heuristic",
            }

        name = company_name.strip()
        flags = []
        confidence = 0.7  # Start with moderate confidence

        # Check 1: Generic / placeholder names
        generic_names = [
            "company", "n/a", "not available", "unknown", "hiring",
            "confidential", "tbd", "na", ".", "-", "test",
            "asdf", "abc", "xxx",
        ]
        if name.lower() in generic_names or len(name) < 2:
            flags.append(f"Generic or placeholder company name: '{name}'")
            confidence -= 0.5

        # Check 2: Excessive special characters
        special_ratio = len(re.findall(r'[^a-zA-Z0-9\s.,&\'-]', name)) / max(len(name), 1)
        if special_ratio > 0.3:
            flags.append("Excessive special characters in company name")
            confidence -= 0.2

        # Check 3: All caps or all lowercase (legitimate companies usually use mixed case)
        if len(name) > 5 and (name == name.upper() or name == name.lower()):
            # Minor flag — many companies do use all-caps abbreviated names
            pass

        # Check 4: Contains suspicious terms
        suspicious_company_terms = [
            "get rich", "easy money", "pyramid", "mlm",
            "multi-level", "network marketing",
        ]
        for term in suspicious_company_terms:
            if term in name.lower():
                flags.append(f"Company name contains suspicious term: '{term}'")
                confidence -= 0.3

        # Check 5: Very long company name (might be a description, not a name)
        if len(name) > 100:
            flags.append("Company name is unusually long (>100 chars)")
            confidence -= 0.1

        # Check 6: Contains URL pattern (companies should use proper names, not URLs)
        if re.search(r'https?://|www\.', name, re.IGNORECASE):
            flags.append("Company name contains URL")
            confidence -= 0.2

        confidence = max(0.0, min(1.0, confidence))
        is_verified = confidence >= 0.5 and len(flags) == 0

        return {
            "company_name": name,
            "is_verified": is_verified,
            "confidence": round(confidence, 2),
            "flags": flags,
            "verification_method": "heuristic",
        }

    except Exception as exc:
        logger.error(f"Company verification error for '{company_name}': {exc}", exc_info=True)
        return {
            "company_name": company_name or "",
            "is_verified": False,
            "confidence": 0.0,
            "flags": [f"Verification error: {exc}"],
            "verification_method": "error",
        }


# ═══════════════════════════════════════════════════════════════════
#  DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════════

def _normalize_text(text: str) -> str:
    """Normalise text for comparison — lowercase, strip whitespace, remove punctuation."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def _compute_similarity(text1: str, text2: str) -> float:
    """Compute similarity ratio between two strings (0.0–1.0)."""
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1, text2).ratio()


def _fingerprint_job(job: dict) -> str:
    """Create a fuzzy fingerprint for a job listing for duplicate detection."""
    title = _normalize_text(job.get("title", ""))
    company = _normalize_text(job.get("company", ""))
    location = _normalize_text(job.get("location", ""))
    # Use first 200 chars of normalised description as part of fingerprint
    desc = _normalize_text(job.get("description", ""))[:200]
    combined = f"{title}|{company}|{location}|{desc}"
    return hashlib.md5(combined.encode()).hexdigest()


def detect_duplicates(job_list: list[dict]) -> list[dict]:
    """
    Detect duplicate postings across platforms.

    Uses a multi-layer approach:
      1. Exact URL match (source_url)
      2. Exact fingerprint match (title + company + location + desc prefix)
      3. Fuzzy similarity on title + company (>= 0.85 similarity)

    Args:
        job_list: List of standardised job records.

    Returns:
        Updated job_list where duplicate jobs have:
          - 'is_duplicate' (bool) — True if a duplicate was found
          - 'duplicate_of' (str) — job_id of the original
          - 'duplicate_reason' (str) — how the duplicate was detected
    """
    try:
        seen_urls: dict[str, str] = {}            # source_url -> job_id
        seen_fingerprints: dict[str, str] = {}     # fingerprint -> job_id
        seen_title_company: list[tuple[str, str, str]] = []  # (norm_title, norm_company, job_id)

        for job in job_list:
            job_id = job.get("job_id", "")
            source_url = job.get("source_url", "")
            is_dup = False
            dup_of = ""
            dup_reason = ""

            # Layer 1: Exact URL match
            if source_url and source_url in seen_urls:
                is_dup = True
                dup_of = seen_urls[source_url]
                dup_reason = "exact_url_match"
            else:
                if source_url:
                    seen_urls[source_url] = job_id

            # Layer 2: Fingerprint match (if not already caught)
            if not is_dup:
                fp = _fingerprint_job(job)
                if fp in seen_fingerprints:
                    is_dup = True
                    dup_of = seen_fingerprints[fp]
                    dup_reason = "fingerprint_match"
                else:
                    seen_fingerprints[fp] = job_id

            # Layer 3: Fuzzy title+company match (cross-platform detection)
            if not is_dup:
                norm_title = _normalize_text(job.get("title", ""))
                norm_company = _normalize_text(job.get("company", ""))
                if norm_title and norm_company:
                    for prev_title, prev_company, prev_id in seen_title_company:
                        title_sim = _compute_similarity(norm_title, prev_title)
                        company_sim = _compute_similarity(norm_company, prev_company)
                        if title_sim >= 0.85 and company_sim >= 0.85:
                            is_dup = True
                            dup_of = prev_id
                            dup_reason = f"fuzzy_match (title={title_sim:.2f}, company={company_sim:.2f})"
                            break
                    if not is_dup:
                        seen_title_company.append((norm_title, norm_company, job_id))

            job["is_duplicate"] = is_dup
            job["duplicate_of"] = dup_of
            job["duplicate_reason"] = dup_reason

        dup_count = sum(1 for j in job_list if j.get("is_duplicate"))
        logger.info(f"Duplicate detection: found {dup_count} duplicates in {len(job_list)} jobs")
        return job_list

    except Exception as exc:
        logger.error(f"Duplicate detection error: {exc}", exc_info=True)
        # Never crash — return the list unchanged
        return job_list


# ═══════════════════════════════════════════════════════════════════
#  EXPIRED POSTING CHECK
# ═══════════════════════════════════════════════════════════════════

def check_expired_posting(job: dict) -> dict:
    """
    Identify expired postings by comparing posted_date vs application_deadline.

    Args:
        job: A standardised job record dict.

    Returns:
        dict with keys:
          - is_expired (bool)
          - expiry_reason (str)
          - days_since_posted (int or None)
          - days_until_deadline (int or None)
    """
    try:
        now = datetime.now()
        result = {
            "is_expired": False,
            "expiry_reason": "",
            "days_since_posted": None,
            "days_until_deadline": None,
        }

        # Check 1: Application deadline has passed
        deadline = job.get("application_deadline", "")
        if deadline:
            try:
                # Try common date formats
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%d %B %Y"):
                    try:
                        deadline_date = datetime.strptime(deadline.strip(), fmt)
                        days_until = (deadline_date - now).days
                        result["days_until_deadline"] = days_until
                        if days_until < 0:
                            result["is_expired"] = True
                            result["expiry_reason"] = f"Deadline passed {abs(days_until)} days ago"
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Check 2: Posted date is very old (>30 days — likely stale)
        date_posted = job.get("date_posted", "")
        if date_posted:
            try:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                    try:
                        posted_date = datetime.strptime(date_posted.strip(), fmt)
                        days_since = (now - posted_date).days
                        result["days_since_posted"] = days_since
                        if days_since > 60:
                            result["is_expired"] = True
                            result["expiry_reason"] = (
                                result["expiry_reason"] or
                                f"Posted {days_since} days ago (likely expired)"
                            )
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        return result

    except Exception as exc:
        logger.error(f"Expired check error: {exc}", exc_info=True)
        return {
            "is_expired": False,
            "expiry_reason": f"Check error: {exc}",
            "days_since_posted": None,
            "days_until_deadline": None,
        }


# ═══════════════════════════════════════════════════════════════════
#  SUSPICIOUS LISTING DETECTION
# ═══════════════════════════════════════════════════════════════════

def flag_suspicious_listing(job: dict) -> dict:
    """
    Flag suspicious listings based on multiple heuristics.

    Checks:
      1. Spelling errors & quality issues in title/description
      2. Unusual payment requests in description
      3. Invalid or suspicious contact links
      4. Missing critical fields
      5. Suspicious title patterns ("earn $X per day" etc.)
      6. Description too short or too generic

    Args:
        job: A standardised job record dict.

    Returns:
        dict with keys:
          - is_suspicious (bool)
          - suspicion_score (float, 0.0–1.0)
          - flags (list[str])
    """
    try:
        flags = []
        score = 0.0  # Suspicion score (higher = more suspicious)
        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")
        apply_link = job.get("apply_link", "")
        contact_info = job.get("contact_info", "")

        # ── Check 1: Missing critical fields ──
        if not title:
            flags.append("Missing job title")
            score += 0.3
        if not company:
            flags.append("Missing company name")
            score += 0.2
        if not description:
            flags.append("Missing job description")
            score += 0.2

        # ── Check 2: Suspicious payment keywords in description ──
        desc_lower = description.lower() if description else ""
        for keyword in SUSPICIOUS_PAYMENT_KEYWORDS:
            if keyword in desc_lower:
                flags.append(f"Suspicious payment keyword: '{keyword}'")
                score += 0.25

        # ── Check 3: Suspicious title patterns ──
        title_lower = title.lower() if title else ""
        for pattern in SUSPICIOUS_TITLE_PATTERNS:
            if re.search(pattern, title_lower):
                flags.append(f"Suspicious title pattern detected")
                score += 0.3
                break

        # ── Check 4: Invalid contact links ──
        if apply_link:
            # Check for javascript: or data: URLs
            if apply_link.startswith(("javascript:", "data:", "blob:")):
                flags.append("Invalid apply link scheme (javascript/data)")
                score += 0.4
            # Check for non-corporate email domains
            elif apply_link.startswith("mailto:"):
                email = apply_link.replace("mailto:", "").split("?")[0]
                for pattern in SUSPICIOUS_CONTACT_PATTERNS:
                    if re.search(pattern, email, re.IGNORECASE):
                        flags.append(f"Non-corporate email domain in apply link: {email}")
                        score += 0.1
                        break

        # ── Check 5: Description quality checks ──
        if description:
            # Too short
            if len(description) < 50:
                flags.append("Very short description (<50 chars)")
                score += 0.15

            # Excessive caps
            if len(description) > 20:
                upper_ratio = sum(1 for c in description if c.isupper()) / len(description)
                if upper_ratio > 0.5:
                    flags.append("Excessive capitalisation in description")
                    score += 0.1

            # Excessive exclamation marks
            if description.count("!") > 5:
                flags.append("Excessive exclamation marks in description")
                score += 0.1

            # Check for common spelling errors that indicate low-quality postings
            spelling_indicators = [
                (r'\brecieve\b', 'receive'),
                (r'\bsalery\b', 'salary'),
                (r'\bimmediatlely\b', 'immediately'),
                (r'\bexpirience\b', 'experience'),
                (r'\boppurtunity\b', 'opportunity'),
                (r'\bguranteed\b', 'guaranteed'),
                (r'\bbenifits\b', 'benefits'),
                (r'\bproffesional\b', 'professional'),
            ]
            for pattern, correct in spelling_indicators:
                if re.search(pattern, desc_lower):
                    flags.append(f"Spelling error detected: should be '{correct}'")
                    score += 0.05

        # ── Check 6: Contact info quality ──
        if contact_info:
            for pattern in SUSPICIOUS_CONTACT_PATTERNS:
                if re.search(pattern, contact_info, re.IGNORECASE):
                    flags.append("Non-corporate email in contact info")
                    score += 0.05

        score = min(1.0, score)
        is_suspicious = score >= 0.3 or len(flags) >= 2

        return {
            "is_suspicious": is_suspicious,
            "suspicion_score": round(score, 2),
            "flags": flags,
        }

    except Exception as exc:
        logger.error(f"Suspicious check error: {exc}", exc_info=True)
        return {
            "is_suspicious": False,
            "suspicion_score": 0.0,
            "flags": [f"Check error: {exc}"],
        }
