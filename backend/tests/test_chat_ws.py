"""Tests for WebSocket chat endpoint authentication."""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from app.models.models import User, UserRole, ApprovalStatus


@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def mock_user():
    """Mock approved user."""
    user = Mock(spec=User)
    user.id = 1
    user.email = "test@example.com"
    user.name = "Test User"
    user.role = UserRole.USER
    user.approval_status = ApprovalStatus.APPROVED
    return user


@pytest.mark.asyncio
async def test_get_user_from_token_invalid():
    """Test user authentication with invalid token."""
    from app.api.chat_ws import get_user_from_token

    mock_db = Mock()

    with pytest.raises(ValueError, match="Invalid authentication token"):
        with patch("app.api.chat_ws.decode_access_token", return_value=None):
            await get_user_from_token("invalid_token", mock_db)


@pytest.mark.asyncio
async def test_get_user_from_token_no_sub():
    """Test user authentication with token missing sub."""
    from app.api.chat_ws import get_user_from_token

    mock_db = Mock()

    with pytest.raises(ValueError, match="Invalid token payload"):
        with patch("app.api.chat_ws.decode_access_token", return_value={}):
            await get_user_from_token("token", mock_db)


@pytest.mark.asyncio
async def test_get_user_from_token_invalid_user_id():
    """Test user authentication with invalid user ID format."""
    from app.api.chat_ws import get_user_from_token

    mock_db = Mock()

    with pytest.raises(ValueError, match="Invalid user ID"):
        with patch("app.api.chat_ws.decode_access_token", return_value={"sub": "not_a_number"}):
            await get_user_from_token("token", mock_db)


@pytest.mark.asyncio
async def test_get_user_from_token_user_not_found():
    """Test user authentication when user doesn't exist."""
    from app.api.chat_ws import get_user_from_token

    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(ValueError, match="User not found"):
        with patch("app.api.chat_ws.decode_access_token", return_value={"sub": "999"}):
            await get_user_from_token("token", mock_db)


@pytest.mark.asyncio
async def test_get_user_from_token_not_approved(mock_user):
    """Test user authentication when user not approved."""
    from app.api.chat_ws import get_user_from_token

    mock_db = Mock()
    mock_user.approval_status = ApprovalStatus.PENDING
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    with pytest.raises(ValueError, match="not approved"):
        with patch("app.api.chat_ws.decode_access_token", return_value={"sub": "1"}):
            await get_user_from_token("token", mock_db)


@pytest.mark.asyncio
async def test_get_user_from_token_success(mock_user):
    """Test successful user authentication."""
    from app.api.chat_ws import get_user_from_token

    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch("app.api.chat_ws.decode_access_token", return_value={"sub": "1"}):
        user = await get_user_from_token("valid_token", mock_db)
        assert user.id == 1
        assert user.email == "test@example.com"
        assert user.approval_status == ApprovalStatus.APPROVED

