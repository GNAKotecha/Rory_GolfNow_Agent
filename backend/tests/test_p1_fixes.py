"""
Tests for P1 fixes:
- Issue 1: MCP isError=true classification (should parse message, not use http_status=200)
- Issue 2: Per-club token cache usage (authenticate_club token used by subsequent HTTP calls)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from app.services.mcp_client import MCPToolResult
from app.services.error_handler import (
    AgentErrorHandler,
    ErrorType,
    classify_error_from_message,
    is_error_retryable,
)


# ============================================================================
# Issue 1: MCP isError=true classification
# ============================================================================

class TestMCPErrorClassification:
    """Test that MCP semantic errors (isError=true) are classified correctly."""
    
    def test_mcp_error_result_has_no_http_status(self):
        """When isError=true, http_status should be None to allow message parsing."""
        # This simulates the expected behavior after fix
        result = MCPToolResult(
            success=False,
            error="401 Unauthorized: Invalid API key",
            http_status=None,  # NOT 200 anymore
        )
        
        assert result.http_status is None
        assert result.success is False
    
    def test_mcp_auth_error_message_classifies_as_auth_failure(self):
        """Auth error in MCP content should be classified as AUTH_FAILURE."""
        handler = AgentErrorHandler()
        
        # Without http_status, should parse message
        error_type = handler.classify_error(
            "401 Unauthorized: Invalid API key",
            http_status=None,  # No HTTP status override
        )
        assert error_type == ErrorType.AUTH_FAILURE
        
        # Also test 403
        error_type = handler.classify_error(
            "403 Forbidden: Access denied",
            http_status=None,
        )
        assert error_type == ErrorType.AUTH_FAILURE
    
    def test_mcp_validation_error_classifies_correctly(self):
        """Validation error in MCP content should be classified as VALIDATION_ERROR."""
        handler = AgentErrorHandler()
        
        error_type = handler.classify_error(
            "Validation error: Missing required field 'club_id'",
            http_status=None,
        )
        assert error_type == ErrorType.VALIDATION_ERROR
        
        error_type = handler.classify_error(
            "400 Bad Request: Invalid format for date parameter",
            http_status=None,
        )
        assert error_type == ErrorType.VALIDATION_ERROR
    
    def test_mcp_auth_error_is_not_retryable(self):
        """AUTH_FAILURE from MCP error should not be retryable."""
        handler = AgentErrorHandler()
        
        error_type = handler.classify_error(
            "401 Unauthorized: Token expired",
            http_status=None,
        )
        assert error_type == ErrorType.AUTH_FAILURE
        assert not is_error_retryable(error_type)
    
    def test_mcp_validation_error_is_not_retryable(self):
        """VALIDATION_ERROR from MCP error should not be retryable."""
        handler = AgentErrorHandler()
        
        error_type = handler.classify_error(
            "Schema validation failed: Invalid enum value",
            http_status=None,
        )
        assert error_type == ErrorType.VALIDATION_ERROR
        assert not is_error_retryable(error_type)
    
    def test_http_200_success_unchanged(self):
        """HTTP 200 success path should still work correctly."""
        result = MCPToolResult(
            success=True,
            result={"data": "value"},
            http_status=200,
        )
        
        assert result.success is True
        assert result.http_status == 200
        assert result.result == {"data": "value"}
    
    def test_http_error_status_still_classified_from_status(self):
        """Non-200 HTTP transport errors should still use status code."""
        handler = AgentErrorHandler()
        
        # When actual HTTP error occurs, classify from status
        error_type = handler.classify_error(
            "Server error",
            http_status=503,
        )
        assert error_type == ErrorType.TOOL_FAILURE
        
        error_type = handler.classify_error(
            "Not found",
            http_status=404,
        )
        assert error_type == ErrorType.TOOL_NOT_FOUND


# ============================================================================
# Issue 2: Per-club token cache usage
# ============================================================================

class TestPerClubTokenCache:
    """Test that per-club token cache is used for subsequent HTTP calls."""
    
    @pytest.fixture
    def mock_brs_provider(self):
        """Create a mock BRS auth provider with singleton reset."""
        from gateway_mcp.core.brs_auth import BRSAuthProvider, BRSToken
        
        # Clear singleton for test isolation
        BRSAuthProvider._instance = None
        
        provider = BRSAuthProvider(
            teesheet_url="https://test.brs.dev",
            client_id="test_client",
            client_secret="test_secret",
        )
        BRSAuthProvider._instance = provider
        
        yield provider
        
        # Cleanup
        BRSAuthProvider._instance = None
    
    def test_get_cached_token_returns_none_when_no_cache(self, mock_brs_provider):
        """get_cached_token returns None when no token cached."""
        token = mock_brs_provider.get_cached_token("test_club")
        assert token is None
    
    def test_get_cached_token_returns_valid_token(self, mock_brs_provider):
        """get_cached_token returns cached token when available."""
        from gateway_mcp.core.brs_auth import BRSToken
        
        # Simulate a cached token
        mock_brs_provider._tokens["test_club"] = BRSToken(
            access_token="cached_token_123",
            expires_at=time.time() + 3600,
            club_id="test_club",
        )
        
        token = mock_brs_provider.get_cached_token("test_club")
        assert token is not None
        assert token.access_token == "cached_token_123"
    
    def test_get_cached_token_returns_none_for_expired(self, mock_brs_provider):
        """get_cached_token returns None for expired tokens."""
        from gateway_mcp.core.brs_auth import BRSToken
        
        # Simulate an expired token
        mock_brs_provider._tokens["test_club"] = BRSToken(
            access_token="expired_token",
            expires_at=time.time() - 100,  # Expired
            club_id="test_club",
        )
        
        token = mock_brs_provider.get_cached_token("test_club")
        assert token is None
    
    def test_get_cached_auth_headers_returns_headers_when_cached(self, mock_brs_provider):
        """get_cached_auth_headers returns headers when token cached."""
        from gateway_mcp.core.brs_auth import BRSToken
        
        mock_brs_provider._tokens["test_club"] = BRSToken(
            access_token="bearer_token_xyz",
            expires_at=time.time() + 3600,
            club_id="test_club",
        )
        
        headers = mock_brs_provider.get_cached_auth_headers("test_club")
        assert headers is not None
        assert headers["Authorization"] == "Bearer bearer_token_xyz"
    
    def test_get_cached_auth_headers_returns_none_when_not_cached(self, mock_brs_provider):
        """get_cached_auth_headers returns None when no token cached."""
        headers = mock_brs_provider.get_cached_auth_headers("unknown_club")
        assert headers is None
    
    def test_clear_token_clears_specific_club(self, mock_brs_provider):
        """clear_token with club_id only clears that club."""
        from gateway_mcp.core.brs_auth import BRSToken
        
        mock_brs_provider._tokens["club_a"] = BRSToken(
            access_token="token_a",
            expires_at=time.time() + 3600,
            club_id="club_a",
        )
        mock_brs_provider._tokens["club_b"] = BRSToken(
            access_token="token_b",
            expires_at=time.time() + 3600,
            club_id="club_b",
        )
        
        mock_brs_provider.clear_token(club_id="club_a")
        
        assert mock_brs_provider.get_cached_token("club_a") is None
        assert mock_brs_provider.get_cached_token("club_b") is not None
    
    @pytest.mark.asyncio
    async def test_get_brs_auth_headers_uses_cached_token(self, mock_brs_provider):
        """get_brs_auth_headers uses cached token when club_id provided."""
        from gateway_mcp.core.brs_auth import get_brs_auth_headers, BRSToken
        
        # Pre-cache a token
        mock_brs_provider._tokens["cached_club"] = BRSToken(
            access_token="cached_bearer_token",
            expires_at=time.time() + 3600,
            club_id="cached_club",
        )
        
        # Should use cached token, not require api_key
        headers = await get_brs_auth_headers(club_id="cached_club")
        assert headers["Authorization"] == "Bearer cached_bearer_token"
    
    @pytest.mark.asyncio
    async def test_get_brs_auth_headers_no_cache_returns_empty(self, mock_brs_provider):
        """get_brs_auth_headers returns empty when no cache and no static key."""
        from gateway_mcp.core.brs_auth import get_brs_auth_headers
        
        # No cached token, no static key - should return empty
        headers = await get_brs_auth_headers(club_id="unknown_club")
        assert headers == {}
    
    @pytest.mark.asyncio
    async def test_static_key_mode_still_works(self):
        """Static API key mode still works when configured."""
        from gateway_mcp.core.brs_auth import BRSAuthProvider, BRSToken
        
        # Clear singleton
        BRSAuthProvider._instance = None
        
        provider = BRSAuthProvider(
            teesheet_url="https://test.brs.dev",
            client_id="test_client",
            client_secret="test_secret",
            api_key="static_api_key",  # Static key configured
        )
        BRSAuthProvider._instance = provider
        
        try:
            # Mock the token exchange
            with patch.object(provider, '_exchange_token', new_callable=AsyncMock) as mock_exchange:
                mock_exchange.return_value = BRSToken(
                    access_token="static_token",
                    expires_at=time.time() + 3600,
                    club_id="static",
                )
                
                token = await provider.get_token()
                assert token.access_token == "static_token"
                mock_exchange.assert_called_once_with("static_api_key", "static")
        finally:
            BRSAuthProvider._instance = None


class TestHTTPCallsWithClubId:
    """Test that HTTP calls properly pass club_id for authentication."""
    
    @pytest.mark.asyncio
    async def test_make_http_call_passes_club_id(self):
        """make_http_call passes club_id to get_brs_auth_headers."""
        from gateway_mcp.core.executors.http_utils import make_http_call
        from gateway_mcp.core.config import Settings, ServiceConfig
        
        settings = MagicMock(spec=Settings)
        settings.services = {
            "teesheet": MagicMock(spec=ServiceConfig, url="https://api.test"),
        }
        
        with patch('gateway_mcp.core.executors.http_utils.get_brs_auth_headers', new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = {"Authorization": "Bearer test"}
            
            with patch('httpx.AsyncClient') as mock_client:
                # Use MagicMock for response - httpx Response.json() is synchronous
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"success": True}
                mock_response.headers = {}
                
                mock_session = AsyncMock()
                mock_session.request.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_session
                
                await make_http_call(
                    settings=settings,
                    service="teesheet",
                    method="GET",
                    path="/api/clubs",
                    club_id="my_club_123",
                )
                
                # Verify club_id was passed to get_brs_auth_headers
                mock_auth.assert_called_once_with(club_id="my_club_123")
    
    @pytest.mark.asyncio
    async def test_http_401_clears_specific_club_token(self):
        """401 response clears the specific club's token, not all tokens."""
        from gateway_mcp.core.executors.http_utils import make_http_call
        from gateway_mcp.core.config import Settings, ServiceConfig
        from gateway_mcp.core.brs_auth import BRSAuthProvider, BRSToken
        
        # Setup provider with two club tokens
        BRSAuthProvider._instance = None
        provider = BRSAuthProvider(
            teesheet_url="https://test.brs.dev",
            client_id="test",
            client_secret="test",
        )
        BRSAuthProvider._instance = provider
        
        provider._tokens["club_a"] = BRSToken(
            access_token="token_a", expires_at=time.time() + 3600, club_id="club_a"
        )
        provider._tokens["club_b"] = BRSToken(
            access_token="token_b", expires_at=time.time() + 3600, club_id="club_b"
        )
        
        settings = MagicMock(spec=Settings)
        settings.services = {
            "teesheet": MagicMock(spec=ServiceConfig, url="https://api.test"),
        }
        
        try:
            with patch('gateway_mcp.core.executors.http_utils.get_brs_auth_headers', new_callable=AsyncMock) as mock_auth:
                mock_auth.return_value = {"Authorization": "Bearer token_a"}
                
                with patch('httpx.AsyncClient') as mock_client:
                    # Use MagicMock for response - httpx Response.json() is synchronous
                    mock_response = MagicMock()
                    mock_response.status_code = 401  # Auth failure
                    mock_response.json.return_value = {"error": "Unauthorized"}
                    mock_response.headers = {}
                    mock_response.text = "Unauthorized"
                    
                    mock_session = AsyncMock()
                    mock_session.request.return_value = mock_response
                    mock_client.return_value.__aenter__.return_value = mock_session
                    
                    result = await make_http_call(
                        settings=settings,
                        service="teesheet",
                        method="GET",
                        path="/api/clubs",
                        club_id="club_a",
                    )
                    
                    assert result.status_code == 401
            
            # Verify club_a token was cleared, but club_b remains
            assert provider.get_cached_token("club_a") is None
            assert provider.get_cached_token("club_b") is not None
            
        finally:
            BRSAuthProvider._instance = None
