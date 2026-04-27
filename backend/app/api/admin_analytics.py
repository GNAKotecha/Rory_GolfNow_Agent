"""Admin analytics API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.session import get_db
from app.models.models import (
    User,
    Session as SessionModel,
    Message as MessageModel,
    WorkflowClassification,
    ToolCall,
    Approval,
    WorkflowCategory,
    WorkflowOutcome,
    UserRole,
)
from app.api.auth_deps import get_approved_user
from app.services.workflow_analytics import (
    count_by_category,
    get_outcome_distribution,
    get_workflow_trends,
    separate_known_vs_emerging,
)

router = APIRouter(prefix="/admin/analytics", tags=["admin"])


# ==============================================================================
# Response Models
# ==============================================================================

class UserStats(BaseModel):
    """User statistics."""
    total_users: int
    approved_users: int
    pending_users: int
    admin_users: int


class SessionStats(BaseModel):
    """Session statistics."""
    total_sessions: int
    active_sessions_7d: int
    active_sessions_30d: int
    avg_messages_per_session: float


class CategoryStat(BaseModel):
    """Workflow category statistic."""
    category: str
    count: int
    percentage: float


class OutcomeStat(BaseModel):
    """Workflow outcome statistic."""
    category: str
    success: int
    partial: int
    failed: int
    escalated: int
    pending: int
    total: int
    success_rate: float


class TrendStat(BaseModel):
    """Workflow trend statistic."""
    category: str
    subcategory: Optional[str]
    count: int
    first_seen: datetime
    last_seen: datetime
    unique_users: int
    avg_confidence: float


class ToolUsageStat(BaseModel):
    """Tool usage statistic."""
    tool_name: str
    call_count: int
    success_count: int
    error_count: int
    success_rate: float


class ApprovalStat(BaseModel):
    """Approval statistic."""
    request_type: str
    total: int
    approved: int
    rejected: int
    pending: int
    approval_rate: float


class WorkflowMaturityStat(BaseModel):
    """Workflow maturity statistics."""
    known_workflows: int
    emerging_workflows: int
    total_workflows: int
    maturity_rate: float


class AdminAnalytics(BaseModel):
    """Complete admin analytics response."""
    user_stats: UserStats
    session_stats: SessionStats
    top_categories: List[CategoryStat]
    outcomes: List[OutcomeStat]
    repeated_workflows: List[TrendStat]
    workflow_maturity: WorkflowMaturityStat
    tool_usage: List[ToolUsageStat]
    approval_stats: List[ApprovalStat]
    generated_at: datetime


# ==============================================================================
# Helper Functions
# ==============================================================================

def verify_admin(current_user: User):
    """Verify user has admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )


def get_user_statistics(db: Session) -> UserStats:
    """Get user statistics."""
    total = db.query(func.count(User.id)).scalar()

    approved = db.query(func.count(User.id)).filter(
        User.approval_status == "approved"
    ).scalar()

    pending = db.query(func.count(User.id)).filter(
        User.approval_status == "pending"
    ).scalar()

    admins = db.query(func.count(User.id)).filter(
        User.role == UserRole.ADMIN
    ).scalar()

    return UserStats(
        total_users=total or 0,
        approved_users=approved or 0,
        pending_users=pending or 0,
        admin_users=admins or 0,
    )


def get_session_statistics(db: Session) -> SessionStats:
    """Get session statistics."""
    total = db.query(func.count(SessionModel.id)).scalar()

    # Active sessions in last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_7d = db.query(func.count(SessionModel.id)).filter(
        SessionModel.updated_at >= seven_days_ago
    ).scalar()

    # Active sessions in last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    active_30d = db.query(func.count(SessionModel.id)).filter(
        SessionModel.updated_at >= thirty_days_ago
    ).scalar()

    # Average messages per session
    message_count = db.query(func.count(MessageModel.id)).scalar()
    avg_messages = (message_count / total) if total > 0 else 0.0

    return SessionStats(
        total_sessions=total or 0,
        active_sessions_7d=active_7d or 0,
        active_sessions_30d=active_30d or 0,
        avg_messages_per_session=round(avg_messages, 2),
    )


