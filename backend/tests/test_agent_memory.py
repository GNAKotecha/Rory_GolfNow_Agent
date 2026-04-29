"""Tests for agent memory cross-session storage."""
import pytest
from unittest.mock import Mock, MagicMock, call
from datetime import datetime, timezone
import json

from app.services.agent_memory import AgentMemory


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    """Mock database session."""
    db = Mock()
    db.execute = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    return db


@pytest.fixture
def agent_memory(mock_db):
    """Create AgentMemory instance with mocked database."""
    return AgentMemory(mock_db)


# ==============================================================================
# User Preference Storage Tests
# ==============================================================================

def test_store_user_preference_success(agent_memory, mock_db):
    """Test successful user preference storage."""
    agent_memory.store_user_preference(
        user_id=1,
        key="output_format",
        value="verbose"
    )

    # Verify execute was called
    assert mock_db.execute.called
    assert mock_db.commit.called

    # Verify SQL contains expected fields
    call_args = mock_db.execute.call_args
    params = call_args[0][1]
    assert params["user_id"] == 1
    assert params["key"] == "output_format"
    assert json.loads(params["value"]) == "verbose"


def test_store_user_preference_complex_value(agent_memory, mock_db):
    """Test storing complex preference value."""
    complex_value = {
        "theme": "dark",
        "notifications": True,
        "items": [1, 2, 3]
    }

    agent_memory.store_user_preference(
        user_id=2,
        key="settings",
        value=complex_value
    )

    assert mock_db.execute.called
    call_args = mock_db.execute.call_args
    params = call_args[0][1]
    assert json.loads(params["value"]) == complex_value


def test_store_user_preference_upsert(agent_memory, mock_db):
    """Test preference storage uses upsert (ON CONFLICT)."""
    agent_memory.store_user_preference(
        user_id=1,
        key="theme",
        value="light"
    )

    # Verify SQL contains ON CONFLICT clause
    call_args = mock_db.execute.call_args
    sql_text = str(call_args[0][0])
    assert "ON CONFLICT" in sql_text.upper()
    assert "DO UPDATE" in sql_text.upper()


def test_store_user_preference_rollback_on_error(agent_memory, mock_db):
    """Test preference storage rolls back on error."""
    mock_db.execute.side_effect = Exception("Database error")

    with pytest.raises(Exception):
        agent_memory.store_user_preference(
            user_id=1,
            key="test",
            value="value"
        )

    assert mock_db.rollback.called


# ==============================================================================
# User Preference Retrieval Tests
# ==============================================================================

def test_get_user_preferences_empty(agent_memory, mock_db):
    """Test getting preferences when none exist."""
    # Mock empty result
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([]))
    mock_db.execute.return_value = mock_result

    preferences = agent_memory.get_user_preferences(user_id=1)

    assert preferences == {}
    assert mock_db.execute.called


def test_get_user_preferences_single(agent_memory, mock_db):
    """Test getting single user preference."""
    # Mock result with one preference
    mock_row = Mock()
    mock_row.key = "theme"
    mock_row.value = json.dumps("dark")

    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([mock_row]))
    mock_db.execute.return_value = mock_result

    preferences = agent_memory.get_user_preferences(user_id=1)

    assert preferences == {"theme": "dark"}


def test_get_user_preferences_multiple(agent_memory, mock_db):
    """Test getting multiple user preferences."""
    # Mock result with multiple preferences
    mock_rows = [
        Mock(key="theme", value=json.dumps("dark")),
        Mock(key="language", value=json.dumps("en")),
        Mock(key="notifications", value=json.dumps(True)),
    ]

    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter(mock_rows))
    mock_db.execute.return_value = mock_result

    preferences = agent_memory.get_user_preferences(user_id=1)

    assert preferences == {
        "theme": "dark",
        "language": "en",
        "notifications": True,
    }


def test_get_user_preferences_error_handling(agent_memory, mock_db):
    """Test preference retrieval handles errors gracefully."""
    mock_db.execute.side_effect = Exception("Database error")

    preferences = agent_memory.get_user_preferences(user_id=1)

    # Should return empty dict on error, not raise
    assert preferences == {}


# ==============================================================================
# Workflow Outcome Storage Tests
# ==============================================================================

