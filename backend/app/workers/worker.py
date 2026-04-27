"""Worker executor for isolated script execution.

Executes deterministic scripts in a constrained environment with:
- Timeout enforcement
- Resource limits (via Docker)
- Structured logging
- Error handling
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
import logging
import subprocess
import asyncio
import uuid
import json
import os

logger = logging.getLogger(__name__)


# ==============================================================================
# Job Status and Result Types
# ==============================================================================

class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class JobRequest:
    """Request to execute a job."""
    script_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30


@dataclass
class JobResult:
    """Result of job execution."""
    job_id: str
    status: JobStatus
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
        }


# ==============================================================================
# Worker Executor
# ==============================================================================

class WorkerExecutor:
    """Executes deterministic scripts in isolated environment."""

    def __init__(self, workspace_path: str = "/workspace"):
        """
        Initialize worker executor.

        Args:
            workspace_path: Path to isolated workspace directory
        """
        self.workspace_path = workspace_path
        self.jobs: Dict[str, JobResult] = {}
        self.scripts_path = os.path.join(
            os.path.dirname(__file__),
            "scripts"
        )

    def _generate_job_id(self) -> str:
        """Generate unique job ID."""
        return str(uuid.uuid4())[:8]

    def _get_script_path(self, script_name: str) -> str:
        """Get full path to script file."""
        # Support both .py files and bare script names
        if not script_name.endswith(".py"):
            script_name = f"{script_name}.py"

        script_path = os.path.join(self.scripts_path, script_name)

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script not found: {script_name}")

        return script_path

    async def _run_script(
        self,
        script_path: str,
        arguments: Dict[str, Any],
        timeout_seconds: int
    ) -> subprocess.CompletedProcess:
        """
        Run script with subprocess.

        Args:
            script_path: Path to script file
            arguments: Script arguments (passed via stdin as JSON)
            timeout_seconds: Execution timeout

        Returns:
            CompletedProcess result
        """
        # Prepare arguments as JSON
        args_json = json.dumps(arguments)

        # Run script with timeout
        process = await asyncio.create_subprocess_exec(
            "python",
            script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=args_json.encode()),
                timeout=timeout_seconds
            )

            return subprocess.CompletedProcess(
                args=["python", script_path],
                returncode=process.returncode or 0,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
            )

        except asyncio.TimeoutError:
            # Kill process on timeout
            process.kill()
            await process.wait()
            raise subprocess.TimeoutExpired(
                cmd=["python", script_path],
                timeout=timeout_seconds
            )

    async def execute_job(self, request: JobRequest) -> JobResult:
        """
        Execute a job with timeout and error handling.

        Args:
            request: Job request

        Returns:
            Job result
        """
        job_id = self._generate_job_id()
        start_time = datetime.now(timezone.utc)

        # Log job execution
        logger.info(
            f"Executing job: {job_id}",
            extra={
                "job_id": job_id,
                "script": request.script_name,
                "arguments": request.arguments,
                "timeout": request.timeout_seconds,
            },
        )

        try:
            # Get script path
            script_path = self._get_script_path(request.script_name)

            # Execute script
            result = await self._run_script(
                script_path,
                request.arguments,
                request.timeout_seconds
            )

            execution_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            # Check for script errors
            if result.returncode != 0:
                job_result = JobResult(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    output=result.stdout,
                    error=result.stderr or "Script exited with non-zero code",
                    execution_time_ms=execution_time,
                    timestamp=start_time,
                )
            else:
                job_result = JobResult(
                    job_id=job_id,
                    status=JobStatus.SUCCESS,
                    output=result.stdout,
                    error=None,
                    execution_time_ms=execution_time,
                    timestamp=start_time,
                )

        except subprocess.TimeoutExpired:
            execution_time = request.timeout_seconds * 1000
            job_result = JobResult(
                job_id=job_id,
                status=JobStatus.TIMEOUT,
                output=None,
                error=f"Job timeout after {request.timeout_seconds}s",
                execution_time_ms=execution_time,
                timestamp=start_time,
            )

            logger.warning(
                f"Job timeout: {job_id}",
                extra={
                    "job_id": job_id,
                    "timeout_seconds": request.timeout_seconds,
                },
            )

        except FileNotFoundError as e:
            execution_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000
            job_result = JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                output=None,
                error=str(e),
                execution_time_ms=execution_time,
                timestamp=start_time,
            )

            logger.error(
                f"Script not found: {job_id}",
                extra={
                    "job_id": job_id,
                    "script": request.script_name,
                    "error": str(e),
                },
            )

        except Exception as e:
            execution_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000
            job_result = JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                output=None,
                error=f"Unexpected error: {str(e)}",
                execution_time_ms=execution_time,
                timestamp=start_time,
            )

            logger.error(
                f"Job execution failed: {job_id}",
                extra={
                    "job_id": job_id,
                    "error": str(e),
                },
                exc_info=True,
            )

        # Log result
        logger.info(
            f"Job completed: {job_id}",
            extra={
                **job_result.to_dict(),
                "success": job_result.status == JobStatus.SUCCESS,
            },
        )

        # Store result
        self.jobs[job_id] = job_result

        return job_result

    def get_job(self, job_id: str) -> Optional[JobResult]:
        """
        Get job result by ID.

        Args:
            job_id: Job ID

        Returns:
            Job result or None if not found
        """
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[JobResult]:
        """
        Get all job results.

        Returns:
            List of job results
        """
        return list(self.jobs.values())
