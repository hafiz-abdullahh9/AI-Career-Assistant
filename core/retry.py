import asyncio
import logging
from functools import wraps
from typing import Callable, Any, Tuple, Type

logger = logging.getLogger("retry_policy")

def retry_on_exception(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    exceptions_to_catch: Tuple[Type[BaseException], ...] = (Exception,)
):
    """
    Exponential backoff retry decorator for asynchronous calls.
    Provides standard error recovery for remote scrapers, API endpoints, and database connections.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions_to_catch as e:
                    if attempt == max_retries:
                        logger.error(
                            f"Final attempt {attempt} failed for function '{func.__name__}' "
                            f"with exception: {type(e).__name__}: {str(e)}. Halting execution."
                        )
                        raise e
                    
                    logger.warning(
                        f"Attempt {attempt} failed for function '{func.__name__}' "
                        f"due to {type(e).__name__}: {str(e)}. "
                        f"Retrying in {delay:.1f} seconds (Backoff factor: {backoff_factor})."
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
            
        return async_wrapper
    return decorator
