"""End-to-end tests for MCP authentication flow (Bug #12 fix).

Tests cover:
- Credential storage via UserMCPCredential model
- Preflight auth check in MCPClient before tool execution
- auth_required result returned when credentials missing or expired
- Valid credentials allow tool call to proceed
- expires_soon triggers refresh attempt (stub path)

These tests use SQLite in-memory and mock the HTTP transport layer
(aiohttp session) so no real MCP server or BRS API is required.
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, MetaData, Table
from app.models.user_mcp_credential import UserMCPCredential
from app.services.mcp_client import MCPClient, MCPToolResult, TOOL_PROVIDER_MAP
from app.config.mcp_config import MCPServerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GATEWAY_CONFIG = MCPServerConfig(
    name="gateway-mcp",
    url="http://localhost:8090/mcp",
    timeout_seconds=10,
    max_retries=0,
)

NON_GATEWAY_CONFIG = MCPServerConfig(
    name="other-mcp",
    url="http://localhost:9000/mcp",
    timeout_seconds=10,
    max_retries=0,
)


def make_memory_db():
    """Create an in-memory SQLite DB with a SQLite-compatible UserMCPCredential table.

    PostgreSQL-specific column types (ARRAY, JSONB) are replaced with JSON/Text
    so tests can run without a real PostgreSQL database. We create the table via
    raw DDL and use the ORM model class on top of it.
    """
    engine = create_engine("sqlite:///:memory:")

    # Create tables manually with SQLite-compatible types
    meta = MetaData()
    # Minimal users table (FK target)
    Table("users", meta,
          Column("id", Integer, primary_key=True),
          Column("email", String(255)))
    # user_mcp_credentials with ARRAY → JSON replacement
    Table("user_mcp_credentials", meta,
          Column("id", Integer, primary_key=True),
          Column("user_id", Integer, nullable=False),
          Column("provider", String(50), nullable=False),
          Column("auth_method", String(20), nullable=False),
          Column("access_token", Text, nullable=False),
          Column("refresh_token", Text),
          Column("token_type", String(20), default="Bearer"),
          Column("expires_at", DateTime),
          Column("scopes", JSON),           # SQLite-compatible
          Column("provider_metadata", JSON), # SQLite-compatible
          Column("created_at", DateTime, default=datetime.utcnow),
          Column("updated_at", DateTime, default=datetime.utcnow))
    meta.create_all(engine)

    Session = sessionmaker(bind=engine)
    return Session()


def store_credential(db, user_id: int, provider: str, expired: bool = False, expires_soon: bool = False):
    """Helper: insert a UserMCPCredential row."""
    if expired:
        expires_at = datetime.utcnow() - timedelta(hours=1)
    elif expires_soon:
        expires_at = datetime.utcnow() + timedelta(minutes=2)
    else:
        expires_at = datetime.utcnow() + timedelta(hours=2)

    cred = UserMCPCredential(
        user_id=user_id,
        provider=provider,
        auth_method="api_key",
        access_token="test_token_xyz",
        token_type="Bearer",
        expires_at=expires_at,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


# ---------------------------------------------------------------------------
# Unit tests: TOOL_PROVIDER_MAP
# ---------------------------------------------------------------------------

class TestToolProviderMap:
    def test_brs_tools_mapped(self):
        assert TOOL_PROVIDER_MAP["get_club_by_name"] == "BRS"
        assert TOOL_PROVIDER_MAP["verify_club_setup"] == "BRS"
        assert TOOL_PROVIDER_MAP["call_api"] == "BRS"

    def test_jira_tools_mapped(self):
        assert TOOL_PROVIDER_MAP["create_jira_issue"] == "Jira"

    def test_unmapped_tool_returns_none(self):
        client = MCPClient(GATEWAY_CONFIG)
        assert client._get_provider_for_tool("nonexistent_tool") is None


# ---------------------------------------------------------------------------
# Unit tests: _preflight_credential_check
# ---------------------------------------------------------------------------

class TestPreflightCredentialCheck:
    def test_no_check_for_non_gateway_client(self):
        """Non-gateway clients skip the preflight check entirely."""
        client = MCPClient(NON_GATEWAY_CONFIG)
        result = client._preflight_credential_check("get_club_by_name", user_id=1)
        assert result is None

    def test_no_check_when_user_id_is_none(self):
        """If no user_id, skip check (system-level call)."""
        client = MCPClient(GATEWAY_CONFIG)
        result = client._preflight_credential_check("get_club_by_name", user_id=None)
        assert result is None

    def test_no_check_for_unmapped_tool(self):
        """Tools not in TOOL_PROVIDER_MAP require no credentials."""
        client = MCPClient(GATEWAY_CONFIG)
        # Patch the DB lookup to confirm it's never called
        with patch.object(client, "_check_user_credential") as mock_check:
            result = client._preflight_credential_check("some_internal_tool", user_id=1)
        assert result is None
        mock_check.assert_not_called()

    def test_auth_required_when_no_credentials(self):
        """Missing credentials return auth_required MCPToolResult."""
        client = MCPClient(GATEWAY_CONFIG)
        with patch.object(client, "_check_user_credential", return_value=None):
            result = client._preflight_credential_check("get_club_by_name", user_id=42)
        assert result is not None
        assert result.success is False
        assert result.error_category == "auth_required"
        assert result.is_semantic_error is True
        assert result.terminal_hint is True
        error_data = json.loads(result.error)
        assert error_data["type"] == "auth_required"
        assert error_data["auth_config"]["provider"] == "BRS"

    def test_auth_required_when_credential_expired(self):
        """Expired credentials return auth_required."""
        db = make_memory_db()
        try:
            cred = store_credential(db, user_id=1, provider="BRS", expired=True)
            client = MCPClient(GATEWAY_CONFIG)
            with patch.object(client, "_check_user_credential", return_value=cred):
                result = client._preflight_credential_check("get_club_by_name", user_id=1)
            assert result is not None
            assert result.error_category == "auth_required"
        finally:
            db.close()

    def test_proceeds_when_credential_valid(self):
        """Valid (non-expired) credentials return None — allow call to proceed."""
        db = make_memory_db()
        try:
            cred = store_credential(db, user_id=1, provider="BRS")
            client = MCPClient(GATEWAY_CONFIG)
            with patch.object(client, "_check_user_credential", return_value=cred):
                result = client._preflight_credential_check("get_club_by_name", user_id=1)
            assert result is None
        finally:
            db.close()

    def test_expires_soon_still_proceeds_if_refresh_fails(self):
        """expires_soon with non-refreshable credential: logs warning, continues."""
        db = make_memory_db()
        try:
            cred = store_credential(db, user_id=1, provider="BRS", expires_soon=True)
            # api_key credentials can_refresh = False (no refresh_token), so refresh is skipped
            assert cred.can_refresh is False
            client = MCPClient(GATEWAY_CONFIG)
            with patch.object(client, "_check_user_credential", return_value=cred):
                result = client._preflight_credential_check("get_club_by_name", user_id=1)
            # Should allow call to proceed since token not yet expired
            assert result is None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Integration tests: call_tool with preflight wired in
# ---------------------------------------------------------------------------

class AsyncContextManagerMock:
    """Async context manager that returns a mock response."""
    def __init__(self, response_mock):
        self._response = response_mock

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


class TestCallToolWithPreflightCheck:
    """Tests for call_tool that exercise the preflight path."""

    def _make_success_response(self):
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={
            "content": [{"type": "text", "text": '{"club_id": 123, "name": "test"}'}],
            "isError": False,
        })
        return resp

    @pytest.mark.asyncio
    async def test_call_tool_returns_auth_required_without_credentials(self):
        """call_tool returns auth_required MCPToolResult when no credentials stored."""
        client = MCPClient(GATEWAY_CONFIG)
        with patch.object(client, "_preflight_credential_check") as mock_preflight:
            mock_preflight.return_value = MCPToolResult(
                success=False,
                error='{"type": "auth_required", "message": "Authentication required"}',
                error_category="auth_required",
                is_semantic_error=True,
                terminal_hint=True,
            )
            result = await client.call_tool("get_club_by_name", {"name": "test"}, user_id=99)

        assert result.success is False
        assert result.error_category == "auth_required"
        assert result.terminal_hint is True
        mock_preflight.assert_called_once_with("get_club_by_name", 99)

    @pytest.mark.asyncio
    async def test_call_tool_proceeds_with_valid_credentials(self):
        """call_tool reaches HTTP transport when preflight returns None."""
        client = MCPClient(GATEWAY_CONFIG)

        success_resp = self._make_success_response()
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManagerMock(success_resp))

        with patch.object(client, "_preflight_credential_check", return_value=None), \
             patch.object(client, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            result = await client.call_tool("get_club_by_name", {"name": "test"}, user_id=1)

        assert result.success is True
        assert result.result == {"club_id": 123, "name": "test"}

    @pytest.mark.asyncio
    async def test_call_tool_no_preflight_for_non_gateway(self):
        """Non-gateway MCP client skips preflight and calls directly."""
        client = MCPClient(NON_GATEWAY_CONFIG)

        success_resp = self._make_success_response()
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManagerMock(success_resp))

        with patch.object(client, "_preflight_credential_check") as mock_preflight, \
             patch.object(client, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            # Non-gateway: preflight returns None immediately (no-op)
            mock_preflight.return_value = None
            result = await client.call_tool("some_tool", {}, user_id=1)

        assert result.success is True


# ---------------------------------------------------------------------------
# Unit tests: UserMCPCredential model properties used in auth check
# ---------------------------------------------------------------------------

class TestUserMCPCredentialModel:
    def test_api_key_not_expired_when_no_expires_at(self):
        db = make_memory_db()
        try:
            cred = UserMCPCredential(
                user_id=1,
                provider="BRS",
                auth_method="api_key",
                access_token="my_api_key",
            )
            db.add(cred)
            db.commit()
            db.refresh(cred)
            assert cred.is_expired is False
            assert cred.expires_soon is False
            assert cred.can_refresh is False
        finally:
            db.close()

    def test_oauth2_credential_can_refresh(self):
        db = make_memory_db()
        try:
            cred = UserMCPCredential(
                user_id=1,
                provider="BRS",
                auth_method="oauth2",
                access_token="access_token",
                refresh_token="refresh_token",
                expires_at=datetime.utcnow() + timedelta(minutes=3),
            )
            db.add(cred)
            db.commit()
            db.refresh(cred)
            assert cred.expires_soon is True
            assert cred.is_expired is False
            assert cred.can_refresh is True
        finally:
            db.close()

    def test_expired_token_detected(self):
        db = make_memory_db()
        try:
            cred = UserMCPCredential(
                user_id=1,
                provider="BRS",
                auth_method="oauth2",
                access_token="old_token",
                expires_at=datetime.utcnow() - timedelta(hours=1),
            )
            db.add(cred)
            db.commit()
            db.refresh(cred)
            assert cred.is_expired is True
        finally:
            db.close()

    def test_get_by_user_and_provider(self):
        db = make_memory_db()
        try:
            cred = store_credential(db, user_id=5, provider="Jira")
            found = UserMCPCredential.get_by_user_and_provider(db, user_id=5, provider="Jira")
            assert found is not None
            assert found.id == cred.id
            not_found = UserMCPCredential.get_by_user_and_provider(db, user_id=5, provider="BRS")
            assert not_found is None
        finally:
            db.close()
