"""Worker client for submitting jobs from backend.

Provides HTTP client for communicating with worker container.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging
import httpx

logger = logging.getLogger(__name__)


# ==============================================================================
# Configuration
# ==============================================================================

@dataclass
class WorkerConfig:
    """Configuration for worker client."""
    url: str
    timeout_seconds: int = 60


# ==============================================================================
# Worker Client
# ==============================================================================

class WorkerClient:
    """Client for submitting jobs to worker container."""

    def __init__(self, config: WorkerConfig):
        """
        Initialize worker client.

        Args:
            config: Worker configuration
        """
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds)
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def submit_job(
        self,
        script_name: str,
        arguments: Dict[str, Any],
        timeout_seconds: int = 30
    ) -> Dict[str, Any]:
        """
        Submit job to worker and wait for result.

        Args:
            script_name: Name of script to execute
            arguments: Script arguments
            timeout_seconds: Job execution timeout

        Returns:
            Job result dictionary

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            logger.info(
                f"Submitting job to worker: {script_name}",
                extra={
                    "script": script_name,
                    "arguments": arguments,
                    "timeout": timeout_seconds,
                }
            )

            response = await self.client.post(
                f"{self.config.url}/jobs",
                json={
                    "script_name": script_name,
                    "arguments": arguments,
                    "timeout_seconds": timeout_seconds,
                }
            )
            response.raise_for_status()

            result = response.json()

            logger.info(
                f"Worker job completed: {result.get('job_id')}",
                extra={
                    "job_id": result.get("job_id"),
                    "status": result.get("status"),
                    "execution_time_ms": result.get("execution_time_ms"),
                }
            )

            return result

        except httpx.HTTPError as e:
            logger.error(
                f"Worker job submission failed: {e}",
                extra={
                    "script": script_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        """
        Get job result by ID.

        Args:
            job_id: Job ID

        Returns:
            Job result dictionary

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            response = await self.client.get(
                f"{self.config.url}/jobs/{job_id}"
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to get job: {job_id}",
                extra={"job_id": job_id, "error": str(e)},
            )
            raise

    async def list_jobs(self) -> list[Dict[str, Any]]:
        """
        List all jobs.

        Returns:
            List of job result dictionaries

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            response = await self.client.get(f"{self.config.url}/jobs")
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Failed to list jobs: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Check worker health.

        Returns:
            True if worker is healthy, False otherwise
        """
        try:
            response = await self.client.get(
                f"{self.config.url}/health",
                timeout=httpx.Timeout(5.0)  # Short timeout for health check
            )
            return response.status_code == 200

        except Exception as e:
            logger.warning(
                f"Worker health check failed: {e}",
                extra={"error": str(e)}
            )
            return False