def test_store_workflow_outcome_success(agent_memory, mock_db):
    """Test successful workflow outcome storage."""
    context = {
        "steps": 5,
        "tools_used": ["search", "analyze"],
        "duration_seconds": 12.5,
    }

    agent_memory.store_workflow_outcome(
        user_id=1,
        workflow_type="data_analysis",
        outcome="completed",
        context=context
    )

    assert mock_db.execute.called
    assert mock_db.commit.called

    # Verify parameters
    call_args = mock_db.execute.call_args
    params = call_args[0][1]
    assert params["user_id"] == 1
    assert params["workflow_type"] == "data_analysis"
    assert params["outcome"] == "completed"
    assert json.loads(params["context"]) == context


def test_store_workflow_outcome_rollback_on_error(agent_memory, mock_db):
    """Test workflow outcome storage rolls back on error."""
    mock_db.execute.side_effect = Exception("Database error")

    with pytest.raises(Exception):
        agent_memory.store_workflow_outcome(
            user_id=1,
            workflow_type="test",
            outcome="failed",
            context={}
        )

    assert mock_db.rollback.called


# ==============================================================================
# Past Outcomes Retrieval Tests
# ==============================================================================

def test_get_relevant_past_outcomes_empty(agent_memory, mock_db):
    """Test getting past outcomes when none exist."""
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([]))
    mock_db.execute.return_value = mock_result

    outcomes = agent_memory.get_relevant_past_outcomes(
        user_id=1,
        workflow_type="test"
    )

    assert outcomes == []


def test_get_relevant_past_outcomes_single(agent_memory, mock_db):
    """Test getting single past outcome."""
    timestamp = datetime.now(timezone.utc)
    context = {"steps": 3}

    mock_row = Mock()
    mock_row.outcome = "completed"
    mock_row.context = json.dumps(context)
    mock_row.created_at = timestamp

    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([mock_row]))
    mock_db.execute.return_value = mock_result

    outcomes = agent_memory.get_relevant_past_outcomes(
        user_id=1,
        workflow_type="test"
    )

    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "completed"
    assert outcomes[0]["context"] == context
    assert outcomes[0]["created_at"] == timestamp


def test_get_relevant_past_outcomes_with_limit(agent_memory, mock_db):
    """Test getting past outcomes respects limit."""
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([]))
    mock_db.execute.return_value = mock_result

    agent_memory.get_relevant_past_outcomes(
        user_id=1,
        workflow_type="test",
        limit=3
    )

    # Verify limit was passed to query
    call_args = mock_db.execute.call_args
    params = call_args[0][1]
    assert params["limit"] == 3


def test_get_relevant_past_outcomes_error_handling(agent_memory, mock_db):
    """Test past outcomes retrieval handles errors gracefully."""
    mock_db.execute.side_effect = Exception("Database error")

    outcomes = agent_memory.get_relevant_past_outcomes(
        user_id=1,
        workflow_type="test"
    )

    # Should return empty list on error, not raise
    assert outcomes == []


# ==============================================================================
# Domain Knowledge Storage Tests
# ==============================================================================

def test_store_domain_knowledge_success(agent_memory, mock_db):
    """Test successful domain knowledge storage."""
    agent_memory.store_domain_knowledge(
        user_id=1,
        domain="golf_booking",
        knowledge="Peak hours are 7-9am on weekends",
        source="api_analysis"
    )

    assert mock_db.execute.called
    assert mock_db.commit.called

    # Verify parameters
    call_args = mock_db.execute.call_args
    params = call_args[0][1]
    assert params["user_id"] == 1
    assert params["domain"] == "golf_booking"
    assert params["knowledge"] == "Peak hours are 7-9am on weekends"
    assert params["source"] == "api_analysis"


def test_store_domain_knowledge_rollback_on_error(agent_memory, mock_db):
    """Test domain knowledge storage rolls back on error."""
    mock_db.execute.side_effect = Exception("Database error")

    with pytest.raises(Exception):
        agent_memory.store_domain_knowledge(
            user_id=1,
            domain="test",
            knowledge="test knowledge",
            source="test"
        )

    assert mock_db.rollback.called


# ==============================================================================
# Domain Knowledge Retrieval Tests
# ==============================================================================

def test_get_domain_knowledge_empty(agent_memory, mock_db):
    """Test getting domain knowledge when none exists."""
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([]))
    mock_db.execute.return_value = mock_result

    knowledge = agent_memory.get_domain_knowledge(
        user_id=1,
        domain="test"
    )

    assert knowledge == []