def get_tool_usage_statistics(db: Session, days: int = 30) -> List[ToolUsageStat]:
    """Get tool usage statistics."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Aggregate tool usage
    query = db.query(
        ToolCall.tool_name,
        func.count(ToolCall.id).label("call_count"),
        func.sum(func.case((ToolCall.error.is_(None), 1), else_=0)).label("success_count"),
        func.sum(func.case((ToolCall.error.isnot(None), 1), else_=0)).label("error_count"),
    ).filter(
        ToolCall.created_at >= start_date
    ).group_by(
        ToolCall.tool_name
    ).order_by(
        desc("call_count")
    )

    results = query.all()

    tool_stats = []
    for r in results:
        success_rate = (r.success_count / r.call_count * 100) if r.call_count > 0 else 0.0
        tool_stats.append(
            ToolUsageStat(
                tool_name=r.tool_name,
                call_count=r.call_count,
                success_count=r.success_count or 0,
                error_count=r.error_count or 0,
                success_rate=round(success_rate, 2),
            )
        )

    return tool_stats


def get_approval_statistics(db: Session, days: int = 30) -> List[ApprovalStat]:
    """Get approval statistics."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Aggregate approvals
    query = db.query(
        Approval.request_type,
        func.count(Approval.id).label("total"),
        func.sum(func.case((Approval.approved == 1, 1), else_=0)).label("approved"),
        func.sum(func.case((Approval.approved == 0, 1), else_=0)).label("rejected"),
        func.sum(func.case((Approval.approved.is_(None), 1), else_=0)).label("pending"),
    ).filter(
        Approval.created_at >= start_date
    ).group_by(
        Approval.request_type
    ).order_by(
        desc("total")
    )

    results = query.all()

    approval_stats = []
    for r in results:
        approval_rate = (r.approved / r.total * 100) if r.total > 0 else 0.0
        approval_stats.append(
            ApprovalStat(
                request_type=r.request_type,
                total=r.total,
                approved=r.approved or 0,
                rejected=r.rejected or 0,
                pending=r.pending or 0,
                approval_rate=round(approval_rate, 2),
            )
        )

    return approval_stats


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.get("", response_model=AdminAnalytics)
async def get_admin_analytics(
    days: int = 30,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    Get comprehensive admin analytics.

    Requires: Admin role.

    Args:
        days: Number of days to look back for time-based stats (default: 30)

    Returns:
        AdminAnalytics with all usage data
    """
    verify_admin(current_user)

    # User and session stats
    user_stats = get_user_statistics(db)
    session_stats = get_session_statistics(db)

    # Workflow category counts
    category_counts = count_by_category(db)
    top_categories = [
        CategoryStat(
            category=c.category,
            count=c.count,
            percentage=c.percentage,
        )
        for c in category_counts
    ]

    # Workflow outcomes
    outcome_distributions = get_outcome_distribution(db)
    outcomes = []
    for o in outcome_distributions:
        success_rate = (o.success / o.total * 100) if o.total > 0 else 0.0
        outcomes.append(
            OutcomeStat(
                category=o.category,
                success=o.success,
                partial=o.partial,
                failed=o.failed,
                escalated=o.escalated,
                pending=o.pending,
                total=o.total,
                success_rate=round(success_rate, 2),
            )
        )

    # Repeated workflows (trends)
    workflow_trends = get_workflow_trends(db, min_count=3, days=days)
    repeated_workflows = [
        TrendStat(
            category=t.category,
            subcategory=t.subcategory,
            count=t.count,
            first_seen=t.first_seen,
            last_seen=t.last_seen,
            unique_users=t.unique_users,
            avg_confidence=t.avg_confidence,
        )
        for t in workflow_trends
    ]

    # Workflow maturity
    maturity_split = separate_known_vs_emerging(db)
    maturity_rate = (
        maturity_split["known"] / maturity_split["total"] * 100
        if maturity_split["total"] > 0 else 0.0
    )
    workflow_maturity = WorkflowMaturityStat(
        known_workflows=maturity_split["known"],
        emerging_workflows=maturity_split["emerging"],
        total_workflows=maturity_split["total"],
        maturity_rate=round(maturity_rate, 2),
    )

    # Tool usage
    tool_usage = get_tool_usage_statistics(db, days=days)

    # Approval stats
    approval_stats = get_approval_statistics(db, days=days)

    return AdminAnalytics(
        user_stats=user_stats,
        session_stats=session_stats,
        top_categories=top_categories,
        outcomes=outcomes,
        repeated_workflows=repeated_workflows,
        workflow_maturity=workflow_maturity,
        tool_usage=tool_usage,
        approval_stats=approval_stats,
        generated_at=datetime.utcnow(),
    )


@router.get("/users", response_model=UserStats)
async def get_user_stats(
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get user statistics. Requires admin role."""
    verify_admin(current_user)
    return get_user_statistics(db)


@router.get("/sessions", response_model=SessionStats)
async def get_session_stats(
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get session statistics. Requires admin role."""
    verify_admin(current_user)
    return get_session_statistics(db)


@router.get("/categories", response_model=List[CategoryStat])
async def get_category_stats(
    days: int = 30,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get workflow category statistics. Requires admin role."""
    verify_admin(current_user)

    start_date = datetime.utcnow() - timedelta(days=days)
    category_counts = count_by_category(db, start_date=start_date)

    return [
        CategoryStat(
            category=c.category,
            count=c.count,
            percentage=c.percentage,
        )
        for c in category_counts
    ]


@router.get("/outcomes", response_model=List[OutcomeStat])
async def get_outcome_stats(
    days: int = 30,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get workflow outcome statistics. Requires admin role."""
    verify_admin(current_user)

    start_date = datetime.utcnow() - timedelta(days=days)
    outcome_distributions = get_outcome_distribution(db, start_date=start_date)

    outcomes = []
    for o in outcome_distributions:
        success_rate = (o.success / o.total * 100) if o.total > 0 else 0.0
        outcomes.append(
            OutcomeStat(
                category=o.category,
                success=o.success,
                partial=o.partial,
                failed=o.failed,
                escalated=o.escalated,
                pending=o.pending,
                total=o.total,
                success_rate=round(success_rate, 2),
            )
        )

    return outcomes


@router.get("/trends", response_model=List[TrendStat])
async def get_trend_stats(
    min_count: int = 3,
    days: int = 30,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get repeated workflow trends. Requires admin role."""
    verify_admin(current_user)

    workflow_trends = get_workflow_trends(db, min_count=min_count, days=days)

    return [
        TrendStat(
            category=t.category,
            subcategory=t.subcategory,
            count=t.count,
            first_seen=t.first_seen,
            last_seen=t.last_seen,
            unique_users=t.unique_users,
            avg_confidence=t.avg_confidence,
        )
        for t in workflow_trends
    ]


@router.get("/tools", response_model=List[ToolUsageStat])
async def get_tool_stats(
    days: int = 30,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get tool usage statistics. Requires admin role."""
    verify_admin(current_user)
    return get_tool_usage_statistics(db, days=days)


@router.get("/approvals", response_model=List[ApprovalStat])
async def get_approval_stats(
    days: int = 30,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get approval statistics. Requires admin role."""
    verify_admin(current_user)
    return get_approval_statistics(db, days=days)
