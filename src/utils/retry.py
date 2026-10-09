"""Retry helper with exponential backoff and error classification."""

import time
from typing import Callable, Any, Type, Tuple
from src.utils.logging import log

def is_retryable_error(exc: Exception) -> bool:
    """Classify if an exception is transient / retryable."""
    msg = str(exc).lower()
    retryable_terms = [
        "429", "too many requests", "rate limit", "quota",
        "500", "502", "503", "504", "service unavailable",
        "timeout", "timed out", "connection reset", "connection refused",
        "temporary failure", "try again"
    ]
    return any(term in msg for term in retryable_terms)

def retry_with_backoff(
    fn: Callable[..., Any],
    stage: str,
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    allowed_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Any:
    """Execute a function with exponential backoff on retryable errors."""
    delay = initial_delay
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except allowed_exceptions as exc:
            last_exception = exc
            if not is_retryable_error(exc):
                log("RETRY", f"Non-retryable error encountered: {exc}", level="WARN")
                raise exc
            
            if attempt < max_retries:
                log("RETRY", f"Attempt {attempt}/{max_retries} failed ({exc}). Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= backoff_factor
            else:
                log("RETRY", f"Attempt {attempt}/{max_retries} failed. Retries exhausted.", level="ERROR")
                raise last_exception

    raise last_exception or RuntimeError(f"Operation failed after {max_retries} attempts.")
