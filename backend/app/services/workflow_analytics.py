"""Workflow analytics service.

Aggregates and analyzes workflow classification data for product insights.
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.models import (
    WorkflowClassification,
    WorkflowCategory,
    WorkflowOutcome,
)
from app.services.workflow_classifier import is_emerging_workflow
import logging

logger = logging.getLogger(__name__)


@dataclass
class CategoryCount:
    """Count of workflows by category."""
    category: str
    count: int
    percentage: float


@dataclass
class OutcomeDistribution:
    """Distribution of outcomes for a category."""
    category: str
    success: int
    partial: int
    failed: int
    escalated: int
    pending: int
    total: int


@dataclass
class UserWorkflowStats:
    """Workflow statistics for a user."""
    user_id: int
    total_requests: int
    category_breakdown: List[CategoryCount]
    outcome_distribution: List[OutcomeDistribution]
    emerging_workflows: int
    known_workflows: int


@dataclass
class WorkflowTrend:
    """Trend data for a workflow category."""
    category: str
    subcategory: Optional[str]
    count: int
    first_seen: datetime
    last_seen: datetime
    unique_users: int
    avg_confidence: float


# ==============================================================================
# Analytics Queries
# ==============================================================================

def count_by_user_and_category(
    user_id: int,
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[CategoryCount]:
    """
    Count workflows by category for a user.

    Args:
        user_id: User ID
        db: Database session
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of CategoryCount objects
    """
    query = db.query(
        WorkflowClassification.category,
        func.count(WorkflowClassification.id).label("count")
    ).filter(WorkflowClassification.user_id == user_id)

    # Apply date filters
    if start_date:
        query = query.filter(WorkflowClassification.created_at >= start_date)
    if end_date:
        query = query.filter(WorkflowClassification.created_at <= end_date)

    query = query.group_by(WorkflowClassification.category)
    results = query.all()

    # Calculate total and percentages
    total = sum(r.count for r in results)

    category_counts = [
        CategoryCount(
            category=r.category.value,
            count=r.count,
            percentage=round((r.count / total * 100), 2) if total > 0 else 0.0,
        )
        for r in results
    ]

    # Sort by count descending
    category_counts.sort(key=lambda x: x.count, reverse=True)

    return category_counts


def count_by_category(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[CategoryCount]:
    """
    Count workflows by category across all users.

    Args:
        db: Database session
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of CategoryCount objects
    """
    query = db.query(
        WorkflowClassification.category,
        func.count(WorkflowClassification.id).label("count")
    )

    # Apply date filters
    if start_date:
        query = query.filter(WorkflowClassification.created_at >= start_date)
    if end_date:
        query = query.filter(WorkflowClassification.created_at <= end_date)

    query = query.group_by(WorkflowClassification.category)
    results = query.all()

    total = sum(r.count for r in results)

    category_counts = [
        CategoryCount(
            category=r.category.value,
            count=r.count,
            percentage=round((r.count / total * 100), 2) if total > 0 else 0.0,
        )
        for r in results
    ]

    category_counts.sort(key=lambda x: x.count, reverse=True)

    return category_counts


def get_outcome_distribution(
    db: Session,
    user_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[OutcomeDistribution]:
    """
    Get outcome distribution by category.

    Args:
        db: Database session
        user_id: Optional user ID filter
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of OutcomeDistribution objects
    """
    query = db.query(
        WorkflowClassification.category,
        WorkflowClassification.outcome,
        func.count(WorkflowClassification.id).label("count")
    )

    # Apply filters
    if user_id:
        query = query.filter(WorkflowClassification.user_id == user_id)
    if start_date:
        query = query.filter(WorkflowClassification.created_at >= start_date)
    if end_date:
        query = query.filter(WorkflowClassification.created_at <= end_date)

    query = query.group_by(
        WorkflowClassification.category,
        WorkflowClassification.outcome
    )
    results = query.all()

    # Aggregate by category
    category_outcomes = {}
    for r in results:
        category = r.category.value
        if category not in category_outcomes:
            category_outcomes[category] = {
                "success": 0,
                "partial": 0,
                "failed": 0,
                "escalated": 0,
                "pending": 0,
            }
        category_outcomes[category][r.outcome.value] = r.count

    # Convert to OutcomeDistribution objects
    distributions = []
    for category, outcomes in category_outcomes.items():
        total = sum(outcomes.values())
        distributions.append(
            OutcomeDistribution(
                category=category,
                success=outcomes["success"],
                partial=outcomes["partial"],
                failed=outcomes["failed"],
                escalated=outcomes["escalated"],
                pending=outcomes["pending"],
                total=total,
            )
        )

    distributions.sort(key=lambda x: x.total, reverse=True)

    return distributions


def separate_known_vs_emerging(
    db: Session,
    user_id: Optional[int] = None,
    confidence_threshold: int = 40,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, int]:
    """
    Separate known workflows from emerging workflows.

    Args:
        db: Database session
        user_id: Optional user ID filter
        confidence_threshold: Threshold for known vs emerging
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Dict with 'known' and 'emerging' counts
    """
    query = db.query(
        WorkflowClassification.category,
        WorkflowClassification.confidence,
    )

    # Apply filters
    if user_id:
        query = query.filter(WorkflowClassification.user_id == user_id)
    if start_date:
        query = query.filter(WorkflowClassification.created_at >= start_date)
    if end_date:
        query = query.filter(WorkflowClassification.created_at <= end_date)

    results = query.all()

    known = 0
    emerging = 0

    for r in results:
        if is_emerging_workflow(r.category, r.confidence, confidence_threshold):
            emerging += 1
        else:
            known += 1

    return {
        "known": known,
        "emerging": emerging,
        "total": known + emerging,
    }


def get_user_workflow_stats(
    user_id: int,
    db: Session,
    days: int = 30,
) -> UserWorkflowStats:
    """
    Get comprehensive workflow statistics for a user.

    Args:
        user_id: User ID
        db: Database session
        days: Number of days to look back

    Returns:
        UserWorkflowStats object
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    # Get category breakdown
    category_breakdown = count_by_user_and_category(
        user_id,
        db,
        start_date=start_date,
    )

    # Get outcome distribution
    outcome_distribution = get_outcome_distribution(
        db,
        user_id=user_id,
        start_date=start_date,
    )

    # Get known vs emerging
    workflow_split = separate_known_vs_emerging(
        db,
        user_id=user_id,
        start_date=start_date,
    )

    return UserWorkflowStats(
        user_id=user_id,
        total_requests=workflow_split["total"],
        category_breakdown=category_breakdown,
        outcome_distribution=outcome_distribution,
        emerging_workflows=workflow_split["emerging"],
        known_workflows=workflow_split["known"],
    )


