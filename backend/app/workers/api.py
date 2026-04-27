"""Worker HTTP API for job submission and status.

Exposes worker executor via FastAPI REST endpoints.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import logging

from app.workers.worker import (
    WorkerExecutor,
    JobRequest,
    JobResult,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Worker API",
    description="Isolated worker for deterministic script execution",
    version="1.0.0"
)

# Initialize worker executor
executor = WorkerExecutor()


# ==============================================================================
# Request/Response Models
# ==============================================================================

class JobSubmitRequest(BaseModel):
    """Job submission request."""
    script_name: str
    arguments: Dict[str, Any] = {}
    timeout_seconds: int = 30


class JobResponse(BaseModel):
    """Job result response."""
    job_id: str
    status: str
    output: str | None
    error: str | None
    execution_time_ms: float
    timestamp: str


# ==============================================================================
# Endpoints
# ==============================================================================

@app.post("/jobs", response_model=JobResponse)
async def submit_job(request: JobSubmitRequest):
    """
    Submit a job for execution.

    Args:
        request: Job submission request

    Returns:
        Job result
    """
    logger.info(
        f"Job submission: {request.script_name}",
        extra={
            "script": request.script_name,
            "arguments": request.arguments,
            "timeout": request.timeout_seconds,
        }
    )

    # Create job request
    job_request = JobRequest(
        script_name=request.script_name,
        arguments=request.arguments,
        timeout_seconds=request.timeout_seconds,
    )

    # Execute job
    result = await executor.execute_job(job_request)

    # Return response
    return JobResponse(**result.to_dict())


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """
    Get job result by ID.

    Args:
        job_id: Job ID

    Returns:
        Job result

    Raises:
        HTTPException: If job not found
    """
    result = executor.get_job(job_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return JobResponse(**result.to_dict())


@app.get("/jobs", response_model=List[JobResponse])
async def list_jobs():
    """
    List all job results.

    Returns:
        List of job results
    """
    results = executor.get_all_jobs()
    return [JobResponse(**r.to_dict()) for r in results]


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "worker",
        "jobs_count": len(executor.jobs),
    }


# ==============================================================================
# Startup/Shutdown
# ==============================================================================

@app.on_event("startup")
async def startup_event():
    """Log startup."""
    logger.info("Worker API starting up")


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown."""
    logger.info("Worker API shutting down")
