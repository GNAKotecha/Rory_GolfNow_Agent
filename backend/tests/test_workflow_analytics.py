"""Tests for workflow analytics."""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.services.workflow_analytics import (
    count_by_user_and_category,
    count_by_category,
    get_outcome_distribution,
    separate_known_vs_emerging,
    get_user_workflow_stats,
    get_workflow_trends,
    log_unknown_workflow,
)
from app.models.models import (
    User,
    Session as SessionModel,
    Message as MessageModel,
    WorkflowClassification,
    WorkflowCategory,
    WorkflowOutcome,
    UserRole,
    ApprovalStatus,
)
from app.db.session import Base


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def db_session(tmp_path):
    """Create a test database session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    user = User(
        email="test@example.com",
        name="Test User",
        password_hash="hashed",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_session(db_session, test_user):
    """Create a test session."""
    session = SessionModel(
        user_id=test_user.id,
        title="Test Session",
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def test_message(db_session, test_session):
    """Create a test message."""
    message = MessageModel(
        session_id=test_session.id,
        role="user",
        content="Test message",
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


def create_classification(
    db_session: Session,
    test_session: SessionModel,
    test_message: MessageModel,
    test_user: User,
    category: WorkflowCategory,
    outcome: WorkflowOutcome,
    confidence: int = 80,
    subcategory: str = None,
) -> WorkflowClassification:
    """Helper to create a workflow classification."""
    classification = WorkflowClassification(
        session_id=test_session.id,
        message_id=test_message.id,
        user_id=test_user.id,
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        outcome=outcome,
        request_text="Test request",
        keywords=["test"],
    )
    db_session.add(classification)
    db_session.commit()
    db_session.refresh(classification)
    return classification


# ==============================================================================
# Count Tests
# ==============================================================================

def test_count_by_user_and_category(db_session, test_user, test_session, test_message):
    """Test counting workflows by user and category."""
    # Create classifications
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS
    )

    # Count by user and category
    counts = count_by_user_and_category(test_user.id, db_session)

    assert len(counts) == 2
    assert counts[0].category == "bug_fix"
    assert counts[0].count == 2
    assert counts[0].percentage == pytest.approx(66.67, rel=0.1)
    assert counts[1].category == "feature"
    assert counts[1].count == 1
    assert counts[1].percentage == pytest.approx(33.33, rel=0.1)


def test_count_by_category(db_session, test_user, test_session, test_message):
    """Test counting workflows by category across all users."""
    # Create classifications
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.ANALYSIS, WorkflowOutcome.SUCCESS
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.ANALYSIS, WorkflowOutcome.SUCCESS
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.QUESTION, WorkflowOutcome.SUCCESS
    )

    # Count by category
    counts = count_by_category(db_session)

    assert len(counts) == 2
    assert counts[0].category == "analysis"
    assert counts[0].count == 2
    assert counts[1].category == "question"
    assert counts[1].count == 1


def test_count_with_date_filter(db_session, test_user, test_session, test_message):
    """Test counting with date filters."""
    # Create old classification
    old_classification = create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS
    )
    old_classification.created_at = datetime.utcnow() - timedelta(days=60)
    db_session.commit()

    # Create recent classification
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS
    )

    # Count with date filter (last 30 days)
    start_date = datetime.utcnow() - timedelta(days=30)
    counts = count_by_user_and_category(
        test_user.id,
        db_session,
        start_date=start_date,
    )

    # Should only count recent classification
    assert len(counts) == 1
    assert counts[0].category == "feature"


# ==============================================================================
# Outcome Tests
# ==============================================================================

def test_get_outcome_distribution(db_session, test_user, test_session, test_message):
    """Test getting outcome distribution."""
    # Create classifications with different outcomes
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.FAILED
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS
    )

    # Get outcome distribution
    distributions = get_outcome_distribution(db_session)

    assert len(distributions) == 2

    # Check bug_fix distribution
    bug_fix_dist = next(d for d in distributions if d.category == "bug_fix")
    assert bug_fix_dist.success == 1
    assert bug_fix_dist.failed == 1
    assert bug_fix_dist.total == 2

    # Check feature distribution
    feature_dist = next(d for d in distributions if d.category == "feature")
    assert feature_dist.success == 1
    assert feature_dist.total == 1


def test_outcome_distribution_by_user(db_session, test_user, test_session, test_message):
    """Test outcome distribution filtered by user."""
    # Create classifications
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS
    )

    # Get distribution for user
    distributions = get_outcome_distribution(db_session, user_id=test_user.id)

    assert len(distributions) == 1
    assert distributions[0].category == "bug_fix"


# ==============================================================================
# Emerging Workflow Tests
# ==============================================================================

def test_separate_known_vs_emerging(db_session, test_user, test_session, test_message):
    """Test separating known vs emerging workflows."""
    # Create known workflows (high confidence)
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS,
        confidence=80
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS,
        confidence=70
    )

    # Create emerging workflows (low confidence or unknown)
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.UNKNOWN, WorkflowOutcome.SUCCESS,
        confidence=20
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.ANALYSIS, WorkflowOutcome.SUCCESS,
        confidence=30
    )

    # Separate known vs emerging
    result = separate_known_vs_emerging(db_session, confidence_threshold=40)

    assert result["known"] == 2
    assert result["emerging"] == 2
    assert result["total"] == 4


# ==============================================================================
# User Stats Tests
# ==============================================================================

def test_get_user_workflow_stats(db_session, test_user, test_session, test_message):
    """Test getting comprehensive user stats."""
    # Create various classifications
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS,
        confidence=80
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS,
        confidence=70
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.UNKNOWN, WorkflowOutcome.FAILED,
        confidence=20
    )

    # Get stats
    stats = get_user_workflow_stats(test_user.id, db_session, days=30)

    assert stats.user_id == test_user.id
    assert stats.total_requests == 3
    assert stats.known_workflows == 2
    assert stats.emerging_workflows == 1
    assert len(stats.category_breakdown) > 0
    assert len(stats.outcome_distribution) > 0


# ==============================================================================
# Trend Tests
# ==============================================================================

def test_get_workflow_trends(db_session, test_user, test_session, test_message):
    """Test getting workflow trends."""
    # Create repeated workflows
    for _ in range(5):
        create_classification(
            db_session, test_session, test_message, test_user,
            WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS,
            confidence=80,
            subcategory="debugging"
        )

    for _ in range(3):
        create_classification(
            db_session, test_session, test_message, test_user,
            WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS,
            confidence=75,
            subcategory="new_feature"
        )

    # Get trends (min_count=3)
    trends = get_workflow_trends(db_session, min_count=3, days=30)

    assert len(trends) == 2
    assert trends[0].category == "bug_fix"
    assert trends[0].count == 5
    assert trends[0].subcategory == "debugging"
    assert trends[1].category == "feature"
    assert trends[1].count == 3


def test_workflow_trends_min_count(db_session, test_user, test_session, test_message):
    """Test trends with minimum count threshold."""
    # Create classifications below threshold
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS
    )
    create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS
    )

    # Get trends (min_count=3)
    trends = get_workflow_trends(db_session, min_count=3, days=30)

    # Should return no trends (counts below threshold)
    assert len(trends) == 0


# ==============================================================================
# Logging Tests
# ==============================================================================

def test_log_unknown_workflow(db_session, test_user, test_session, test_message, caplog):
    """Test logging of unknown workflows."""
    import logging

    classification = create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.UNKNOWN, WorkflowOutcome.PENDING,
        confidence=10
    )

    # Log unknown workflow
    with caplog.at_level(logging.WARNING):
        log_unknown_workflow(classification, db_session)

    # Check that warning was logged
    assert "Unknown workflow detected" in caplog.text


def test_log_known_workflow(db_session, test_user, test_session, test_message, caplog):
    """Test that known workflows are not logged as warnings."""
    import logging

    classification = create_classification(
        db_session, test_session, test_message, test_user,
        WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS,
        confidence=80
    )

    # Log workflow (should not log warning for known category)
    with caplog.at_level(logging.WARNING):
        log_unknown_workflow(classification, db_session)

    # Should not have warning
    assert "Unknown workflow detected" not in caplog.text
