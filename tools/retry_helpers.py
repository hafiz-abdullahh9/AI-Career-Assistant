"""
Retry helpers with exponential backoff.
Includes the `@retry_with_backoff` decorator/wrapper.
"""

import asyncio
import logging
import random
import time
from typing import Callable, Any, TypeVar, Union, cast
from config import settings
import openai

logger = logging.getLogger("career_assistant.retry")

F = TypeVar('F', bound=Callable[..., Any])

def is_transient_error(exc: Exception) -> bool:
    """Determine if the exception is a transient/retryable error."""
    # Check OpenAI specific errors
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIConnectionError):
        return True
    if isinstance(exc, openai.Timeout):
        return True
    if isinstance(exc, openai.InternalServerError):
        return True
    
    # Check status code if available (e.g. HTTP status codes)
    if hasattr(exc, "status_code"):
        status_code = getattr(exc, "status_code")
        if status_code in (429, 500, 502, 503, 504):
            return True
            
    # Check general transient error messages / classes
    exc_str = str(exc).lower()
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    
    transient_indicators = [
        "timeout", "timed out", "connection reset", "connection refused", 
        "rate limit", "too many requests", "429", "500", "502", "503", "504"
    ]
    if any(indicator in exc_str for indicator in transient_indicators):
        return True
        
    return False

def retry_with_backoff(
    retries: int = None,
    base_delay: float = None,
    max_delay: float = None,
    backoff_factor: float = None
):
    """
    Decorator/wrapper that retries a synchronous or asynchronous function on transient failures.
    Uses exponential backoff.
    """
    if retries is None:
        retries = getattr(settings, "MAX_RETRIES", 3)
    if base_delay is None:
        base_delay = getattr(settings, "RETRY_BASE_DELAY", 1.0)
    if max_delay is None:
        max_delay = getattr(settings, "RETRY_MAX_DELAY", 60.0)
    if backoff_factor is None:
        backoff_factor = getattr(settings, "RETRY_BACKOFF_FACTOR", 2.0)

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                current_delay = base_delay
                for attempt in range(retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as exc:
                        if attempt == retries or not is_transient_error(exc):
                            logger.error(f"Async call to {func.__name__} failed permanently on attempt {attempt + 1}: {exc}")
                            raise exc
                        
                        # Apply jitter
                        jitter = random.uniform(0.8, 1.2)
                        sleep_time = current_delay * jitter
                        logger.warning(
                            f"Async call to {func.__name__} failed (attempt {attempt + 1}/{retries + 1}): {exc}. "
                            f"Retrying in {sleep_time:.1f}s..."
                        )
                        await asyncio.sleep(sleep_time)
                        current_delay = min(max_delay, current_delay * backoff_factor)
            return cast(F, async_wrapper)
        else:
            def sync_wrapper(*args, **kwargs):
                current_delay = base_delay
                for attempt in range(retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as exc:
                        if attempt == retries or not is_transient_error(exc):
                            logger.error(f"Sync call to {func.__name__} failed permanently on attempt {attempt + 1}: {exc}")
                            raise exc
                        
                        # Apply jitter
                        jitter = random.uniform(0.8, 1.2)
                        sleep_time = current_delay * jitter
                        logger.warning(
                            f"Sync call to {func.__name__} failed (attempt {attempt + 1}/{retries + 1}): {exc}. "
                            f"Retrying in {sleep_time:.1f}s..."
                        )
                        time.sleep(sleep_time)
                        current_delay = min(max_delay, current_delay * backoff_factor)
            return cast(F, sync_wrapper)
    return decorator
