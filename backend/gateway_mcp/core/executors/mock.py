"""
Mock Executor Backend

For unit and integration testing without external dependencies.
"""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable

from gateway_mcp.core.executors.base import (
    ExecResult,
    ExecutorBackend,
    HTTPResult,
    JobEvent,
    JobHandle,
    JobStatus,
)


@dataclass
class MockCall:
    """Record of a mock executor call."""
    
    method: str
    service: str
    args: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class MockResponse:
    """Configured response for a mock call."""
    
    # For run_command / submit_command
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    
    # For query_db
    rows: list[dict[str, Any]] = field(default_factory=list)
    
    # For call_http
    status_code: int = 200
    body: dict[str, Any] | list[Any] | str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    
    # Error simulation
    raise_error: Exception | None = None


class MockExecutorBackend:
    """
    Mock executor for testing.
    
    Usage:
        mock = MockExecutorBackend()
        
        # Configure responses
        mock.set_response("teesheet", MockResponse(
            stdout='{"club_id": 1, "name": "Test Club"}',
            exit_code=0,
        ))
        
        # Run tests
        result = await mock.run_command("teesheet", ["new-club", ...], 30)
        
        # Verify calls
        assert len(mock.calls) == 1
        assert mock.calls[0].service == "teesheet"
    """
    
    def __init__(self):
        self.calls: list[MockCall] = []
        self.responses: dict[str, MockResponse] = {}
        self.default_response = MockResponse()
        
        # Optional callback for dynamic responses
        self.response_callback: Callable[[str, str, dict], MockResponse] | None = None
    
    def reset(self) -> None:
        """Clear all calls and responses."""
        self.calls.clear()
        self.responses.clear()
        self.response_callback = None
    
    def set_response(self, service: str, response: MockResponse) -> None:
        """Set response for a specific service."""
        self.responses[service] = response
    
    def set_response_callback(
        self,
        callback: Callable[[str, str, dict], MockResponse],
    ) -> None:
        """Set a callback for dynamic response generation."""
        self.response_callback = callback
    
    def _get_response(self, call_method: str, service: str, args: dict) -> MockResponse:
        """Get response for a call."""
        if self.response_callback:
            return self.response_callback(call_method, service, args)
        return self.responses.get(service, self.default_response)
    
    def _record_call(self, call_method: str, service: str, **kwargs) -> None:
        """Record a call for verification."""
        self.calls.append(MockCall(
            method=call_method,
            service=service,
            args=kwargs,
        ))
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> ExecResult:
        """Mock command execution."""
        self._record_call("run_command", service, argv=argv, timeout=timeout)
        
        response = self._get_response("run_command", service, {"argv": argv})
        
        if response.raise_error:
            raise response.raise_error
        
        return ExecResult(
            exit_code=response.exit_code,
            stdout=response.stdout,
            stderr=response.stderr,
            duration_ms=10,  # Mock duration
        )
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """Mock job submission."""
        self._record_call("submit_command", service, argv=argv, timeout=timeout)
        
        response = self._get_response("submit_command", service, {"argv": argv})
        
        if response.raise_error:
            raise response.raise_error
        
        return MockJobHandle(
            job_id=f"mock-job-{len(self.calls)}",
            response=response,
            backend=self,
        )
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """Mock database query."""
        self._record_call("query_db", db, query=query, params=params)
        
        response = self._get_response("query_db", db, {"query": query, "params": params})
        
        if response.raise_error:
            raise response.raise_error
        
        return response.rows
    
    async def call_http(
        self,
        service: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HTTPResult:
        """Mock HTTP call."""
        self._record_call(
            "call_http",
            service,
            method=method,
            path=path,
            body=body,
            headers=headers,
        )
        
        response = self._get_response("call_http", service, {
            "method": method,
            "path": path,
            "body": body,
        })
        
        if response.raise_error:
            raise response.raise_error
        
        return HTTPResult(
            status_code=response.status_code,
            body=response.body,
            headers=response.headers,
            duration_ms=5,
        )


class MockJobHandle(JobHandle):
    """Mock job handle for testing."""
    
    def __init__(
        self,
        job_id: str,
        response: MockResponse,
        backend: MockExecutorBackend,
    ):
        self.job_id = job_id
        self._response = response
        self._backend = backend
        self._status = JobStatus.SUCCEEDED
        self._cancelled = False
    
    async def status(self) -> JobStatus:
        if self._cancelled:
            return JobStatus.CANCELLED
        return self._status
    
    async def stream(self) -> AsyncIterator[JobEvent]:
        """Stream job events (mock implementation yields one completion event)."""
        yield JobEvent(
            event_type="status",
            data="completed",
            timestamp="2026-05-10T00:00:00Z",
        )
    
    async def result(self) -> ExecResult:
        if self._response.raise_error:
            raise self._response.raise_error
        
        return ExecResult(
            exit_code=self._response.exit_code,
            stdout=self._response.stdout,
            stderr=self._response.stderr,
            duration_ms=10,
        )
    
    async def cancel(self) -> None:
        self._cancelled = True
        self._status = JobStatus.CANCELLED


# Type check
_: ExecutorBackend = MockExecutorBackend()  # type: ignore