def test_get_domain_knowledge_single(agent_memory, mock_db):
    """Test getting single domain knowledge item."""
    mock_row = Mock()
    mock_row.knowledge = "Test knowledge item"

    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([mock_row]))
    mock_db.execute.return_value = mock_result

    knowledge = agent_memory.get_domain_knowledge(
        user_id=1,
        domain="test"
    )

    assert knowledge == ["Test knowledge item"]


def test_get_domain_knowledge_multiple(agent_memory, mock_db):
    """Test getting multiple domain knowledge items."""
    mock_rows = [
        Mock(knowledge="Knowledge 1"),
        Mock(knowledge="Knowledge 2"),
        Mock(knowledge="Knowledge 3"),
    ]

    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter(mock_rows))
    mock_db.execute.return_value = mock_result

    knowledge = agent_memory.get_domain_knowledge(
        user_id=1,
        domain="test"
    )

    assert knowledge == ["Knowledge 1", "Knowledge 2", "Knowledge 3"]


def test_get_domain_knowledge_with_limit(agent_memory, mock_db):
    """Test getting domain knowledge respects limit."""
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([]))
    mock_db.execute.return_value = mock_result

    agent_memory.get_domain_knowledge(
        user_id=1,
        domain="test",
        limit=5
    )

    # Verify limit was passed to query
    call_args = mock_db.execute.call_args
    params = call_args[0][1]
    assert params["limit"] == 5


def test_get_domain_knowledge_error_handling(agent_memory, mock_db):
    """Test domain knowledge retrieval handles errors gracefully."""
    mock_db.execute.side_effect = Exception("Database error")

    knowledge = agent_memory.get_domain_knowledge(
        user_id=1,
        domain="test"
    )

    # Should return empty list on error, not raise
    assert knowledge == []


# ==============================================================================
# Transaction Batching Tests
# ==============================================================================

def test_batch_context_manager_success(agent_memory, mock_db):
    """Test batch context manager commits on success."""
    with agent_memory.batch():
        agent_memory.store_user_preference(1, "key1", "value1")
        agent_memory.store_user_preference(1, "key2", "value2")

    # Verify operations were batched (no intermediate commits)
    assert mock_db.execute.call_count == 2
    # Single commit at end of batch
    assert mock_db.commit.call_count == 1
    assert not mock_db.rollback.called


def test_batch_context_manager_rollback_on_error(agent_memory, mock_db):
    """Test batch context manager rolls back on error."""
    mock_db.execute.side_effect = [None, Exception("Database error")]

    with pytest.raises(Exception, match="Database error"):
        with agent_memory.batch():
            agent_memory.store_user_preference(1, "key1", "value1")
            agent_memory.store_user_preference(1, "key2", "value2")  # Fails

    # Verify rollback was called
    assert mock_db.rollback.called
    assert mock_db.commit.call_count == 0


def test_batch_with_mixed_operations(agent_memory, mock_db):
    """Test batch with different memory operations."""
    with agent_memory.batch():
        agent_memory.store_user_preference(1, "pref", "value")
        agent_memory.store_workflow_outcome(1, "test", "success", {"data": "test"})
        agent_memory.store_domain_knowledge(1, "golf", "knowledge", "source")

    # Verify all operations executed
    assert mock_db.execute.call_count == 3
    # Single commit at end
    assert mock_db.commit.call_count == 1


def test_non_batch_operations_still_commit_individually(agent_memory, mock_db):
    """Test operations outside batch still commit individually."""
    # Reset commit counter
    mock_db.commit.reset_mock()

    agent_memory.store_user_preference(1, "key1", "value1")
    assert mock_db.commit.call_count == 1

    agent_memory.store_user_preference(1, "key2", "value2")
    assert mock_db.commit.call_count == 2


def test_batch_mode_flag_resets_after_context(agent_memory, mock_db):
    """Test batch mode flag is properly reset after context exits."""
    assert agent_memory._batch_mode is False

    with agent_memory.batch():
        assert agent_memory._batch_mode is True

    assert agent_memory._batch_mode is False


def test_batch_mode_resets_even_on_error(agent_memory, mock_db):
    """Test batch mode flag resets even when error occurs."""
    mock_db.execute.side_effect = Exception("Error")

    assert agent_memory._batch_mode is False

    with pytest.raises(Exception):
        with agent_memory.batch():
            assert agent_memory._batch_mode is True
            agent_memory.store_user_preference(1, "key", "value")

    # Flag should be reset
    assert agent_memory._batch_mode is False
