"""Tests for workflow classification."""
import pytest

from app.services.workflow_classifier import (
    classify_workflow,
    is_emerging_workflow,
    extract_keywords,
    calculate_confidence,
    detect_subcategory,
    CATEGORY_PATTERNS,
)
from app.models.models import WorkflowCategory


# ==============================================================================
# Classification Tests
# ==============================================================================

def test_classify_bug_fix():
    """Test bug fix classification."""
    requests = [
        "Fix the login bug",
        "Debug the error in payment processing",
        "There's an issue with the API endpoint",
        "The app crashes when I click submit",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.BUG_FIX
        assert result.confidence > 30
        assert len(result.keywords) > 0


def test_classify_feature():
    """Test feature classification."""
    requests = [
        "Create a new dashboard",
        "Add user authentication",
        "Build a reporting module",
        "Implement email notifications",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.FEATURE
        assert result.confidence > 30


def test_classify_analysis():
    """Test analysis classification."""
    requests = [
        "Review the code for security issues",
        "Analyze the performance bottleneck",
        "Explain how the authentication works",
        "Investigate why the tests are failing",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.ANALYSIS
        assert result.confidence > 30


def test_classify_question():
    """Test question classification."""
    requests = [
        "What is the current status?",
        "How does the payment flow work?",
        "Where are the config files?",
        "Can you show me the logs?",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.QUESTION
        assert result.confidence > 0


def test_classify_workflow():
    """Test multi-step workflow classification."""
    requests = [
        "First create a user, then add permissions, and finally send notification",
        "Run the tests, then deploy to staging, and after that notify the team",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.WORKFLOW
        assert result.confidence > 30


def test_classify_creative():
    """Test creative classification."""
    requests = [
        "Design a new architecture for the API",
        "Brainstorm ideas for the landing page",
        "Draft a proposal for the new feature",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.CREATIVE
        assert result.confidence > 30


def test_classify_admin():
    """Test admin classification."""
    requests = [
        "Configure the database settings",
        "Manage user permissions",
        "Deploy the application",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.ADMIN
        assert result.confidence > 30


def test_classify_unknown():
    """Test unknown classification."""
    requests = [
        "",
        "asdf",
        "xyz123",
    ]

    for request in requests:
        result = classify_workflow(request)
        assert result.category == WorkflowCategory.UNKNOWN
        assert result.confidence <= 30


def test_subcategory_detection():
    """Test subcategory detection."""
    result = classify_workflow("Debug the authentication error")
    assert result.category == WorkflowCategory.BUG_FIX
    assert result.subcategory in ["error_investigation", "debugging"]

    result = classify_workflow("Create a new user dashboard")
    assert result.category == WorkflowCategory.FEATURE
    assert result.subcategory == "new_feature"

    result = classify_workflow("Review the code for issues")
    assert result.category == WorkflowCategory.ANALYSIS
    assert result.subcategory == "code_review"


def test_confidence_calculation():
    """Test confidence score calculation."""
    # High confidence - multiple keywords
    result = classify_workflow("Fix the bug in the error handling code")
    assert result.confidence > 60

    # Medium confidence - single keyword
    result = classify_workflow("Fix this")
    assert 30 < result.confidence <= 60

    # Low confidence - ambiguous
    result = classify_workflow("Do something")
    assert result.confidence <= 40


# ==============================================================================
# Helper Function Tests
# ==============================================================================

def test_extract_keywords():
    """Test keyword extraction."""
    text = "Fix the bug in the authentication module"
    patterns = CATEGORY_PATTERNS[WorkflowCategory.BUG_FIX]

    keywords = extract_keywords(text, patterns)
    assert "fix" in keywords
    assert "bug" in keywords
    assert len(keywords) >= 2


def test_calculate_confidence():
    """Test confidence calculation."""
    # Many matches
    confidence = calculate_confidence(["bug", "fix", "error"], 10, 100)
    assert confidence > 50

    # Few matches
    confidence = calculate_confidence(["bug"], 10, 50)
    assert confidence > 0
    assert confidence < 50

    # No matches
    confidence = calculate_confidence([], 10, 100)
    assert confidence == 0


def test_detect_subcategory():
    """Test subcategory detection."""
    patterns = CATEGORY_PATTERNS[WorkflowCategory.BUG_FIX]

    subcategory = detect_subcategory("Debug the error", patterns["subcategories"])
    assert subcategory == "debugging"

    subcategory = detect_subcategory("Fix the issue", patterns["subcategories"])
    assert subcategory == "fix_implementation"

    subcategory = detect_subcategory("Random text", patterns["subcategories"])
    assert subcategory is None


def test_is_emerging_workflow():
    """Test emerging workflow detection."""
    # Unknown category
    assert is_emerging_workflow(WorkflowCategory.UNKNOWN, 80) is True

    # Low confidence
    assert is_emerging_workflow(WorkflowCategory.FEATURE, 30) is True

    # Known workflow
    assert is_emerging_workflow(WorkflowCategory.FEATURE, 70) is False


def test_empty_request():
    """Test classification of empty request."""
    result = classify_workflow("")
    assert result.category == WorkflowCategory.UNKNOWN
    assert result.confidence == 0
    assert result.keywords == []


def test_ambiguous_request():
    """Test classification of ambiguous request."""
    result = classify_workflow("Can you help me?")
    # Should classify as question due to "can you" and "?"
    assert result.category == WorkflowCategory.QUESTION
    assert result.confidence > 0


def test_multiple_categories():
    """Test request that matches multiple categories."""
    # Should pick the best match
    result = classify_workflow("Fix the bug and add a new feature")
    # Should classify as bug_fix or feature (whichever has higher confidence)
    assert result.category in [WorkflowCategory.BUG_FIX, WorkflowCategory.FEATURE]
    assert result.confidence > 30
