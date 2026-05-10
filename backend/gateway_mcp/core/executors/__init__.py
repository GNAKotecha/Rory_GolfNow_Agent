"""
Executor Backends

ExecutorBackend implementations for different environments:
- docker_exec: Local BRS (docker exec)
- k8s_exec: QA BRS (kubectl exec)
- job_runner: Prod BRS (workflow API)
- mcp_proxy: Upstream MCP servers (Atlassian, Github)
- http_rest: Direct external REST (fallback)
- mock: Testing
"""

from gateway_mcp.core.executors.base import (
    ExecResult,
    ExecutorBackend,
    HTTPResult,
    JobEvent,
    JobHandle,
    JobStatus,
)
from gateway_mcp.core.executors.docker_exec import DockerExecBackend
from gateway_mcp.core.executors.http_rest import HTTPAllowlist, HTTPRestBackend
from gateway_mcp.core.executors.job_runner import JobRunnerBackend
from gateway_mcp.core.executors.k8s_exec import K8sExecBackend
from gateway_mcp.core.executors.mcp_proxy import MCPProxyBackend
from gateway_mcp.core.executors.mock import MockExecutorBackend, MockResponse

__all__ = [
    # Protocol and types
    "ExecutorBackend",
    "ExecResult",
    "HTTPResult",
    "JobHandle",
    "JobEvent",
    "JobStatus",
    # Backends
    "DockerExecBackend",
    "K8sExecBackend",
    "JobRunnerBackend",
    "MCPProxyBackend",
    "HTTPRestBackend",
    "HTTPAllowlist",
    "MockExecutorBackend",
    "MockResponse",
]

