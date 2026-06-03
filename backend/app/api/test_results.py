"""
Test Results API - Admin endpoints for querying E2E test results.

Provides endpoints to:
- Submit test run results
- Query test history with filtering
- Analyze trends over time
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from app.db.session import get_db
from app.models.test_run import TestRun, TestScenarioResult
from app.api.auth_deps import get_current_user
from app.models.models import User, UserRole

router = APIRouter(prefix="/api/admin/test-results", tags=["test-results"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.post("/report")
async def submit_test_results(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
) -> dict:
    """
    Submit test run results.
    
    Expected data format:
    {
        "timestamp": "2026-06-03T...",
        "environment": "dev",
        "total_scenarios": 15,
        "passed": 14,
        "failed": 1,
        "duration_seconds": 45.3,
        "tags": ["core"],
        "scenarios": [...]
    }
    """
    try:
        # Create TestRun
        test_run = TestRun(
            run_id=str(uuid.uuid4()),
            tenant_id=admin.tenant_id,
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            environment=data.get("environment", "dev"),
            total_scenarios=data.get("total_scenarios", 0),
            passed=data.get("passed", 0),
            failed=data.get("failed", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            tags=data.get("tags", [])
        )
        db.add(test_run)
        db.flush()

        # Create scenario results
        for scenario_data in data.get("scenarios", []):
            scenario_result = TestScenarioResult(
                test_run_id=test_run.id,
                scenario_name=scenario_data.get("scenario_name", "unknown"),
                success=scenario_data.get("success", False),
                turn_count=scenario_data.get("turn_count", 0),
                tool_calls_count=scenario_data.get("tool_calls_count", 0),
                error_message=scenario_data.get("error_message"),
                turn_results=scenario_data.get("turn_results", [])
            )
            db.add(scenario_result)

        db.commit()

        return {
            "success": True,
            "run_id": test_run.run_id,
            "message": f"Stored {len(data.get('scenarios', []))} scenario results"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to store results: {str(e)}")


@router.get("/")
async def list_test_results(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    environment: Optional[str] = None,
    scenario_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
) -> dict:
    """
    List test results with optional filtering.
    
    Query parameters:
    - limit: Results per page (default 50)
    - offset: Pagination offset (default 0)
    - environment: Filter by environment (dev/staging/prod)
    - scenario_name: Filter by scenario name
    - start_date: ISO datetime filter (after)
    - end_date: ISO datetime filter (before)
    """
    try:
        # Build query
        query = db.query(TestRun).filter(TestRun.tenant_id == admin.tenant_id)

        if environment:
            query = query.filter(TestRun.environment == environment)

        if start_date:
            start = datetime.fromisoformat(start_date)
            query = query.filter(TestRun.timestamp >= start)

        if end_date:
            end = datetime.fromisoformat(end_date)
            query = query.filter(TestRun.timestamp <= end)

        # Count total
        total = query.count()

        # Apply pagination
        runs = query.order_by(desc(TestRun.timestamp)).limit(limit).offset(offset).all()

        # Build response with scenarios
        results = []
        for run in runs:
            scenarios = db.query(TestScenarioResult).filter(
                TestScenarioResult.test_run_id == run.id
            ).all()

            # Apply scenario filter if provided
            if scenario_name:
                scenarios = [s for s in scenarios if scenario_name.lower() in s.scenario_name.lower()]

            results.append({
                "run_id": run.run_id,
                "timestamp": run.timestamp.isoformat(),
                "environment": run.environment,
                "total_scenarios": run.total_scenarios,
                "passed": run.passed,
                "failed": run.failed,
                "pass_rate": (run.passed / run.total_scenarios * 100) if run.total_scenarios > 0 else 0,
                "duration_seconds": run.duration_seconds,
                "tags": run.tags,
                "scenarios": [
                    {
                        "name": s.scenario_name,
                        "success": s.success,
                        "turns": s.turn_count,
                        "tool_calls": s.tool_calls_count,
                        "error": s.error_message
                    }
                    for s in scenarios
                ]
            })

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query failed: {str(e)}")


@router.get("/trends")
async def test_result_trends(
    days: int = Query(7, ge=1, le=90),
    environment: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
) -> dict:
    """
    Get test result trends over the specified number of days.
    
    Query parameters:
    - days: Number of days to analyze (default 7, max 90)
    - environment: Filter by environment
    """
    try:
        # Date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Query runs in date range
        query = db.query(TestRun).filter(
            and_(
                TestRun.tenant_id == admin.tenant_id,
                TestRun.timestamp >= start_date,
                TestRun.timestamp <= end_date
            )
        )

        if environment:
            query = query.filter(TestRun.environment == environment)

        runs = query.order_by(TestRun.timestamp).all()

        if not runs:
            return {
                "period_days": days,
                "environment": environment or "all",
                "data": [],
                "summary": {
                    "avg_pass_rate": 0.0,
                    "trend": "no_data"
                }
            }

        # Group by day
        daily_data = {}
        for run in runs:
            day_key = run.timestamp.date().isoformat()
            if day_key not in daily_data:
                daily_data[day_key] = {"runs": 0, "passed": 0, "total": 0}

            daily_data[day_key]["runs"] += 1
            daily_data[day_key]["passed"] += run.passed
            daily_data[day_key]["total"] += run.total_scenarios

        # Calculate trend line
        data_points = [
            {
                "date": day,
                "pass_rate": (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0,
                "runs": stats["runs"],
                "passed": stats["passed"],
                "total": stats["total"]
            }
            for day, stats in sorted(daily_data.items())
        ]

        # Calculate average and trend
        pass_rates = [d["pass_rate"] for d in data_points]
        avg_pass_rate = sum(pass_rates) / len(pass_rates) if pass_rates else 0

        # Simple trend detection
        if len(pass_rates) >= 2:
            recent = pass_rates[-3:] if len(pass_rates) >= 3 else pass_rates
            old = pass_rates[:-3] if len(pass_rates) > 3 else pass_rates[0:1]
            recent_avg = sum(recent) / len(recent)
            old_avg = sum(old) / len(old)

            if recent_avg > old_avg + 5:
                trend = "improving"
            elif recent_avg < old_avg - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "period_days": days,
            "environment": environment or "all",
            "data": data_points,
            "summary": {
                "total_runs": len(runs),
                "avg_pass_rate": round(avg_pass_rate, 2),
                "trend": trend
            }
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Trend analysis failed: {str(e)}")
