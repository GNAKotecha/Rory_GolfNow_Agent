"""Advanced Async Event Loop Management for MCP Registry.

Provides robust event loop initialization, management, and error handling.
"""
import asyncio
import sys
import contextvars
import logging
import functools
from typing import Optional, Any, Callable, Coroutine, TypeVar, Union

logger = logging.getLogger(__name__)

# Type variable for return type preservation
T = TypeVar('T')

class MCPEventLoopManager:
    """Centralized Event Loop Management for MCP Operations."""

    _instance = None
    _loop: Optional[asyncio.AbstractEventLoop] = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_event_loop(cls) -> asyncio.AbstractEventLoop:
        """
        Retrieve or create a new event loop with robust error handling.

        Strategies:
        - Prefer existing running loop
        - Create platform-specific loop
        - Ensure thread-safety
        """
        try:
            # Prefer getting the current event loop first
            if sys.platform != 'win32':
                try:
                    return asyncio.get_running_loop()
                except RuntimeError:
                    pass

            # Create a new event loop if no running loop exists
            if cls._loop is None or cls._loop.is_closed():
                try:
                    # Use ProactorEventLoop for Windows, SelectorEventLoop for others
                    cls._loop = asyncio.ProactorEventLoop() if sys.platform == 'win32' else asyncio.SelectorEventLoop()
                    asyncio.set_event_loop(cls._loop)
                    logger.info("Event loop created successfully")
                except Exception as e:
                    logger.error(f"Failed to create event loop: {e}")
                    raise

            return cls._loop

        except Exception as e:
            logger.critical(f"Catastrophic event loop failure: {e}")
            raise RuntimeError("Unable to initialize event loop") from e

    @classmethod
    def run_in_loop(cls,
                    coro: Coroutine[Any, Any, Any],
                    timeout: Optional[float] = 30.0
    ) -> Any:
        """
        Run a coroutine in the managed event loop with context preservation.

        Ensures:
        - Proper event loop is used
        - Context variables are correctly propagated
        - Graceful error handling
        - Optional timeout

        Args:
            coro: Coroutine to run
            timeout: Maximum execution time in seconds

        Returns:
            Result of the coroutine
        """
        loop = cls.get_event_loop()
        context = contextvars.copy_context()

        def run_with_context():
            try:
                return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            except asyncio.TimeoutError:
                logger.warning(f"Coroutine {coro} timed out after {timeout} seconds")
                raise
            except Exception as e:
                logger.error(f"Event loop execution failed: {e}")
                raise

        return context.run(run_with_context)

    @classmethod
    def close_event_loop(cls):
        """Safely close the event loop."""
        if cls._loop and not cls._loop.is_closed():
            try:
                cls._loop.close()
                cls._loop = None
                logger.info("Event loop closed successfully")
            except Exception as e:
                logger.warning(f"Error closing event loop: {e}")

# Global singleton for event loop management
mcp_event_loop_manager = MCPEventLoopManager()

def mcp_async_method(func):
    """
    Decorator to standardize async method error handling and logging.

    Provides:
    - Consistent error logging
    - Context preservation
    - Timeout handling
    - Detailed method tracing
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        method_name = func.__name__
        logger.debug(f"Starting async method: {method_name}")

        try:
            # Use the event loop manager for execution
            result = await func(*args, **kwargs)
            logger.debug(f"Async method {method_name} completed successfully")
            return result
        except asyncio.CancelledError:
            logger.warning(f"Async method {method_name} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Async method {method_name} failed: {e}", exc_info=True)
            raise

    return wrapper

def safe_async_call(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    timeout: Optional[float] = 30.0,
    **kwargs: Any
) -> Optional[T]:
    """
    Safely wrap an async call with comprehensive error handling.

    Args:
        func: Coroutine function to call
        timeout: Maximum execution time in seconds
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        Result of the async function or None on failure
    """
    try:
        loop = mcp_event_loop_manager.get_event_loop()

        async def _wrapped_call():
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)

        return loop.run_until_complete(_wrapped_call())

    except asyncio.TimeoutError:
        logger.warning(f"Async call to {func.__name__} timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Async call failed: {func.__name__}: {e}", exc_info=True)

    return None

# Expose the event loop manager for direct usage
__all__ = [
    'MCPEventLoopManager',
    'mcp_event_loop_manager',
    'mcp_async_method',
    'safe_async_call'
]