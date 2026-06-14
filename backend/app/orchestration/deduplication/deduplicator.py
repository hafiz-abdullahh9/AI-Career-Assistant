import hashlib
import re
import uuid
from datetime import datetime, timedelta, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import Application
from app.orchestration.schemas.governance_schemas import DeduplicationResult


def normalize_text(text: str | None) -> str:
    """
    Standardizes company names or role titles by lowercasing,
    stripping punctuation, and collapsing multiple spaces.
    """
    if not text:
        return ""
    text_lower = text.lower().strip()
    # Remove corporate suffixes
    text_cleaned = re.sub(
        r"\b(inc|co|corp|ltd|llc|incorporated|corporation|limited|company)\b",
        "",
        text_lower
    )
    # Remove extra whitespace and punctuation
    text_cleaned = re.sub(r"[^\w\s]", "", text_cleaned)
    text_cleaned = re.sub(r"\s+", " ", text_cleaned).strip()
    return text_cleaned


def normalize_url(url: str | None) -> str:
    """
    Normalizes a job URL by lowercasing, stripping query params,
    trailing slashes, and 'www.' prefixes.
    """
    if not url:
        return ""
    url_lower = url.lower().strip()
    # Strip query parameters
    if "?" in url_lower:
        url_lower = url_lower.split("?")[0]
    # Strip trailing slash
    url_lower = url_lower.rstrip("/")
    # Strip www.
    url_lower = url_lower.replace("://www.", "://")
    return url_lower


class Deduplicator:
    """
    Implements a two-layer deduplication system:
    - Layer 1: Short window (24h) to prevent accidental rapid re-apply spam.
    - Layer 2: Long window (30d) to prevent applying to the same role/company.
    Normalized dedup keys include: normalized company, normalized role, and normalized URL.
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    def calculate_dedup_hash(
        self,
        company: str,
        role: str,
        url: str | None
    ) -> str:
        """
        Calculate a unique SHA-256 hash for the normalized application fields.
        """
        norm_company = normalize_text(company)
        norm_role = normalize_text(role)
        norm_url = normalize_url(url)

        combined = f"{norm_company}|{norm_role}|{norm_url}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    async def check_duplicate(
        self,
        db: AsyncSession,
        user_id: str,
        company: str,
        role: str,
        url: str | None
    ) -> DeduplicationResult:
        """
        Check both Redis cache layers and DB for duplicate applications.
        """
        hash_val = self.calculate_dedup_hash(company, role, url)
        
        # ── Layer 1: Redis Short Window (24 hours) ──
        short_key = f"dedup:short:{user_id}:{hash_val}"
        existing_short = await self._redis.get(short_key)
        if existing_short:
            return DeduplicationResult(
                is_duplicate=True,
                reason="Duplicate application attempt blocked by short-term (24h) spam prevention.",
                existing_application_id=existing_short.decode("utf-8") if isinstance(existing_short, bytes) else str(existing_short)
            )

        # ── Layer 2: Redis Long Window (30 days) ──
        long_key = f"dedup:long:{user_id}:{hash_val}"
        existing_long = await self._redis.get(long_key)
        if existing_long:
            return DeduplicationResult(
                is_duplicate=True,
                reason="Duplicate application attempt blocked by long-term (30d) duplicate policy.",
                existing_application_id=existing_long.decode("utf-8") if isinstance(existing_long, bytes) else str(existing_long)
            )

        # ── DB Fallback (30-day window search) ──
        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
        stmt = select(Application).where(
            Application.user_id == uuid.UUID(user_id),
            Application.queued_at >= thirty_days_ago,
            Application.deleted_at.is_(None)
        )
        res = await db.execute(stmt)
        past_apps = res.scalars().all()

        norm_company = normalize_text(company)
        norm_role = normalize_text(role)
        norm_url = normalize_url(url)

        for app in past_apps:
            app_company = normalize_text(app.company_name)
            app_role = normalize_text(app.role_title)
            app_url = normalize_url(app.application_url)

            # Match criteria: either same normalized URL OR (same normalized company and role)
            if (norm_url and norm_url == app_url) or (norm_company == app_company and norm_role == app_role):
                # Repopulate Redis cache for future speedup
                await self.record_applied(user_id, company, role, url, str(app.application_id))
                return DeduplicationResult(
                    is_duplicate=True,
                    reason=f"Duplicate application to '{app.company_name}' for '{app.role_title}' found in DB history (within 30 days).",
                    existing_application_id=str(app.application_id)
                )

        return DeduplicationResult(is_duplicate=False)

    async def record_applied(
        self,
        user_id: str,
        company: str,
        role: str,
        url: str | None,
        application_id: str
    ) -> None:
        """
        Record a successful application in Redis for both short (24h) and long (30d) cache layers.
        """
        hash_val = self.calculate_dedup_hash(company, role, url)
        short_key = f"dedup:short:{user_id}:{hash_val}"
        long_key = f"dedup:long:{user_id}:{hash_val}"

        pipe = self._redis.pipeline()
        pipe.set(short_key, application_id, ex=24 * 3600)  # 24 hours
        pipe.set(long_key, application_id, ex=30 * 24 * 3600)  # 30 days
        await pipe.execute()