def get_workflow_trends(
    db: Session,
    min_count: int = 3,
    days: int = 30,
) -> List[WorkflowTrend]:
    """
    Get trending workflows (repeated patterns).

    Args:
        db: Database session
        min_count: Minimum count to be considered a trend
        days: Number of days to look back

    Returns:
        List of WorkflowTrend objects
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    query = db.query(
        WorkflowClassification.category,
        WorkflowClassification.subcategory,
        func.count(WorkflowClassification.id).label("count"),
        func.min(WorkflowClassification.created_at).label("first_seen"),
        func.max(WorkflowClassification.created_at).label("last_seen"),
        func.count(func.distinct(WorkflowClassification.user_id)).label("unique_users"),
        func.avg(WorkflowClassification.confidence).label("avg_confidence"),
    ).filter(
        WorkflowClassification.created_at >= start_date
    ).group_by(
        WorkflowClassification.category,
        WorkflowClassification.subcategory,
    ).having(
        func.count(WorkflowClassification.id) >= min_count
    )

    results = query.all()

    trends = [
        WorkflowTrend(
            category=r.category.value,
            subcategory=r.subcategory,
            count=r.count,
            first_seen=r.first_seen,
            last_seen=r.last_seen,
            unique_users=r.unique_users,
            avg_confidence=round(r.avg_confidence, 2),
        )
        for r in results
    ]

    # Sort by count descending
    trends.sort(key=lambda x: x.count, reverse=True)

    return trends


def log_unknown_workflow(
    classification: WorkflowClassification,
    db: Session,
):
    """
    Log unknown/uncategorized workflow for review.

    Args:
        classification: WorkflowClassification record
        db: Database session
    """
    if classification.category == WorkflowCategory.UNKNOWN:
        logger.warning(
            f"Unknown workflow detected",
            extra={
                "user_id": classification.user_id,
                "session_id": classification.session_id,
                "message_id": classification.message_id,
                "request_text": classification.request_text[:200],
                "confidence": classification.confidence,
            }
        )
