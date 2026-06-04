"""
Centralized Async Tool Execution Framework

Provides robust, safe async tool execution with:
- Context preservation
- Comprehensive error handling
- Timeout management
- Workspace isolation
- Logging and tracing
"""

import asyncio
import logging
import os
import shutil
import tempfile
import functools
from typing import Any, Callable, Optional, TypeVar, Union, List, Dict
from contextvars import ContextVar
from pathlib import Path

logger = logging.getLogger(__name__)

# Context variable for tracking tool execution
tool_context: ContextVar[Dict[str, Any]] = ContextVar('tool_context', default={})

T = TypeVar('T')

class WorkspaceManager:
    """
    Manages isolated workspaces for async tool execution.

    Provides:
    - Temporary directory creation
    - Safe workspace isolation
    - Cleanup mechanisms
    """

    @staticmethod
    def create_workspace(prefix: str = 'mcp_tool_') -> Path:
        """
        Create an isolated temporary workspace.

        Args:
            prefix: Prefix for temporary directory name

        Returns:
            Path to the created workspace
        """
        workspace_path = Path(tempfile.mkdtemp(prefix=prefix))
        logger.debug(f"Created workspace: {workspace_path}")
        return workspace_path

    @staticmethod
    def cleanup_workspace(workspace_path: Path):
        """
        Safely remove a workspace directory.

        Args:
            workspace_path: Path to the workspace to remove
        """
        try:
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.debug(f"Cleaned up workspace: {workspace_path}")
        except Exception as e:
            logger.warning(f"Error cleaning workspace {workspace_path}: {e}")

class AsyncToolExecutor:
    """
    Centralized async tool execution framework.

    Provides:
    - Safe async method execution
    - Comprehensive error handling
    - Context preservation
    - Workspace isolation
    - Timeout management
    """

    @staticmethod
    async def execute(
        func: Callable[..., T],
        *args,
        timeout: Optional[float] = 30.0,
        workspace_prefix: str = 'mcp_tool_',
        retry_count: int = 1,
        **kwargs
    ) -> T:
        """
        Execute an async tool with robust management.

        Args:
            func: Async function to execute
            timeout: Maximum execution time
            workspace_prefix: Prefix for temporary workspace
            retry_count: Number of retry attempts on failure
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
            Exception: For unrecoverable execution errors
        """
        last_error = None

        for attempt in range(retry_count + 1):
            # Create isolated workspace
            workspace = WorkspaceManager.create_workspace(workspace_prefix)

            try:
                # Add workspace to function arguments
                kwargs['workspace'] = workspace

                # Capture existing context
                previous_context = tool_context.get().copy()

                # Set new context with workspace information
                context_token = tool_context.set({
                    'workspace': str(workspace),
                    'start_time': asyncio.get_event_loop().time(),
                    'function': func.__name__,
                    'attempt': attempt + 1
                })

                try:
                    # Execute with timeout
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout
                    )

                    logger.info(f"Tool {func.__name__} executed successfully (attempt {attempt + 1})")
                    return result

                except asyncio.TimeoutError:
                    last_error = asyncio.TimeoutError(f"Tool {func.__name__} timed out after {timeout} seconds (attempt {attempt + 1})")
                    logger.warning(str(last_error))

                except Exception as e:
                    last_error = e
                    logger.error(f"Tool execution error: {func.__name__} - {e}", exc_info=True)

                finally:
                    # Restore previous context
                    tool_context.reset(context_token)
                    tool_context.set(previous_context)

            finally:
                # Always clean up workspace, even if execution fails
                WorkspaceManager.cleanup_workspace(workspace)

            # Exponential backoff between retries
            if attempt < retry_count:
                await asyncio.sleep(2 ** attempt)

        # If all retries failed, raise the last encountered error
        if last_error:
            raise last_error

        # This should never be reached, but included for type checking
        raise RuntimeError("Unexpected execution failure")

def async_tool(
    timeout: Optional[float] = 30.0,
    workspace_prefix: str = 'mcp_tool_'
):
    """
    Decorator for async tool methods.

    Provides:
    - Automatic workspace management
    - Timeout handling
    - Error logging

    Args:
        timeout: Maximum execution time
        workspace_prefix: Prefix for temporary workspace
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await AsyncToolExecutor.execute(
                func,
                *args,
                timeout=timeout,
                workspace_prefix=workspace_prefix,
                **kwargs
            )
        return wrapper
    return decorator

# Expose main components
__all__ = [
    'AsyncToolExecutor',
    'WorkspaceManager',
    'async_tool',
    'tool_context'
]