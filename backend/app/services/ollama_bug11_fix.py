"""
Bug #11 Fix: LLM Timeout and Retry Logic

This file contains the fixed version of ollama.py with:
1. Increased timeout from 60s to 180s
2. Retry logic with exponential backoff (3 attempts)

Apply this fix by copying changes to ollama.py
"""

# CHANGE 1: Update default timeout in OllamaHTTPClientPool.__init__ (line 100)
# OLD:
#   self._default_timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
# NEW:
#   self._default_timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

# CHANGE 2: Update all hardcoded timeout values from 60.0 to 180.0
# Lines to change: 393, 404, 537, 570
# OLD: timeout=60.0,
# NEW: timeout=180.0,

# CHANGE 3: Add retry wrapper function (add after imports, before OllamaHTTPClientPool)
"""
import functools
from typing import Callable, TypeVar, ParamSpec

P = ParamSpec('P')
T = TypeVar('T')

def retry_on_timeout(max_retries: int = 3):
    '''
    Decorator to retry async functions on timeout/connection errors.

    Bug #11 fix: Add exponential backoff retry logic for transient failures.
    '''
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        backoff_seconds = 2 ** attempt
                        logger.warning(
                            f"Request failed (attempt {attempt + 1}/{max_retries}), retrying in {backoff_seconds}s",
                            extra={"error": str(e), "function": func.__name__}
                        )
                        await asyncio.sleep(backoff_seconds)
                        continue
                    logger.error(
                        f"Request failed after {max_retries} attempts",
                        extra={"error": str(e), "function": func.__name__}
                    )
                    raise
                except Exception:
                    # Non-retryable error - raise immediately
                    raise
            # Should not reach here
            if last_exception:
                raise last_exception
            raise Exception("Unexpected retry loop exit")
        return wrapper
    return decorator
"""

# CHANGE 4: Apply decorator to generate_chat_completion (line ~340)
# OLD:
#   async def generate_chat_completion(
# NEW:
#   @retry_on_timeout(max_retries=3)
#   async def generate_chat_completion(

# CHANGE 5: Apply decorator to generate_chat_completion_with_tools (line ~474)
# OLD:
#   async def generate_chat_completion_with_tools(
# NEW:
#   @retry_on_timeout(max_retries=3)
#   async def generate_chat_completion_with_tools(
